"""Persistent conversation tests with real SQLite/ADK and an offline model."""
import asyncio
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from . import main
from .test_api import fake_file_model, MODEL_METHOD


def reply(text):
    async def generate(model, llm_request, stream=False):
        yield LlmResponse(content=types.Content(role='model', parts=[types.Part(text=text)]))
    return generate


def history_text(request):
    return '\n'.join(part.text for content in request.contents for part in content.parts or [] if part.text)


class HistoryTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        for name, value in [('DATA_DIR', self.root / 'data'), ('WORKSPACE_ROOT', self.root / 'workspace')]:
            patched = patch.object(main, name, value)
            patched.start()
            self.addCleanup(patched.stop)
        env = patch.dict('os.environ', {'GOOGLE_API_KEY': 'offline-history-key'})
        env.start()
        self.addCleanup(env.stop)
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close)

    def new_chat(self):
        response = self.client.post('/chats')
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()['id']

    def send(self, chat_id, text, model):
        with patch(MODEL_METHOD, model):
            return self.client.post('/tasks', json={'task': text, 'chat_id': chat_id})

    def test_history_survives_restart_and_reaches_next_model_turn(self):
        chat = self.new_chat()
        first = self.send(chat, 'Remember SILVER-HERON', reply('I remembered SILVER-HERON.'))
        self.assertEqual(first.status_code, 200, first.text)
        saved = self.client.get(f'/chats/{chat}').json()
        self.assertEqual(saved['runs'][0]['task'], 'Remember SILVER-HERON')
        self.assertTrue(saved['runs'][0]['logs'])
        self.assertEqual(saved['runs'][0]['result']['final_response'], 'I remembered SILVER-HERON.')
        self.assertEqual(first.json()['session_id'], chat)

        async def follow_up(model, llm_request, stream=False):
            text = history_text(llm_request)
            self.assertIn('Remember SILVER-HERON', text)
            self.assertIn('I remembered SILVER-HERON.', text)
            self.assertIn('What was the name?', text)
            async for event in reply('SILVER-HERON')(model, llm_request, stream):
                yield event

        # Drop the Python store object, as a new backend process would.
        with patch.object(main, 'chat_store', None):
            self.assertEqual(self.client.get(f'/chats/{chat}').json(), saved)
            second = self.send(chat, 'What was the name?', follow_up)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertNotEqual(first.json()['run_id'], second.json()['run_id'])
        self.assertEqual(first.json()['session_id'], second.json()['session_id'])
        self.assertEqual(len(self.client.get(f'/chats/{chat}').json()['runs']), 2)

    def test_new_chat_has_separate_context_but_can_read_shared_files(self):
        first_chat = self.new_chat()
        created = self.send(first_chat, 'Create a shared file', fake_file_model([
            ('WriteFile', {'path': 'shared/src/main.c', 'content': 'int main(void) { return 0; }'}),
        ]))
        self.assertEqual(created.status_code, 200, created.text)
        second_chat = self.new_chat()
        transport = fake_file_model([
            ('list_directory', {}), ('ReadFile', {'path': 'shared/src/main.c'}),
        ])

        async def inspect(model, llm_request, stream=False):
            self.assertNotIn('Create a shared file', history_text(llm_request))
            async for event in transport(model, llm_request, stream):
                yield event

        inspected = self.send(second_chat, 'Inspect existing source', inspect)
        self.assertEqual(inspected.status_code, 200, inspected.text)
        results = [event['result'] for event in inspected.json()['tool_events'] if event['type'] == 'tool_result']
        self.assertEqual(results[0]['entries'][0]['name'], 'shared')
        self.assertIn('return 0', results[1]['content'])
        self.assertEqual(created.json()['workspace'], inspected.json()['workspace'])

    def test_delete_removes_history_and_adk_session_but_keeps_files(self):
        chat = self.new_chat()
        response = self.send(chat, 'Save a file', fake_file_model([
            ('WriteFile', {'path': 'keep.c', 'content': 'keep me'}),
        ]))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.client.delete(f'/chats/{chat}').status_code, 200)
        self.assertEqual(self.client.get(f'/chats/{chat}').status_code, 404)
        self.assertEqual(self.client.get('/chats').json()['chats'], [])
        self.assertEqual((self.root / 'workspace/keep.c').read_text(), 'keep me')
        with sqlite3.connect(self.root / 'data/conversations.db') as db:
            for table in ('chats', 'chat_runs', 'run_logs', 'sessions', 'events'):
                self.assertEqual(db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0], 0)

    def test_error_and_redacted_logs_are_saved_without_fake_reply(self):
        chat = self.new_chat()

        async def broken(model, llm_request, stream=False):
            raise ConnectionError('private provider details')
            yield

        response = self.send(chat, 'Do something', broken)
        self.assertEqual(response.status_code, 502)
        saved = self.client.get(f'/chats/{chat}').json()['runs'][0]
        self.assertEqual(saved['outcome'], 'failed')
        self.assertIsNone(saved['result'])
        self.assertEqual(saved['logs'][-1]['source'], 'Error')
        self.assertNotIn('private provider details', json.dumps(saved))
        self.send(chat, 'My accidental key: offline-history-key', reply('Hello'))
        self.assertNotIn('offline-history-key', self.client.get(f'/chats/{chat}').text)

    def test_restart_marks_incomplete_turn_and_preserves_logs(self):
        store = main.get_store()
        chat = store.create_chat()['id']
        store.start_run(chat, 'unfinished', 'Interrupted task')
        store.append_log({'type': 'log', 'run_id': 'unfinished', 'source': 'Agent',
                          'timestamp': '2026-11-17T00:00:00Z', 'message': 'Starting'})
        with patch.object(main, 'chat_store', None):
            run = self.client.get(f'/chats/{chat}').json()['runs'][0]
        self.assertEqual(run['outcome'], 'interrupted')
        self.assertEqual(run['logs'][0]['message'], 'Starting')
        self.assertIn('Backend restarted', run['logs'][-1]['message'])

    def test_missing_chat_is_rejected(self):
        from uuid import uuid4
        response = self.client.post('/tasks', json={'task': 'Hello', 'chat_id': str(uuid4())})
        self.assertEqual(response.status_code, 404)

    def test_pending_tool_is_closed_before_followup(self):
        chat = self.new_chat()
        from google.adk.events import Event
        service = main.session_service()

        async def save_interrupted():
            session = await service.create_session(app_name=main.APP_NAME, user_id='local_user', session_id=chat)
            await service.append_event(session, Event(author='firmware_agent', invocation_id='interrupted',
                content=types.Content(role='model', parts=[types.Part(function_call=types.FunctionCall(
                    id='unfinished-call', name='compile_firmware', args={}))])))
        asyncio.run(save_interrupted())

        async def inspect(model, llm_request, stream=False):
            responses = [part.function_response for content in llm_request.contents
                         for part in content.parts or [] if part.function_response]
            self.assertEqual(responses[0].id, 'unfinished-call')
            self.assertEqual(responses[0].response['status'], 'interrupted')
            async for event in reply('I will inspect the files.')(model, llm_request, stream):
                yield event
        response = self.send(chat, 'Continue', inspect)
        self.assertEqual(response.status_code, 200, response.text)
