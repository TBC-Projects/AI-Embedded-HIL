"""Contract smoke tests: python -m unittest src.orchestration.test_api."""

import unittest

from fastapi.testclient import TestClient

from src.orchestration.main import TaskRequest, app, run_agent_loop


class ApiTests(unittest.TestCase):
    def test_health(self):
        with TestClient(app) as client:
            response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_task_not_implemented(self):
        with TestClient(app) as client:
            response = client.post("/tasks", json={"task": "Send Hello over UART"})
        self.assertEqual(response.status_code, 501)
        self.assertIn("not implemented", response.json()["detail"])

    def test_invalid_task(self):
        with TestClient(app) as client:
            for body in ({}, {"task": ""}, {"task": "  "}):
                self.assertEqual(client.post("/tasks", json=body).status_code, 422)

    def test_agent_placeholder(self):
        with self.assertRaises(NotImplementedError):
            run_agent_loop(TaskRequest(task="example"))
