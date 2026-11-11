"""One Gemini agent with simulated compile/flash tools; no hardware access."""

import json
import os
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from google.adk.agents import Agent
from google.adk.agents.run_config import RunConfig
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import BaseModel, Field, field_validator

# This demo uses the Gemini API with GOOGLE_API_KEY, rather than Vertex AI.
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "FALSE"

app = FastAPI(title="Embedded AI HIL orchestration", version="0.1.0")
MODEL = "gemini-2.5-flash"
APP_NAME = "firmware_mvp"


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
        # Avoid exposing credentials or provider internals in an error response.
        print(f"Agent run failed ({type(error).__name__}).", flush=True)
        raise HTTPException(
            status_code=502,
            detail="Gemini/ADK did not complete the run. Check the API key, model access, "
            "quota, and network connection. Compile/flash tools are simulated only.",
        ) from error


async def run_agent_loop(task: TaskRequest) -> dict:
    """Let ADK handle model -> tool -> model turns for one fresh session."""
    # These ordinary Python functions are nested so each task owns its fake build.
    # Replace their bodies with runner calls when real build/flash interfaces exist.
    built_artifact: str | None = None

    def compile_firmware() -> dict:
        """Simulate compiling prepared C firmware. Return a fake artifact ID on success.

        No code is read or compiled, and no build artifact is written.
        """
        nonlocal built_artifact
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
    )
    runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
    tool_events = []
    final_response = ""
    try:
        session = await runner.session_service.create_session(
            app_name=APP_NAME, user_id="local_user",
        )
        print(f"\n[{session.id}] Starting Gemini agent; compile/flash are SIMULATED.", flush=True)
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
                print(f"[{session.id}] {json.dumps(entry)}", flush=True)
            for response in event.get_function_responses():
                entry = {"type": "tool_result", "name": response.name, "result": response.response}
                tool_events.append(entry)
                print(f"[{session.id}] {json.dumps(entry)}", flush=True)
            if event.is_final_response() and event.content:
                # Do not expose model thought/reasoning parts.
                final_response = "".join(
                    part.text for part in event.content.parts or []
                    if part.text and not part.thought
                )

        if not final_response:
            raise RuntimeError("Agent finished without a final text response")
        print(f"[{session.id}] Final answer: {final_response}", flush=True)
        return {
            "session_id": session.id,
            "model": MODEL,
            "simulated": True,
            "simulation_note": "Gemini is real; compilation and flashing are fake. No hardware was contacted.",
            "tool_events": tool_events,
            "final_response": final_response,
        }
    finally:
        # The session exists only in this runner's RAM and is not persisted.
        await runner.close()
