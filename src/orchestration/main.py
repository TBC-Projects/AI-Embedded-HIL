"""One Gemini agent with local file tools, real ARM builds, a real QEMU test tool, and simulated flashing."""

import asyncio
from contextlib import suppress
import json
import os
import re
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from google.adk.agents import Agent
from google.adk.agents.run_config import RunConfig
from google.adk.environment import LocalEnvironment
from google.adk.runners import InMemoryRunner
from google.adk.tools.environment import EnvironmentToolset
from google.genai import types
from google.genai.errors import APIError
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

from src.build import build as firmware_build
from src.build import harness as firmware_harness
from src.build import qemu_gate as firmware_qemu
from src.build.common import StageResult

# Read settings such as GOOGLE_API_KEY from a local .env file at the repo root.
# .env is git-ignored, so the key stays on this computer. A value already set in
# the terminal (export GOOGLE_API_KEY=...) takes priority over the file.
REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")

# This demo uses the Gemini API with GOOGLE_API_KEY, rather than Vertex AI.
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "FALSE"

app = FastAPI(title="Embedded AI HIL orchestration", version="0.1.0")
# ADK's model registry expects the bare Gemini ID, without the API's models/ prefix.
MODEL = "gemini-3.8-flash"
APP_NAME = "firmware_mvp"
PROGRESS_INTERVAL_SECONDS = 10
WORKSPACE_ROOT = Path(__file__).resolve().parent / "workspaces"
BUILD_SUPPORT_DIR = Path(firmware_build.__file__).resolve().parent / "target"


def check_code_rules(project: Path) -> StageResult:
    """Run the harness's code rules on project/src/*.c and *.h, before compiling.

    The harness reads text in its "=== FILE src/<name> ===" format, so the
    project's files are packed into that format first. harness.run deletes and
    rewrites the folder it is given, so it works in a throwaway temporary
    folder, never in the agent's project.
    """
    reply = ""
    paths = sorted(list(project.glob("src/*.c")) + list(project.glob("src/*.h")))
    for path in paths:
        reply = reply + f"=== FILE src/{path.name} ===\n" + path.read_text() + "\n"
    with TemporaryDirectory() as scratch:
        return firmware_harness.run(reply, Path(scratch) / "attempt")


class TaskRequest(BaseModel):
    task: str = Field(min_length=1, max_length=10000)

    @field_validator("task")
    @classmethod
    def nonblank_task(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Task must contain non-whitespace characters")
        return value.strip()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/tasks")
async def submit_task(request: TaskRequest) -> dict:
    """Wait for one agent run and return its answer and tool transcript."""
    if not os.environ.get("GOOGLE_API_KEY", "").strip():
        raise HTTPException(status_code=503, detail="Set GOOGLE_API_KEY before submitting a task.")
    try:
        return await run_agent_loop(request)
    except Exception as error:
        print(f"Agent run failed ({type(error).__name__}).", flush=True)
        if isinstance(error, APIError):
            # Print only the provider's diagnostic fields, not a raw traceback,
            # request headers, or full response. Redact keys before printing.
            diagnostic = json.dumps({
                "google_http_code": error.code,
                "google_status": error.status,
                "message": error.message,
            })
            for name in ("GOOGLE_API_KEY", "GEMINI_API_KEY"):
                secret = os.environ.get(name)
                if secret:
                    diagnostic = diagnostic.replace(secret, "[REDACTED]")
            diagnostic = re.sub(
                r"(?:AIza|AQ\.)[A-Za-z0-9_.-]+", "[REDACTED]", diagnostic,
            )
            print(f"Google API diagnostic: {diagnostic}", flush=True)
        raise HTTPException(
            status_code=502,
            detail="Gemini/ADK did not complete the run. Check the API key, model access, "
            "quota, and network connection. See the backend terminal for Google's "
            "redacted error details. Builds and QEMU runs are real; only flashing is simulated.",
        ) from error


async def run_agent_loop(task: TaskRequest) -> dict:
    """Let ADK handle model -> tool -> model turns for one fresh session."""
    run_id = uuid4().hex
    started = monotonic()
    phase = "setting up the agent"
    model_calls = 0

    def log(message: str) -> None:
        print(f"[{run_id} +{monotonic() - started:.1f}s] {message}", flush=True)

    # These ADK callbacks observe model turns without printing prompts or thoughts.
    def before_model(callback_context, llm_request):
        nonlocal phase, model_calls
        model_calls += 1
        phase = f"waiting for Gemini response #{model_calls} (SDK retries may occur)"
        log(f"Requesting {MODEL}: model call #{model_calls}.")

    def after_model(callback_context, llm_response):
        nonlocal phase
        phase = f"processing Gemini response #{model_calls}"
        log(f"Received Gemini response for model call #{model_calls}.")

    async def report_waiting() -> None:
        while True:
            await asyncio.sleep(PROGRESS_INTERVAL_SECONDS)
            # This is a local heartbeat, not evidence of progress inside Google.
            log(f"Still active; current stage: {phase}. This is a local waiting update.")

    log("Task accepted. Creating agent and runner; checks, compilation and QEMU are REAL, flashing is SIMULATED.")
    # An explicit directory keeps generated files after ADK closes the environment.
    # Every task shares this directory so later requests can revise existing files.
    # Session IDs still identify conversations, but are not used as folder names.
    workspace = WORKSPACE_ROOT
    workspace.mkdir(parents=True, exist_ok=True)
    log(f"Local file workspace: {workspace}. File writes are REAL.")
    file_toolset = EnvironmentToolset(
        environment=LocalEnvironment(working_dir=workspace),
    )
    # Select ADK's ready-made file tools. Do not expose its Execute shell tool.
    file_tools = [
        tool for tool in await file_toolset.get_tools()
        if tool.name in {"ReadFile", "WriteFile", "EditFile"}
    ]
    # Each task tracks its latest successful build, and whether that build passed
    # test_firmware. compile -> test -> flash must use the same artifact_id.
    built_artifact: str | None = None
    built_project: Path | None = None
    tested_artifact: str | None = None

    async def compile_firmware(project_dir: str = ".") -> dict:
        """Check and compile a project's src/ code with the real ARM cross-compiler.

        Args:
            project_dir: Project folder relative to the workspace, e.g. uart-hello.

        Runs in order and stops at the first failure (failed_stage says which):
          1. harness: code rules (no libc/printf/malloc, int main(void), src/ layout)
          2. build: arm-none-eabi-gcc; support files are copied into the project first
        Returns feedback on failure, or artifact_id and binary metadata on success.
        Next, pass the artifact_id to test_firmware to run it in QEMU.
        """
        nonlocal built_artifact, built_project, tested_artifact, phase
        # A failed rebuild must not leave a previous artifact eligible for testing or flashing.
        built_artifact = None
        built_project = None
        tested_artifact = None
        project = (workspace / project_dir).resolve()
        if not project.is_relative_to(workspace.resolve()):
            return {"status": "error", "simulated": False, "blame": "code",
                    "feedback": "project_dir must stay inside the workspace."}
        if not project.is_dir():
            return {"status": "error", "simulated": False, "blame": "code",
                    "feedback": "Project directory does not exist. Write project/src/main.c first."}

        log(f"Compiling {project} with {firmware_build.CC} (REAL).")
        phase_before_build = phase
        phase = f"compiling {project_dir} with {firmware_build.CC}"
        # Keep blocking compiler processes off the asynchronous server event loop.
        try:
            for name in ("start.S", "linker.ld", "hil.c", "hil.h"):
                destination = project / name
                if destination.is_symlink():
                    return {"status": "error", "simulated": False, "blame": "code",
                            "feedback": f"Fixed support file {name} must not be a symlink."}
                shutil.copyfile(BUILD_SUPPORT_DIR / name, destination)

            # 1. Harness: reject code that can never work on bare metal, before gcc runs.
            result = await asyncio.to_thread(check_code_rules, project)
            # 2. Build with the real ARM cross-compiler.
            if result.ok:
                result = await asyncio.to_thread(firmware_build.run, project)
        except OSError as error:
            log(f"Build setup failed ({type(error).__name__}).")
            return {"status": "error", "simulated": False, "blame": "rig",
                    "feedback": "Could not prepare or run the build. Check support files and toolchain installation."}
        finally:
            phase = phase_before_build

        log(f"{result.stage} {'passed' if result.ok else 'failed'}: {result.summary}")
        if result.ok:
            built_artifact = f"firmware-{uuid4().hex}"
            built_project = project
        return {
            "status": "success" if result.ok else "error",
            "simulated": False,
            "artifact_id": built_artifact,
            "failed_stage": None if result.ok else result.stage,
            "summary": result.summary,
            "feedback": result.feedback,
            "blame": result.blame if not result.ok else None,
            "artifacts": result.artifacts,
        }

    async def test_firmware(artifact_id: str, expect_output: str = "") -> dict:
        """Run the compiled firmware on an emulated Raspberry Pi Zero (QEMU). This is REAL.

        Args:
            artifact_id: Exact artifact_id from the latest successful compile result.
            expect_output: Optional text the firmware must print on its console,
                e.g. "UART ready". Leave empty to only check that it runs.

        Copies kernel.elf into the project's test_firmware/ subfolder, runs it there
        for a few seconds, and saves the console output as test_firmware/qemu.log.
        Firmware may loop forever and never return from main; that is normal.
        Passes if it boots and keeps running without hil_panic (and, if given,
        prints expect_output). Fails on hil_panic, a crash before main, QEMU
        exiting, or missing expect_output. QEMU has no real timing, so passing
        does not prove timing on hardware.
        """
        nonlocal tested_artifact, phase
        tested_artifact = None
        log("Executing test_firmware (REAL QEMU); checking artifact ID.")
        if built_artifact is None or built_project is None or artifact_id != built_artifact:
            return {
                "status": "error",
                "simulated": False,
                "blame": "code",
                "feedback": "Artifact mismatch or no successful build yet. Compile first and use its exact artifact_id. Nothing was run.",
            }

        test_dir = built_project / "test_firmware"
        phase_before_test = phase
        phase = f"running {artifact_id} in QEMU"
        try:
            if test_dir.is_symlink():
                return {"status": "error", "simulated": False, "blame": "code",
                        "feedback": "test_firmware/ must be a normal folder, not a symlink."}
            test_dir.mkdir(exist_ok=True)
            shutil.copyfile(built_project / "kernel.elf", test_dir / "kernel.elf")
            # Keep the blocking QEMU process off the asynchronous server event loop.
            result = await asyncio.to_thread(
                firmware_qemu.run, test_dir / "kernel.elf",
                expect=expect_output.strip() or None,
            )
            console = result.artifacts.get("console", "")
            (test_dir / "qemu.log").write_text(console)
        except OSError as error:
            log(f"QEMU test setup failed ({type(error).__name__}).")
            return {"status": "error", "simulated": False, "blame": "rig",
                    "feedback": "Could not prepare or run the QEMU test. Check that kernel.elf exists and QEMU is installed."}
        finally:
            phase = phase_before_test

        log(f"QEMU test {'passed' if result.ok else 'failed'}: {result.summary}")
        if result.ok:
            tested_artifact = artifact_id
        return {
            "status": "success" if result.ok else "error",
            "simulated": False,
            "artifact_id": artifact_id,
            "summary": result.summary,
            "feedback": result.feedback,
            "blame": result.blame if not result.ok else None,
            "console": console,
            "test_dir": str(test_dir),
        }

    def flash_firmware(artifact_id: str) -> dict:
        """Simulate flashing an artifact that passed test_firmware.

        Args:
            artifact_id: Exact artifact_id that compiled and then passed test_firmware.
        """
        log("Executing flash_firmware locally (SIMULATED); checking artifact ID.")
        if tested_artifact is None or artifact_id != tested_artifact:
            return {
                "status": "error",
                "simulated": True,
                "message": "Artifact mismatch, or it has not passed test_firmware yet. Compile, then test, and use that exact artifact_id. Nothing was flashed.",
            }
        return {
            "status": "success",
            "simulated": True,
            "artifact_id": artifact_id,
            "message": "Simulated flashing succeeded. No Raspberry Pi was contacted or firmware uploaded.",
        }

    agent = Agent(
        name="firmware_agent",
        model=MODEL,
        instruction=(
            "You generate, compile, and test bare-metal C firmware for Raspberry Pi Zero W. "
            f"Your local workspace is {workspace}. "
            "Files persist across tasks. Read existing files before revising them. "
            "Use WriteFile to save generated code, ReadFile to inspect it, and EditFile "
            "to revise it. Use paths relative to this workspace. File operations are REAL. "
            "When asked to write code, save it with WriteFile rather than only quoting "
            "it in your final answer. Report filenames and any tool errors honestly. "
            "Code checks, compilation, and the QEMU emulator test are REAL; only flashing "
            "is SIMULATED. The workflow is compile_firmware -> test_firmware -> "
            "flash_firmware, always with the same artifact_id. "
            "compile_firmware runs two steps and stops at the first failure, named in "
            "failed_stage: 'harness' (code rules: no stdio.h, stdlib.h, string.h, "
            "printf, malloc, free, sprintf; never use _start, __stack_top or "
            "__bss_start) and 'build' (gcc errors). "
            "test_firmware boots the build on an emulated Pi Zero in the project's "
            "test_firmware/ folder and runs it for a few seconds. Firmware normally "
            "loops forever and never returns from main; that is expected and passes "
            "as long as it boots and does not call hil_panic. To check behaviour, have "
            "the firmware print a status line with hil_puts (e.g. 'UART ready') and pass "
            "that text as expect_output; the test then fails if it is never printed. "
            "A hil_panic, a crash before main, or QEMU exiting fails. Its console "
            "output is in the result. "
            "Save C source under a project's src/ directory, e.g. uart-hello/src/main.c. "
            "Then call compile_firmware(project_dir='uart-hello'). For workspace-root "
            "projects, write src/main.c and use project_dir='.'. The build compiles "
            "src/*.c (not nested source directories). Define int main(void). "
            "The build supplies fixed start.S, linker.ld, hil.c, and hil.h; do not edit "
            "these support files. Use freestanding C, not libc/stdio. "
            "For console output, include hil.h and call hil_puts. "
            "If compile_firmware or test_firmware fails with blame='code', use its "
            "feedback to revise the source, then compile and test again. "
            "If blame='rig', report the setup problem and stop rather than rewriting code. "
            "Only call test_firmware with the exact artifact_id from the latest "
            "successful compile_firmware, and only call flash_firmware with an "
            "artifact_id that passed test_firmware; never invent an ID. "
            "Use tool results to report what happened. Explain that the checks, "
            "compilation and QEMU test were real, flashing was simulated, and no hardware "
            "was contacted. QEMU does not model real timing, so passing it does not "
            "prove timing on real hardware. "
            "You cannot execute shell commands or access hardware."
        ),
        tools=[compile_firmware, test_firmware, flash_firmware, *file_tools],
        before_model_callback=before_model,
        after_model_callback=after_model,
    )
    runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
    tool_events = []
    final_response = ""
    heartbeat = asyncio.create_task(report_waiting(), name=f"firmware-progress-{run_id}")
    try:
        phase = "creating the in-memory session"
        log("Creating fresh in-memory session.")
        session = await runner.session_service.create_session(
            app_name=APP_NAME, user_id="local_user", session_id=run_id,
        )
        log("Session created. Starting ADK runtime.")
        message = types.Content(role="user", parts=[types.Part(text=task.task)])

        # ADK calls Gemini, executes the Python tools it requests, and sends their
        # results back to Gemini. We observe events, rather than scripting calls.
        async for event in runner.run_async(
            user_id=session.user_id,
            session_id=session.id,
            new_message=message,
            run_config=RunConfig(max_llm_calls=8),
        ):
            for call in event.get_function_calls():
                entry = {"type": "tool_call", "name": call.name, "arguments": call.args}
                tool_events.append(entry)
                log(json.dumps(entry))
            for response in event.get_function_responses():
                entry = {"type": "tool_result", "name": response.name, "result": response.response}
                tool_events.append(entry)
                log(json.dumps(entry))
            if event.is_final_response() and event.content:
                # Do not expose model thought/reasoning parts.
                final_response = "".join(
                    part.text for part in event.content.parts or []
                    if part.text and not part.thought
                )

        if not final_response:
            raise RuntimeError("Agent finished without a final text response")
        log(f"Final answer: {final_response}")
        log("Agent run completed. Returning answer and tool transcript to the HTTP client.")
        return {
            "session_id": session.id,
            "model": MODEL,
            "workspace": str(workspace),
            "simulated": True,
            "simulation_note": "Gemini, file operations, code checks, compilation, and the QEMU run are real; flashing is simulated. No hardware was contacted.",
            "tool_events": tool_events,
            "final_response": final_response,
        }
    except asyncio.CancelledError:
        log(f"Agent run cancelled during: {phase}.")
        raise
    except Exception as error:
        log(f"Agent run failed during: {phase} ({type(error).__name__}).")
        raise
    finally:
        heartbeat.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat
        # The session exists only in this runner's RAM and is not persisted.
        log("Closing runner and releasing in-memory resources.")
        try:
            await runner.close()
        finally:
            # We passed individual tools to Agent, so close their toolset ourselves.
            # LocalEnvironment preserves an explicitly supplied workspace directory.
            await file_toolset.close()
        log("Runner closed; waiting updates stopped. Workspace files are preserved.")
