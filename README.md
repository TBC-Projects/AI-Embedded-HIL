# AI Embedded Hardware-in-the-Loop

## Introduction
This document is intended to provide a comprehensive overview of our project's developments and serve as a reference tool for new members joining our team.

This report serves two primary functions:

1. **Project Review:** The document provides details on our established objectives, achievements, encountered challenges, key learnings, and prospective future plans. This reflective evaluation allows our team to track progress, make necessary adjustments, and maintain a clear vision moving forward.
2. **New Member Orientation:** The report also serves as a detailed onboarding guide designed to assist new members in understanding the project's context, objectives, and intricacies. We intend this guide to expedite the acclimatization process and equip newcomers with the necessary knowledge to contribute effectively in the forthcoming semester. Orientation slides: https://docs.google.com/presentation/d/1kqiqQ6VsCJaMvE94yqhtiwX4twRjIrdG3Ff06LFMH-U/edit?usp=sharing

## About the Project

* Project Title: AI Embedded Hardware-in-the-Loop
* Project Purpose: Autonomously write bare-metal C/C++ for a target microcontroller, flash it onto physical hardware, and verify real-time behavior with FPGA-assisted hardware-in-the-loop testing. When a run fails, the system uses the captured trace to revise the source until the checks pass.
* Brief Description: An orchestration engine turns a hardware specification into firmware. A runner cross-compiles and flashes a Raspberry Pi Zero W. A PYNQ-Z2 FPGA records pin timing and logic state and returns a trace for the next revision. Inspired by [Sentinel](https://devpost.com/software/sentinel-c8ki50).
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

The current implementation is a browser-local demonstration plus an independent
FastAPI skeleton. It does not call a model, compile firmware, upload binaries, or
access hardware. No authentication, database, or deployment is included.

Frontend (Node.js 22.14+):

```sh
cd src/dashboard
npm ci
npm run dev
```

Open the local URL printed by Vite. Run plays a fixed simulated UART example:
failed test → scripted revision → passing test. The task is not interpreted or
executed. All evidence and the illustrative diff are simulated, and the real device
indicator stays Disconnected. Stop cancels playback.

Backend (Python 3.10+, from the repository root):

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r src/orchestration/requirements.txt
python -m uvicorn src.orchestration.main:app --reload --host 127.0.0.1 --port 8000
```

`GET /health` returns 200. Valid `POST /tasks` requests return 501 because agent
execution is not implemented. The frontend does not need this server running.

| Directory | Responsibility and integration point |
| --- | --- |
| `src/dashboard/` | UI; typed workflow interface and replaceable mock workflow. Connect a future backend transport here. |
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
