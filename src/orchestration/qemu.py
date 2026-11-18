"""Run an ELF briefly and return its UART output, without judging the firmware."""

import asyncio
import math
from pathlib import Path
from time import monotonic

QEMU = "qemu-system-arm"
MAX_OUTPUT_BYTES = 64 * 1024  # Per stream; keep draining after this limit.


async def observe(elf: Path, duration_seconds: float = 1.0) -> dict:
    """Capture a bounded QEMU run. Always stop and reap the child process."""
    if not math.isfinite(duration_seconds) or not 0 < duration_seconds <= 10:
        return {"status": "error", "execution_status": "invalid_request",
                "message": "duration_seconds must be greater than 0 and at most 10."}
    if not elf.is_file():
        return {"status": "error", "execution_status": "infrastructure_error",
                "message": "Compiled ELF is missing. Compile the project again."}

    try:
        process = await asyncio.create_subprocess_exec(
            QEMU, "-M", "raspi0", "-kernel", str(elf),
            "-display", "none", "-serial", "stdio", "-monitor", "none",
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError:
        return {"status": "error", "execution_status": "infrastructure_error",
                "message": "Could not start qemu-system-arm. Check that QEMU is installed."}

    async def collect(stream):
        # Read both streams while QEMU runs so a full pipe cannot block it.
        output = bytearray()
        truncated = False
        while chunk := await stream.read(4096):
            remaining = MAX_OUTPUT_BYTES - len(output)
            output.extend(chunk[:remaining])
            truncated = truncated or len(chunk) > remaining
        return output.decode("utf-8", errors="replace").replace("\r", ""), truncated

    started = monotonic()
    uart_reader = asyncio.create_task(collect(process.stdout))
    error_reader = asyncio.create_task(collect(process.stderr))
    stopped_by_limit = False
    try:
        try:
            await asyncio.wait_for(process.wait(), timeout=duration_seconds)
        except asyncio.TimeoutError:
            stopped_by_limit = True
    finally:
        # Also runs if the HTTP/agent task is cancelled or an exception occurs.
        if process.returncode is None:
            process.kill()
        await process.wait()
        uart, errors = await asyncio.gather(uart_reader, error_reader)

    uart_output, uart_truncated = uart
    qemu_errors, errors_truncated = errors
    return {
        "status": "success" if stopped_by_limit or process.returncode == 0 else "error",
        "execution_status": "observation_complete" if stopped_by_limit else "process_exited",
        "observed_seconds": round(monotonic() - started, 3),
        "stopped_by": "observation_limit" if stopped_by_limit else "process_exit",
        "exit_code": None if stopped_by_limit else process.returncode,
        "uart_output": uart_output,
        "qemu_errors": qemu_errors,
        "uart_truncated": uart_truncated,
        "errors_truncated": errors_truncated,
        "simulated": False,
        "note": "Emulator observation only. Tool success is not a firmware test pass; no physical hardware was used.",
    }
