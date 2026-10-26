import csv
import io
import json
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Barrier, Event

from acquisition.bootstrap import build
from acquisition.campaigns import Brief, build_draft
from acquisition.contracts import Conflict, NotFound
from acquisition.creative import fixture_catalog
from acquisition.reviews import ReviewPolicy, creatives_from
from acquisition.adapters.review_report import render_review
from acquisition.adapters.sqlite.database import Database
from acquisition.reasoning import ModelConfig
from test_model_copy import FakeModel


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "review.sqlite"
        self.now = 1792886400.0
        self.app = build(self.path, lambda: self.now)
        self.store = self.app.reviews.store
        self.pack = json.loads((Path(__file__).resolve().parents[1] / "config/iwoca-product-facts-v1.json").read_text())
        self.store.register_actor("one", "operator", ("operator",))
        self.store.register_actor("one", "human", ("reviewer",))
        self.store.activate("one", "operator", "evidence", self.pack, ReviewPolicy())
        self.run = self.app.start("one", "campaign", size=1000)
        self.app.worker.drain("one")
        self.opened = self.store.open_case("one", self.run, "operator")
        self.case = self.opened["case_id"]
        self.subject = self.opened["subject_id"]

    def approve(self, subject=None, key="approve", ttl=86400):
        return self.store.decide("one", self.case, subject or self.subject, "human", "approve", key,
                                 "Reviewed the exact synthetic audience and copy.", ttl)

    def handoff(self, approval, key="handoff"):
        return self.store.handoff("one", self.case, approval["id"], "operator", key)

    def count(self, table):
        with self.app.reviews.store.database.connect() as db:
            return db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]

    def mailed_business(self):
        view = self.store.view("one", self.case)
        draft = self.app.drafts.get("one", view["subject"]["draft_id"])
        return next(csv.DictReader(io.StringIO(draft.mailing_csv)))["business_id"]

    def suppress(self, key="suppression"):
        return self.store.suppress("one", "operator", key, self.mailed_business(), "Synthetic suppression received.")

    def test_exact_subject_and_actor_are_bound_to_persistent_approval(self):
        approval = self.approve()
        reopened = build(self.path, lambda: self.now)
        view = reopened.reviews.store.view("one", self.case)
        self.assertTrue(view["approval_valid"])
        self.assertEqual(view["approval"]["subject_id"], self.subject)
        self.assertEqual(view["approval"]["actor"], "human")
        self.assertEqual(view["subject"]["snapshot_id"], view["manifest"]["snapshot_id"])
        receipt = reopened.reviews.store.handoff("one", self.case, approval["id"], "operator", "handoff")
        self.assertEqual(receipt["recipients"], 681)
        self.assertEqual(receipt["mailing_sha256"], view["manifest"]["mailing_sha256"])
        self.assertEqual(receipt["mode"], "SYNTHETIC_NO_PRINT_NO_SEND")

    def test_suppression_invalidates_then_rebuild_requires_fresh_approval(self):
        old = self.approve()
        business = self.mailed_business()
        self.suppress()
        self.assertFalse(self.store.view("one", self.case)["approval_valid"])
        with self.assertRaises(Conflict):
            self.handoff(old)
        revised = self.app.reviews.refresh("one", self.case, self.subject, "operator", "refresh")
        view = self.store.view("one", self.case)
        self.assertNotEqual(revised["subject_id"], self.subject)
        self.assertTrue(view["candidate_valid"])
        self.assertFalse(view["approval_valid"])
        self.assertEqual(view["changes"]["removed_count"], 1)
        self.assertIn(business, view["changes"]["removed_preview"])
        with self.assertRaises(Conflict):
            self.approve(key="stale-browser")
        fresh = self.approve(revised["subject_id"], key="fresh")
        self.assertEqual(self.handoff(fresh)["recipients"], 680)
        self.assertEqual(self.count("simulated_agency_jobs"), 1)

    def test_evidence_aba_does_not_revive_old_approval(self):
        approval = self.approve()
        revised_pack = self.pack | {"version": "iwoca-flexi-loan/facts-v2"}
        self.store.activate("one", "operator", "new-evidence", revised_pack, ReviewPolicy())
        self.store.activate("one", "operator", "restored-evidence", self.pack, ReviewPolicy())
        with self.assertRaises(Conflict):
            self.handoff(approval)
        self.assertFalse(self.store.view("one", self.case)["approval_valid"])
        # Replaying an earlier activation is a receipt read, not a rollback.
        self.store.activate("one", "operator", "evidence", self.pack, ReviewPolicy())
        self.assertEqual(self.store.evidence("one")["evidence_epoch"], 3)
        revised = self.app.reviews.refresh("one", self.case, self.subject, "operator", "rebind-evidence")
        self.assertEqual(self.handoff(self.approve(revised["subject_id"], key="fresh"))["subject_id"], revised["subject_id"])

    def test_policy_changes_invalidate_and_limit_new_approval_lifetime(self):
        approval = self.approve()
        self.store.activate("one", "operator", "new-policy", self.pack, ReviewPolicy(max_approval_seconds=30))
        with self.assertRaises(Conflict):
            self.handoff(approval)
        revised = self.app.reviews.refresh("one", self.case, self.subject, "operator", "policy-refresh")
        with self.assertRaises(ValueError):
            self.approve(revised["subject_id"], key="over-limit", ttl=31)
        fresh = self.approve(revised["subject_id"], key="within-limit", ttl=30)
        self.assertEqual(fresh["expires_at"], self.now + 30)

    def test_expiry_is_enforced_at_the_exact_boundary(self):
        approval = self.approve(ttl=60)
        self.now += 60
        with self.assertRaises(Conflict):
            self.handoff(approval)
        self.assertFalse(self.store.view("one", self.case)["approval_valid"])
        self.assertEqual(self.count("simulated_agency_jobs"), 0)

    def test_approval_expiry_is_capped_by_product_evidence(self):
        from datetime import datetime, timezone
        self.now = datetime(2026, 11, 24, 23, 59, 30, tzinfo=timezone.utc).timestamp()
        approval = self.approve(ttl=60)
        self.assertEqual(approval["expires_at"], self.now + 30)
        self.now += 30
        with self.assertRaises(Conflict):
            self.handoff(approval)

    def test_reviewer_disable_and_reenable_cannot_revive_old_authority(self):
        approval = self.approve()
        self.store.register_actor("one", "human", ("reviewer",), False)
        self.store.register_actor("one", "human", ("reviewer",), True)
        with self.assertRaises(Conflict):
            self.handoff(approval)
        fresh = self.approve(key="review-again")
        self.assertGreater(fresh["actor_generation"], approval["actor_generation"])
        self.handoff(fresh)

    def test_revocation_and_later_rejection_block_earlier_approval(self):
        first = self.approve()
        self.store.revoke("one", self.case, first["id"], "human", "revoke", "Withdraw the synthetic approval.")
        with self.assertRaises(Conflict):
            self.handoff(first)
        second = self.approve(key="second")
        self.store.decide("one", self.case, self.subject, "human", "reject", "reject", "Needs another review.", 60)
        with self.assertRaises(Conflict):
            self.handoff(second, "second-handoff")

    def test_acknowledgement_never_becomes_review_approval(self):
        self.app.tasks.acknowledge("one", self.run, self.store.view("one", self.case)["subject"]["draft_id"], self.now)
        self.app.worker.drain("one")
        self.assertFalse(self.store.view("one", self.case)["approval_valid"])
        self.assertEqual(self.count("review_decisions"), 0)
        with self.assertRaises(NotFound):
            self.store.handoff("one", self.case, "invented", "operator", "handoff")

    def test_scope_roles_and_approval_case_substitution_are_rejected(self):
        approval = self.approve()
        with self.assertRaises(ValueError):
            self.store.decide("one", self.case, self.subject, "operator", "approve", "wrong-role", "Reason.", 60)
        with self.assertRaises(ValueError):
            self.store.handoff("one", self.case, approval["id"], "human", "wrong-operator")
        self.store.register_actor("two", "operator", ("operator",))
        self.store.register_actor("two", "human", ("reviewer",))
        with self.assertRaises(NotFound):
            self.store.view("two", self.case)
        with self.assertRaises(NotFound):
            self.store.decide("two", self.case, self.subject, "human", "approve", "wrong-scope", "Reason.", 60)
        other = self.app.start("one", "other", size=100)
        self.app.worker.drain("one")
        case = self.store.open_case("one", other, "operator")
        with self.assertRaises(NotFound):
            self.store.handoff("one", case["case_id"], approval["id"], "operator", "wrong-case")

    def test_lost_ack_replay_observes_one_job_even_after_expiry(self):
        approval = self.approve(ttl=10)
        receipt = self.handoff(approval)
        self.now += 20
        reopened = build(self.path, lambda: self.now)
        same = reopened.reviews.store.handoff("one", self.case, approval["id"], "operator", "handoff")
        fresh_key = reopened.reviews.store.handoff("one", self.case, approval["id"], "operator", "observe-accepted")
        self.assertEqual(receipt, same)
        self.assertEqual(receipt, fresh_key)
        self.assertEqual(self.count("simulated_agency_jobs"), 1)
        self.assertFalse(reopened.reviews.store.view("one", self.case)["approval_valid"])

    def test_request_replay_binds_inputs_and_refresh_is_idempotent(self):
        first = self.approve()
        self.assertEqual(first, self.approve())
        with self.assertRaises(Conflict):
            self.approve(ttl=60)
        self.suppress()
        one = self.app.reviews.refresh("one", self.case, self.subject, "operator", "refresh")
        self.assertEqual(one, self.app.reviews.refresh("one", self.case, self.subject, "operator", "refresh"))
        self.assertEqual(len(self.store.view("one", self.case)["revisions"]), 2)

    def test_run_cancellation_blocks_previously_valid_approval(self):
        approval = self.approve()
        self.app.tasks.cancel("one", self.run, self.now)
        with self.assertRaises(Conflict):
            self.handoff(approval)
        self.assertFalse(self.store.view("one", self.case)["approval_valid"])

    def test_edits_to_exported_files_do_not_change_accepted_bytes(self):
        approval = self.approve()
        view = self.store.view("one", self.case)
        path = self.app.export_review("one", self.case, self.root / "export")
        (path / "mailing.csv").write_text("edited projection")
        self.assertEqual(self.handoff(approval)["mailing_sha256"], view["manifest"]["mailing_sha256"])

    def test_stored_artifact_tampering_blocks_acceptance(self):
        approval = self.approve()
        with self.store.database.transaction() as db:
            db.execute("UPDATE drafts SET mailing='tampered' WHERE organization='one'")
        with self.assertRaises(Conflict):
            self.handoff(approval)
        self.assertEqual(self.count("simulated_agency_jobs"), 0)

    def test_decision_and_event_are_atomic(self):
        with self.store.database.connect() as db:
            db.execute("CREATE TRIGGER fail_review BEFORE INSERT ON review_events WHEN NEW.kind='review_approve' BEGIN SELECT RAISE(ABORT,'fixture'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.approve()
        self.assertEqual(self.count("review_decisions"), 0)
        self.assertFalse(self.store.view("one", self.case)["approval_valid"])
        with self.store.database.connect() as db:
            db.execute("DROP TRIGGER fail_review")
        self.handoff(self.approve())

    def test_simulated_acceptance_and_receipt_are_atomic(self):
        approval = self.approve()
        with self.store.database.connect() as db:
            db.execute("CREATE TRIGGER fail_accept BEFORE INSERT ON review_events WHEN NEW.kind='simulated_handoff_accepted' BEGIN SELECT RAISE(ABORT,'fixture'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.handoff(approval)
        self.assertEqual(self.count("simulated_agency_jobs"), 0)
        with self.store.database.connect() as db:
            db.execute("DROP TRIGGER fail_accept")
        self.handoff(approval)
        self.assertEqual(self.count("simulated_agency_jobs"), 1)

    def test_evidence_changes_during_preparation_fail_the_compare_and_swap(self):
        original = self.app.reviews.builder.refresh
        def intervening(*args):
            draft_id = original(*args)
            self.store.activate("one", "operator", "intervening", self.pack | {"version": "facts-new"}, ReviewPolicy())
            return draft_id
        self.app.reviews.builder.refresh = intervening
        with self.assertRaises(Conflict):
            self.app.reviews.refresh("one", self.case, self.subject, "operator", "refresh")
        self.assertEqual(self.store.view("one", self.case)["subject"]["id"], self.subject)

    def test_acceptance_reads_time_after_acquiring_its_write_lock(self):
        approval = self.approve(ttl=1)
        started = Event()
        def accept():
            started.set()
            with self.assertRaises(Conflict):
                self.handoff(approval)
        with ThreadPoolExecutor(max_workers=1) as pool:
            with self.store.database.transaction():
                future = pool.submit(accept)
                self.assertTrue(started.wait(5))
                self.now += 2
            future.result(timeout=10)
        self.assertEqual(self.count("simulated_agency_jobs"), 0)

    def test_concurrent_handoffs_create_one_simulated_job(self):
        approval = self.approve()
        barrier = Barrier(2)
        def accept(key):
            barrier.wait()
            return self.handoff(approval, key)
        with ThreadPoolExecutor(max_workers=2) as pool:
            receipts = list(pool.map(accept, ("first-handoff", "second-handoff")))
        self.assertEqual(receipts[0], receipts[1])
        self.assertEqual(self.count("simulated_agency_jobs"), 1)

    def test_suppression_and_handoff_have_a_valid_transaction_order(self):
        approval = self.approve()
        business = self.mailed_business()
        barrier = Barrier(2)
        def accept():
            barrier.wait()
            try:
                return self.handoff(approval)
            except Conflict:
                return None
        def suppress():
            barrier.wait()
            return self.store.suppress("one", "operator", "racing-suppression", business, "Synthetic update.")
        with ThreadPoolExecutor(max_workers=2) as pool:
            a, b = pool.submit(accept), pool.submit(suppress)
            receipt, _ = a.result(timeout=10), b.result(timeout=10)
        view = self.store.view("one", self.case)
        self.assertFalse(view["approval_valid"])
        if receipt:
            accepted = next(e["sequence"] for e in view["events"] if e["kind"] == "simulated_handoff_accepted")
            suppressed = next(e["sequence"] for e in view["events"] if e["kind"] == "suppression_added")
            self.assertLess(accepted, suppressed)
        else:
            self.assertEqual(self.count("simulated_agency_jobs"), 0)

    def test_new_case_after_suppression_can_be_rebuilt_without_a_dead_end(self):
        self.suppress()
        other = self.app.start("one", "later", size=1000)
        self.app.worker.drain("one")
        case = self.store.open_case("one", other, "operator")
        self.assertFalse(self.store.view("one", case["case_id"])["candidate_valid"])
        revised = self.app.reviews.refresh("one", case["case_id"], case["subject_id"], "operator", "new-case-refresh")
        self.assertTrue(self.store.view("one", case["case_id"])["candidate_valid"])
        self.assertNotEqual(case["subject_id"], revised["subject_id"])

    def test_copy_replacement_invalidates_old_approval_and_needs_current_grounding(self):
        approval = self.approve()
        model = FakeModel()
        app = build(self.path, lambda: self.now, model, ModelConfig("test/model", max_calls=10))
        run = app.start_model("one", "copy-revision", size=1000, campaign_id="campaign")
        app.worker.drain("one")
        state = app.tasks.inspect("one", run)
        draft_id = state["tasks"][-1]["output"]["draft_id"]
        revised = app.reviews.replace("one", self.case, self.subject, draft_id, "operator", "copy-replacement")
        self.assertTrue(self.store.view("one", self.case)["changes"]["copy_changed"])
        with self.assertRaises(Conflict):
            self.handoff(approval)
        fresh = self.approve(revised["subject_id"], key="copy-reviewed")
        self.handoff(fresh)
        self.assertEqual(len(model.requests), 6)  # Review and handoff issue no model calls.

    def test_forged_fixture_copy_cannot_bypass_grounding(self):
        view = self.store.view("one", self.case)
        snapshot = self.app.audiences.get("one", view["subject"]["snapshot_id"])
        copy = fixture_catalog()
        draft = build_draft(snapshot, Brief("campaign"), (replace(copy[0], opening="You are guaranteed funds."),) + copy[1:])
        self.app.drafts.put("one", "forged", draft)
        with self.assertRaises(Conflict):
            self.app.reviews.replace("one", self.case, self.subject, draft.id, "operator", "replace-forged")

    def test_fixture_identity_cannot_hide_changed_segment_metadata(self):
        view = self.store.view("one", self.case)
        snapshot = self.app.audiences.get("one", view["subject"]["snapshot_id"])
        original = fixture_catalog()
        swapped = tuple(replace(c, segment="contractors" if c.segment == "inventory" else "inventory") for c in original)
        self.assertEqual({c.id for c in original}, {c.id for c in swapped})
        draft = build_draft(snapshot, Brief("campaign"), swapped)
        self.app.drafts.put("one", "swapped-fixtures", draft)
        with self.assertRaises(Conflict):
            self.app.reviews.replace("one", self.case, self.subject, draft.id, "operator", "swap-fixtures")
        self.assertEqual(self.store.view("one", self.case)["subject"]["id"], self.subject)

    def test_readonly_report_escapes_untrusted_text(self):
        view = self.store.view("one", self.case)
        view["manifest"]["creatives"][0]["opening"] = '<script>alert("copy")</script>'
        html = render_review(view, "demo.sqlite")
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn(self.subject, html)
        self.assertIn("read-only", html)

    def test_review_clock_and_request_validation_leave_state_unchanged(self):
        before = self.count("review_decisions")
        self.now = float("inf")
        with self.assertRaises(ValueError):
            self.approve()
        self.assertEqual(self.count("review_decisions"), before)
