# Roadmap

Follow the Week 5–10 plan for the rest of this quarter. The two-quarter outline further down is the broader scope. Winter quarter is the extension set, and it starts after the Week 9 loop passes.

## This quarter: Weeks 5–10

### Week 5 — Concurrent subsystem bring-up

| Co-lead | Work |
| --- | --- |
| 1. Agent orchestration and telemetry | Scaffold the agent pipeline. The agent framework is not chosen yet. Ingest a repository and generate basic C for a target spec, starting with a GPIO register-write function. |
| 2. FPGA logic | Synthesize `pintrace6` for the PYNQ-Z2. Check the 100 MHz timestamp counter, rising/falling trigger, and circular BRAM buffer with a testbench or a waveform generator. |
| 3. Target hardware and toolchain | Stand up a bare-metal cross-compiler and custom linker script. The toolchain packaging is not chosen yet. Bring up the bare-metal UART bootloader on the Pi Zero W so it can receive a precompiled binary over serial and run it from RAM without pulling the SD card. |

### Week 6 — Communication layer and driver interfaces

| Co-lead | Work |
| --- | --- |
| 1 | Backend for the job queue and state transitions. Dashboard shell that shows agent reasoning and compile logs as they happen. Neither stack is chosen yet. |
| 2 | Map AXI-Lite registers to the PYNQ-Z2 processing system through `/dev/mem`. Host service on the PYNQ image for capture status, arm, capture, and trace. The service stack is not chosen yet. |
| 3 | Runner daemon that polls the job queue, runs the cross-compiler, and performs the serial flash handshake with CRC32. |

### Week 7 — Physical handshake

| Owners | Work | Exit check |
| --- | --- | --- |
| Leads 2 and 3 | Wire six GPIO milestone strobes and ground from the Pi Zero W to the PYNQ-Z2 PMOD or Arduino headers. | Pins named in [hardware.md](hardware.md). |
| Leads 1 and 3 | Point the orchestrator output queue at the runner. The agent emits a C file that toggles the strobes. The runner compiles, flashes over UART, and the Pi boots. | Read the PYNQ capture and confirm the FPGA timestamps match the GPIO toggles. |

### Week 8 — Feedback loop and trace diffing

| Owners | Work | Exit check |
| --- | --- | --- |
| Lead 1 | Trace analyzer. Fetch the FPGA trace, rebuild the timeline, and report missing strobes, timing deltas, and races in a form the agent can read. | |
| Leads 2 and 3 | Runner watchdog, timeouts, and a hardware reset so a panic or a hang power-cycles the Pi and frees the queue. | A structured post-mortem arrives from the hardware with no one in the loop. |

### Week 9 — Autonomous self-healing

All three leads. Ask the system for a full bare-metal driver from a datasheet. In-scope examples: BCM2835 system-timer delays, mini-UART initialization, interrupt handling. Put a subtle timing bug or a wrong register bitmask into the prompt context so the first run fails on the hardware.

Exit check:

`Prompt → Generate C → Flash Pi → FPGA trace → Detect fault → Auto-refactor → Pass`

The agent corrects the bug from the FPGA trace and the rerun is clean.

### Week 10 — Benchmark, telemetry, winter handoff

All three leads.

* Reliability runs on at least five different bare-metal tasks. Record autonomous pass rate and time-to-fix.
* Waveform viewer next to the agent thought log.
* Write down the platform architecture, the queue and trace interfaces, and the wiring pinout.
* Leave the tree ready for winter: a multi-node target farm, or a harder protocol such as HDMI or Bluetooth.

## Original two-quarter outline

### Quarter 1 — Foundation and infrastructure

| Weeks | Goal |
| --- | --- |
| 1–3 | Define the agent-to-runner IPC schema. Stand up bare-metal toolchain scripts and an automated flash pipeline. |
| 4–6 | Verilog or VHDL for high-speed GPIO and bus capture. Shared-memory DMA buffers that move traces to the host. |
| 7–10 | Orchestrator prompts aimed at bare-metal patterns. First dashboard for test cycles and logic traces. |

Weeks 5–10 of the plan above are the schedule that replaced the overlapping part of this outline. The orchestrator hands work to the runner through a job queue. Trace readout is the AXI-Lite register map plus a host service on the PYNQ.

### Quarter 2 — Closed loop and refinement

| Weeks | Goal |
| --- | --- |
| 1–4 | Join orchestrator, runner, target, and FPGA into one continuous loop. Measure flash-run-verify latency. |
| 5–8 | Teach the orchestrator to read waveform mismatches. Multi-step revisions driven by hardware feedback. |
| 9–11 | Multi-protocol tasks, such as a driver for a complex sensor. Dashboard polish, faster compiles, and final documentation. |

Week 9 of the current plan is the first version of this loop. Quarter 2 work that is still open after Week 10 moves to winter.

## Winter quarter

The bench is assumed to already close the loop. Winter uses it.

| Track | Goal |
| --- | --- |
| Self-Defining Systems | Extend the agent from “write this firmware” to “watch health across layers.” One stated target is KV-cache management and data movement on edge devices. |
| Advanced protocol synthesis | Bare-metal HDMI, Bluetooth, or USB from specification PDFs, with the FPGA checking timing. |
| Edge-device farm | One runner becomes a pool of 5–10 microcontrollers so the agent can test parallel RTOS implementations on real boards at the same time. |
