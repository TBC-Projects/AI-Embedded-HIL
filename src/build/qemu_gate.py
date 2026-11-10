"""
DELIVERABLE D3: THE QEMU GATE
=============================

BACKGROUND (read this first)
----------------------------
QEMU is an EMULATOR: a program that pretends to be a different computer.
`qemu-system-arm -M raspi0` pretends to be a Raspberry Pi Zero, so we can run
the AI's program on a fake Pi in our laptop before trying the real one.
This is much faster than real hardware, and if the AI's code is broken,
nothing physical gets stuck.

The Pi has no screen. It talks through a SERIAL PORT (a simple cable that sends
text one character at a time). With `-serial stdio`, QEMU turns the Pi's serial
port into normal program output (stdout), which Python can read.

Our support code (target/hil.c) makes every program print these MARKERS:
    HIL:BOOT             the program started
    HIL:DONE             the program finished normally
    HIL:PANIC <reason>   the program hit an error and gave up
(The marker strings are also in common.py as MARK_BOOT, MARK_DONE, MARK_PANIC.)

Install QEMU:
    Mac:    brew install qemu
    Ubuntu: sudo apt install qemu-system-arm
    Check:  qemu-system-arm --version   (needs 6.2 or newer)

TRY IT BY HAND first (after D2 works, or with any kernel.elf):
    qemu-system-arm -M raspi0 -kernel kernel.elf -display none -serial stdio -monitor none
You'll see HIL:BOOT ... HIL:DONE, and then QEMU KEEPS RUNNING (the program
reboots after DONE). Press Ctrl+C to stop it. Your code must stop it too.


WHAT TO BUILD
-------------
run(elf, timeout_s=5.0) -> StageResult

STEPS
    1. Start QEMU as a background process with subprocess.Popen, using:
           qemu-system-arm -M raspi0 -kernel <elf> -display none -serial stdio -monitor none
       If QEMU isn't installed, Popen raises FileNotFoundError: report blame="rig".
    2. Keep reading QEMU's output, adding it to a string.
       Stop as soon as you see HIL:DONE or HIL:PANIC, or when timeout_s seconds pass.
    3. ALWAYS stop QEMU at the end: proc.kill() then proc.wait().
       Use try/finally so this happens even if your code crashes.
    4. Decide the result from what was printed:

       what the console showed              result  summary must contain
       HIL:DONE                             pass
       HIL:PANIC                            fail    "hil_panic"
       HIL:BOOT, but no DONE in time        fail    "no HIL:DONE"   (an infinite loop)
       nothing at all                       fail    "never reached main"

       Every failure is blame="code" (except QEMU not installed). The feedback
       should include the last ~20 lines of console output, so the AI can see
       what happened: common.tail(text, 20).

THE TRICKY PART: reading without getting stuck
    proc.stdout.read() waits until QEMU EXITS, which never happens. And
    readline() waits forever if the program prints nothing. Use the
    `selectors` module to wait at most 0.1 s for new output. You may copy this:

        import selectors, subprocess, time
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        sel = selectors.DefaultSelector()
        sel.register(proc.stdout, selectors.EVENT_READ)
        output = b""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if sel.select(timeout=0.1):              # is there new output?
                output += proc.stdout.read1(4096)    # read what's there; don't wait
            text = output.decode(errors="replace")
            # ... check text for the markers, and break when done ...

    The console uses "\\r\\n" line endings. Use .replace("\\r", "") to clean them up.

DON'T check timing here. QEMU's speed isn't realistic; the real FPGA measures timing.


WHAT TO RETURN
--------------
    StageResult("qemu", ok, summary, feedback=..., blame=..., artifacts={"console": text})


HOW YOU KNOW YOU'RE DONE
------------------------
From src/build/, run:   python3 -m pytest tests/test_qemu_gate.py -v
(Skipped if QEMU or gcc isn't installed: install both first!)
A passing program must finish in under 3 seconds, so you must stop as soon as you
see HIL:DONE, not wait for the timeout.
"""
from __future__ import annotations

from pathlib import Path

from common import StageResult

QEMU = "qemu-system-arm"
TIMEOUT_S = 5.0


def run(elf: Path, timeout_s: float = TIMEOUT_S) -> StageResult:
    """Boot elf on an emulated Pi Zero and check that it prints HIL:DONE."""
    # TODO
    raise NotImplementedError("TODO: write the QEMU gate")
