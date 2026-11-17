"""One Gemini agent with local file tools, real ARM builds, and simulated flashing."""

import asyncio
from contextlib import suppress
import json
import os
import re
import shutil
from pathlib import Path
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
from pydantic import BaseModel, Field, field_validator

from src.build import build as firmware_build

# This demo uses the Gemini API with GOOGLE_API_KEY, rather than Vertex AI.
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "FALSE"

app = FastAPI(title="Embedded AI HIL orchestration", version="0.1.0")
# ADK's model registry expects the bare Gemini ID, without the API's models/ prefix.
MODEL = "gemini-3.8-flash"
APP_NAME = "firmware_mvp"
PROGRESS_INTERVAL_SECONDS = 10
WORKSPACE_ROOT = Path(__file__).resolve().parent / "workspaces"
BUILD_SUPPORT_DIR = Path(firmware_build.__file__).resolve().parent / "target"


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
            "redacted error details. Builds are real; only flashing is simulated.",
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

    log("Task accepted. Creating agent and runner; compilation is REAL, flashing is SIMULATED.")
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
    # Each task tracks its latest successful build for the simulated flash tool.
    built_artifact: str | None = None

    async def compile_firmware(project_dir: str = ".") -> dict:
        """Build a project's src/*.c files using the real ARM cross-compiler.

        Args:
            project_dir: Project folder relative to the workspace, e.g. uart-hello.

        Fixed startup/linker/HIL support files are copied into the project first.
        Returns compiler feedback on failure, or artifact_id and binary metadata
        on success. A successful build does not prove correct runtime behavior.
        """
        nonlocal built_artifact, phase
        # A failed rebuild must not leave a previous artifact eligible for flashing.
        built_artifact = None
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
            result = await asyncio.to_thread(firmware_build.run, project)
        except OSError as error:
            log(f"Build setup failed ({type(error).__name__}).")
            return {"status": "error", "simulated": False, "blame": "rig",
                    "feedback": "Could not prepare or run the build. Check support files and toolchain installation."}
        finally:
            phase = phase_before_build

        log(f"Build {'succeeded' if result.ok else 'failed'}: {result.summary}")
        if result.ok:
            built_artifact = f"firmware-{uuid4().hex}"
        return {
            "status": "success" if result.ok else "error",
            "simulated": False,
            "artifact_id": built_artifact,
            "summary": result.summary,
            "feedback": result.feedback,
            "blame": result.blame if not result.ok else None,
            "artifacts": result.artifacts,
        }

    def flash_firmware(artifact_id: str) -> dict:
        """Simulate flashing the artifact returned by compile_firmware.

        Args:
            artifact_id: Exact artifact_id from the successful compile result.
        """
        log("Executing flash_firmware locally (SIMULATED); checking artifact ID.")
        if built_artifact is None or artifact_id != built_artifact:
            return {
                "status": "error",
                "simulated": True,
                "message": "Artifact mismatch or no successful build yet. Compile first and use its exact artifact_id. Nothing was flashed.",
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
            "You generate and compile bare-metal C firmware for Raspberry Pi Zero W. "
            f"Your local workspace is {workspace}. "
            "Files persist across tasks. Read existing files before revising them. "
            "Use WriteFile to save generated code, ReadFile to inspect it, and EditFile "
            "to revise it. Use paths relative to this workspace. File operations are REAL. "
            "When asked to write code, save it with WriteFile rather than only quoting "
            "it in your final answer. Report filenames and any tool errors honestly. "
            "Compilation is REAL; only flashing is SIMULATED. "
            "Save C source under a project's src/ directory, e.g. uart-hello/src/main.c. "
            "Then call compile_firmware(project_dir='uart-hello'). For workspace-root "
            "projects, write src/main.c and use project_dir='.'. The build compiles "
            "src/*.c (not nested source directories). Define int main(void). "
            "The build supplies fixed start.S, linker.ld, hil.c, and hil.h; do not edit "
            "these support files. Use freestanding C, not libc/stdio. "
            "For console output, include hil.h and call hil_puts. "
            "If a build fails with blame='code', use its feedback to revise the source. "
            "If blame='rig', report the setup problem and stop rather than rewriting code. "
            "For a compile-and-flash request, call compile_firmware first. "
            "Only if it succeeds, call flash_firmware with the exact artifact_id "
            "returned by compile_firmware; never invent an ID. "
            "Use tool results to report what happened. Explain that compilation was real, "
            "flashing was simulated, and no hardware was contacted. A successful build "
            "does not prove the firmware behaves correctly. "
            "You cannot execute shell commands, access hardware, or test real firmware."
        ),
        tools=[compile_firmware, flash_firmware, *file_tools],
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
            "simulation_note": "Gemini, file operations, and compilation are real; flashing is simulated. No hardware was contacted.",
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
