"""Conversation-origin acceptance, immutable receipt exports and restart recovery."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from acquisition.conversations import FIXTURE_MESSAGE
from acquisition.contracts import Conflict
from acquisition.workspace import Workspace


class ConversationHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.w = Workspace(self.root, real_clock=lambda: 1792972800.0)
        self.c = self.w.create_conversation('chat', 'Handoff')['id']
        self.w.message_conversation(self.c, 'message', 0, FIXTURE_MESSAGE)
        self.w.start_preparation(self.c, 'prepare', 1, True, False)
        for _ in range(5): self.w.advance_preparations()
        self.sid = self.w.conversation(self.c)['campaigns'][0]['session_id']
        self.state = self.w.view(self.sid)
        self.subject = self.state['review']['subject']['id']

    def approve(self):
        return self.w.action(self.sid, 'approve', {'request_id': 'approve', 'subject_id': self.subject, 'reason': 'Reviewed exact campaign.'})['review']['approval']['id']

    def test_receipt_export_requires_exact_accepted_subject_and_preserves_history(self):
        with self.assertRaises(Conflict): self.w.artifact(self.sid, 'handoff', self.subject)
        approval = self.approve()
        state = self.w.action(self.sid, 'handoff', {'request_id': 'handoff', 'approval_id': approval})
        original = {k: self.w.artifact(self.sid, k, self.subject)[0] for k in ('handoff', 'manifest', 'mailing', 'assignments')}
        receipt = json.loads(original['handoff'])
        self.assertEqual(receipt, state['review']['handoff'])
        self.assertEqual(receipt['subject_id'], self.subject)
        self.assertEqual(receipt['approval_id'], approval)
        self.assertEqual(receipt['mode'], 'SYNTHETIC_NO_PRINT_NO_SEND')
        self.w.message_conversation(self.c, 'later-edit', 1, 'Use £300 instead.')
        reopened = Workspace(self.root, real_clock=lambda: 1792972800.0)
        for kind, content in original.items():
            self.assertEqual(reopened.artifact(self.sid, kind, self.subject)[0], content)
            with self.assertRaises(Conflict): reopened.artifact(self.sid, kind, 'another-subject')
        self.assertFalse(reopened.view(self.sid)['review']['candidate_valid'])

    def test_fresh_process_replays_one_acceptance_after_partial_control_acknowledgement(self):
        approval = self.approve()
        payload = {'request_id': 'handoff', 'approval_id': approval}
        accepted = self.w.action(self.sid, 'handoff', payload)['review']['handoff']
        with self.w.control() as db:
            db.execute('UPDATE commands SET done=0 WHERE session_id=? AND request_id=?', (self.sid, 'handoff'))
        self.w.message_conversation(self.c, 'edit', 1, 'Use £300 instead.')
        code = """import sys,json
from acquisition.workspace import Workspace
w=Workspace(sys.argv[1],real_clock=lambda:1792972800.0)
s=w.action(sys.argv[2],'handoff',json.loads(sys.argv[3]))
print(json.dumps(s['review']['handoff']))
"""
        result = subprocess.run([sys.executable, '-c', code, str(self.root), self.sid, json.dumps(payload)], env=dict(os.environ, PYTHONPATH=str(Path('src').resolve())), text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), accepted)
        events = self.w.view(self.sid)['review']['events']
        self.assertEqual(sum(e['kind'] == 'simulated_handoff_accepted' for e in events), 1)

    def test_expired_approval_or_changed_reviewer_cannot_accept(self):
        approval = self.approve()
        session = self.w._session(self.sid)
        session['clock'] += 86400
        self.w._save(session)
        with self.assertRaises(Conflict): self.w.action(self.sid, 'handoff', {'request_id': 'expired', 'approval_id': approval})
        session['clock'] -= 86400
        self.w._save(session)
        app = self.w._app(session)
        app.reviews.store.register_actor(session['organization'], 'local-reviewer', ('reviewer',), enabled=False)
        with self.assertRaises(Conflict): self.w.action(self.sid, 'handoff', {'request_id': 'disabled', 'approval_id': approval})
        self.assertIsNone(self.w.view(self.sid)['review']['handoff'])
