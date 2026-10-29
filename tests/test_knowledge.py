"""Planning knowledge provenance and workspace source boundaries."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from acquisition.bootstrap import build
from acquisition.contracts import NotFound, digest
from acquisition.reasoning import ModelConfig
from acquisition.workspace import Workspace
from test_conversations import PlannerModel


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.clock = lambda: 1792972800.0
        self.model = PlannerModel()
        self.config = ModelConfig("test/model", max_calls=2, force_tool_choice=True)
        self.app = build(self.root / "knowledge.sqlite", self.clock, self.model, self.config)

    def test_frozen_playbooks_survive_changed_source_and_process_restart(self):
        service = self.app.conversations
        identity = service.create("org-one", "create", "Knowledge")['id']
        service.message("org-one", identity, "message", 0, "Plan a £600 contractor experiment.")
        original = {"version": "test/v1", "purpose": "Original purpose", "experiment": "Original experiment", "playbooks": [{"id": "original", "segment": "contractors", "title": "First", "guidance": "Original guidance"}]}
        with patch.object(service, "guidance", return_value=original):
            run = service.plan("org-one", identity, "plan", 1)
        self.app.worker.drain("org-one", run_id=run)
        old = service.view("org-one", identity)['current_plan']
        self.assertEqual(old['guidance']['id'], "knowledge_" + digest(old['guidance']['content']))
        self.assertEqual(old['guidance']['content']['playbooks'], original)
        with self.assertRaises(NotFound):
            service.view("org-two", identity)
        restarted = build(self.root / "knowledge.sqlite", self.clock, self.model, self.config)
        with patch.object(restarted.conversations, "guidance", side_effect=OSError("source unavailable")):
            self.assertEqual(restarted.conversations.plan("org-one", identity, "plan", 1), run)
        self.assertEqual(restarted.conversations.view("org-one", identity)['current_plan']['guidance'], old['guidance'])
        restarted.conversations.message("org-one", identity, "message2", 1, "Use £300 instead.")
        with patch.object(restarted.conversations, "guidance", return_value=original | {"purpose": "Changed purpose"}):
            second = restarted.conversations.plan("org-one", identity, "plan2", 2)
        self.assertNotEqual(restarted.tasks.inspect("org-one", second)['tasks'][0]['inputs']['knowledge_id'], old['guidance']['id'])
        history = restarted.conversations.view("org-one", identity)['plans']
        self.assertFalse(history[0]['current'])
        self.assertEqual(history[0]['guidance']['content']['playbooks'], original)
        self.assertEqual(history[1]['guidance']['content']['playbooks']['purpose'], 'Changed purpose')

    def test_frozen_snapshot_tampering_is_not_presented_as_valid(self):
        service = self.app.conversations
        identity = service.create("org-one", "create", "Knowledge")['id']
        service.message("org-one", identity, "message", 0, "Plan a £600 contractor experiment.")
        service.plan("org-one", identity, "plan", 1)
        with service.store.database.transaction() as db:
            db.execute("UPDATE conversation_plans SET payload=replace(payload, 'campaign-playbooks/v1', 'campaign-playbooks/v2') WHERE organization=? AND conversation_id=?", ("org-one", identity))
        from acquisition.contracts import Conflict
        with self.assertRaises(Conflict):
            service.view("org-one", identity)

    def test_library_exposes_sources_without_claiming_authority(self):
        data = Workspace(self.root / "workspace", real_clock=self.clock).knowledge()
        self.assertEqual(data['playbooks']['status'], 'advisory_synthetic_only')
        self.assertTrue(data['product_facts']['sources'])
        self.assertTrue(data['editorial']['rules'])
        self.assertIn("scoped", data['learning'])
