import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from acquisition.adapters.sqlite.database import Database, DAY_FOUR, CONVERSATIONS


class LearningCliTests(unittest.TestCase):
    def test_demo_and_reports_survive_separate_process_replay(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path, output = root / "learning.sqlite", root / "report"
            env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
            def cli(*args):
                result = subprocess.run([sys.executable, "-m", "acquisition", "--db", str(path), *args], env=env,
                    text=True, capture_output=True, check=True)
                return json.loads(result.stdout)
            first = cli("demo-learning", "--out", str(output))
            replay = cli("demo-learning", "--out", str(output))
            self.assertEqual(first["receipt"], replay["receipt"])
            self.assertEqual(first["mode"], "SIMULATED_CLOCK_SYNTHETIC_OUTCOMES")
            self.assertTrue(first["replay_same_receipt"])
            report = Path(first["learning_html"]).read_text()
            self.assertIn("No measured customer performance", report)
            self.assertNotIn(chr(0x2014), report)
            self.assertIn("observing", (output / "pending.html").read_text().lower())
            pending = cli("--organization", first["organization"], "learning-show", "--cohort", first["cohort_id"])
            self.assertEqual(pending["status"], "finalized")
            self.assertEqual(pending["missing"], 0)
            with Database(path).connect() as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM learning_beliefs").fetchone()[0], 6)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM learning_outcomes").fetchone()[0], 754)

    def test_schema_four_upgrade_preserves_review_and_legacy_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "old.sqlite"
            original = Database._apply_migration
            def skip_four(connection, script):
                if script not in {DAY_FOUR, CONVERSATIONS}:
                    original(connection, script)
            with patch.object(Database, "_apply_migration", side_effect=skip_four), patch.object(Database, "_validate_conversation_schema"):
                old = Database(path)
            with old.connect() as db:
                self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 4)
                db.execute("INSERT INTO review_actors VALUES('one','owner','[\"operator\"]',1,7)")
                cutoff = [tuple(r) for r in db.execute("SELECT * FROM legacy_task_admissions")]
            upgraded = Database(path)
            with upgraded.connect() as db:
                self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 6)
                self.assertEqual(db.execute("SELECT generation FROM review_actors").fetchone()[0], 7)
                self.assertEqual([tuple(r) for r in db.execute("SELECT * FROM legacy_task_admissions")], cutoff)

    def test_schema_five_migration_failure_rolls_back_and_can_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "old.sqlite"
            original = Database._apply_migration
            def skip(connection, script):
                if script not in {DAY_FOUR, CONVERSATIONS}:
                    original(connection, script)
            with patch.object(Database, "_apply_migration", side_effect=skip), patch.object(Database, "_validate_conversation_schema"):
                Database(path)
            def fail(connection, script):
                if script == DAY_FOUR:
                    connection.execute("CREATE TABLE learning_cohorts(fixture TEXT)")
                    connection.execute("PRAGMA user_version=5")
                    raise OSError("Injected migration failure")
                original(connection, script)
            with patch.object(Database, "_apply_migration", side_effect=fail), self.assertRaises(OSError):
                Database(path)
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 4)
                self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='learning_cohorts'").fetchone())
            with Database(path).connect() as db:
                self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 6)
