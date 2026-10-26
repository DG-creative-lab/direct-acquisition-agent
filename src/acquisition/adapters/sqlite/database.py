import sqlite3
from contextlib import contextmanager
from pathlib import Path


SCHEMA = """
BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS runs (
 id TEXT PRIMARY KEY, organization TEXT NOT NULL, request_id TEXT NOT NULL,
 request_hash TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN
 ('queued','running','waiting','succeeded','failed','cancelled')),
 created_at REAL NOT NULL, UNIQUE(organization,request_id));
CREATE TABLE IF NOT EXISTS tasks (
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id), position INTEGER NOT NULL,
 capability TEXT NOT NULL, inputs TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN
 ('queued','running','waiting','succeeded','failed','cancelled')),
 attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL,
 available_at REAL NOT NULL, lease_until REAL, token TEXT, output TEXT, resume TEXT,
 UNIQUE(run_id,position));
CREATE INDEX IF NOT EXISTS tasks_ready ON tasks(status,available_at);
CREATE TABLE IF NOT EXISTS events (
 sequence INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL REFERENCES runs(id),
 task_id TEXT, kind TEXT NOT NULL, data TEXT NOT NULL, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS audiences (
 organization TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(organization,id));
CREATE TABLE IF NOT EXISTS drafts (
 organization TEXT NOT NULL, id TEXT NOT NULL, manifest TEXT NOT NULL,
 mailing TEXT NOT NULL, assignments TEXT NOT NULL, PRIMARY KEY(organization,id));
CREATE TABLE IF NOT EXISTS draft_operations (
 organization TEXT NOT NULL, operation_id TEXT NOT NULL, draft_id TEXT NOT NULL,
 PRIMARY KEY(organization,operation_id),
 FOREIGN KEY(organization,draft_id) REFERENCES drafts(organization,id));
PRAGMA user_version=1;
COMMIT;
"""

DAY_TWO = """
BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS editorial_memories (
 organization TEXT NOT NULL, id TEXT NOT NULL, segment TEXT NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(organization,id));
CREATE TABLE IF NOT EXISTS creative_contexts (
 organization TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(organization,id));
CREATE TABLE IF NOT EXISTS generated_catalogues (
 organization TEXT NOT NULL, operation_id TEXT NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(organization,operation_id));
CREATE TABLE IF NOT EXISTS model_calls (
 organization TEXT NOT NULL, run_id TEXT NOT NULL REFERENCES runs(id), call_key TEXT NOT NULL,
 task_id TEXT NOT NULL REFERENCES tasks(id), lease_token TEXT NOT NULL,
 request_hash TEXT NOT NULL, status TEXT NOT NULL, response TEXT, error TEXT,
 PRIMARY KEY(organization,run_id,call_key));
PRAGMA user_version=2;
COMMIT;
"""


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in {0, 1, 2}:
                raise ValueError(f"Unsupported database schema {version}")
            if version == 0:
                connection.executescript(SCHEMA)
            if version < 2:
                connection.executescript(DAY_TWO)
            connection.execute("PRAGMA journal_mode=WAL")

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self):
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
