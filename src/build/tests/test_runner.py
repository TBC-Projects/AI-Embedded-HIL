"""Tests for runner.py, using the fake Pi and FPGA in fake_rig.py (no hardware needed)."""
import pytest

from runner import Runner
from tests.fake_rig import FakeFpga, FakePi


@pytest.fixture
def binary(tmp_path):
    p = tmp_path / "kernel.bin"
    p.write_bytes(bytes(range(256)) * 20)        # 5 KB dummy payload
    return p


def make(mode, with_fpga=True):
    """Start a fake Pi (and optionally a fake FPGA) and a Runner connected to them."""
    pi = FakePi(mode)
    fpga = FakeFpga() if with_fpga else None
    return pi, fpga, Runner(pi.path, fpga.path if fpga else None)


def test_flash_run_and_trace(binary):
    pi, fpga, runner = make("done")
    r = runner.flash_and_run(binary, run_timeout_s=3)
    pi.close()
    assert r.ok, r.summary
    assert "HIL:BOOT" in r.artifacts["console"] and "working" in r.artifacts["console"]
    trace = r.artifacts["trace"]
    assert len(trace) == 6
    assert trace[0].t_ns == 1_000_000            # 100_000 ticks x 10 ns
    assert fpga.commands[:1] == [b"A"]           # armed before flashing
    assert fpga.commands[-2:] == [b"S", b"D"]


def test_panic_is_a_code_failure(binary):
    pi, _, runner = make("panic")
    r = runner.flash_and_run(binary, run_timeout_s=3)
    pi.close()
    assert not r.ok and r.blame == "code"
    assert "bad timer" in r.feedback


def test_hang_times_out(binary):
    pi, _, runner = make("hang")
    r = runner.flash_and_run(binary, run_timeout_s=1)
    pi.close()
    assert not r.ok and r.blame == "code"
    assert r.artifacts["outcome"] == "hang"


def test_crc_error_retries_then_blames_rig(binary):
    pi, _, runner = make("bad_crc", with_fpga=False)
    r = runner.flash_and_run(binary, run_timeout_s=1, tries=3)
    pi.close()
    assert not r.ok and r.blame == "rig"
    assert pi.flashes == 3


def test_no_bootloader_blames_rig(binary):
    pi, _, runner = make("silent", with_fpga=False)
    r = runner.flash_and_run(binary, run_timeout_s=1, tries=1)
    pi.close()
    assert not r.ok and r.blame == "rig"
