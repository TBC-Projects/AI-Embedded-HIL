# AI Embedded Hardware-in-the-Loop

## Introduction
This document is intended to provide a comprehensive overview of our project's developments and serve as a reference tool for new members joining our team.

This report serves two primary functions:

1. **Project Review:** The document provides details on our established objectives, achievements, encountered challenges, key learnings, and prospective future plans. This reflective evaluation allows our team to track progress, make necessary adjustments, and maintain a clear vision moving forward.
2. **New Member Orientation:** The report also serves as a detailed onboarding guide designed to assist new members in understanding the project's context, objectives, and intricacies. We intend this guide to expedite the acclimatization process and equip newcomers with the necessary knowledge to contribute effectively in the forthcoming semester. Orientation slides: https://docs.google.com/presentation/d/1kqiqQ6VsCJaMvE94yqhtiwX4twRjIrdG3Ff06LFMH-U/edit?usp=sharing

## About the Project

* Project Title: AI Embedded Hardware-in-the-Loop
* Project Purpose: Autonomously write bare-metal C/C++ for a target microcontroller, flash it onto physical hardware, and verify real-time behavior with FPGA-assisted hardware-in-the-loop testing. When a run fails, the system uses the captured trace to revise the source until the checks pass.
* Brief Description: An orchestration engine turns a hardware specification into firmware. A runner cross-compiles and flashes a Raspberry Pi Zero W. A Basys 3 FPGA records pin timing and logic state and returns a trace for the next revision over its onboard USB-UART. Inspired by [Sentinel](https://devpost.com/software/sentinel-c8ki50).
* Contributors Involved: name, name, name
* Git Repo Link: https://github.com/TBC-Projects/AI-Embedded-HIL

## Accomplishments


## Challenges Faced

## Potential Improvements


## Relevant Resources


## Other Information

* Define Abbreviations
  * TBC - The Boring Club
  * HIL - Hardware-in-the-Loop
  * FPGA - Field-Programmable Gate Array
  * GPIO - General-Purpose Input/Output
  * UART - Universal Asynchronous Receiver-Transmitter
* Team Leads
  1. Adelin Ma
  2. Elias Assalif
  3. Ruiqi Liu

## Local MVP

The current implementation is a React dashboard connected to a FastAPI backend
using Google ADK and Gemini with local file tools, real ARM
compilation through `src/orchestration/compiler.py`, bounded QEMU UART observations,
and simulated flashing. The agent can
save and revise real source files in the shared
`src/orchestration/workspaces/` directory across all chats. Conversation context and activity logs persist in SQLite;
follow-up messages reuse the selected chat. Builds require the ARM toolchain described in the orchestration README.
The backend does not upload binaries or access hardware. SQLite is built into
Python; pip installs its async adapter. No authentication or deployment is included.

Frontend (Node.js 22.14+):

```sh
cd src/dashboard
npm ci
npm run dev
```

Open the local URL printed by Vite after starting the backend below. Send submits
your message to the real agent in the selected chat. The sidebar selects saved
conversations; each turn keeps its chronological backend/QEMU log and Markdown answer. Stop
cancels backend work and waits for cleanup. Only one run can be active at a time.

Backend (Python 3.10+, from the repository root).

macOS / Linux:

```sh
python3 -m venv .venv
source .venv/bin/activate
./.venv/bin/python -m pip install -r src/orchestration/requirements.txt
export GOOGLE_API_KEY='your-Google-AI-Studio-API-key'
./.venv/bin/python -m uvicorn src.orchestration.main:app --reload --host 127.0.0.1 --port 8000
```

Windows (PowerShell):

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r src\orchestration\requirements.txt
$env:GOOGLE_API_KEY = "your-Google-AI-Studio-API-key"
.\.venv\Scripts\python.exe -m uvicorn src.orchestration.main:app --reload --host 127.0.0.1 --port 8000
```

On Windows, `Activate.ps1` may be blocked by the execution policy, so the block
above calls `.\.venv\Scripts\python.exe` directly; `curl` is an alias for
`Invoke-WebRequest`, so use `curl.exe` or `Invoke-RestMethod`.

`GET /health` returns 200. `POST /tasks` sends the prompt to a Gemini agent with
local file tools, real compile and bounded QEMU tools, and simulated flashing. It returns the workspace path,
answer, and tool transcript. See the [file generation example](src/orchestration/README.md#generate-a-real-local-file) and
[test prompts and long-wait notes](src/orchestration/README.md#long-waits-and-test-prompts)
before testing: some runs have waited a long time for a final model response, and
there is no overall backend timeout. The frontend needs this server running and
uses /tasks/stream through Vite's /api proxy. Closing the stream cancels its run.

| Directory | Responsibility and integration point |
| --- | --- |
| `src/dashboard/` | Saved conversation sidebar, messages, streamed backend/QEMU logs, Stop, and answers. |
| `src/orchestration/` | API and future isolated agent loop, permitted tool calls, revisions, and retry limits. |
| `src/runner/` | Future build/artifact handling, upload/start, UART/FPGA feedback, timeout/reset/recovery. No service yet. |
| `src/target/` | Raspberry Pi firmware (unchanged). |
| `src/fpga/` | Separate signal capture logic (unchanged). |
| `doc/` | Architecture, hardware planning, and roadmap. |

The Pi executes firmware. The FPGA observes connected digital signals and emitted
debug milestones, not arbitrary program state. Historical hardware protocol details
in planning documents are proposals: build ownership, binary format, upload/start,
reset, serial configuration, FPGA capture, and result format still require agreement.
Orchestration owns the agent workflow; runner owns concrete build/hardware operations.
They can share one backend process. Keep model credentials on the backend outside Git.

See [dashboard setup and checks](src/dashboard/README.md),
[API setup and checks](src/orchestration/README.md), and
[runner responsibilities and open decisions](src/runner/README.md).
