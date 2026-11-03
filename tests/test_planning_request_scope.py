"""Conversation-local planning identities across verified admission and recovery."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from acquisition.bootstrap import build
from acquisition.contracts import Conflict, NotFound, digest
from acquisition.conversations import FIXTURE_MESSAGE
from acquisition.reasoning import ModelConfig
from test_legacy_action_replay import durable_rows
from test_conversations import PlannerModel


class PlanningRequestScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'plans.sqlite';self.now=1792972800.
        self.config=ModelConfig('test/model',max_calls=2,force_tool_choice=True)
        self.app=build(self.path,clock=lambda:self.now,model_config=self.config,verified_admissions=True)
        self.org='one';self.first=self.chat('first');self.second=self.chat('second')

    def chat(self, key, organization=None):
        org=organization or self.org
        cid=self.app.conversations.create(org,key)['id']
        self.app.conversations.message(org,cid,'message',0,FIXTURE_MESSAGE)
        return cid

    def intent(self, run, organization=None):
        org=organization or self.org
        state=self.app.tasks.inspect(org,run)
        return self.app.admissions.store.get(org,state['admission']['id'])

    def test_same_native_key_in_two_chats_preserves_native_tasks_and_distinct_admissions(self):
        runs=[];intents=[]
        for cid in (self.first,self.second):
            run=self.app.conversations.plan_fixture(self.org,cid,'shared',1)
            intent=self.intent(run);runs.append(run);intents.append(intent)
            task=intent.tasks[0].inputs
            self.assertEqual(task['request_id'],'shared')
            self.assertEqual(task['conversation_id'],cid)
            self.assertEqual(task['run_request_id'],'conversation-plan:'+digest({'conversation':cid,'request':'shared'}))
            self.assertEqual(self.app.conversations.view(self.org,cid)['current_plan']['request_id'],'shared')
            with self.app.tasks.database.connect() as db:
                journal=db.execute('SELECT request_id,payload FROM conversation_plans WHERE organization=? AND conversation_id=?',(self.org,cid)).fetchone()
                self.assertEqual(journal['request_id'],'shared')
                self.assertEqual(json.loads(journal['payload'])['request_id'],'shared')
            self.assertEqual(self.app.worker.drain(self.org,run_id=run),0)
        self.assertNotEqual(runs[0],runs[1]);self.assertNotEqual(intents[0].id,intents[1].id)
        self.assertNotEqual(intents[0].request_id,intents[1].request_id)
        self.app.conversations.message(self.org,self.first,'later',1,'Use a £400 budget instead.')
        before=durable_rows(self.app)
        reopened=build(self.path,clock=lambda:self.now,model_config=self.config)
        with patch.object(reopened.conversations,'planning_context',side_effect=AssertionError('Rebuilt replay context')):
            for cid,run in zip((self.first,self.second),runs):
                self.assertEqual(reopened.conversations.plan_fixture(self.org,cid,'shared',1),run)
            with self.assertRaises(Conflict):reopened.conversations.plan_fixture(self.org,self.first,'shared',2)
        self.assertEqual(durable_rows(reopened),before)

    def test_model_requests_share_native_key_but_not_consent_or_configuration(self):
        first=self.app.conversations.plan(self.org,self.first,'shared',1)
        second=self.app.conversations.plan(self.org,self.second,'shared',1)
        a,b=self.intent(first),self.intent(second)
        self.assertIsNotNone(a.consent_id);self.assertNotEqual(a.consent_id,b.consent_id)
        before=durable_rows(self.app)
        wrong=build(self.path,clock=lambda:self.now,model_config=replace(self.config,model='other/model'))
        with self.assertRaises(Conflict):wrong.conversations.plan(self.org,self.first,'shared',1)
        with self.assertRaises(Conflict):self.app.conversations.plan_fixture(self.org,self.first,'shared',1)
        context=self.app.admissions.store.request_inputs(self.org,a.request_id)['context']
        with self.assertRaises(Conflict):self.app.conversations.plan(self.org,self.first,'shared',1,frozen_context=context|{'previous_results':[{}]})
        self.assertEqual(durable_rows(self.app),before)
        self.assertEqual(self.app.calls.inspect(self.org,first),[])
        self.assertEqual(self.app.calls.inspect(self.org,second),[])

    def test_raw_staged_request_keeps_its_key_bytes_and_fingerprint_while_another_chat_uses_same_native_key(self):
        store=self.app.admissions.store;native='shared'
        context=self.app.conversations.planning_context(self.org,self.first,native,1,True)
        original=store.request_planning(self.org,self.first,native,1,context,fixture=True,allow_model=False)
        with store.database.connect() as db:saved=tuple(db.execute('SELECT * FROM admission_requests WHERE organization=? AND request_id=?',(self.org,native)).fetchone())
        second=self.app.conversations.plan_fixture(self.org,self.second,native,1)
        reopened=build(self.path,clock=lambda:self.now,model_config=self.config)
        first=reopened.conversations.plan_fixture(self.org,self.first,native,1)
        self.assertEqual(store.find_request(self.org,native).run_id,first)
        self.assertEqual(store.get_request(self.org,native),original)
        with store.database.connect() as db:self.assertEqual(tuple(db.execute('SELECT * FROM admission_requests WHERE organization=? AND request_id=?',(self.org,native)).fetchone()),saved)
        self.assertNotEqual(first,second)
        before=durable_rows(self.app)
        self.assertEqual(reopened.conversations.plan_fixture(self.org,self.first,native,1),first)
        self.assertEqual(durable_rows(self.app),before)

    def test_partial_new_admission_recovers_original_staging_without_new_context(self):
        with patch.object(self.app.admissions.store,'admit',side_effect=OSError('Interrupted after staging')):
            with self.assertRaises(OSError):self.app.conversations.plan_fixture(self.org,self.first,'retry',1)
        pending=self.app.admissions.store.pending_requests(self.org)
        self.assertEqual(len(pending),1);saved=pending[0]
        reopened=build(self.path,clock=lambda:self.now,model_config=self.config)
        with patch.object(reopened.conversations,'planning_context',side_effect=AssertionError('Rebuilt admitted context')):
            run=reopened.conversations.plan_fixture(self.org,self.first,'retry',1)
        self.assertEqual(reopened.admissions.store.get_request(self.org,saved.request_id),saved)
        self.assertEqual(self.intent(run),saved)

    def test_concurrent_shared_native_keys_have_separate_owners(self):
        def plan(cid):return self.app.conversations.plan_fixture(self.org,cid,'same',1)
        with ThreadPoolExecutor(max_workers=2) as pool:runs=list(pool.map(plan,(self.first,self.second)))
        self.assertEqual(len(set(runs)),2)
        for cid,run in zip((self.first,self.second),runs):
            self.assertEqual(self.intent(run).ownership.scope_id,cid)
            self.assertEqual(self.app.worker.drain(self.org,run_id=run),0)

    def test_native_key_cannot_be_reused_for_a_later_revision_or_by_alternate_writers(self):
        # Exercise the new-format facade in an unselected store too, so the
        # compatibility writer must understand the native key reservation.
        path=Path(self.temp.name)/'mixed.sqlite';app=build(path,clock=lambda:self.now,model_config=self.config,gateway=PlannerModel())
        cid=app.conversations.create(self.org,'mixed')['id'];app.conversations.message(self.org,cid,'message',0,FIXTURE_MESSAGE)
        context=app.conversations.planning_context(self.org,cid,'repeat',1,False)
        with patch.object(app.admissions.store,'admit',side_effect=OSError):
            with self.assertRaises(OSError):app.admissions.planning(self.org,cid,'repeat',1,fixture=False,config=self.config,context_factory=lambda:context)
        app.conversations.message(self.org,cid,'next',1,'Use a £400 budget instead.')
        context=app.conversations.planning_context(self.org,cid,'repeat',2,False)
        before=durable_rows(app)
        with self.assertRaises(Conflict):app.conversations.plan(self.org,cid,'repeat',2,frozen_context=context)
        with self.assertRaises(Conflict):app.admissions.planning(self.org,cid,'repeat',2,fixture=False,config=self.config,context_factory=lambda:context)
        # A distinct outer key must not mint another reservation of the same
        # native command, even when calling the storage port directly.
        with self.assertRaises(Conflict):app.admissions.store.request_planning(self.org,cid,'another-wrapper',2,context,
            fixture=False,allow_model=True,model_config=self.config,native_request_id='repeat')
        self.assertEqual(durable_rows(app),before)

    def test_planning_namespace_does_not_collide_with_a_campaign_request_or_another_organization(self):
        campaign=self.app.start(self.org,'shared',size=20)
        plan=self.app.conversations.plan_fixture(self.org,self.first,'shared',1)
        other=self.chat('first','other-org')
        foreign=self.app.conversations.plan_fixture('other-org',other,'shared',1)
        self.assertEqual(len({campaign,plan,foreign}),3)
        self.assertEqual(self.intent(foreign,'other-org').ownership.organization,'other-org')
        self.assertIsNone(self.app.admissions.store.request_for_planning('other-org',self.first,'shared'))
        before=durable_rows(self.app)
        with self.assertRaises(NotFound):self.app.conversations.plan_fixture('other-org',self.first,'shared',1)
        self.assertEqual(durable_rows(self.app),before)

    def test_six_request_capacity_counts_native_and_scoped_records_once(self):
        for revision in range(1,7):
            if revision>1:self.app.conversations.message(self.org,self.first,'message-'+str(revision),revision-1,'Use a £600 budget.')
            self.app.conversations.plan(self.org,self.first,'plan-'+str(revision),revision)
        self.app.conversations.message(self.org,self.first,'message-7',6,'Use a £600 budget.')
        before=durable_rows(self.app)
        with self.assertRaisesRegex(ValueError,'budget exhausted'):
            self.app.conversations.plan(self.org,self.first,'plan-7',7)
        with self.assertRaisesRegex(ValueError,'budget exhausted'):
            self.app.admissions.store.request_planning(self.org,self.first,'another-wrapper',7,{},
                fixture=False,allow_model=True,model_config=self.config,native_request_id='plan-7')
        self.assertEqual(durable_rows(self.app),before)
        with self.app.tasks.database.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM model_calls').fetchone()[0],0)

    def test_fresh_process_replays_new_plans_with_the_native_key(self):
        expected={cid:self.app.conversations.plan_fixture(self.org,cid,'shared',1) for cid in (self.first,self.second)}
        script='''import json,sys
from pathlib import Path
from acquisition.bootstrap import build
app=build(Path(sys.argv[1]))
print(json.dumps({cid:app.conversations.plan_fixture('one',cid,'shared',1) for cid in sys.argv[2:]}))
'''
        before=durable_rows(self.app)
        result=subprocess.run([sys.executable,'-c',script,str(self.path),self.first,self.second],
            env=dict(os.environ,PYTHONPATH=str(Path('src').resolve())),capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(json.loads(result.stdout),expected)
        self.assertEqual(durable_rows(self.app),before)
