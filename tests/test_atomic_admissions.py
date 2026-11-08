"""Real SQLite admission effects, consent, scope, crashes and paused execution."""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, closing
from dataclasses import replace
from pathlib import Path
from threading import Event
from unittest.mock import patch

from acquisition.adapters.sqlite.database import Database, ATOMIC_ADMISSIONS
from acquisition.adapters.sqlite.tasks import insert_run
from acquisition.bootstrap import build, build_admissions
from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.conversations import ExecutionOwnership, FIXTURE_MESSAGE, planning_intent
from acquisition.reasoning import CallScope, ModelConfig, ModelError
from acquisition.runtime import TaskSpec
from test_conversations import PlannerModel


class AtomicAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.now=1792886400.0
        self.config=ModelConfig('test/model',max_calls=2,force_tool_choice=True)
        self.open('first')

    def open(self, name):
        self.path=self.root/(name+'.sqlite');self.model=PlannerModel()
        self.app=build(self.path,clock=lambda:self.now,gateway=self.model,model_config=self.config)
        self.store=build_admissions(self.path,clock=lambda:self.now)
        self.org='local-conversations'
        self.cid=self.app.conversations.create(self.org,'chat')['id']
        self.app.conversations.message(self.org,self.cid,'message',0,FIXTURE_MESSAGE)

    def context(self, key='prepare',fixture=True):
        return self.app.conversations.planning_context(self.org,self.cid,key,1,fixture)

    def request(self, key='prepare',fixture=True,context=None):
        return self.store.request_planning(self.org,self.cid,key,1,context or self.context(key,fixture),
            fixture=fixture,allow_model=not fixture,model_config=None if fixture else self.config)

    def counts(self):
        with self.store.database.connect() as db:
            return {t:db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in
                    ('admission_requests','execution_admissions','conversation_plans','runs','tasks','events',
                     'execution_runs','conversation_execution','model_calls','review_decisions','simulated_agency_jobs')}

    def test_request_is_non_executable_and_admission_commits_exact_linked_records(self):
        context=self.context(fixture=False)
        context['budget_policy']='absolute-gbp/v1'
        intent=self.request(fixture=False,context=context)
        self.assertEqual(intent.tasks[0].inputs['budget_policy'],'absolute-gbp/v5')
        self.assertEqual(self.counts()['admission_requests'],1)
        self.assertEqual(self.counts()['runs'],0)
        self.assertIsNone(self.store.find_request(self.org,'prepare'))
        self.assertEqual(self.store.get_request(self.org,'prepare'),intent)
        self.assertEqual(self.store.pending_requests(self.org),[intent])
        self.assertIsNone(self.store.get_request('foreign','prepare'))
        self.assertEqual(self.store.pending_requests('foreign'),[])
        receipt=self.store.admit(intent,self.now)
        self.assertEqual(self.store.pending_requests(self.org),[])
        self.assertEqual(self.store.get(self.org,intent.id),intent)
        self.assertEqual(self.store.find_request(self.org,'prepare'),receipt)
        counts=self.counts()
        for table in ('runs','tasks','execution_admissions','execution_runs','conversation_plans','conversation_execution'):
            self.assertEqual(counts[table],1,table)
        self.assertEqual(counts['events'],2)
        self.assertEqual(counts['model_calls'],0)
        self.assertEqual(counts['review_decisions'],0)
        self.assertEqual(counts['simulated_agency_jobs'],0)
        self.assertEqual(self.app.execution.for_run(self.org,receipt.run_id)['run_revision'],1)
        with self.store.database.connect() as db:
            self.assertEqual(db.execute('SELECT status FROM execution_admissions').fetchone()[0],'paused')
        self.assertEqual(len(self.model.requests),0)

    def test_missing_consent_changed_inputs_and_mode_downgrade_cannot_admit(self):
        context=self.context(fixture=False)
        with self.assertRaises(ValueError):self.store.request_planning(self.org,self.cid,'denied',1,context,
            fixture=False,allow_model=False,model_config=self.config)
        original=self.request(fixture=False,context=context)
        altered=[replace(original,consent_id='other-consent'),
            replace(original,model_config=replace(self.config,model='other/model')),
            replace(original,model_config=None,consent_id=None),
            replace(original,source_fingerprint='0'*64),replace(original,context_fingerprint='1'*64),
            replace(original,ownership=ExecutionOwnership('standalone',self.org,'root')),
            replace(original,parent_run_id='another-run'),replace(original,workflow_version='unknown/v1'),
            replace(original,task_plan_json=canonical([{'capability':'test.unknown','inputs':{},'max_attempts':3}]))]
        for value in altered:
            with self.subTest(value=value),self.assertRaises(Conflict):self.store.admit(value,self.now)
        with self.assertRaises(NotFound):self.store.admit(replace(original,request_id='no-consent'),self.now)
        with self.assertRaises(Conflict):self.store.request_planning(self.org,self.cid,'prepare',1,context,
            fixture=False,allow_model=True,model_config=replace(self.config,model='other/model'))
        self.assertEqual(self.counts()['runs'],0)
        self.assertEqual(self.counts()['admission_requests'],1)

    def test_replay_is_observation_after_stop_and_changed_request_key_conflicts(self):
        context=self.context();intent=self.request(context=context)
        receipt=self.store.admit(intent,self.now);before=self.counts()
        self.app.execution.stop(self.org,self.cid,'stop',1)
        stopped=self.counts()
        self.now+=10
        self.assertEqual(self.store.admit(intent,self.now),receipt)
        self.assertEqual(self.store.request_planning(self.org,self.cid,'prepare',1,context,
            fixture=True,allow_model=False),intent)
        self.assertEqual(self.counts(),stopped)
        with self.assertRaises(NotFound):self.store.admit(replace(intent,request_id='different'),self.now)
        self.assertEqual(self.counts()['runs'],before['runs'])

    def test_alternate_key_cannot_repeat_a_staged_or_admitted_revision(self):
        first=self.request()
        for admitted in (False,True):
            if admitted:self.store.admit(first,self.now)
            with self.subTest(admitted=admitted),self.assertRaises(Conflict):self.request('another-key')
        self.assertEqual(self.counts()['runs'],1)

    def test_foreign_organization_conversation_and_parent_substitution_fail(self):
        intent=self.request()
        with self.store.database.connect() as db:
            source=json.loads(db.execute('SELECT source FROM admission_requests WHERE organization=? AND request_id=?',
                                         (self.org,intent.request_id)).fetchone()[0])
        with self.assertRaises(Conflict):planning_intent(self.org,'another',source|{'organization':'foreign'},
            self.context(),[],fixture=True,allow_model=False,config=None)
        with self.assertRaises(NotFound):self.store.request_planning('foreign',self.cid,'request',1,self.context(),fixture=True,allow_model=False)
        with self.assertRaises(NotFound):self.store.admit(replace(intent,organization='foreign'),self.now)
        receipt=self.store.admit(intent,self.now)
        self.assertIsNone(self.store.find_request('foreign','prepare'))
        self.assertIsNone(self.store.get_request('foreign','prepare'))
        self.assertEqual(self.store.pending_requests('foreign'),[])
        with self.assertRaises(NotFound):self.store.get('foreign',intent.id)
        other=self.app.conversations.create(self.org,'another-chat')['id']
        with self.assertRaises(Conflict):self.store.admit(replace(intent,
            ownership=replace(intent.ownership,scope_id=other)),self.now)
        self.assertEqual(self.store.find_request(self.org,'prepare'),receipt)

    def test_source_edit_and_stop_between_request_and_admission_create_no_tasks(self):
        for operation in ('edit','stop'):
            with self.subTest(operation=operation):
                self.open(operation);intent=self.request()
                if operation=='edit':self.app.conversations.message(self.org,self.cid,'edit',1,'Change the budget to £500.')
                else:self.app.execution.stop(self.org,self.cid,'stop',1)
                with self.assertRaises(Conflict):self.store.admit(intent,self.now)
                self.assertEqual(self.counts()['runs'],0)
                self.assertEqual(self.counts()['execution_admissions'],0)

    def test_frozen_inputs_survive_caller_mutation_and_unavailable_current_catalogue(self):
        context=self.context();intent=self.request(context=context);before=intent.fingerprint
        context['knowledge']['procedures'].append('Changed current guidance.')
        intent.tasks[0].inputs['messages'][0]['content']='Changed copy.'
        with patch('acquisition.bootstrap.agent_catalogue',side_effect=OSError('unavailable current catalogue')):
            reopened=build_admissions(self.path,clock=lambda:self.now)
            restored=reopened.get_request(self.org,intent.request_id)
            self.assertEqual(reopened.pending_requests(self.org),[restored])
            original=reopened.preflight
            def checked(frozen,*args):
                original(frozen,*args)
                frozen['messages'][0]['content']='Mutation of a validation copy.'
            with patch.object(reopened,'preflight',side_effect=checked):receipt=reopened.admit(restored,self.now)
            self.assertEqual(reopened.get(self.org,intent.id).fingerprint,before)
        self.assertEqual(receipt.fingerprint,before)

    def test_invalid_context_scope_history_fixture_and_input_budget_fail_before_saving(self):
        for change in ({'previous_results':[{'outcome':'invented'}]},
                       {'messages':[{'content':'invented'}]}, {'extra':'not-a-context-field'},
                       {'knowledge_id':'knowledge_fake'}, {'fixture':'other-fixture'}):
            with self.subTest(change=change),self.assertRaises((ValueError,Conflict)):
                self.request(context=self.context()|change)
        context=self.context(fixture=False)
        small=replace(self.config,max_input_bytes=1024)
        context['model_config']['max_input_bytes']=1024
        with self.assertRaisesRegex(ModelError,'input_budget_exceeded'):
            self.store.request_planning(self.org,self.cid,'small',1,context,fixture=False,allow_model=True,model_config=small)
        self.assertEqual(self.counts()['admission_requests'],0)
        self.assertEqual(self.counts()['model_calls'],0)

    def test_model_mode_cannot_carry_a_fixture_flag_and_assets_must_match_scope(self):
        context=self.context(fixture=False)|{'fixture':'another-fixture'}
        with self.assertRaises(Conflict):self.request(fixture=False,context=context)
        for fixture in (True,False):
            context=self.context(fixture=fixture)
            assets=context['knowledge']['agent_assets'];assets['organization']='foreign'
            for source in assets['sources']:
                source['organization']='foreign'
                source['id']='source_'+digest({k:v for k,v in source.items() if k!='id'})
            assets['id']='assets_'+digest({k:v for k,v in assets.items() if k!='id'})
            context['knowledge_id']='knowledge_'+digest(context['knowledge'])
            with self.subTest(fixture=fixture),self.assertRaises(ValueError):self.request(fixture=fixture,context=context)
        self.assertEqual(self.counts()['admission_requests'],0)

    def test_saved_consent_and_current_source_bytes_are_independently_checked(self):
        for field in ('consent','source'):
            with self.subTest(field=field):
                self.open('changed-'+field);intent=self.request(fixture=False)
                with self.store.database.transaction() as db:
                    if field=='consent':
                        db.execute('DROP TRIGGER admission_requests_no_update')
                        db.execute("UPDATE admission_requests SET consent=json_set(consent,'$.allow_model',json('false'))")
                    else:
                        db.execute("UPDATE conversation_messages SET content='Altered history' WHERE organization=? AND conversation_id=?",(self.org,self.cid))
                with self.assertRaises(Conflict):self.store.admit(intent,self.now)
                self.assertEqual(self.counts()['runs'],0)

    def test_claim_and_reservation_stay_paused_even_with_a_restored_running_lease(self):
        intent=self.request(fixture=False);receipt=self.store.admit(intent,self.now)
        self.assertIsNone(self.app.tasks.claim(self.org,self.now,60,run_id=receipt.run_id))
        self.assertEqual(self.app.worker.drain(self.org),0)
        with self.store.database.transaction() as db:
            task=db.execute('SELECT id FROM tasks WHERE run_id=?',(receipt.run_id,)).fetchone()[0]
            db.execute("UPDATE tasks SET status='running',token='test-lease',lease_until=? WHERE id=?",(self.now+60,task))
            db.execute("UPDATE runs SET status='running' WHERE id=?",(receipt.run_id,))
        scope=CallScope(self.org,receipt.run_id,task,'test-lease')
        with self.assertRaisesRegex(ModelError,'execution_admission_paused'):
            self.app.calls.reserve(scope,'call','hash',2,self.now)
        self.assertEqual(self.counts()['model_calls'],0)
        self.assertEqual(len(self.model.requests),0)

    def test_format_marker_keeps_a_damaged_admission_paused(self):
        intent=self.request();receipt=self.store.admit(intent,self.now)
        with self.store.database.transaction() as db:
            db.execute('DROP TRIGGER execution_admissions_no_delete')
            db.execute('DELETE FROM execution_admissions WHERE organization=? AND id=?',(self.org,intent.id))
        self.assertIsNone(self.app.tasks.claim(self.org,self.now,60,run_id=receipt.run_id))
        with self.assertRaises(Conflict):self.store.admit(intent,self.now)
        self.assertEqual(self.counts()['runs'],1)

    def test_legacy_planning_cannot_duplicate_a_paused_request_and_legacy_first_is_preserved(self):
        self.request()
        with self.assertRaises(Conflict):self.app.conversations.plan_fixture(self.org,self.cid,'legacy',1)
        for policy in ('absolute-gbp/v1','absolute-gbp/v2','absolute-gbp/v3','absolute-gbp/v4'):
            self.open('legacy-first-'+policy.rsplit('/',1)[-1])
            context=self.context('legacy')
            context['budget_policy']=policy
            run=self.app.conversations.plan_fixture(self.org,self.cid,'legacy',1,frozen_context=context)
            frozen=self.app.conversations.store.snapshot(self.org,self.cid)['admissions'][0]
            self.assertEqual(frozen['budget_policy'],'absolute-gbp/v5')
            self.assertEqual(self.store.legacy_planning(self.org,self.cid,'legacy',1,fixture=True,
                                                      config=None,frozen_context=context),run)
            with self.assertRaises(Conflict):
                self.store.legacy_planning(self.org,self.cid,'legacy',1,fixture=True,config=None,
                                           frozen_context=context|{'knowledge_id':'changed'})
            self.assertEqual(self.app.conversations.store.snapshot(self.org,self.cid)['admissions'][0],frozen)
            with self.assertRaises(Conflict):self.request()
            self.assertEqual(self.counts()['admission_requests'],0)
            self.assertEqual(self.app.worker.drain(self.org),1)

    def test_legacy_request_key_collision_does_not_stage_or_consume_a_later_revision(self):
        for with_run in (False,True):
            with self.subTest(with_run=with_run):
                self.open('legacy-key-'+str(with_run))
                context=self.context('used-key')
                frozen=self.app.conversations.store.admit(self.org,self.cid,'used-key',1,context,
                    self.now,self.app.conversations._fixture_preflight)
                if with_run:self.app.conversations.plan_fixture(self.org,self.cid,'used-key',1)
                self.app.conversations.message(self.org,self.cid,'next',1,'Prepare a £600 experiment.')
                context=self.app.conversations.planning_context(self.org,self.cid,'used-key',2,False)
                before=self.counts()
                with self.assertRaises(Conflict):self.store.request_planning(self.org,self.cid,'used-key',2,
                    context,fixture=False,allow_model=True,model_config=self.config)
                self.assertEqual(self.counts(),before)
                self.assertIsNone(self.store.get_request(self.org,'used-key'))
                self.assertEqual(self.store.pending_requests(self.org),[])
                replacement=self.store.request_planning(self.org,self.cid,'replacement',2,context,
                    fixture=False,allow_model=True,model_config=self.config)
                receipt=self.store.admit(replacement,self.now)
                self.assertEqual(self.store.get(self.org,replacement.id),replacement)
                self.assertIsNone(self.app.tasks.claim(self.org,self.now,60,run_id=receipt.run_id))
                self.assertEqual(self.app.conversations.store.snapshot(self.org,self.cid)['admissions'][0],frozen)
                self.assertEqual(len(self.model.requests),0)

    def test_runtime_request_key_collision_is_scoped_and_rejected_before_staging(self):
        for same_organization in (True,False):
            with self.subTest(same_organization=same_organization):
                self.open('runtime-key-'+str(same_organization))
                key='occupied'
                runtime_key='conversation-plan:'+digest({'conversation':self.cid,'request':key})
                self.app.tasks.create(self.org if same_organization else 'another-org',runtime_key,
                    [TaskSpec('test.local',{})],self.now)
                before=self.counts()
                if same_organization:
                    with self.assertRaises(Conflict):self.request(key)
                    self.assertEqual(self.counts(),before)
                    self.assertEqual(self.store.pending_requests(self.org),[])
                    intent=self.request('replacement')
                else:intent=self.request(key)
                self.assertEqual(self.store.admit(intent,self.now).fingerprint,intent.fingerprint)

    def test_atomic_request_key_cannot_be_reused_by_legacy_on_a_later_revision(self):
        for admitted in (False,True):
            with self.subTest(admitted=admitted):
                self.open('atomic-first-'+str(admitted));intent=self.request('used-key')
                if admitted:self.store.admit(intent,self.now)
                self.app.conversations.message(self.org,self.cid,'next',1,'Prepare a £600 experiment.')
                before=self.counts()
                with self.assertRaises(Conflict):self.app.conversations.plan(self.org,self.cid,'used-key',2)
                self.assertEqual(self.counts(),before)
                self.assertEqual(self.store.get_request(self.org,'used-key'),intent)
                run=self.app.conversations.plan(self.org,self.cid,'replacement',2)
                self.assertEqual(self.app.worker.drain(self.org),1)
                self.assertEqual(self.app.tasks.inspect(self.org,run)['run']['status'],'succeeded')

    def test_staging_reserves_runtime_key_against_campaign_and_generic_writers(self):
        intent=self.request(fixture=False)
        key=intent.tasks[0].inputs['run_request_id'];before=self.counts()
        writers=[lambda:self.app.start(self.org,key,size=10,campaign_id='unrelated-campaign'),
                 lambda:self.app.start_model(self.org,key,size=10,campaign_id='unrelated-model-campaign'),
                 lambda:self.app.tasks.create(self.org,key,list(intent.tasks),self.now)]
        for writer in writers:
            with self.subTest(writer=writer),self.assertRaises(Conflict):writer()
            self.assertEqual(self.counts(),before)
        program="""import sys
from acquisition.bootstrap import build
from acquisition.contracts import Conflict
app=build(sys.argv[1],clock=lambda:1792886400.)
try:app.start('local-conversations',sys.argv[2],size=10,campaign_id='after-restart')
except Conflict:sys.exit(0)
sys.exit(1)
"""
        result=subprocess.run([sys.executable,'-c',program,str(self.path),key],
            env=dict(os.environ,PYTHONPATH=str(Path('src').resolve())),capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(self.counts(),before)
        other=self.app.start('another-org',key,size=10,campaign_id='another-org-campaign')
        self.assertIsNotNone(other)
        reopened=build_admissions(self.path,clock=lambda:self.now)
        restored=reopened.get_request(self.org,intent.request_id)
        receipt=reopened.admit(restored,self.now)
        self.assertEqual(reopened.admit(restored,self.now),receipt)
        self.assertEqual(reopened.get(self.org,intent.id),intent)
        self.assertIsNone(self.app.tasks.claim(self.org,self.now,60,run_id=receipt.run_id))
        self.assertEqual(len(self.model.requests),0)

    def test_staging_lock_prevents_a_waiting_campaign_writer_stealing_the_key(self):
        entered,release,writer_entered=Event(),Event(),Event()
        original=self.store.preflight;transaction=self.app.tasks.database.transaction
        def held(*args):
            original(*args);entered.set()
            if not release.wait(10):raise TimeoutError('Staging held for the competing writer')
        @contextmanager
        def observed():
            writer_entered.set()
            with transaction() as db:yield db
        key='conversation-plan:'+digest({'conversation':self.cid,'request':'prepare'})
        with patch.object(self.store,'preflight',side_effect=held),ThreadPoolExecutor(2) as pool:
            staged=pool.submit(self.request)
            try:
                self.assertTrue(entered.wait(5))
                with patch.object(self.app.tasks.database,'transaction',observed):
                    competing=pool.submit(self.app.start,self.org,key,10,campaign_id='competing-campaign')
                    self.assertTrue(writer_entered.wait(5))
                    self.assertFalse(competing.done())
                    release.set();intent=staged.result(10)
                    with self.assertRaises(Conflict):competing.result(10)
            finally:release.set()
        self.assertEqual(self.counts()['runs'],0)
        self.assertEqual(self.store.admit(intent,self.now).fingerprint,intent.fingerprint)

    def test_only_exact_owner_and_task_plan_can_consume_a_runtime_reservation(self):
        intent=self.request();key=intent.tasks[0].inputs['run_request_id'];before=self.counts()
        for owner,specs in [((intent.request_id,'0'*64),list(intent.tasks)),
                            (('another-request',intent.fingerprint),list(intent.tasks)),
                            ((intent.request_id,intent.fingerprint),[TaskSpec('test.other',{})])]:
            with self.subTest(owner=owner,specs=specs),self.assertRaises(Conflict):
                with self.store.database.transaction() as db:
                    insert_run(db,self.org,key,specs,self.now,reservation_owner=owner)
            self.assertEqual(self.counts(),before)
        with self.assertRaises(Conflict):
            with self.store.database.transaction() as db:
                insert_run(db,self.org,'not-reserved',list(intent.tasks),self.now,
                           reservation_owner=(intent.request_id,intent.fingerprint))
        self.assertEqual(self.store.admit(intent,self.now).fingerprint,intent.fingerprint)

    def test_every_admission_insert_and_precommit_failure_roll_back_as_one_unit(self):
        faults=[('runs','1'),('tasks','1'),('events',"NEW.kind='run_created'"),('execution_runs','1'),
                ('conversation_plans','1'),('execution_admissions','1'),('events',"NEW.kind='execution_admitted'")]
        for index,(table,condition) in enumerate(faults):
            with self.subTest(table=table,condition=condition):
                self.open('fault-'+str(index));intent=self.request();before=self.counts()
                with self.store.database.transaction() as db:
                    db.execute(f"CREATE TRIGGER reject_write AFTER INSERT ON {table} WHEN {condition} BEGIN SELECT RAISE(ABORT,'test fault'); END")
                with self.assertRaises(sqlite3.IntegrityError):self.store.admit(intent,self.now)
                self.assertEqual(self.counts(),before)
                with self.store.database.transaction() as db:db.execute('DROP TRIGGER reject_write')
                self.store.admit(intent,self.now)
                self.assertEqual(self.counts()['runs'],1)
        self.open('precommit');intent=self.request();before=self.counts();original=self.store.database.transaction
        @contextmanager
        def fail_commit():
            with original() as db:
                yield db
                raise OSError('Before commit')
        with patch.object(self.store.database,'transaction',fail_commit),self.assertRaises(OSError):self.store.admit(intent,self.now)
        self.assertEqual(self.counts(),before)

    def test_request_insert_failure_leaves_no_consent_or_executable_work(self):
        with self.store.database.transaction() as db:
            db.execute("CREATE TRIGGER reject_request AFTER INSERT ON admission_requests BEGIN SELECT RAISE(ABORT,'test fault'); END")
        with self.assertRaises(sqlite3.IntegrityError):self.request()
        self.assertEqual(self.counts()['admission_requests'],0)
        self.assertEqual(self.counts()['runs'],0)
        with self.store.database.transaction() as db:db.execute('DROP TRIGGER reject_request')
        key='conversation-plan:'+digest({'conversation':self.cid,'request':'prepare'})
        self.assertIsNotNone(self.app.start(self.org,key,size=10,campaign_id='unreserved-after-rollback'))

    def test_competing_request_keys_and_lost_acknowledgements_commit_once(self):
        context=self.context()
        def stage(key):
            store=build_admissions(self.path,clock=lambda:self.now)
            try:return store.request_planning(self.org,self.cid,key,1,context,fixture=True,allow_model=False)
            except Conflict:return None
        with ThreadPoolExecutor(2) as pool:proposals=list(pool.map(stage,('first','second')))
        self.assertEqual(sum(p is not None for p in proposals),1)
        intent=next(p for p in proposals if p)
        def admit(_):return build_admissions(self.path,clock=lambda:self.now).admit(intent,self.now)
        with ThreadPoolExecutor(2) as pool:receipts=list(pool.map(admit,range(2)))
        self.assertEqual(receipts[0],receipts[1]);self.assertEqual(self.counts()['runs'],1)
        self.assertEqual(self.counts()['events'],2)

    def test_lock_wait_includes_source_changes_and_final_clock_validation(self):
        intent=self.request();entered=Event();original=self.store.database.transaction
        @contextmanager
        def observed():
            entered.set()
            with original() as db:yield db
        with ThreadPoolExecutor(1) as pool:
            with self.app.calls.database.transaction() as db:
                with patch.object(self.store.database,'transaction',observed):
                    future=pool.submit(self.store.admit,intent,self.now)
                    self.assertTrue(entered.wait(5))
                    db.execute('UPDATE conversations SET revision=2 WHERE organization=? AND id=?',(self.org,self.cid))
            with self.assertRaises(Conflict):future.result(10)
        self.assertEqual(self.counts()['runs'],0)
        self.open('clock');intent=self.request();original=self.store.preflight
        def slow(*args):original(*args);self.now=float('inf')
        with patch.object(self.store,'preflight',slow),self.assertRaises(ValueError):self.store.admit(intent,1792886400.)
        self.assertEqual(self.counts()['runs'],0)

    def test_planning_limit_counts_legacy_and_staged_revisions_together(self):
        for revision in range(1,6):
            self.app.conversations.plan(self.org,self.cid,'legacy-'+str(revision),revision)
            self.app.conversations.message(self.org,self.cid,'next-'+str(revision),revision,'Prepare a £600 experiment.')
        context=self.app.conversations.planning_context(self.org,self.cid,'sixth',6,False)
        self.store.request_planning(self.org,self.cid,'sixth',6,context,fixture=False,allow_model=True,model_config=self.config)
        self.app.conversations.message(self.org,self.cid,'next-sixth',6,'Prepare a £500 experiment.')
        context=self.app.conversations.planning_context(self.org,self.cid,'seventh',7,False)
        with self.assertRaisesRegex(ValueError,'budget exhausted'):
            self.store.request_planning(self.org,self.cid,'seventh',7,context,fixture=False,allow_model=True,model_config=self.config)
        with self.assertRaisesRegex(ValueError,'budget exhausted'):
            self.app.conversations.plan(self.org,self.cid,'legacy-seventh',7)
        self.assertEqual(self.counts()['admission_requests'],1)

    def test_real_process_crash_before_commit_and_after_commit_recovers_original_identity(self):
        intent=self.request()
        program="""import json,os,sqlite3,sys
from acquisition.bootstrap import build_admissions
original=sqlite3.connect
class CrashConnection(sqlite3.Connection):
 def execute(self,sql,*args,**kwargs):
  result=super().execute(sql,*args,**kwargs)
  if sys.argv[3]=='before' and sql.startswith('INSERT INTO execution_admissions'):os._exit(73)
  return result
sqlite3.connect=lambda *args,**kwargs:original(*args,factory=CrashConnection,**kwargs)
store=build_admissions(sys.argv[1],clock=lambda:1792886400.)
intent=store.get_request('local-conversations',sys.argv[2])
store.admit(intent,1792886400.)
os._exit(74)
"""
        environment=dict(os.environ,PYTHONPATH=str(Path('src').resolve()))
        for stage,expected in (('before',73),('after',74)):
            result=subprocess.run([sys.executable,'-c',program,str(self.path),intent.request_id,stage],
                env=environment,capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,expected,result.stderr)
            reopened=build_admissions(self.path,clock=lambda:self.now)
            receipt=reopened.find_request(self.org,intent.request_id)
            if stage=='before':
                self.assertIsNone(receipt);self.assertEqual(self.counts()['runs'],0)
                self.assertEqual(reopened.pending_requests(self.org),[intent])
            else:
                self.assertEqual(reopened.get(self.org,intent.id),intent)
                self.assertEqual(reopened.admit(intent,self.now),receipt)
                self.assertEqual(self.counts()['runs'],1)
                self.assertIsNone(self.app.tasks.claim(self.org,self.now,60,run_id=receipt.run_id))

    def test_new_journals_are_immutable_and_receipt_observation_detects_task_substitution(self):
        intent=self.request();receipt=self.store.admit(intent,self.now)
        for table in ('admission_requests','execution_admissions'):
            for sql in ('UPDATE '+table+' SET payload=payload','DELETE FROM '+table):
                with self.subTest(sql=sql),self.assertRaises(sqlite3.IntegrityError):
                    with self.store.database.transaction() as db:db.execute(sql)
        with self.store.database.transaction() as db:
            db.execute("UPDATE tasks SET inputs='{}' WHERE run_id=?",(receipt.run_id,))
        with self.assertRaises(Conflict):self.store.get(self.org,intent.id)
        with self.assertRaises(Conflict):self.store.admit(intent,self.now)

    def test_schema_eleven_failure_rolls_back_without_changing_legacy_cutoff(self):
        with self.store.database.transaction() as db:
            old=[tuple(r) for r in db.execute('SELECT * FROM legacy_task_admissions')]
            db.execute('DROP TABLE execution_admissions');db.execute('DROP TABLE admission_requests')
            db.execute('PRAGMA user_version=10')
        original=Database._apply_migration
        def interrupted(db,script):
            original(db,script)
            if script==ATOMIC_ADMISSIONS:raise OSError('Migration interrupted')
        with patch.object(Database,'_apply_migration',side_effect=interrupted),self.assertRaises(OSError):Database(self.path)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],10)
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='execution_admissions'").fetchone())
            self.assertEqual([tuple(r) for r in db.execute('SELECT * FROM legacy_task_admissions')],old)
        reopened=Database(self.path)
        with reopened.connect() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],15)
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')


if __name__=='__main__':unittest.main()
