# HIL pipeline (steps 4–7)

Takes code written by an LLM and checks it in stages: first cheaply, then on an emulator, and finally on the real Raspberry Pi Zero with the Basys 3 FPGA recording its pins.

```
LLM reply ──► harness ──► build ──► QEMU gate ──► runner ──► (analyzer, step 11, not written yet)
              check text   gcc       emulated Pi   real Pi + FPGA trace
```

The pipeline stops at the first stage that fails. Every stage returns a `StageResult` (see `common.py`):

| Field | Meaning |
|---|---|
| `ok` | passed? If not, the pipeline stops here |
| `summary` | one line for logs and the dashboard |
| `feedback` | on failure, text written for the LLM |
| `blame` | `"code"`: send the feedback to the LLM and try again. `"rig"`: tool or hardware problem, so retry without the LLM |
| `artifacts` | data for later stages: file paths, console output, the FPGA trace |

## Files

| File | What it does | Read this if you're working on... |
|---|---|---|
| `pipeline.py` | runs the stages in order; the command-line entry point | the orchestrator |
| `common.py` | `StageResult`, blame values, `HIL:*` console markers | any stage |
| `harness.py` | splits the LLM reply into files and rejects obvious mistakes | the LLM prompt, new code rules |
| `build.py` | compiles with `arm-none-eabi-gcc` → `kernel.elf`, `kernel.bin` | compiler flags, the linker script |
| `qemu_gate.py` | boots `kernel.elf` on an emulated Pi Zero | anything run before real hardware |
| `runner.py` | flashes the real Pi over UART, reads its console, downloads the FPGA trace | the bootloader, the FPGA trace core |
| `target/` | `start.S`, `linker.ld`, `hil.c`, `hil.h`: fixed files built into every program. The LLM never edits these | Pi-side support code |
| `examples/` | sample LLM replies: good, rejected, compile error, hang | trying the pipeline |
| `tests/` | pytest tests. `fake_rig.py` fakes the Pi and FPGA so the runner can be tested without hardware | — |

## Setup

```bash
brew install --cask gcc-arm-embedded && brew install qemu
```

```bash
pip install pyserial pytest
```

On Ubuntu, use `sudo apt install gcc-arm-none-eabi qemu-system-arm` instead of the brew command.

## Running (from `src/build/`)

Run the tests. Tests that need gcc or QEMU are skipped if the tool isn't installed:
```bash
python3 -m pytest tests
```

Run a sample reply through harness → build → QEMU:
```bash
python3 pipeline.py examples/blink_reply.txt
```

Also run it on the real rig:
```bash
python3 pipeline.py examples/blink_reply.txt --pi /dev/tty.usbserial-XXXX --fpga /dev/tty.usbserial-YYYY
```

Each attempt is written to `jobs/demo/attempt-1/`, which git ignores: the LLM's files, `kernel.elf`, `kernel.bin`, and `build.log`.

## How the Pi program reports back

`target/hil.c` prints these markers on the Pi's serial console. The QEMU gate and the runner both look for them:

| Marker | Printed when |
|---|---|
| `HIL:BOOT` | before `main()` runs |
| `HIL:DONE` | after `main()` returns (then the Pi reboots into the bootloader) |
| `HIL:PANIC <reason>` | the program called `hil_panic("reason")` |

## Serial protocols (proposed: the firmware must match)

The full details are at the top of `runner.py`. In short:

- **Pi bootloader:**
  - The Pi sends `RDY` while it's waiting.
  - The host sends `HIL1` + length + CRC32 + the binary.
  - The Pi answers `OK` (CRC matched) or `ER` (resend).
- **FPGA trace core:**
  - `A` arms it and `S` stops it. The FPGA answers each with `K`.
  - `D` dumps the recorded edges as 8-byte records: a timestamp in 10 ns ticks, the pin levels, and which pins changed.

## Getting started (new members)

Each stage file (`harness.py`, `build.py`, `qemu_gate.py`, `runner.py`, `pipeline.py`) starts with a long comment. It explains the background, what to build, suggested steps, and how to check your work. The code underneath is empty on purpose: you write it.

Recommended order:

| Order | Deliverable | File | You'll learn | Hardware needed |
|---|---|---|---|---|
| 1 | D1 Harness | `harness.py` | strings, regex, files | none |
| 2 | D2 Build | `build.py` | running programs from Python, cross-compiling | none |
| 3 | D3 QEMU gate | `qemu_gate.py` | emulators, reading a running process | none |
| 4 | D4 Runner (pairs) | `runner.py` | serial ports, binary protocols | none (uses fakes in `tests/fake_rig.py`) |
| 5 | D8 Pipeline | `pipeline.py` | putting it together | optional |

Steps:
1. Read `common.py` first. It's short, and every stage uses it.
2. Open your deliverable's file and read the whole top comment before writing any code.
3. Try the "by hand" commands in the comment, if there are any.
4. Run only your own tests while you work, e.g. `python3 -m pytest tests/test_harness.py -v`.
   They fail with `NotImplementedError: TODO` until you write the code; that's expected.
5. Don't edit the files in `tests/`. They're how we know a deliverable is done.

## Still to write

- The Pi UART bootloader. It must speak the protocol above, set up UART0, and move itself above 16 MB so it never overlaps a program.
- The Basys 3 trace core.
- The analyzer (step 11). It checks `artifacts["trace"]` from the runner.
