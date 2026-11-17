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
    HIL:BOOT             the program started (main is about to run)
    HIL:DONE             main returned (only small test programs ever do this)
    HIL:PANIC <reason>   the program hit an error and gave up

IMPORTANT: real firmware NEVER finishes. It is an endless loop (like a tiny
operating system), so it never prints HIL:DONE. The gate can't wait for an
ending; instead it runs the program for a while and checks it didn't crash.
(The marker strings are also in common.py as MARK_BOOT, MARK_DONE, MARK_PANIC.)

Install QEMU:
    Mac:    brew install qemu
    Ubuntu: sudo apt install qemu-system-arm
    Check:  qemu-system-arm --version   (needs 6.2 or newer)

TRY IT BY HAND first (after D2 works, or with any kernel.elf):
    qemu-system-arm -M raspi0 -kernel kernel.elf -display none -serial stdio -monitor none
You'll see HIL:BOOT and the program's output. QEMU KEEPS RUNNING (firmware loops
forever; a program that does return prints HIL:DONE and reboots). Press Ctrl+C
to stop it. Your code must stop it too.


WHAT TO BUILD
-------------
run(elf, timeout_s=5.0, expect=None) -> StageResult
    timeout_s  how long to let the program run
    expect     optional text the program must print, e.g. "tick" or "UART ready"

STEPS
    1. Start QEMU as a background process with subprocess.Popen, using:
           qemu-system-arm -M raspi0 -kernel <elf> -display none -serial stdio -monitor none
       If QEMU isn't installed, Popen raises FileNotFoundError: report blame="rig".
    2. Keep reading QEMU's output, adding it to a string.
       Stop early on HIL:PANIC, HIL:DONE, or the expect text; otherwise run for
       the full timeout_s seconds.
    3. ALWAYS stop QEMU at the end: proc.kill() then proc.wait().
       Use try/finally so this happens even if your code crashes.
    4. Decide the result from what was printed:

       what happened                                  result  summary contains
       HIL:PANIC                                      fail    "hil_panic"
       QEMU stopped by itself                         fail    "QEMU exited"
       no HIL:BOOT at all                             fail    "never reached main"
       HIL:DONE (main returned)                       pass    "finished"
       expect given and it appeared                   pass    "printed"
       expect given but it never appeared             fail    "did not print"
       no expect: booted, no panic, still running     pass    "still running"

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
A program that prints HIL:DONE or the expect text must pass in under 3 seconds,
so stop as soon as you see it instead of waiting for the timeout.
"""
from __future__ import annotations

import selectors
import subprocess
import time
from pathlib import Path
# Support both package imports from orchestration and the existing local CLI/tests.
if __package__:
    from .common import StageResult, tail
else:
    from common import StageResult, tail

# the emulator program; "-M raspi0" (below) makes it pretend to be a Raspberry Pi Zero
QEMU = "qemu-system-arm"
# How long to let the program run. Firmware loops forever, so a program that is
# still running (and hasn't panicked) after this long passes.
TIMEOUT_S = 5.0


def run(elf: Path, timeout_s: float = TIMEOUT_S, expect: str | None = None) -> StageResult:
    """Boot elf on an emulated Pi Zero and check that it runs without crashing.

    Firmware usually loops forever, so the program does NOT have to finish:
    it passes if it boots and is still running without a panic after timeout_s.
    If `expect` is given, the program must also print that text (and then
    passes right away).
    """

    # 1. Start QEMU as a separate process, pretending to be a Pi Zero.
    #    "-serial stdio" sends the Pi's console text to QEMU's stdout, so we can read it.
    # cmd looks like this:
    #   qemu-system-arm -M raspi0 -kernel kernel.elf -display none -serial stdio -monitor none
    cmd = [QEMU, "-M", "raspi0", "-kernel", str(elf),
           "-display", "none", "-serial", "stdio", "-monitor", "none"]
    # create pipes from that subprocess so that we can read the output from
    # from over here
    try:
        qemu = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        # QEMU isn't installed
        return StageResult("qemu", False, f"{QEMU} is not installed", blame="rig")

    # 2. Read what the program prints until we have an answer or time runs out.
    output = b""
    qemu_quit = False
    try:
        watcher = selectors.DefaultSelector()
        watcher.register(qemu.stdout, selectors.EVENT_READ)
        deadline = time.monotonic() + timeout_s

        while time.monotonic() < deadline:
            # check what is printed
            if watcher.select(timeout=0.1):
                output = output + qemu.stdout.read1(4096)

            text = output.decode(errors="replace")
            # stop early if we already know the answer
            if "HIL:PANIC" in text or "HIL:DONE" in text:
                break
            if expect and expect in text:
                break
            # check if qemu has quit on its own
            if qemu.poll() is not None:
                qemu_quit = True
                break
        # If the loop ran out of time, the program is still running. For firmware
        # that is normal: it is an endless loop and never finishes.
    finally:
        qemu.kill()
        qemu.wait()

    console = output.decode(errors="replace").replace("\r", "")
    artifacts = {"console": console}

    # 3. Decide the result. Failures first: a panic always fails.
    if "HIL:PANIC" in console:
        reason = "the program called hil_panic"
    elif "HIL:DONE" in console:
        # main returned; fine for small test programs (an expect check still applies)
        if expect and expect not in console:
            reason = f"the program finished without printing '{expect}'"
        else:
            return StageResult("qemu", True, "booted and finished (main returned)", artifacts=artifacts)
    elif qemu_quit:
        reason = "QEMU exited unexpectedly"
    elif "HIL:BOOT" not in console:
        reason = "the program never reached main (no HIL:BOOT)"
    elif expect and expect in console:
        return StageResult("qemu", True, f"booted and printed '{expect}'", artifacts=artifacts)
    elif expect:
        reason = f"the program did not print '{expect}' within {timeout_s:g}s"
    else:
        # Booted, no panic, still running when time ran out: normal for firmware.
        return StageResult("qemu", True,
                           f"booted and still running after {timeout_s:g}s without a panic",
                           artifacts=artifacts)

    # The AI gets the reason plus the last 50 lines the program printed.
    # we can make this smaller if we have a smaller context window, but we want to give
    # the LLM enough info to debug
    feedback = f"QEMU test failed: {reason}.\nConsole output:\n{tail(console, 50)}"
    return StageResult("qemu", False, reason, feedback=feedback, artifacts=artifacts)
