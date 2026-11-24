"""Bounded capture/cleanup tests. Real child processes; no Gemini needed."""

import asyncio
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

from . import qemu


class QemuObservationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.elf = Path(directory.name) / "kernel.elf"
        self.elf.write_bytes(b"test")
        self.children = []
        self.spawn = asyncio.create_subprocess_exec
        env = patch.dict(os.environ, {"QEMU_PATH": ""})
        env.start()
        self.addCleanup(env.stop)

    async def launch_child(self, script, **kwargs):
        child = await self.spawn(sys.executable, "-u", "-c", script, **kwargs)
        self.children.append(child)
        return child

    async def test_captures_partial_uart_and_errors_then_stops_child(self):
        async def spawn(*args, **kwargs):
            self.assertEqual(args[0], qemu.QEMU)
            return await self.launch_child(
                'import sys,time; print("Hello", end="", flush=True); '
                'print("diagnostic", file=sys.stderr, flush=True); time.sleep(60)',
                **kwargs,
            )
        with patch.object(qemu.asyncio, "create_subprocess_exec", spawn):
            result = await qemu.observe(self.elf, 2.0)
        self.assertEqual(result["uart_output"], "Hello")
        self.assertIn("diagnostic", result["qemu_errors"])
        self.assertEqual(result["stopped_by"], "observation_limit")
        self.assertNotIn("test_outcome", result)
        self.assertIsNotNone(self.children[0].returncode)

    async def test_early_process_error_is_reported_with_stderr(self):
        async def spawn(*args, **kwargs):
            return await self.launch_child(
                'import sys; print("bad ELF", file=sys.stderr); sys.exit(1)', **kwargs,
            )
        with patch.object(qemu.asyncio, "create_subprocess_exec", spawn):
            result = await qemu.observe(self.elf, 2.0)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["execution_status"], "process_exited")
        self.assertEqual(result["exit_code"], 1)
        self.assertIn("bad ELF", result["qemu_errors"])

    async def test_drains_both_streams_and_marks_truncated_output(self):
        async def spawn(*args, **kwargs):
            return await self.launch_child(
                'import sys,time; sys.stdout.write("A"*100000); sys.stdout.flush(); '
                'sys.stderr.write("B"*100000); sys.stderr.flush(); time.sleep(60)', **kwargs,
            )
        with patch.object(qemu.asyncio, "create_subprocess_exec", spawn), patch.object(qemu, "MAX_OUTPUT_BYTES", 128):
            result = await qemu.observe(self.elf, 2.0)
        self.assertEqual(result["uart_output"], "A" * 128)
        self.assertEqual(result["qemu_errors"], "B" * 128)
        self.assertTrue(result["uart_truncated"])
        self.assertTrue(result["errors_truncated"])

    async def test_cancellation_reaps_child(self):
        ready = asyncio.Event()

        async def spawn(*args, **kwargs):
            child = await self.launch_child('import time; time.sleep(60)', **kwargs)
            ready.set()
            return child

        with patch.object(qemu.asyncio, "create_subprocess_exec", spawn):
            task = asyncio.create_task(qemu.observe(self.elf, 10))
            await ready.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertIsNotNone(self.children[0].returncode)

    async def test_invalid_duration_missing_elf_and_missing_qemu(self):
        for duration in (0, -1, 11, float("nan"), float("inf")):
            result = await qemu.observe(self.elf, duration)
            self.assertEqual(result["execution_status"], "invalid_request")
        result = await qemu.observe(self.elf.parent / "missing.elf")
        self.assertEqual(result["execution_status"], "infrastructure_error")
        with patch.object(qemu, "QEMU", "missing-qemu-for-test"):
            result = await qemu.observe(self.elf)
        self.assertEqual(result["execution_status"], "infrastructure_error")

    # --- Windows fallback (Selector event loop has no subprocess support) ---

    def test_threaded_capture_reads_both_streams_and_stops_child(self):
        argv = [sys.executable, "-u", "-c",
                'import sys,time; print("Hello", end="", flush=True); '
                'print("diagnostic", file=sys.stderr, flush=True); time.sleep(60)']
        uart, errors, uart_truncated, errors_truncated, stopped, code = (
            qemu._capture_threaded(argv, 2.0, threading.Event()))
        self.assertEqual(uart, "Hello")
        self.assertIn("diagnostic", errors)
        self.assertFalse(uart_truncated)
        self.assertFalse(errors_truncated)
        self.assertTrue(stopped)
        self.assertIsNotNone(code)

    async def test_falls_back_to_threads_when_loop_cannot_spawn(self):
        seen = {}

        async def no_subprocess(*args, **kwargs):
            raise NotImplementedError

        def fake_capture(argv, duration, stop):
            seen["argv"] = argv
            return "HIL:BOOT\n", "", False, False, True, None

        with patch.object(qemu.asyncio, "create_subprocess_exec", no_subprocess), \
                patch.object(qemu, "_capture_threaded", fake_capture):
            result = await qemu.observe(self.elf, 0.2)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["uart_output"], "HIL:BOOT\n")
        self.assertEqual(result["stopped_by"], "observation_limit")
        self.assertEqual(seen["argv"][0], qemu.QEMU)

    async def test_missing_qemu_suggests_qemu_path(self):
        with patch.object(qemu, "QEMU", "missing-qemu-for-test"):
            result = await qemu.observe(self.elf)
        self.assertEqual(result["execution_status"], "infrastructure_error")
        self.assertIn("missing-qemu-for-test", result["message"])
        self.assertIn("QEMU_PATH", result["message"])
