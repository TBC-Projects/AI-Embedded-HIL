# Orchestration: minimal Gemini agent

One Google ADK Agent and InMemoryRunner handle each task. Gemini makes real API
calls and can use ADK's built-in ReadFile, WriteFile, and EditFile tools to create
real local source files. Compile and flash remain simulated Python tools: no
compiler runs, no binary is created, and no Raspberry Pi is contacted. The
dashboard still uses its separate browser-local mock workflow.

## Run locally

From the repository root, create a virtual environment (Python 3.11+ recommended):

```sh
python3 -m venv .venv
source .venv/bin/activate
./.venv/bin/python -m pip install -r src/orchestration/requirements.txt
export GOOGLE_API_KEY='your-Google-AI-Studio-API-key'
./.venv/bin/python -m uvicorn src.orchestration.main:app --reload --host 127.0.0.1 --port 8000
```

Get a key from https://aistudio.google.com/apikey. Keep it outside Git. The backend
reads GOOGLE_API_KEY; this demo explicitly uses the Gemini API rather than Vertex
AI. Model: `gemini-3.8-flash` (the `MODEL` constant in main.py, without a `models/`
prefix because ADK resolves bare Gemini IDs). Actual model calls
require model access, available quota, and network connectivity.

In another terminal:

```sh
curl http://127.0.0.1:8000/health
curl -sS --max-time 90 http://127.0.0.1:8000/tasks \
  -H 'Content-Type: application/json' \
  -d '{"task":"Call compile_firmware exactly once. If it succeeds, call flash_firmware exactly once using its returned artifact_id. After receiving the flash result, report both statuses in one sentence and finish. Do not call further tools."}' \
  | python3 -m json.tool
```

The response contains `session_id`, `model`, `workspace`, `simulated`, `simulation_note`,
`tool_events` (calls, arguments, and results), and `final_response`. Tool events and
Gemini's final answer are also printed in the server terminal. `simulated: true`
refers to the firmware operations; the model interaction is real. The server logs
session setup, model requests/responses, tool execution, completion/failure, and
cleanup with a run ID and elapsed seconds. Every 10 seconds a local heartbeat
reports the current stage; it does not imply Google is making progress. Prompts
and model thought content are not logged. There is no overall time limit yet.
API docs are at
http://127.0.0.1:8000/docs. Requests wait until completion; there is no streaming or
background job queue.

## Generate a real local file

With the server running, submit this in another terminal:

```sh
curl -sS --max-time 90 http://127.0.0.1:8000/tasks \
  -H 'Content-Type: application/json' \
  -d '{"task":"Use WriteFile to create main.c containing a minimal C program with int main(void) that returns 0. Then use ReadFile to verify it. Do not compile or flash. Briefly report the filename and finish."}' \
  | python3 -m json.tool
```

Every request uses the same directory: `src/orchestration/workspaces/`.
The terminal log and response's `workspace` field show its absolute path. Open
`main.c` there in your editor. Files remain after the run, even on failure, and
the workspace folder is ignored by Git. Later requests can read and edit prior
files. The agent can create subdirectories by writing paths such as
`uart-hello/main.c`. Existing `src/target/` code is untouched.

Each request still has a fresh conversation/session and a new ID for logging;
that ID no longer creates a directory. The agent does not remember earlier chats,
so tell it which existing files to read. Submit tasks one at a time to avoid
simultaneous edits to the shared files. Files are not automatically cleared.

In main.py, EnvironmentToolset supplies existing ADK implementations. We select
its three file tools and register them beside compile_firmware and flash_firmware.
The shell Execute tool is not registered. Gemini supplies file paths and contents
as structured tool arguments; no code-block extractor is used. File tool calls
and results appear in the same transcript as compile/flash, including code content.
`simulated: true` refers only to build/flash; file writes and reads are real.

The compile stub does not read or validate generated code. Its success does not
prove a generated program compiles or behaves correctly. To try the whole flow,
ask to write a C file, then compile it in simulation, flash the returned artifact
ID in simulation, and finish with a short summary. Real compiler integration is
still future work. LocalEnvironment is a local development tool, not an OS sandbox.

## Long waits and test prompts

During local testing, a compile-and-flash run completed both simulated tools but
then waited a long time for Gemini's final response. We stopped the run before
completion, so this does not establish an infinite loop or a faulty flash tool.
There is no overall backend timeout; the eight-model-call limit does not limit
how long an individual call may wait.

Use the explicit compile-and-flash prompt above for further testing. It makes the
stopping instruction clear but is not a verified fix for long waits. The two
smaller prompts below have completed successfully in live local tests:

- Connectivity only: `Do not call any tools. Reply with exactly: Hello`
- One tool and final answer: `Call compile_firmware exactly once. Do not flash anything. After receiving the tool result, briefly report its status and artifact ID, then finish.`

Watch the backend/Uvicorn terminal for model calls, tool results, and waiting
updates. The curl terminal displays JSON only after completion. `--max-time 90`
limits curl's wait, not the backend run. If it times out, stop and restart the
backend before retrying so the earlier run does not remain active.

## How it works

1. FastAPI validates TaskRequest: nonblank text, at most 10,000 characters.
2. The endpoint checks GOOGLE_API_KEY and awaits run_agent_loop.
3. That function defines compile_firmware and flash_firmware, with build state
   private to this request. ADK turns their names, docstrings, and type annotations
   into tool descriptions Gemini can use.
4. ADK's EnvironmentToolset supplies three local file tools in the shared workspace.
   An Agent gives Gemini instructions, those file tools, and the two simulated
   compile/flash functions. An InMemoryRunner creates
   a fresh session and manages model/tool/model turns. A session holds this run's
   conversation and tool results in RAM; no conversation is reused across tasks.
5. For the example prompt, Gemini is instructed to compile first and then pass the
   exact returned artifact ID to flash. Python does not preselect these calls.
   The flash stub rejects an unknown ID or a call before a build.
6. The runner executes requested tools and feeds results back to Gemini. Our event
   loop collects tool calls/results and the final answer, excluding thought parts.
7. FastAPI returns JSON; the runner is closed and its session is not persisted.

The runner allows at most eight model calls per task. Tool selection and wording
are model-driven, so inspect tool_events to see what actually happened. HTTP 200
means an answer was returned, not that real firmware was tested. Missing API key
returns 503; invalid task input returns 422; an unsuccessful Gemini/ADK run returns
502 without exposing provider internals.

Replace the two nested tool bodies in main.py with concrete runner operations
later, preserving structured success/error results and the artifact handoff. The
compile stub currently creates only an ID; the flash stub only checks that ID.
No arbitrary shell execution, real firmware validation, hardware
protocols, UART/FPGA retrieval, authentication, or dashboard integration is included.
Orchestration owns agent decisions and limits; runner will own concrete hardware
operations. Its unresolved interfaces are documented in src/runner/README.md.

## Offline tests

```sh
python -m pip install -r src/orchestration/requirements-dev.txt
python -m unittest src.orchestration.test_api
```

Tests replace only the model transport. They use the actual ADK runner to discover
and execute the real stub functions, verify artifact handoff and rejection, fresh
sessions, real file write/read/edit and persistence, workspace path rejection,
shell-tool exclusion, thought filtering, request validation, and error responses. They do not
verify Gemini connectivity, credentials, quota, or real model tool selection.
