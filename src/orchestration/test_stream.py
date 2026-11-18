"""Real HTTP checks for incremental delivery, cancellation, and single-run access.

No model API calls. A local Uvicorn server runs the same FastAPI app.
"""
import asyncio
import json
import os
import socket
import threading
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx
import uvicorn

from . import main


class StreamTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.socket = socket.socket()
        cls.socket.bind(('127.0.0.1', 0))
        cls.url = f'http://127.0.0.1:{cls.socket.getsockname()[1]}'
        cls.server = uvicorn.Server(uvicorn.Config(main.app, log_level='error', lifespan='off'))
        cls.thread = threading.Thread(target=cls.server.run, kwargs={'sockets': [cls.socket]}, daemon=True)
        cls.thread.start()
        deadline = time.monotonic() + 5
        while not cls.server.started:
            if time.monotonic() > deadline:
                raise RuntimeError('Test server failed to start')
            time.sleep(0.01)

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.thread.join(timeout=5)
        cls.socket.close()

    def setUp(self):
        self.client = httpx.Client(base_url=self.url, timeout=5, trust_env=False)
        self.addCleanup(self.client.close)
        environment = patch.dict(os.environ, {'GOOGLE_API_KEY': 'offline-key'})
        environment.start()
        self.addCleanup(environment.stop)

    def test_incremental_delivery_and_conflicting_request(self):
        release = threading.Event()
        run_id = str(uuid4())

        async def agent(request, emit=None, run_id=None):
            emit({'type': 'log', 'run_id': run_id, 'timestamp': '2026-11-17T00:00:00Z',
                  'source': 'Agent', 'message': 'First model request'})
            while not release.is_set():
                await asyncio.sleep(0.01)
            return {'session_id': run_id, 'model': 'offline', 'workspace': '/tmp', 'final_response': 'Hello'}

        with patch.object(main, 'run_agent_loop', agent):
            with self.client.stream('POST', f'/tasks/stream?run_id={run_id}', json={'task': 'Hello'}) as response:
                self.assertEqual(response.status_code, 200)
                lines = response.iter_lines()
                # This arrives while the producer is deliberately blocked.
                first = json.loads(next(lines))
                self.assertEqual(first['message'], 'First model request')
                conflict = self.client.post('/tasks', json={'task': 'Second request'})
                self.assertEqual(conflict.status_code, 409)
                release.set()
                self.assertEqual(json.loads(next(lines))['result']['final_response'], 'Hello')

    def test_stop_waits_for_cleanup_and_next_run_can_start(self):
        cleaned = threading.Event()
        run_id = str(uuid4())

        async def agent(request, emit=None, run_id=None):
            try:
                emit({'type': 'log', 'run_id': run_id, 'timestamp': '2026-11-17T00:00:00Z',
                      'source': 'QEMU', 'message': 'Observing'})
                await asyncio.sleep(60)
            finally:
                await asyncio.sleep(0.03)
                cleaned.set()

        with patch.object(main, 'run_agent_loop', agent):
            with self.client.stream('POST', f'/tasks/stream?run_id={run_id}', json={'task': 'Observe'}) as response:
                lines = response.iter_lines()
                self.assertEqual(json.loads(next(lines))['message'], 'Observing')
                stopped = self.client.post(f'/tasks/{run_id}/stop')
                self.assertEqual(stopped.status_code, 200)
                self.assertTrue(cleaned.is_set())
                self.assertIn('Run stopped', json.loads(next(lines))['message'])
            self.assertTrue(main.active_run.done())
            self.assertEqual(self.client.post(f'/tasks/{run_id}/stop').status_code, 404)

    def test_disconnect_cancels_backend_task(self):
        cleaned = threading.Event()
        run_id = str(uuid4())

        async def agent(request, emit=None, run_id=None):
            try:
                emit({'type': 'log', 'run_id': run_id, 'timestamp': '2026-11-17T00:00:00Z',
                      'source': 'Agent', 'message': 'Waiting'})
                await asyncio.sleep(60)
            finally:
                await asyncio.sleep(0.03)
                cleaned.set()

        with patch.object(main, 'run_agent_loop', agent):
            with self.client.stream('POST', f'/tasks/stream?run_id={run_id}', json={'task': 'Hello'}) as response:
                self.assertEqual(json.loads(next(response.iter_lines()))['message'], 'Waiting')
            self.assertTrue(cleaned.wait(timeout=3), 'Disconnect did not clean up the active run')
            self.assertTrue(main.active_run.done())
