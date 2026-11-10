"""Step 5: Build. Cross-compiles one attempt folder for the Raspberry Pi Zero.

Input: an attempt folder (normally made by harness.py)
    attempt/
        linker.ld          memory layout (required)
        start.S, hil.c     fixed support code: every *.S and *.c at the top level
        hil.h
        src/*.c            the LLM's code

Output, written into the same folder:
    kernel.elf   the program with debug info; QEMU boots this
    kernel.bin   the raw bytes that get flashed to the real Pi
    build.log    the exact gcc command and everything gcc printed

Failures:
    compile error              blame=code  feedback = end of gcc's errors
    kernel.bin over 1 MB       blame=code
    no src/*.c files           blame=code
    linker.ld missing          blame=rig   (a harness bug, not the LLM's fault)
    toolchain missing/broken   blame=rig

Deliverable D2. Run the tests with: python3 -m pytest tests/test_build.py
"""
from __future__ import annotations

import subprocess
import zlib
from pathlib import Path

from common import BLAME_CODE, BLAME_RIG, StageResult, tail

STAGE = "build"

# Toolchain. Mac: brew install --cask gcc-arm-embedded
#            Ubuntu: sudo apt install gcc-arm-none-eabi
CC = "arm-none-eabi-gcc"
OBJCOPY = "arm-none-eabi-objcopy"

CFLAGS = [
    "-mcpu=arm1176jzf-s", "-marm",                 # Pi Zero CPU (BCM2835, ARMv6), 32-bit ARM code
    "-O2", "-g",                                   # optimise, but keep debug info in kernel.elf
    "-ffreestanding", "-nostdlib", "-fno-builtin",  # bare metal: no OS and no C library
    "-Wall", "-Wextra",
    "-Werror=implicit-function-declaration",       # calling an undeclared function is an error
]

MAX_BIN_BYTES = 1 << 20  # 1 MB. Real programs are a few KB; anything bigger is a mistake.
TOOL_TIMEOUT_S = 60


def run(attempt_dir: Path) -> StageResult:
    """Compile attempt_dir into kernel.elf and kernel.bin."""
    # TODO 0: Check the input.
    #   - linker.ld missing          -> _fail(..., blame=BLAME_RIG)
    #   - no LLM sources (src/*.c)   -> _fail("no src/*.c files",
    #                                         "No C source files were provided under src/.")
    #   Use _find_sources(attempt_dir) to get (fixed_sources, llm_sources).

    # TODO 1: Compile and link everything into kernel.elf.
    #   Command: [CC, *CFLAGS, "-I.", "-T", "linker.ld", <all sources>, "-o", "kernel.elf", "-lgcc"]
    #   - Run it with _run_tool(cmd, attempt_dir). If that returns None -> return _tool_missing(CC)
    #   - Write build.log: the command (joined with spaces), a blank line, then stdout + stderr.
    #   - Non-zero return code -> _fail("compile failed",
    #       "The code did not compile. Compiler output:\n" + tail(<gcc stderr>))

    # TODO 2: Convert the ELF into raw bytes with
    #   [OBJCOPY, "-O", "binary", "kernel.elf", "kernel.bin"]
    #   - Tool missing -> _tool_missing(OBJCOPY). Non-zero return code -> blame=BLAME_RIG.

    # TODO 3: Check the size and compute the checksum.
    #   - Read kernel.bin. Larger than MAX_BIN_BYTES -> _fail(f"binary too large ({size} bytes)", ...)
    #     The feedback should give the size, the limit, and suggest removing large static arrays.
    #   - crc = zlib.crc32(binary)
    #   - Return a passing StageResult with summary f"kernel.bin {size} B, crc32 {crc:08x}"
    #     and artifacts: "elf", "bin" (paths as str), "length", "crc32",
    #     "warnings" (tail of gcc's stderr, or "" if there were none).
    raise NotImplementedError("TODO: build.run")


def _find_sources(attempt_dir: Path) -> tuple[list[str], list[str]]:
    """Return (fixed support files, LLM files), as paths relative to attempt_dir.

    fixed: every *.S then every *.c directly in attempt_dir, sorted, e.g. ["start.S", "hil.c"]
    llm:   every src/*.c, sorted, e.g. ["src/main.c"]
    """
    # TODO: use attempt_dir.glob(...). Return names relative to attempt_dir, because
    #       gcc runs inside attempt_dir.
    fixed_sources = sorted(
        path.name
        for pattern in ("*.S", "*.c")
        for path in attempt_dir.glob(pattern)
        if path.is_file()
    )

    llm_sources = sorted(
        path.relative_to(attempt_dir).as_posix()
        for path in (attempt_dir / "src").glob("*.c")
        if path.is_file()
    )

    return fixed_sources, llm_sources


def _run_tool(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess | None:
    """Run a toolchain command in cwd. Returns None if the tool isn't installed."""
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                              timeout=TOOL_TIMEOUT_S)
    except FileNotFoundError:
        return None


def _tool_missing(tool: str) -> StageResult:
    return _fail(f"{tool} is not installed", f"{tool} is not installed on the build machine",
                 blame=BLAME_RIG)


def _fail(summary: str, feedback: str, blame: str = BLAME_CODE) -> StageResult:
    return StageResult(STAGE, False, summary, feedback=feedback, blame=blame)
