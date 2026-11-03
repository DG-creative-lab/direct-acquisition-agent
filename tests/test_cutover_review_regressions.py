"""Campaign identity, native request scopes and observational legacy replay."""
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
from acquisition.contracts import Conflict
from acquisition.conversations import FIXTURE_MESSAGE
from acquisition.reasoning import ModelConfig
from acquisition.workspace import Workspace
import test_admission_workflow_coverage as coverage
import test_copy_revisions as revisions


def records(app):
    with app.tasks.database.connect() as db:
        return {t:[tuple(r) for r in db.execute('SELECT * FROM '+t)] for t in (
            'admission_requests','execution_admissions','runs','tasks','events','execution_runs',
            'model_calls','review_decisions','learning_beliefs','audiences','creative_contexts','editorial_memories')}


class CampaignIdentityTests(unittest.TestCase):
    setUp=coverage.WorkflowAdmissionTests.setUp
    plan=coverage.WorkflowAdmissionTests.plan
    conversation_refs=coverage.WorkflowAdmissionTests.conversation_refs

    def parent(self):
        scope,_=self.conversation_refs()
        plan=self.app.conversations.view(self.org,self.cid)['current_plan']['result']
        app=build(self.path,clock=lambda:self.now,verified_admissions=True)
        parent=app.start_conversation(scope,scope,plan,'2026-10-26')
        return app,scope,parent

    def test_legacy_conversation_campaign_modes_replay_their_original_task_plans(self):
        # Separate stores keep the fixture and model histories independent.
        for model in (False,True):
            with self.subTest(model=model),tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'history.sqlite'
                app=build(path,clock=lambda:self.now,model_config=self.config,gateway=revisions.RevisionModel())
                cid=app.conversations.create('local-conversations','chat')['id']
                app.conversations.message('local-conversations',cid,'message',0,FIXTURE_MESSAGE)
                planner=app.conversations.plan if model else app.conversations.plan_fixture
                run=planner('local-conversations',cid,'plan',1);app.worker.drain('local-conversations',run_id=run)
                plan=app.conversations.view('local-conversations',cid)['current_plan']['result']
                self.assertEqual(plan['copy_mode'],'model' if model else 'fixture')
                # The fixture planner chooses fixture copy. Use the saved model
                # planner's result unchanged, including its selected copy mode.
                scope='legacy-campaign'
                run=app.start_conversation(scope,scope,plan,'2026-10-26');app.worker.drain(scope,run_id=run)
                app.admissions.store.seal_legacy_writes();before=records(app)
                reopened=build(path,clock=lambda:self.now,model_config=self.config)
                with patch.object(reopened,'_model_inputs',side_effect=AssertionError('Rebuilt legacy copy inputs')):
                    self.assertEqual(reopened.start_conversation(scope,scope,plan,'2026-10-26'),run)
                with self.assertRaises(Conflict):reopened.start_conversation(scope,scope,plan|{'budget_pence':plan['budget_pence']+1},'2026-10-26')
                self.assertEqual(records(reopened),before)

    def test_staged_child_reserves_campaign_across_kinds_and_runtime_keys(self):
        app,scope,parent=self.parent()
        with self.assertRaisesRegex(Conflict,'campaign identity'):
            app.start(scope,'reuse-parent',size=100,campaign_id=scope,parent_run_id=parent)
        with patch.object(app.admissions.store,'admit',side_effect=OSError('Interrupted after staging')):
            with self.assertRaises(OSError):app.start(scope,'child-key',size=100,campaign_id='shared',parent_run_id=parent)
        staged=app.admissions.store.get_request(scope,'child-key');before=records(app)
        with self.assertRaises(Conflict):app.start(scope,'standalone-key',size=100,campaign_id='shared')
        self.assertEqual(records(app),before)
        child=app.start(scope,'child-key',size=100,campaign_id='shared',parent_run_id=parent)
        self.assertEqual(app.admissions.store.get_request(scope,'child-key'),staged)
        app.execution.stop(self.org,self.cid,'stop',1)
        self.assertEqual(app.tasks.inspect(scope,child)['run']['status'],'cancelled')
        self.assertIsNone(app.tasks.find_run(scope,'standalone-key'))

    def test_staged_standalone_reserves_campaign_against_a_later_child(self):
        app,scope,parent=self.parent()
        with patch.object(app.admissions.store,'admit',side_effect=OSError('Interrupted after staging')):
            with self.assertRaises(OSError):app.start(scope,'standalone-key',size=100,campaign_id='shared')
        before=records(app)
        with self.assertRaises(Conflict):app.start(scope,'child-key',size=100,campaign_id='shared',parent_run_id=parent)
        self.assertEqual(records(app),before)

    def test_concurrent_cross_kind_commands_have_one_campaign_owner(self):
        app,scope,parent=self.parent()
        def start(parent_id):
            try:return app.start(scope,'child' if parent_id else 'root',size=100,campaign_id='racing',parent_run_id=parent_id)
            except Conflict:return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            runs=list(pool.map(start,(None,parent)))
        self.assertEqual(sum(run is not None for run in runs),1)
        with app.tasks.database.connect() as db:
            rows=db.execute("SELECT payload FROM admission_requests WHERE organization=? AND json_extract(payload,'$.source_id')='racing'",(scope,)).fetchall()
        self.assertEqual(len(rows),1)
        self.assertEqual(app.worker.drain(scope),0)

    def test_pre_fix_cross_kind_staging_is_rechecked_at_admission(self):
        app,scope,parent=self.parent();store=app.admissions.store
        composer=store.workflow_intent
        def old_composer(*args):
            intent,_=composer(*args)
            return intent,args[2]+':'+intent.source_id
        # Reproduce the old writer's two incompatible, immutable staging rows.
        with patch.object(store,'workflow_intent',side_effect=old_composer), \
                patch.object(store,'_campaign_available'),patch.object(store,'admit',side_effect=OSError):
            for key,parent_id in (('child',parent),('root',None)):
                with self.assertRaises(OSError):app.start(scope,key,size=100,campaign_id='duplicate',parent_run_id=parent_id)
        before=records(app)
        for key in ('child','root'):
            with self.assertRaisesRegex(Conflict,'Campaign identity'):
                store.admit(store.get_request(scope,key),self.now)
        self.assertEqual(records(app),before)

    def test_pre_fix_operation_key_resumes_unchanged_and_is_organization_scoped(self):
        app,scope,parent=self.parent();store=app.admissions.store;composer=store.workflow_intent
        def old_composer(*args):
            intent,_=composer(*args)
            return intent,args[2]+':'+intent.source_id
        with patch.object(store,'workflow_intent',side_effect=old_composer),patch.object(store,'admit',side_effect=OSError):
            with self.assertRaises(OSError):app.start(scope,'child',size=100,campaign_id='same',parent_run_id=parent)
        staged=store.get_request(scope,'child')
        before=records(app)
        with self.assertRaisesRegex(Conflict,'Campaign identity'):
            app.start(scope,'conflicting-root',size=100,campaign_id='same')
        self.assertEqual(records(app),before)
        other=app.start('another-org','other',size=100,campaign_id='same')
        child=app.start(scope,'child',size=100,campaign_id='same',parent_run_id=parent)
        self.assertNotEqual(child,other)
        self.assertEqual(store.get_request(scope,'child'),staged)
        self.assertTrue(app.tasks.inspect(scope,child)['admission']['binding_valid'])



class RoutingIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.now=1792972800.
        self.w=Workspace(self.root,real_clock=lambda:self.now,verified_admissions=True)

    def test_native_routing_key_can_match_a_plan_and_another_conversation(self):
        first=self.w.create_conversation('first','First')['id']
        self.w.message_conversation(first,'message',0,FIXTURE_MESSAGE)
        app=self.w._conversation_app(with_model=True)
        plan=app.conversations.plan_fixture('local-conversations',first,'shared',1)
        routes=[]
        for cid in (first,self.w.create_conversation('second','Second')['id']):
            if cid!=first:self.w.message_conversation(cid,'message',0,FIXTURE_MESSAGE)
            row=app.actions.admit('local-conversations',cid,'shared',1,'What should I consider next?',False,self.w.action_context(cid,1))
            run=app.actions.reconcile('local-conversations',row)
            state=app.tasks.inspect('local-conversations',run)
            self.assertEqual(state['tasks'][0]['inputs']['request_id'],'shared')
            self.assertEqual(state['tasks'][0]['inputs']['inputs']['conversation_id'],cid)
            self.assertEqual(app.worker.drain('local-conversations',run_id=run),0)
            reopened=Workspace(self.root,real_clock=lambda:self.now)._conversation_app(with_model=True)
            before=records(reopened)
            self.assertEqual(reopened.actions.reconcile('local-conversations',row),run)
            self.assertEqual(records(reopened),before)
            routes.append(run)
        self.assertEqual(len({plan,*routes}),3)

    def test_existing_raw_routing_wrapper_replays_without_rekeying(self):
        cid=self.w.create_conversation('chat','Chat')['id']
        self.w.message_conversation(cid,'message',0,FIXTURE_MESSAGE)
        app=self.w._conversation_app(with_model=True);org='local-conversations'
        row=app.actions.admit(org,cid,'native',1,'What should I consider next?',False,self.w.action_context(cid,1))
        intent=app.admissions.store.request_workflow(org,'native','routing',{'action_id':row['id']},
            entrypoint={'action_id':row['id']},allow_model=True,model_config=app.actions.config)
        run=app.admissions.store.admit(intent,self.now).run_id
        before=records(app)
        self.assertEqual(app.actions.reconcile(org,row),run)
        self.assertEqual(records(app),before)



class LegacyReplayTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'legacy.sqlite';self.now=1792972800.
        self.config=ModelConfig('test/model',max_calls=10,force_tool_choice=True)

    def test_fixture_command_replay_returns_legacy_run_without_new_authority(self):
        app=build(self.path,clock=lambda:self.now)
        args={'size':20,'seed':7,'budget_pence':12345,'as_of':'2026-10-26','campaign_id':'historical'}
        run=app.start('one','request',**args);app.worker.drain('one',run_id=run)
        app.admissions.store.seal_legacy_writes();before=records(app)
        reopened=build(self.path,clock=lambda:self.now)
        self.assertEqual(reopened.start('one','request',**args),run)
        for change in ({'size':21},{'seed':8},{'budget_pence':12346},{'as_of':'2026-10-27'},{'campaign_id':'other'}):
            with self.subTest(change=change),self.assertRaises(Conflict):reopened.start('one','request',**(args|change))
        self.assertEqual(reopened.worker.drain('one',run_id=run),0)
        self.assertEqual(records(reopened),before)
        self.assertFalse(reopened.tasks.inspect('one',run)['admission']['binding_valid'])

    def test_model_command_replays_original_context_without_keys_or_catalogue(self):
        model=revisions.RevisionModel()
        app=build(self.path,clock=lambda:self.now,gateway=model,model_config=self.config)
        run=app.start_model('one','request',size=100,as_of='2026-10-26')
        app.worker.drain('one',run_id=run);app.admissions.store.seal_legacy_writes()
        reopened=build(self.path,clock=lambda:self.now,model_config=self.config)
        before=records(reopened)
        with patch.object(reopened,'_model_inputs',side_effect=AssertionError('Legacy replay rebuilt context')):
            self.assertEqual(reopened.start_model('one','request',size=100,as_of='2026-10-26'),run)
        wrong=build(self.path,clock=lambda:self.now,model_config=replace(self.config,max_calls=9))
        with self.assertRaises(Conflict):wrong.start_model('one','request',size=100,as_of='2026-10-26')
        self.assertEqual(records(reopened),before)

    def test_completed_legacy_plan_remains_observable_after_a_later_message(self):
        app=build(self.path,clock=lambda:self.now)
        cid=app.conversations.create('one','chat')['id']
        app.conversations.message('one',cid,'message',0,FIXTURE_MESSAGE)
        run=app.conversations.plan_fixture('one',cid,'plan',1);app.worker.drain('one',run_id=run)
        app.conversations.message('one',cid,'later',1,'Use a £400 budget instead.')
        app.admissions.store.seal_legacy_writes();before=records(app)
        reopened=build(self.path,clock=lambda:self.now)
        with patch.object(reopened.conversations,'planning_context',side_effect=AssertionError('Rebuilt historical context')):
            self.assertEqual(reopened.conversations.plan_fixture('one',cid,'plan',1),run)
        with self.assertRaises(Conflict):reopened.conversations.plan_fixture('one',cid,'plan',2)
        self.assertEqual(records(reopened),before)

    def test_legacy_model_plan_replay_checks_mode_settings_and_frozen_context(self):
        app=build(self.path,clock=lambda:self.now,model_config=self.config,gateway=revisions.RevisionModel())
        cid=app.conversations.create('one','chat')['id']
        app.conversations.message('one',cid,'message',0,FIXTURE_MESSAGE)
        run=app.conversations.plan('one',cid,'plan',1);app.worker.drain('one',run_id=run)
        frozen=app.tasks.inspect('one',run)['tasks'][0]['inputs']
        context={k:v for k,v in frozen.items() if k not in {'conversation_id','request_id','revision','messages','run_request_id'}}
        app.admissions.store.seal_legacy_writes();before=records(app)
        reopened=build(self.path,clock=lambda:self.now,model_config=self.config)
        self.assertEqual(reopened.conversations.plan('one',cid,'plan',1,frozen_context=context),run)
        self.assertEqual(reopened.conversations.plan('one',cid,'plan',1,frozen_context=context|{'messages':frozen['messages']}),run)
        with self.assertRaises(Conflict):reopened.conversations.plan('one',cid,'plan',1,frozen_context=context|{'messages':[]})
        with self.assertRaises(Conflict):reopened.conversations.plan_fixture('one',cid,'plan',1)
        with self.assertRaises(Conflict):reopened.conversations.plan('one',cid,'plan',1,frozen_context=context|{'previous_results':[{}]})
        wrong=build(self.path,clock=lambda:self.now,model_config=replace(self.config,model='other/model'))
        with self.assertRaises(Conflict):wrong.conversations.plan('one',cid,'plan',1)
        self.assertEqual(records(reopened),before)

    def test_cli_replays_exact_legacy_fixture_in_a_fresh_process(self):
        app=build(self.path,clock=lambda:self.now)
        run=app.start('one','legacy',size=20)
        app.admissions.store.seal_legacy_writes();before=records(app)
        env=dict(os.environ,PYTHONPATH=str(Path('src').resolve()))
        def replay(size):
            return subprocess.run([sys.executable,'-m','acquisition','--db',str(self.path),'--organization','one',
                'create','--request-id','legacy','--size',str(size)],env=env,capture_output=True,text=True,timeout=20)
        result=replay(20)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['run_id'],run)
        self.assertNotEqual(replay(21).returncode,0)
        self.assertEqual(records(app),before)
