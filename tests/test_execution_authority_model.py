"""Independent transition oracle at the current SQLite reservation boundary.

This is a baseline for the admission-store cutover, not proof that the new
admission port is implemented. Owners are fixed by the scenario specification;
the oracle never reads production ownership or status derivation helpers.
"""

import itertools
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from acquisition.bootstrap import build
from acquisition.contracts import Conflict
from acquisition.reasoning import CallScope, ModelError
from acquisition.runtime import LeaseLost, TaskSpec


OWNERS={'a1':'a','a2':'a','b1':'b'}
RESPONSE={'usage':{'cost':0},'observation':'test-only'}


class ExecutionOracle:
    """Finite specification: two accounts, three leases, two slots per account."""
    def __init__(self):
        self.stopped=set()
        self.calls={}

    def transition(self, action):
        operation,run,key=action
        if operation=='restart':return 'ok'
        if operation=='stop':
            self.stopped.add(run)  # Here run names the account, not a runtime ID.
            return 'ok'
        if operation=='reserve':
            owner=OWNERS[run]
            if owner in self.stopped:return 'blocked'
            prior=self.calls.get((run,key))
            if prior:return 'replay' if prior=='recorded' else 'blocked'
            if sum(OWNERS[r]==owner for r,k in self.calls)>=2:return 'blocked'
            self.calls[run,key]='reserved'
            return 'new'
        if self.calls.get((run,key))!='reserved':return 'blocked'
        # An observation can arrive after stop. It cannot authorize more work.
        self.calls[run,key]='unknown' if operation=='unknown' else 'recorded'
        return 'ok'

    def projection(self, owner):
        calls={(r,k):s for (r,k),s in self.calls.items() if OWNERS[r]==owner}
        counts=dict(in_progress=0,uncertain=0,rejected=0,completed=0)
        for status in calls.values():
            counts['completed' if status=='recorded' else
                   'uncertain' if status=='unknown' or owner in self.stopped else 'in_progress']+=1
        return dict(used=len(calls),remaining=2-len(calls),stopped=owner in self.stopped,counts=counts,
                    pending_receipts=sum(s=='reserved' for s in calls.values()),
                    cost_complete=all(s=='recorded' for s in calls.values()))


class SqliteScenario:
    """Thin public-port driver. SQL only installs the test's smaller quota."""
    organization='local-conversations'

    def __init__(self, path):
        self.path=path
        self.app=build(path,clock=lambda:1000.0)
        self.conversations={}
        self.runs={}
        self.scopes={}
        for label in ('a','b'):
            store=self.app.conversations.store
            conversation=store.create(self.organization,'chat-'+label,'Test '+label,1000.0)
            store.append(self.organization,conversation,'message-'+label,0,'Prepare a £600 experiment.',1000.0)
            self.conversations[label]=conversation
            self.app.execution.view(self.organization,conversation)
        with self.app.calls.database.transaction() as db:
            db.execute('UPDATE conversation_execution SET call_limit=2')
        for label,owner in OWNERS.items():
            run=self.app.tasks.create(self.organization,'run-'+label,[TaskSpec('test.inference',
                {'brief':{'conversation_id':self.conversations[owner],'conversation_revision':1}})],1000.0)
            claim=self.app.tasks.claim(self.organization,1000.0,180.0,run_id=run)
            self.runs[label]=run
            self.scopes[label]=CallScope(self.organization,run,claim.task_id,claim.token)

    def transition(self, action):
        operation,run,key=action
        try:
            if operation=='restart':self.app=build(self.path,clock=lambda:1000.0)
            elif operation=='stop':self.app.execution.stop(self.organization,self.conversations[run],'stop-'+run,1)
            elif operation=='reserve':
                value=self.app.calls.reserve(self.scopes[run],key,'a'*64,12,1000.0)
                return 'new' if value is None else 'replay'
            else:
                self.app.calls.record(self.scopes[run],key,None if operation=='unknown' else RESPONSE,
                                      'provider_request_failed' if operation=='unknown' else None)
            return 'ok'
        except (Conflict,ModelError,LeaseLost):return 'blocked'


class ExecutionAuthorityModelTests(unittest.TestCase):
    def assert_matches(self, scenario, oracle):
        for owner,conversation in scenario.conversations.items():
            view=scenario.app.execution.view(scenario.organization,conversation)
            for name,expected in oracle.projection(owner).items():
                self.assertEqual(view[name],expected,(owner,name,oracle.calls))
            self.assertTrue(view['accounting_complete'])
        for label,run in scenario.runs.items():
            rows=scenario.app.calls.inspect(scenario.organization,run)
            self.assertEqual({r['key']:r['status'] for r in rows},
                             {k:s for (r,k),s in oracle.calls.items() if r==label})

    def trace(self, actions):
        with tempfile.TemporaryDirectory() as directory:
            scenario=SqliteScenario(Path(directory)/'application.sqlite')
            oracle=ExecutionOracle()
            self.assert_matches(scenario,oracle)
            for action in actions:
                self.assertEqual(scenario.transition(action),oracle.transition(action),action)
                self.assert_matches(scenario,oracle)

    def test_every_pair_in_the_bounded_transition_alphabet(self):
        alphabet=(('reserve','a1','one'),('reserve','a2','one'),('reserve','b1','one'),
                  ('record','a1','one'),('unknown','a1','one'),('stop','a',None),('restart',None,None))
        # All 49 pairs include invalid observations, duplicate reservations,
        # stop ordering, shared owners, isolated accounts and restart ordering.
        for actions in itertools.product(alphabet,repeat=2):
            with self.subTest(actions=actions):self.trace(actions)

    def test_shared_last_slot_and_completed_replay_at_the_limit(self):
        self.trace((('reserve','a1','one'),('record','a1','one'),('reserve','a2','one'),
                    ('reserve','a1','two'),('reserve','a1','one'),('reserve','b1','one'),
                    ('restart',None,None),('reserve','a2','two')))

    def test_uncertain_call_and_late_observation_across_stop_restart(self):
        self.trace((('reserve','a1','one'),('unknown','a1','one'),('restart',None,None),
                    ('reserve','a1','one'),('reserve','a2','one'),('stop','a',None),
                    ('record','a2','one'),('reserve','a2','two'),('reserve','b1','one'),
                    ('restart',None,None),('reserve','a1','one')))

    def test_fresh_process_observes_the_same_stopped_account_and_original_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            scenario=SqliteScenario(Path(directory)/'application.sqlite');oracle=ExecutionOracle()
            for action in (('reserve','a1','one'),('unknown','a1','one'),('stop','a',None)):
                self.assertEqual(scenario.transition(action),oracle.transition(action))
            code="""import json,sys
from acquisition.bootstrap import build
app=build(sys.argv[1],clock=lambda:1000.0)
print(json.dumps({'view':app.execution.view('local-conversations',sys.argv[2]),
                  'calls':app.calls.inspect('local-conversations',sys.argv[3])}))
"""
            result=subprocess.run([sys.executable,'-c',code,str(scenario.path),scenario.conversations['a'],scenario.runs['a1']],
                                  env=dict(os.environ,PYTHONPATH='src'),capture_output=True,text=True,check=True)
            observed=json.loads(result.stdout)
            for name,expected in oracle.projection('a').items():self.assertEqual(observed['view'][name],expected)
            self.assertEqual(observed['calls'][0]['status'],'unknown')
            self.assertEqual(observed['calls'][0]['error'],'provider_request_failed')


if __name__=='__main__':unittest.main()
