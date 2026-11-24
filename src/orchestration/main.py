"""One Gemini agent with local files, ARM builds, bounded QEMU runs, and simulated flashing."""

import asyncio
from contextlib import suppress
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from uuid import UUID, uuid4

from anyio import CancelScope
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from google.adk.agents import Agent
from google.adk.agents.run_config import RunConfig
from google.adk.environment import LocalEnvironment
from google.adk.events import Event
from google.adk.runners import Runner
from google.adk.sessions.sqlite_session_service import SqliteSessionService
from google.adk.tools.environment import EnvironmentToolset
from google.genai import types
from google.genai.errors import APIError
from pydantic import BaseModel, Field, field_validator

from . import compiler as firmware_build
from . import qemu as firmware_qemu
from .history import ChatStore

# This demo uses the Gemini API with GOOGLE_API_KEY, rather than Vertex AI.
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "FALSE"

app = FastAPI(title="Embedded AI HIL orchestration", version="0.1.0")
# ADK's model registry expects the bare Gemini ID, without the API's models/ prefix.
#MODEL = "gemini-3.8-flash"
#MODEL = "gemini-3.7-flash"
MODEL = "gemini-3.5-flash-lite"
APP_NAME = "firmware_mvp"
PROGRESS_INTERVAL_SECONDS = 10
WORKSPACE_ROOT = Path(__file__).resolve().parent / "workspaces"
BUILD_SUPPORT_DIR = Path(__file__).resolve().parent / "firmware"
DATA_DIR = Path(__file__).resolve().parent / "data"
chat_store: ChatStore | None = None
active_run: asyncio.Task | None = None
active_run_id: str | None = None
active_chat_id: str | None = None


def get_store() -> ChatStore:
    global chat_store
    path = DATA_DIR / "conversations.db"
    if chat_store is None or chat_store.path != path:
        chat_store = ChatStore(path)
        chat_store.recover_interrupted()
    return chat_store


def session_service() -> SqliteSessionService:
    return SqliteSessionService(db_path=str(get_store().path))


def redact(text: str) -> str:
    for name in ("GOOGLE_API_KEY", "GEMINI_API_KEY"):
        secret = os.environ.get(name)
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return re.sub(r"(?:AIza|AQ\.)[A-Za-z0-9_.-]+", "[REDACTED]", text)


def error_detail(error: Exception) -> str:
    print(f"Agent run failed ({type(error).__name__}).", flush=True)
    if isinstance(error, APIError):
        diagnostic = redact(json.dumps({
            "google_http_code": error.code, "google_status": error.status,
            "message": error.message,
        }))
        print(f"Google API diagnostic: {diagnostic}", flush=True)
        return f"Google API error: {diagnostic}"
    return "Agent run failed. See the backend terminal for diagnostics."


def start_run(request, run_id, emit=None):
    """One active run per backend process, including cleanup after cancellation."""
    global active_run, active_run_id, active_chat_id
    if not os.environ.get("GOOGLE_API_KEY", "").strip():
        raise HTTPException(status_code=503, detail="Set GOOGLE_API_KEY before submitting a task.")
    if active_run is not None and not active_run.done():
        raise HTTPException(status_code=409, detail="Another run is active. Stop it or wait for it to finish.")
    store = get_store()
    chat_id = str(request.chat_id) if request.chat_id else store.create_chat()["id"]
    if store.get_chat(chat_id) is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    request = request.model_copy(update={"chat_id": UUID(chat_id), "task": redact(request.task)})
    store.start_run(chat_id, run_id, request.task)

    def record(event):
        event = json.loads(redact(json.dumps({**event, "chat_id": chat_id})))
        saved = store.append_log(event)
        if emit:
            emit(saved)

    async def execute():
        try:
            result = await run_agent_loop(request, emit=record, run_id=run_id)
            result = json.loads(redact(json.dumps({**result, "chat_id": chat_id, "run_id": run_id})))
            store.finish_run(run_id, "completed", result)
            return result
        except asyncio.CancelledError:
            record({"type": "log", "run_id": run_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(), "source": "Backend",
                    "message": "Run stopped; resources released."})
            store.finish_run(run_id, "stopped")
            raise
        except Exception as error:
            record({"type": "log", "run_id": run_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(), "source": "Error",
                    "message": error_detail(error)})
            store.finish_run(run_id, "failed")
            raise

    active_run_id = run_id
    active_chat_id = chat_id
    active_run = asyncio.create_task(execute())
    return active_run


class TaskRequest(BaseModel):
    task: str = Field(min_length=1, max_length=10000)
    chat_id: UUID | None = None

    @field_validator("task")
    @classmethod
    def nonblank_task(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Task must contain non-whitespace characters")
        return value.strip()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/chats")
async def list_chats():
    return {"chats": get_store().list_chats(),
            "active_run": {"run_id": active_run_id, "chat_id": active_chat_id}
            if active_run is not None and not active_run.done() else None}


@app.post("/chats", status_code=201)
async def create_chat():
    return {**get_store().create_chat(), "runs": []}


@app.get("/chats/{chat_id}")
async def get_chat(chat_id: UUID):
    chat = get_store().get_chat(str(chat_id))
    if chat is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return chat


@app.delete("/chats/{chat_id}")
async def delete_chat(chat_id: UUID):
    if str(chat_id) == active_chat_id and active_run is not None and not active_run.done():
        raise HTTPException(status_code=409, detail="Stop this conversation's run before deleting it.")
    if get_store().get_chat(str(chat_id)) is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    await session_service().delete_session(app_name=APP_NAME, user_id="local_user", session_id=str(chat_id))
    get_store().delete_chat(str(chat_id))
    return {"message": "Conversation deleted. Workspace files were kept."}


@app.post("/tasks")
async def submit_task(request: TaskRequest) -> dict:
    """Wait for one agent run and return its answer and tool transcript."""
    task = start_run(request, uuid4().hex)
    try:
        return await task
    except asyncio.CancelledError:
        raise HTTPException(status_code=409, detail="Run stopped.")
    except Exception as error:
        raise HTTPException(status_code=502, detail=error_detail(error)) from error


@app.post("/tasks/stream")
async def stream_task(request: TaskRequest, run_id: UUID):
    """Stream newline-delimited JSON: log entries followed by the final answer."""
    queue = asyncio.Queue()
    run_id = str(run_id)
    task = start_run(request, run_id, emit=queue.put_nowait)

    async def produce():
        try:
            result = await task
            queue.put_nowait({"type": "final", "run_id": run_id, "result": result})
        except asyncio.CancelledError:
            pass  # execute() has already saved and emitted the cancellation log.
        except Exception:
            pass  # execute() has already saved and emitted the error log.
        finally:
            queue.put_nowait(None)

    producer = asyncio.create_task(produce())

    async def body():
        try:
            while (event := await queue.get()) is not None:
                yield redact(json.dumps(event)) + "\n"
        finally:
            # A closed browser/tab also cancels the server run. Shield cleanup
            # from Starlette's disconnect cancellation until child processes stop.
            with CancelScope(shield=True):
                if not task.done() and not task.cancelling():
                    task.cancel()
                await producer

    return StreamingResponse(body(), media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/tasks/{run_id}/stop")
async def stop_task(run_id: UUID):
    if str(run_id) != active_run_id or active_run is None or active_run.done():
        raise HTTPException(status_code=404, detail="This run is no longer active.")
    task = active_run
    if not task.cancelling():
        task.cancel()
    with suppress(asyncio.CancelledError, Exception):
        await task
    return {"message": "Run stopped."}


async def run_agent_loop(task: TaskRequest, emit=None, run_id=None) -> dict:
    """Run one turn using this chat's saved ADK session and the shared files."""
    run_id = run_id or uuid4().hex
    started = monotonic()
    phase = "setting up the agent"
    model_calls = 0

    def log(message: str, source="Agent", details=None) -> None:
        message = redact(message)
        details = redact(details) if details is not None else None
        print(f"[{run_id} +{monotonic() - started:.1f}s] {message}", flush=True)
        if details:
            print(details, flush=True)
        if emit:
            emit({"type": "log", "run_id": run_id,
                  "timestamp": datetime.now(timezone.utc).isoformat(),
                  "source": source, "message": message, "details": details})

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

    def list_directory(path: str = ".") -> dict:
        """List files and folders inside the shared workspace without reading contents.

        Args:
            path: Directory relative to the workspace. Use '.' to discover projects,
                then list a returned directory path to explore inside it.

        Lists one level at a time, up to 200 entries. Does not execute a shell.
        """
        try:
            root = workspace.resolve()
            directory = (root / path).resolve()
            if not directory.is_relative_to(root):
                return {"status": "error", "message": "Path must stay inside the workspace."}
            if not directory.is_dir():
                return {"status": "error", "message": "Directory does not exist or the path is a file."}
            children = sorted(directory.iterdir(), key=lambda entry: entry.name)
            entries = []
            for child in children[:200]:
                # Report links as links without inspecting their targets.
                kind = "symlink" if child.is_symlink() else (
                    "directory" if child.is_dir() else "file" if child.is_file() else "other"
                )
                entries.append({"name": child.name, "path": child.relative_to(root).as_posix(),
                                "type": kind})
            return {"status": "success", "path": directory.relative_to(root).as_posix(),
                    "entries": entries, "truncated": len(children) > 200}
        except (OSError, RuntimeError):
            return {"status": "error", "message": "Could not list the directory. Check its path and permissions."}

    # Each task tracks its latest successful build for the simulated flash tool.
    built_artifact: str | None = None
    built_elf: Path | None = None

    async def compile_firmware(project_dir: str = ".") -> dict:
        """Build a project's src/*.c files using the real ARM cross-compiler.

        Args:
            project_dir: Project folder relative to the workspace, e.g. uart-hello.

        Fixed startup/linker/HIL support files are copied into the project first.
        Returns compiler feedback on failure, or artifact_id and binary metadata
        on success. A successful build does not prove correct runtime behavior.
        """
        nonlocal built_artifact, built_elf, phase
        # A failed rebuild must not leave a previous artifact eligible for flashing.
        built_artifact = None
        built_elf = None
        project = (workspace / project_dir).resolve()
        if not project.is_relative_to(workspace.resolve()):
            return {"status": "error", "simulated": False, "blame": "code",
                    "feedback": "project_dir must stay inside the workspace."}
        if not project.is_dir():
            return {"status": "error", "simulated": False, "blame": "code",
                    "feedback": "Project directory does not exist. Write project/src/main.c first."}

        log(f"Compiling {project} with {firmware_build.CC} (REAL).", "Build")
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
            build_task = asyncio.create_task(asyncio.to_thread(firmware_build.run, project))
            try:
                result = await asyncio.shield(build_task)
            except asyncio.CancelledError:
                log("Stop requested; waiting for the compiler to finish before releasing the workspace.", "Build")
                with suppress(Exception):
                    await build_task
                raise
        except OSError as error:
            log(f"Build setup failed ({type(error).__name__}).")
            return {"status": "error", "simulated": False, "blame": "rig",
                    "feedback": "Could not prepare or run the build. Check support files and toolchain installation."}
        finally:
            phase = phase_before_build

        log(f"Build {'succeeded' if result.ok else 'failed'}: {result.summary}", "Build")
        if result.ok:
            built_artifact = f"firmware-{uuid4().hex}"
            built_elf = Path(result.artifacts["elf"])
        return {
            "status": "success" if result.ok else "error",
            "simulated": False,
            "artifact_id": built_artifact,
            "summary": result.summary,
            "feedback": result.feedback,
            "blame": result.blame if not result.ok else None,
            "artifacts": result.artifacts,
        }

    async def run_qemu(artifact_id: str, duration_seconds: float = 1.0) -> dict:
        """Run the latest compiled ELF briefly and return its collected UART output.

        Args:
            artifact_id: Exact ID from the latest successful compile in this task.
            duration_seconds: Observation window, default 1 second; greater than 0, at most 10.

        QEMU is stopped afterwards, including for continuously running firmware.
        Returns uart_output and qemu_errors; it does not decide whether tests pass.
        """
        nonlocal phase
        if built_artifact is None or artifact_id != built_artifact or built_elf is None:
            return {"status": "error", "execution_status": "invalid_request",
                    "message": "Compile successfully first and use that exact artifact_id. QEMU was not started."}
        previous_phase = phase
        phase = f"observing QEMU for up to {duration_seconds} seconds"
        log(f"Starting bounded QEMU observation: {duration_seconds}s (REAL).")
        try:
            result = await firmware_qemu.observe(built_elf, duration_seconds)
        finally:
            phase = previous_phase
        log(f"QEMU observation ended: {result['execution_status']}.")
        return {"artifact_id": artifact_id, **result}

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
            "Files persist across tasks and ALL conversations in one shared workspace. "
            "An older conversation may describe files that have since changed; read "
            "the current files before revising them. Artifact IDs are valid only in "
            "the current turn: recompile before QEMU/flash in a follow-up. "
            "Use list_directory('.') to discover existing projects, then list their "
            "subdirectories and read relevant source files. Directory listings are "
            "one level at a time; returned paths are relative to the workspace. "
            "Use WriteFile to save generated code, ReadFile to inspect it, and EditFile "
            "to revise it. Use paths relative to this workspace. File operations are REAL. "
            "When asked to write code, save it with WriteFile rather than only quoting "
            "it in your final answer. Report filenames and any tool errors honestly. "
            "Compilation and QEMU execution are REAL; only flashing is SIMULATED. "
            "When asked to execute or inspect firmware in emulation, compile first, "
            "then call run_qemu with the exact artifact_id. It captures UART for one "
            "second by default (configurable up to ten), stops QEMU, and returns "
            "uart_output and qemu_errors. Use this evidence to explain behavior or "
            "revise files, recompile, and run again. Firmware need not return from main. "
            "observation_complete only means the observation window ended, not that "
            "firmware passed a test. Check the user's expected output, missing output, "
            "HIL:PANIC, and diagnostics. Never treat infrastructure errors as firmware "
            "test failures. This is a UART log, not an FPGA trace or real timing proof. "
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
            "You cannot execute arbitrary shell commands or access physical hardware."
        ),
        tools=[list_directory, compile_firmware, run_qemu, flash_firmware, *file_tools],
        before_model_callback=before_model,
        after_model_callback=after_model,
    )
    service = session_service()
    runner = Runner(agent=agent, app_name=APP_NAME, session_service=service)
    tool_events = []
    final_response = ""
    heartbeat = asyncio.create_task(report_waiting(), name=f"firmware-progress-{run_id}")
    try:
        phase = "loading the saved conversation session"
        conversation_id = str(task.chat_id) if task.chat_id else run_id
        session = await service.get_session(
            app_name=APP_NAME, user_id="local_user", session_id=conversation_id)
        if session is None:
            log("Creating saved conversation session.")
            session = await service.create_session(
                app_name=APP_NAME, user_id="local_user", session_id=conversation_id)
        else:
            log("Loaded saved conversation history.")
            # A stopped turn may have saved a tool request without its result.
            # Close that request honestly so the next Gemini call has a complete
            # tool exchange. Never rerun a cancelled operation automatically.
            pending = {}
            for previous in session.events:
                for call in previous.get_function_calls():
                    pending[call.id] = (call, previous.invocation_id)
                for response in previous.get_function_responses():
                    pending.pop(response.id, None)
            for call, invocation_id in pending.values():
                await service.append_event(session, Event(
                    author="firmware_agent", invocation_id=invocation_id,
                    content=types.Content(role="user", parts=[types.Part(
                        function_response=types.FunctionResponse(id=call.id, name=call.name,
                            response={"status": "interrupted", "message":
                                      "This tool call was interrupted. Its result is unknown. Inspect current files and recompile before running firmware."}),
                    )]),
                ))
            if pending:
                log("Recorded interrupted tool calls before continuing the conversation.")
        log("Starting ADK runtime.")
        message = types.Content(role="user", parts=[types.Part(text=task.task)])

        # ADK calls Gemini, executes the Python tools it requests, and sends their
        # results back to Gemini. We observe events, rather than scripting calls.
        async for event in runner.run_async(
            user_id=session.user_id,
            session_id=session.id,
            new_message=message,
            run_config=RunConfig(max_llm_calls=30),
        ):
            for call in event.get_function_calls():
                entry = {"type": "tool_call", "name": call.name, "arguments": call.args}
                tool_events.append(entry)
                log(f"Tool call: {call.name}", details=json.dumps(call.args, indent=2))
            for response in event.get_function_responses():
                entry = {"type": "tool_result", "name": response.name, "result": response.response}
                tool_events.append(entry)
                payload = response.response
                if response.name == "run_qemu":
                    metadata = {key: value for key, value in payload.items()
                                if key not in {"uart_output", "qemu_errors"}}
                    log("QEMU observation returned.", "QEMU", json.dumps(metadata, indent=2))
                    log("Captured UART output", "QEMU UART", payload.get("uart_output") or "(no UART output)")
                    if payload.get("qemu_errors"):
                        log("Emulator diagnostics", "QEMU", payload["qemu_errors"])
                else:
                    log(f"Tool result: {response.name}", "Build" if response.name == "compile_firmware" else "Agent",
                        json.dumps(payload, indent=2))
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
            "simulation_note": "Gemini, file operations, compilation, and QEMU runs are real; physical flashing is simulated. No hardware was contacted.",
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
        # The runner closes after this turn; its session remains in SQLite.
        log("Closing runner and releasing in-memory resources.")
        try:
            await runner.close()
        finally:
            # We passed individual tools to Agent, so close their toolset ourselves.
            # LocalEnvironment preserves an explicitly supplied workspace directory.
            await file_toolset.close()
        log("Runner closed; waiting updates stopped. Workspace files are preserved.")
