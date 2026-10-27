"""Conversation-to-campaign scope, identity and review authority."""

import csv
import io
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from unittest.mock import patch

from acquisition.contracts import Conflict
from acquisition.conversations import FIXTURE_MESSAGE
from acquisition.workspace import Workspace
from test_conversations import PlannerModel, proposal


class ConversationCampaignTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = Workspace(self.root, real_clock=lambda: 1792972800.0)
        self.model = PlannerModel()
        self.key = patch("acquisition.workspace.openrouter_key", return_value="fixture")
        self.gateway = patch("acquisition.workspace.OpenRouter", return_value=self.model)
        self.key.start()
        self.gateway.start()
        self.addCleanup(self.key.stop)
        self.addCleanup(self.gateway.stop)
        self.conversation = self.workspace.create_conversation("new", "Contractors")["id"]
        self.workspace.message_conversation(self.conversation, "m1", 0, "Plan a £600 contractor experiment.")
        self.plan = self.workspace.plan_conversation(self.conversation, "p1", 1)["current_plan"]["result"]

    def draft(self, request="draft", revision=1, plan_id=None):
        return self.workspace.draft_conversation(self.conversation, request, revision, plan_id or self.plan["id"])

    def test_brief_creates_exact_segment_budget_and_reviewable_fixture_draft(self):
        state = self.draft()
        review, manifest = state["review"], state["review"]["manifest"]
        self.assertTrue(review["candidate_valid"], review["blocked_reasons"])
        self.assertFalse(review["approval_valid"])
        self.assertEqual(manifest["brief"]["budget_pence"], 60000)
        self.assertEqual(manifest["brief"]["segments"], ["contractors"])
        self.assertEqual(manifest["brief"]["plan_id"], self.plan["id"])
        self.assertLessEqual(manifest["variable_cost_pence"], 60000)
        self.assertEqual({c["segment"] for c in manifest["creatives"]}, {"contractors"})
        mailed = [row for row in state["audience"] if row["arm"] in {"A", "B", "no_mail"}]
        self.assertTrue(mailed)
        self.assertEqual({row["segment"] for row in mailed}, {"contractors"})
        counts = manifest["counts"]
        self.assertEqual(counts["input"], sum(v for k, v in counts.items() if k != "input"))
        self.assertGreater(manifest["exclusion_reasons"]["outside_selected_segment"], 0)
        self.assertEqual(len(self.model.requests), 1)
        again = self.draft()
        self.assertEqual(again["review"]["subject"]["id"], review["subject"]["id"])
        self.assertEqual(len(self.workspace.listing()["sessions"]), 1)
        reopened = Workspace(self.root, real_clock=lambda: 1792972800.0)
        self.assertEqual(reopened.view(state["session"]["id"])["review"]["subject"], review["subject"])

    def test_conversation_change_invalidates_approval_at_commit_and_requires_new_plan(self):
        state = self.draft()
        session = state["session"]["id"]
        subject = state["review"]["subject"]["id"]
        approved = self.workspace.action(session, "approve", {"request_id": "approve", "subject_id": subject,
                                                                  "reason": "Reviewed the synthetic campaign."})
        approval = approved["review"]["approval"]["id"]
        self.workspace.message_conversation(self.conversation, "m2", 1, "Use £300 instead.")
        stale = self.workspace.view(session)
        self.assertFalse(stale["review"]["candidate_valid"])
        self.assertFalse(stale["review"]["approval_valid"])
        with self.assertRaises(Conflict):
            self.workspace.action(session, "handoff", {"request_id": "handoff", "approval_id": approval})
        with self.assertRaises(Conflict):
            self.draft("new-request")
        self.model.results = [proposal(budget_pence=30000)]
        second_plan = self.workspace.plan_conversation(self.conversation, "p2", 2)["current_plan"]["result"]
        new = self.workspace.draft_conversation(self.conversation, "draft2", 2, second_plan["id"])
        self.assertNotEqual(new["session"]["id"], session)
        self.assertNotEqual(new["review"]["subject"]["id"], subject)
        self.assertFalse(new["review"]["approval_valid"])
        self.assertEqual(new["review"]["manifest"]["brief"]["budget_pence"], 30000)

    def test_review_and_conversation_edits_serialize_at_the_authority_boundary(self):
        state = self.draft()
        session = state["session"]["id"]
        app = self.workspace._app(self.workspace._session(session))
        scope = self.workspace._session(session)["organization"]
        store = app.reviews.store
        entered, release, editing = Event(), Event(), Event()
        original = store._conversation_source
        def gated(*args):
            entered.set()
            self.assertTrue(release.wait(5))
            return original(*args)
        def approve():
            with patch.object(store, "_conversation_source", side_effect=gated):
                return store.decide(scope, state["review"]["case_id"], state["review"]["subject"]["id"],
                                    "local-reviewer", "approve", "concurrent-approve", "Reviewed exact draft.", 86400)
        def edit():
            editing.set()
            return app.conversations.message("local-conversations", self.conversation, "concurrent-edit", 1, "Use £300 instead.")
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(approve)
            self.assertTrue(entered.wait(5))
            second = pool.submit(edit)
            self.assertTrue(editing.wait(5))
            release.set()
            receipt = first.result(timeout=10)
            second.result(timeout=10)
        self.assertFalse(self.workspace.view(session)["review"]["approval_valid"])
        with self.assertRaises(Conflict):
            store.handoff(scope, state["review"]["case_id"], receipt["id"], "local-operator", "late-handoff")

    def test_offline_mode_and_original_provenance_cannot_be_substituted(self):
        state = self.draft()
        app = self.workspace._app(self.workspace._session(state["session"]["id"]))
        scope = self.workspace._session(state["session"]["id"])["organization"]
        case = state["review"]["case_id"]
        old = state["review"]["subject"]["id"]
        original = app.drafts.get(scope, state["review"]["subject"]["draft_id"])
        from acquisition.campaigns import Brief, build_draft
        from acquisition.creative import fixture_catalog
        snapshot = app.audiences.get(scope, original.manifest["snapshot_id"])
        unbound = build_draft(snapshot, Brief("substitute"), fixture_catalog())
        unbound_id = app.drafts.put(scope, "substitute", unbound)
        with self.assertRaises(Conflict):
            app.reviews.replace(scope, case, old, unbound_id, "local-operator", "replace")

    def test_changed_plan_request_is_rejected(self):
        state = self.draft()
        with self.assertRaises(Conflict):
            self.workspace.draft_conversation(self.conversation, "draft", 1, "brief_other")
        with self.assertRaises(Conflict):
            self.workspace.draft_conversation(self.conversation, "other", 1, "brief_other")
        self.assertEqual(len(self.workspace.listing()["sessions"]), 1)
        self.assertEqual(state["session"]["mode"], "fixture")

    def test_model_copy_proposal_is_not_silently_downgraded(self):
        self.workspace.message_conversation(self.conversation, "m2", 1, "Use £300 and model copy.")
        self.model.results = [proposal(budget_pence=30000, copy_mode="model")]
        plan = self.workspace.plan_conversation(self.conversation, "p2", 2)["current_plan"]["result"]
        with self.assertRaises(ValueError):
            self.workspace.draft_conversation(self.conversation, "model-draft", 2, plan["id"])
        self.assertEqual(self.workspace.listing()["sessions"], [])

    def test_lost_metadata_reuses_the_original_run_and_draft(self):
        original = self.workspace._save
        failed = []
        def fail_case(session):
            if session["case_id"] and not failed:
                failed.append(True)
                raise OSError("injected metadata failure")
            original(session)
        with patch.object(self.workspace, "_save", side_effect=fail_case), self.assertRaises(OSError):
            self.draft()
        recovered = self.draft()
        self.assertTrue(recovered["review"]["candidate_valid"])
        self.assertEqual(len(self.workspace.listing()["sessions"]), 1)
        self.assertEqual(len(self.model.requests), 1)

    def test_offline_example_prepares_a_draft_without_model_calls(self):
        conversation = self.workspace.create_conversation("offline", "Offline example")["id"]
        self.workspace.message_conversation(conversation, "message", 0, FIXTURE_MESSAGE)
        plan = self.workspace.plan_conversation_fixture(conversation, "plan", 1)["current_plan"]["result"]
        before = len(self.model.requests)
        state = self.workspace.draft_conversation(conversation, "draft", 1, plan["id"])
        self.assertTrue(state["review"]["candidate_valid"], state["review"]["blocked_reasons"])
        self.assertEqual(len(self.model.requests), before)

    def test_offline_example_cannot_interpret_an_arbitrary_message(self):
        conversation = self.workspace.create_conversation("invalid-offline", "Offline example")["id"]
        self.workspace.message_conversation(conversation, "message", 0, "Prepare a £600 inventory campaign.")
        with self.assertRaises(ValueError):
            self.workspace.plan_conversation_fixture(conversation, "plan", 1)
        self.assertEqual(self.workspace.conversation(conversation)["plans"], [])

    def accept_and_open(self, state, prefix):
        session = state["session"]["id"]
        approved = self.workspace.action(session, "approve", {"request_id": prefix + "-approve", "subject_id": state["review"]["subject"]["id"], "reason": "Reviewed the synthetic draft."})
        self.workspace.action(session, "handoff", {"request_id": prefix + "-handoff", "approval_id": approved["review"]["approval"]["id"]})
        return self.workspace.action(session, "open-learning", {"request_id": prefix + "-learning"})

    def test_independent_conversations_can_open_separate_cohorts(self):
        first = self.draft()
        second_id = self.workspace.create_conversation("other-conversation", "Offline example")["id"]
        self.workspace.message_conversation(second_id, "message", 0, FIXTURE_MESSAGE)
        plan = self.workspace.plan_conversation_fixture(second_id, "plan", 1)["current_plan"]["result"]
        second = self.workspace.draft_conversation(second_id, "draft", 1, plan["id"])
        self.assertNotEqual(self.workspace._session(first["session"]["id"])["organization"], self.workspace._session(second["session"]["id"])["organization"])
        self.assertIsNotNone(self.accept_and_open(first, "first")["learning"])
        self.assertIsNotNone(self.accept_and_open(second, "second")["learning"])

    def test_followup_inherits_database_learning_and_disabled_reviewer(self):
        first = self.draft()
        session_id = first["session"]["id"]
        opened = self.accept_and_open(first, "first")
        member = next(row for row in opened["audience"] if row["arm"] in {"A", "B"})
        self.workspace.action(session_id, "suppress", {"request_id": "suppress", "business_id": member["id"], "reason": "Exclude this business."})
        self.workspace.action(session_id, "finalize", {"request_id": "finalize"})
        session = self.workspace._session(session_id)
        app = self.workspace._app(session)
        scope = session["organization"]
        before = app.learning.store.memory(scope, "contractors")
        self.assertTrue(before)
        app.reviews.store.register_actor(scope, "local-reviewer", ("reviewer",), enabled=False)
        child = self.workspace.create("next", "fixture", session_id)
        child_session = self.workspace._session(child["session"]["id"])
        self.assertEqual(child_session["organization"], scope)
        self.assertEqual(child_session["database_scope"], "conversations")
        self.assertEqual(self.workspace._app(child_session).learning.store.memory(scope, "contractors"), before)
        self.assertIn(member["id"], child["review"]["suppressions"])
        with self.assertRaisesRegex(ValueError, "Active local reviewer"):
            self.workspace.action(child_session["id"], "approve", {"request_id": "denied", "subject_id": child["review"]["subject"]["id"], "reason": "Attempt while disabled."})
