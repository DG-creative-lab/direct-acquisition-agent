"""Review regressions: incompatible workers, pre-migration authority and time."""

import json
import sqlite3
import tempfile
import unittest
from dataclasses import asdict, replace
from pathlib import Path

from acquisition.adapters.sqlite.database import SCHEMA, DAY_TWO, Database
from acquisition.adapters.synthetic import generate
from acquisition.bootstrap import build
from acquisition.campaigns import Brief
from acquisition.contracts import Conflict, canonical, digest
from acquisition.reasoning import ModelConfig
from acquisition.runtime import TaskSpec
from test_model_copy import FakeModel


class ReviewRegressions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = 1792886400.0
        self.config = ModelConfig("test/model", max_calls=10)

    def app(self, name="state", model=None, config=None):
        return build(self.root / (name + ".sqlite"), lambda: self.now, model, config)

    def test_incompatible_workers_do_not_claim_consume_attempts_or_fail_a_run(self):
        model = FakeModel()
        original = self.app(model=model, config=self.config)
        run = original.start_model("one", "resumable", size=100)
        before = original.tasks.inspect("one", run)
        for config in (None, replace(self.config, model="wrong/model"), replace(self.config, max_calls=9),
                       replace(self.config, force_tool_choice=True)):
            worker = self.app(model=FakeModel() if config else None, config=config)
            for _ in range(4):
                self.assertEqual(worker.worker.drain("one"), 0)
            self.assertEqual(worker.tasks.inspect("one", run), before)
        original.worker.drain("one")
        self.assertEqual(original.tasks.inspect("one", run)["run"]["status"], "waiting")
        self.assertEqual(len(model.requests), 6)

    def test_partial_progress_and_expired_lease_are_preserved_for_the_right_worker(self):
        model = FakeModel()
        app = self.app(model=model, config=self.config)
        run = app.start_model("one", "partial", size=100)
        app.worker.drain("one", 2)
        app.tasks.claim("one", self.now, 1)
        self.now += 2
        before = app.tasks.inspect("one", run)
        offline = self.app()
        self.assertFalse(offline.worker.tick("one"))
        self.assertEqual(offline.tasks.inspect("one", run), before)
        app.worker.drain("one")
        self.assertEqual(app.tasks.inspect("one", run)["run"]["status"], "waiting")
        self.assertEqual(len(model.requests), 6)

    def test_incompatible_model_run_does_not_starve_compatible_offline_work(self):
        app = self.app(model=FakeModel(), config=self.config)
        model_run = app.start_model("one", "model", size=100)
        offline_run = app.start("one", "offline", size=100)
        offline = self.app()
        self.assertEqual(offline.worker.drain("one"), 3)
        self.assertEqual(offline.tasks.inspect("one", offline_run)["run"]["status"], "waiting")
        state = offline.tasks.inspect("one", model_run)
        self.assertEqual(state["run"]["status"], "queued")
        self.assertTrue(all(t["attempts"] == 0 for t in state["tasks"]))

    def test_cli_create_then_unconfigured_work_stays_resumable(self):
        from acquisition.__main__ import main
        from contextlib import redirect_stdout
        from io import StringIO
        from unittest.mock import patch
        model = FakeModel()
        path = str(self.root / "cli.sqlite")
        def cli(*args):
            with patch("sys.argv", ["acquisition", "--db", path, *args]), redirect_stdout(StringIO()) as output:
                main()
            return json.loads(output.getvalue())
        with patch("acquisition.__main__.OpenRouter", return_value=model), \
             patch("acquisition.__main__.openrouter_key", return_value="fixture-not-a-key"), \
             patch("acquisition.__main__.build", side_effect=lambda path, **kwargs: build(path, clock=lambda: self.now, **kwargs)):
            run = cli("create-model", "--size", "100")["run_id"]
            self.assertEqual(cli("work")["worker_ticks"], 0)
            state = cli("status", "--run", run)
            self.assertEqual(state["run"]["status"], "queued")
            self.assertTrue(all(t["attempts"] == 0 for t in state["tasks"]))
            self.assertEqual(cli("--model", "openai/gpt-oss-120b", "work")["worker_ticks"], 5)
            self.assertEqual(cli("status", "--run", run)["run"]["status"], "waiting")
        self.assertEqual(len(model.requests), 6)

    def legacy_fixture(self):
        """Write actual schema-v2 rows before the current application opens the DB."""
        path = self.root / "legacy.sqlite"
        config = ModelConfig("test/model")
        snapshot = generate("one", 100)
        guidance = json.loads((Path(__file__).resolve().parents[1] / "config/editorial-v2.json").read_text())
        contexts = {}
        with sqlite3.connect(path) as db:
            db.executescript(SCHEMA)
            db.executescript(DAY_TWO)
            db.execute("INSERT INTO audiences VALUES(?,?,?)", ("one", snapshot.id, canonical(asdict(snapshot))))
            for segment in ("inventory", "contractors"):
                context = {"segment": segment, "guidance": guidance, "memory": [{"id": "legacy-memory"}],
                           "audience_summary": {"mode": "synthetic"}}
                identity = "context_" + digest({"organization": "one", **context})
                contexts[segment] = identity
                db.execute("INSERT INTO creative_contexts VALUES(?,?,?)", ("one", identity, canonical(context)))
            shared = {"snapshot_id": snapshot.id, "brief": asdict(Brief("legacy")), "workflow_version": "monthly-mail/v2",
                      "context_ids": contexts, "model_config": asdict(config)}
            specs = [TaskSpec("audiences.inspect_model.v2", shared)] + [
                TaskSpec("creative.generate.v2", shared | {"segment": segment}) for segment in sorted(contexts)
            ] + [TaskSpec("campaigns.build_model_draft.v2", shared), TaskSpec("campaigns.model_review_checkpoint.v2", shared, 5)]
            db.execute("INSERT INTO runs VALUES(?,?,?,?,?,?)", ("legacy-run", "one", "legacy", digest([asdict(s) for s in specs]), "queued", self.now))
            for i, spec in enumerate(specs):
                db.execute("""INSERT INTO tasks(id,run_id,position,capability,inputs,status,max_attempts,available_at)
                    VALUES(?, 'legacy-run', ?, ?, ?, 'queued', ?, ?)""",
                    (f"legacy-task-{i}", i, spec.capability, canonical(spec.inputs), spec.max_attempts, self.now))
        return path, config, specs

    def test_real_pre_migration_v2_rows_resume_but_cannot_authorize_a_new_run(self):
        path, config, specs = self.legacy_fixture()
        model = FakeModel()
        app = build(path, lambda: self.now, model, config)
        self.assertEqual(app.tasks.create("one", "legacy", specs, self.now), "legacy-run")
        with self.assertRaises(ValueError):
            app.tasks.create("one", "new-legacy", specs, self.now)
        app.worker.drain("one")
        state = app.tasks.inspect("one", "legacy-run")
        self.assertEqual(state["run"]["status"], "waiting")
        self.assertEqual(len(model.requests), 4)
        draft = app.drafts.get("one", state["tasks"][-1]["output"]["draft_id"])
        self.assertTrue(all("fact_pack_id" not in item for item in draft.manifest["creatives"]))
        reopened = build(path, lambda: self.now, model, config)
        self.assertEqual(reopened.tasks.create("one", "legacy", specs, self.now), "legacy-run")

    def test_legacy_migration_failure_rolls_back_the_cutoff_and_can_be_retried(self):
        from unittest.mock import patch
        path, config, _ = self.legacy_fixture()
        with patch("acquisition.adapters.sqlite.database.stored_plan_hash", side_effect=OSError("fixture migration failure")):
            with self.assertRaises(OSError):
                build(path, lambda: self.now)
        with sqlite3.connect(path) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 2)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='legacy_task_admissions'").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT status FROM runs WHERE id='legacy-run'").fetchone()[0], "queued")
        app = build(path, lambda: self.now, FakeModel(), config)
        app.worker.drain("one")
        self.assertEqual(app.tasks.inspect("one", "legacy-run")["run"]["status"], "waiting")

    def test_restart_does_not_grandfather_post_migration_v2_rows(self):
        path, config, specs = self.legacy_fixture()
        build(path, lambda: self.now)
        # Simulate an alternate writer after the migration boundary. Merely
        # persisting matching v2 JSON must not create compatibility authority.
        with sqlite3.connect(path) as db:
            db.execute("INSERT INTO runs VALUES(?,?,?,?,?,?)", ("new-run", "two", "new", digest([asdict(specs[0])]), "queued", self.now))
            db.execute("""INSERT INTO tasks(id,run_id,position,capability,inputs,status,max_attempts,available_at)
                VALUES('new-task','new-run',0,?,?,'queued',3,?)""", (specs[0].capability, canonical(specs[0].inputs), self.now))
        app = build(path, lambda: self.now, FakeModel(), config)
        with self.assertRaises(Conflict):
            app.worker.tick("two")
        state = app.tasks.inspect("two", "new-run")
        self.assertEqual(state["tasks"][0]["attempts"], 0)
        self.assertEqual(state["run"]["status"], "queued")

    def test_legacy_certificate_binds_original_plan_even_after_coordinated_rewrite(self):
        path, config, specs = self.legacy_fixture()
        build(path, lambda: self.now)
        rewritten = [replace(s, inputs=s.inputs | {"brief": asdict(Brief("different"))}) for s in specs]
        with sqlite3.connect(path) as db:
            for i, spec in enumerate(rewritten):
                db.execute("UPDATE tasks SET inputs=? WHERE id=?", (canonical(spec.inputs), f"legacy-task-{i}"))
            db.execute("UPDATE runs SET request_hash=? WHERE id='legacy-run'", (digest([asdict(s) for s in rewritten]),))
        app = build(path, lambda: self.now, FakeModel(), config)
        with self.assertRaises(Conflict):
            app.worker.tick("one")
        self.assertEqual(app.tasks.inspect("one", "legacy-run")["tasks"][0]["attempts"], 0)

    def test_nonfinite_creation_acknowledgement_and_cancellation_are_atomic(self):
        app = self.app()
        for bad in (float("inf"), float("-inf"), float("nan")):
            with self.assertRaises(ValueError):
                app.tasks.create("one", "bad", [TaskSpec("test", {})], bad)
        with Database(self.root / "state.sqlite").connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM runs").fetchone()[0], 0)
        run = app.start("one", "valid", size=100)
        app.worker.drain("one")
        before = app.tasks.inspect("one", run)
        reference = before["tasks"][-1]["output"]["reference"]
        for bad in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(ValueError):
                app.tasks.acknowledge("one", run, reference, bad)
            with self.assertRaises(ValueError):
                app.tasks.cancel("one", run, bad)
            self.assertEqual(app.tasks.inspect("one", run), before)
        app.tasks.acknowledge("one", run, reference, self.now)
        app.worker.drain("one")
        self.assertEqual(app.tasks.inspect("one", run)["run"]["status"], "succeeded")

    def test_overflowing_lease_expiry_is_rejected_before_any_state_change(self):
        app = self.app()
        run = app.start("one", "clock", size=100)
        before = app.tasks.inspect("one", run)
        with self.assertRaises(ValueError):
            app.tasks.claim("one", 1e308, 1e308)
        self.assertEqual(app.tasks.inspect("one", run), before)
