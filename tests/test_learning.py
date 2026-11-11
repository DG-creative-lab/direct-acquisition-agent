"""Independent counts, real SQLite faults, scope, maturity and recovery probes."""
import copy
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from unittest.mock import patch
from pathlib import Path
from threading import Barrier

from acquisition.bootstrap import build
from acquisition.contracts import Conflict, NotFound, digest
from acquisition.learning import counts_for, posterior, recommend, WINDOW_SECONDS
from acquisition.local_root import CHECKPOINT_FILE
from acquisition.review_demo import run_review_demo
from acquisition.adapters.learning_report import render_learning
from acquisition.reasoning import ModelConfig
from test_model_copy import FakeModel


class LearningDomainTests(unittest.TestCase):
    def test_literal_counts_and_prior_are_not_model_scores(self):
        members = [{"business_id": "one", "segment": "inventory", "arm": "A", "creative_id": "copy"},
                   {"business_id": "two", "segment": "inventory", "arm": "A", "creative_id": "copy"},
                   {"business_id": "three", "segment": "inventory", "arm": "no_mail", "creative_id": ""}]
        outcomes = {"one": {"response": True}, "two": {"response": False}, "three": {"response": False}}
        groups = counts_for(members, outcomes)
        a, control = groups
        self.assertEqual((a["trials"], a["successes"], a["alpha"], a["beta"]), (2, 1, 2, 20))
        self.assertEqual((control["trials"], control["successes"], control["alpha"], control["beta"]), (1, 0, 1, 20))
        self.assertAlmostEqual(a["mean"], 1 / 11)
        self.assertEqual(counts_for(list(reversed(members)), outcomes), groups)
        for changed in ({"one": outcomes["one"], "two": outcomes["two"]}, outcomes | {"extra": {"response": True}}):
            with self.assertRaises(Conflict):
                counts_for(members, changed)

    def test_prior_sampling_matches_analytic_beta_quantiles(self):
        groups = [posterior("inventory", arm, arm, 0, 0) for arm in ("A", "B", "no_mail")]
        result = recommend("analytic-prior", groups)[0]
        for low, high in result["response_intervals_90"].values():
            # Beta(1,19) CDF is 1-(1-x)^19, giving exact reference quantiles.
            self.assertAlmostEqual(low, 1 - .95 ** (1 / 19), delta=.003)
            self.assertAlmostEqual(high, 1 - .05 ** (1 / 19), delta=.01)
        self.assertEqual(result["action"], "collect_more_evidence")

    def test_recommendation_uses_control_and_reports_uncertainty_reproducibly(self):
        groups = [posterior("inventory", arm, arm, 200, success) for arm, success in (("A", 65), ("B", 4), ("no_mail", 3))]
        first = recommend("frozen-cohort", groups)
        self.assertEqual(first, recommend("frozen-cohort", groups))
        inventory, missing = first
        self.assertEqual(inventory["candidate_arm"], "A")
        self.assertEqual(inventory["action"], "propose_next_experiment")
        self.assertGreater(inventory["lift_interval_90"][0], 0)
        self.assertEqual(missing["action"], "collect_more_evidence")
        small = [posterior("inventory", arm, arm, 9, success) for arm, success in (("A", 9), ("B", 0), ("no_mail", 0))]
        self.assertEqual(recommend("small", small)[0]["action"], "collect_more_evidence")
        # A beats B but loses to the control: no recommendation to use A.
        poor = [posterior("inventory", arm, arm, 200, success) for arm, success in (("A", 50), ("B", 1), ("no_mail", 100))]
        self.assertEqual(recommend("negative-lift", poor)[0]["action"], "collect_more_evidence")


class LearningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "learning.sqlite"
        self.now = 1792886400.0
        self.app = build(self.path, lambda: self.now)
        demo = run_review_demo(self.app, "learning-tests", "fixture", self.root / "review", str(self.path))
        self.scope, self.case = demo["organization"], demo["case_id"]
        self.actor = "demo-operator"
        self.store = self.app.learning.store
        self.opened = self.app.learning.open(self.scope, self.case, self.actor, "open")
        self.cohort = self.opened["cohort_id"]
        self.proposal = self.app.learning.source.accepted(self.scope, self.case)
        self.rows = [member | {"response": i % 10 == 0, "observed_at": self.now + 1 if i % 10 == 0 else self.opened["window_end"]}
                     for i, member in enumerate(self.proposal["members"])]

    def batch(self, rows=None):
        return {"schema": "synthetic-outcomes/v1", "mode": "SYNTHETIC_ONLY", "cohort_id": self.cohort,
                "outcomes": self.rows if rows is None else rows}

    def ingest(self, rows=None, key="ingest"):
        return self.store.ingest(self.scope, self.actor, key, self.cohort, self.batch(rows))

    def mature(self):
        self.now = self.opened["window_end"]
        self.ingest()

    def finalize(self, key="finalize"):
        return self.store.finalize(self.scope, self.actor, key, self.cohort, self.opened["window_end"])

    def count(self, table):
        with self.store.database.connect() as db:
            return db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]

    def report(self, report_id, *pages, final=True, watermark=None):
        # Use the frozen acceptance as the expected source, independent of the adapter.
        report = {key: self.proposal[key] for key in ("organization", "job_id", "metric", "window_start", "window_end")}
        return report | {"schema": "synthetic-provider-report/v1", "mode": "SYNTHETIC_ONLY",
            "cohort_id": self.cohort, "report_id": report_id, "final": final,
            "watermark": self.opened["window_end"] if watermark is None else watermark,
            "page_count": len(pages), "pages": [
                {"report_id": report_id, "number": number, "events": [
                    {"event_id": "synthetic_event_" + digest({"cohort_id": self.cohort, "business_id": row["business_id"]}),
                     "outcome": row} for row in rows]}
                for number, rows in enumerate(pages, 1)]}

    def import_report(self, report, key="report"):
        path = self.root / "provider-report.json"
        path.write_text(json.dumps(report))
        return self.app.learning.ingest_report(self.scope, self.actor, key, self.cohort, path)

    def test_duplicate_json_fields_in_report_fail_before_any_import_writes(self):
        self.now = self.opened["window_end"]
        report = self.report("unique-fields", self.rows[:1])
        raw = json.dumps(report)
        path = self.root / "provider-report.json"
        duplicates = (
            ('"final": true', '"final": false, "final": true'),
            ('"number": 1', '"number": 2, "number": 1'),
            ('"event_id":', '"event_id": "different-event", "event_id":'),
            ('"response": true', '"response": false, "response": true'),
            ('"response": true', r'"resp\u006fnse": true, "response": true'),
        )
        for field, duplicate in duplicates:
            with self.subTest(duplicate=duplicate):
                self.assertEqual(raw.count(field), 1)
                path.write_text(raw.replace(field, duplicate, 1))
                with self.assertRaisesRegex(ValueError, "Duplicate JSON field"):
                    self.app.learning.ingest_report(self.scope, self.actor, "report", self.cohort, path)
        self.assertEqual(self.count("learning_outcomes"), 0)
        self.assertEqual(self.count("learning_commands"), 1)
        self.assertEqual(self.count("learning_events"), 1)
        self.assertEqual(self.import_report(report)["added"], 1)

    def test_missing_report_page_writes_nothing_and_original_request_recovers_via_cli(self):
        self.now = self.opened["window_end"]
        report = self.report("with-gap", self.rows[:4], self.rows[4:7], self.rows[7:])
        with self.assertRaisesRegex(Conflict, "missing pages"):
            self.import_report(report | {"pages": [report["pages"][0], report["pages"][2]]})
        self.assertEqual(self.count("learning_outcomes"), 0)
        self.assertEqual(self.count("learning_commands"), 1)
        self.assertEqual(self.store.view(self.scope, self.cohort)["missing"], 754)

        path = self.root / "provider-report.json"
        path.write_text(json.dumps(report))
        script = '''import sys
import acquisition.__main__ as cli
from functools import partial
now = float(sys.argv.pop(1))
cli.build = partial(cli.build, clock=lambda: now)
cli.main()
'''
        child = subprocess.run([sys.executable, "-c", script, str(self.now), "--db", str(self.path),
                                "--organization", self.scope, "learning-import-report", "--cohort", self.cohort,
                                "--actor", self.actor, "--request-id", "report", "--file", str(path)],
                               capture_output=True, text=True, timeout=30,
                               env=dict(os.environ, PYTHONPATH=str(Path("src").resolve())))
        self.assertEqual(child.returncode, 0, child.stderr)
        receipt = json.loads(child.stdout)
        self.assertEqual(receipt["added"], 754)
        self.assertTrue(receipt["coverage_complete"])
        self.assertEqual(self.import_report(report), receipt)
        self.assertEqual(self.count("learning_outcomes"), 754)
        self.assertEqual(self.count("learning_beliefs"), 0)

    def test_duplicate_events_and_cumulative_reports_preserve_independent_counts(self):
        self.now += 1
        positives = [row for row in self.rows if row["response"]][:4]
        early = self.report("early", positives, positives[:2], final=False, watermark=self.now)
        receipt = self.import_report(early, "early")
        self.assertEqual((receipt["added"], receipt["duplicates"], receipt["duplicate_events"]), (4, 0, 2))
        self.assertFalse(receipt["coverage_complete"])
        with self.assertRaisesRegex(Conflict, "window must close"):
            self.finalize()

        self.now = self.opened["window_end"]
        final = self.report("cumulative", self.rows[:400], self.rows[400:])
        receipt = self.import_report(final, "cumulative")
        self.assertEqual((receipt["added"], receipt["duplicates"], receipt["missing_from_report"]), (750, 4, 0))
        self.assertTrue(receipt["coverage_complete"])
        reordered = final | {"pages": [page | {"events": list(reversed(page["events"]))}
                                       for page in reversed(final["pages"])]}
        self.assertEqual(self.import_report(reordered, "cumulative"), receipt)
        replay = self.import_report(reordered, "cumulative-replay")
        self.assertEqual((replay["added"], replay["duplicates"]), (0, 754))
        self.assertEqual(self.import_report(early, "late-early")["added"], 0)
        self.assertEqual(sum(e["kind"] == "provider_report_imported"
                             for e in self.store.view(self.scope, self.cohort)["events"]), 2)
        finalization = self.finalize()
        self.assertEqual((finalization["observations"], finalization["successes"]), (754, 76))
        beliefs = self.store.view(self.scope, self.cohort)["beliefs"]
        self.assertEqual(sum(row["trials"] for row in beliefs if row["arm"] == "no_mail"), 74)

    def test_monitor_restarts_after_report_commit_without_recounting_observations(self):
        self.now += 1
        early = self.report("early", [row for row in self.rows if row["response"]][:4],
                            final=False, watermark=self.now)
        final = self.report("final", self.rows[:400], self.rows[400:])
        files = [self.root / name for name in ("early.json", "final.json")]
        for path, report in zip(files, (early, final)):
            path.write_text(json.dumps(report))
        schedule = self.app.learning.schedule_reports(self.scope, self.actor, "schedule", self.cohort,
                                                      self.now, 86400, files)
        self.assertEqual((schedule["position"], schedule["next_due"]), (0, self.now))
        for path in files:
            path.unlink()

        def tick(now, lease_time, crash=False):
            script = """
import os
import sys
from unittest.mock import patch
import acquisition.__main__ as cli
from acquisition.adapters.sqlite.report_monitoring import SqliteReportMonitoring

now, lease_time, crash = sys.argv[1:4]
del sys.argv[1:4]
real_build = cli.build
def build(*args, **kwargs):
    app = real_build(*args, **kwargs, clock=lambda: float(now))
    app.learning.monitoring.lease_clock = lambda: float(lease_time)
    return app
cli.build = build
if crash == 'True':
    # The normal importer has already returned from its committed transaction.
    with patch.object(SqliteReportMonitoring, 'finish', lambda *args: os._exit(91)):
        cli.main()
else:
    cli.main()
"""
            return subprocess.run(
                [sys.executable, "-c", script, str(now), str(lease_time), str(crash),
                 "--db", str(self.path), "--organization", self.scope, "learning-monitor-tick", "--cohort", self.cohort],
                capture_output=True, text=True, timeout=30, env=dict(os.environ, PYTHONPATH=str(Path("src").resolve())))

        crash = tick(self.now, 100, crash=True)
        self.assertEqual(crash.returncode, 91, crash.stderr)
        self.assertEqual(self.count("learning_outcomes"), 4)
        self.assertEqual(self.count("learning_commands"), 3)  # Open, schedule and the first report import.
        self.assertEqual(self.app.learning.monitoring.status(self.scope, self.cohort)["position"], 0)
        self.assertEqual(self.store.report_snapshot(self.scope, self.cohort, "early")["import_receipt"]["added"], 4)

        leased = tick(self.now, 101)
        self.assertEqual(leased.returncode, 0, leased.stderr)
        self.assertEqual(json.loads(leased.stdout)["monitoring"]["position"], 0)
        resumed = tick(self.now, 131)
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        plan = json.loads(resumed.stdout)["monitoring"]
        self.assertEqual((plan["position"], plan["last_report_id"], plan["watermark"]), (1, "early", self.now))
        self.assertEqual(self.count("learning_commands"), 3)
        self.assertEqual(self.count("learning_outcomes"), 4)
        self.assertEqual(self.count("learning_beliefs"), 0)

        self.now = self.opened["window_end"]
        complete = tick(self.now, 132)
        self.assertEqual(complete.returncode, 0, complete.stderr)
        self.assertEqual(json.loads(complete.stdout)["monitoring"]["status"], "complete")
        report_receipt = self.store.report_snapshot(self.scope, self.cohort, "final")["import_receipt"]
        self.assertEqual((report_receipt["added"], report_receipt["duplicates"]), (750, 4))
        self.assertEqual(self.count("learning_beliefs"), 0)
        result = self.finalize()
        self.assertEqual((result["observations"], result["successes"]), (754, 76))
        view = self.store.view(self.scope, self.cohort)
        self.assertEqual(sum(group["trials"] for group in view["beliefs"] if group["arm"] == "no_mail"), 74)
        self.assertEqual([event["payload"]["report_id"] for event in view["events"]
                          if event["kind"] == "provider_report_imported"], ["early", "final"])

    def test_monitor_pause_fences_a_claim_and_cadence_keeps_the_cohort_cutoff(self):
        self.now += 1
        positives = [row for row in self.rows if row["response"]][:2]
        monitor = self.app.learning.monitoring
        early = self.report("early", positives[:1], final=False, watermark=self.now)
        later = self.report("later", positives, final=False, watermark=self.now)
        with self.assertRaisesRegex(Conflict, "accepted cohort"):
            monitor.start(self.scope, self.actor, "wrong", self.cohort, self.now, 60, [early | {"job_id": "another-job"}])
        conflicting = self.report("later", [positives[0] | {"observed_at": self.now - 1}], final=False, watermark=self.now)
        with self.assertRaisesRegex(Conflict, "disagree on an immutable outcome"):
            monitor.start(self.scope, self.actor, "conflicting", self.cohort, self.now, 60, [early, conflicting])
        self.assertIsNone(monitor.status(self.scope, self.cohort))
        monitor.start(self.scope, self.actor, "schedule", self.cohort, self.now, 60, [early, later])
        self.assertIsNone(monitor.status("another-organization", self.cohort))
        self.assertIsNone(monitor.claim("another-organization", self.cohort))
        old_token = monitor.claim(self.scope, self.cohort)
        self.assertIsNotNone(old_token)
        self.assertIsNone(monitor.claim(self.scope, self.cohort))
        self.now -= 1
        self.assertFalse(monitor.import_claim(self.scope, self.cohort, old_token))
        self.assertEqual(self.count("learning_outcomes"), 0)
        self.now += 1
        pause = monitor.update(self.scope, self.actor, "pause", self.cohort, 1, "paused")
        self.assertEqual(pause["status"], "paused")
        monitor.import_claim(self.scope, self.cohort, old_token)
        monitor.finish(self.scope, self.cohort, old_token)
        self.app.learning.check_reports(self.scope, self.cohort)
        self.assertEqual(self.count("learning_outcomes"), 0)
        with self.assertRaisesRegex(Conflict, "current unfinished schedule"):
            monitor.update(self.scope, self.actor, "stale", self.cohort, 1, "scheduled")
        resume = monitor.update(self.scope, self.actor, "resume", self.cohort, 2, "scheduled", 3600)
        self.assertEqual(resume, monitor.update(self.scope, self.actor, "resume", self.cohort, 2, "scheduled", 3600))
        lease_time = 100
        monitor.lease_clock = lambda: lease_time
        lease = monitor.claim(self.scope, self.cohort)
        original = self.store.import_report

        def expire_during_import(*args):
            nonlocal lease_time
            original(*args)
            lease_time = 131

        with patch.object(self.store, "import_report", side_effect=expire_during_import):
            with self.assertRaisesRegex(Conflict, "expired before import committed"):
                monitor.import_claim(self.scope, self.cohort, lease)
        self.assertEqual(self.count("learning_outcomes"), 0)
        self.app.learning.check_reports(self.scope, self.cohort)
        plan = monitor.status(self.scope, self.cohort)
        self.assertEqual((plan["position"], plan["next_due"]), (1, self.now + 3600))
        self.app.learning.check_reports(self.scope, self.cohort)
        self.assertEqual(self.count("learning_outcomes"), 1)
        self.now = self.opened["window_end"]
        self.app.learning.check_reports(self.scope, self.cohort)
        self.assertEqual(self.count("learning_outcomes"), 2)
        self.assertEqual(self.store.view(self.scope, self.cohort)["cohort"]["window_end"], self.now)
        with self.assertRaisesRegex(Conflict, "including controls"):
            self.finalize()

    def test_complete_pages_and_final_watermark_do_not_substitute_for_control_outcomes(self):
        self.now = self.opened["window_end"]
        mailed = [row for row in self.rows if row["arm"] != "no_mail"]
        report = self.report("treatment-only", mailed[:350], mailed[350:])
        receipt = self.import_report(report)
        self.assertEqual((receipt["added"], receipt["missing_from_report"]), (680, 74))
        self.assertFalse(receipt["coverage_complete"])
        with self.assertRaisesRegex(Conflict, "including controls"):
            self.finalize()
        self.assertEqual(self.count("learning_beliefs"), 0)
        self.assertEqual(self.store.view(self.scope, self.cohort)["missing"], 74)

    def test_provider_report_identity_conflicts_leave_existing_outcomes_unchanged(self):
        self.now = self.opened["window_end"]
        report = self.report("original", self.rows[:1])
        self.import_report(report)
        changed = self.report("original", self.rows[:2])
        with self.assertRaisesRegex(Conflict, "request ID"):
            self.import_report(changed)
        with self.assertRaisesRegex(Conflict, "report ID"):
            self.import_report(changed, "another-key")
        conflicting = self.rows[0] | {"response": False, "observed_at": self.now}
        with self.assertRaisesRegex(Conflict, "immutable outcome"):
            self.import_report(self.report("conflicting", [self.rows[1], conflicting]), "conflicting")
        self.assertEqual(self.count("learning_outcomes"), 1)
        self.assertEqual(self.count("learning_commands"), 2)

    def test_snapshot_provenance_is_scoped_and_verifies_the_saved_pages(self):
        self.now = self.opened["window_end"]
        report = self.report("provenance", self.rows[:1], self.rows[1:2])
        receipt = self.import_report(report)
        (self.root / "provider-report.json").unlink()
        reopened = build(self.path, clock=lambda: self.now).learning.store
        source = reopened.report_snapshot(self.scope, self.cohort, "provenance")
        self.assertEqual(source["snapshot"], report)
        self.assertEqual(digest(source["snapshot"]), receipt["report_sha256"])
        self.assertEqual(source["import_receipt"], receipt | {"actor": self.actor})
        self.assertEqual(reopened.view(self.scope, self.cohort)["events"][-1]["payload"], source["import_receipt"])
        with self.assertRaises(NotFound):
            reopened.report_snapshot("another-scope", self.cohort, "provenance")
        with self.store.database.transaction() as db:
            db.execute("""UPDATE learning_events SET payload=json_remove(payload, '$.snapshot.pages[1]')
                WHERE organization=? AND cohort_id=? AND kind='provider_report_source_recorded'""",
                (self.scope, self.cohort))
        with self.assertRaisesRegex(Conflict, "does not match the import receipt"):
            reopened.report_snapshot(self.scope, self.cohort, "provenance")
        with self.assertRaisesRegex(Conflict, "does not match the import receipt"):
            self.import_report(report, "corrupt-retry")
        self.assertEqual(self.count("learning_commands"), 2)

    def test_exact_legacy_report_can_attach_provenance_without_rewriting_its_receipt(self):
        self.now = self.opened["window_end"]
        report = self.report("legacy", self.rows[:1])
        receipt = self.import_report(report)
        with self.store.database.transaction() as db:
            db.execute("DELETE FROM learning_events WHERE organization=? AND cohort_id=? AND kind='provider_report_source_recorded'",
                       (self.scope, self.cohort))
        with self.assertRaisesRegex(NotFound, "snapshot is unavailable"):
            self.store.report_snapshot(self.scope, self.cohort, "legacy")
        self.assertEqual(self.import_report(report), receipt)
        replay = self.import_report(report, "attach-original")
        self.assertEqual((replay["added"], replay["duplicates"]), (0, 1))
        self.assertEqual(self.store.report_snapshot(self.scope, self.cohort, "legacy"),
                         {"import_receipt": receipt | {"actor": self.actor}, "snapshot": report})
        self.assertEqual(self.import_report(report, "repeat-attachment")["added"], 0)
        self.assertEqual(self.count("learning_events"), 3)

    def test_report_rejects_substituted_evidence_and_invalid_watermarks(self):
        self.now = self.opened["window_end"]
        report = self.report("source", self.rows[:2])
        wrong_page = copy.deepcopy(report)
        wrong_page["pages"][0]["report_id"] = "different-snapshot"
        wrong_event = copy.deepcopy(report)
        wrong_event["pages"][0]["events"][0]["event_id"] = wrong_event["pages"][0]["events"][1]["event_id"]
        wrong_assignment = self.rows[0] | {"arm": "no_mail" if self.rows[0]["arm"] == "A" else "A"}
        cases = [
            (report | {"organization": "different-scope"}, "accepted cohort"),
            (report | {"job_id": "different-job"}, "accepted cohort"),
            (report | {"metric": "delivered"}, "accepted cohort"),
            (report | {"watermark": self.now + 1}, "watermark"),
            (report | {"watermark": self.now - 1}, "entire closed"),
            (report | {"final": False}, "non-response requires a final report"),
            (wrong_page, "belong to the report"),
            (wrong_event, "event identity"),
            (self.report("wrong-assignment", [wrong_assignment]), "frozen business assignment"),
        ]
        for invalid, expected in cases:
            with self.subTest(expected=expected), self.assertRaisesRegex(ValueError, expected):
                self.import_report(invalid)
        with self.store.database.transaction() as db:
            db.execute("DELETE FROM simulated_agency_jobs WHERE organization=? AND case_id=?", (self.scope, self.case))
        with self.assertRaisesRegex(Conflict, "accepted experiment is invalid"):
            self.import_report(report)
        self.assertEqual(self.count("learning_outcomes"), 0)
        self.assertEqual(self.count("learning_commands"), 1)

    def test_report_import_rolls_back_with_audit_and_checkpoint_clone_refuses_writes(self):
        self.now = self.opened["window_end"]
        report = self.report("atomic", self.rows[:2])
        for event in ("provider_report_imported", "provider_report_source_recorded"):
            with self.subTest(event=event):
                with self.store.database.transaction() as db:
                    db.execute(f"""CREATE TRIGGER fail_report_event BEFORE INSERT ON learning_events
                        WHEN NEW.kind='{event}' BEGIN SELECT RAISE(ABORT, 'fixture'); END""")
                with self.assertRaises(sqlite3.IntegrityError):
                    self.import_report(report)
                self.assertEqual(self.count("learning_outcomes"), 0)
                self.assertEqual(self.count("learning_commands"), 1)
                self.assertEqual(self.count("learning_events"), 1)
                with self.store.database.transaction() as db:
                    db.execute("DROP TRIGGER fail_report_event")

        restored = self.root / "inspection"
        restored.mkdir()
        (restored / CHECKPOINT_FILE).write_text("{}")
        db_path = restored / self.path.name
        shutil.copyfile(self.path, db_path)
        before = db_path.read_bytes()
        inspection = build(db_path, clock=lambda: self.now)
        with self.assertRaisesRegex(Conflict, "inspection-only"):
            inspection.learning.ingest_report(self.scope, self.actor, "report", self.cohort, self.root / "provider-report.json")
        self.assertEqual(inspection.learning.store.view(self.scope, self.cohort)["missing"], 754)
        self.assertEqual(db_path.read_bytes(), before)

    def test_only_accepted_campaign_can_open_and_members_include_controls(self):
        self.assertEqual(self.opened["members"], 754)
        self.assertEqual(self.opened["window_end"] - self.opened["window_start"], WINDOW_SECONDS)
        self.assertEqual(sum(m["arm"] == "no_mail" for m in self.proposal["members"]), 74)
        run = self.app.start(self.scope, "unaccepted")
        self.app.worker.drain(self.scope)
        case = self.app.reviews.store.open_case(self.scope, run, self.actor)
        with self.assertRaises(Conflict):
            self.app.learning.open(self.scope, case["case_id"], self.actor, "not-accepted")
        self.assertEqual(self.count("learning_cohorts"), 1)

    def test_coordinated_membership_omission_cannot_define_its_own_denominator(self):
        forged = copy.deepcopy(self.proposal)
        forged["members"] = [m for m in forged["members"] if m["arm"] != "no_mail"]
        forged["id"] = "cohort_" + digest({k: v for k, v in forged.items() if k != "id"})
        with self.assertRaises(Conflict):
            self.store.open(self.scope, self.actor, "omitted-controls", forged)
        self.assertEqual(self.count("learning_cohorts"), 1)
        self.assertEqual(self.count("learning_members"), 754)

    def test_early_responses_do_not_update_beliefs_or_close_the_window(self):
        self.now += 1
        positives = [r for r in self.rows if r["response"]]
        self.ingest(positives)
        view = self.store.view(self.scope, self.cohort)
        self.assertEqual(view["status"], "observing")
        self.assertEqual(view["beliefs"], [])
        self.assertEqual(view["recommendations"], [])
        self.assertEqual(self.store.memory(self.scope, "inventory")["groups"], [])
        with self.assertRaises(Conflict):
            self.finalize()
        with self.assertRaises(ValueError):
            self.ingest([r for r in self.rows if not r["response"]], "early-negatives")
        self.assertEqual(self.count("learning_beliefs"), 0)

    def test_complete_early_responses_still_cannot_finalize_before_maturity(self):
        self.now += 1
        all_positive = [r | {"response": True, "observed_at": self.now} for r in self.rows]
        self.ingest(all_positive)
        self.assertEqual(self.store.view(self.scope, self.cohort)["missing"], 0)
        with self.assertRaises(Conflict):
            self.finalize()
        self.assertEqual(self.count("learning_beliefs"), 0)
        self.now = self.opened["window_end"]
        receipt = self.finalize()
        self.assertEqual((receipt["observations"], receipt["successes"]), (754, 754))

    def test_absent_results_and_missing_control_are_pending_not_failures(self):
        self.now = self.opened["window_end"]
        treatments = [r for r in self.rows if r["arm"] != "no_mail"]
        self.ingest(treatments)
        with self.assertRaises(Conflict):
            self.finalize()
        view = self.store.view(self.scope, self.cohort)
        self.assertEqual(view["missing"], 74)
        self.assertEqual(view["status"], "awaiting_complete_outcomes")
        self.assertFalse(view["beliefs"])
        self.ingest([r for r in self.rows if r["arm"] == "no_mail"], "controls")
        self.finalize()
        self.assertEqual(sum(g["trials"] for g in self.store.view(self.scope, self.cohort)["beliefs"]), 754)

    def test_complete_mature_counts_survive_restart_and_replay_once(self):
        self.mature()
        first = self.finalize()
        reopened = build(self.path, lambda: self.now)
        same = reopened.learning.store.finalize(self.scope, self.actor, "finalize", self.cohort, self.opened["window_end"])
        different_key = self.finalize("new-finalize-key")
        self.assertEqual(first, same)
        self.assertEqual(first, different_key)
        self.assertEqual(first["observations"], 754)
        self.assertEqual(first["successes"], 76)
        self.assertEqual(self.count("learning_beliefs"), 6)
        view = self.store.view(self.scope, self.cohort)
        for group in view["beliefs"]:
            members = [r for r in self.rows if r["segment"] == group["segment"] and r["arm"] == group["arm"]]
            successes = sum(r["response"] for r in members)
            self.assertEqual((group["trials"], group["successes"], group["alpha"], group["beta"]),
                             (len(members), successes, 1 + successes, 19 + len(members) - successes))

    def test_finalization_replay_preserves_original_actor_time_and_single_effect_event(self):
        self.mature()
        first = self.finalize()
        original = self.store.view(self.scope, self.cohort)["events"]
        self.now += 10
        self.app.reviews.store.register_actor(self.scope, "second-operator", ("operator",))
        replay = self.store.finalize(self.scope, "second-operator", "observe-finalized", self.cohort, self.opened["window_end"])
        self.assertEqual(replay, first)
        self.assertEqual(self.store.view(self.scope, self.cohort)["events"], original)
        finalized = [e for e in original if e["kind"] == "cohort_finalized"]
        self.assertEqual(len(finalized), 1)
        self.assertEqual(finalized[0]["payload"]["actor"], self.actor)
        self.assertEqual(finalized[0]["at"], first["finalized_at"])
        with self.store.database.connect() as db:
            cached = json.loads(db.execute("SELECT receipt FROM learning_commands WHERE organization=? AND request_id='observe-finalized'", (self.scope,)).fetchone()[0])
        self.assertEqual(cached, first)
        reopened = build(self.path, lambda: self.now)
        self.assertEqual(reopened.learning.store.finalize(self.scope, "second-operator", "observe-finalized", self.cohort, self.opened["window_end"]), first)
        self.assertEqual(reopened.learning.store.view(self.scope, self.cohort)["events"], original)
        with self.assertRaises(Conflict):
            self.store.finalize(self.scope, "second-operator", "observe-finalized", self.cohort, self.opened["window_end"] + 1)
        self.assertEqual(self.count("learning_beliefs"), 6)

    def test_dedup_across_batches_and_keys_never_inflates_counts(self):
        self.mature()
        original = self.ingest()
        reordered = self.ingest(list(reversed(self.rows)))
        again = self.ingest(key="new-batch-key")
        self.assertEqual(original, reordered)
        self.assertEqual(again["added"], 0)
        self.assertEqual(again["duplicates"], 754)
        self.finalize()
        self.ingest(key="after-finalization-identical")
        self.assertEqual(self.count("learning_outcomes"), 754)
        self.assertEqual(self.finalize()["observations"], 754)

    def test_changed_or_duplicate_outcomes_and_request_reuse_are_rejected(self):
        self.mature()
        changed = copy.deepcopy(self.rows)
        changed[0]["observed_at"] += 1
        for key in ("ingest", "conflicting-fresh-key"):
            with self.assertRaises(Conflict):
                self.ingest(changed, key)
        with self.assertRaises(Conflict):
            self.ingest([self.rows[0], self.rows[0]], "duplicates")
        self.assertEqual(self.count("learning_outcomes"), 754)

    def test_assignment_scope_and_schema_substitution_are_rejected(self):
        self.now = self.opened["window_end"]
        mutations = {"business_id": "outsider", "segment": "other", "arm": "B" if self.rows[0]["arm"] == "A" else "A", "creative_id": "other-copy"}
        for field, value in mutations.items():
            with self.subTest(field=field), self.assertRaises(Conflict):
                self.ingest([self.rows[0] | {field: value}], "bad-" + field)
        with self.assertRaises(ValueError):
            self.ingest([self.rows[0] | {"response": 1}], "integer-score")
        with self.assertRaises(ValueError):
            self.store.ingest(self.scope, self.actor, "real-data", self.cohort, self.batch() | {"mode": "REAL"})
        self.app.reviews.store.register_actor("other", self.actor, ("operator",))
        with self.assertRaises(NotFound):
            self.store.view("other", self.cohort)
        with self.assertRaises(NotFound):
            self.store.ingest("other", self.actor, "cross-scope", self.cohort, self.batch())
        self.app.reviews.store.register_actor(self.scope, "reviewer-only", ("reviewer",))
        with self.assertRaises(ValueError):
            self.store.ingest(self.scope, "reviewer-only", "wrong-role", self.cohort, self.batch())
        self.assertEqual(self.count("learning_outcomes"), 0)

    def test_observation_window_boundaries_and_complete_through(self):
        self.now = self.opened["window_end"]
        row = self.rows[0]
        for at in (self.opened["window_start"] - 1, self.opened["window_end"], float("nan"), float("inf")):
            with self.subTest(at=at), self.assertRaises(ValueError):
                self.ingest([row | {"response": True, "observed_at": at}], "bad-time")
        with self.assertRaises(ValueError):
            self.ingest([row | {"response": False, "observed_at": self.opened["window_end"] - 1}], "partial-negative")
        self.mature()
        for through in (self.opened["window_end"] - 1, self.opened["window_end"] + 1):
            with self.assertRaises(Conflict):
                self.store.finalize(self.scope, self.actor, "wrong-through", self.cohort, through)
        self.finalize()

    def test_finalize_event_failure_rolls_back_counts_and_receipt(self):
        self.mature()
        with self.store.database.connect() as db:
            db.execute("CREATE TRIGGER fail_final BEFORE INSERT ON learning_events WHEN NEW.kind='cohort_finalized' BEGIN SELECT RAISE(ABORT,'injected'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.finalize()
        self.assertEqual(self.count("learning_beliefs"), 0)
        self.assertIsNone(self.store.view(self.scope, self.cohort)["finalization"])
        with self.store.database.connect() as db:
            db.execute("DROP TRIGGER fail_final")
        self.finalize()
        self.assertEqual(self.count("learning_beliefs"), 6)

    def test_partial_ingest_failure_rolls_back_all_rows(self):
        self.now = self.opened["window_end"]
        second = sorted(self.rows, key=lambda r: r["business_id"])[1]["business_id"]
        with self.store.database.connect() as db:
            db.execute("CREATE TRIGGER fail_ingest BEFORE INSERT ON learning_outcomes WHEN NEW.business_id='" + second + "' BEGIN SELECT RAISE(ABORT,'injected'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.ingest()
        self.assertEqual(self.count("learning_outcomes"), 0)
        with self.store.database.connect() as db:
            db.execute("DROP TRIGGER fail_ingest")
        self.mature()

    def test_concurrent_finalization_never_duplicates_beliefs(self):
        self.mature()
        barrier = Barrier(2)
        def finalize(key):
            barrier.wait()
            return self.finalize(key)
        with ThreadPoolExecutor(max_workers=2) as pool:
            receipts = list(pool.map(finalize, ("one-finalizer", "two-finalizers")))
        self.assertEqual(receipts[0], receipts[1])
        self.assertEqual(self.count("learning_beliefs"), 6)
        self.assertEqual(self.finalize()["observations"], 754)

    def test_cohort_open_replay_and_overlapping_businesses(self):
        self.assertEqual(self.opened, self.app.learning.open(self.scope, self.case, self.actor, "open"))
        self.assertEqual(self.opened, self.app.learning.open(self.scope, self.case, self.actor, "observe-open"))
        events = self.store.view(self.scope, self.cohort)["events"]
        self.assertEqual(len([e for e in events if e["kind"] == "cohort_opened"]), 1)
        run = self.app.start(self.scope, "second-campaign")
        self.app.worker.drain(self.scope)
        review = self.app.reviews.store
        case = review.open_case(self.scope, run, self.actor)
        revised = self.app.reviews.refresh(self.scope, case["case_id"], case["subject_id"], self.actor, "fresh-second")
        approval = review.decide(self.scope, case["case_id"], revised["subject_id"], "scripted-reviewer", "approve", "approve-second", "Synthetic second campaign.")
        review.handoff(self.scope, case["case_id"], approval["id"], self.actor, "accept-second")
        with self.assertRaises(Conflict):
            self.app.learning.open(self.scope, case["case_id"], self.actor, "overlapping")
        self.assertEqual(self.count("learning_cohorts"), 1)
        self.assertEqual(self.count("learning_members"), 754)

    def test_read_only_report_escapes_untrusted_values(self):
        view = self.store.view(self.scope, self.cohort)
        view["limitations"].append('<script>alert("x")</script>')
        report = render_learning(view)
        self.assertNotIn("<script>", report)
        self.assertIn("&lt;script&gt;", report)
        self.assertNotIn(chr(0x2014), report)

    def test_learning_memory_is_scoped_frozen_and_cannot_approve(self):
        model = FakeModel()
        app = build(self.path, lambda: self.now, model, ModelConfig("test/model"))
        before = app.start_model(self.scope, "before-learning", size=100)
        prior = app.tasks.inspect(self.scope, before)["tasks"][0]["inputs"]["context_ids"]
        self.mature()
        self.finalize()
        # This fixture closes inside the product evidence review window.
        self.now = self.proposal["window_start"] + WINDOW_SECONDS
        after = app.start_model(self.scope, "after-learning", size=100)
        current = app.tasks.inspect(self.scope, after)["tasks"][0]["inputs"]["context_ids"]
        for segment in prior:
            frozen = app.memory.get_context(self.scope, prior[segment])
            fresh = app.memory.get_context(self.scope, current[segment])
            self.assertFalse(frozen["audience_summary"]["outcome_evidence"]["groups"])
            self.assertTrue(fresh["audience_summary"]["outcome_evidence"]["groups"])
            self.assertEqual(fresh["audience_summary"]["outcome_evidence"]["mode"], "SYNTHETIC_ONLY")
        self.assertEqual(self.store.memory("other", "inventory")["groups"], [])
        self.assertEqual(len(model.requests), 0)
        self.assertEqual(self.count("review_decisions"), 2)

    def test_model_run_freezes_all_segments_before_concurrent_finalization(self):
        self.mature()
        model = FakeModel()
        app = build(self.path, lambda: self.now, model, ModelConfig("test/model"))
        database = app.learning.store.database
        connect = database.connect
        finalized = []

        class Cursor:
            def __init__(cursor_self, cursor):
                cursor_self.cursor = cursor

            def fetchall(cursor_self):
                rows = cursor_self.cursor.fetchall()
                if not finalized:
                    # Writer commits after the reader has established its WAL
                    # snapshot, before any later segment can be frozen.
                    finalized.append(self.finalize())
                return rows

        class Connection:
            def __init__(connection_self, connection):
                connection_self.connection = connection

            def __getattr__(connection_self, name):
                return getattr(connection_self.connection, name)

            def execute(connection_self, sql, *args):
                cursor = connection_self.connection.execute(sql, *args)
                if "SELECT b.* FROM learning_beliefs" in sql:
                    self.assertTrue(connection_self.connection.in_transaction)
                    return Cursor(cursor)
                return cursor

        @contextmanager
        def observed_connect():
            with connect() as db:
                yield Connection(db)

        with patch.object(database, "connect", observed_connect):
            run = app.start_model(self.scope, "concurrent-learning-freeze", size=100)
        self.assertEqual(len(finalized), 1)
        context_ids = app.tasks.inspect(self.scope, run)["tasks"][0]["inputs"]["context_ids"]
        for segment, identity in context_ids.items():
            frozen = app.memory.get_context(self.scope, identity)["audience_summary"]["outcome_evidence"]
            self.assertEqual(frozen["groups"], [], segment)
            self.assertEqual(len(app.learning.store.memory(self.scope, segment)["groups"]), 3)
        self.assertEqual(len(model.requests), 0)

    def test_learning_memory_does_not_leak_future_finalized_evidence(self):
        original_time = self.now
        self.mature()
        self.finalize()
        self.assertTrue(self.store.memory(self.scope, "inventory")["groups"])
        self.now = original_time
        self.assertEqual(self.store.memory(self.scope, "inventory")["groups"], [])

    def test_concurrent_conflicting_imports_have_one_immutable_winner(self):
        self.now = self.opened["window_end"]
        one = self.rows[0] | {"response": True, "observed_at": self.opened["window_start"]}
        two = self.rows[0] | {"response": False, "observed_at": self.opened["window_end"]}
        barrier = Barrier(2)
        def ingest(pair):
            key, row = pair
            barrier.wait()
            try:
                self.ingest([row], key)
                return row
            except Conflict:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(ingest, (("positive", one), ("negative", two))))
        winners = [r for r in results if r is not None]
        self.assertEqual(len(winners), 1)
        self.assertEqual(self.count("learning_outcomes"), 1)
        with self.store.database.connect() as db:
            self.assertEqual(json.loads(db.execute("SELECT payload FROM learning_outcomes").fetchone()[0]), winners[0])

    def test_nonfinite_clock_rejects_mutation_before_state_changes(self):
        for bad in (float("inf"), float("-inf"), float("nan")):
            self.now = bad
            with self.assertRaises(ValueError):
                self.ingest()
            with self.assertRaises(ValueError):
                self.finalize()
        self.assertEqual(self.count("learning_outcomes"), 0)
        self.assertEqual(self.count("learning_beliefs"), 0)
