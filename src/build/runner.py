"""
DELIVERABLE D4: THE RUNNER  (the hardest one: work in pairs, start after D1-D2)
==========================

BACKGROUND (read this first)
----------------------------
This is the only code that talks to REAL hardware. It sends the AI's program to
the real Raspberry Pi, runs it, and collects a recording from the FPGA.

Two boards, each plugged into your laptop with a USB cable:
    Raspberry Pi Zero   runs the AI's program.
                        A small USB-to-serial adapter (CP2102) connects to it.
    Basys 3 FPGA        watches 8 wires coming from the Pi ("strobe pins") and records
                        exactly when each one changes, accurate to 10 nanoseconds.
                        That's how we check the program's timing.

A SERIAL PORT is a simple connection that sends bytes one after another.
On a Mac each board shows up as a file like /dev/tty.usbserial-0001.
In Python, use the pyserial library (pip install pyserial):

    import serial
    port = serial.Serial("/dev/tty.usbserial-0001", 115200, timeout=0.2)
    port.write(b"hello")     # send bytes
    data = port.read(256)    # read up to 256 bytes; returns b"" after 0.2 s if nothing came

A PROTOCOL is the set of rules two devices agree on, so they understand each
other. The other teams are building the Pi bootloader and the FPGA design to match
the two protocols below. DON'T change them without talking to those teams.

Note: b"..." is a BYTES string. Serial ports send bytes, not normal Python strings.


PROTOCOL 1: SENDING A PROGRAM TO THE PI
---------------------------------------
The Pi runs a small "bootloader" program that waits for us to send it a program.

    Pi  -> us  "RDY\\n"       repeated about twice a second: "I'm ready, send me a program"
    us  -> Pi  a 12-byte header, then the program bytes (kernel.bin):
                   b"HIL1"                    4 bytes: "a program is coming"
                   length of the program      4 bytes \\
                   CRC32 of the program       4 bytes  > both made with struct.pack("<II", length, crc)
    Pi  -> us  "OK\\n"         the CRC matched and the program is starting
           or  "ER\\n"         the data got corrupted: send it again
    then the program's own text: HIL:BOOT ... HIL:DONE (or HIL:PANIC <reason>)

PROTOCOL 2: TALKING TO THE FPGA
-------------------------------
    send b"A"  (Arm: clear the memory, start recording)  -> FPGA answers b"K"
    send b"S"  (Stop recording)                           -> FPGA answers b"K"
    send b"D"  (Dump: send me the recording)              -> FPGA answers with:
          2 bytes   how many records follow (little-endian number)
          then, for each record, 8 bytes:
              5 bytes  time since Arm, counted in 10-nanosecond ticks (little-endian)
              1 byte   the level of all 8 pins after the change (bit 0 = pin S0, ...)
              1 byte   which pins just changed
              1 byte   flags (ignore for now)
    "Little-endian" means the smallest byte comes first. Python handles it for you:
        int.from_bytes(five_bytes, "little")   and   struct.unpack("<H", two_bytes)


WHAT TO BUILD
-------------
    runner = Runner(pi_port, fpga_port)     # fpga_port can be None: no recording
    result = runner.flash_and_run("kernel.bin", run_timeout_s=10.0, tries=3)

flash_and_run steps:
    1. Read from the Pi until you see b"RDY".
    2. If there's an FPGA, send "A" (arm) NOW, before the program starts,
       or you'll miss its first pin changes.
    3. Send the header + program. Read until you see b"OK\\n" or b"ER\\n".
       (Leftover "RDY" lines may still arrive: skip them.)
    4. On OK: keep reading the Pi's text until HIL:DONE, HIL:PANIC, or run_timeout_s.
       Careful: the first lines of the program's text may arrive in the SAME read
       as "OK\\n". Keep whatever comes after it.
    5. If there's an FPGA: send "S" (stop), then "D" (dump), and decode the records.
    If there's no RDY, or the answer is ER: try again, up to `tries` attempts in total.


WHAT TO RETURN
--------------
    StageResult("runner", ok, summary, feedback=..., blame=...,
                artifacts={"console": text,
                           "outcome": "done" or "panic" or "hang",
                           "trace": list of records})
    Each trace record needs .t_ns (time in nanoseconds = ticks * 10), .pins and
    .changed. A small @dataclass works well for this.

    what happened            ok     blame    notes
    HIL:DONE                 True
    HIL:PANIC                False  "code"   feedback includes the Pi's text
    no DONE in time          False  "code"   outcome "hang"
    every attempt failed     False  "rig"    a hardware problem: the AI must not be blamed


TESTING WITHOUT HARDWARE
------------------------
You DON'T need the real boards to finish this. tests/fake_rig.py creates a FAKE Pi
and a FAKE FPGA that follow both protocols exactly. Each one has a .path you pass
to Runner, just like a real port. Read fake_rig.py first: it shows the protocols
from the other side.

From src/build/, run:   python3 -m pytest tests/test_runner.py -v
The tests check: a normal run with a decoded trace, a panic, a hang, a corrupted
transfer (retried exactly `tries` times, then blamed on the "rig"), and a Pi that
never says RDY.
"""
from __future__ import annotations

from pathlib import Path

from common import StageResult


class Runner:
    def __init__(self, pi_port: str, fpga_port: str | None = None):
        """Open the serial port to the Pi (and to the FPGA, if fpga_port is given)."""
        # TODO
        raise NotImplementedError("TODO: write the runner")

    def flash_and_run(self, bin_path: Path, run_timeout_s: float = 10.0,
                      tries: int = 3) -> StageResult:
        """Send the program to the Pi, run it, and collect its output and the FPGA recording."""
        # TODO
        raise NotImplementedError("TODO: write the runner")
