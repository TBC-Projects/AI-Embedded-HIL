"""Tests for qemu_gate.py. Each test builds a tiny program from fixtures/ and boots it.
Skipped unless arm-none-eabi-gcc and qemu-system-arm are installed."""
import shutil
import time
import subprocess
from pathlib import Path

import pytest

import qemu_gate

FIX = Path(__file__).parent / "fixtures"
CC = "arm-none-eabi-gcc"
pytestmark = pytest.mark.skipif(
    shutil.which(CC) is None or shutil.which(qemu_gate.QEMU) is None,
    reason="needs arm-none-eabi-gcc and qemu-system-arm")


def elf(tmp_path: Path, name: str) -> Path:
    """Build a tiny fixture program straight with gcc (independent of build.py)."""
    out = tmp_path / f"{name}.elf"
    subprocess.run([CC, "-mcpu=arm1176jzf-s", "-marm", "-O2", "-ffreestanding",
                    "-nostdlib", "-I", str(FIX), "-T", str(FIX / "linker.ld"),
                    str(FIX / "start.S"), str(FIX / f"{name}.c"), "-o", str(out)],
                   check=True, capture_output=True)
    return out


def test_done_passes_quickly(tmp_path):
    program = elf(tmp_path, "done")
    started = time.monotonic()
    r = qemu_gate.run(program)
    assert r.ok, r.feedback
    assert "working" in r.artifacts["console"]
    assert time.monotonic() - started < 3   # stops at HIL:DONE, not at the timeout


def test_panic_fails_with_console(tmp_path):
    r = qemu_gate.run(elf(tmp_path, "panic"))
    assert not r.ok
    assert "hil_panic" in r.summary
    assert "bad timer" in r.feedback


def test_hang_times_out(tmp_path):
    r = qemu_gate.run(elf(tmp_path, "hang"), timeout_s=1.5)
    assert not r.ok
    assert "no HIL:DONE" in r.summary
    assert "stuck" in r.feedback


def test_never_boots(tmp_path):
    r = qemu_gate.run(elf(tmp_path, "silent"), timeout_s=1.5)
    assert not r.ok
    assert "never reached main" in r.summary
