"""Store-format cutover through public callers, raw writers and fresh workers."""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import asdict, replace
from pathlib import Path
from threading import Event
from unittest.mock import patch

from acquisition.bootstrap import build, build_admissions
from acquisition.contracts import Conflict, digest
from acquisition.conversations import FIXTURE_MESSAGE
from acquisition.reasoning import CallScope, ModelConfig, ModelError
from acquisition.runtime import Claim, LeaseLost, Outcome, TaskSpec
from acquisition.workspace import Workspace
import test_admission_workflow_coverage as coverage
import test_copy_revisions as revisions
import test_followups as followups
import test_workspace as workspace_tests
from acquisition.workspace_server import WorkspaceServer


class AdmissionEntrypointTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.path=self.root/'app.sqlite';self.now=1792972800.
        self.config=ModelConfig('test/model',max_calls=10,force_tool_choice=True)
        self.model=revisions.RevisionModel()
        self.app=build(self.path,clock=lambda:self.now,model_config=self.config,gateway=self.model,verified_admissions=True)
        self.org='one'

    def counts(self):
        with self.app.tasks.database.connect() as db:
            return {t:db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in
                ('runs','tasks','events','execution_admissions','model_calls','review_decisions','learning_beliefs')}

    def assert_paused(self, org, run):
        state=self.app.tasks.inspect(org,run)
        self.assertEqual(state['admission']['status'],'paused')
        self.assertTrue(state['admission']['binding_valid'])
        before=self.counts()
        self.assertEqual(self.app.worker.drain(org,run_id=run),0)
        scope=CallScope(org,run,state['tasks'][0]['id'],'restored-worker-token')
        with self.assertRaisesRegex(ModelError,'execution_admission_paused'):
            self.app.calls.reserve(scope,'call','0'*64,10,self.now)
        self.assertEqual(self.counts(),before)
        self.assertFalse(self.model.planner.requests)
        self.assertFalse(self.model.copy.requests)

    def test_fixture_and_model_entrypoints_commit_paused_verified_work(self):
        for model in (False,True):
            key='root-'+str(model)
            start=self.app.start_model if model else self.app.start
            run=start(self.org,key,size=100,as_of='2026-10-26')
            intent=self.app.admissions.store.get_request(self.org,key)
            self.assertEqual(intent.ownership.kind,'standalone')
            self.assertIsNone(intent.parent_run_id)
            self.assertEqual(self.app.tasks.find_run(self.org,key),run)
            self.assert_paused(self.org,run)

    def test_original_model_command_replays_before_regenerating_context(self):
        run=self.app.start_model(self.org,'model',size=100,as_of='2026-10-26')
        intent=self.app.admissions.store.get_request(self.org,'model')
        reopened=build(self.path,clock=lambda:self.now,model_config=self.config)
        with patch.object(reopened,'_model_inputs',side_effect=AssertionError('Rebuilt context on replay')):
            self.assertEqual(reopened.start_model(self.org,'model',size=100,as_of='2026-10-26'),run)
            with self.assertRaises(Conflict):reopened.start_model(self.org,'model',size=101,as_of='2026-10-26')
        changed=build(self.path,clock=lambda:self.now,model_config=replace(self.config,model='different/model'))
        with self.assertRaises(Conflict):changed.start_model(self.org,'model',size=100,as_of='2026-10-26')
        self.assertEqual(reopened.admissions.store.get_request(self.org,'model'),intent)
        self.assert_paused(self.org,run)

    def test_parent_is_explicit_and_inherited_before_first_claim(self):
        parent=self.app.start(self.org,'parent',size=100)
        child=self.app.start_model(self.org,'child',size=100,as_of='2026-10-26',parent_run_id=parent)
        source=self.app.admissions.store.get_request(self.org,'parent')
        inherited=self.app.admissions.store.get_request(self.org,'child')
        self.assertEqual(inherited.parent_run_id,parent)
        self.assertEqual(inherited.ownership,source.ownership)
        self.assert_paused(self.org,child)
        with self.assertRaises(Conflict):self.app.start(self.org,'another',campaign_id='parent')

    def test_raw_writers_and_unregistered_capabilities_cannot_bypass_cutover(self):
        before=self.counts()
        raw=build(self.path,clock=lambda:self.now)
        for org in ('one','another'):
            with self.subTest(org=org),self.assertRaisesRegex(Conflict,'requires verified admission'):
                raw.tasks.create(org,'raw',[TaskSpec('new.provider-tool',{})],self.now)
        self.assertEqual(self.counts(),before)

    def test_verified_creation_does_not_require_a_workspace_ancestry_witness(self):
        with patch('acquisition.bootstrap.bind_workspace_journal',side_effect=AssertionError('Workspace supplied execution authority')):
            app=build(self.path,clock=lambda:self.now,workspace_organization=self.org)
            run=app.start(self.org,'without-workspace',size=20)
        self.assertTrue(app.tasks.inspect(self.org,run)['admission']['binding_valid'])

    def test_existing_builder_observes_cutover_and_raw_store_replay_stays_historical(self):
        path=self.root/'legacy.sqlite'
        old=build(path,clock=lambda:self.now)
        existing=old.start('legacy','old',size=20)
        before=old.tasks.inspect('legacy',existing)
        old.admissions.store.seal_legacy_writes()
        self.assertEqual(old.tasks.create('legacy','old',[TaskSpec(t['capability'],t['inputs'],t['max_attempts']) for t in before['tasks']],self.now),existing)
        self.assertEqual(old.worker.drain('legacy'),0)
        self.assertEqual(old.tasks.inspect('legacy',existing)['events'],before['events'])
        new=old.start('legacy','new',size=20)
        self.assertTrue(old.tasks.inspect('legacy',new)['admission']['binding_valid'])
        with self.assertRaises(Conflict):old.tasks.create('legacy','bypass',[TaskSpec('other',{})],self.now)

    def test_cutover_waits_for_running_work_and_does_not_activate_an_expired_lease(self):
        path=self.root/'busy.sqlite';old=build(path,clock=lambda:self.now)
        run=old.start(self.org,'busy',size=20)
        old.tasks.claim(self.org,self.now,60,run_id=run)
        with self.assertRaisesRegex(Conflict,'Quiesce'):old.admissions.store.seal_legacy_writes()
        self.assertFalse(old.admissions.required())
        old.tasks.cancel(self.org,run,self.now)
        old.admissions.store.seal_legacy_writes()
        self.assertTrue(old.admissions.required())

    def test_policy_cannot_be_downgraded_or_lost_silently(self):
        with self.app.tasks.database.transaction() as db:
            with self.assertRaises(sqlite3.IntegrityError):db.execute('DELETE FROM admission_store_policy')
            with self.assertRaises(sqlite3.IntegrityError):db.execute("UPDATE admission_store_policy SET policy='legacy'")
            db.execute('DROP TABLE admission_store_policy')
        with self.assertRaisesRegex(Conflict,'policy metadata'):self.app.start(self.org,'blocked',size=20)

    def test_claim_and_reservation_recheck_the_exact_committed_plan(self):
        run=self.app.start(self.org,'root',size=20)
        state=self.app.tasks.inspect(self.org,run);before=self.counts()
        with self.app.tasks.database.transaction() as db:
            db.execute("UPDATE tasks SET inputs=json_set(inputs,'$.brief.budget_pence',1) WHERE run_id=? AND position=0",(run,))
        with self.assertRaises(Conflict):self.app.tasks.claim(self.org,self.now,60,run_id=run)
        with self.assertRaises(Conflict):self.app.calls.reserve(CallScope(self.org,run,state['tasks'][0]['id'],'old-lease'),'call','hash',10,self.now)
        self.assertEqual(self.counts(),before)
        self.assertFalse(self.app.tasks.inspect(self.org,run)['admission']['binding_valid'])

    def test_fresh_cli_creation_and_worker_use_the_persisted_store_format(self):
        path=self.root/'cli.sqlite';env=dict(os.environ,PYTHONPATH=str(Path('src').resolve()))
        def cli(*args):
            return subprocess.run([sys.executable,'-m','acquisition','--db',str(path),'--organization','cli',*args],
                env=env,capture_output=True,text=True,timeout=20)
        selected=cli('admission-cutover');self.assertEqual(selected.returncode,0,selected.stderr)
        created=cli('create','--request-id','command','--size','20')
        self.assertEqual(created.returncode,0,created.stderr)
        run=json.loads(created.stdout)['run_id']
        worked=cli('work');self.assertEqual(worked.returncode,0,worked.stderr)
        self.assertEqual(json.loads(worked.stdout)['worker_ticks'],0)
        state=json.loads(cli('status','--run',run).stdout)
        self.assertEqual(state['admission']['status'],'paused')
        self.assertEqual([t['attempts'] for t in state['tasks']],[0,0,0])

    def test_model_admission_without_credentials_does_not_load_a_provider(self):
        path=self.root/'no-key.sqlite';env=dict(os.environ,PYTHONPATH=str(Path('src').resolve()))
        result=subprocess.run([sys.executable,'-m','acquisition','--db',str(path),'--verified-admissions',
            '--env-file',str(self.root/'missing.env'),'create-model','--request-id','model','--size','20'],
            env=env,capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        app=build(path,clock=lambda:self.now)
        self.assertTrue(app.tasks.inspect('demo-org',json.loads(result.stdout)['run_id'])['admission']['binding_valid'])

    def test_restored_running_task_cannot_settle_or_reserve_while_paused(self):
        run=self.app.start(self.org,'root',size=20)
        state=self.app.tasks.inspect(self.org,run);task=state['tasks'][0]
        with self.app.tasks.database.transaction() as db:
            db.execute('DROP TRIGGER verified_task_effect')  # Model an interrupted/broken restore; Python must also fence.
            db.execute("UPDATE runs SET status='running' WHERE id=?",(run,))
            db.execute("UPDATE tasks SET status='running',token='restored',lease_until=? WHERE id=?",(self.now+60,task['id']))
        claim=Claim(self.org,run,task['id'],task['capability'],task['inputs'],'restored',1,None)
        before=self.counts()
        with self.assertRaises(LeaseLost):self.app.tasks.settle(claim,Outcome('succeeded',{'forged':'result'}),self.now)
        with self.assertRaisesRegex(ModelError,'execution_admission_paused'):
            self.app.calls.reserve(CallScope(self.org,run,task['id'],'restored'),'call','hash',10,self.now)
        self.assertEqual(self.counts(),before)

    def test_cached_pre_cutover_sql_writer_cannot_create_claim_or_reserve(self):
        run=self.app.start(self.org,'root',size=20)
        task=self.app.tasks.inspect(self.org,run)['tasks'][0]
        # This connection uses the old table protocol directly, without any new
        # Python gate or connection-specific validation function.
        with sqlite3.connect(self.path) as old:
            with self.assertRaisesRegex(sqlite3.IntegrityError,'precede runtime'):
                old.execute("INSERT INTO runs VALUES('old-writer','one','bypass','hash','queued',0)")
            with self.assertRaisesRegex(sqlite3.IntegrityError,'remains paused'):
                old.execute("UPDATE tasks SET status='running' WHERE id=?",(task['id'],))
            with self.assertRaisesRegex(sqlite3.IntegrityError,'inference remains paused'):
                old.execute("INSERT INTO model_calls VALUES(?,?,?,?,?,?,'reserved',NULL,NULL)",
                    (self.org,run,'raw-call',task['id'],'old-token','hash'))
        self.assertEqual(self.app.calls.inspect(self.org,run),[])
        self.assertEqual(self.app.tasks.inspect(self.org,run)['tasks'][0]['attempts'],0)

    def test_reserved_provider_work_prevents_cutover_until_its_original_observation_arrives(self):
        path=self.root/'reserved.sqlite'
        app=build(path,clock=lambda:self.now,model_config=self.config,gateway=self.model)
        run=app.start_model(self.org,'original',size=20,as_of='2026-10-26')
        claim=app.tasks.claim(self.org,self.now,60,run_id=run)
        scope=CallScope(self.org,run,claim.task_id,claim.token)
        app.calls.reserve(scope,'original-call','hash',10,self.now)
        app.tasks.cancel(self.org,run,self.now)
        with self.assertRaisesRegex(Conflict,'Quiesce'):app.admissions.store.seal_legacy_writes()
        app.calls.record(scope,'original-call',None,'provider_outcome_unknown')
        app.admissions.store.seal_legacy_writes()
        self.assertEqual(app.calls.inspect(self.org,run)[0]['status'],'unknown')
        self.assertEqual(app.worker.drain(self.org),0)

    def test_cutover_cannot_strand_a_partially_admitted_legacy_plan(self):
        path=self.root/'partial.sqlite';app=build(path,clock=lambda:self.now)
        cid=app.conversations.create(self.org,'chat')['id']
        app.conversations.message(self.org,cid,'message',0,FIXTURE_MESSAGE)
        context=app.conversations.planning_context(self.org,cid,'plan',1,True)
        app.conversations.store.admit(self.org,cid,'plan',1,context,self.now,lambda _:None)
        with self.assertRaisesRegex(Conflict,'original legacy planning'):app.admissions.store.seal_legacy_writes()
        self.assertFalse(app.admissions.required())
        run=app.conversations.plan_fixture(self.org,cid,'plan',1)
        app.admissions.store.seal_legacy_writes()
        self.assertEqual(app.worker.drain(self.org,run_id=run),0)

    def test_cutover_serializes_a_waiting_raw_writer_and_rolls_back_on_failure(self):
        path=self.root/'serialized.sqlite';old=build(path,clock=lambda:self.now)
        entered,release,writing=Event(),Event(),Event()
        def clock():
            entered.set()
            if not release.wait(5):raise TimeoutError('Missing seal release')
            return self.now
        store=build_admissions(path,clock)
        def writer():
            writing.set()
            return old.tasks.create(self.org,'raw',[TaskSpec('unregistered',{})],self.now)
        with ThreadPoolExecutor(max_workers=2) as pool:
            selected=pool.submit(store.seal_legacy_writes)
            self.assertTrue(entered.wait(5))
            competing=pool.submit(writer)
            self.assertTrue(writing.wait(5));release.set()
            selected.result(timeout=5)
            with self.assertRaises(Conflict):competing.result(timeout=5)
        with old.tasks.database.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM runs').fetchone()[0],0)
        other=build_admissions(self.root/'rollback.sqlite',clock=lambda:self.now)
        transaction=other.database.transaction
        @contextmanager
        def failed_commit():
            with transaction() as db:
                yield db
                raise OSError('Cutover commit interrupted')
        with patch.object(other.database,'transaction',failed_commit),self.assertRaises(OSError):other.seal_legacy_writes()
        self.assertFalse(other.required())
        other.seal_legacy_writes();self.assertTrue(other.required())

    def test_runtime_key_is_reserved_against_a_competing_writer_before_task_creation(self):
        original=self.app.admissions.store.admit
        def interrupted(intent,now):raise OSError('Interrupted after staging')
        with patch.object(self.app.admissions.store,'admit',side_effect=interrupted),self.assertRaises(OSError):
            self.app.start(self.org,'original',size=20)
        with self.assertRaises(Conflict):self.app.tasks.create(self.org,'original',[TaskSpec('other',{})],self.now)
        with patch.object(self.app.admissions.store,'admit',side_effect=original):
            run=self.app.start(self.org,'original',size=20)
        self.assert_paused(self.org,run)

    def test_deferred_admission_rolls_back_with_runtime_before_commit(self):
        before=self.counts()
        with patch('acquisition.adapters.sqlite.admissions.event',side_effect=OSError('Commit interrupted')):
            with self.assertRaises(OSError):self.app.start(self.org,'retry',size=20)
        self.assertEqual(self.counts(),before)
        self.assertIsNotNone(self.app.admissions.store.get_request(self.org,'retry'))
        self.assertIsNone(self.app.admissions.store.find_request(self.org,'retry'))
        run=self.app.start(self.org,'retry',size=20)
        self.assert_paused(self.org,run)


class ConversationEntrypointTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.now=1792972800.
        self.w=Workspace(self.root,real_clock=lambda:self.now,verified_admissions=True)
        self.cid=self.w.create_conversation('chat','Verified chat')['id']
        self.w.message_conversation(self.cid,'message',0,FIXTURE_MESSAGE)

    def test_chat_coordinator_saves_paused_plan_and_recovers_original_request(self):
        self.w.start_preparation(self.cid,'prepare',1,True,False)
        view=self.w.conversation(self.cid);plan=view['current_plan'];progress=view['preparations'][0]
        self.assertEqual(plan['status'],'queued')
        self.assertEqual(progress['status'],'blocked')
        self.assertIn('Execution remains paused',progress['detail'])
        reopened=Workspace(self.root,real_clock=lambda:self.now)
        reopened.advance_preparations()
        self.assertEqual(reopened.conversation(self.cid)['current_plan']['run_id'],plan['run_id'])
        app=reopened._conversation_app()
        self.assertTrue(app.admissions.required())
        self.assertEqual(app.calls.inspect('local-conversations',plan['run_id']),[])

    def test_model_planning_needs_no_key_and_cannot_downgrade_consent(self):
        with patch('acquisition.workspace.openrouter_key',side_effect=AssertionError('Loaded a key')):
            self.w.start_preparation(self.cid,'prepare',1,False,False)
        app=self.w._conversation_app(with_model=True)
        view=self.w.conversation(self.cid);request=view['preparations'][0]['plan_request_id']
        intent=app.admissions.store.get('local-conversations',app.tasks.inspect('local-conversations',view['current_plan']['run_id'])['admission']['id'])
        self.assertIsNotNone(intent.consent_id)
        self.assertEqual(intent.model_config.max_calls,2)
        self.assertEqual(app.worker.drain('local-conversations'),0)
        with self.assertRaises(Conflict):app.conversations.plan_fixture('local-conversations',self.cid,request,1)

    def test_raw_planning_writer_is_closed_before_it_can_consume_a_slot(self):
        app=self.w._conversation_app();context=app.conversations.planning_context('local-conversations',self.cid,'raw',1,True)
        with self.assertRaisesRegex(Conflict,'requires verified admission'):
            app.conversations.store.admit('local-conversations',self.cid,'raw',1,context,self.now,lambda _:None)
        run=app.conversations.plan_fixture('local-conversations',self.cid,'proper',1)
        self.assertTrue(app.tasks.inspect('local-conversations',run)['admission']['binding_valid'])

    def test_route_reconciliation_uses_saved_action_and_never_starts_a_model(self):
        app=self.w._conversation_app(with_model=True)
        row=app.actions.admit('local-conversations',self.cid,'question',1,'What should I consider next?',False,self.w.action_context(self.cid,1))
        run=app.actions.reconcile('local-conversations',row)
        state=app.tasks.inspect('local-conversations',run)
        self.assertTrue(state['admission']['binding_valid'])
        self.assertEqual(state['tasks'][0]['inputs']['inputs']['allow_model_copy'],False)
        self.assertEqual(app.worker.drain('local-conversations',run_id=run),0)
        self.assertEqual(app.actions.reconcile('local-conversations',row),run)

    def test_public_followup_progress_reports_pause_without_requesting_credentials(self):
        with patch('acquisition.workspace.openrouter_key',side_effect=AssertionError('Loaded a provider key')):
            self.w.route_followup(self.cid,'question',1,'What should I consider next?',False)
            self.w.advance_actions()
            action=self.w.conversation(self.cid)['actions'][0]
        self.assertEqual(action['status'],'blocked')
        self.assertIn('Execution remains paused',action['detail'])
        self.assertTrue(action['generation']['admission_paused'])

    def test_new_standalone_workspace_campaign_inherits_the_persistent_root_gate(self):
        view=self.w.create('campaign','fixture')
        self.assertIsNone(view['review'])
        self.assertTrue(view['generation']['admission_paused'])
        reopened=Workspace(self.root,real_clock=lambda:self.now)
        replay=reopened.create('campaign','fixture')
        self.assertEqual(replay['generation']['run_id'],view['generation']['run_id'])


class CampaignCallerCoverageTests(unittest.TestCase):
    setUp=coverage.WorkflowAdmissionTests.setUp
    plan=coverage.WorkflowAdmissionTests.plan
    conversation_refs=coverage.WorkflowAdmissionTests.conversation_refs
    root_refs=coverage.WorkflowAdmissionTests.root_refs

    def test_completed_legacy_plan_can_feed_verified_conversation_preparation(self):
        scope,refs=self.conversation_refs()
        plan=self.app.conversations.view(self.org,self.cid)['current_plan']['result']
        self.store.seal_legacy_writes()
        app=build(self.path,clock=lambda:self.now)
        run=app.start_conversation(scope,scope,plan,'2026-10-26')
        intent=app.admissions.store.get_request(scope,scope)
        self.assertEqual(intent.ownership.scope_id,self.cid)
        self.assertEqual(intent.tasks[0].inputs['brief']['plan_id'],refs['plan_id'])
        self.assertEqual(app.worker.drain(scope),0)

    def test_conversation_child_shares_account_and_stop_without_workspace_ancestry(self):
        scope,_=self.conversation_refs()
        plan=self.app.conversations.view(self.org,self.cid)['current_plan']['result']
        app=build(self.path,clock=lambda:self.now,model_config=self.config,verified_admissions=True)
        parent=app.start_conversation(scope,scope,plan,'2026-10-26')
        child=app.start_model(scope,'child',size=100,as_of='2026-10-26',parent_run_id=parent)
        root_intent=app.admissions.store.get_request(scope,scope)
        child_intent=app.admissions.store.get_request(scope,'child')
        self.assertEqual(child_intent.ownership,root_intent.ownership)
        self.assertEqual(app.execution.for_run(scope,child),app.execution.for_run(scope,parent))
        app.execution.stop(self.org,self.cid,'stop',1)
        for run in (parent,child):self.assertEqual(app.tasks.inspect(scope,run)['run']['status'],'cancelled')
        with self.assertRaises(Conflict):app.start(scope,'too-late',size=20,parent_run_id=parent)


class RevisionCallerCoverageTests(unittest.TestCase):
    setUp=revisions.CopyRevisionTests.setUp

    def test_native_revision_reconciliation_uses_verified_owner_and_saved_permission(self):
        revisions.CopyRevisionTests.admit(self)
        receipt=self.app.reviews.store.revision_request(self.scope,'revision')
        self.app.admissions.store.seal_legacy_writes()
        configured=self.w._app(self.w._session(self.sid),revision_admission=True)
        run=configured.revisions.reconcile(self.scope,receipt)
        intent=configured.admissions.store.get(self.scope,configured.tasks.inspect(self.scope,run)['admission']['id'])
        self.assertEqual(intent.parent_run_id,self.base['review']['run_id'])
        self.assertEqual(asdict(intent.model_config),receipt['task_inputs']['model_config'])
        self.assertEqual(configured.worker.drain(self.scope,run_id=run),0)
        self.assertEqual(configured.revisions.reconcile(self.scope,receipt),run)
        modified=json.loads(json.dumps(receipt));modified['task_inputs']['feedback']='Changed after confirmation'
        with self.assertRaises(Conflict):configured.revisions.reconcile(self.scope,modified)


class FollowupCallerCoverageTests(unittest.TestCase):
    setUp=followups.FollowupTests.setUp
    approve=followups.FollowupTests.approve
    accept=followups.FollowupTests.accept

    def test_frozen_followup_preparation_uses_verified_ancestry_without_reconstructing_workspace_links(self):
        p=followups.FollowupTests.finalized(self)
        app=self.w._app(self.w._session(self.sid));app.admissions.store.seal_legacy_writes()
        with patch.object(self.w,'_ensure_descendant_links',side_effect=AssertionError('Reconstructed new ancestry')):
            identity='workspace_'+digest({'followup':p['id']})[:24]
            from acquisition.campaigns import brief_from
            brief=brief_from(p['brief']|{'campaign_id':identity,'followup_id':p['id']})
            run=app.start_followup(self.scope,identity,p['snapshot_id'],brief)
        intent=app.admissions.store.get_request(self.scope,identity)
        self.assertEqual(intent.parent_run_id,self.parent['review']['run_id'])
        self.assertEqual(app.worker.drain(self.scope,run_id=run),0)

    def test_manual_workspace_child_uses_admission_parent_after_projection_changes(self):
        followups.FollowupTests.finalized(self)
        app=self.w._app(self.w._session(self.sid));app.admissions.store.seal_legacy_writes()
        with patch('acquisition.adapters.sqlite.execution.SqliteExecution.descendant',side_effect=AssertionError('Workspace reconstructed authority')):
            child=self.w.create('manual-child','fixture',parent_id=self.sid)
            session=self.w._session(child['session']['id'])
            intent=app.admissions.store.get_request(self.scope,session['id'])
            self.assertEqual(intent.parent_run_id,self.parent['review']['run_id'])
            session['parent_id']='missing-presentation-parent';self.w._save(session)
            replay=self.w.prepare(session['id'])
        self.assertEqual(replay['generation']['run_id'],child['generation']['run_id'])
        self.assertIsNone(replay['review'])
        self.assertEqual(app.admissions.store.get_request(self.scope,session['id']),intent)


class AdmissionHttpTests(unittest.TestCase):
    setUp=workspace_tests.WorkspaceHttpTests.setUp
    stop=workspace_tests.WorkspaceHttpTests.stop
    request=workspace_tests.WorkspaceHttpTests.request

    def test_http_creation_obeys_the_persisted_gate_and_transport_authority(self):
        self.server.workspace._conversation_app().admissions.store.seal_legacy_writes()
        status,_,_=self.request('/api/sessions',{'request_id':'denied','mode':'fixture'},{'X-Workspace-Token':'wrong'})
        self.assertEqual(status,403)
        status,body,_=self.request('/api/sessions',{'request_id':'allowed','mode':'fixture','verified_admissions':False})
        self.assertEqual(status,400)
        status,body,_=self.request('/api/sessions',{'request_id':'allowed','mode':'fixture'})
        self.assertEqual(status,200,body)
        value=json.loads(body)
        self.assertEqual(value['tasks']['admission']['status'],'paused')
        self.assertTrue(value['generation']['admission_paused'])
        self.assertIsNone(value['review'])
        self.assertTrue(self.server.workspace._conversation_app().admissions.required())

    def test_second_server_cannot_select_cutover_before_obtaining_the_root_lock(self):
        original=self.server.workspace._conversation_app()
        self.assertFalse(original.admissions.required())
        second=Workspace(self.server.workspace.root,verified_admissions=True)
        with self.assertRaises(BlockingIOError):WorkspaceServer(0,second,self.server.assets)
        self.assertFalse(original.admissions.required())
