"""Offline API tests using the real ADK runner with a fake model transport."""

import asyncio
import unittest
import io
import shutil
import zlib
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient
from google.adk.models.llm_response import LlmResponse
from google.adk.models.google_llm import Gemini
from google.adk.models.registry import LLMRegistry
from google.genai import types
from google.genai.errors import ClientError

from src.orchestration import main as orchestration_main
from src.orchestration.main import MODEL, TaskRequest, app, run_agent_loop
from src.build import build as firmware_build
from src.build import qemu_gate as firmware_qemu
from src.build.common import StageResult

MODEL_METHOD = "google.adk.models.google_llm.Gemini.generate_content_async"


def fake_model(*, try_invalid_artifacts=False):
    """Replace only Gemini's network call; ADK still discovers and runs the tools."""
    async def generate(model, llm_request, stream=False):
        results = [
            part.function_response
            for content in llm_request.contents
            for part in content.parts or []
            if part.function_response
        ]
        if try_invalid_artifacts:
            sequence = ["flash_before_build", "compile", "test", "flash_wrong_id", "flash", "final"]
        else:
            sequence = ["compile", "test", "flash", "final"]
        step = sequence[len(results)]
        if step == "compile":
            name, args = "compile_firmware", {}
        elif step in ("flash_before_build", "flash_wrong_id"):
            name, args = "flash_firmware", {"artifact_id": "not-a-built-artifact"}
        elif step in ("test", "flash"):
            build = next(result.response for result in results if result.name == "compile_firmware")
            name = "test_firmware" if step == "test" else "flash_firmware"
            args = {"artifact_id": build["artifact_id"]}
        else:
            yield LlmResponse(content=types.Content(role="model", parts=[
                types.Part(text="Private reasoning must not appear in the API.", thought=True),
                types.Part(text="Compilation and the QEMU test succeeded; flashing was simulated. No hardware was contacted."),
            ]))
            return
        yield LlmResponse(content=types.Content(role="model", parts=[
            types.Part(function_call=types.FunctionCall(name=name, args=args)),
        ]))
    return generate


def fake_file_model(operations):
    """Request real ADK file operations without contacting Gemini."""
    async def generate(model, llm_request, stream=False):
        assert set(llm_request.tools_dict) == {
            "ReadFile", "WriteFile", "EditFile", "compile_firmware", "test_firmware", "flash_firmware",
        }  # In particular, shell execution must not be offered to the model.
        results = [
            part.function_response
            for content in llm_request.contents
            for part in content.parts or []
            if part.function_response
        ]
        if len(results) == len(operations):
            yield LlmResponse(content=types.Content(role="model", parts=[
                types.Part(text="File operations finished. Flashing is simulated."),
            ]))
            return
        name, args = operations[len(results)]
        if name in ("test_firmware", "flash_firmware"):
            # test uses the latest successful build; flash uses the latest passing test.
            source = "compile_firmware" if name == "test_firmware" else "test_firmware"
            args = {**args, "artifact_id": next(
                (result.response["artifact_id"] for result in reversed(results)
                 if result.name == source and result.response["status"] == "success"),
                "no-successful-artifact",
            )}
        yield LlmResponse(content=types.Content(role="model", parts=[
            types.Part(function_call=types.FunctionCall(name=name, args=args)),
        ]))
    return generate


class ApiTests(unittest.TestCase):
    def test_configured_model_resolves_to_direct_gemini(self):
        # Resolve without a network call; a models/ prefix breaks ADK routing.
        self.assertIsInstance(LLMRegistry.new_llm(MODEL), Gemini)

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace_root = Path(temporary.name) / "workspace"
        root_patch = patch("src.orchestration.main.WORKSPACE_ROOT", self.workspace_root)
        root_patch.start()
        self.addCleanup(root_patch.stop)
        self.real_build = firmware_build.run

        def test_build(project):
            # Most tests focus on ADK plumbing; real compiler tests follow below.
            binary = project / "kernel.bin"
            binary.write_bytes(b"test binary")
            (project / "kernel.elf").write_bytes(b"test elf")
            return StageResult("build", True, "test build succeeded", artifacts={
                "bin": str(binary), "length": binary.stat().st_size,
            })

        build_patch = patch("src.orchestration.main.firmware_build.run", side_effect=test_build)
        self.build_mock = build_patch.start()
        self.addCleanup(build_patch.stop)
        # The harness rules and the QEMU gate pass by default, like the build above.
        # Tests that check them restore the real functions or return failures.
        self.real_rules = orchestration_main.check_code_rules
        rules_patch = patch("src.orchestration.main.check_code_rules",
                            return_value=StageResult("harness", True, "test rules passed"))
        self.rules_mock = rules_patch.start()
        self.addCleanup(rules_patch.stop)
        qemu_patch = patch("src.orchestration.main.firmware_qemu.run",
                           return_value=StageResult("qemu", True, "test QEMU passed",
                                                    artifacts={"console": "HIL:BOOT\nHIL:DONE\n"}))
        self.qemu_mock = qemu_patch.start()
        self.addCleanup(qemu_patch.stop)
        self.client = TestClient(app)
        # A dummy value passes our configuration check. Network calls are mocked.
        self.environment = patch.dict("os.environ", {"GOOGLE_API_KEY": "offline-test-key"})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def submit(self):
        return self.client.post("/tasks", json={
            "task": "Compile the prepared firmware, flash it if the build succeeds, and tell me what happened.",
        })

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_invalid_task(self):
        for body in ({}, {"task": ""}, {"task": "  "}, {"task": "x" * 10001}):
            self.assertEqual(self.client.post("/tasks", json=body).status_code, 422)

    def test_missing_key(self):
        with patch.dict("os.environ", {"GOOGLE_API_KEY": ""}):
            response = self.submit()
        self.assertEqual(response.status_code, 503)
        self.assertIn("GOOGLE_API_KEY", response.json()["detail"])

    def test_compile_then_flash_through_real_runner(self):
        with patch(MODEL_METHOD, fake_model()):
            response = self.submit()
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertTrue(data["simulated"])
        events = data["tool_events"]
        self.assertEqual([event["name"] for event in events], [
            "compile_firmware", "compile_firmware", "test_firmware", "test_firmware",
            "flash_firmware", "flash_firmware",
        ])
        artifact = events[1]["result"]["artifact_id"]
        self.assertEqual(events[2]["arguments"]["artifact_id"], artifact)
        self.assertEqual(events[3]["result"]["status"], "success")
        self.assertEqual(events[4]["arguments"]["artifact_id"], artifact)
        self.assertEqual(events[5]["result"]["status"], "success")
        self.assertNotIn("Private reasoning", data["final_response"])

    def test_flash_rejects_unbuilt_and_wrong_artifacts(self):
        with patch(MODEL_METHOD, fake_model(try_invalid_artifacts=True)):
            response = self.submit()
        self.assertEqual(response.status_code, 200, response.text)
        results = [event["result"] for event in response.json()["tool_events"] if event["type"] == "tool_result"]
        self.assertEqual([result["status"] for result in results], ["error", "success", "success", "error", "success"])
        self.assertEqual([result["simulated"] for result in results], [True, False, False, True, True])

    def test_new_task_gets_fresh_session_and_build(self):
        with patch(MODEL_METHOD, fake_model()):
            first, second = self.submit().json(), self.submit().json()
        self.assertNotEqual(first["session_id"], second["session_id"])
        self.assertEqual(first["workspace"], second["workspace"])
        self.assertNotEqual(first["tool_events"][1]["result"]["artifact_id"], second["tool_events"][1]["result"]["artifact_id"])

    def test_provider_error_is_not_reported_as_success(self):
        async def broken_model(model, llm_request, stream=False):
            raise ConnectionError("Provider details must not be returned")
            yield  # Make this an async generator, like the actual model method.

        with patch(MODEL_METHOD, broken_model):
            response = self.submit()
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("Provider details", response.text)

    def test_google_error_diagnostic_redacts_key(self):
        async def rejected_model(model, llm_request, stream=False):
            raise ClientError(400, {"error": {
                "code": 400,
                "status": "INVALID_ARGUMENT",
                "message": "API key not valid: offline-test-key",
            }})
            yield

        output = io.StringIO()
        with patch(MODEL_METHOD, rejected_model), redirect_stdout(output):
            response = self.submit()
        self.assertEqual(response.status_code, 502)
        self.assertIn('"google_http_code": 400', output.getvalue())
        self.assertIn("API key not valid: [REDACTED]", output.getvalue())
        self.assertNotIn("offline-test-key", output.getvalue())
        self.assertNotIn("offline-test-key", response.text)

    def test_real_files_persist_after_write_read_edit_and_simulated_build(self):
        operations = [
            ("WriteFile", {"path": "firmware/main.c", "content": "int main(void) { return 0; }\n"}),
            ("ReadFile", {"path": "firmware/main.c"}),
            ("EditFile", {"path": "firmware/main.c", "old_string": "return 0", "new_string": "return 1"}),
            ("ReadFile", {"path": "firmware/main.c"}),
            ("compile_firmware", {}),
            ("test_firmware", {}),
            ("flash_firmware", {}),
        ]
        with patch(MODEL_METHOD, fake_file_model(operations)):
            response = self.submit()
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        workspace = Path(data["workspace"])
        self.assertEqual(workspace, self.workspace_root)
        self.assertEqual((workspace / "firmware/main.c").read_text(), "int main(void) { return 1; }\n")
        results = [event["result"] for event in data["tool_events"] if event["type"] == "tool_result"]
        self.assertEqual([result["status"] for result in results], ["ok", "ok", "ok", "ok", "success", "success", "success"])
        self.assertIn("return 0", results[1]["content"])
        self.assertIn("return 1", results[3]["content"])

    def test_later_request_can_read_and_edit_existing_file(self):
        with patch(MODEL_METHOD, fake_file_model([
            ("WriteFile", {"path": "uart-hello/main.c", "content": "int main(void) { return 0; }\n"}),
        ])):
            first = self.submit()
        self.assertEqual(first.status_code, 200, first.text)
        with patch(MODEL_METHOD, fake_file_model([
            ("ReadFile", {"path": "uart-hello/main.c"}),
            ("EditFile", {"path": "uart-hello/main.c", "old_string": "return 0", "new_string": "return 1"}),
        ])):
            second = self.submit()
        self.assertEqual(second.status_code, 200, second.text)
        self.assertNotEqual(first.json()["session_id"], second.json()["session_id"])
        self.assertEqual(first.json()["workspace"], second.json()["workspace"])
        results = [event["result"] for event in second.json()["tool_events"] if event["type"] == "tool_result"]
        self.assertIn("return 0", results[0]["content"])
        self.assertEqual(results[1]["status"], "ok")
        self.assertIn("return 1", (self.workspace_root / "uart-hello/main.c").read_text())

    def test_file_tools_reject_paths_outside_shared_workspace(self):
        outside = self.workspace_root.parent / "outside.c"
        operations = [
            ("WriteFile", {"path": "../outside.c", "content": "must not be saved"}),
            ("WriteFile", {"path": str(outside), "content": "must not be saved"}),
        ]
        with patch(MODEL_METHOD, fake_file_model(operations)):
            response = self.submit()
        self.assertEqual(response.status_code, 200, response.text)
        results = [event["result"] for event in response.json()["tool_events"] if event["type"] == "tool_result"]
        self.assertTrue(all(result["status"] == "error" for result in results))
        self.assertFalse(outside.exists())

    @unittest.skipUnless(shutil.which(firmware_build.CC) and shutil.which(firmware_build.OBJCOPY), "ARM toolchain not installed")
    def test_agent_writes_and_really_compiles_firmware(self):
        self.build_mock.side_effect = self.real_build
        self.rules_mock.side_effect = self.real_rules
        operations = [
            ("WriteFile", {"path": "demo/src/main.c", "content": 'int main(void) { return 0; }\n'}),
            ("compile_firmware", {"project_dir": "demo"}),
            ("test_firmware", {}),
            ("flash_firmware", {}),
        ]
        with patch(MODEL_METHOD, fake_file_model(operations)):
            response = self.submit()
        self.assertEqual(response.status_code, 200, response.text)
        results = [event["result"] for event in response.json()["tool_events"] if event["type"] == "tool_result"]
        build = results[1]
        self.assertEqual(build["status"], "success", build)
        self.assertFalse(build["simulated"])
        project = self.workspace_root / "demo"
        self.assertTrue((project / "kernel.elf").is_file())
        self.assertTrue((project / "build.log").is_file())
        binary = (project / "kernel.bin").read_bytes()
        self.assertEqual(build["artifacts"]["length"], len(binary))
        self.assertEqual(build["artifacts"]["crc32"], zlib.crc32(binary))
        self.assertEqual(results[2]["status"], "success", results[2])     # QEMU (mocked here)
        self.assertEqual(results[3]["artifact_id"], build["artifact_id"])
        self.assertTrue(results[3]["simulated"])

    @unittest.skipUnless(shutil.which(firmware_build.CC) and shutil.which(firmware_build.OBJCOPY), "ARM toolchain not installed")
    def test_agent_receives_compiler_error_and_can_fix_it(self):
        self.build_mock.side_effect = self.real_build
        self.rules_mock.side_effect = self.real_rules
        operations = [
            ("WriteFile", {"path": "demo/src/main.c", "content": "int main(void) { return 0 }\n"}),
            ("compile_firmware", {"project_dir": "demo"}),
            ("EditFile", {"path": "demo/src/main.c", "old_string": "return 0", "new_string": "return 0;"}),
            ("compile_firmware", {"project_dir": "demo"}),
        ]
        with patch(MODEL_METHOD, fake_file_model(operations)):
            response = self.submit()
        self.assertEqual(response.status_code, 200, response.text)
        builds = [event["result"] for event in response.json()["tool_events"] if event["type"] == "tool_result" and event["name"] == "compile_firmware"]
        self.assertEqual(builds[0]["status"], "error")
        self.assertEqual(builds[0]["blame"], "code")
        self.assertIn("src/main.c", builds[0]["feedback"])
        self.assertIsNone(builds[0]["artifact_id"])
        self.assertEqual(builds[1]["status"], "success", builds[1])

    def test_compile_rejects_project_path_outside_workspace(self):
        with patch(MODEL_METHOD, fake_file_model([("compile_firmware", {"project_dir": ".."})])):
            response = self.submit()
        result = response.json()["tool_events"][1]["result"]
        self.assertEqual(result["status"], "error")
        self.build_mock.assert_not_called()

    def test_missing_compiler_returns_rig_failure(self):
        self.build_mock.side_effect = self.real_build
        operations = [
            ("WriteFile", {"path": "src/main.c", "content": "int main(void) { return 0; }"}),
            ("compile_firmware", {}),
        ]
        with patch.object(firmware_build, "CC", "missing-arm-compiler-for-test"), patch(MODEL_METHOD, fake_file_model(operations)):
            response = self.submit()
        result = response.json()["tool_events"][3]["result"]
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["blame"], "rig")
        self.assertIsNone(result["artifact_id"])

    @unittest.skipUnless(shutil.which(firmware_build.CC), "ARM compiler not installed")
    def test_missing_objcopy_returns_rig_failure(self):
        self.build_mock.side_effect = self.real_build
        operations = [
            ("WriteFile", {"path": "src/main.c", "content": "int main(void) { return 0; }"}),
            ("compile_firmware", {}),
        ]
        with patch.object(firmware_build, "OBJCOPY", "missing-arm-objcopy-for-test"), patch(MODEL_METHOD, fake_file_model(operations)):
            response = self.submit()
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()["tool_events"][3]["result"]
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["blame"], "rig")

    def test_failed_rebuild_invalidates_previous_artifact(self):
        outcomes = [
            StageResult("build", True, "built", artifacts={"bin": "kernel.bin"}),
            StageResult("build", False, "compile failed", feedback="syntax error"),
        ]

        def build_then_fail(project):
            (project / "kernel.elf").write_bytes(b"test elf")   # test_firmware copies this
            return outcomes.pop(0)

        self.build_mock.side_effect = build_then_fail
        operations = [("compile_firmware", {}), ("test_firmware", {}), ("compile_firmware", {}), ("flash_firmware", {})]
        with patch(MODEL_METHOD, fake_file_model(operations)):
            response = self.submit()
        self.assertEqual(response.status_code, 200, response.text)
        results = [event["result"] for event in response.json()["tool_events"] if event["type"] == "tool_result"]
        self.assertEqual([result["status"] for result in results], ["success", "success", "error", "error"])

    def test_harness_rejects_bad_code_before_compiling(self):
        self.rules_mock.side_effect = self.real_rules
        operations = [
            ("WriteFile", {"path": "demo/src/main.c",
                           "content": '#include <stdio.h>\nint main(void) { printf("hi"); return 0; }\n'}),
            ("compile_firmware", {"project_dir": "demo"}),
        ]
        with patch(MODEL_METHOD, fake_file_model(operations)):
            response = self.submit()
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()["tool_events"][3]["result"]
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["failed_stage"], "harness")
        self.assertEqual(result["blame"], "code")
        self.assertIn("stdio", result["feedback"])
        self.assertIsNone(result["artifact_id"])
        self.build_mock.assert_not_called()      # gcc never ran
        self.qemu_mock.assert_not_called()
        # The harness works in a temporary folder and never deletes the agent's files.
        self.assertTrue((self.workspace_root / "demo/src/main.c").is_file())

    def test_test_firmware_runs_qemu_in_project_subfolder(self):
        operations = [
            ("WriteFile", {"path": "demo/src/main.c", "content": "int main(void) { return 0; }\n"}),
            ("compile_firmware", {"project_dir": "demo"}),
            ("test_firmware", {}),
        ]
        with patch(MODEL_METHOD, fake_file_model(operations)):
            response = self.submit()
        self.assertEqual(response.status_code, 200, response.text)
        results = [event["result"] for event in response.json()["tool_events"] if event["type"] == "tool_result"]
        build, test = results[1], results[2]
        self.assertEqual(build["status"], "success", build)
        self.qemu_mock.assert_called_once()        # compile_firmware no longer runs QEMU itself
        test_dir = self.workspace_root.resolve() / "demo" / "test_firmware"
        self.qemu_mock.assert_called_once_with(test_dir / "kernel.elf", expect=None)
        self.assertEqual(test["status"], "success", test)
        self.assertEqual(test["artifact_id"], build["artifact_id"])
        self.assertEqual(test["test_dir"], str(test_dir))
        self.assertIn("HIL:DONE", test["console"])                      # QEMU output reaches the model
        self.assertIn("HIL:DONE", (test_dir / "qemu.log").read_text())  # and is saved in the subfolder

    def test_compile_alone_does_not_run_qemu(self):
        with patch(MODEL_METHOD, fake_file_model([("compile_firmware", {})])):
            response = self.submit()
        self.assertEqual(response.json()["tool_events"][1]["result"]["status"], "success")
        self.qemu_mock.assert_not_called()

    def test_test_firmware_rejects_unbuilt_and_wrong_artifacts(self):
        with patch(MODEL_METHOD, fake_file_model([("test_firmware", {})])):
            response = self.submit()
        result = response.json()["tool_events"][1]["result"]
        self.assertEqual(result["status"], "error")
        self.assertFalse(result["simulated"])
        self.qemu_mock.assert_not_called()

    def test_flash_requires_a_passing_test(self):
        operations = [("compile_firmware", {}), ("flash_firmware", {})]   # skipped test_firmware
        with patch(MODEL_METHOD, fake_file_model(operations)):
            response = self.submit()
        results = [event["result"] for event in response.json()["tool_events"] if event["type"] == "tool_result"]
        self.assertEqual([result["status"] for result in results], ["success", "error"])

    def test_qemu_failure_is_code_blame_and_blocks_flashing(self):
        self.qemu_mock.side_effect = [
            StageResult("qemu", True, "booted and finished"),
            StageResult("qemu", False, "no HIL:DONE after 5s (hang or infinite loop)",
                        feedback="QEMU test failed: hang.\nConsole output:\nHIL:BOOT\nstuck"),
        ]
        operations = [("compile_firmware", {}), ("test_firmware", {}),
                      ("compile_firmware", {}), ("test_firmware", {}), ("flash_firmware", {})]
        with patch(MODEL_METHOD, fake_file_model(operations)):
            response = self.submit()
        self.assertEqual(response.status_code, 200, response.text)
        results = [event["result"] for event in response.json()["tool_events"] if event["type"] == "tool_result"]
        self.assertEqual([result["status"] for result in results], ["success", "success", "success", "error", "error"])
        failed_test = results[3]
        self.assertEqual(failed_test["blame"], "code")
        self.assertIn("stuck", failed_test["feedback"])

    @unittest.skipUnless(
        shutil.which(firmware_build.CC) and shutil.which(firmware_build.OBJCOPY) and shutil.which(firmware_qemu.QEMU),
        "ARM toolchain and qemu-system-arm needed")
    def test_real_harness_build_and_qemu_end_to_end(self):
        self.rules_mock.side_effect = self.real_rules
        self.build_mock.side_effect = self.real_build
        self.qemu_mock.side_effect = firmware_qemu.run
        operations = [
            ("WriteFile", {"path": "demo/src/main.c",
                           "content": '#include "hil.h"\nint main(void) { hil_puts("hello\\n"); return 0; }\n'}),
            ("compile_firmware", {"project_dir": "demo"}),
            ("test_firmware", {}),
        ]
        with patch(MODEL_METHOD, fake_file_model(operations)):
            response = self.submit()
        results = [event["result"] for event in response.json()["tool_events"] if event["type"] == "tool_result"]
        self.assertEqual(results[1]["status"], "success", results[1])
        self.assertEqual(results[2]["status"], "success", results[2])
        self.assertIn("hello", results[2]["console"])

    def test_expect_output_is_passed_to_qemu(self):
        operations = [
            ("WriteFile", {"path": "demo/src/main.c", "content": "int main(void) { for (;;) { } }\n"}),
            ("compile_firmware", {"project_dir": "demo"}),
            ("test_firmware", {"expect_output": "  UART ready  "}),
        ]
        with patch(MODEL_METHOD, fake_file_model(operations)):
            response = self.submit()
        self.assertEqual(response.status_code, 200, response.text)
        test_dir = self.workspace_root.resolve() / "demo" / "test_firmware"
        self.qemu_mock.assert_called_once_with(test_dir / "kernel.elf", expect="UART ready")

    @unittest.skipUnless(
        shutil.which(firmware_build.CC) and shutil.which(firmware_build.OBJCOPY) and shutil.which(firmware_qemu.QEMU),
        "ARM toolchain and qemu-system-arm needed")
    def test_real_endless_firmware_passes_and_can_be_flashed(self):
        # Real firmware never returns from main. It must still pass and be flashable.
        self.rules_mock.side_effect = self.real_rules
        self.build_mock.side_effect = self.real_build
        self.qemu_mock.side_effect = firmware_qemu.run
        endless = '#include "hil.h"\nint main(void) {\n    hil_puts("UART ready\\n");\n    for (;;) { }\n}\n'
        operations = [
            ("WriteFile", {"path": "demo/src/main.c", "content": endless}),
            ("compile_firmware", {"project_dir": "demo"}),
            ("test_firmware", {}),                                  # run-only check
            ("test_firmware", {"expect_output": "UART ready"}),    # output check
            ("test_firmware", {"expect_output": "never printed"}), # must fail
        ]
        with patch(MODEL_METHOD, fake_file_model(operations)):
            response = self.submit()
        results = [event["result"] for event in response.json()["tool_events"] if event["type"] == "tool_result"]
        self.assertEqual(results[1]["status"], "success", results[1])
        self.assertEqual(results[2]["status"], "success", results[2])
        self.assertIn("still running", results[2]["summary"])
        self.assertEqual(results[3]["status"], "success", results[3])
        self.assertIn("UART ready", results[3]["console"])
        self.assertEqual(results[4]["status"], "error")
        self.assertEqual(results[4]["blame"], "code")
        self.assertIn("did not print 'never printed'", results[4]["summary"])

    @unittest.skipUnless(
        shutil.which(firmware_build.CC) and shutil.which(firmware_build.OBJCOPY) and shutil.which(firmware_qemu.QEMU),
        "ARM toolchain and qemu-system-arm needed")
    def test_real_endless_firmware_full_flow_to_flash(self):
        self.rules_mock.side_effect = self.real_rules
        self.build_mock.side_effect = self.real_build
        self.qemu_mock.side_effect = firmware_qemu.run
        endless = '#include "hil.h"\nint main(void) {\n    for (;;) { strobe_pulse(0); }\n}\n'
        operations = [
            ("WriteFile", {"path": "demo/src/main.c", "content": endless}),
            ("compile_firmware", {"project_dir": "demo"}),
            ("test_firmware", {}),
            ("flash_firmware", {}),
        ]
        with patch(MODEL_METHOD, fake_file_model(operations)):
            response = self.submit()
        results = [event["result"] for event in response.json()["tool_events"] if event["type"] == "tool_result"]
        self.assertEqual([result["status"] for result in results], ["ok", "success", "success", "success"], results)


class ProgressTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root_patch = patch("src.orchestration.main.WORKSPACE_ROOT", Path(temporary.name))
        root_patch.start()
        self.addCleanup(root_patch.stop)

    async def test_waiting_logs_model_turns_and_cleans_up(self):
        transport = fake_model()

        async def slow_model(model, llm_request, stream=False):
            await asyncio.sleep(0.04)
            async for response in transport(model, llm_request, stream):
                yield response

        output = io.StringIO()
        with patch(MODEL_METHOD, slow_model), patch(
            "src.orchestration.main.PROGRESS_INTERVAL_SECONDS", 0.01,
        ), redirect_stdout(output):
            result = await run_agent_loop(TaskRequest(task="Compile and flash"))

        text = output.getvalue()
        self.assertIn("Creating fresh in-memory session", text)
        self.assertIn("Still active; current stage: waiting for Gemini response #1", text)
        self.assertIn("Received Gemini response for model call #3", text)
        self.assertIn("Agent run completed", text)
        self.assertIn("Runner closed; waiting updates stopped", text)
        self.assertNotIn("Private reasoning", text)
        self.assertTrue(result["simulated"])
        self.assertFalse(any(
            task.get_name().startswith("firmware-progress-")
            for task in asyncio.all_tasks()
        ))

    async def test_failure_stops_waiting_updates(self):
        async def broken_model(model, llm_request, stream=False):
            await asyncio.sleep(0.04)
            raise ConnectionError("offline failure")
            yield

        output = io.StringIO()
        with patch(MODEL_METHOD, broken_model), patch(
            "src.orchestration.main.PROGRESS_INTERVAL_SECONDS", 0.01,
        ), redirect_stdout(output):
            with self.assertRaises(ConnectionError):
                await run_agent_loop(TaskRequest(task="Compile and flash"))

        self.assertIn("failed during: waiting for Gemini response #1", output.getvalue())
        self.assertIn("Runner closed; waiting updates stopped", output.getvalue())
        self.assertFalse(any(
            task.get_name().startswith("firmware-progress-")
            for task in asyncio.all_tasks()
        ))
