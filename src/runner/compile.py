"""
WORKSTREAM 2 — THE COMPILE TOOL
===============================

BACKGROUND: WHY A CROSS-COMPILER
--------------------------------
The laptop runs x86-64 Windows/macOS/Linux. The Raspberry Pi Zero W runs a
BCM2835: a 32-bit ARM1176JZF-S core (ARMv6) with no operating system. Machine
code for one cannot execute on the other, and a host compiler would also link
against the host C library and emit a program that expects an OS to load it.

A CROSS-COMPILER runs on the laptop and produces code for the Pi. Ours is
`arm-none-eabi-gcc`:

    arm    target instruction set
    none   no operating system (bare metal)
    eabi   ARM Embedded ABI: calling convention, struct layout, byte order
    gcc    the driver program

The driver does not compile by itself: it runs `cc1` (C front end), `as`
(assembler) and `collect2`/`ld` (linker), all built for this target. With
`-nostdlib` it skips the C library and the default startup files, but `-lgcc`
still links libgcc, which supplies helpers such as `__aeabi_uidiv` — the
ARM1176 has no hardware divide instruction.

INSTALL AND VERIFY
------------------
    macOS    brew install --cask gcc-arm-embedded
    Ubuntu   sudo apt install gcc-arm-none-eabi
    Windows  winget install --id Arm.GnuArmEmbeddedToolchain -e

    arm-none-eabi-gcc --version                  # 14.2.1 works
    arm-none-eabi-gcc -dumpmachine               # arm-none-eabi
    arm-none-eabi-gcc -print-libgcc-file-name    # must print a real path

PowerShell note: quote the argument (`'-print-file-name=libgcc.a'`). Unquoted,
PowerShell rewrites it and gcc prints a meaningless name. If
`-print-libgcc-file-name` returns a path that exists, the toolchain is complete.

WHERE THIS TOOL SITS
--------------------
    AI reply -> harness (D1) -> [compile tool] -> QEMU gate (D3) -> runner (D4)
                                  kernel.elf      emulated Pi     real Pi + FPGA

The harness turns one AI reply into a workspace:

    workspace/
        start.S  hil.c  hil.h  linker.ld    fixed support layer (src/build/target/)
        src/*.c                             the AI's code

WHAT HAPPENS INSIDE compile_firmware()
--------------------------------------
 1. Check that linker.ld exists and src/*.c is non-empty. Return a status; a
    missing file is a fact about the workspace, not an exception.
 2. Delete old kernel.elf / kernel.bin. A failed build must never leave the
    previous image where the uploader can still find it.
 3. Compile and link in one gcc invocation — the repository's existing command:

        arm-none-eabi-gcc
            -mcpu=arm1176jzf-s -marm -O2 -g
            -ffreestanding -nostdlib -fno-builtin -Wall -Wextra
            -Werror=implicit-function-declaration
            -I. -T linker.ld start.S hil.c src/main.c
            -o kernel.elf -lgcc

    gcc compiles each .c/.S to a temporary object file and links them with
    linker.ld. To watch the pieces separately, add `-c` per file and link the
    .o files yourself (see HOW TO RUN IT below).
 4. Save the command and the full compiler output to build.log.
 5. Non-zero exit -> compile_error, or link_error when the output contains
    "undefined reference". diagnostics is the tail of the output.
 6. `objcopy -O binary kernel.elf kernel.bin` strips the ELF container so the
    uploader sends exactly the bytes that belong at address 0x8000.
 7. Reject images over max_bytes (1 MB by default), compute crc32, return.

FLAG BY FLAG
------------
    -mcpu=arm1176jzf-s -marm   the Pi Zero's CPU, ARM state (not Thumb)
    -O2 -g                     optimise, keep symbols for debugging and QEMU
    -ffreestanding -nostdlib -fno-builtin    no OS, no C library
    -Wall -Wextra              warnings are part of the feedback to the model
    -Werror=implicit-function-declaration    a missing #include is an error,
                               not a silent int return
    -I.                        find hil.h in the workspace
    -T linker.ld               memory layout: entry _start, everything at 0x8000
    -lgcc                      software divide and other ARM helpers

WHERE THE IMAGE APPEARS
-----------------------
All three files are written into the workspace root:

    kernel.elf   has symbols; the QEMU gate boots this
    kernel.bin   the flat image the UART bootloader receives
    build.log    the command line plus everything gcc printed

Check it by hand:

    arm-none-eabi-readelf -h kernel.elf     # Entry point address: 0x8000
    arm-none-eabi-nm kernel.elf | grep _start
    ls -l kernel.bin

WHAT IT RETURNS
---------------
A CompileResult (dataclass, below). Success carries artifact_id
"kernel-<crc32>" — the same checksum the HIL1 upload header carries — plus the
elf/binary paths, size and duration. Failure carries status and diagnostics.

HOW TO TELL SUCCESS FROM FAILURE
--------------------------------
    exit 0 and kernel.elf + kernel.bin exist   -> ok
    exit != 0 with "error:" lines              -> compile_error
    exit != 0 with "undefined reference to"    -> link_error
    FileNotFoundError                          -> toolchain_missing
    exit 0 but no kernel.bin                   -> objcopy_failed
    an old kernel.bin survives a failure       -> step 2 was skipped

HOW TO RUN IT
-------------
    cd src/runner
    python -B -m pytest tests -v -p no:cacheprovider     # 4 passed
    python compile.py <workspace> --json                 # one build

The four-step version by hand, in a workspace (same flags as above):

    arm-none-eabi-gcc <flags> -c start.S -o start.o
    arm-none-eabi-gcc <flags> -c hil.c   -o hil.o
    arm-none-eabi-gcc <flags> -c src/main.c -o main.o
    arm-none-eabi-gcc <flags> -T linker.ld start.o hil.o main.o -o kernel.elf -lgcc
    arm-none-eabi-objcopy -O binary kernel.elf kernel.bin

    main.o is a REL (relocatable) ARM file with entry 0x0; kernel.elf is EXEC
    with entry 0x8000; kernel.bin is about 1.2 KB and starts with ARM
    instructions, not with the ELF magic 7f 45 4c 46.

HOW YOU KNOW YOU'RE DONE
------------------------
    tests/test_compile.py .... 4 passed
    a deliberately broken source returns compile_error with "src/main.c:4:24"
    in diagnostics, and kernel.bin is gone afterwards.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import zlib
from dataclasses import asdict, dataclass, field
from pathlib import Path

CC = os.environ.get("ARM_CC", "arm-none-eabi-gcc")
OBJCOPY = os.environ.get("ARM_OBJCOPY", "arm-none-eabi-objcopy")

# Must match src/build/build.py: the Pi Zero W is a BCM2835 with an ARM1176JZF-S.
CFLAGS = [
    "-mcpu=arm1176jzf-s", "-marm",
    "-O2", "-g",
    "-ffreestanding", "-nostdlib", "-fno-builtin",
    "-Wall", "-Wextra",
    "-Werror=implicit-function-declaration",
]

MAX_BIN_BYTES = 1 << 20
TOOL_TIMEOUT_S = 60
DIAG_LINES = 40
DIAG_CHARS = 4000
ARTIFACTS = ("kernel.elf", "kernel.bin")


@dataclass
class CompileResult:
    """What one build produced, in a form the agent loop can act on."""

    ok: bool
    status: str
    summary: str
    diagnostics: str = ""
    artifact_id: str | None = None
    elf: str | None = None
    binary: str | None = None
    size: int = 0
    crc32: str | None = None
    duration_s: float = 0.0
    command: list[str] = field(default_factory=list)


def compile_firmware(workspace: str | Path, *, cc: str | None = None,
                     timeout_s: float = TOOL_TIMEOUT_S,
                     max_bytes: int = MAX_BIN_BYTES) -> CompileResult:
    """Build one workspace and describe the outcome. Never raises for build errors."""
    ws = Path(workspace).resolve()
    started = time.monotonic()
    compiler = cc or CC

    def done(**kw) -> CompileResult:
        kw.setdefault("duration_s", round(time.monotonic() - started, 3))
        return CompileResult(**kw)

    if not (ws / "linker.ld").is_file():
        return done(ok=False, status="missing_linker_script",
                    summary="linker.ld is missing",
                    diagnostics=f"{ws / 'linker.ld'} does not exist; "
                                "nothing can be linked without the memory layout.",
                    command=[])

    fixed, generated = _find_sources(ws)
    if not generated:
        return done(ok=False, status="no_sources",
                    summary="no src/*.c files",
                    diagnostics="No C source files were provided under src/.",
                    command=[])

    # A failed build must not leave the previous image behind: the uploader
    # would happily flash stale code.
    for name in ARTIFACTS:
        stale = ws / name
        if stale.exists():
            stale.unlink()

    command = [compiler, *CFLAGS, "-I.", "-T", "linker.ld",
               *fixed, *generated, "-o", "kernel.elf", "-lgcc"]

    try:
        built = subprocess.run(command, cwd=ws, capture_output=True, text=True,
                               timeout=timeout_s)
    except FileNotFoundError:
        return done(ok=False, status="toolchain_missing",
                    summary=f"{compiler} is not installed",
                    diagnostics=_install_hint(compiler),
                    command=command)
    except subprocess.TimeoutExpired:
        return done(ok=False, status="timeout",
                    summary=f"compiler did not finish in {timeout_s:g}s",
                    diagnostics="The build timed out. Look for an include cycle "
                                "or a huge source file.",
                    command=command)

    output = (built.stdout + built.stderr).strip()
    (ws / "build.log").write_text(f"$ {' '.join(command)}\n\n{output}\n", encoding="utf-8")

    if built.returncode != 0:
        status = "link_error" if "undefined reference" in output else "compile_error"
        return done(ok=False, status=status,
                    summary="link failed" if status == "link_error" else "compile failed",
                    diagnostics=_trim(output), command=command)

    try:
        copied = subprocess.run([OBJCOPY, "-O", "binary", "kernel.elf", "kernel.bin"],
                                cwd=ws, capture_output=True, text=True, timeout=timeout_s)
    except FileNotFoundError:
        return done(ok=False, status="toolchain_missing",
                    summary=f"{OBJCOPY} is not installed",
                    diagnostics=_install_hint(OBJCOPY), command=command)
    if copied.returncode != 0:
        return done(ok=False, status="objcopy_failed", summary="objcopy failed",
                    diagnostics=_trim(copied.stdout + copied.stderr), command=command)

    image = ws / "kernel.bin"
    data = image.read_bytes()
    if len(data) > max_bytes:
        return done(ok=False, status="too_large",
                    summary=f"binary too large ({len(data)} bytes)",
                    diagnostics=f"kernel.bin is {len(data)} bytes; the limit is "
                                f"{max_bytes} bytes. Remove large static arrays.",
                    command=command)

    crc = zlib.crc32(data) & 0xFFFFFFFF
    return done(ok=True, status="ok",
                summary=f"kernel.bin {len(data)} B, crc32 {crc:08x}",
                diagnostics=_trim(built.stderr),
                artifact_id=f"kernel-{crc:08x}",
                elf=str(ws / "kernel.elf"), binary=str(image),
                size=len(data), crc32=f"{crc:08x}", command=command)


def _find_sources(ws: Path) -> tuple[list[str], list[str]]:
    """Return (fixed support files, generated files), relative to the workspace.

    Fixed files are every *.S then every *.c at the workspace root; generated
    files are src/*.c. Both are sorted so the command line is reproducible.
    """
    fixed = [p.name for p in sorted(ws.glob("*.S"))]
    fixed += [p.name for p in sorted(ws.glob("*.c"))]
    src = ws / "src"
    generated = [p.relative_to(ws).as_posix() for p in sorted(src.glob("*.c"))]
    return fixed, generated


def _trim(text: str, max_lines: int = DIAG_LINES, max_chars: int = DIAG_CHARS) -> str:
    """Keep the tail of a compiler log: the useful part is at the end."""
    text = text.strip()
    if not text:
        return ""
    lines = text.splitlines()[-max_lines:]
    return "\n".join(lines)[-max_chars:]


def _install_hint(tool: str) -> str:
    return (f"{tool} was not found on PATH.\n"
            "macOS:   brew install --cask gcc-arm-embedded\n"
            "Ubuntu:  sudo apt install gcc-arm-none-eabi\n"
            "Windows: winget install Arm.GnuArmEmbeddedToolchain "
            "(then reopen the terminal)\n"
            "Check with: arm-none-eabi-gcc --version")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile one firmware workspace")
    parser.add_argument("workspace", help="folder with linker.ld, start.S, src/*.c")
    parser.add_argument("--cc", default=CC, help=f"compiler (default: {CC})")
    parser.add_argument("--json", action="store_true", help="print the full result as JSON")
    args = parser.parse_args()

    result = compile_firmware(args.workspace, cc=args.cc)
    if args.json:
        print(json.dumps(asdict(result), indent=2))
    else:
        print(f"[{'PASS' if result.ok else 'FAIL'}] {result.status}: {result.summary}")
        if result.artifact_id:
            print(f"artifact: {result.artifact_id} ({result.size} bytes)")
        if result.diagnostics:
            print(f"--- diagnostics ---\n{result.diagnostics}")
    sys.exit(0 if result.ok else 1)


if __name__ == "__main__":
    main()
