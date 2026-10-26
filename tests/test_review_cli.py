import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from acquisition.adapters.sqlite.database import Database, SCHEMA, DAY_TWO, DAY_THREE
from acquisition.contracts import digest, canonical
from unittest.mock import patch


class ReviewCliTests(unittest.TestCase):
    def test_scripted_journey_and_replay_survive_real_process_restart(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "day-three.sqlite"
            env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
            # A process-local injected clock keeps the CLI test independent of
            # the host date without adding a backdating option to the product.
            wrapper = "from acquisition import __main__ as c; from acquisition.bootstrap import build; c.build=lambda path,**kw:build(path,clock=lambda:1792972800,**kw); c.main()"
            def cli(*args):
                result = subprocess.run([sys.executable, "-c", wrapper, "--db", str(path), *args],
                    env=env, text=True, capture_output=True, check=True)
                return json.loads(result.stdout)
            first = cli("demo-review", "--out", str(root / "report"))
            second = cli("demo-review", "--out", str(root / "report"))
            self.assertEqual(first["receipt"], second["receipt"])
            self.assertTrue(second["already_completed"])
            self.assertTrue(first["replay_same_receipt"])
            self.assertEqual(first["changes"]["removed_count"], 1)
            report = Path(first["review_html"]).read_text()
            self.assertIn("Accepted by the local simulator", report)
            self.assertNotIn(chr(0x2014), report)
            self.assertTrue((Path(first["export_directory"]) / "mailing.csv").is_file())
            view = cli("--organization", first["organization"], "review-show", "--case", first["case_id"])
            self.assertTrue(view["approval_valid"])
            self.assertEqual(len(view["revisions"]), 2)
            with Database(path).connect() as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM simulated_agency_jobs").fetchone()[0], 1)

    def test_completed_demo_replays_on_a_later_calendar_day(self):
        from acquisition.bootstrap import build
        from acquisition.review_demo import run_review_demo
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "demo.sqlite"
            now = 1792972800.0
            app = build(path, clock=lambda: now)
            first = run_review_demo(app, "one", "calendar", root / "report", str(path))
            now += 172800
            reopened = build(path, clock=lambda: now)
            replay = run_review_demo(reopened, "one", "calendar", root / "report", str(path))
            self.assertEqual(first["receipt"], replay["receipt"])
            self.assertTrue(replay["already_completed"])
            view = reopened.reviews.store.view(first["organization"], first["case_id"])
            self.assertFalse(view["approval_valid"])
            self.assertEqual(len(view["revisions"]), 2)

    def test_schema_three_upgrade_preserves_the_legacy_admission_cutoff(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "old.sqlite"
            db = sqlite3.connect(path, isolation_level=None)
            db.row_factory = sqlite3.Row
            try:
                db.executescript(SCHEMA)
                db.executescript(DAY_TWO)
                plan_hash = digest([{"capability": "fixture", "inputs": {}, "max_attempts": 3}])
                db.execute("INSERT INTO runs VALUES('original','one','old',?,'queued',0)", (plan_hash,))
                db.execute("""INSERT INTO tasks(id,run_id,position,capability,inputs,status,max_attempts,available_at)
                    VALUES('original-task','original',0,'fixture',?,'queued',3,0)""", (canonical({}),))
                db.execute("BEGIN IMMEDIATE")
                Database._freeze_legacy_admissions(db)
                db.commit()
                db.execute("INSERT INTO runs VALUES('later','one','new',?,'queued',0)", (plan_hash,))
                db.execute("""INSERT INTO tasks(id,run_id,position,capability,inputs,status,max_attempts,available_at)
                    VALUES('later-task','later',0,'fixture',?,'queued',3,0)""", (canonical({}),))
                old = [tuple(r) for r in db.execute("SELECT * FROM legacy_task_admissions")]
            finally:
                db.close()
            migrated = Database(path)
            with migrated.connect() as db:
                self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 4)
                self.assertEqual([tuple(r) for r in db.execute("SELECT * FROM legacy_task_admissions")], old)
                self.assertEqual(db.execute("SELECT status FROM runs WHERE id='later'").fetchone()[0], "queued")

    def test_review_migration_failure_is_atomic_and_retryable(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "old.sqlite"
            db = sqlite3.connect(path, isolation_level=None)
            try:
                db.executescript(SCHEMA)
                db.executescript(DAY_TWO)
                db.execute("BEGIN IMMEDIATE")
                Database._freeze_legacy_admissions(db)
                db.commit()
            finally:
                db.close()
            original = Database._apply_migration
            def fail(connection, script):
                if script == DAY_THREE:
                    connection.execute("CREATE TABLE review_actors(fixture TEXT)")
                    raise OSError("Injected review migration failure")
                return original(connection, script)
            with patch.object(Database, "_apply_migration", side_effect=fail):
                with self.assertRaises(OSError):
                    Database(path)
            db = sqlite3.connect(path)
            try:
                self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 3)
                self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='review_actors'").fetchone())
            finally:
                db.close()
            Database(path)
