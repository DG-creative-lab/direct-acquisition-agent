"""Continuation contracts against real SQLite, task leases and inference journals."""

import os
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from unittest.mock import patch

from acquisition.contracts import Conflict, NotFound
from acquisition.conversations import FIXTURE_MESSAGE
from acquisition.reasoning import ModelError
from acquisition.workspace import Workspace
from test_conversations import PlannerModel, proposal
from test_model_copy import FakeModel, reply


class CombinedModel:
    def __init__(self, result=None):
        self.planner = PlannerModel(result or proposal(copy_mode="model"))
        self.copy = FakeModel()

    def complete(self, request):
        if request["tools"][0]["function"]["name"] == "submit_campaign_brief":
            return self.planner.complete(request)
        return self.copy.complete(request)


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = 1792972800.0
        self.w = self.open()
        self.model = CombinedModel()
        for patcher in (patch("acquisition.workspace.openrouter_key", return_value="fixture"),
                        patch("acquisition.workspace.OpenRouter", return_value=self.model)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.c = self.w.create_conversation("c", "Continuous contractor experiment")["id"]

    def open(self):
        return Workspace(self.root, real_clock=lambda: self.now)

    def admit(self, fixture=False, consent=True, request="prepare"):
        message = FIXTURE_MESSAGE if fixture else "Prepare a £600 contractor experiment with model copy."
        self.w.message_conversation(self.c, "m1", 0, message)
        return self.w.start_preparation(self.c, request, 1, fixture, consent and not fixture)["preparations"][0]

    def finish(self, workspace=None):
        w = workspace or self.w
        for _ in range(10):
            w.advance_preparations()
            row = w.conversation(self.c)["preparations"][0]
            if row["status"] not in {"admitting", "planning", "preparing"}:
                return row
        self.fail("Preparation did not reach a bounded stopping state")

    def assert_no_release(self, w=None):
        app = (w or self.w)._conversation_app()
        with app.tasks.database.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM review_decisions").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM simulated_agency_jobs").fetchone()[0], 0)

    def test_one_authorized_request_reaches_exact_unapproved_model_draft(self):
        row = self.admit()
        self.assertEqual(row["status"], "planning")
        self.assertEqual(self.model.planner.requests, [])
        self.assertEqual(self.model.copy.requests, [])
        frozen = self.w._conversation_app().conversations.store.snapshot("local-conversations", self.c)["admissions"][0]
        self.assertIn("playbooks", frozen["knowledge"])
        self.assertEqual(frozen["model_config"]["max_calls"], 2)
        self.assertEqual(self.finish()["status"], "review_ready")
        view = self.w.conversation(self.c)
        campaign = self.w.view(view["campaigns"][0]["session_id"])
        self.assertTrue(campaign["review"]["candidate_valid"])
        self.assertFalse(campaign["review"]["approval_valid"])
        self.assertEqual(campaign["review"]["manifest"]["brief"]["budget_pence"], 60000)
        self.assertEqual(campaign["review"]["manifest"]["brief"]["segments"], ["contractors"])
        self.assertEqual(len(self.model.planner.requests), 1)
        self.assertEqual(len(self.model.copy.requests), 3)
        self.assert_no_release()
        for _ in range(2):
            self.w.start_preparation(self.c, "prepare", 1, False, True)
            self.w.advance_preparations()
        self.assertEqual(len(self.model.copy.requests), 3)
        self.assertEqual(len(self.w.listing()["sessions"]), 1)

    def test_explicit_copy_consent_cannot_be_expanded_by_replay_or_new_key(self):
        row = self.admit(consent=False)
        self.assertEqual(self.finish()["status"], "needs_consent")
        self.assertEqual(self.w.listing()["sessions"], [])
        self.assertEqual(self.model.copy.requests, [])
        for key in ("prepare", "different"):
            with self.assertRaises(Conflict):
                self.w.start_preparation(self.c, key, 1, False, True)
        with self.assertRaises(NotFound):
            self.w.preparations.store.get("another-organization", row["id"])
        self.assertEqual(self.w.preparations.store.listing("another-organization"), [])
        self.assert_no_release()

    def test_clarification_creates_no_campaign(self):
        self.model.planner.results = [proposal(outcome="clarification", question="What total budget should I use?", budget_pence=None, segments=[])]
        self.admit()
        self.assertEqual(self.finish()["status"], "needs_input")
        self.assertEqual(self.w.listing()["sessions"], [])
        self.assertEqual(self.model.copy.requests, [])

    def test_restart_and_lost_status_write_reuse_original_draft(self):
        self.admit(fixture=True)
        self.w.advance_preparations()
        row = self.w.preparations.store.listing("local-conversations")[0]
        # Draft/session commits may succeed before the coordinator status write.
        for _ in range(3):
            self.w.step_preparation_campaign("local-conversations", row, self.w.preparation_source("local-conversations", self.c)["current_plan"]["result"])
        before = self.w.conversation(self.c)["campaigns"][0]
        w = self.open()
        self.assertEqual(self.finish(w)["status"], "review_ready")
        self.assertEqual(w.conversation(self.c)["campaigns"][0]["case_id"], before["case_id"])
        self.assertEqual(len(w.listing()["sessions"]), 1)
        self.assertEqual(self.model.planner.requests, [])
        self.assertEqual(self.model.copy.requests, [])
        self.assert_no_release(w)

    def test_real_process_restart_resumes_a_queued_fixture(self):
        self.admit(fixture=True)
        env = dict(os.environ, PYTHONPATH=str(Path("src").resolve()))
        code = "from acquisition.workspace import Workspace; import sys; w=Workspace(sys.argv[1]); [w.advance_preparations() for _ in range(6)]"
        result = subprocess.run([sys.executable, "-c", code, str(self.root)], env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.w.conversation(self.c)["preparations"][0]["status"], "review_ready")
        self.assert_no_release()

    def test_failed_coordinator_write_cannot_leave_a_plan_or_task(self):
        with patch.object(self.w.preparations.store, "create", side_effect=OSError("lost admission")):
            with self.assertRaises(OSError):
                self.admit(fixture=True)
        self.assertEqual(len(self.w._conversation_app().conversations.store.snapshot("local-conversations", self.c)["admissions"]), 0)
        self.assertEqual(self.w.preparations.store.listing("local-conversations"), [])
        self.w.start_preparation(self.c, "prepare", 1, True, False)
        self.assertEqual(self.finish()["status"], "review_ready")
        self.assertEqual(self.model.planner.requests, [])

    def test_concurrent_identical_admission_creates_one_coordinator(self):
        self.w.message_conversation(self.c, "m1", 0, FIXTURE_MESSAGE)
        def admit():
            return self.open().start_preparation(self.c, "prepare", 1, True, False)["preparations"][0]["id"]
        with ThreadPoolExecutor(max_workers=2) as pool:
            ids = list(pool.map(lambda _: admit(), range(2)))
        self.assertEqual(ids[0], ids[1])
        self.assertEqual(len(self.w.preparations.store.listing("local-conversations")), 1)
        self.assertEqual(self.finish()["status"], "review_ready")

    def test_edit_during_model_call_stops_copy_and_progress_reads_do_not_block(self):
        self.admit()
        entered, release = Event(), Event()
        original = self.model.complete
        def delayed(request):
            entered.set()
            self.assertTrue(release.wait(5))
            return original(request)
        with patch.object(self.model, "complete", side_effect=delayed), ThreadPoolExecutor(max_workers=2) as pool:
            future = pool.submit(self.w.advance_preparations)
            self.assertTrue(entered.wait(5))
            try:
                read = pool.submit(self.w.conversation, self.c).result(timeout=2)
                self.assertEqual(read["preparations"][0]["status"], "planning")
                pool.submit(self.w.message_conversation, self.c, "m2", 1, "Use £300 instead.").result(timeout=2)
            finally:
                release.set()
            future.result(timeout=10)
        self.assertEqual(self.finish()["status"], "stale")
        self.assertEqual(self.model.copy.requests, [])
        self.assertEqual(self.w.listing()["sessions"], [])

    def test_unknown_provider_result_is_terminal_and_never_retried(self):
        self.admit()
        with patch.object(self.model, "complete", side_effect=ModelError("provider_request_failed")):
            row = self.finish()
        self.assertEqual(row["status"], "uncertain")
        self.assertIn("charged", row["detail"])
        before = self.w._conversation_app().calls.inspect("local-conversations", row["run_id"])
        self.open().advance_preparations()
        self.w.start_preparation(self.c, "prepare", 1, False, True)
        self.assertEqual(self.w._conversation_app().calls.inspect("local-conversations", row["run_id"]), before)
        self.assertEqual(self.model.copy.requests, [])

    def test_interrupted_reservation_is_reported_on_restart_before_dispatch(self):
        self.admit()
        with patch.object(self.model, "complete", side_effect=KeyboardInterrupt()):
            with self.assertRaises(KeyboardInterrupt):
                self.w.advance_preparations()
        w = self.open()
        w.preparations.recover("local-conversations")
        self.assertEqual(w.conversation(self.c)["preparations"][0]["status"], "uncertain")
        w.advance_preparations()
        self.assertEqual(self.model.planner.requests, [])
        self.assertEqual(self.model.copy.requests, [])

    def test_known_auth_failure_and_unrelated_plan_are_not_retried(self):
        self.admit()
        other = self.w.create_conversation("other", "Unrelated")["id"]
        self.w.message_conversation(other, "message", 0, "Use £600 for contractors.")
        app = self.w._conversation_app(with_model=True)
        unrelated = app.conversations.plan("local-conversations", other, "other-plan", 1)
        with patch.object(self.model, "complete", side_effect=ModelError("provider_http_401")):
            self.assertEqual(self.finish()["status"], "failed")
        self.assertEqual(app.tasks.inspect("local-conversations", unrelated)["run"]["status"], "queued")
        self.assertEqual(self.model.copy.requests, [])

    def test_revised_brief_invalidates_review_approval_after_continuous_preparation(self):
        self.admit(fixture=True)
        self.finish()
        campaign = self.w.view(self.w.conversation(self.c)["campaigns"][0]["session_id"])
        session = campaign["session"]["id"]
        approval = self.w.action(session, "approve", {"request_id": "approve", "subject_id": campaign["review"]["subject"]["id"], "reason": "Reviewed the exact synthetic experiment."})
        self.w.message_conversation(self.c, "m2", 1, "Use £300 instead.")
        self.assertFalse(self.w.view(session)["review"]["approval_valid"])
        with self.assertRaises(Conflict):
            self.w.action(session, "handoff", {"request_id": "handoff", "approval_id": approval["review"]["approval"]["id"]})

    def test_edit_before_planner_repair_prevents_a_second_provider_call(self):
        self.admit()
        def edit_and_return_invalid(request):
            self.w.message_conversation(self.c, "correction", 1, "Use £300 instead.")
            return reply("submit_campaign_brief", proposal(budget_pence=70000))
        with patch.object(self.model, "complete", side_effect=edit_and_return_invalid) as dispatch:
            self.w.advance_preparations()
        self.assertEqual(dispatch.call_count, 1)
        self.assertEqual(self.finish()["status"], "stale")
        self.assertEqual(self.model.copy.requests, [])

    def test_edit_during_copy_stops_further_calls_and_draft_commit(self):
        self.admit()
        self.w.advance_preparations()  # Plan, then audience validation.
        self.w.advance_preparations()
        original = self.model.complete
        count = []
        def edit_during_copy(request):
            result = original(request)
            count.append(True)
            self.w.message_conversation(self.c, "correction", 1, "Use £300 instead.")
            return result
        with patch.object(self.model, "complete", side_effect=edit_during_copy):
            self.w.advance_preparations()
        self.assertEqual(len(count), 1)
        self.assertEqual(self.finish()["status"], "stale")
        self.assertIsNone(self.w.conversation(self.c)["campaigns"][0]["case_id"])
        self.assertEqual(len(self.model.copy.requests), 1)
        self.assert_no_release()

    def test_copy_timeout_and_interrupted_copy_reservation_remain_uncertain(self):
        for failure in (ModelError("provider_request_failed"), KeyboardInterrupt()):
            with self.subTest(failure=type(failure).__name__), tempfile.TemporaryDirectory() as root:
                w = Workspace(root, real_clock=lambda: self.now)
                c = w.create_conversation("new", "Copy failure")["id"]
                w.message_conversation(c, "m", 0, "Prepare £600 for contractors with model copy.")
                w.start_preparation(c, "prep", 1, False, True)
                w.advance_preparations()
                w.advance_preparations()
                with patch.object(self.model, "complete", side_effect=failure):
                    if isinstance(failure, KeyboardInterrupt):
                        with self.assertRaises(KeyboardInterrupt):
                            w.advance_preparations()
                    else:
                        w.advance_preparations()
                reopened = Workspace(root, real_clock=lambda: self.now)
                reopened.preparations.recover("local-conversations")
                row = reopened.conversation(c)["preparations"][0]
                self.assertEqual(row["status"], "uncertain")
                self.assertTrue(row["generation"]["outcome_uncertain"])
                with patch.object(self.model, "complete", side_effect=AssertionError("Forbidden automatic repeat")):
                    reopened.advance_preparations()
                self.assertIsNone(reopened.conversation(c)["campaigns"][0]["case_id"])

    def test_changed_request_fields_and_invalid_consent_are_rejected_before_inference(self):
        self.admit(fixture=True)
        for fixture, consent, revision in ((True, True, 1), (True, 0, 1), (True, False, True), (False, False, 1)):
            with self.subTest(fixture=fixture, consent=consent, revision=revision):
                with self.assertRaises((Conflict, ValueError)):
                    self.w.start_preparation(self.c, "prepare", revision, fixture, consent)
        self.assertEqual(self.model.copy.requests, [])
        self.assertEqual(self.model.planner.requests, [])

    def test_configuration_failure_blocks_without_claiming_the_saved_plan(self):
        row = self.admit()
        original = self.w._conversation_app
        def unavailable(with_model=False):
            if with_model:
                raise ValueError("A server credential is unavailable")
            return original()
        with patch.object(self.w, "_conversation_app", side_effect=unavailable):
            self.w.advance_preparations()
        row = self.w.preparations.store.get("local-conversations", row["id"])
        self.assertEqual(row["status"], "blocked")
        state = self.w._conversation_app().tasks.inspect("local-conversations", row["run_id"])
        self.assertEqual(state["run"]["status"], "queued")
        self.assertEqual(state["tasks"][0]["attempts"], 0)
        self.assertEqual(self.model.planner.requests, [])

    def test_stale_briefs_keep_uncertain_planner_and_copy_journals_after_restart(self):
        for phase in ("planning", "copy"):
            for interrupted in (False, True):
                with self.subTest(phase=phase, interrupted=interrupted), tempfile.TemporaryDirectory() as root:
                    w = Workspace(root, real_clock=lambda: self.now)
                    c = w.create_conversation("new", "Changed brief")["id"]
                    w.message_conversation(c, "m", 0, "Prepare a £600 contractor campaign with model copy.")
                    w.start_preparation(c, "prep", 1, False, True)
                    if phase == "copy":
                        w.advance_preparations()
                        w.advance_preparations()
                    def change_then_fail(request):
                        w.message_conversation(c, "edit", 1, "Use £300 instead.")
                        raise KeyboardInterrupt() if interrupted else ModelError("provider_request_failed")
                    with patch.object(self.model, "complete", side_effect=change_then_fail) as dispatch:
                        if interrupted:
                            with self.assertRaises(KeyboardInterrupt):
                                w.advance_preparations()
                        else:
                            w.advance_preparations()
                        self.assertEqual(dispatch.call_count, 1)
                    reopened = Workspace(root, real_clock=lambda: self.now)
                    reopened.preparations.recover("local-conversations")
                    row = reopened.conversation(c)["preparations"][0]
                    self.assertEqual(row["status"], "uncertain")
                    self.assertFalse(row["current"])
                    self.assertIn("brief changed", row["detail"])
                    self.assertIn("charged", row["detail"])
                    self.assertTrue(row["generation"]["outcome_uncertain"])
                    self.assertTrue(row["generation"]["unresolved_calls"])
                    self.assertEqual(row["generation"]["provider_error"], None if interrupted else "provider_request_failed")
                    if phase == "planning":
                        self.assertEqual(row["run_id"], row["generation"]["run_id"])
                    with patch.object(self.model, "complete", side_effect=AssertionError("Uncertain work must not repeat")):
                        reopened.advance_preparations()
                    self.assert_no_release(reopened)
                    # Older terminal status records must still expose their original journal.
                    saved = reopened.preparations.store.get("local-conversations", row["id"])
                    reopened.preparations.store.update("local-conversations", saved, "stale", "The brief changed.")
                    historical = reopened.conversation(c)["preparations"][0]
                    self.assertTrue(historical["generation"]["outcome_uncertain"])
                    self.assertEqual(historical["generation"]["unresolved_calls"], row["generation"]["unresolved_calls"])

    def test_coordinator_is_discoverable_before_and_after_plan_admission_without_a_browser(self):
        for point in ("before-plan", "after-plan-record", "after-plan"):
            with self.subTest(point=point), tempfile.TemporaryDirectory() as root:
                w = Workspace(root, real_clock=lambda: self.now)
                c = w.create_conversation("new", "Interrupted admission")["id"]
                w.message_conversation(c, "message", 0, FIXTURE_MESSAGE)
                if point == "before-plan":
                    fault = patch.object(w, "admit_preparation_plan", side_effect=KeyboardInterrupt())
                elif point == "after-plan-record":
                    fault = patch("acquisition.adapters.sqlite.tasks.SqliteTasks.create", side_effect=KeyboardInterrupt())
                else:
                    original = w.preparations.store.update
                    def lose_run_identity(organization, prior, status, detail, **kwargs):
                        if status == "planning":
                            raise KeyboardInterrupt()
                        return original(organization, prior, status, detail, **kwargs)
                    fault = patch.object(w.preparations.store, "update", side_effect=lose_run_identity)
                with fault, self.assertRaises(KeyboardInterrupt):
                    w.start_preparation(c, "prepare", 1, True, False)
                row = w.preparations.store.listing("local-conversations")[0]
                self.assertEqual(row["status"], "admitting")
                self.assertIsNone(row["run_id"])
                self.assertFalse(row["inputs"]["allow_model_copy"])
                original_context = row["planning_context"]
                admitted = w._conversation_app().conversations.view("local-conversations", c)["current_plan"]
                self.assertEqual(admitted is None, point == "before-plan")
                if admitted:
                    original_run = admitted["run_id"]
                    self.assertEqual((w.preparation_generation("local-conversations", row) or {}).get("run_id"), original_run)
                code = '''
import sys
from unittest.mock import patch
from acquisition.workspace import Workspace
w = Workspace(sys.argv[1])
w.preparations.recover('local-conversations')
with patch('acquisition.conversations.application.ConversationService._knowledge', side_effect=AssertionError('Do not rebuild frozen guidance')):
    [w.advance_preparations() for _ in range(8)]
'''
                result = subprocess.run([sys.executable, "-c", code, root],
                    env=dict(os.environ, PYTHONPATH=str(Path("src").resolve())), capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                reopened = Workspace(root, real_clock=lambda: self.now)
                view = reopened.conversation(c)
                self.assertEqual(view["preparations"][0]["status"], "review_ready")
                self.assertEqual(view["current_plan"]["guidance"]["content"], original_context["knowledge"])
                self.assertEqual(len(view["plans"]), 1)
                self.assertEqual(len(view["campaigns"]), 1)
                if admitted and original_run:
                    self.assertEqual(view["current_plan"]["run_id"], original_run)
                self.assert_no_release(reopened)

    def test_model_consent_and_original_context_survive_an_admission_interruption(self):
        with patch.object(self.w, "admit_preparation_plan", side_effect=KeyboardInterrupt()), self.assertRaises(KeyboardInterrupt):
            self.admit()
        row = self.w.preparations.store.listing("local-conversations")[0]
        self.assertTrue(row["inputs"]["allow_model_copy"])
        self.assertEqual(row["planning_context"]["model_config"]["max_calls"], 2)
        self.assertEqual(self.model.planner.requests, [])
        reopened = self.open()
        with patch("acquisition.conversations.application.ConversationService._knowledge", side_effect=AssertionError("Frozen inputs must be reused")):
            self.assertEqual(self.finish(reopened)["status"], "review_ready")
        self.assertEqual(len(self.model.planner.requests), 1)
        self.assertEqual(len(self.model.copy.requests), 3)
        self.assert_no_release(reopened)
