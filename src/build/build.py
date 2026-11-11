"""
DELIVERABLE D2: THE BUILD STAGE
===============================

BACKGROUND (read this first)
----------------------------
Your laptop has an Intel/AMD or Apple chip. The Raspberry Pi Zero has an ARM
chip, which understands completely different machine instructions. So we can't
use the normal `gcc` on your laptop: we need a CROSS-COMPILER, a compiler that
runs on your laptop but produces code for the Pi. Ours is called
`arm-none-eabi-gcc`:
    arm   = for ARM chips
    none  = no operating system (bare metal)
    eabi  = the standard way ARM programs are laid out

The compiler produces two kinds of output:
    kernel.elf  the program PLUS extra info (function names, debug data).
                The emulator in the next stage (QEMU) loads this file.
    kernel.bin  ONLY the raw bytes of the program, nothing else. This is what
                gets sent to the real Pi over a cable.

Install the cross-compiler:
    Mac:    brew install --cask gcc-arm-embedded
    Ubuntu: sudo apt install gcc-arm-none-eabi
    Check:  arm-none-eabi-gcc --version

Before you write any Python, TRY IT BY HAND (this teaches you the whole task):
    cd src/build
    python3 -c "import shutil; shutil.copytree('tests/fixtures/minimal_attempt', '/tmp/try')"
    cd /tmp/try
    arm-none-eabi-gcc -mcpu=arm1176jzf-s -marm -O2 -g -ffreestanding -nostdlib \\
        -fno-builtin -Wall -Wextra -I. -T linker.ld start.S src/main.c -o kernel.elf -lgcc
    arm-none-eabi-objcopy -O binary kernel.elf kernel.bin
    ls -l kernel.*
Now break src/main.c on purpose (delete a ';') and run gcc again. That error
message is exactly what we want to send back to the AI.

What the flags mean (you don't need to memorise them):
    -mcpu=arm1176jzf-s -marm   build for the Pi Zero's exact CPU
    -O2 -g                     optimise, but keep debug info
    -ffreestanding -nostdlib -fno-builtin   no operating system, no C library
    -Wall -Wextra              show lots of warnings
    -I.                        look for #include files in this folder
    -T linker.ld               use our memory layout file
    -lgcc                      a small helper library gcc needs


WHAT TO BUILD
-------------
run(attempt_dir) does in Python what you just did by hand:

INPUT: a folder made by the harness (D1):
    attempt_dir/
        linker.ld         must exist
        start.S, hil.c    compile every .S and .c file in this folder...
        hil.h
        src/main.c ...    ...plus every .c file in src/ (there must be at least one)

STEPS
    1. Check that linker.ld exists and there's at least one src/*.c file.
    2. Run arm-none-eabi-gcc (flags above) INSIDE attempt_dir to make kernel.elf.
    3. Save the command you ran and everything gcc printed to attempt_dir/build.log.
    4. If gcc failed, stop and report the error.
    5. Run arm-none-eabi-objcopy to make kernel.bin.
    6. Check kernel.bin isn't bigger than MAX_BIN_BYTES (1 MB).
    7. Compute the CRC32 of kernel.bin: zlib.crc32(data). A CRC is a "fingerprint"
       number, so the Pi can check that every byte arrived correctly.


WHAT TO RETURN (see common.py for StageResult)
----------------------------------------------
Success:
    StageResult("build", True, "kernel.bin 1148 B",
                artifacts={"elf": <path>, "bin": <path>, "length": <size>, "crc32": <crc>})

Failures. "blame" says WHO caused the problem:
    "code" = the AI's code is wrong -> the AI gets the feedback and tries again
    "rig"  = our setup is broken    -> retry WITHOUT asking the AI

    situation                    blame    what to say
    gcc reports an error         "code"   the LAST ~40 lines of gcc's error output
                                          (common.tail() does this for you)
    kernel.bin over 1 MB         "code"   summary must contain "too large"
    no src/*.c files             "code"   feedback must mention "src/"
    linker.ld missing            "rig"    (our harness's fault, not the AI's)
    gcc isn't installed          "rig"


USEFUL PYTHON TOOLS
-------------------
    subprocess.run(cmd_list, cwd=folder, capture_output=True, text=True)
        runs a command. Then use .returncode (0 = success), .stdout and .stderr.
        If the program isn't installed, it raises FileNotFoundError.
    Path.glob("*.c")   list matching files in a folder
    zlib.crc32(bytes)  the checksum


HOW YOU KNOW YOU'RE DONE
------------------------
From src/build/, run:   python3 -m pytest tests/test_build.py -v
(Tests that need gcc are skipped if it isn't installed: install it first!)
Note: the tests change MAX_BIN_BYTES while running, so use the variable inside
run(). Don't copy its value somewhere else when the file loads.
"""
from __future__ import annotations

from ast import main
from pathlib import Path
import subprocess
import zlib
from common import StageResult, tail

CC = "arm-none-eabi-gcc"            # the cross-compiler
OBJCOPY = "arm-none-eabi-objcopy"   # turns kernel.elf into kernel.bin
MAX_BIN_BYTES = 1 << 20             # 1 MB
# everything for the arm compiler
CFLAGS = ["-mcpu=arm1176jzf-s", "-marm", "-O2", "-g",
          "-ffreestanding", "-nostdlib", "-fno-builtin", "-Wall", "-Wextra"]

def run(attempt_dir: Path) -> StageResult:
    """Compile attempt_dir into kernel.elf and kernel.bin."""
    # TODO
    # 1. Check the input folder.
    # we need the linker to exist and at least one source file to compile
    # if it doesn't exist then we need to blame the harness 
    if not (attempt_dir / "linker.ld").exists():
        return StageResult("build", False, "linker.ld missing", blame="rig")

    # gets all the support files ending in .S or .c
    support = []
    for path in attempt_dir.glob("*.S"):
        support.append(path.name)
    for path in attempt_dir.glob("*.c"):
        support.append(path.name)
    support.sort()

    # gets all the LLM generated .c files in src/
    llm_code = []
    for path in attempt_dir.glob("src/*.c"):
        llm_code.append("src/" + path.name)
    llm_code.sort()    
    if not llm_code:
        return StageResult("build", False, "no src/*.c files",
                           feedback="No C source files were provided under src/.")

    # 2. Compile everything into kernel.elf.
    cmd = [CC, *CFLAGS, "-I.", "-T", "linker.ld", *support, *llm_code, "-o", "kernel.elf", "-lgcc"]
    try:
        gcc = subprocess.run(cmd, cwd=attempt_dir, capture_output=True, text=True)
    except FileNotFoundError:
        return StageResult("build", False, f"{CC} is not installed", blame="rig")

    # this step is trying to save a log of all the commands that we ran 
    # and the output of the compiler to a file called build.log
    # eg. arm-none-eabi-gcc -mcpu=arm1176jzf-s -marm -O2 -g ... -I. -T linker.ld hil.c start.S src/main.c -o kernel.elf -lgcc
    # src/main.c: In function 'main':
    # src/main.c:4:22: error: expected ';' before 'return'
    #     4 |     hil_puts("hi\n")
    #       |                     ^
    #       |                     ;
    (attempt_dir / "build.log").write_text(" ".join(cmd) + "\n\n" + gcc.stdout + gcc.stderr)
    if gcc.returncode != 0:
        return StageResult("build", False, "compile failed",
                           feedback="The code did not compile:\n" + tail(gcc.stderr))

    # 3. Turn kernel.elf into the raw bytes we send to the Pi.
    objcopy = subprocess.run([OBJCOPY, "-O", "binary", "kernel.elf", "kernel.bin"],
                             cwd=attempt_dir, capture_output=True, text=True)
    if objcopy.returncode != 0:
        return StageResult("build", False, "objcopy failed", blame="rig")

    # 4. Check the size and compute the checksum.
    # checksum is a networking term to check if the data was corrupted in the transmission
    # process becuase the checksum at the pi should be the same here 
    # max size is 1 MB because the pi has limited memory and we don't want to send too much data
    data = (attempt_dir / "kernel.bin").read_bytes()
    if len(data) > MAX_BIN_BYTES:
        return StageResult("build", False, f"binary too large ({len(data)} bytes)",
                           feedback=f"The program is {len(data)} bytes; the limit is {MAX_BIN_BYTES}.")

    # return the result with the path to the kernel.elf and kernel.bin files, 
    # the length of the binary, and the crc32 checksum
    return StageResult("build", True, f"kernel.bin {len(data)} B", artifacts={
        # should be used by qemu to check for correctness
        "elf": str(attempt_dir / "kernel.elf"),
        # should be used by the runner to send to the pi
        "bin": str(attempt_dir / "kernel.bin"),
        # so bootloader knows how many bytes to read
        "length": len(data),
        # so bootloader can check for data corruption during transmission
        "crc32": zlib.crc32(data),
    })
