# Orchestration: minimal Gemini agent

One Google ADK Agent and InMemoryRunner handle each task. Gemini makes real API
calls and can use ADK's built-in ReadFile, WriteFile, and EditFile tools to create
real local source files. compile_firmware calls the local compiler.py helper to produce
real ARM binaries. Only flash_firmware remains simulated; no Raspberry Pi is
contacted. run_qemu can execute a build for a bounded observation window and return
its UART output to Gemini. The dashboard streams real backend activity and inline QEMU captures.

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
  -d '{"task":"Write build-demo/src/main.c with int main(void) that returns 0. Call compile_firmware with project_dir build-demo. If the build succeeds, call flash_firmware once with the returned artifact_id. Report the real build result and simulated flash result, then finish."}' \
  | python3 -m json.tool
```

The response contains `session_id`, `model`, `workspace`, `simulated`, `simulation_note`,
`tool_events` (calls, arguments, and results), and `final_response`. Tool events and
Gemini's final answer are also printed in the server terminal. `simulated: true`
refers to flashing only; Gemini, file operations, and compilation are real. The server logs
session setup, model requests/responses, tool execution, completion/failure, and
cleanup with a run ID and elapsed seconds. Every 10 seconds a local heartbeat
reports the current stage; it does not imply Google is making progress. Prompts
and model thought content are not logged. There is no overall time limit yet.
API docs are at
http://127.0.0.1:8000/docs. POST /tasks keeps its JSON response for curl.
The dashboard uses POST /tasks/stream for live logs; no background job queue is used.

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
its three file tools and register them beside compile_firmware, run_qemu, and flash_firmware.
An additional ordinary Python tool, `list_directory(path=".")`, discovers existing
projects in the shared workspace. It returns names, types, and workspace-relative
paths for one directory level. The agent can then list subdirectories and use
ReadFile on the returned paths. It rejects paths outside the workspace, including
links resolving outside it. Results are sorted and capped at 200 entries, with a
`truncated` flag; it reads no file contents and runs no shell commands.

Try in the dashboard: “List the workspace, explore the source folders, and explain
what the existing firmware does. Do not change, compile, or run anything.”

The shell Execute tool is not registered. Gemini supplies file paths and contents
as structured tool arguments; no code-block extractor is used. File tool calls
and results appear in the same transcript as compile/flash, including code content.
The compile result has `simulated: false`; the flash result has `simulated: true`.
The top-level simulation note explains that only flashing remains simulated.

## Real compilation

Install both ARM tools if needed (no additional Python dependency is required):

```sh
# macOS
brew install --cask gcc-arm-embedded
# Ubuntu: sudo apt install gcc-arm-none-eabi
arm-none-eabi-gcc --version
arm-none-eabi-objcopy --version
```

For example, have the agent write `build-demo/src/main.c`, then call
`compile_firmware(project_dir="build-demo")`. The directory must be inside the
shared workspace. With no argument, the tool builds the workspace root and expects
`src/*.c` there. The compiler helper compiles direct children of `src/`, not
arbitrarily nested sources. A standalone file such as `uart-hello/main.c` must be
placed under `uart-hello/src/main.c` before using that project layout.

Before each build, orchestration copies the fixed `start.S`, `linker.ld`, `hil.c`,
and `hil.h` files from `src/orchestration/firmware/` into the project root, replacing those
support copies. Generated firmware should not edit them. Use freestanding C with
`int main(void)`; libc/stdio are unavailable. For UART output, include `hil.h` and
use `hil_puts`. Then `compiler.run(project)` compiles and links the code
and produces `kernel.elf`, `kernel.bin`, and `build.log` in that project.

All Python and firmware support for this agent MVP lives in this directory:

```text
src/orchestration/
  main.py             FastAPI, ADK agent, and tools
  compiler.py         ARM compiler invocation and structured build results
  qemu.py             bounded execution and UART/diagnostic capture
  firmware/
    start.S           stack/BSS setup, then hil_init -> main -> hil_exit
    linker.ld         memory layout and entry point
    hil.c             UART output, status markers, GPIO helpers
    hil.h             declarations and register definitions
  workspaces/         persistent generated projects and build output (ignored by Git)
```

The compiler helper and templates were adapted from the separate `src/build/`
pipeline, but orchestration does not import or copy files from it anymore.
External requirements are still the Python packages and ARM toolchain.
Change the templates in `firmware/`, not generated workspace copies: the next
compile refreshes the copies. After main returns, hil_exit prints `HIL:DONE` and
loops without requesting a watchdog reset. QEMU stays open until stopped.
hil_panic retains its existing watchdog reset behavior on an explicit failure.

The blocking build runs in a worker thread so terminal heartbeats and other HTTP
requests can continue. Success returns an artifact ID and the existing build
metadata: ELF/binary paths, byte length, and CRC32. The flash stub accepts the ID
only from the latest successful build in this task. A failed rebuild clears it.

Compiler errors return `status: error`, `blame: code`, and feedback Gemini can
use to edit the file and compile again. Missing tools/support files are setup
failures (`blame: rig`); the agent should report them rather than rewrite firmware.
A successful compilation does not establish correct runtime behavior. Use run_qemu
for emulator observations. Physical hardware execution and FPGA capture remain future work.
LocalEnvironment is a local development tool, not an OS sandbox.

## Observe firmware in QEMU

Install QEMU if needed: `brew install qemu` on macOS, or
`sudo apt install qemu-system-arm` on Ubuntu. No extra Python dependency is needed.

Restart the backend, then in another terminal:

```sh
curl -sS --max-time 90 http://127.0.0.1:8000/tasks \
  -H 'Content-Type: application/json' \
  -d '{"task":"Use WriteFile to create qemu-demo/src/main.c that includes hil.h and defines int main(void) which calls hil_puts with Hello from firmware, then returns 0. Compile project qemu-demo. If compilation succeeds, call run_qemu with the returned artifact_id and duration_seconds 1. Interpret its uart_output and qemu_errors, report what was observed, and finish. Do not flash."}' \
  | python3 -m json.tool
```

The agent calls `run_qemu(artifact_id, duration_seconds=1.0)`. The ID must come
from the latest successful compile in this task. Each call starts a fresh QEMU
process, collects output, stops it, and returns the observation to Gemini through
ADK's normal tool-result flow. It does not keep an emulator running between calls.

The helper launches the same `qemu-system-arm -M raspi0 -kernel ... -display none
-serial stdio -monitor none` command used manually, with stdout/stderr pipes.
It drains both pipes while running. The observation defaults to one second and
can be greater than zero up to ten seconds. Startup and cleanup add overhead.
The process is also stopped and reaped if the agent task is cancelled.

The tool returns `uart_output`, `qemu_errors`, `observed_seconds`, `execution_status`,
`stopped_by`, and `exit_code`. An observation ending normally has
`execution_status: observation_complete` and `stopped_by: observation_limit`;
`exit_code` is null because Python intentionally stopped QEMU. An early process
exit includes its exit code. Missing QEMU or ELF returns an infrastructure error.
Output is limited to the first 64 KiB per stream, with truncation flags; excess
bytes are drained and discarded to avoid blocking the emulator or growing RAM usage.

The UART log and diagnostics appear in `tool_events` in the API response and the
backend terminal. Gemini can interpret them, edit files, rebuild, and run again.
`HIL:DONE` does not stop observation early; firmware that loops forever is also
observed for the chosen window. Tool success means output collection completed,
not that firmware passed a test. Empty output, HIL:PANIC, or unexpected text are
evidence for the agent to interpret against your task. This is not an FPGA trace
or a measurement of real hardware timing. No mandatory QEMU pass gate is added
to the simulated flash tool. Rebuilding invalidates the previous run's artifact ID.

## Long waits and test prompts

Before real compilation was integrated, a local run completed both simulated tools but
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
3. That function defines compile_firmware, run_qemu, and flash_firmware, with build state
   private to this request. ADK turns their names, docstrings, and type annotations
   into tool descriptions Gemini can use.
4. ADK's EnvironmentToolset supplies three local file tools in the shared workspace.
   An Agent gives Gemini instructions, those file tools, the real compile/QEMU tools,
   and simulated flash tool. An InMemoryRunner creates
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

The compile tool uses this directory's compiler.py; it does not call src/build,
the harness, or the rest of that pipeline. The flash stub only checks the artifact ID.
No general shell tool, automatic firmware test verdict, physical hardware
protocols, FPGA retrieval, or authentication is included.
Orchestration owns agent decisions and limits; runner will own concrete hardware
operations. Its unresolved interfaces are documented in src/runner/README.md.

## Offline tests

```sh
python -m pip install -r src/orchestration/requirements-dev.txt
python -m unittest src.orchestration.test_api src.orchestration.test_qemu src.orchestration.test_stream
```

Tests replace the model transport. Most mock the build stage to test ADK plumbing;
integration tests use the installed ARM compiler and are skipped if it is absent.
They verify real binary creation and metadata, compiler-error feedback and repair,
QEMU UART feedback reaching the model, bounded process cleanup (including cancellation),
early errors and bounded output buffers,
missing tools, invalidation after a failed rebuild, artifact handoff, fresh
sessions, real file write/read/edit and persistence, workspace path rejection,
shell-tool exclusion, thought filtering, request validation, and error responses. They do not
verify Gemini connectivity, credentials, quota, or real model tool selection.

## Dashboard streaming and Stop

Start this backend on 127.0.0.1:8000, then run `npm run dev` in src/dashboard and
open Vite's Local URL. The frontend proxies /api to this backend. Run submits one
prompt and streams application log messages, inline QEMU UART captures, and the
final answer. It does not manufacture progress stages or firmware test verdicts.

`POST /tasks/stream?run_id=<UUID>` accepts the same task JSON as /tasks. It returns
application/x-ndjson: each line is either a `log` event (run_id, timestamp, source,
message, optional details) or a `final` event containing the result. QEMU UART is
labeled `QEMU UART`; emulator diagnostics are labeled `QEMU`. Provider errors are
redacted and sent as Error log entries. No prompts or model thought parts are
logged. HTTP validation, missing-key, and busy errors happen before streaming.

`POST /tasks/<UUID>/stop` cancels that active run and waits for cleanup. Closing
the stream also cancels the run. Cancelled QEMU observations terminate their child
processes. A compiler already running in a worker thread finishes before the
workspace is released, so Stop may briefly wait. The log explains this wait.

Both task endpoints share one active-run limit per backend process. A second run
returns 409 rather than editing the shared files concurrently. Use a single
Uvicorn worker for this local MVP. Sessions and logs are not persisted or resumable.
The existing POST /tasks still returns its original complete JSON result.

The HTTP streaming tests bind a temporary loopback port and verify events arriving
before completion, conflict rejection, Stop cleanup, and cancellation on disconnect.
