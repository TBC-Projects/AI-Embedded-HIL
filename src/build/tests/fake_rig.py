"""Fake hardware for testing runner.py without a Pi or an FPGA.

Each fake opens a pseudo-terminal (a pair of connected virtual serial ports).
The runner opens one end via .path, as if it were a real USB serial port, and a
background thread plays the device on the other end. Both fakes speak the
protocols documented at the top of runner.py.
"""
import os
import struct
import threading
import time
import tty
import zlib


def _open_pty() -> tuple[int, str]:
    """Return (our file descriptor, path of the other end for the runner to open)."""
    ours, theirs = os.openpty()
    tty.setraw(ours)    # raw mode: pass bytes through unchanged
    tty.setraw(theirs)
    return ours, os.ttyname(theirs)


class FakePi:
    """Pretends to be the Pi bootloader plus a program running after it.

    mode decides what happens after a flash:
        "done"     CRC ok, the program prints HIL:DONE
        "panic"    CRC ok, the program prints HIL:PANIC bad timer
        "hang"     CRC ok, the program prints nothing more
        "bad_crc"  always answers ER, so the runner retries
        "silent"   never sends RDY, as if the bootloader isn't running
    """

    def __init__(self, mode: str = "done"):
        self.mode = mode
        self.fd, self.path = _open_pty()
        self.flashes = 0        # how many binaries the runner has sent
        self._stopped = False
        threading.Thread(target=self._run, daemon=True).start()

    def close(self) -> None:
        self._stopped = True

    def _run(self) -> None:
        os.set_blocking(self.fd, False)
        received = b""
        while not self._stopped:
            if self.mode != "silent":
                os.write(self.fd, b"RDY\n")
            time.sleep(0.1)
            received += self._read()

            # Wait for a full header: "HIL1" + length + crc (12 bytes).
            start = received.find(b"HIL1")
            if start < 0 or len(received) < start + 12:
                continue
            received = received[start:]
            length, crc = struct.unpack("<II", received[4:12])
            while len(received) < 12 + length:
                received += self._read()
                time.sleep(0.01)
            binary, received = received[12:12 + length], received[12 + length:]
            self.flashes += 1

            crc_ok = zlib.crc32(binary) == crc and self.mode != "bad_crc"
            if not crc_ok:
                os.write(self.fd, b"ER\n")
                continue
            self._play_program()

    def _play_program(self) -> None:
        os.write(self.fd, b"OK\nHIL:BOOT\r\nworking\r\n")
        if self.mode == "done":
            os.write(self.fd, b"HIL:DONE\r\n")
        elif self.mode == "panic":
            os.write(self.fd, b"HIL:PANIC bad timer\r\n")
        else:  # hang: say nothing until the test ends
            while not self._stopped:
                time.sleep(0.1)
        time.sleep(0.2)

    def _read(self) -> bytes:
        try:
            return os.read(self.fd, 65536)
        except (BlockingIOError, OSError):
            return b""


class FakeFpga:
    """Pretends to be the Basys 3 trace core.

    Answers A and S with "K". Answers D with `edges` records, one every 1 ms,
    with strobe S0 toggling.
    """

    def __init__(self, edges: int = 6):
        self.fd, self.path = _open_pty()
        self.edges = edges
        self.commands = []      # every command byte received, in order
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        while True:
            command = os.read(self.fd, 1)
            self.commands.append(command)
            if command in (b"A", b"S"):
                os.write(self.fd, b"K")
            elif command == b"D":
                os.write(self.fd, struct.pack("<H", self.edges) + self._records())

    def _records(self) -> bytes:
        records = b""
        for i in range(1, self.edges + 1):
            ticks = 100_000 * i                          # 1 ms apart at 10 ns per tick
            pins, changed, flags = i & 1, 0b1, 0
            records += ticks.to_bytes(5, "little") + bytes([pins, changed, flags])
        return records
