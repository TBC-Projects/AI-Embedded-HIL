"""Runs one attempt through every stage, in order:

    LLM reply -> harness -> build -> QEMU gate -> runner (only if a Pi is connected)

It stops at the first stage that fails. The orchestrator then reads that
result: blame=code means send .feedback to the LLM for the next attempt;
blame=rig means retry the same code without the LLM.

Usage (from src/build/):
    python3 pipeline.py examples/blink_reply.txt             # no hardware
    python3 pipeline.py examples/blink_reply.txt --pi /dev/tty.usbserial-0001 --fpga /dev/tty.usbserial-XXXX
"""
from __future__ import annotations

import time
from pathlib import Path

import build
import harness
import qemu_gate
from common import StageResult


def run_attempt(reply: str, attempt_dir: Path, runner=None) -> list[StageResult]:
    """Run every stage on one LLM reply.

    reply        the LLM's raw text
    attempt_dir  folder to build in; it is wiped first
    runner       a runner.Runner to also test on real hardware, or None to stop after QEMU

    Returns the result of each stage that ran. If anything failed, the failure
    is the last item.
    """
    stages = [
        lambda: harness.run(reply, attempt_dir),
        lambda: build.run(attempt_dir),
        lambda: qemu_gate.run(attempt_dir / "kernel.elf"),
    ]
    if runner is not None:
        stages.append(lambda: runner.flash_and_run(attempt_dir / "kernel.bin"))
    # TODO (D7): add the analyzer here. It checks the runner's artifacts["trace"].

    results = []
    # TODO (D8): run each stage in order.
    #   - Time it: started = time.monotonic() before, then set result.seconds afterwards.
    #   - Add the result to `results`.
    #   - If the result isn't ok, stop: later stages need the earlier ones to have passed.
    raise NotImplementedError("TODO: run_attempt loop")
    return results


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Run one LLM reply through the HIL pipeline")
    parser.add_argument("reply", help="text file containing an LLM reply")
    parser.add_argument("--out", default="jobs/demo/attempt-1", help="attempt folder")
    parser.add_argument("--pi", help="Pi serial port; leave out to skip real hardware")
    parser.add_argument("--fpga", help="Basys 3 serial port")
    args = parser.parse_args()

    runner = None
    if args.pi:
        from runner import Runner  # imported here so pyserial is only needed with hardware
        runner = Runner(args.pi, args.fpga)

    reply = Path(args.reply).read_text()
    for result in run_attempt(reply, Path(args.out), runner):
        status = "PASS" if result.ok else "FAIL"
        print(f"[{status}] {result.stage:8s} {result.seconds:5.2f}s  {result.summary}")
        if not result.ok:
            print(f"\n--- feedback for the LLM (blame={result.blame}) ---\n{result.feedback}")


if __name__ == "__main__":
    main()
