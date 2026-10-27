"""Force the stale-version interleaving and verify whole-chain atomicity."""

import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from threading import Event, current_thread
from unittest.mock import patch

from acquisition.adapters.sqlite.database import Database, SCHEMA, DAY_TWO
from acquisition.contracts import canonical, digest


class DatabaseInitializationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def seed(self, path, version):
        if version:
            with closing(sqlite3.connect(path)) as db, db:
                db.executescript(SCHEMA)

    def assert_reopenable(self, path):
        for _ in range(3):
            db = Database(path)
            with db.connect() as connection:
                self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 6)
                self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertIsNotNone(connection.execute("SELECT name FROM sqlite_master WHERE name='legacy_task_admissions'").fetchone())

    def test_forced_stale_version_interleaving_cannot_downgrade_the_database(self):
        for version in (0, 1):
            with self.subTest(version=version):
                path = self.root / f"controlled-{version}.sqlite"
                self.seed(path, version)
                first_read, second_attempt, first_finished = Event(), Event(), Event()
                original_connect = sqlite3.connect
                observations = []
                class VersionResult:
                    def __init__(self, row):
                        self.row = row
                    def fetchone(self):
                        return self.row
                class ControlledConnection(sqlite3.Connection):
                    seen_version = False
                    def execute(connection, sql, *args, **kwargs):
                        name = current_thread().name
                        if name == "second" and sql.strip().upper() == "BEGIN IMMEDIATE":
                            second_attempt.set()
                        result = super().execute(sql, *args, **kwargs)
                        if sql.strip().lower() == "pragma user_version" and not connection.seen_version:
                            connection.seen_version = True
                            row = result.fetchone()  # Finish the read before waiting; do not hold a stale read cursor.
                            locked = connection.in_transaction
                            observations.append((name, locked, row[0]))
                            if name == "first":
                                first_read.set()
                                if not second_attempt.wait(5):
                                    raise TimeoutError("Second initializer did not reach the boundary")
                            elif name == "second" and not locked:
                                second_attempt.set()
                                if not first_finished.wait(5):
                                    raise TimeoutError("First initializer did not finish")
                            return VersionResult(row)
                        return result
                def connect(*args, **kwargs):
                    return original_connect(*args, factory=ControlledConnection, **kwargs)
                def initialize(name):
                    current_thread().name = name
                    try:
                        Database(path)
                    finally:
                        if name == "first":
                            first_finished.set()
                with patch("acquisition.adapters.sqlite.database.sqlite3.connect", side_effect=connect):
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        first = pool.submit(initialize, "first")
                        self.assertTrue(first_read.wait(5))
                        second = pool.submit(initialize, "second")
                        first.result(timeout=15)
                        second.result(timeout=15)
                self.assertCountEqual(observations, [("first", True, version), ("second", True, 6)])
                self.assert_reopenable(path)

    def test_two_processes_can_initialize_versions_zero_and_one(self):
        environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
        code = "import sys; from acquisition.adapters.sqlite.database import Database; sys.stdin.readline(); Database(sys.argv[1])"
        for version in (0, 1):
            with self.subTest(version=version):
                path = self.root / f"process-{version}.sqlite"
                self.seed(path, version)
                children = [subprocess.Popen([sys.executable, "-c", code, str(path)], env=environment,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
                try:
                    for child in children:
                        child.stdin.write("start\n")
                        child.stdin.flush()
                    for child in children:
                        _, error = child.communicate(timeout=15)
                        self.assertEqual(child.returncode, 0, error)
                finally:
                    for child in children:
                        if child.poll() is None:
                            child.kill()
                            child.communicate()
                self.assert_reopenable(path)

    def test_failure_rolls_back_all_migration_steps_and_version_changes(self):
        for version in (0, 1):
            with self.subTest(version=version):
                path = self.root / f"rollback-{version}.sqlite"
                self.seed(path, version)
                with patch.object(Database, "_freeze_legacy_admissions", side_effect=OSError("injected migration failure")):
                    with self.assertRaises(OSError):
                        Database(path)
                with closing(sqlite3.connect(path)) as db, db:
                    self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], version)
                    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                    self.assertNotIn("model_calls", tables)
                    self.assertNotIn("legacy_task_admissions", tables)
                    self.assertEqual("runs" in tables, version == 1)
                self.assert_reopenable(path)

    def test_old_race_damage_is_repaired_without_refreshing_legacy_admissions(self):
        path = self.root / "stale-marker.sqlite"
        spec = {"capability": "fixture", "inputs": {}, "max_attempts": 3}
        with closing(sqlite3.connect(path)) as db, db:
            db.executescript(SCHEMA)
            db.executescript(DAY_TWO)
            db.execute("INSERT INTO runs VALUES('original','one','old',?,'queued',0)", (digest([spec]),))
            db.execute("""INSERT INTO tasks(id,run_id,position,capability,inputs,status,max_attempts,available_at)
                VALUES('original-task','original',0,'fixture',?,'queued',3,0)""", (canonical({}),))
        Database(path)
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("INSERT INTO conversations VALUES('one','conversation','request','Saved',1,0)")
            db.execute("INSERT INTO conversation_messages VALUES('one','conversation','message',1,'Preserved objective',0)")
            db.execute("PRAGMA user_version=2")
            db.execute("INSERT INTO runs VALUES('later','one','new',?,'queued',0)", (digest([spec]),))
            db.execute("""INSERT INTO tasks(id,run_id,position,capability,inputs,status,max_attempts,available_at)
                VALUES('later-task','later',0,'fixture',?,'queued',3,0)""", (canonical({}),))
        self.assert_reopenable(path)
        with closing(sqlite3.connect(path)) as db, db:
            self.assertEqual(db.execute("SELECT run_id FROM legacy_task_admissions").fetchall(), [("original",)])
            self.assertEqual(db.execute("SELECT content FROM conversation_messages").fetchall(), [("Preserved objective",)])

    def test_busy_wal_activation_is_retried_without_repeating_migrations(self):
        path = self.root / "busy-wal.sqlite"
        original_connect = sqlite3.connect
        attempts, versions = [], []
        class BusyOnce(sqlite3.Connection):
            def execute(connection, sql, *args, **kwargs):
                command = sql.strip().rstrip(";").upper()
                if command.startswith("PRAGMA USER_VERSION="):
                    versions.append(command)
                if command == "PRAGMA JOURNAL_MODE=WAL":
                    attempts.append(command)
                    if len(attempts) == 1:
                        error = sqlite3.OperationalError("database is locked")
                        error.sqlite_errorcode = sqlite3.SQLITE_BUSY
                        raise error
                return super().execute(sql, *args, **kwargs)
        def connect(*args, **kwargs):
            return original_connect(*args, factory=BusyOnce, **kwargs)
        with patch("acquisition.adapters.sqlite.database.sqlite3.connect", side_effect=connect), \
             patch("acquisition.adapters.sqlite.database.time.sleep") as sleep:
            Database(path)
        self.assertEqual(len(attempts), 2)
        self.assertEqual(sleep.call_count, 1)
        self.assertEqual(versions, ["PRAGMA USER_VERSION=1", "PRAGMA USER_VERSION=2", "PRAGMA USER_VERSION=3", "PRAGMA USER_VERSION=4", "PRAGMA USER_VERSION=5", "PRAGMA USER_VERSION=6"])
        self.assert_reopenable(path)

    def test_wal_retry_is_bounded_and_does_not_hide_other_sqlite_errors(self):
        original_connect = sqlite3.connect
        for code in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_IOERR):
            with self.subTest(code=code):
                path = self.root / f"wal-error-{code}.sqlite"
                attempts = []
                class JournalError(sqlite3.Connection):
                    def execute(connection, sql, *args, **kwargs):
                        if sql.strip().upper() == "PRAGMA JOURNAL_MODE=WAL":
                            attempts.append(sql)
                            error = sqlite3.OperationalError("fixture journal failure")
                            error.sqlite_errorcode = code
                            raise error
                        return super().execute(sql, *args, **kwargs)
                def connect(*args, **kwargs):
                    return original_connect(*args, factory=JournalError, **kwargs)
                with patch("acquisition.adapters.sqlite.database.sqlite3.connect", side_effect=connect), \
                     patch("acquisition.adapters.sqlite.database.time.monotonic", side_effect=[0, 11]), \
                     patch("acquisition.adapters.sqlite.database.time.sleep") as sleep:
                    with self.assertRaises(sqlite3.OperationalError):
                        Database(path)
                self.assertEqual(len(attempts), 1)
                sleep.assert_not_called()
                self.assert_reopenable(path)
