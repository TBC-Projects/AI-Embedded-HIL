"""Tests for compile.py. Build tests are skipped without arm-none-eabi-gcc."""
import shutil
from pathlib import Path

import pytest

import compile as compile_tool

SRC = Path(__file__).resolve().parents[2]           # .../src
SUPPORT = SRC / "build" / "target"                  # the fixed support layer
EXAMPLE = SRC / "build" / "examples" / "blink" / "main.c"
needs_gcc = pytest.mark.skipif(shutil.which(compile_tool.CC) is None,
                               reason="arm-none-eabi-gcc not installed")


def make_workspace(tmp_path: Path) -> Path:
    for name in ("start.S", "linker.ld", "hil.c", "hil.h"):
        shutil.copy(SUPPORT / name, tmp_path)
    (tmp_path / "src").mkdir()
    shutil.copy(EXAMPLE, tmp_path / "src" / "main.c")
    return tmp_path


@needs_gcc
def test_known_good_builds(tmp_path):
    ws = make_workspace(tmp_path)
    r = compile_tool.compile_firmware(ws)
    assert r.ok, r.diagnostics
    assert r.artifact_id and r.artifact_id.startswith("kernel-")
    assert r.size > 0
    assert (ws / "kernel.elf").is_file()
    assert (ws / "kernel.bin").is_file()


@needs_gcc
def test_broken_source_reports_compile_error(tmp_path):
    ws = make_workspace(tmp_path)
    (ws / "src" / "main.c").write_text("int main(void) { return 0 }\n")
    r = compile_tool.compile_firmware(ws)
    assert not r.ok and r.status == "compile_error"
    assert "error:" in r.diagnostics
    assert "src/main.c" in r.diagnostics       # the agent must see the file:line
    assert not (ws / "kernel.bin").exists()    # no stale image left behind


def test_missing_toolchain_is_reported(tmp_path):
    ws = make_workspace(tmp_path)
    r = compile_tool.compile_firmware(ws, cc="definitely-not-a-compiler")
    assert not r.ok and r.status == "toolchain_missing"


def test_no_sources_is_reported(tmp_path):
    shutil.copy(SUPPORT / "linker.ld", tmp_path)
    r = compile_tool.compile_firmware(tmp_path)
    assert not r.ok and r.status == "no_sources"
