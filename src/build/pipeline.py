"""
DELIVERABLE D8: THE PIPELINE  (do this last: it connects D1-D4)
=============================

BACKGROUND
----------
Each stage you built does one job. The pipeline runs them in order on one AI reply:

    AI reply -> harness (D1) -> build (D2) -> QEMU gate (D3) -> runner (D4, only with real hardware)

If a stage fails, STOP: there's no point compiling code the harness rejected,
or flashing a program that crashed in QEMU. The failing stage's .feedback is
what gets sent back to the AI for its next try.


WHAT TO BUILD
-------------
1. run_attempt(reply, attempt_dir, runner=None) -> list of StageResult
       - Call harness.run, then build.run, then qemu_gate.run(attempt_dir / "kernel.elf").
       - If `runner` isn't None, also call runner.flash_and_run(attempt_dir / "kernel.bin").
       - Time each stage (time.monotonic() before and after) and store it in result.seconds.
       - Stop after the first result whose .ok is False.
       - Return the results of every stage that ran.

2. A command-line program, so anyone can try it (argparse is good for this):
       python3 pipeline.py examples/blink_reply.txt
       python3 pipeline.py examples/blink_reply.txt --pi /dev/tty.usbserial-XXXX --fpga /dev/tty.usbserial-YYYY
   Save the attempt to jobs/demo/attempt-1. Print one line per stage, for example:
       [PASS] harness   0.01s  accepted 1 file(s)
       [PASS] build     0.31s  kernel.bin 1148 B
       [FAIL] qemu      5.02s  no HIL:DONE after 5s (hang or infinite loop)
   and, after a failure, print the feedback the AI would get.


HOW YOU KNOW YOU'RE DONE
------------------------
    python3 pipeline.py examples/blink_reply.txt           -> every stage passes
    python3 pipeline.py examples/buggy_reply.txt           -> the harness rejects it
    python3 pipeline.py examples/compile_error_reply.txt   -> the build fails with gcc's error
    python3 pipeline.py examples/hang_reply.txt            -> QEMU reports a hang
"""
from __future__ import annotations

from pathlib import Path

import build
import harness
import qemu_gate
from common import StageResult


def run_attempt(reply: str, attempt_dir: Path, runner=None) -> list[StageResult]:
    """Run the stages in order on one AI reply. Stop at the first failure."""
    # TODO
    raise NotImplementedError("TODO: write the pipeline")


if __name__ == "__main__":
    # TODO: the command-line program
    raise NotImplementedError("TODO: write the command-line program")
