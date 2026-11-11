"""One Gemini agent with simulated compile/flash tools; no hardware access."""

import asyncio
from contextlib import suppress
import json
import os
import re
from time import monotonic
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from google.adk.agents import Agent
from google.adk.agents.run_config import RunConfig
from google.adk.runners import InMemoryRunner
from google.genai import types
from google.genai.errors import APIError
from pydantic import BaseModel, Field, field_validator

# This demo uses the Gemini API with GOOGLE_API_KEY, rather than Vertex AI.
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "FALSE"

app = FastAPI(title="Embedded AI HIL orchestration", version="0.1.0")
# ADK's model registry expects the bare Gemini ID, without the API's models/ prefix.
MODEL = "gemini-3.8-flash"
APP_NAME = "firmware_mvp"
PROGRESS_INTERVAL_SECONDS = 10


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
            "redacted error details. Compile/flash tools are simulated only.",
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

    log("Task accepted. Creating agent and runner; compile/flash are SIMULATED.")
    # These ordinary Python functions are nested so each task owns its fake build.
    # Replace their bodies with runner calls when real build/flash interfaces exist.
    built_artifact: str | None = None

    def compile_firmware() -> dict:
        """Simulate compiling prepared C firmware. Return a fake artifact ID on success.

        No code is read or compiled, and no build artifact is written.
        """
        nonlocal built_artifact
        log("Executing compile_firmware locally (SIMULATED).")
        built_artifact = f"simulated-firmware-{uuid4().hex}"
        return {
            "status": "success",
            "simulated": True,
            "artifact_id": built_artifact,
            "message": "Simulated compilation succeeded. No compiler ran or binary was created.",
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
                "message": "Artifact mismatch or no build yet. Compile first and use its exact artifact_id. Nothing was flashed.",
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
            "You demonstrate a firmware workflow with two SIMULATED tools. "
            "For a compile-and-flash request, call compile_firmware first. "
            "Only if it succeeds, call flash_firmware with the exact artifact_id "
            "returned by compile_firmware; never invent an ID. "
            "Use tool results to report what happened. Always explain that compilation "
            "and flashing were simulated and no hardware was contacted. "
            "You cannot edit code, execute shell commands, or test real firmware."
        ),
        tools=[compile_firmware, flash_firmware],
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
            "simulated": True,
            "simulation_note": "Gemini is real; compilation and flashing are fake. No hardware was contacted.",
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
        await runner.close()
        log("Runner closed; waiting updates stopped.")
