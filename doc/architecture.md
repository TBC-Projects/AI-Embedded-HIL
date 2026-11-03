# Architecture

## Current MVP boundary

The dashboard is a React/TypeScript/Vite page with an independent, browser-local
mock workflow. It plays fixed sample agent actions, build output, UART feedback,
and a failed-test/revision/passing-test sequence. It does not execute the submitted
task. The FastAPI skeleton exposes health and rejects task execution with HTTP 501.
There is no active agent loop or runner service. See the component READMEs for setup.

The detailed Week 5–10 design below is historical planning, not an implemented or
agreed interface contract. Build ownership, binary format, upload/start, reset,
serial configuration, FPGA capture, and structured results remain unresolved.
Orchestration owns model calls and agent retries; runner owns concrete build and
hardware operations. These backend components can initially share one process.
The Pi executes firmware; the FPGA observes connected digital signals and explicit
debug milestones, not arbitrary program state.

## Planned architecture

The platform is split into a cognitive side and a physical side. The orchestrator decides what firmware to write and how to react to a failure. The runner, the Pi, and the FPGA only build, flash, execute, and measure.

```mermaid
flowchart LR
  spec[Hardware specification] --> orch[Orchestration engine]
  orch --> dash[Web dashboard]
  orch --> runner[Runner agent]
  runner --> gcc[Cross-compiler]
  gcc --> pi[Pi Zero W]
  pi --> fpga[Basys 3 pintrace6]
  fpga --> orch
```

## Components

### Web dashboard

Page for the people watching a run. It shows brief agent action summaries and tool
results, never private model reasoning. The MVP uses React, TypeScript, and Vite.
Real cross-compile status, generated code diffs, and FPGA timing diagrams remain
future integration work. The interactive waveform viewer is outside the MVP.

### Orchestration engine

Service that reads a specification, proposes firmware structure, calls a code model, and owns the retry loop. The agent framework is not chosen yet. Week 6 adds a backend that queues jobs and tracks state. The runner polls that queue. Week 8 adds the trace analyzer: fetch the FPGA trace, rebuild the timeline, and hand the agent a structured list of missing strobes, timing deltas, and races.

### Runner agent

Local daemon on the machine that can see the Pi. It takes generated source, runs the cross-compiler, flashes over UART with a CRC32 check, and starts the test. Week 8 adds a watchdog and a timeout so a hung binary cannot sit on the queue, plus a reset line that power-cycles or resets the Pi after a panic.

### Target hardware

Raspberry Pi Zero W running the test firmware bare metal. The Week 5 bootloader receives a prebuilt binary on the serial port and jumps to it in RAM. The SD card stays inserted.

### FPGA module

Basys 3 (Artix-7). The `pintrace6` core is a deterministic observer on the wires between the Pi and the bench: SPI, I2C, UART, PWM, and GPIO. It timestamps edges and checks them against the assertions for that run.

Week 5 capture core:

* 100 MHz timestamp counter
* Trigger on rising or falling edge
* Circular buffer in BRAM

Week 6 host path:

* The Basys 3 has no onboard processor, so the Runner PC takes the host role the PYNQ's Zynq cores would have played
* Capture registers are framed over the board's built-in USB-UART instead of memory-mapped
* The Runner PC exposes capture status, arm, capture, and trace to the orchestrator. The service stack is not chosen yet.

The trace path to the orchestrator is this USB-UART link and the Runner PC process reading it.

## Closed loop

Week 9 is the first time the whole path is required to heal itself.

1. A prompt asks for a bare-metal driver. Examples already in scope: BCM2835 system-timer delays, mini-UART init, interrupt setup.
2. The agent writes C.
3. The runner cross-compiles and flashes the Pi over UART.
4. The Pi toggles the milestone strobes. `pintrace6` records timestamps.
5. The analyzer compares the trace with the expected edges.
6. On a mismatch, the agent revises the source from that report and the job runs again.
7. The agent’s revised image passes on the next flash.

The stress test injects a timing bug or a wrong register bitmask into the prompt context so the first flash is expected to fail on the wires.

## Interfaces

| From | To | Contract |
| --- | --- | --- |
| Orchestrator | Runner | Job queue. The runner polls for source, builds it, and posts compile and flash results. The queue implementation is not chosen yet. |
| Runner | Pi Zero W | UART bootloader. Binary payload, CRC32, execute from RAM. |
| Runner | Pi reset | Week 8 hardware reset or power-cycle when the watchdog fires. |
| Orchestrator | PYNQ-Z2 | Capture status, arm, capture, and trace from the host process. |
| Pi GPIO | FPGA | Six milestone strobe pins plus a shared ground, landed on PMOD or Arduino headers. |
| Dashboard | Orchestrator | Action summaries and tool/compile results. The transport is not chosen yet. |
