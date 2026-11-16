"""Composition stays lazy; injected model sessions retain bounded identity."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from uuid import uuid4

from acquisition.bootstrap import build_workspace
from acquisition.adapters.models.workspace_sessions import WorkspaceSessions
from acquisition.application.workspace import ModelSessionExpired
from acquisition.contracts import Conflict
from test_model_copy import FakeModel
from test_preparations import CombinedModel


class WorkspaceCompositionTests(unittest.TestCase):
    def test_injected_gateway_is_lazy_and_fresh_process_replay_adds_no_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model, constructions = FakeModel(), []
            def gateway():
                constructions.append('explicit-generation')
                return model
            workspace = build_workspace(root, real_clock=lambda: 1792972800., gateway_factory=gateway)
            self.assertEqual(workspace.listing()['sessions'], [])
            self.assertEqual(constructions, [])
            self.assertFalse((root / 'conversations.sqlite').exists())
            workspace.create('offline', 'fixture')
            self.assertEqual(constructions, [])
            generated = workspace.create('generated', 'model')
            self.assertEqual(len(model.requests), 6)
            self.assertFalse(generated['review']['approval_valid'])
            self.assertTrue(constructions)
            code = '''import json,sys
from acquisition.bootstrap import build_workspace
def unavailable(): raise AssertionError('Replay constructed a provider')
w=build_workspace(sys.argv[1],real_clock=lambda:1792972800.,gateway_factory=unavailable)
print(json.dumps(w.create('generated','model')['review']['subject']['id']))
'''
            result = subprocess.run([sys.executable, '-c', code, str(root)],
                env=dict(os.environ, PYTHONPATH=str(Path('src').resolve())),
                capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), generated['review']['subject']['id'])
            self.assertEqual(len(model.requests), 6)

    def test_expired_or_foreign_handle_cannot_supply_gateway_and_reconnect_keeps_binding(self):
        now = [0.]
        provider = CombinedModel()
        sessions = WorkspaceSessions(lambda: self.fail('Unexpected legacy gateway'),
            gateway_factory=lambda key: provider, catalogue_source=lambda: [{'id': 'vendor/model', 'tier': 'Lower cost'}],
            clock=lambda: now[0])
        key, tab = 'fixture-key-' + 'x' * 40, str(uuid4())
        original = sessions.connect(key, tab)
        with self.assertRaises(Conflict):
            sessions.connect(key, str(uuid4()), previous=original['handle'])
        with sessions.browser(original['handle'], tab, 'vendor/model', 'Lower cost'):
            frozen = sessions.selected(2)
            self.assertIs(sessions.gateway(frozen), provider)
        now[0] = 300.
        sessions.expire()
        with self.assertRaises(ModelSessionExpired), sessions.browser(original['handle'], tab):
            self.fail('An expired handle remained usable')
        recovered = sessions.connect(key, tab)
        self.assertEqual(recovered['binding'], original['binding'])
        self.assertNotEqual(recovered['handle'], original['handle'])
        with sessions.browser(recovered['handle'], tab, 'vendor/model', 'Lower cost'):
            self.assertIs(sessions.gateway(frozen), provider)
        self.assertEqual(provider.planner.requests, [])
        self.assertEqual(provider.copy.requests, [])

    def test_browser_connection_bound_rejects_overflow_without_revoking_existing_tab(self):
        provider = CombinedModel()
        sessions = WorkspaceSessions(lambda: provider, gateway_factory=lambda key: provider)
        first = None
        for index in range(32):
            tab = str(uuid4())
            connection = sessions.connect('fixture-key-' + str(index) + 'x' * 40, tab)
            if first is None: first = (connection, tab)
        with self.assertRaises(Conflict):
            sessions.connect('fixture-key-overflow-' + 'x' * 40, str(uuid4()))
        connection, tab = first
        with sessions.browser(connection['handle'], tab):
            self.assertEqual(sessions.binding, connection['binding'])
        self.assertEqual(provider.planner.requests, [])
        self.assertEqual(provider.copy.requests, [])
