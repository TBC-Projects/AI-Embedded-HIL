"""Step 7: Runner. The only code that touches the physical rig.

Hardware (two USB serial ports):
    CP2102 adapter   <-> Pi Zero UART0     the bootloader, then the program's console
    Basys 3 (FTDI)   <-> FPGA trace core   records every edge on the Pi's strobe pins

Only one process can open a serial port at a time, so in the full system the
runner is a long-running process that the orchestrator sends jobs to.

What flash_and_run() does:
    1. Wait for the Pi bootloader to say it's ready ("RDY").
    2. Arm the FPGA, so it catches the very first strobe edge.
    3. Send the binary and wait for the bootloader's "OK" (CRC matched) or "ER".
    4. Read the program's console until HIL:DONE, HIL:PANIC, or the timeout.
    5. Stop the FPGA and download the captured edges.
If step 1 or 3 fails, it retries up to `tries` times and then reports
blame=rig, so the LLM never sees hardware problems.

Pi bootloader protocol (PROPOSED; the bootloader firmware must match it):
    Pi   -> host : "RDY\\n" about every 500 ms while waiting
    host -> Pi   : b"HIL1" + length (u32, little-endian) + crc32 (u32, LE) + binary
    Pi   -> host : "OK\\n" (CRC matched, jumping to 0x8000) or "ER\\n" (try again)
    then the program's own console output: HIL:BOOT ... HIL:DONE | HIL:PANIC <reason>

FPGA trace core protocol (PROPOSED; the FPGA design must match it):
    host sends "A" (arm)  -> FPGA replies "K"
    host sends "S" (stop) -> FPGA replies "K"
    host sends "D" (dump) -> FPGA replies with a u16 record count, then 8-byte records:
                             5 bytes  timestamp in 10 ns ticks (little-endian)
                             1 byte   pin levels after the edge (bit n = strobe Sn)
                             1 byte   which pins changed
                             1 byte   flags (unused for now)

Usage:
    python3 runner.py kernel.bin --pi /dev/tty.usbserial-XXXX --fpga /dev/tty.usbserial-YYYY

Deliverable D4. Run the tests with: python3 -m pytest tests/test_runner.py
(tests/fake_rig.py fakes the Pi and the FPGA, so no hardware is needed.)
"""
from __future__ import annotations

import struct
import time
import zlib
from dataclasses import dataclass
from pathlib import Path

import serial  # pip install pyserial

from common import BLAME_CODE, BLAME_RIG, StageResult, find_verdict, tail

STAGE = "runner"
BAUD = 115200

# Bootloader protocol
BOOT_MAGIC = b"HIL1"
READY = b"RDY"
ACCEPTED = b"OK\n"
REJECTED = b"ER\n"

# Timeouts and sizes
READY_TIMEOUT_S = 3.0    # how long to wait for RDY before resetting the Pi
VERDICT_TIMEOUT_S = 3.0  # how long to wait for OK/ER after sending the binary
SEND_CHUNK = 1024        # bytes written per serial write
READ_CHUNK = 256         # bytes read per serial read

# FPGA trace records
TRACE_RECORD = struct.Struct("<5sBBB")  # timestamp, pins, changed, flags (8 bytes)
NS_PER_TICK = 10                        # the trace core counts at 100 MHz


@dataclass
class TraceRecord:
    """One edge seen by the FPGA."""
    t_ns: int     # time since the FPGA was armed, in nanoseconds
    pins: int     # level of all 8 strobe pins after this edge (bit n = strobe Sn)
    changed: int  # which pins changed at this edge (bit n = strobe Sn)


class Fpga:
    """Talks to the Basys 3 trace core. Protocol: see the top of this file."""

    def __init__(self, port: str, baud: int = BAUD):
        self.serial = serial.Serial(port, baud, timeout=1.0)

    def arm(self) -> None:
        """Clear old records and start recording edges."""
        self._command(b"A")

    def stop(self) -> None:
        """Stop recording."""
        self._command(b"S")

    def dump(self) -> list[TraceRecord]:
        """Download every recorded edge."""
        self.serial.reset_input_buffer()
        self.serial.write(b"D")
        # TODO:
        #   1. Read 2 bytes and unpack the record count: struct.unpack("<H", ...)
        #   2. Read count * TRACE_RECORD.size bytes.
        #   3. For each record in TRACE_RECORD.iter_unpack(raw) -> (timestamp, pins, changed, flags):
        #        timestamp is 5 raw bytes: convert with int.from_bytes(timestamp, "little"),
        #        then multiply by NS_PER_TICK to get nanoseconds.
        #        Append TraceRecord(t_ns, pins, changed).
        raise NotImplementedError("TODO: Fpga.dump")

    def _command(self, letter: bytes) -> None:
        """Send a one-letter command and check that the FPGA answers "K"."""
        # TODO: clear the input buffer, write the letter, read 1 byte.
        #       If it isn't b"K", raise IOError(f"FPGA did not acknowledge {letter!r}").
        raise NotImplementedError("TODO: Fpga._command")


class Runner:
    """Owns the Pi's serial port (and optionally the FPGA's) and runs one binary at a time."""

    def __init__(self, pi_port: str, fpga_port: str | None = None,
                 baud: int = BAUD, use_dtr_reset: bool = False):
        """
        pi_port        CP2102 serial port connected to the Pi
        fpga_port      Basys 3 serial port; None runs without a trace
        use_dtr_reset  True if the CP2102's DTR pin is wired to the Pi's RUN pad,
                       which lets us reset the Pi from software
        """
        self.pi = serial.Serial(pi_port, baud, timeout=0.2)
        self.fpga = Fpga(fpga_port) if fpga_port else None
        self.use_dtr_reset = use_dtr_reset

    def flash_and_run(self, bin_path: Path, run_timeout_s: float = 10.0,
                      tries: int = 3) -> StageResult:
        """Flash bin_path to the Pi, run it, and collect its console and trace."""
        binary = Path(bin_path).read_bytes()

        # TODO Steps 1-3: early_console = self._flash(binary, tries)
        #   If it returns None -> failing StageResult,
        #   summary "flash failed (no RDY or CRC error)", blame=BLAME_RIG.

        # TODO Step 4: console, outcome = self._read_console(early_console, run_timeout_s)

        # TODO Step 5: if there's an FPGA, stop it and dump the trace (otherwise trace = []).

        # TODO: build the result. artifacts = {"console": ..., "trace": ..., "outcome": ...}
        #   - "done"  -> pass, summary f"ran on Pi, {len(trace)} edges captured"
        #   - "panic" -> reason "the program called hil_panic"
        #   - "hang"  -> reason f"no HIL:DONE within {run_timeout_s:g}s on real hardware (hang)"
        #   On failure: call self.reset_pi() (gets the bootloader back for the next job) and
        #   return blame=BLAME_CODE with
        #   feedback f"On the real Pi: {reason}.\nConsole:\n{tail(console, 20)}"
        raise NotImplementedError("TODO: flash_and_run")

    def reset_pi(self) -> None:
        """Reset the Pi by pulsing DTR. Does nothing unless use_dtr_reset is set."""
        if self.use_dtr_reset:
            self.pi.dtr = True   # asserting DTR pulls the RUN pad low
            time.sleep(0.1)
            self.pi.dtr = False

    # --- helpers -------------------------------------------------------------

    def _flash(self, binary: bytes, tries: int) -> bytes | None:
        """Send the binary to the bootloader, retrying up to `tries` times.

        Returns any console bytes that arrived right after "OK" (the program can
        start printing at once), or None if every try failed.
        """
        header = BOOT_MAGIC + struct.pack("<II", len(binary), zlib.crc32(binary))

        # TODO: for each try:
        #   1. self.pi.reset_input_buffer(), then wait for READY with
        #      self._read_until([READY], READY_TIMEOUT_S).
        #      No RDY -> self.reset_pi() and go on to the next try.
        #   2. If there's an FPGA, arm it NOW, before sending, or the first edges are missed.
        #   3. self.pi.reset_input_buffer() (drop old RDY lines), then self._send(header + binary).
        #   4. Wait for ACCEPTED or REJECTED with _read_until(..., VERDICT_TIMEOUT_S).
        #      If ACCEPTED is in the reply, return everything AFTER it:
        #      reply.split(ACCEPTED, 1)[1]
        #      Otherwise self.reset_pi() and try again.
        # After every try has failed, return None.
        raise NotImplementedError("TODO: _flash")

    def _send(self, data: bytes) -> None:
        for start in range(0, len(data), SEND_CHUNK):
            self.pi.write(data[start:start + SEND_CHUNK])
        self.pi.flush()

    def _read_until(self, tokens: list[bytes], timeout_s: float) -> tuple[bool, bytes]:
        """Read from the Pi until any of `tokens` appears or time runs out.

        Returns (found, everything read so far).
        """
        # TODO: keep calling self.pi.read(READ_CHUNK) and adding to a buffer until one of
        #       the tokens is in the buffer (return True, buffer) or the deadline passes
        #       (return False, buffer). Use time.monotonic() for the deadline.
        raise NotImplementedError("TODO: _read_until")

    def _read_console(self, console: bytes, timeout_s: float) -> tuple[str, str]:
        """Keep reading the program's console until it finishes or time runs out.

        `console` is what was already received along with "OK".
        Returns (console text, outcome), where outcome is "done", "panic" or "hang".
        """
        # TODO:
        #   1. Check find_verdict(console.decode(errors="replace")) FIRST: the program may
        #      already have finished in the bytes that came with "OK".
        #   2. While there's no verdict and the deadline hasn't passed, read more with
        #      self.pi.read(READ_CHUNK) and check again.
        #   3. Return the text with "\r" removed, and the verdict (or "hang" if there was none).
        raise NotImplementedError("TODO: _read_console")


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Flash one binary to the Pi and run it")
    parser.add_argument("bin", help="kernel.bin produced by build.py")
    parser.add_argument("--pi", required=True, help="CP2102 port, e.g. /dev/tty.usbserial-0001")
    parser.add_argument("--fpga", help="Basys 3 port, e.g. /dev/tty.usbserial-210183A1B2C31")
    args = parser.parse_args()

    result = Runner(args.pi, args.fpga).flash_and_run(Path(args.bin))
    print(result.summary)
    print(result.artifacts.get("console", ""))


if __name__ == "__main__":
    main()
