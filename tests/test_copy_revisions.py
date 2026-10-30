"""Copy-only scope, immutable admission, paid-call fencing and exact publication."""

import csv
import io
import json
import os
import subprocess
import sys
import tempfile
from threading import Event
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from acquisition.contracts import Conflict, NotFound
from acquisition.creative.grounding import product_suffix
from acquisition.reasoning import ModelError
from acquisition.reviews import ReviewPolicy
from acquisition.runtime import LeaseLost, TaskSpec
from acquisition.workspace import Workspace
from test_preparations import CombinedModel
from test_model_copy import reply


class RevisionModel(CombinedModel):
    def __init__(self):
        super().__init__()
        self.revision_calls = []
        self.change_sibling = False

    def complete(self, request):
        name = request["tools"][0]["function"]["name"]
        contexts = [json.loads(m["content"]) for m in request["messages"] if m["role"] == "tool" and '"copy_revision"' in m["content"]]
        revision = next((c for c in contexts if "copy_revision" in c), None)
        if revision or any('"copy_revision"' in (m.get("content") or "") for m in request["messages"]):
            self.revision_calls.append(request)
        if name == "submit_grounded_copy" and revision:
            args = {"guidance_id": revision["guidance"]["version"], "memory_id": revision["memory"][0]["id"], "fact_pack_id": revision["fact_pack_id"]}
            for base in revision["copy_revision"]["base_variants"]:
                arm = base["arm"].lower()
                fields = {"headline": base["headline"], "opening": base["opening"].removesuffix(product_suffix(revision["product_facts"], base["fact_id"])),
                          "hypothesis": base["hypothesis"], "fact_id": base["fact_id"]}
                if base["arm"] == revision["copy_revision"]["arm"]:
                    if base["headline"] != "When might project invoices fall due?":
                        fields["headline"] = "When might project invoices fall due?"
                        fields["opening"] = "If you are scheduling a project, when might client invoices fall due?"
                    else:
                        fields["headline"] = "Considering project payment dates?"
                        fields["opening"] = "For your planned project, when might client payments arrive?"
                elif self.change_sibling:
                    fields["headline"] = "A changed project hook?"
                args.update({k + "_" + arm: v for k, v in fields.items()})
            return reply(name, args)
        return super().complete(request)


class CopyRevisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = 1792972800.0
        self.model = RevisionModel()
        for p in (patch("acquisition.workspace.openrouter_key", return_value="fake"), patch("acquisition.workspace.OpenRouter", return_value=self.model)):
            p.start(); self.addCleanup(p.stop)
        self.w = Workspace(self.root, real_clock=lambda: self.now)
        self.c = self.w.create_conversation("conversation", "Revision campaign")["id"]
        self.w.message_conversation(self.c, "message", 0, "Prepare a £600 contractor campaign with model copy.")
        self.w.start_preparation(self.c, "prepare", 1, False, True)
        for _ in range(6): self.w.advance_preparations()
        self.sid = self.w.conversation(self.c)["campaigns"][0]["session_id"]
        self.base = self.w.view(self.sid)
        self.scope = self.w._session(self.sid)["organization"]
        self.app = self.w._app(self.w._session(self.sid))
        self.target = next(c for c in self.base["review"]["manifest"]["creatives"] if c["arm"] == "B")

    def admit(self, request="revision", state=None, target=None):
        state = state or self.base
        return self.w.request_copy_revision(self.sid, request, state["review"]["subject"]["id"],
            target or next(c["id"] for c in state["review"]["manifest"]["creatives"] if c["arm"] == "B"), "Make variant B more direct.", True)

    def finish(self):
        for _ in range(5):
            self.w.advance_copy_revisions()
            state = self.w.view(self.sid)
            if state["copy_revisions"][-1]["status"] not in {"admitted", "queued", "running"}:
                return state
        self.fail("Revision did not reach a bounded stopping state")

    def approve(self):
        return self.w.action(self.sid, "approve", {"request_id": "approval", "subject_id": self.base["review"]["subject"]["id"], "reason": "Reviewed the exact synthetic campaign."})

    def test_revision_preserves_population_other_letter_product_wording_and_money(self):
        approved = self.approve()
        admitted = self.admit()
        self.assertFalse(admitted["review"]["approval_valid"])
        with self.assertRaises(Conflict):
            self.w.action(self.sid, "handoff", {"request_id": "old-handoff", "approval_id": approved["review"]["approval"]["id"]})
        self.assertEqual(self.model.revision_calls, [])
        self.assertTrue(self.app.reviews.store.revision_request(self.scope, "revision")["inputs"]["allow_model_copy"])
        result = self.finish()
        self.assertEqual(result["copy_revisions"][0]["status"], "complete")
        self.assertTrue(result["review"]["candidate_valid"], result["review"]["blocked_reasons"])
        self.assertFalse(result["review"]["approval_valid"])
        old, new = self.base["review"], result["review"]
        self.assertNotEqual(old["subject"]["id"], new["subject"]["id"])
        self.assertEqual(old["subject"]["snapshot_id"], new["subject"]["snapshot_id"])
        for field in ("brief", "counts", "arm_counts", "variable_cost_pence", "exclusion_reasons"):
            self.assertEqual(old["manifest"][field], new["manifest"][field])
        letters = {c["arm"]: c for c in new["manifest"]["creatives"]}
        original = {c["arm"]: c for c in old["manifest"]["creatives"]}
        for field in ("id", "headline", "opening", "hypothesis", "locked_block", "fact_id"):
            self.assertEqual(original["A"][field], letters["A"][field])
        self.assertNotEqual(original["B"]["id"], letters["B"]["id"])
        self.assertEqual(letters["B"]["headline"], "When might project invoices fall due?")
        self.assertEqual(original["B"]["fact_id"], letters["B"]["fact_id"])
        self.assertEqual([(r["id"], r["arm"]) for r in self.base["audience"]], [(r["id"], r["arm"]) for r in result["audience"]])
        self.assertIsNone(result["learning"])
        self.assertEqual(len(self.model.revision_calls), 1)  # Only the proposal sees copy feedback; the critic does not.
        self.assertEqual(len(self.app.calls.inspect(self.scope, result["copy_revisions"][0]["run_id"])), 3)
        self.assertEqual(self.app.drafts.get(self.scope, old["subject"]["draft_id"]).manifest, old["manifest"])

    def test_replay_uses_original_receipt_without_keys_calls_or_another_subject(self):
        self.admit(); result = self.finish()
        before = len(self.model.revision_calls)
        with patch("acquisition.workspace.OpenRouter", side_effect=AssertionError("No model adapter is needed on replay")):
            replay = self.admit()
        self.assertTrue(replay["command_replayed"])
        self.assertEqual(replay["review"]["subject"], result["review"]["subject"])
        self.assertEqual(len(self.model.revision_calls), before)
        self.assertEqual(len(replay["review"]["revisions"]), 2)
        self.assertEqual(len([e for e in replay["review"]["events"] if e["kind"] == "copy_revision_requested"]), 1)
        with self.assertRaises(Conflict):
            self.w.request_copy_revision(self.sid, "revision", self.base["review"]["subject"]["id"], self.target["id"], "Different feedback.", True)

    def test_admission_and_rejection_are_atomic(self):
        self.approve()
        from acquisition.adapters.sqlite.reviews import SqliteReviews
        original = SqliteReviews._event
        def fail(store, db, organization, case_id, kind, payload, now):
            if kind == "copy_revision_requested": raise OSError("Injected audit failure")
            return original(store, db, organization, case_id, kind, payload, now)
        with patch.object(SqliteReviews, "_event", new=fail), self.assertRaises(OSError): self.admit()
        view = self.w.view(self.sid)
        self.assertTrue(view["review"]["approval_valid"])
        self.assertEqual(view["copy_revisions"], [])
        self.assertEqual(self.model.revision_calls, [])

    def test_new_keys_cannot_repeat_a_subject_and_three_revisions_bound_the_case(self):
        self.admit()
        with self.assertRaises(Conflict): self.admit("different")
        state = self.finish()
        for i in (2, 3):
            self.admit("revision-" + str(i), state)
            state = self.finish()
            self.assertEqual(state["copy_revisions"][-1]["status"], "complete")
        with self.assertRaises(Conflict): self.admit("revision-4", state)
        self.assertEqual(len(state["copy_revisions"]), 3)

    def test_concurrent_revision_admissions_have_one_winner(self):
        def request(key):
            try:
                w = Workspace(self.root, real_clock=lambda: self.now)
                w.request_copy_revision(self.sid, key, self.base["review"]["subject"]["id"], self.target["id"], "Make variant B more direct.", True)
                return True
            except Conflict: return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(request, ["one", "two"])), 1)
        self.assertEqual(len(self.w.view(self.sid)["copy_revisions"]), 1)
        self.assertEqual(self.model.revision_calls, [])

    def test_model_cannot_change_the_other_variant(self):
        self.model.change_sibling = True
        self.admit(); result = self.finish()
        self.assertEqual(result["copy_revisions"][0]["status"], "failed")
        self.assertEqual(result["review"]["subject"], self.base["review"]["subject"])
        self.assertLessEqual(len(self.app.calls.inspect(self.scope, result["copy_revisions"][0]["run_id"])), 5)

    def test_unknown_and_interrupted_calls_survive_restart_without_repeat(self):
        for interrupted in (False, True):
            if interrupted:
                # A new source subject is required to make a separate deliberate request.
                self.w.action(self.sid, "refresh", {"request_id": "new-subject", "subject_id": self.base["review"]["subject"]["id"]})
                self.base = self.w.view(self.sid)
            self.admit("crash" if interrupted else "timeout")
            with patch.object(self.model, "complete", side_effect=KeyboardInterrupt() if interrupted else ModelError("provider_request_failed")):
                if interrupted:
                    with self.assertRaises(KeyboardInterrupt): self.w.advance_copy_revisions()
                else: self.w.advance_copy_revisions()
            reopened = Workspace(self.root, real_clock=lambda: self.now)
            reopened.recover_copy_revisions()
            result = reopened.view(self.sid)
            self.assertEqual(result["copy_revisions"][-1]["status"], "uncertain")
            self.assertTrue(result["copy_revisions"][-1]["generation"]["unresolved_calls"])
            with patch.object(self.model, "complete", side_effect=AssertionError("Never repeat uncertain inference")): reopened.advance_copy_revisions()

    def test_missing_key_blocks_admitted_revision_durably_and_resumes_original_request(self):
        from acquisition.adapters.openrouter import OpenRouter
        self.admit()
        receipt = self.app.reviews.store.revision_request(self.scope, "revision")
        with patch("acquisition.workspace.openrouter_key", return_value=""), patch("acquisition.workspace.OpenRouter", side_effect=OpenRouter):
            self.w.advance_copy_revisions()
            self.w.advance_copy_revisions()
        reopened = Workspace(self.root, real_clock=lambda: self.now)
        row = reopened.view(self.sid)["copy_revisions"][0]
        self.assertEqual(row["status"], "blocked")
        self.assertEqual(row["block"]["code"], "configuration_unavailable")
        self.assertIn("Restore", row["block"]["detail"])
        self.assertIsNone(row["run_id"])
        self.assertEqual(self.model.revision_calls, [])
        self.assertEqual(self.app.reviews.store.revision_request(self.scope, "revision"), receipt)
        self.assertEqual(self.admit()["copy_revisions"][0]["id"], row["id"])
        result = self.finish()["copy_revisions"][0]
        self.assertEqual(result["status"], "complete")
        self.assertIsNone(result["block"])
        self.assertEqual(result["id"], receipt["id"])
        self.assertEqual(result["run_id"], self.app.tasks.find_run(self.scope, receipt["id"]))
        self.assertEqual(len(self.app.reviews.store.revision_requests(self.scope, self.base["review"]["case_id"])), 1)

    def test_restored_configuration_exposes_running_progress_during_a_delayed_provider_call(self):
        self.admit()
        with patch("acquisition.workspace.openrouter_key", side_effect=ModelError("missing-key")):
            self.w.advance_copy_revisions()
        blocked = self.w.view(self.sid)["copy_revisions"][0]
        self.assertEqual(blocked["status"], "blocked")
        started, release = Event(), Event()
        original = self.model.complete

        def delayed(request):
            started.set()
            if not release.wait(10):
                raise AssertionError("Test did not release the delayed provider")
            return original(request)

        with patch.object(self.model, "complete", side_effect=delayed), ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.w.advance_copy_revisions)
            try:
                self.assertTrue(started.wait(5), "Restored request never reached the provider")
                for _ in range(2):
                    row = Workspace(self.root, real_clock=lambda: self.now).view(self.sid)["copy_revisions"][0]
                    self.assertEqual(row["id"], blocked["id"])
                    self.assertEqual(row["status"], "running")
                    self.assertIsNone(row["block"])
                    self.assertEqual(row["generation"]["status"], "running")
                    self.assertTrue(row["generation"]["outcome_uncertain"])
                    self.assertEqual(row["generation"]["unresolved_calls"][0]["status"], "reserved")
            finally:
                release.set()
            future.result(timeout=5)
        completed = self.finish()["copy_revisions"][0]
        self.assertEqual(completed["status"], "complete")
        self.assertEqual(completed["run_id"], row["run_id"])
        self.assertIsNone(completed["block"])
        self.assertFalse(completed["generation"]["outcome_uncertain"])

    def test_changed_model_settings_block_queued_revision_without_consuming_attempts(self):
        from dataclasses import replace
        self.admit()
        receipt = self.app.reviews.store.revision_request(self.scope, "revision")
        original_app = self.w._app
        run = original_app(self.w._session(self.sid), with_model=True).revisions.reconcile(self.scope, receipt)
        before = self.app.tasks.inspect(self.scope, run)

        def wrong_settings(session, with_model=False):
            app = original_app(session, with_model=with_model)
            if with_model:
                app.revisions.config = replace(app.revisions.config, model="private-model-setting")
            return app

        with patch.object(self.w, "_app", side_effect=wrong_settings):
            self.w.advance_copy_revisions()
        row = self.w.view(self.sid)["copy_revisions"][0]
        self.assertEqual(row["status"], "blocked")
        self.assertEqual(row["run_id"], run)
        self.assertEqual(row["block"]["code"], "configuration_unavailable")
        self.assertNotIn("private-model-setting", json.dumps(row))
        self.assertEqual(self.app.tasks.inspect(self.scope, run), before)
        self.assertEqual(self.model.revision_calls, [])
        completed = self.finish()["copy_revisions"][0]
        self.assertEqual(completed["status"], "complete")
        self.assertEqual(completed["run_id"], run)
        self.assertIsNone(completed["block"])

    def test_expired_evidence_blocks_one_revision_without_starving_a_later_campaign(self):
        c = self.w.create_conversation("later-conversation", "Later campaign")["id"]
        self.w.message_conversation(c, "message", 0, "Prepare a £600 contractor campaign with model copy.")
        self.w.start_preparation(c, "later-prepare", 1, False, True)
        for _ in range(6): self.w.advance_preparations()
        later = self.w.conversation(c)["campaigns"][0]["session_id"]
        later_state = self.w.view(later)
        later_target = next(c["id"] for c in later_state["review"]["manifest"]["creatives"] if c["arm"] == "B")
        self.admit()
        self.w.request_copy_revision(later, "later-revision", later_state["review"]["subject"]["id"], later_target, "Make B more direct.", True)
        receipt = self.app.reviews.store.revision_request(self.scope, "revision")
        session = self.w._session(self.sid)
        session["clock"] = self.now + 31 * 86400
        self.w._save(session)
        for _ in range(4): self.w.advance_copy_revisions()
        blocked = Workspace(self.root, real_clock=lambda: self.now).view(self.sid)["copy_revisions"][0]
        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(blocked["block"]["code"], "evidence_unavailable")
        self.assertIn("frozen inputs", blocked["block"]["detail"])
        self.assertIsNone(blocked["run_id"])
        self.assertEqual(self.app.reviews.store.revision_request(self.scope, "revision"), receipt)
        self.assertEqual(self.w.view(later)["copy_revisions"][0]["status"], "complete")
        later_scope = self.w._session(later)["organization"]
        with self.w.control() as db:
            self.assertIsNone(db.execute("SELECT code FROM copy_revision_blocks WHERE organization=? AND revision_id=?", (later_scope, blocked["id"])).fetchone())

    def test_source_changes_during_inference_fence_later_calls_and_publication(self):
        for change in ("message", "evidence", "suppression", "operator", "run"):
            with self.subTest(change=change):
                # Reset a fresh case for every independent interleaving.
                self.setUp_case_change(change)

    def setUp_case_change(self, change):
        with tempfile.TemporaryDirectory() as root:
            w = Workspace(root, real_clock=lambda: self.now)
            c = w.create_conversation("c", "Fresh")["id"]; w.message_conversation(c, "m", 0, "Prepare £600 for contractors with model copy.")
            w.start_preparation(c, "p", 1, False, True)
            for _ in range(6): w.advance_preparations()
            sid = w.conversation(c)["campaigns"][0]["session_id"]; base = w.view(sid)
            scope = w._session(sid)["organization"]; app = w._app(w._session(sid))
            target = next(x["id"] for x in base["review"]["manifest"]["creatives"] if x["arm"] == "B")
            w.request_copy_revision(sid, "r", base["review"]["subject"]["id"], target, "Make the hook more direct.", True)
            original = self.model.complete
            def interleave(request):
                result = original(request)
                if change == "message": w.message_conversation(c, "edit", 1, "Use £300 instead.")
                elif change == "evidence": app.reviews.store.activate(scope, "local-operator", "policy-change", app.reviews.store.evidence(scope)["pack"], ReviewPolicy(max_approval_seconds=60))
                elif change == "suppression": app.reviews.store.suppress(scope, "local-operator", "suppress", next(r["id"] for r in base["audience"] if r["arm"] == "B"), "New suppression.")
                elif change == "operator": app.reviews.store.register_actor(scope, "local-operator", ("operator",), enabled=False)
                else: app.tasks.cancel(scope, base["session"]["run_id"], self.now)
                return result
            with patch.object(self.model, "complete", side_effect=interleave) as dispatch: w.advance_copy_revisions()
            self.assertEqual(dispatch.call_count, 1)
            w.advance_copy_revisions()
            self.assertEqual(w.view(sid)["review"]["subject"], base["review"]["subject"])

    def test_expired_publication_lease_cannot_publish(self):
        self.admit(); self.w.advance_copy_revisions()
        row = self.w.view(self.sid)["copy_revisions"][0]
        app = self.w._app(self.w._session(self.sid), with_model=True)
        claim = app.tasks.claim(self.scope, self.now, 1, run_id=row["run_id"])
        self.now += 1
        with self.assertRaises(LeaseLost): app.worker.capabilities[claim.capability](claim)
        self.assertEqual(self.w.view(self.sid)["review"]["subject"], self.base["review"]["subject"])

    def test_publication_rechecks_the_lease_after_validation(self):
        self.admit(); self.w.advance_copy_revisions()
        row = self.w.view(self.sid)["copy_revisions"][0]
        app = self.w._app(self.w._session(self.sid), with_model=True)
        claim = app.tasks.claim(self.scope, self.now, 1, run_id=row["run_id"])
        original = app.reviews.store._validate
        def expire(*args):
            result = original(*args); self.now += 1; return result
        with patch.object(app.reviews.store, "_validate", side_effect=expire), self.assertRaises(LeaseLost): app.worker.capabilities[claim.capability](claim)
        self.assertEqual(self.w.view(self.sid)["review"]["subject"], self.base["review"]["subject"])

    def test_recorded_generation_replays_after_worker_loss_without_more_model_calls(self):
        self.admit()
        receipt = self.app.reviews.store.revision_requests(self.scope, self.base["review"]["case_id"])[0]
        app = self.w._app(self.w._session(self.sid), with_model=True)
        run = app.revisions.reconcile(self.scope, receipt)
        claim = app.tasks.claim(self.scope, self.now, 1, run_id=run)
        app.worker.capabilities[claim.capability](claim)  # Domain result committed, task acknowledgement lost.
        before = len(self.model.revision_calls)
        self.now += 2
        result = self.finish()
        self.assertEqual(result["copy_revisions"][0]["status"], "complete")
        self.assertEqual(len(self.model.revision_calls), before)

    def test_publication_receipt_replay_survives_later_conversation_edits(self):
        self.admit(); self.w.advance_copy_revisions()
        row = self.w.view(self.sid)["copy_revisions"][0]
        app = self.w._app(self.w._session(self.sid), with_model=True)
        claim = app.tasks.claim(self.scope, self.now, 1, run_id=row["run_id"])
        first = app.worker.capabilities[claim.capability](claim)
        self.w.message_conversation(self.c, "edit", 1, "Use £300 instead.")
        self.now += 2
        self.w.advance_copy_revisions()
        self.assertEqual(self.w.view(self.sid)["copy_revisions"][0]["published_subject_id"], first.data["subject_id"])
        self.assertEqual(len(self.w.view(self.sid)["review"]["revisions"]), 2)

    def test_another_run_cannot_reuse_a_paid_revision_admission(self):
        self.admit()
        receipt = self.app.reviews.store.revision_requests(self.scope, self.base["review"]["case_id"])[0]
        app = self.w._app(self.w._session(self.sid), with_model=True)
        run = app.revisions.reconcile(self.scope, receipt)
        state = app.tasks.inspect(self.scope, run)
        fork = app.tasks.create(self.scope, "unauthorized-fork", [TaskSpec(t["capability"], t["inputs"]) for t in state["tasks"]], self.now)
        app.worker.drain(self.scope, run_id=fork)
        self.assertEqual(self.model.revision_calls, [])
        self.assertEqual(app.tasks.inspect(self.scope, fork)["run"]["status"], "failed")
        self.assertEqual(self.finish()["copy_revisions"][0]["status"], "complete")

    def test_rejected_inputs_and_scope_create_no_revision_or_model_call(self):
        with self.assertRaises(ValueError): self.w.request_copy_revision(self.sid, "r", self.base["review"]["subject"]["id"], self.target["id"], "Make it direct.", False)
        with self.assertRaises(Conflict): self.w.request_copy_revision(self.sid, "r", "subject_other", self.target["id"], "Make it direct.", True)
        with self.assertRaises(NotFound): self.w._app(self.w._session(self.sid), with_model=True).revisions.admit("other", self.base["review"]["case_id"], "r", self.base["review"]["subject"]["id"], self.target["id"], "Make it direct.", True)
        self.assertEqual(self.w.view(self.sid)["copy_revisions"], [])
        self.assertEqual(self.model.revision_calls, [])

    def test_admitted_revision_recovers_in_a_fresh_process_without_browser_state(self):
        self.admit()
        code = '''
import sys
from unittest.mock import patch
from acquisition.workspace import Workspace
from test_copy_revisions import RevisionModel
with patch('acquisition.workspace.openrouter_key', return_value='fake'), patch('acquisition.workspace.OpenRouter', return_value=RevisionModel()):
    w=Workspace(sys.argv[1], real_clock=lambda:1792972800.0)
    [w.advance_copy_revisions() for _ in range(3)]
'''
        result = subprocess.run([sys.executable, "-c", code, str(self.root)], env=dict(os.environ, PYTHONPATH=os.pathsep.join((str(Path('src').resolve()), str(Path('tests').resolve())))), capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.w.view(self.sid)["copy_revisions"][0]["status"], "complete")

    def test_read_packet_cannot_combine_old_letters_with_a_new_publication(self):
        self.admit(); self.w.advance_copy_revisions()
        original = self.w._copy_revision_progress
        once = []
        def publish_during_read(app, scope, case):
            if not once:
                once.append(True)
                self.w.advance_copy_revisions()
            return original(app, scope, case)
        with patch.object(self.w, "_copy_revision_progress", side_effect=publish_during_read):
            packet = self.w.view(self.sid)
        self.assertEqual(packet["review"]["subject"]["id"], packet["copy_revisions"][0]["published_subject_id"])
        self.assertEqual(next(c["headline"] for c in packet["review"]["manifest"]["creatives"] if c["arm"] == "B"), "When might project invoices fall due?")

    def test_read_packet_cannot_combine_old_approval_with_an_admitted_revision(self):
        approved = self.approve()
        self.assertTrue(approved["review"]["approval_valid"])
        writer = Workspace(self.root, real_clock=lambda: self.now)
        original = self.w._copy_revision_progress
        admissions = []

        def admit_during_read(app, scope, case):
            if not admissions:
                admissions.append(writer.request_copy_revision(self.sid, "revision", self.base["review"]["subject"]["id"],
                    self.target["id"], "Make variant B more direct.", True))
            return original(app, scope, case)

        with patch.object(self.w, "_copy_revision_progress", side_effect=admit_during_read):
            packet = self.w.view(self.sid)
        self.assertEqual(len(admissions), 1)
        self.assertEqual(packet["review"]["subject"]["id"], approved["review"]["subject"]["id"])
        self.assertEqual(packet["copy_revisions"][0]["status"], "admitted")
        self.assertFalse(packet["review"]["approval_valid"])
        self.assertEqual(packet["review"]["approval"]["decision"], "reject")
        self.assertTrue(any(e["kind"] == "copy_revision_requested" for e in packet["review"]["events"]))
        reopened = Workspace(self.root, real_clock=lambda: self.now).view(self.sid)
        self.assertEqual(packet["review"], reopened["review"])
        self.assertEqual(self.model.revision_calls, [])

    def test_copy_scope_validator_rejects_an_untargeted_letter_change(self):
        from dataclasses import replace
        from acquisition.campaigns import brief_from, build_draft, validate_copy_revision
        from acquisition.reviews import creatives_from
        self.admit(); candidate = self.finish()
        before = self.app.drafts.get(self.scope, self.base["review"]["subject"]["draft_id"])
        after = self.app.drafts.get(self.scope, candidate["review"]["subject"]["draft_id"])
        variants = tuple(replace(c, headline="Changed project question?") if c.arm == "A" else c for c in creatives_from(after))
        snapshot = self.app.audiences.get(self.scope, after.manifest["snapshot_id"])
        substituted = build_draft(snapshot, brief_from(after.manifest["brief"]), variants)
        with self.assertRaises(Conflict): validate_copy_revision(before, substituted, self.target["id"])

    def test_an_unrelated_rebuild_receipt_cannot_masquerade_as_copy_publication(self):
        self.admit()
        request = self.app.reviews.store.revision_request(self.scope, "revision")
        self.w.action(self.sid, "refresh", {"request_id": request["id"] + ":publish", "subject_id": self.base["review"]["subject"]["id"]})
        row = self.w.view(self.sid)["copy_revisions"][0]
        self.assertEqual(row["status"], "stale")
        self.assertIsNone(row["published_subject_id"])
        self.assertIsNone(row["run_id"])
        self.w.advance_copy_revisions()
        self.assertEqual(self.model.revision_calls, [])
