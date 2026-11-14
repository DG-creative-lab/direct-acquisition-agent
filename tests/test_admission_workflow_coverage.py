"""Paused workflow admissions through real source journals and SQLite restarts."""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

from acquisition.adapters.synthetic import generate
from acquisition.bootstrap import build, build_admissions
from acquisition.campaigns import Brief
from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.conversations import FIXTURE_MESSAGE
from acquisition.reasoning import CallScope, ModelConfig, ModelError
from acquisition.runtime import TaskSpec
from acquisition.reviews import ActorUnavailable
from acquisition.workspace import Workspace
from acquisition.adapters.sqlite.database import Database, WORKFLOW_ADMISSIONS, ADMISSION_CUTOVER, WRITING_PREFERENCES, SIMULATED_DELIVERY, REPORT_MONITORING
from acquisition.adapters.sqlite.contacts import CONTACT_DIRECTORY
from acquisition.adapters.sqlite.recipient_contexts import RECIPIENT_CONTEXTS
import test_copy_revisions as revisions
import test_followups as followups


class WorkflowAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.now=1792972800.
        self.w=Workspace(self.root,real_clock=lambda:self.now)
        self.path=self.root/'conversations.sqlite';self.org='local-conversations'
        self.cid=self.w.create_conversation('chat','Paused coverage')['id']
        self.w.message_conversation(self.cid,'message',0,FIXTURE_MESSAGE)
        self.app=self.w._conversation_app()
        self.store=build_admissions(self.path,clock=lambda:self.now)
        self.config=ModelConfig('test/model',max_calls=10,force_tool_choice=True)

    def count(self, table):
        with self.store.database.connect() as db:return db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]

    def root_refs(self, campaign='root', model=False, scope=None):
        scope=scope or self.org
        app=build(self.path,clock=lambda:self.now,model_config=self.config,gateway=revisions.RevisionModel())
        snapshot=app.audiences.put(generate(scope,100,42,'2026-10-26'))
        contexts={}
        if model:
            captured=[]
            def capture(org,key,specs,now):captured.extend(specs);return 'not-created'
            with patch.object(app.tasks,'create',side_effect=capture):
                app.start_model(scope,campaign,size=100,as_of='2026-10-26')
            contexts=captured[0].inputs['context_ids']
        return {'brief':asdict(Brief(campaign,60000)), 'snapshot_id':snapshot,'context_ids':contexts}

    def stage(self, kind, refs, key='request', scope=None, config=None):
        return self.store.request_workflow(scope or self.org,key,kind,refs,
            allow_model=config is not None,model_config=config)

    def assert_paused(self, intent):
        before={t:self.count(t) for t in ('model_calls','review_decisions','simulated_agency_jobs','learning_beliefs')}
        receipt=self.store.admit(intent,self.now)
        self.assertIsNone(self.app.tasks.claim(intent.organization,self.now,60,run_id=receipt.run_id))
        self.assertEqual(self.store.find_request(intent.organization,intent.request_id),receipt)
        self.assertEqual(self.store.get(intent.organization,intent.id),intent)
        self.assertEqual(before,{t:self.count(t) for t in before})
        self.assertEqual(build_admissions(self.path,clock=lambda:self.now).admit(intent,self.now),receipt)
        with self.store.database.connect() as db:
            self.assertEqual(db.execute('SELECT status FROM execution_admissions WHERE id=?',(intent.id,)).fetchone()[0],'paused')
            task=db.execute('SELECT id,attempts FROM tasks WHERE run_id=? ORDER BY position',(receipt.run_id,)).fetchone()
            self.assertEqual(task['attempts'],0)
        with self.assertRaisesRegex(ModelError,'execution_admission_paused_before_cutover'):
            self.app.calls.reserve(CallScope(intent.organization,receipt.run_id,task['id'],'restored-token'),
                'not-dispatched','0'*64,10,self.now)
        return receipt

    def plan(self, model=False):
        app=self.app
        if model:
            app=build(self.path,clock=lambda:self.now,model_config=self.config,gateway=revisions.RevisionModel())
            # This is an independently valid saved planning operation, not an
            # injected successful output or an unverified caller proposal.
            app.conversations.message(self.org,self.cid,'edit',1,'Prepare a £600 contractor campaign with model copy.')
            run=app.conversations.plan(self.org,self.cid,'plan',2)
        else:run=app.conversations.plan_fixture(self.org,self.cid,'plan',1)
        app.worker.drain(self.org,run_id=run)
        return app.conversations.view(self.org,self.cid)['plans'][-1]['result']

    def conversation_refs(self, model=False):
        plan=self.plan(model)
        scope='workspace_'+digest({'conversation_id':self.cid,'plan_id':plan['id']})[:24]
        app=build(self.path,clock=lambda:self.now,model_config=self.config,gateway=revisions.RevisionModel())
        captured=[]
        with patch.object(app.tasks,'create',side_effect=lambda org,key,specs,now:captured.extend(specs)):
            app.start_conversation(scope,scope,plan,'2026-10-26')
        inputs=captured[0].inputs
        return scope,{'plan_id':plan['id'],'snapshot_id':inputs['snapshot_id'],'context_ids':inputs.get('context_ids',{})}

    def route(self, content='What should I change next?'):
        self.plan()
        app=build(self.path,clock=lambda:self.now,model_config=self.config,gateway=revisions.RevisionModel())
        return app.actions.admit(self.org,self.cid,'route-source',1,content,False,self.w.action_context(self.cid,1))

    def test_standalone_fixture_and_model_plans_use_explicit_root_ownership_without_calls(self):
        for model in (False,True):
            refs=self.root_refs('root-'+str(model),model)
            intent=self.stage('standalone-campaign',refs,'request-'+str(model),config=self.config if model else None)
            self.assertEqual(intent.ownership.kind,'standalone')
            self.assertIsNone(intent.parent_run_id)
            receipt=self.assert_paused(intent)
            self.assertIsNone(self.app.execution.for_run(self.org,receipt.run_id))
            self.assertTrue(all(s.inputs['execution_admission_id']==intent.id for s in intent.tasks))
            self.assertTrue(all(s.inputs['workflow_version']==('monthly-mail/v3' if model else 'monthly-mail/v1') for s in intent.tasks))

    def test_conversation_fixture_binds_successful_plan_revision_and_current_source(self):
        scope,refs=self.conversation_refs()
        intent=self.stage('conversation-campaign',refs,scope=scope)
        self.assertEqual(intent.ownership.scope_id,self.cid)
        self.assertEqual(intent.ownership.organization,self.org)
        self.assertEqual(intent.tasks[0].inputs['brief']['plan_id'],refs['plan_id'])
        receipt=self.assert_paused(intent)
        self.assertEqual(self.app.execution.for_run(scope,receipt.run_id)['run_revision'],1)
        with self.assertRaises(Conflict):self.stage('conversation-campaign',refs,'foreign',scope='foreign')

    def test_conversation_model_preflights_the_saved_objective_and_v3_contexts(self):
        scope,refs=self.conversation_refs(True)
        intent=self.stage('conversation-campaign',refs,scope=scope,config=self.config)
        self.assertEqual(intent.ownership.revision,2)
        self.assertEqual(intent.tasks[0].inputs['workflow_version'],'conversation-model-mail/v3')
        self.assert_paused(intent)

    def test_routing_uses_original_question_context_and_separate_one_call_consent(self):
        action=self.route()
        cfg=ModelConfig(**action['model_config'])
        refs={'action_id':action['id']}
        with self.assertRaises(ValueError):self.stage('routing',refs)
        with self.assertRaises(Conflict):self.stage('routing',refs,config=replace(cfg,model='changed/model'))
        intent=self.stage('routing',refs,config=cfg)
        self.assertEqual(intent.tasks[0].inputs['context']['dialogue'],action['context']['dialogue'])
        self.assertFalse(intent.tasks[0].inputs['inputs']['allow_model_copy'])
        self.assert_paused(intent)
        configured=build(self.path,clock=lambda:self.now,model_config=self.config,gateway=revisions.RevisionModel())
        with self.assertRaises(Conflict):configured.actions.reconcile(self.org,action)

    def test_aliases_do_not_create_fake_runtime_tasks(self):
        action=self.route('status')
        with self.assertRaises(Conflict):self.stage('routing',{'action_id':action['id']},config=replace(self.config,max_calls=1))
        self.assertEqual(self.count('admission_requests'),0)

    def test_manual_child_inherits_verified_account_and_original_revision(self):
        scope,refs=self.conversation_refs()
        root=self.stage('conversation-campaign',refs,'root',scope=scope)
        parent=self.store.admit(root,self.now)
        childrefs=self.root_refs('child',scope=scope)|{'parent_run_id':parent.run_id}
        child=self.stage('manual-descendant',childrefs,'child',scope=scope)
        self.assertEqual(child.ownership,root.ownership)
        self.assertEqual(child.parent_run_id,parent.run_id)
        self.assert_paused(child)
        self.assertEqual(self.count('conversation_execution'),1)
        with self.assertRaises(Conflict):self.stage('standalone-campaign',
            {'snapshot_id':refs['snapshot_id'],'brief':asdict(Brief(root.source_id))},'erase',scope=scope)

    def test_manual_standalone_lineage_requires_a_positive_parent_not_missing_metadata(self):
        root=self.stage('standalone-campaign',self.root_refs(),'root')
        parent=self.store.admit(root,self.now)
        child=self.stage('manual-descendant',self.root_refs('child')|{'parent_run_id':parent.run_id},'child')
        self.assertEqual(child.ownership,root.ownership)
        self.assert_paused(child)
        legacy=self.app.start(self.org,'legacy',size=20)
        with self.assertRaises(Conflict):self.stage('manual-descendant',self.root_refs('unknown-child')|{'parent_run_id':legacy},'unknown')
        with self.assertRaises(NotFound):self.stage('manual-descendant',self.root_refs('foreign-child',scope='other')|{'parent_run_id':parent.run_id},'foreign',scope='other')

    def test_request_key_source_operation_and_runtime_key_cannot_be_reused(self):
        refs=self.root_refs()
        first=self.stage('standalone-campaign',refs)
        changed=self.root_refs('changed')
        with self.assertRaises(Conflict):self.stage('standalone-campaign',changed)
        with self.assertRaises(Conflict):self.stage('standalone-campaign',refs,'second')
        for writer in (lambda:self.app.tasks.create(self.org,'root',first.tasks,self.now),
                       lambda:self.app.start(self.org,'root',size=100)):
            with self.assertRaises(Conflict):writer()
        self.assertEqual(self.count('runs'),0)
        self.assert_paused(first)

    def test_changed_intents_denied_permission_and_foreign_sources_have_no_effect(self):
        refs=self.root_refs(model=True)
        with self.assertRaises(ValueError):self.store.request_workflow(self.org,'no','standalone-campaign',refs,allow_model=False,model_config=self.config)
        intent=self.stage('standalone-campaign',refs,config=self.config)
        for modified in (replace(intent,parent_run_id='invented'),replace(intent,source_fingerprint='0'*64),
                         replace(intent,model_config=replace(self.config,model='other/model'))):
            with self.assertRaises(Conflict):self.store.admit(modified,self.now)
        with self.assertRaises(NotFound):self.stage('standalone-campaign',refs,'foreign',scope='foreign',config=self.config)
        self.assertEqual(self.count('runs'),0)

    def test_changed_brief_and_stop_block_children_before_runtime_insertion(self):
        scope,refs=self.conversation_refs()
        intent=self.stage('conversation-campaign',refs,scope=scope)
        self.app.execution.stop(self.org,self.cid,'stop',1)
        with self.assertRaises(Conflict):self.store.admit(intent,self.now)
        self.assertEqual(self.count('execution_admissions'),0)

    def test_conversation_edit_after_staging_keeps_the_original_request_historical(self):
        scope,refs=self.conversation_refs()
        intent=self.stage('conversation-campaign',refs,scope=scope)
        self.w.message_conversation(self.cid,'edit',1,'Use £400 instead.')
        self.assertEqual(self.store.get_request(scope,'request'),intent)
        with self.assertRaises(Conflict):self.store.admit(intent,self.now)
        self.assertEqual(self.count('execution_admissions'),0)

    def test_selected_dataset_provenance_reaches_every_paused_campaign_task(self):
        plan=self.plan()
        candidates=self.app.conversation_audiences.candidates(self.org,self.cid,1,plan['id'])
        entry=candidates['entries'][0]
        selection=self.app.conversation_audiences.select(self.org,self.cid,'source',1,plan['id'],
            entry['dataset_id'],entry['version'],entry['checksum'],entry['id'])
        scope='workspace_'+digest({'conversation_id':self.cid,'plan_id':plan['id']})[:24]
        snapshot,_=self.app.conversation_audiences.materialize(self.org,self.cid,1,plan['id'],scope)
        self.app.audiences.put(snapshot)
        wrong=replace(snapshot,seed=snapshot.seed+1);self.app.audiences.put(wrong)
        with self.assertRaises(Conflict):self.stage('conversation-campaign',{'plan_id':plan['id'],'snapshot_id':wrong.id},scope=scope)
        intent=self.stage('conversation-campaign',{'plan_id':plan['id'],'snapshot_id':snapshot.id},scope=scope)
        for task in intent.tasks:self.assertEqual(task.inputs['brief']['audience_source'],selection)
        self.assert_paused(intent)

    def test_missing_incomplete_and_wrong_snapshot_context_are_rejected_before_staging(self):
        refs=self.root_refs(model=True)
        with self.assertRaises(NotFound):self.stage('standalone-campaign',refs|{'snapshot_id':'missing'},config=self.config)
        snapshot=self.app.audiences.get(self.org,refs['snapshot_id'])
        incomplete=replace(snapshot,complete=False);self.app.audiences.put(incomplete)
        with self.assertRaises(Conflict):self.stage('standalone-campaign',refs|{'snapshot_id':incomplete.id},config=self.config)
        other=self.app.audiences.put(replace(snapshot,seed=123))
        with self.assertRaises(Conflict):self.stage('standalone-campaign',refs|{'snapshot_id':other},config=self.config)
        with self.assertRaisesRegex(ModelError,'input_budget_exceeded'):
            self.stage('standalone-campaign',refs,config=replace(self.config,max_input_bytes=1024))
        self.assertEqual(self.count('admission_requests'),0)

    def test_source_deadline_is_rechecked_after_preflight_before_both_commits(self):
        refs=self.root_refs(model=True)
        original=self.store.workflow_intent
        def delayed(*args):
            intent=original(*args)
            self.now=1795564800.  # The recorded product review window has ended.
            return intent
        with patch.object(self.store,'workflow_intent',side_effect=delayed),self.assertRaises(Conflict):
            self.stage('standalone-campaign',refs,config=self.config)
        self.assertEqual(self.count('admission_requests'),0)
        self.now=1792972800.
        intent=self.stage('standalone-campaign',refs,config=self.config)
        with patch.object(self.store,'workflow_intent',side_effect=delayed),self.assertRaises(Conflict):
            self.store.admit(intent,self.now)
        self.assertEqual(self.count('execution_admissions'),0)

    def test_new_source_kinds_do_not_consume_another_planning_slot(self):
        action=self.route()
        self.stage('routing',{'action_id':action['id']},config=ModelConfig(**action['model_config']))
        self.w.message_conversation(self.cid,'edit',1,'Prepare a £600 contractor campaign.')
        app=build(self.path,clock=lambda:self.now,model_config=self.config,gateway=revisions.RevisionModel())
        run=app.conversations.plan(self.org,self.cid,'next-plan',2)
        app.worker.drain(self.org,run_id=run)
        self.assertEqual(app.tasks.inspect(self.org,run)['run']['status'],'succeeded')

    def test_unknown_workflows_cannot_supply_raw_tasks_or_ownership(self):
        for kind,refs in (('unknown',{}),('standalone-campaign',{'tasks':[],'ownership':{}})):
            with self.assertRaises(ValueError):self.stage(kind,refs)
        self.assertEqual(self.count('admission_requests'),0)

    def test_admission_failure_rolls_back_runtime_ownership_receipt_and_event(self):
        intent=self.stage('standalone-campaign',self.root_refs())
        before=self.count('runs'),self.count('events')
        with patch('acquisition.adapters.sqlite.admissions.event',side_effect=OSError('crash')):
            with self.assertRaises(OSError):self.store.admit(intent,self.now)
        self.assertEqual((self.count('runs'),self.count('events')),before)
        self.assertEqual(self.count('execution_admissions'),0)
        self.assert_paused(intent)

    def test_concurrent_duplicate_requests_and_fresh_process_replay(self):
        refs=self.root_refs()
        def stage(_):return build_admissions(self.path,clock=lambda:self.now).request_workflow(
            self.org,'same','standalone-campaign',refs,allow_model=False)
        with ThreadPoolExecutor(max_workers=2) as pool:intents=list(pool.map(stage,range(2)))
        self.assertEqual(intents[0],intents[1]);receipt=self.assert_paused(intents[0])
        code='''import sys,json
from dataclasses import asdict
from acquisition.bootstrap import build_admissions
s=build_admissions(sys.argv[1],clock=lambda:1792972800.)
i=s.get_request('local-conversations','same')
print(json.dumps(asdict(s.admit(i,1792972800.))))
'''
        result=subprocess.run([sys.executable,'-c',code,str(self.path)],env=dict(os.environ,PYTHONPATH=str(Path('src').resolve())),capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout),asdict(receipt))


class RevisionAdmissionCoverageTests(unittest.TestCase):
    setUp=revisions.CopyRevisionTests.setUp

    def test_native_exact_subject_receipt_is_consumed_without_repeating_rejection(self):
        revisions.CopyRevisionTests.admit(self)
        receipt=self.app.reviews.store.revision_request(self.scope,'revision')
        store=build_admissions(self.root/'conversations.sqlite',clock=lambda:self.now)
        with store.database.connect() as db:before=db.execute('SELECT COUNT(*) FROM review_decisions').fetchone()[0]
        cfg=ModelConfig(**receipt['task_inputs']['model_config'])
        with self.assertRaises(Conflict):store.request_workflow(self.scope,'changed','copy-revision',{'revision_request_id':'revision'},
            allow_model=True,model_config=replace(cfg,model='changed/model'))
        intent=store.request_workflow(self.scope,'paused-revision','copy-revision',{'revision_request_id':'revision'},
            allow_model=True,model_config=cfg)
        admitted=store.admit(intent,self.now)
        self.assertEqual(intent.parent_run_id,self.base['review']['run_id'])
        self.assertIsNone(self.app.tasks.claim(self.scope,self.now,180,run_id=admitted.run_id))
        with self.assertRaises(Conflict):store.request_workflow(self.scope,'not-a-campaign','manual-descendant',
            {'parent_run_id':admitted.run_id,'brief':asdict(Brief('child-of-revision')),
             'snapshot_id':self.base['review']['manifest']['snapshot_id']},allow_model=False)
        with store.database.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM review_decisions').fetchone()[0],before)
        configured=self.w._app(self.w._session(self.sid),with_model=True)
        with self.assertRaises(Conflict):configured.revisions.reconcile(self.scope,receipt)

    def test_revision_admission_rechecks_revoked_operator_and_evidence(self):
        revisions.CopyRevisionTests.admit(self)
        receipt=self.app.reviews.store.revision_request(self.scope,'revision')
        store=build_admissions(self.root/'conversations.sqlite',clock=lambda:self.now)
        intent=store.request_workflow(self.scope,'paused','copy-revision',{'revision_request_id':'revision'},
            allow_model=True,model_config=ModelConfig(**receipt['task_inputs']['model_config']))
        with store.database.transaction() as db:db.execute('UPDATE review_actors SET enabled=0 WHERE organization=? AND id=?',(self.scope,'local-operator'))
        with self.assertRaises(ActorUnavailable):store.admit(intent,self.now)


class LearningAdmissionCoverageTests(unittest.TestCase):
    setUp=followups.FollowupTests.setUp
    approve=followups.FollowupTests.approve
    accept=followups.FollowupTests.accept

    def test_finalized_followup_inherits_real_parent_and_preserves_learning_and_approval(self):
        p=followups.FollowupTests.finalized(self)
        store=build_admissions(self.root/'conversations.sqlite',clock=lambda:1792972800.)
        intent=store.request_workflow(self.scope,'paused-followup','learning-followup',{'proposal_id':p['id']},allow_model=False)
        self.assertEqual(intent.parent_run_id,self.parent['review']['run_id'])
        before=self.w.view(self.sid)
        receipt=store.admit(intent,1792972800.)
        app=self.w._app(self.w._session(self.sid))
        self.assertIsNone(app.tasks.claim(self.scope,1792972800.,60,run_id=receipt.run_id))
        after=self.w.view(self.sid)
        self.assertEqual(after['learning'],before['learning'])
        self.assertEqual(after['review']['approval'],before['review']['approval'])

    def test_followup_suppression_change_blocks_paused_admission(self):
        p=followups.FollowupTests.finalized(self)
        store=build_admissions(self.root/'conversations.sqlite',clock=lambda:1792972800.)
        intent=store.request_workflow(self.scope,'paused-followup','learning-followup',{'proposal_id':p['id']},allow_model=False)
        app=self.w._app(self.w._session(self.sid))
        app.reviews.store.suppress(self.scope,'local-operator','late',p['population'][0],'Changed after staging')
        with self.assertRaises(Conflict):store.admit(intent,1792972800.)

    def test_model_followup_uses_frozen_contexts_without_current_catalogue_or_new_calls(self):
        p=followups.FollowupTests.finalized(self)
        store=build_admissions(self.root/'conversations.sqlite',clock=lambda:1792972800.)
        with patch('acquisition.bootstrap.agent_catalogue',side_effect=OSError('Current catalogue unavailable')):
            intent=store.request_workflow(self.scope,'model-followup','learning-followup',{'proposal_id':p['id']},
                allow_model=True,model_config=ModelConfig(**p['model_config']))
            receipt=store.admit(intent,1792972800.)
        self.assertEqual(intent.tasks[0].inputs['context_ids'],p['contexts'])
        self.assertEqual(intent.tasks[0].inputs['workflow_version'],'monthly-mail/v3')
        app=self.w._app(self.w._session(self.sid))
        self.assertIsNone(app.tasks.claim(self.scope,1792972800.,60,run_id=receipt.run_id))

    @staticmethod
    def admission_effects(store):
        with store.database.connect() as db:
            return {table:db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in (
                'admission_requests','execution_admissions','runs','tasks','events','execution_runs',
                'model_calls','review_decisions','simulated_agency_jobs','learning_beliefs')}

    def test_model_followup_rejects_changed_frozen_settings_before_staging(self):
        p=followups.FollowupTests.finalized(self)
        store=build_admissions(self.root/'conversations.sqlite',clock=lambda:1792972800.)
        original=ModelConfig(**p['model_config'])
        changes={'model':'other/model','max_calls':9,'max_input_bytes':32000,
                 'max_output_tokens':128,'max_prompt_usd_per_million':0.25,
                 'max_completion_usd_per_million':0.5}
        before=self.admission_effects(store)
        for field,value in changes.items():
            changed=replace(original,**{field:value})
            self.assertNotEqual(changed.payload(),p['model_config'])
            with self.subTest(field=field),patch('acquisition.workflows.admission_coverage._copy_preflight',
                    side_effect=AssertionError('Mismatched settings reached model preflight')):
                with self.assertRaisesRegex(Conflict,'frozen model settings'):
                    store.request_workflow(self.scope,'changed-'+field,'learning-followup',{'proposal_id':p['id']},
                        allow_model=True,model_config=changed)
            self.assertEqual(self.admission_effects(store),before)
        intent=store.request_workflow(self.scope,'original','learning-followup',{'proposal_id':p['id']},
            allow_model=True,model_config=original)
        receipt=store.admit(intent,1792972800.)
        for task in intent.tasks:self.assertEqual(task.inputs['model_config'],p['model_config'])
        app=self.w._app(self.w._session(self.sid))
        self.assertEqual(app.followups.get(self.scope,p['id']),p)
        self.assertIsNone(app.tasks.claim(self.scope,1792972800.,60,run_id=receipt.run_id))

    def test_model_followup_rechecks_frozen_settings_for_previously_staged_request(self):
        p=followups.FollowupTests.finalized(self)
        path=self.root/'conversations.sqlite'
        store=build_admissions(path,clock=lambda:1792972800.)
        changed=replace(ModelConfig(**p['model_config']),model='other/model')
        from acquisition.workflows.admission_coverage import coverage_plan
        def old_task_builder(kind,references,source,config,organization,now):
            # Reproduce the prior writer's unchecked task construction. The
            # actual saved source, its fingerprint and consent stay intact.
            substituted=source|{'proposal':source['proposal']|{'model_config':config.payload()}}
            return coverage_plan(kind,references,substituted,config,organization,now)
        with patch('acquisition.workflows.admission_coverage.coverage_plan',side_effect=old_task_builder):
            intent=store.request_workflow(self.scope,'previous-writer','learning-followup',{'proposal_id':p['id']},
                allow_model=True,model_config=changed)
        reopened=build_admissions(path,clock=lambda:1792972800.)
        self.assertEqual(reopened.get_request(self.scope,'previous-writer'),intent)
        before=self.admission_effects(reopened)
        with self.assertRaisesRegex(Conflict,'frozen model settings'):reopened.admit(intent,1792972800.)
        self.assertEqual(self.admission_effects(reopened),before)
        self.assertEqual(reopened.get_request(self.scope,'previous-writer'),intent)
        self.assertIsNone(reopened.find_request(self.scope,'previous-writer'))


class WorkflowAdmissionMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'old.sqlite';self.now=1792972800.
        original=Database._apply_migration
        def eleven(db,script):
            if script not in {WORKFLOW_ADMISSIONS,ADMISSION_CUTOVER, WRITING_PREFERENCES, SIMULATED_DELIVERY, REPORT_MONITORING, CONTACT_DIRECTORY, RECIPIENT_CONTEXTS}:original(db,script)
        with patch.object(Database,'_apply_migration',side_effect=eleven),patch.object(Database,'_initialize_workspace_schema'),patch.object(Database,'_validate_writing_preference_schema'),patch.object(Database,'_validate_simulated_delivery_schema'),patch.object(Database,'_validate_report_monitoring_schema'),patch.object(Database,'_validate_contact_schema'),patch.object(Database,'_validate_recipient_context_schema'):
            app=build(self.path,clock=lambda:self.now)
            store=build_admissions(self.path,clock=lambda:self.now)
            org='one';cid=app.conversations.create(org,'chat')['id']
            app.conversations.message(org,cid,'message',0,FIXTURE_MESSAGE)
            context=app.conversations.planning_context(org,cid,'plan',1,True)
            self.intent=store.request_planning(org,cid,'plan',1,context,fixture=True,allow_model=False)
            self.receipt=store.admit(self.intent,self.now)
        self.tables=('admission_requests','execution_admissions','legacy_task_admissions','runs','tasks','events','execution_runs')
        self.before=self.records()

    def records(self):
        with sqlite3.connect(self.path) as db:
            return {table:db.execute('SELECT * FROM '+table).fetchall() for table in self.tables}

    def test_schema_twelve_preserves_original_bytes_receipts_and_legacy_cutoff(self):
        with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda _:Database(self.path),range(2)))
        self.assertEqual(self.records(),self.before)
        store=build_admissions(self.path,clock=lambda:self.now)
        self.assertEqual(store.admit(self.intent,self.now),self.receipt)
        with store.database.connect() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],19)
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
            with self.assertRaises(sqlite3.IntegrityError):db.execute('DELETE FROM admission_requests')

    def test_interrupted_forward_migration_rolls_back_the_entire_rebuild(self):
        original=Database._apply_migration
        def fail(db,script):
            original(db,script)
            if script==WORKFLOW_ADMISSIONS:raise OSError('Crash before commit')
        with patch.object(Database,'_apply_migration',side_effect=fail),self.assertRaises(OSError):Database(self.path)
        self.assertEqual(self.records(),self.before)
        with sqlite3.connect(self.path) as db:self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],11)
        Database(self.path)
        self.assertEqual(self.records(),self.before)
