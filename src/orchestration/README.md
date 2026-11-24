# Orchestration: minimal Gemini agent

One Google ADK Agent and InMemoryRunner handle each task. Gemini makes real API
calls and can use ADK's built-in ReadFile, WriteFile, and EditFile tools to create
real local source files. compile_firmware runs the harness code rules and build.py
(real ARM binaries); test_firmware boots that build in the QEMU gate (an emulated
Pi Zero). The order is compile -> test -> flash. Only flash_firmware remains simulated;
no Raspberry Pi is contacted. The dashboard still uses its separate browser-local mock workflow.

## Run locally

From the repository root, create a virtual environment (Python 3.11+ recommended):

```sh
python3 -m venv .venv
source .venv/bin/activate
./.venv/bin/python -m pip install -r src/orchestration/requirements.txt
cp .env.example .env          # once; then put your key in .env (see below)
./.venv/bin/python -m uvicorn src.orchestration.main:app --reload --host 127.0.0.1 --port 8000
```

Get a key from https://aistudio.google.com/apikey and put it in `.env` at the
repository root, after `GOOGLE_API_KEY=` (no quotes or spaces). `.env` is
git-ignored, so the key stays on your computer; never put a real key in
`.env.example`, which is committed. The server loads `.env` when it starts, so
restart it after changing the key. A key set in the terminal
(`export GOOGLE_API_KEY=...`) takes priority over `.env`. The backend reads
GOOGLE_API_KEY; this demo explicitly uses the Gemini API rather than Vertex
AI. Model: `gemini-3.8-flash` (the `MODEL` constant in main.py, without a `models/`
prefix because ADK resolves bare Gemini IDs). Actual model calls
require model access, available quota, and network connectivity.

In another terminal:

```sh
curl http://127.0.0.1:8000/health
curl -sS --max-time 90 http://127.0.0.1:8000/tasks \
  -H 'Content-Type: application/json' \
  -d '{"task":"Write build-demo/src/main.c with int main(void) that returns 0. Call compile_firmware with project_dir build-demo. If the build succeeds, call test_firmware with the returned artifact_id. If that passes, call flash_firmware once with the same artifact_id. Report the real build and QEMU results and the simulated flash result, then finish."}' \
  | python3 -m json.tool
```

The response contains `session_id`, `model`, `workspace`, `simulated`, `simulation_note`,
`tool_events` (calls, arguments, and results), and `final_response`. Tool events and
Gemini's final answer are also printed in the server terminal. `simulated: true`
refers to flashing only; Gemini, file operations, code checks, compilation, and the
QEMU run are real. The server logs
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
its three file tools and register them beside compile_firmware, test_firmware, and flash_firmware.
The shell Execute tool is not registered. Gemini supplies file paths and contents
as structured tool arguments; no code-block extractor is used. File tool calls
and results appear in the same transcript as compile/flash, including code content.
The compile result has `simulated: false`; the flash result has `simulated: true`.
The top-level simulation note explains that only flashing remains simulated.

## Real checks, compilation, and QEMU

Install the ARM tools and QEMU if needed (no additional Python dependency is required):

```sh
# macOS
brew install --cask gcc-arm-embedded
brew install qemu
# Ubuntu: sudo apt install gcc-arm-none-eabi qemu-system-arm
arm-none-eabi-gcc --version
arm-none-eabi-objcopy --version
qemu-system-arm --version     # 6.2 or newer
```

The agent's tools run in this order, passing the same `artifact_id` along:

```
compile_firmware(project_dir) -> test_firmware(artifact_id, expect_output) -> flash_firmware(artifact_id)
   harness + build (real)          QEMU (real)                     simulated
```

compile_firmware runs two stages and stops at the first failure. The result's
`failed_stage` names it (`null` on success):

| Tool / stage | What it checks | Typical failure (blame) |
|---|---|---|
| compile: `harness` | `src/build/harness.py` rules: only `src/<name>.c`/`.h`, no libc headers, no `printf`/`malloc`/`free`/`sprintf`, no startup symbols, `int main(void)` present | `#include <stdio.h>` (code) |
| compile: `build` | `src/build/build.py`: arm-none-eabi-gcc + objcopy | syntax error (code); toolchain missing (rig) |
| `test_firmware` | `src/build/qemu_gate.py`: runs the build in `qemu-system-arm -M raspi0` for 5 s; it must boot and keep running without `hil_panic` (and print `expect_output`, if given) | `hil_panic`, crash before `main`, QEMU exits, `expect_output` never printed (code); QEMU missing (rig) |

The harness reads its usual `=== FILE src/<name> ===` text, so the project's `src/`
files are packed into that format and checked in a temporary folder; the agent's
project folder is never modified by the harness.

test_firmware works like flash_firmware: it only accepts the exact `artifact_id`
from the latest successful compile_firmware in this task, and rejects anything
else without running QEMU. It runs in its own subfolder of the project:

```
build-demo/
  src/main.c            the agent's code
  kernel.elf, kernel.bin, build.log    from compile_firmware
  test_firmware/
    kernel.elf          copy of the build that was tested
    qemu.log            QEMU console output (HIL:BOOT, then whatever the firmware prints)
```

The result includes the console output (`console`) and the folder (`test_dir`).

Firmware normally loops forever and never returns from `main`, so the QEMU test
does not wait for the program to finish. It runs it for 5 seconds
(`qemu_gate.TIMEOUT_S`) and decides:

| What happens in QEMU | Result |
|---|---|
| `HIL:PANIC` | fail |
| QEMU exits on its own | fail |
| no `HIL:BOOT` (crashed before `main`) | fail |
| `expect_output` given and printed | pass, right away |
| `expect_output` given but not printed in 5 s | fail |
| no `expect_output`: booted, no panic, still running after 5 s | pass ("still running") |
| `HIL:DONE` (`main` returned; small test programs) | pass |

A run-only pass just means it didn't crash. For a meaningful check, have the
firmware print a status line (for example `hil_puts("UART ready\n")`) and pass
that text as `expect_output`.

For example, have the agent write `build-demo/src/main.c`, then call
`compile_firmware(project_dir="build-demo")`. The directory must be inside the
shared workspace. With no argument, the tool builds the workspace root and expects
`src/*.c` there. The existing build stage compiles direct children of `src/`, not
arbitrarily nested sources. A standalone file such as `uart-hello/main.c` must be
placed under `uart-hello/src/main.c` before using that project layout.

Before each build, orchestration copies the fixed `start.S`, `linker.ld`, `hil.c`,
and `hil.h` files from `src/build/target/` into the project root, replacing those
support copies. Generated firmware should not edit them. Use freestanding C with
`int main(void)`; libc/stdio are unavailable. For UART output, include `hil.h` and
use `hil_puts`. Then the existing `build.run(project)` compiles and links the code
and produces `kernel.elf`, `kernel.bin`, and `build.log` in that project.

The blocking harness, build, and QEMU steps run in a worker thread so terminal heartbeats and other HTTP
requests can continue. A successful compile returns an artifact ID and the existing
build metadata: ELF/binary paths, byte length, and CRC32. The flash stub accepts the
ID only after that same build passed test_firmware in this task. A new compile, or a
failed test, clears it.

Rule violations, compiler errors, and QEMU failures return `status: error`,
`blame: code`, and feedback Gemini can use to edit the file and compile again.
Missing tools/support files are setup failures (`blame: rig`); the agent should
report them rather than rewrite firmware. QEMU does not model real timing, so
passing it does not prove timing on hardware. Hardware execution and UART/FPGA
collection are not called by this integration.
LocalEnvironment is a local development tool, not an OS sandbox.

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
3. That function defines compile_firmware, test_firmware, and flash_firmware, with build state
   private to this request. ADK turns their names, docstrings, and type annotations
   into tool descriptions Gemini can use.
4. ADK's EnvironmentToolset supplies three local file tools in the shared workspace.
   An Agent gives Gemini instructions, those file tools, the real compile and
   QEMU test tools, and the simulated flash tool. An InMemoryRunner creates
   a fresh session and manages model/tool/model turns. A session holds this run's
   conversation and tool results in RAM; no conversation is reused across tasks.
5. For the example prompt, Gemini is instructed to compile, then test, then flash,
   passing the exact returned artifact ID along. Python does not preselect these calls.
   test_firmware rejects an unknown ID or a call before a build; the flash stub
   rejects anything that has not passed test_firmware.
6. The runner executes requested tools and feeds results back to Gemini. Our event
   loop collects tool calls/results and the final answer, excluding thought parts.
7. FastAPI returns JSON; the runner is closed and its session is not persisted.

The runner allows at most eight model calls per task. Tool selection and wording
are model-driven, so inspect tool_events to see what actually happened. HTTP 200
means an answer was returned, not that real firmware was tested. Missing API key
returns 503; invalid task input returns 422; an unsuccessful Gemini/ADK run returns
502 without exposing provider internals.

The compile and test tools reuse the harness, build, and QEMU stages directly; they
do not call the unfinished runner. The flash stub only checks the artifact ID.
No general shell tool, runtime firmware validation, hardware
protocols, UART/FPGA retrieval, authentication, or dashboard integration is included.
Orchestration owns agent decisions and limits; runner will own concrete hardware
operations. Its unresolved interfaces are documented in src/runner/README.md.

## Offline tests

```sh
python -m pip install -r src/orchestration/requirements-dev.txt
python -m unittest src.orchestration.test_api
```

Tests replace the model transport. Most mock the harness rules, build stage, and
QEMU gate (passing by default) to test ADK plumbing; integration tests use the
installed ARM compiler (and QEMU for one end-to-end test) and are skipped if absent.
They verify harness rejection before gcc runs, test_firmware running QEMU in the
project's test_firmware/ folder and rejecting unknown IDs, flashing only after a
passing test, QEMU failures blocking flashing,
real binary creation and metadata, compiler-error feedback and repair,
missing tools, invalidation after a failed rebuild, artifact handoff, fresh
sessions, real file write/read/edit and persistence, workspace path rejection,
shell-tool exclusion, thought filtering, request validation, and error responses. They do not
verify Gemini connectivity, credentials, quota, or real model tool selection.
