"""Offline API tests using the real ADK runner with a fake model transport."""

import asyncio
import unittest
import io
from contextlib import redirect_stdout
from unittest.mock import patch

from fastapi.testclient import TestClient
from google.adk.models.llm_response import LlmResponse
from google.adk.models.google_llm import Gemini
from google.adk.models.registry import LLMRegistry
from google.genai import types
from google.genai.errors import ClientError

from src.orchestration.main import MODEL, TaskRequest, app, run_agent_loop

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
            sequence = ["flash_before_build", "compile", "flash_wrong_id", "flash", "final"]
        else:
            sequence = ["compile", "flash", "final"]
        step = sequence[len(results)]
        if step == "compile":
            name, args = "compile_firmware", {}
        elif step in ("flash_before_build", "flash_wrong_id"):
            name, args = "flash_firmware", {"artifact_id": "not-a-built-artifact"}
        elif step == "flash":
            build = next(result.response for result in results if result.name == "compile_firmware")
            name, args = "flash_firmware", {"artifact_id": build["artifact_id"]}
        else:
            yield LlmResponse(content=types.Content(role="model", parts=[
                types.Part(text="Private reasoning must not appear in the API.", thought=True),
                types.Part(text="Simulated compilation and flashing succeeded. No hardware was contacted."),
            ]))
            return
        yield LlmResponse(content=types.Content(role="model", parts=[
            types.Part(function_call=types.FunctionCall(name=name, args=args)),
        ]))
    return generate


class ApiTests(unittest.TestCase):
    def test_configured_model_resolves_to_direct_gemini(self):
        # Resolve without a network call; a models/ prefix breaks ADK routing.
        self.assertIsInstance(LLMRegistry.new_llm(MODEL), Gemini)

    def setUp(self):
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
            "compile_firmware", "compile_firmware", "flash_firmware", "flash_firmware",
        ])
        artifact = events[1]["result"]["artifact_id"]
        self.assertEqual(events[2]["arguments"]["artifact_id"], artifact)
        self.assertEqual(events[3]["result"]["status"], "success")
        self.assertNotIn("Private reasoning", data["final_response"])

    def test_flash_rejects_unbuilt_and_wrong_artifacts(self):
        with patch(MODEL_METHOD, fake_model(try_invalid_artifacts=True)):
            response = self.submit()
        self.assertEqual(response.status_code, 200, response.text)
        results = [event["result"] for event in response.json()["tool_events"] if event["type"] == "tool_result"]
        self.assertEqual([result["status"] for result in results], ["error", "success", "error", "success"])
        self.assertTrue(all(result["simulated"] for result in results))

    def test_new_task_gets_fresh_session_and_build(self):
        with patch(MODEL_METHOD, fake_model()):
            first, second = self.submit().json(), self.submit().json()
        self.assertNotEqual(first["session_id"], second["session_id"])
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


class ProgressTests(unittest.IsolatedAsyncioTestCase):
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
