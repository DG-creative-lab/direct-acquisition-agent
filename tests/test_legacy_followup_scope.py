"""Historical receipts never authorize a new unsupported follow-up request."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from acquisition.adapters.sqlite.conversations import SqliteConversations
from acquisition.contracts import Conflict, canonical
from acquisition.workspace import Workspace
import test_conversation_handoff as handoff_tests


class LegacyFollowupScopeTests(unittest.TestCase):
    approve = handoff_tests.ConversationHandoffTests.approve

    def setUp(self):
        original = SqliteConversations.admit

        def legacy_admission(store, *args, **kwargs):
            # Emulate the old producer before its task or draft is created.
            # Assertions below run with all current guards installed.
            frozen = original(store, *args, **kwargs)
            frozen = {k: v for k, v in frozen.items() if k not in {'requested_scope', 'budget_policy'}}
            with store.database.transaction() as db:
                db.execute('UPDATE conversation_plans SET payload=? WHERE organization=? AND conversation_id=? AND request_id=?',
                           (canonical(frozen), 'local-conversations', frozen['conversation_id'], frozen['request_id']))
            return frozen

        with patch.object(SqliteConversations, 'admit', legacy_admission):
            handoff_tests.ConversationHandoffTests.setUp(self)
        self.app = self.w._app(self.w._session(self.sid))
        self.owner = self.w._session(self.sid)['organization']
        self.database = self.app.tasks.database
        self.assertNotIn('requested_scope', self.state['review']['manifest']['brief'])
        self.assertNotIn('campaign_scope', self.state['review']['manifest'])
        self.draft = self.app.drafts.get(self.owner, self.state['review']['subject']['draft_id'])
        self.w.action(self.sid, 'handoff', {'request_id': 'legacy-handoff', 'approval_id': self.approve()})
        self.w.action(self.sid, 'open-learning', {'request_id': 'legacy-open'})
        self.learning = self.w.action(self.sid, 'finalize', {'request_id': 'legacy-final'})['learning']
        self.cohort = self.learning['cohort']['id']
        self.proposal = self.w.propose_followup(self.sid, 'legacy-proposal', self.cohort)
        self.assertNotIn('requested_scope', self.proposal['brief'])
        self.app = self.w._app(self.w._session(self.sid))
        self.database = self.app.tasks.database
        self.assertEqual(self.app.learning.store.hypothesis_source(self.owner, self.cohort)['status'], 'finalized')

    def counts(self):
        with self.database.connect() as db:
            return {table: db.execute('SELECT count(*) FROM ' + table).fetchone()[0]
                    for table in ('review_commands', 'creative_contexts', 'audiences', 'tasks', 'drafts', 'draft_operations', 'model_calls', 'review_decisions', 'review_events', 'simulated_agency_jobs')}

    def raw_proposal(self):
        return {k: v for k, v in self.proposal.items() if k not in {'id', 'kind'}}

    def test_legacy_source_is_checked_before_contexts_save_and_new_admission_but_replay_survives(self):
        before = self.counts()
        with self.database.connect() as db:
            row = db.execute('SELECT payload FROM conversation_plans WHERE organization=? AND conversation_id=?',
                             ('local-conversations', self.c)).fetchone()
            original = json.loads(row[0])
            current = db.execute('SELECT content FROM conversation_messages WHERE organization=? AND conversation_id=?',
                                 ('local-conversations', self.c)).fetchone()[0]
        for source in ('frozen', 'current', 'missing-plan'):
            with self.subTest(source=source):
                try:
                    with self.database.transaction() as db:
                        if source == 'frozen':
                            frozen = copy.deepcopy(original)
                            frozen['messages'][0]['content'] = 'Use £600 for an email campaign in France.'
                            db.execute('UPDATE conversation_plans SET payload=? WHERE organization=? AND conversation_id=?',
                                       (canonical(frozen), 'local-conversations', self.c))
                        elif source == 'current':
                            db.execute('UPDATE conversation_messages SET content=? WHERE organization=? AND conversation_id=?',
                                       ('Use £600 for an email campaign in France.', 'local-conversations', self.c))
                        else:
                            db.execute('DELETE FROM conversation_plans WHERE organization=? AND conversation_id=?',
                                       ('local-conversations', self.c))
                    with self.assertRaises(Conflict):
                        self.app.learning.store.hypothesis_source(self.owner, self.cohort)
                    with self.assertRaises(Conflict):
                        self.w.propose_followup(self.sid, 'new-' + source, self.cohort)
                    with self.assertRaises(Conflict):
                        self.app.followups.put(self.owner, 'save-' + source, self.raw_proposal())
                    with self.assertRaises(Conflict):
                        self.w.prepare_followup(self.sid, 'prepare-' + source, self.proposal['id'], 'fixture', False)
                    self.assertEqual(self.counts(), before)
                    self.assertEqual(self.w.propose_followup(self.sid, 'legacy-proposal', self.cohort), self.proposal)
                    self.assertEqual(self.app.followups.get(self.owner, self.proposal['id']), self.proposal)
                    self.assertEqual(self.app.learning.store.view(self.owner, self.cohort)['finalization'], self.learning['finalization'])
                    self.assertEqual(self.app.drafts.get(self.owner, self.draft.id), self.draft)
                    if source == 'current':
                        code = """import sys
from acquisition.contracts import Conflict
from acquisition.workspace import Workspace
w=Workspace(sys.argv[1],real_clock=lambda:1792972800.)
assert w.propose_followup(sys.argv[2],'legacy-proposal',sys.argv[3])['id']==sys.argv[4]
try:w.propose_followup(sys.argv[2],'fresh-process-proposal',sys.argv[3])
except Conflict:print('blocked')
else:raise AssertionError('An unsupported legacy source admitted a new follow-up')
"""
                        result = subprocess.run([sys.executable, '-c', code, str(self.root), self.sid, self.cohort, self.proposal['id']],
                                                env=dict(os.environ, PYTHONPATH=str(Path('src').resolve())), capture_output=True, text=True, timeout=15)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(result.stdout.strip(), 'blocked')
                finally:
                    with self.database.transaction() as db:
                        db.execute('INSERT OR REPLACE INTO conversation_plans(organization,conversation_id,request_id,revision,payload,created_at) VALUES(?,?,?,?,?,?)',
                                   ('local-conversations', self.c, original['request_id'], original['revision'], canonical(original), 1792972800.))
                        db.execute('UPDATE conversation_messages SET content=? WHERE organization=? AND conversation_id=?',
                                   (current, 'local-conversations', self.c))
        self.assertEqual(Workspace(self.root, real_clock=lambda: 1792972800.).propose_followup(
            self.sid, 'supported-legacy-proposal', self.cohort)['brief'], self.proposal['brief'])

    def test_legacy_source_change_during_proposal_writes_rolls_back_the_receipt(self):
        before = self.counts()
        with self.database.connect() as db:
            current = db.execute('SELECT content FROM conversation_messages WHERE organization=? AND conversation_id=?',
                                 ('local-conversations', self.c)).fetchone()[0]
            db.execute("CREATE TRIGGER alter_legacy_request AFTER INSERT ON review_commands "
                       "WHEN NEW.request_id='followup-request:legacy-save-race' BEGIN "
                       "UPDATE conversation_messages SET content='Use email in France with £600.' "
                       "WHERE organization='local-conversations' AND conversation_id='" + self.c + "'; END")
        with self.assertRaises(Conflict):
            self.app.followups.put(self.owner, 'legacy-save-race', self.raw_proposal())
        self.assertEqual(self.counts(), before)
        with self.database.connect() as db:
            self.assertEqual(db.execute('SELECT content FROM conversation_messages WHERE organization=? AND conversation_id=?',
                                        ('local-conversations', self.c)).fetchone()[0], current)
        self.assertEqual(self.app.followups.get(self.owner, self.proposal['id']), self.proposal)

    def test_later_legacy_generations_retain_the_original_request_boundary(self):
        child = self.w.prepare_followup(self.sid, 'legacy-child', self.proposal['id'], 'fixture', False)
        self.assertTrue(child['review']['candidate_valid'])
        sid = child['session']['id']
        approved = self.w.action(sid, 'approve', {'request_id': 'child-review', 'subject_id': child['review']['subject']['id'], 'reason': 'Reviewed this exact child.'})
        self.w.action(sid, 'handoff', {'request_id': 'child-handoff', 'approval_id': approved['review']['approval']['id']})
        self.w.action(sid, 'open-learning', {'request_id': 'child-open'})
        learned = self.w.action(sid, 'finalize', {'request_id': 'child-final'})
        cohort = learned['learning']['cohort']['id']
        descendant = self.w.propose_followup(sid, 'legacy-grandchild', cohort)
        self.assertNotIn('requested_scope', descendant['brief'])
        before = self.counts()
        self.w.message_conversation(self.c, 'amended-legacy-root', 1, 'Use email in France with £600.')
        with self.assertRaises(Conflict):
            self.w.propose_followup(sid, 'changed-root-grandchild', cohort)
        with self.assertRaises(Conflict):
            self.w.prepare_followup(sid, 'changed-root-prepare', descendant['id'], 'fixture', False)
        self.assertEqual(self.counts(), before)
        self.assertEqual(self.w.propose_followup(sid, 'legacy-grandchild', cohort), descendant)


    def test_legacy_child_source_mutations_roll_back_publication_review_and_acceptance(self):
        child = self.w.prepare_followup(self.sid, 'legacy-child-atomic', self.proposal['id'], 'fixture', False)
        sid = child['session']['id']
        draft = self.app.drafts.get(self.owner, child['review']['subject']['draft_id'])
        subject = child['review']['subject']['id']
        for stage in ('publication', 'review_approve', 'simulated_handoff_accepted'):
            with self.subTest(stage=stage):
                approval = None
                if stage == 'simulated_handoff_accepted':
                    approval = self.w.action(sid, 'approve', {'request_id': 'atomic-child-approve', 'subject_id': subject,
                                                             'reason': 'Reviewed this exact child.'})['review']['approval']['id']
                before = self.counts()
                with self.database.connect() as db:
                    message = db.execute('SELECT content FROM conversation_messages WHERE organization=? AND conversation_id=?',
                                         ('local-conversations', self.c)).fetchone()[0]
                    condition = "AFTER INSERT ON draft_operations" if stage == 'publication' else "AFTER INSERT ON review_events WHEN NEW.kind='" + stage + "'"
                    db.execute('CREATE TRIGGER change_legacy_child_source ' + condition + " BEGIN UPDATE conversation_messages "
                               "SET content='Use email in France with £600.' WHERE organization='local-conversations' AND conversation_id='" + self.c + "'; END")
                try:
                    with self.assertRaises(Conflict):
                        if stage == 'publication':
                            self.app.drafts.put(self.owner, 'legacy-child-alternate-operation', draft)
                        elif stage == 'review_approve':
                            self.w.action(sid, 'approve', {'request_id': 'racing-child-approve', 'subject_id': subject,
                                                          'reason': 'Reviewed this exact child.'})
                        else:
                            self.w.action(sid, 'handoff', {'request_id': 'racing-child-handoff', 'approval_id': approval})
                    self.assertEqual(self.counts(), before)
                    with self.database.connect() as db:
                        self.assertEqual(db.execute('SELECT content FROM conversation_messages WHERE organization=? AND conversation_id=?',
                                                    ('local-conversations', self.c)).fetchone()[0], message)
                finally:
                    with self.database.connect() as db:
                        db.execute('DROP TRIGGER change_legacy_child_source')
