"""Run an ELF briefly and return its UART output, without judging the firmware.

On Windows, asyncio can only spawn subprocesses on the Proactor event loop.
uvicorn uses the Selector loop when it runs with --reload (or workers > 1),
and that loop raises NotImplementedError for subprocesses. Observation then
falls back to a background thread that drives subprocess.Popen; the returned
fields are identical. On macOS and Linux the asyncio path is unchanged.
"""

import asyncio
import math
import os
import subprocess
import threading
import time
from pathlib import Path
from time import monotonic

QEMU = "qemu-system-arm"
MAX_OUTPUT_BYTES = 64 * 1024  # Per stream; keep draining after this limit.
POLL_SECONDS = 0.02


def _qemu_command() -> str:
    """Return the executable name, allowing QEMU_PATH to override PATH."""
    return os.environ.get("QEMU_PATH") or QEMU


async def observe(elf: Path, duration_seconds: float = 1.0) -> dict:
    """Capture a bounded QEMU run. Always stop and reap the child process."""
    if not math.isfinite(duration_seconds) or not 0 < duration_seconds <= 10:
        return {"status": "error", "execution_status": "invalid_request",
                "message": "duration_seconds must be greater than 0 and at most 10."}
    if not elf.is_file():
        return {"status": "error", "execution_status": "infrastructure_error",
                "message": "Compiled ELF is missing. Compile the project again."}

    qemu = _qemu_command()

    argv = [qemu, "-M", "raspi0", "-kernel", str(elf),
            "-display", "none", "-serial", "stdio", "-monitor", "none"]

    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except NotImplementedError:
        # Windows SelectorEventLoop: no subprocess support (uvicorn --reload).
        return await _observe_threaded(argv, duration_seconds)
    except OSError:
        return _infrastructure_error(
            f"Could not start {qemu}. Check that QEMU is installed and on PATH, "
            "or set QEMU_PATH to the executable."
        )

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
    return _result(
        uart_output=uart_output, qemu_errors=qemu_errors,
        uart_truncated=uart_truncated, errors_truncated=errors_truncated,
        stopped_by_limit=stopped_by_limit, returncode=process.returncode,
        started=started,
    )


async def _observe_threaded(argv: list[str], duration_seconds: float) -> dict:
    """Run the same observation on a worker thread.

    Used when the running event loop cannot create subprocesses. The thread is
    told to stop through an event, so cancelling the awaiting task still kills
    and reaps QEMU promptly.
    """
    started = monotonic()
    stop = threading.Event()
    try:
        captured = await asyncio.to_thread(
            _capture_threaded, argv, duration_seconds, stop)
    except OSError:
        return _infrastructure_error(
            f"Could not start {argv[0]}. Check that QEMU is installed and on PATH, "
            "or set QEMU_PATH to the executable."
        )
    finally:
        stop.set()
    uart, errors, uart_truncated, errors_truncated, stopped_by_limit, returncode = captured
    return _result(
        uart_output=uart, qemu_errors=errors,
        uart_truncated=uart_truncated, errors_truncated=errors_truncated,
        stopped_by_limit=stopped_by_limit, returncode=returncode,
        started=started,
    )


def _capture_threaded(argv: list[str], duration_seconds: float,
                      stop_event: threading.Event) -> tuple:
    """Blocking capture of one QEMU run, bounded like the asyncio path."""
    process = subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    uart = bytearray()
    errors = bytearray()
    truncated = [False, False]

    def drain(stream, sink, index):
        while True:
            chunk = stream.read(4096)
            if not chunk:
                return
            remaining = MAX_OUTPUT_BYTES - len(sink)
            sink.extend(chunk[:remaining])
            truncated[index] = truncated[index] or len(chunk) > remaining

    readers = [
        threading.Thread(target=drain, args=(process.stdout, uart, 0), daemon=True),
        threading.Thread(target=drain, args=(process.stderr, errors, 1), daemon=True),
    ]
    for reader in readers:
        reader.start()

    deadline = monotonic() + duration_seconds
    while monotonic() < deadline and not stop_event.is_set():
        if process.poll() is not None:
            break
        time.sleep(POLL_SECONDS)

    stopped_by_limit = process.poll() is None
    try:
        if stopped_by_limit:
            process.kill()
    finally:
        process.wait()
        for reader in readers:
            reader.join(timeout=1.0)
        process.stdout.close()
        process.stderr.close()

    return (
        uart.decode("utf-8", errors="replace").replace("\r", ""),
        errors.decode("utf-8", errors="replace").replace("\r", ""),
        truncated[0],
        truncated[1],
        stopped_by_limit,
        process.returncode,
    )


def _result(*, uart_output, qemu_errors, uart_truncated, errors_truncated,
            stopped_by_limit, returncode, started) -> dict:
    """Build the observation result; both execution paths share this shape."""
    return {
        "status": "success" if stopped_by_limit or returncode == 0 else "error",
        "execution_status": "observation_complete" if stopped_by_limit else "process_exited",
        "observed_seconds": round(monotonic() - started, 3),
        "stopped_by": "observation_limit" if stopped_by_limit else "process_exit",
        "exit_code": None if stopped_by_limit else returncode,
        "uart_output": uart_output,
        "qemu_errors": qemu_errors,
        "uart_truncated": uart_truncated,
        "errors_truncated": errors_truncated,
        "simulated": False,
        "note": "Emulator observation only. Tool success is not a firmware test pass; no physical hardware was used.",
    }


def _infrastructure_error(message: str) -> dict:
    return {"status": "error", "execution_status": "infrastructure_error",
            "message": message}
