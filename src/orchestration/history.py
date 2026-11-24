"""SQLite storage for the chat list, submitted turns, and visible activity logs.

ADK stores its own session/event tables in the same database. These tables only
hold what the dashboard needs; they do not expose ADK's internal model events.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import uuid4


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ChatStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS chats (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chat_runs (
                    id TEXT PRIMARY KEY, chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
                    task TEXT NOT NULL, created_at TEXT NOT NULL, outcome TEXT NOT NULL,
                    result TEXT
                );
                CREATE TABLE IF NOT EXISTS run_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL REFERENCES chat_runs(id) ON DELETE CASCADE,
                    event TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS chat_runs_by_chat ON chat_runs(chat_id);
                CREATE INDEX IF NOT EXISTS run_logs_by_run ON run_logs(run_id);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def create_chat(self) -> dict:
        chat = {'id': str(uuid4()), 'title': 'New conversation', 'created_at': now(), 'updated_at': now()}
        with self.connect() as db:
            db.execute('INSERT INTO chats VALUES (:id, :title, :created_at, :updated_at)', chat)
        return chat

    def list_chats(self) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute('SELECT * FROM chats ORDER BY updated_at DESC, id')]

    def get_chat(self, chat_id: str) -> dict | None:
        with self.connect() as db:
            row = db.execute('SELECT * FROM chats WHERE id=?', (chat_id,)).fetchone()
            if row is None:
                return None
            chat = dict(row)
            chat['runs'] = []
            for row in db.execute('SELECT * FROM chat_runs WHERE chat_id=? ORDER BY created_at, id', (chat_id,)):
                run = dict(row)
                run['run_id'] = run.pop('id')
                run['result'] = json.loads(run['result']) if run['result'] else None
                run['logs'] = [json.loads(log['event']) for log in db.execute(
                    'SELECT event FROM run_logs WHERE run_id=? ORDER BY id', (run['run_id'],),
                )]
                chat['runs'].append(run)
            return chat

    def start_run(self, chat_id: str, run_id: str, task: str):
        stamp = now()
        with self.connect() as db:
            db.execute('INSERT INTO chat_runs VALUES (?, ?, ?, ?, ?, NULL)',
                       (run_id, chat_id, task, stamp, 'running'))
            db.execute("UPDATE chats SET title=CASE WHEN title='New conversation' THEN ? ELSE title END, updated_at=? WHERE id=?",
                       (' '.join(task.split())[:65], stamp, chat_id))

    def append_log(self, event: dict) -> dict:
        with self.connect() as db:
            cursor = db.execute('INSERT INTO run_logs(run_id, event) VALUES (?, ?)',
                                (event['run_id'], json.dumps(event)))
            event = {**event, 'id': cursor.lastrowid}
            db.execute('UPDATE run_logs SET event=? WHERE id=?', (json.dumps(event), event['id']))
        return event

    def finish_run(self, run_id: str, outcome: str, result=None):
        with self.connect() as db:
            db.execute('UPDATE chat_runs SET outcome=?, result=? WHERE id=?',
                       (outcome, json.dumps(result) if result is not None else None, run_id))
            db.execute('UPDATE chats SET updated_at=? WHERE id=(SELECT chat_id FROM chat_runs WHERE id=?)',
                       (now(), run_id))

    def recover_interrupted(self):
        # Agent tasks cannot resume after a server restart; preserve and explain the log.
        with self.connect() as db:
            interrupted = list(db.execute("SELECT id, chat_id FROM chat_runs WHERE outcome='running'"))
        for run in interrupted:
            self.append_log({'type': 'log', 'run_id': run['id'], 'chat_id': run['chat_id'],
                             'timestamp': now(), 'source': 'Backend',
                             'message': 'Backend restarted before this run finished. You can send a follow-up.'})
            self.finish_run(run['id'], 'interrupted')

    def delete_chat(self, chat_id: str):
        with self.connect() as db:
            db.execute('DELETE FROM chats WHERE id=?', (chat_id,))
