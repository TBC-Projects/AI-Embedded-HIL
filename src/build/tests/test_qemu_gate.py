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


def test_endless_loop_still_running_passes(tmp_path):
    # Real firmware never returns from main. Booting and running without a
    # panic until the time limit counts as a pass.
    r = qemu_gate.run(elf(tmp_path, "hang"), timeout_s=1.5)
    assert r.ok, r.feedback
    assert "still running" in r.summary
    assert "stuck" in r.artifacts["console"]


def test_firmware_loop_with_expect_passes_as_soon_as_text_appears(tmp_path):
    program = elf(tmp_path, "firmware_loop")
    started = time.monotonic()
    r = qemu_gate.run(program, timeout_s=10, expect="UART ready")
    assert r.ok, r.feedback
    assert "printed 'UART ready'" in r.summary
    assert time.monotonic() - started < 3   # didn't wait for the 10 s limit


def test_firmware_loop_keeps_printing(tmp_path):
    r = qemu_gate.run(elf(tmp_path, "firmware_loop"), timeout_s=10, expect="tick")
    assert r.ok, r.feedback


def test_expected_text_missing_fails(tmp_path):
    r = qemu_gate.run(elf(tmp_path, "hang"), timeout_s=1.5, expect="UART ready")
    assert not r.ok
    assert r.blame == "code"
    assert "did not print 'UART ready'" in r.summary
    assert "stuck" in r.feedback          # the AI still sees what was printed


def test_never_boots(tmp_path):
    r = qemu_gate.run(elf(tmp_path, "silent"), timeout_s=1.5)
    assert not r.ok
    assert "never reached main" in r.summary
