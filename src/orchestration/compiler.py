"""Local ARM build helper, adapted from src/build/build.py.

Kept here so the orchestration MVP does not import the separate build pipeline.
"""

from dataclasses import dataclass, field
from pathlib import Path
import subprocess
import zlib


@dataclass
class StageResult:
    stage: str
    ok: bool
    summary: str
    feedback: str = ""
    blame: str = "code"  # "code": revise firmware; "rig": fix the local setup.
    artifacts: dict = field(default_factory=dict)


CC = "arm-none-eabi-gcc"
OBJCOPY = "arm-none-eabi-objcopy"
MAX_BIN_BYTES = 1 << 20
CFLAGS = [
    "-mcpu=arm1176jzf-s", "-marm", "-O2", "-g", "-ffreestanding",
    "-nostdlib", "-fno-builtin", "-Wall", "-Wextra",
]


def run(project: Path) -> StageResult:
    """Compile a prepared project into kernel.elf and kernel.bin."""
    if not (project / "linker.ld").is_file():
        return StageResult("build", False, "linker.ld missing", blame="rig")

    sources = sorted("src/" + path.name for path in project.glob("src/*.c"))
    if not sources:
        return StageResult("build", False, "no src/*.c files",
                           feedback="No C source files were provided under src/.")
    support = sorted(path.name for path in project.glob("*.S"))
    support += sorted(path.name for path in project.glob("*.c"))
    command = [CC, *CFLAGS, "-I.", "-T", "linker.ld", *support, *sources,
               "-o", "kernel.elf", "-lgcc"]
    try:
        compiled = subprocess.run(command, cwd=project, capture_output=True, text=True)
    except FileNotFoundError:
        return StageResult("build", False, f"{CC} is not installed", blame="rig")

    (project / "build.log").write_text(
        " ".join(command) + "\n\n" + compiled.stdout + compiled.stderr,
    )
    if compiled.returncode != 0:
        feedback = "\n".join(compiled.stderr.strip().splitlines()[-40:])[-2000:]
        return StageResult("build", False, "compile failed",
                           feedback="The code did not compile:\n" + feedback)

    command = [OBJCOPY, "-O", "binary", "kernel.elf", "kernel.bin"]
    try:
        converted = subprocess.run(command, cwd=project, capture_output=True, text=True)
    except FileNotFoundError:
        return StageResult("build", False, f"{OBJCOPY} is not installed", blame="rig")
    with (project / "build.log").open("a") as log:
        log.write("\n" + " ".join(command) + "\n" + converted.stdout + converted.stderr)
    if converted.returncode != 0:
        return StageResult("build", False, "objcopy failed", blame="rig",
                           feedback=converted.stderr[-2000:])

    data = (project / "kernel.bin").read_bytes()
    if len(data) > MAX_BIN_BYTES:
        return StageResult("build", False, f"binary too large ({len(data)} bytes)",
                           feedback=f"The program is {len(data)} bytes; the limit is {MAX_BIN_BYTES}.")
    return StageResult("build", True, f"kernel.bin {len(data)} B", artifacts={
        "elf": str(project / "kernel.elf"),
        "bin": str(project / "kernel.bin"),
        "length": len(data),
        "crc32": zlib.crc32(data),
    })
