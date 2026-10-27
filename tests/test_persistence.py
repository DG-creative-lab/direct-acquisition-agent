import json
import hashlib
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from acquisition.adapters.sqlite.database import Database
from acquisition.adapters.sqlite.tasks import SqliteTasks
from acquisition.adapters.synthetic import generate
from acquisition.bootstrap import build
from acquisition.campaigns import Brief, build_draft
from acquisition.contracts import Conflict, NotFound
from acquisition.creative import fixture_catalog
from acquisition.runtime import LeaseLost, Outcome, RetryableError, TaskSpec, Worker


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "test.sqlite"
        self.now = 1000.0
        self.app = build(self.path, lambda: self.now)

    def task(self, specs=None, organization="one", request="request"):
        return self.app.tasks.create(organization, request, specs or [TaskSpec("test.v1", {})], self.now)

    def test_request_replay_binds_exact_inputs_even_after_restart(self):
        run = self.app.start("one", "same", size=100)
        reopened = build(self.path)
        self.assertEqual(reopened.start("one", "same", size=100), run)
        with self.assertRaises(Conflict):
            reopened.start("one", "same", size=101)
        self.assertEqual(len(reopened.tasks.inspect("one", run)["tasks"]), 3)

    def test_simultaneous_create_and_claim_have_one_winner(self):
        with ThreadPoolExecutor(2) as pool:
            runs = list(pool.map(lambda _: self.task(), range(2)))
        self.assertEqual(runs[0], runs[1])
        with ThreadPoolExecutor(2) as pool:
            claims = list(pool.map(lambda _: self.app.tasks.claim("one", self.now, 60), range(2)))
        self.assertEqual(sum(claim is not None for claim in claims), 1)
        self.assertEqual(self.app.tasks.inspect("one", runs[0])["tasks"][0]["attempts"], 1)

    def test_expired_attempt_cannot_commit_before_or_after_reclaim(self):
        run = self.task()
        first = self.app.tasks.claim("one", self.now, 60)
        self.now = 1060
        with self.assertRaises(LeaseLost):
            self.app.tasks.settle(first, Outcome("succeeded", {}), self.now)
        second = build(self.path).tasks.claim("one", self.now, 60)
        self.assertNotEqual(first.token, second.token)
        with self.assertRaises(LeaseLost):
            self.app.tasks.settle(first, Outcome("succeeded", {"wrong": True}), self.now)
        self.app.tasks.settle(second, Outcome("succeeded", {"correct": True}), self.now)
        state = self.app.tasks.inspect("one", run)
        self.assertEqual(state["run"]["status"], "succeeded")
        self.assertEqual(state["tasks"][0]["output"], {"correct": True})

    def test_targeted_worker_only_recovers_and_claims_the_requested_run(self):
        expired = self.task(request="expired")
        first = self.app.tasks.claim("one", self.now, 60, run_id=expired)
        queued = self.task(request="queued")
        completed = self.task(request="completed")
        worker = Worker(self.app.tasks, {"test.v1": lambda claim: Outcome("succeeded", {"run": claim.run_id})}, lambda: self.now)
        self.assertEqual(worker.drain("one", run_id=completed), 1)
        self.now += 61
        expired_before = self.app.tasks.inspect("one", expired)
        queued_before = self.app.tasks.inspect("one", queued)
        self.assertEqual(worker.drain("one", run_id=completed), 0)
        self.assertEqual(self.app.tasks.inspect("one", expired), expired_before)
        self.assertEqual(self.app.tasks.inspect("one", queued), queued_before)
        self.assertEqual(worker.drain("one", run_id=queued), 1)
        self.assertEqual(self.app.tasks.inspect("one", expired), expired_before)
        with self.assertRaises(NotFound):
            worker.drain("two", run_id=expired)
        self.assertEqual(worker.drain("one", run_id=expired), 1)
        self.assertEqual(self.app.tasks.inspect("one", expired)["tasks"][0]["attempts"], 2)
        with self.assertRaises(LeaseLost):
            self.app.tasks.settle(first, Outcome("succeeded", {}), self.now)

    def test_cancel_fences_a_running_worker_and_terminal_resurrection(self):
        run = self.task()
        claim = self.app.tasks.claim("one", self.now, 60)
        self.app.tasks.cancel("one", run, self.now)
        with self.assertRaises(LeaseLost):
            self.app.tasks.settle(claim, Outcome("succeeded", {}), self.now)
        with self.assertRaises(Conflict):
            self.app.tasks.acknowledge("one", run, "anything", self.now)
        self.assertIsNone(self.app.tasks.claim("one", self.now + 1000, 60))
        self.assertEqual(self.app.tasks.inspect("one", run)["run"]["status"], "cancelled")

    def test_scope_is_checked_on_every_public_persistence_boundary(self):
        run = self.app.start("one", "request", size=100)
        self.app.worker.drain("one")
        state = self.app.tasks.inspect("one", run)
        draft_id = state["tasks"][-1]["output"]["reference"]
        snapshot_id = state["tasks"][0]["inputs"]["snapshot_id"]
        for action in (
            lambda: self.app.tasks.inspect("two", run),
            lambda: self.app.tasks.cancel("two", run, self.now),
            lambda: self.app.tasks.acknowledge("two", run, draft_id, self.now),
            lambda: self.app.audiences.get("two", snapshot_id),
            lambda: self.app.drafts.get("two", draft_id),
            lambda: self.app.export("two", run, Path(self.temporary.name)),
        ):
            with self.assertRaises(NotFound):
                action()
        self.assertIsNone(self.app.tasks.claim("two", self.now, 60))
        with self.assertRaises(Conflict):
            self.app.drafts.put("two", "attempt", self.app.drafts.get("one", draft_id))

    def test_checkpoint_rejects_wrong_reference_and_preserves_no_release_semantics(self):
        run = self.app.start("one", "request", size=100)
        self.assertEqual(self.app.worker.drain("one"), 3)
        state = self.app.tasks.inspect("one", run)
        with self.assertRaises(Conflict):
            self.app.tasks.acknowledge("one", run, "other-draft", self.now)
        reopened = build(self.path, lambda: self.now)
        self.assertFalse(reopened.worker.tick("one"))
        reference = state["tasks"][-1]["output"]["reference"]
        reopened.tasks.acknowledge("one", run, reference, self.now)
        with self.assertRaises(Conflict):
            reopened.tasks.acknowledge("one", run, reference, self.now)
        self.assertEqual(reopened.worker.drain("one"), 1)
        result = reopened.tasks.inspect("one", run)
        self.assertEqual(result["run"]["status"], "succeeded")
        self.assertIs(result["tasks"][-1]["output"]["release_authority"], False)
        self.assertFalse(reopened.worker.tick("one"))

    def test_crash_after_draft_commit_reuses_artifact_on_recovery(self):
        run = self.app.start("one", "request", size=100)
        self.app.worker.tick("one")
        claim = self.app.tasks.claim("one", self.now, 60)
        original = self.app.worker.capabilities[claim.capability](claim)
        # Process disappears before task receipt. The domain operation committed.
        self.now += 61
        restarted = build(self.path, lambda: self.now)
        restarted.worker.drain("one")
        state = restarted.tasks.inspect("one", run)
        self.assertEqual(state["tasks"][1]["output"]["draft_id"], original.data["draft_id"])
        self.assertEqual(state["tasks"][1]["attempts"], 2)
        with Database(self.path).connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM drafts").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM draft_operations").fetchone()[0], 1)

    def test_result_state_and_event_commit_atomically(self):
        run = self.task()
        claim = self.app.tasks.claim("one", self.now, 60)
        with Database(self.path).connect() as connection:
            connection.execute("""CREATE TRIGGER fail_event BEFORE INSERT ON events
                WHEN NEW.kind='task_succeeded' BEGIN SELECT RAISE(ABORT,'injected'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.app.tasks.settle(claim, Outcome("succeeded", {"receipt": "committed"}), self.now)
        state = self.app.tasks.inspect("one", run)
        self.assertEqual(state["run"]["status"], "running")
        self.assertEqual(state["tasks"][0]["status"], "running")
        self.assertIsNone(state["tasks"][0]["output"])
        with Database(self.path).connect() as connection:
            connection.execute("DROP TRIGGER fail_event")
        self.app.tasks.settle(claim, Outcome("succeeded", {"receipt": "committed"}), self.now)

    def test_retries_are_delayed_and_bounded(self):
        run = self.task([TaskSpec("transient", {}, max_attempts=2)])
        def transient(_):
            raise RetryableError("fixture")
        worker = Worker(self.app.tasks, {"transient": transient}, lambda: self.now)
        self.assertEqual(worker.drain("one"), 1)
        self.assertFalse(worker.tick("one"))
        self.now += 2
        self.assertTrue(worker.tick("one"))
        self.assertFalse(worker.tick("one"))
        state = self.app.tasks.inspect("one", run)
        self.assertEqual(state["run"]["status"], "failed")
        self.assertEqual(state["tasks"][0]["attempts"], 2)

    def test_repeated_crashes_exhaust_attempt_budget(self):
        run = self.task([TaskSpec("test", {}, max_attempts=1)])
        self.app.tasks.claim("one", self.now, 1)
        self.now += 1
        self.assertIsNone(self.app.tasks.claim("one", self.now, 1))
        self.assertEqual(self.app.tasks.inspect("one", run)["run"]["status"], "failed")

    def test_unsupported_capability_and_workflow_version_fail_closed(self):
        first = self.task([TaskSpec("unknown", {})])
        self.app.worker.drain("one")
        self.assertEqual(self.app.tasks.inspect("one", first)["tasks"][0]["output"]["error_code"], "unsupported_capability")
        second = self.task([TaskSpec("audiences.inspect.v1", {"workflow_version": "monthly-mail/v2"})], request="new")
        self.app.worker.drain("one")
        self.assertEqual(self.app.tasks.inspect("one", second)["run"]["status"], "failed")

    def test_draft_integrity_and_operation_conflicts(self):
        snapshot = generate("one", 100)
        draft = build_draft(snapshot, Brief("test"), fixture_catalog())
        self.app.drafts.put("one", "operation", draft)
        with self.assertRaises(Conflict):
            self.app.drafts.put("one", "another", replace(draft, mailing_csv=draft.mailing_csv + "tampered"))
        changed = build_draft(snapshot, Brief("test", budget_pence=850), fixture_catalog())
        with self.assertRaises(Conflict):
            self.app.drafts.put("one", "operation", changed)
        with Database(self.path).connect() as connection:
            connection.execute("UPDATE drafts SET mailing='tampered' WHERE id=?", (draft.id,))
        with self.assertRaises(Conflict):
            self.app.drafts.get("one", draft.id)

    def test_database_version_skew_is_rejected(self):
        with Database(self.path).connect() as connection:
            connection.execute("PRAGMA user_version=999")
        with self.assertRaises(ValueError):
            build(self.path)

    def test_creative_catalogue_drift_does_not_resume_an_old_run(self):
        run = self.app.start("one", "request", size=100)
        self.app.worker.drain("one")
        state = self.app.tasks.inspect("one", run)
        self.app.tasks.acknowledge("one", run, state["tasks"][-1]["output"]["reference"], self.now)
        # Version skew is exercised through the real registered capability.
        handler = self.app.worker.capabilities["campaigns.review_checkpoint.v1"]
        workflow = handler.__self__
        workflow.campaigns.creatives = (replace(fixture_catalog()[0], opening="changed"),) + fixture_catalog()[1:]
        self.app.worker.drain("one")
        state = self.app.tasks.inspect("one", run)
        self.assertEqual(state["run"]["status"], "failed")
        self.assertNotIn("mode", state["tasks"][-1]["output"])

    def test_exported_bytes_match_manifest_and_can_be_rebuilt(self):
        run = self.app.start("one", "request", size=100)
        self.app.worker.drain("one")
        destination = self.app.export("one", run, Path(self.temporary.name) / "exports")
        manifest = json.loads((destination / "manifest.json").read_text())
        original = (destination / "mailing.csv").read_bytes()
        self.assertEqual(hashlib.sha256(original).hexdigest(), manifest["mailing_sha256"])
        (destination / "mailing.csv").write_text("edited by operator")
        self.app.export("one", run, Path(self.temporary.name) / "exports")
        self.assertEqual((destination / "mailing.csv").read_bytes(), original)

    def test_invalid_runtime_resource_limits(self):
        for limit in (0, 1001, True):
            with self.assertRaises(ValueError):
                self.app.worker.drain("one", limit)
        for duration in (0, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                Worker(self.app.tasks, {}, lambda: self.now, lease_seconds=duration)
        with self.assertRaises(ValueError):
            TaskSpec("test", {}, max_attempts=True)

    def test_real_process_restart_and_exports(self):
        environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
        def cli(*arguments):
            result = subprocess.run([sys.executable, "-m", "acquisition", "--db", str(self.path),
                                     "--organization", "one", *arguments], env=environment,
                                    text=True, capture_output=True, check=True)
            return json.loads(result.stdout)
        run = cli("create", "--size", "100")["run_id"]
        self.assertEqual(cli("work")["worker_ticks"], 3)
        waiting = cli("status", "--run", run)
        self.assertEqual(waiting["run"]["status"], "waiting")
        reference = waiting["tasks"][-1]["output"]["reference"]
        exported = cli("export", "--run", run, "--out", self.temporary.name)
        directory = Path(exported["export_directory"])
        self.assertEqual({p.name for p in directory.iterdir()}, {"manifest.json", "mailing.csv", "assignments.csv"})
        cli("acknowledge", "--run", run, "--reference", reference)
        self.assertEqual(cli("work")["worker_ticks"], 1)
        self.assertEqual(cli("status", "--run", run)["run"]["status"], "succeeded")
