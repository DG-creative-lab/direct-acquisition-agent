"""Bound conversational simulation commands and immutable accepted learning."""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
import test_conversation_handoff as fixtures
from acquisition.contracts import Conflict


class ConversationLearningTests(unittest.TestCase):
    setUp = fixtures.ConversationHandoffTests.setUp
    approve = fixtures.ConversationHandoffTests.approve

    def accept(self):
        a = self.approve()
        return self.w.action(self.sid, 'handoff', {'request_id':'handoff','approval_id':a})['review']['handoff']

    def step(self, action, request, job, cohort=None):
        payload = {'request_id':request,'handoff_id':job}
        if cohort is not None: payload['cohort_id'] = cohort
        return self.w.action(self.sid, action, payload)

    def test_bound_commands_reject_unaccepted_or_substituted_job_and_cohort_before_mutation(self):
        with self.assertRaises(Conflict): self.step('open-learning','not-accepted','wrong')
        job = self.accept()['id']
        before = self.w._session(self.sid)
        with self.assertRaises(Conflict): self.step('open-learning','wrong-job','other-job')
        self.assertEqual(self.w._session(self.sid), before)
        opened = self.step('open-learning','open',job)
        cohort = opened['learning']['cohort']['id']
        for action in ('observe','finalize'):
            for bad_job,bad_cohort in ((job,'other-cohort'),('other-job',cohort)):
                with self.subTest(action=action, job=bad_job, cohort=bad_cohort):
                    with self.assertRaises(Conflict): self.step(action,'bad-'+action,bad_job,bad_cohort)
                    self.assertEqual(self.w.view(self.sid)['learning'], opened['learning'])
                    self.assertEqual(self.w._session(self.sid)['clock'], opened['session']['clock'])

    def test_pending_denominators_and_history_finalize_once_across_process_replay(self):
        receipt = self.accept()
        opened = self.step('open-learning','open',receipt['id'])
        l = opened['learning']; cohort = l['cohort']['id']
        expected = opened['review']['manifest']['counts']['mailed'] + opened['review']['manifest']['counts']['holdout']
        self.assertEqual(l['enrolled'], expected)
        self.assertEqual(l['missing'], expected)
        early = self.step('observe','early',receipt['id'],cohort)['learning']
        self.assertGreater(early['received'], 0)
        self.assertGreater(early['missing'], 0)
        self.assertEqual(early['beliefs'], [])
        self.assertEqual(early['recommendations'], [])
        self.w.message_conversation(self.c,'edit',1,'Use £300 in the next campaign.')
        final = self.step('finalize','final',receipt['id'],cohort)
        l = final['learning']
        self.assertEqual(l['missing'],0)
        self.assertEqual(l['status'],'finalized')
        self.assertEqual(sum(b['trials'] for b in l['beliefs']), expected)
        self.assertEqual({b['arm'] for b in l['beliefs']}, {'A','B','no_mail'})
        self.assertEqual(final['review']['handoff'],receipt)
        self.assertFalse(final['review']['candidate_valid'])
        with self.w.control() as db:
            db.execute('UPDATE commands SET done=0 WHERE session_id=? AND request_id=?',(self.sid,'final'))
        code = """import sys,json
from acquisition.workspace import Workspace
w=Workspace(sys.argv[1],real_clock=lambda:1792972800.0)
s=w.action(sys.argv[2],'finalize',json.loads(sys.argv[3]))
print(json.dumps(s['learning']))
"""
        result = subprocess.run([sys.executable,'-c',code,str(self.root),self.sid,json.dumps({'request_id':'final','handoff_id':receipt['id'],'cohort_id':cohort})],env=dict(os.environ,PYTHONPATH=str(Path('src').resolve())),capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        replay = json.loads(result.stdout)
        self.assertEqual(replay,l)
        self.assertEqual(sum(e['kind']=='cohort_finalized' for e in replay['events']),1)

    def test_learning_role_and_request_identity_still_bound(self):
        job = self.accept()['id']
        opened = self.step('open-learning','open',job)
        cohort = opened['learning']['cohort']['id']
        with self.assertRaises(Conflict): self.step('finalize','open',job,cohort)
        session = self.w._session(self.sid)
        app = self.w._app(session)
        app.reviews.store.register_actor(session['organization'],'local-operator',('operator',),enabled=False)
        with self.assertRaises(ValueError): self.step('finalize','denied',job,cohort)
        self.assertEqual(self.w.view(self.sid)['learning']['beliefs'],[])
