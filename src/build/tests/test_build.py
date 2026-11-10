"""Tests for build.py. Most need arm-none-eabi-gcc and are skipped without it."""
import shutil
import zlib
from pathlib import Path

import pytest

import build

FIXTURE = Path(__file__).parent / "fixtures" / "minimal_attempt"
needs_gcc = pytest.mark.skipif(shutil.which(build.CC) is None,
                               reason="arm-none-eabi-gcc not installed")


@pytest.fixture
def attempt(tmp_path):
    dst = tmp_path / "attempt"
    shutil.copytree(FIXTURE, dst)
    return dst


@needs_gcc
def test_good_source_builds_elf_and_bin(attempt):
    r = build.run(attempt)
    assert r.ok, r.feedback
    data = (attempt / "kernel.bin").read_bytes()
    assert r.artifacts["length"] == len(data) > 0
    assert r.artifacts["crc32"] == zlib.crc32(data) & 0xFFFFFFFF
    assert (attempt / "kernel.elf").exists()
    assert (attempt / "build.log").exists()


@needs_gcc
def test_compile_error_is_returned_as_feedback(attempt):
    (attempt / "src" / "main.c").write_text("int main(void) { return 0 }\n")
    r = build.run(attempt)
    assert not r.ok
    assert r.blame == "code"
    assert "expected ';'" in r.feedback
    assert "src/main.c" in r.feedback


@needs_gcc
def test_oversized_binary_is_rejected(attempt, monkeypatch):
    monkeypatch.setattr(build, "MAX_BIN_BYTES", 8)
    r = build.run(attempt)
    assert not r.ok and "too large" in r.summary


def test_missing_linker_script_is_a_rig_fault(attempt):
    (attempt / "linker.ld").unlink()
    r = build.run(attempt)
    assert not r.ok and r.blame == "rig"


def test_no_generated_sources(attempt):
    (attempt / "src" / "main.c").unlink()
    r = build.run(attempt)
    assert not r.ok and "src/" in r.feedback
