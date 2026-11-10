"""Shared pieces used by every pipeline stage.

Every stage (harness, build, qemu_gate, runner) returns a StageResult.
The pipeline only looks at:
    .ok        -> keep going, or stop here?
    .blame     -> after a failure, ask the LLM again, or just retry the rig?
    .feedback  -> the text we send back to the LLM
Keeping this contract small means anyone can rewrite one stage without
touching the others.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# --- Who is responsible for a failure --------------------------------------
BLAME_CODE = "code"  # the generated code is wrong: send feedback to the LLM, try again
BLAME_RIG = "rig"    # a tool or the hardware misbehaved: retry without the LLM

# --- Console markers --------------------------------------------------------
# target/hil.c prints these on the Pi's serial console. The QEMU gate and the
# runner both watch for them to decide whether a program passed.
MARK_BOOT = "HIL:BOOT"    # printed before main() runs
MARK_DONE = "HIL:DONE"    # printed after main() returns
MARK_PANIC = "HIL:PANIC"  # printed by hil_panic("reason")


@dataclass
class StageResult:
    """The outcome of one pipeline stage.

    stage      which stage produced this: "harness", "build", "qemu" or "runner"
    ok         True if the stage passed and the pipeline may continue
    summary    one human-readable line for logs and the dashboard
    feedback   on failure, a short explanation written for the LLM
    blame      BLAME_CODE or BLAME_RIG; only meaningful when ok is False
    artifacts  anything later stages or the UI need (file paths, console text, trace, ...)
    seconds    how long the stage took; filled in by pipeline.py
    """
    stage: str
    ok: bool
    summary: str
    feedback: str = ""
    blame: str = BLAME_CODE
    artifacts: dict = field(default_factory=dict)
    seconds: float = 0.0


def find_verdict(console: str) -> str | None:
    """Look for an end marker in console text.

    Returns "panic", "done", or None if the program hasn't finished yet.
    Panic is checked first: a program that panics never prints DONE.
    """
    if MARK_PANIC in console:
        return "panic"
    if MARK_DONE in console:
        return "done"
    return None


def tail(text: str, max_lines: int = 40, max_chars: int = 2000) -> str:
    """Return only the end of a long log.

    Compiler and console output can run to thousands of lines. The useful part
    is usually at the end, and the LLM's context is limited, so we keep the tail.
    """
    last_lines = text.strip().splitlines()[-max_lines:]
    return "\n".join(last_lines)[-max_chars:]
