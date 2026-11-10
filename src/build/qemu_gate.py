"""Step 6: QEMU gate. Boots kernel.elf on an emulated Pi Zero before we touch real hardware.

QEMU's "raspi0" machine emulates the same chip as the Pi Zero. We connect
its serial port to our stdin/stdout and watch for the markers that
target/hil.c prints (see common.py):

    console shows                         result
    -----------------------------------   -------------------------------
    HIL:DONE                              pass
    HIL:PANIC <reason>                    fail: the program gave up
    HIL:BOOT, but no DONE before timeout  fail: hang or infinite loop
    nothing at all                        fail: never reached main()
    QEMU exits on its own                 fail
    qemu-system-arm not installed         fail, blame=rig

QEMU doesn't model real timing, so timing checks belong to the FPGA trace
(runner.py), not here.

Install: brew install qemu  /  sudo apt install qemu-system-arm  (needs QEMU 6.2 or newer)

Deliverable D3. Run the tests with: python3 -m pytest tests/test_qemu_gate.py
"""
from __future__ import annotations

import selectors
import subprocess
import time
from pathlib import Path

from common import BLAME_CODE, BLAME_RIG, MARK_BOOT, StageResult, find_verdict, tail

STAGE = "qemu"
QEMU = "qemu-system-arm"
TIMEOUT_S = 5.0

QEMU_ARGS = [
    "-M", "raspi0",              # emulate a Raspberry Pi Zero
    "-display", "none",          # no window
    "-serial", "stdio",          # the Pi's UART0 becomes QEMU's stdin/stdout
    "-monitor", "none",
    "-d", "guest_errors,unimp",  # report bad register accesses on stderr
]


def run(elf: Path, timeout_s: float = TIMEOUT_S) -> StageResult:
    """Boot elf in QEMU and decide pass/fail from its console output."""
    try:
        qemu = subprocess.Popen([QEMU, *QEMU_ARGS, "-kernel", str(elf)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError:
        return StageResult(STAGE, False, f"{QEMU} is not installed",
                           feedback=f"{QEMU} is not installed on the build machine",
                           blame=BLAME_RIG)

    try:
        console, guest_errors, outcome = _watch(qemu, timeout_s)
    finally:
        # Always stop QEMU. After HIL:DONE the program reboots itself,
        # so QEMU would otherwise run forever.
        qemu.kill()
        qemu.wait()

    artifacts = {"console": console, "guest_errors": guest_errors}

    # TODO: turn the outcome into a StageResult.
    #   - outcome "done" -> passing StageResult, summary "booted and finished", with artifacts.
    #   - anything else  -> failing StageResult, blame=BLAME_CODE, with artifacts:
    #       summary  = _explain(outcome, console, timeout_s)
    #       feedback = f"QEMU test failed: {reason}.\nConsole:\n{tail(console, 20)}"
    #                  and, if guest_errors isn't blank, add
    #                  f"\nQEMU guest errors:\n{tail(guest_errors, 15)}"
    raise NotImplementedError("TODO: qemu_gate.run result")


def _watch(qemu: subprocess.Popen, timeout_s: float) -> tuple[str, str, str]:
    """Read QEMU's output until the program finishes, QEMU exits, or time runs out.

    Returns (console text, guest error text, outcome), where outcome is
    "done", "panic", "exited" or "timeout".
    """
    # A selector lets us wait on stdout and stderr at the same time without blocking.
    selector = selectors.DefaultSelector()
    selector.register(qemu.stdout, selectors.EVENT_READ, "console")
    selector.register(qemu.stderr, selectors.EVENT_READ, "errors")
    output = {"console": b"", "errors": b""}

    # TODO: loop until timeout_s has passed (use time.monotonic() for the deadline):
    #   1. for key, _ in selector.select(timeout=0.1):
    #          output[key.data] += key.fileobj.read1(4096)
    #   2. Decode the console so far (errors="replace") and call find_verdict() on it.
    #      If it returns "done" or "panic", that's the outcome: stop looping.
    #   3. If qemu.poll() is not None, QEMU has exited by itself: outcome "exited", stop.
    #   If the deadline passes first, the outcome is "timeout".
    # Important: stop as soon as you have a verdict. Don't wait out the timeout.
    outcome = "timeout"
    raise NotImplementedError("TODO: _watch loop")

    # The console has "\r\n" line endings; remove the "\r"s.
    console = output["console"].decode(errors="replace").replace("\r", "")
    return console, output["errors"].decode(errors="replace"), outcome


def _explain(outcome: str, console: str, timeout_s: float) -> str:
    """Turn a failed outcome into one sentence for the summary and the LLM.

        "panic"                      -> "the program called hil_panic"
        "exited"                     -> "QEMU exited unexpectedly"
        no MARK_BOOT in the console  -> "the program never reached main (no HIL:BOOT)"
        otherwise (a timeout)        -> f"no HIL:DONE after {timeout_s:g}s (hang or infinite loop)"
    """
    # TODO: return the right sentence. The tests check for these exact phrases.
    raise NotImplementedError("TODO: _explain")
