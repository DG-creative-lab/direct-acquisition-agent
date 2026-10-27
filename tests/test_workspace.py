"""Reachable UI authority, recovery and same-origin transport boundaries."""
import io
import json
import http.client
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from acquisition.workspace import Workspace
from acquisition.workspace_server import WorkspaceServer, main
from acquisition.contracts import Conflict, NotFound
from acquisition.reasoning import ModelConfig
from acquisition.bootstrap import build
from test_model_copy import FakeModel


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = Workspace(self.root, real_clock=lambda: 1792972800.0)
        self.view = self.workspace.create("campaign", "fixture")
        self.id = self.view["session"]["id"]
        self.subject = self.view["review"]["subject"]["id"]

    def act(self, action, request_id=None, **kwargs):
        return self.workspace.action(self.id, action, {"request_id": request_id or action, **kwargs})

    def approve(self, key="approve", subject=None):
        return self.act("approve", key, subject_id=subject or self.subject, reason="Reviewed the synthetic audience, exact copy and evidence.")

    def accepted(self):
        approved = self.approve()
        return self.act("handoff", approval_id=approved["review"]["approval"]["id"])

    def learned(self):
        self.accepted()
        self.act("open-learning")
        return self.act("finalize")

    def test_browser_journey_suppression_invalidates_approval_then_fresh_review(self):
        approved = self.approve()
        old_approval = approved["review"]["approval"]["id"]
        row = next(r for r in approved["audience"] if r["arm"] in {"A", "B"})
        blocked = self.act("suppress", business_id=row["id"], reason="Synthetic late suppression.")
        self.assertFalse(blocked["review"]["approval_valid"])
        with self.assertRaises(Conflict):
            self.act("handoff", approval_id=old_approval)
        fresh = self.act("refresh", subject_id=self.subject)
        with self.assertRaises(Conflict):
            self.approve("stale-browser")
        fresh = self.approve("fresh", fresh["review"]["subject"]["id"])
        accepted = self.act("handoff", "fresh-handoff", approval_id=fresh["review"]["approval"]["id"])
        self.assertEqual(accepted["review"]["handoff"]["recipients"], fresh["review"]["manifest"]["counts"]["mailed"])
        self.assertNotIn(row["id"], self.workspace.artifact(self.id, "mailing", fresh["review"]["subject"]["id"])[0].decode())

    def test_learning_pending_finalizes_once_and_survives_restart(self):
        self.accepted()
        self.act("open-learning")
        early = self.act("observe")
        self.assertEqual(early["learning"]["status"], "observing")
        self.assertGreater(early["learning"]["received"], 0)
        self.assertEqual(early["learning"]["beliefs"], [])
        final = self.act("finalize")
        self.assertEqual(len(final["learning"]["beliefs"]), 6)
        self.assertEqual(final["learning"]["missing"], 0)
        events = final["learning"]["events"]
        replay = self.act("finalize")
        self.assertTrue(replay["command_replayed"])
        self.assertEqual(replay["learning"]["events"], events)
        reopened = Workspace(self.root).view(self.id)
        self.assertEqual(reopened["learning"]["finalization"], final["learning"]["finalization"])
        self.assertEqual(reopened["review"]["subject"], final["review"]["subject"])

    def test_artifact_download_cannot_substitute_a_newer_subject(self):
        with self.assertRaises(Conflict):
            self.workspace.artifact(self.id, "manifest", "stale-subject")
        body, _, _ = self.workspace.artifact(self.id, "manifest", self.subject)
        self.assertEqual(json.loads(body)["snapshot_id"], self.view["review"]["subject"]["snapshot_id"])

    def test_request_reuse_cannot_advance_clock_or_change_action(self):
        self.accepted()
        self.act("open-learning")
        early = self.act("observe", "same-key")
        with self.assertRaises(Conflict):
            self.act("finalize", "same-key")
        self.assertEqual(self.workspace.view(self.id)["session"]["clock"], early["session"]["clock"])
        self.assertEqual(self.workspace.view(self.id)["learning"]["beliefs"], [])

    def test_explicit_rejection_revocation_and_no_inherited_approval(self):
        rejected = self.act("reject", subject_id=self.subject, reason="Synthetic copy needs review.")
        self.assertFalse(rejected["review"]["approval_valid"])
        approved = self.approve()
        revoked = self.act("revoke", approval_id=approved["review"]["approval"]["id"], reason="Review withdrawn.")
        self.assertFalse(revoked["review"]["approval_valid"])
        with self.assertRaises(Conflict):
            self.act("handoff", approval_id=approved["review"]["approval"]["id"])

    def test_creation_replay_exact_scope_and_payload_controls(self):
        same = self.workspace.create("campaign", "fixture")
        self.assertEqual(same["session"]["case_id"], self.view["session"]["case_id"])
        with self.assertRaises(Conflict):
            self.workspace.create("campaign", "model")
        with self.assertRaises(ValueError):
            self.act("approve", subject_id=self.subject, reason="Reason.", organization="other")
        with self.assertRaises(NotFound):
            self.workspace.view("unknown")
        with self.assertRaises(Conflict):
            self.workspace.create("not-yet-learned", "fixture", self.id)
        self.assertEqual(len(self.workspace.listing()["sessions"]), 1)

    def test_unknown_ack_after_domain_commit_recovers_with_same_request(self):
        original_save = self.workspace._save
        failed = []
        def fail_once(session):
            if session["cohort_id"] and not failed:
                failed.append(True)
                raise OSError("Injected metadata receipt loss")
            original_save(session)
        self.accepted()
        with patch.object(self.workspace, "_save", side_effect=fail_once):
            with self.assertRaises(OSError):
                self.act("open-learning", "lost-receipt")
        recovered = self.act("open-learning", "lost-receipt")
        self.assertIsNotNone(recovered["learning"])
        self.assertEqual(len([e for e in recovered["learning"]["events"] if e["kind"] == "cohort_opened"]), 1)

    def test_model_preparation_uses_existing_agent_and_checks_without_paid_calls(self):
        model = FakeModel()
        real_build = build
        def model_build(path, clock, gateway, model_config):
            return real_build(path, clock, model if gateway else None, model_config)
        with patch("acquisition.workspace.openrouter_key", return_value="fixture"), patch("acquisition.workspace.OpenRouter", return_value=model), patch("acquisition.workspace.build", side_effect=model_build):
            live = self.workspace.create("model", "model")
        self.assertEqual(len(model.requests), 6)
        self.assertTrue(all(c["status"] == "generated_unreviewed" for c in live["review"]["manifest"]["creatives"]))
        self.assertFalse(live["review"]["approval_valid"])

    def test_lost_run_metadata_resumes_original_model_context_after_memory_changes(self):
        model = FakeModel()
        original_save = self.workspace._save
        def fail_before_run_receipt(session):
            if session["run_id"] and not session["case_id"]:
                raise OSError("Injected lost run metadata")
            original_save(session)
        with patch("acquisition.workspace.openrouter_key", return_value="fixture"), patch("acquisition.workspace.OpenRouter", return_value=model):
            with patch.object(self.workspace, "_save", side_effect=fail_before_run_receipt), self.assertRaises(OSError):
                self.workspace.create("lost-run", "model")
            saved = next(s for s in self.workspace.listing()["sessions"] if s["mode"] == "model")
            session = self.workspace._session(saved["id"])
            app = self.workspace._app(session)
            run_id = app.tasks.find_run(session["organization"], saved["id"])
            self.assertIsNotNone(run_id)
            inputs = app.tasks.inspect(session["organization"], run_id)["tasks"][0]["inputs"]
            app.memory.remember(session["organization"], "inventory", "New editorial preference.", "Do not reuse a stale plan.", "Changed after admission.")
            recovered = self.workspace.prepare(saved["id"])
        self.assertEqual(recovered["session"]["run_id"], run_id)
        self.assertEqual(recovered["tasks"]["tasks"][0]["inputs"], inputs)
        self.assertEqual(len(model.requests), 6)

    def test_next_experiment_uses_mature_memory_without_inheriting_approval(self):
        self.learned()
        model = FakeModel()
        with patch("acquisition.workspace.openrouter_key", return_value="fixture"), patch("acquisition.workspace.OpenRouter", return_value=model):
            following = self.workspace.create("next-model", "model", self.id)
        self.assertFalse(following["review"]["approval_valid"])
        self.assertIsNone(following["review"]["handoff"])
        session = self.workspace._session(following["session"]["id"])
        app = self.workspace._app(session)
        for c in following["review"]["manifest"]["creatives"]:
            context = app.memory.get_context(session["organization"], c["context_id"])
            self.assertEqual(len(context["audience_summary"]["outcome_evidence"]["groups"]), 3)
        self.assertEqual(len(model.requests), 6)


class WorkspaceStartupTests(unittest.TestCase):
    def test_missing_assets_report_the_reproducible_pnpm_build_commands(self):
        error = io.StringIO()
        with (
            patch("acquisition.workspace_server.Path.exists", return_value=False),
            patch("sys.argv", ["workspace-server"]),
            redirect_stderr(error),
            self.assertRaises(SystemExit) as stopped,
        ):
            main()

        message = error.getvalue()
        self.assertEqual(stopped.exception.code, 2)
        self.assertIn(
            "pnpm --dir frontend install --frozen-lockfile "
            "&& pnpm --dir frontend run build",
            message,
        )
        self.assertNotIn("npm", message.split())


class WorkspaceHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        assets = self.root / "assets"
        assets.mkdir()
        (assets / "index.html").write_text('<meta name="workspace-token" content="__WORKSPACE_TOKEN__">')
        self.server = WorkspaceServer(0, Workspace(self.root / "data"), assets)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)

    def request(self, path, payload=None, headers=None):
        defaults = {"X-Workspace-Token": self.server.token}
        if payload is not None:
            defaults |= {"Content-Type": "application/json", "Origin": self.base}
        defaults.update(headers or {})
        req = urllib.request.Request(self.base + path, data=json.dumps(payload).encode() if payload is not None else None, headers=defaults)
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                return response.status, response.read(), response.headers
        except urllib.error.HTTPError as error:
            with error:
                return error.code, error.read(), error.headers

    def test_host_token_and_origin_guard_every_mutation(self):
        for bad in ({"Host": "attacker.invalid"}, {"X-Workspace-Token": "wrong"}, {"Origin": "https://attacker.invalid"}, {"Origin": "null"}):
            with self.subTest(headers=bad):
                status, _, _ = self.request('/api/sessions', {"request_id": "forged", "mode": "fixture"}, bad)
                self.assertEqual(status, 403)
        self.assertEqual(self.server.workspace.listing()["sessions"], [])
        self.assertEqual(self.request('/api/sessions', headers={"X-Workspace-Token": ""})[0], 403)

    def absolute_request(self, method, headers):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
        try:
            body = json.dumps({"request_id": "absolute-target", "mode": "fixture"}) if method == "POST" else None
            connection.request(method, self.base + "/api/sessions", body=body, headers={"Content-Type": "application/json", **headers})
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def test_absolute_form_get_is_rejected_before_api_routing(self):
        for headers in ({}, {"X-Workspace-Token": self.server.token}):
            with self.subTest(headers=headers):
                self.assertEqual(self.absolute_request("GET", headers)[0], 400)
        self.assertEqual(self.server.workspace.listing()["sessions"], [])

    def test_absolute_form_post_cannot_create_a_campaign_without_guards(self):
        for headers in ({}, {"X-Workspace-Token": self.server.token},
                        {"X-Workspace-Token": self.server.token, "Origin": self.base}):
            with self.subTest(headers=headers):
                self.assertEqual(self.absolute_request("POST", headers)[0], 400)
        self.assertEqual(self.server.workspace.listing()["sessions"], [])

    def test_second_server_cannot_mutate_the_same_workspace(self):
        with self.assertRaises(BlockingIOError):
            WorkspaceServer(0, self.server.workspace, self.server.assets)

    def test_static_assets_cannot_serve_private_files(self):
        (self.root / ".env.local").write_text("do-not-serve")
        status, body, headers = self.request('/')
        self.assertEqual(status, 200)
        self.assertIn(self.server.token.encode(), body)
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        for path in ('/../.env.local', '/%2e%2e/.env.local', '/api/unknown'):
            status, body, _ = self.request(path)
            self.assertEqual(status, 404)
            self.assertNotIn(b"do-not-serve", body)

    def test_conversations_keep_http_guards_and_fixed_server_scope(self):
        path = "/api/conversations"
        for headers in ({"X-Workspace-Token": "wrong"}, {"Origin": "https://attacker.invalid"}):
            self.assertEqual(self.request(path, {"request_id": "new", "title": "Contractors"}, headers)[0], 403)
        self.assertEqual(json.loads(self.request(path)[1])["conversations"], [])
        self.assertEqual(self.request(path, {"request_id": "new", "title": "Contractors", "organization": "other"})[0], 400)
        self.assertEqual(self.request(path, headers={"X-Workspace-Token": ""})[0], 403)

    def test_conversation_http_planning_is_explicit_and_creates_no_campaign(self):
        from test_conversations import PlannerModel
        model = PlannerModel()
        with patch("acquisition.workspace.openrouter_key", return_value="fixture"), patch("acquisition.workspace.OpenRouter", return_value=model):
            status, body, _ = self.request("/api/conversations", {"request_id": "new", "title": "Contractors"})
            self.assertEqual(status, 200)
            identity = json.loads(body)["id"]
            path = "/api/conversations/" + identity
            payload = {"request_id": "message", "expected_revision": 0, "content": "Prepare a £600 UK contractor experiment."}
            self.assertEqual(self.request(path + "/messages", payload)[0], 200)
            self.assertEqual(self.request(path)[0], 200)
            self.assertEqual(model.requests, [])
            self.assertEqual(self.request(path + "/plan", {"request_id": "plan", "expected_revision": 1, "approve": True})[0], 400)
            status, body, _ = self.request(path + "/plan", {"request_id": "plan", "expected_revision": 1})
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["current_plan"]["result"]["budget_pence"], 60000)
            self.assertEqual(len(model.requests), 1)
            self.assertEqual(self.request(path + "/plan", {"request_id": "plan", "expected_revision": 1})[0], 200)
            self.assertEqual(len(model.requests), 1)
            self.assertEqual(self.request(path + "/approve", {"request_id": "approval", "expected_revision": 1})[0], 400)
            self.assertEqual(self.request(path + "/messages", payload | {"request_id": "stale"})[0], 409)
        self.assertEqual(self.server.workspace.listing()["sessions"], [])

    def test_real_http_json_actions_artifacts_and_input_boundaries(self):
        status, body, _ = self.request('/api/sessions', {"request_id": "http", "mode": "fixture"})
        self.assertEqual(status, 200)
        state = json.loads(body)
        identity = state["session"]["id"]
        self.assertEqual(self.request('/api/sessions/'+identity)[0], 200)
        path='/api/sessions/'+identity+'/approve'
        self.assertEqual(self.request(path,{"request_id":"approve","subject_id":"stale","reason":"Review."})[0],409)
        self.assertEqual(self.request(path,{"request_id":"missing-reason"})[0],400)
        self.assertEqual(self.request('/api/sessions',{ "request_id":"too-large","mode":"fixture","padding":"x"*17000})[0],400)
        status, body, headers = self.request('/api/sessions/'+identity+'/artifacts/manifest?subject_id='+state['review']['subject']['id'])
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["counts"]["input"],1000)
        self.assertIn('attachment',headers['Content-Disposition'])
