"""Application authority survives missing or adversarial workspace projections."""
import json
import math
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from acquisition.bootstrap import build
from acquisition.adapters.synthetic import generate
from acquisition.campaigns import Brief
from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.conversations import FIXTURE_MESSAGE, EnvironmentIntent
from acquisition.workspace import Workspace
from acquisition.reviews import ActorUnavailable
from acquisition.reasoning import ModelConfig
from test_legacy_action_replay import durable_rows
import test_followups as followups


class WorkspaceAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.now=1792972800.
        self.w=Workspace(self.root,real_clock=lambda:self.now,verified_admissions=True)

    def create(self,key='root',mode='fixture'):
        return self.w._session(self.w.create(key,mode)['session']['id'])

    def prepare(self,key='prepare',fixture=True):
        cid=self.w.create_conversation('chat','Owned continuation')['id']
        self.w.message_conversation(cid,'message',0,FIXTURE_MESSAGE)
        self.w.start_preparation(cid,key,1,fixture,False)
        return cid,self.w.preparations.store.for_revision('local-conversations',cid,1)

    def app(self,session):return self.w._app(session)

    def unlinked(self,key,mode='fixture',parent_id=None):
        with patch.object(self.w,'_project_session',side_effect=OSError('projection interrupted')):
            with self.assertRaises(OSError):self.w.create(key,mode,parent_id)
        return self.w.authority.get('workspace_'+digest({'request_id':key})[:24])

    def test_fixture_environment_rejects_valid_model_run_with_its_exact_key_after_restart(self):
        session=self.unlinked('mode-mismatch');org=session['organization'];sid=session['id']
        app=build(self.app(session).tasks.database.path,clock=lambda:self.now,
                  model_config=ModelConfig('openai/gpt-oss-120b',max_calls=10,force_tool_choice=True))
        run=app.start_model(org,sid,as_of='2026-10-25')
        self.assertTrue(app.tasks.inspect(org,run)['admission']['binding_valid'])
        before=durable_rows(app)
        with self.assertRaises(Conflict):self.w.authority.save(session|{'run_id':run})
        self.assertEqual(durable_rows(app),before)
        reopened=Workspace(self.root,real_clock=lambda:self.now)
        with patch('acquisition.workspace.OpenRouter',side_effect=AssertionError('Provider loaded')):
            with self.assertRaises(Conflict):reopened.prepare(sid)
        self.assertIsNone(reopened.authority.get(sid)['run_id'])
        self.assertEqual(app.calls.inspect(org,run),[])
        self.assertEqual(app.worker.drain(org,run_id=run),0)

    def test_run_link_rejects_valid_same_mode_commands_with_changed_inputs(self):
        variants=({'size':40},{'seed':43},{'budget_pence':60000},{'as_of':'2026-10-26'})
        for index,changed in enumerate(variants):
            with self.subTest(changed=changed):
                session=self.unlinked('wrong-command-'+str(index));app=self.app(session)
                run=app.start(session['organization'],session['id'],**({'as_of':'2026-10-25'}|changed))
                self.assertTrue(app.tasks.inspect(session['organization'],run)['admission']['binding_valid'])
                before=durable_rows(app)
                with self.assertRaises(Conflict):self.w.authority.save(session|{'run_id':run})
                self.assertEqual(durable_rows(app),before)

    def forged_audience_run(self,session,snapshot,entry_changes=None):
        app=self.w._app(session,with_model=True);org=session['organization'];sid=session['id']
        as_of=datetime.fromtimestamp(session['clock'],timezone.utc).date().isoformat()
        brief=asdict(Brief(sid));model=session['mode']=='model'
        refs={'brief':brief,'snapshot_id':app.audiences.put(snapshot),'runtime_request_id':sid}
        entry={'method':'start','size':1000,'seed':42,'as_of':as_of,'brief':brief,'campaign_id':None,'parent_run_id':None}
        if model:
            _,contexts=app._model_inputs(org,sid,snapshot_override=snapshot)
            refs['context_ids']=contexts
            entry|={'method':'start-model','budget_pence':85000,'objective':None,
                    'snapshot_override':None,'contexts_override':None}
        entry|=entry_changes or {}
        run=app.admissions.workflow(org,sid,'standalone-campaign',entry,lambda:refs,allow_model=model,
                                    config=app.model_config if model else None)
        self.assertTrue(app.tasks.inspect(org,run)['admission']['binding_valid'])
        return app,run

    def test_original_entrypoint_is_checked_even_with_the_expected_audience(self):
        session=self.unlinked('correct-audience-wrong-command')
        day=datetime.fromtimestamp(session['clock'],timezone.utc).date().isoformat()
        app,run=self.forged_audience_run(session,generate(session['organization'],1000,42,day),{'size':20})
        before=durable_rows(app)
        with self.assertRaises(Conflict):self.w.authority.save(session|{'run_id':run})
        self.assertEqual(durable_rows(app),before)

    def test_claimed_generation_parameters_cannot_certify_a_different_audience(self):
        for mode in ('fixture','model'):
            for variant in ('size','seed','date','content'):
                with self.subTest(mode=mode,variant=variant):
                    session=self.unlinked('audience-'+mode+'-'+variant,mode)
                    day=datetime.fromtimestamp(session['clock'],timezone.utc).date().isoformat()
                    snapshot=generate(session['organization'],20 if variant=='size' else 1000,
                                      43 if variant=='seed' else 42,'2026-10-24' if variant=='date' else day)
                    if variant=='content':
                        snapshot=replace(snapshot,records=(replace(snapshot.records[0],address='DEMO ONLY DO NOT POST: substituted'),)+snapshot.records[1:])
                    app,run=self.forged_audience_run(session,snapshot);before=durable_rows(app)
                    with self.assertRaises(Conflict):self.w.authority.save(session|{'run_id':run})
                    self.assertEqual(durable_rows(app),before)
                    self.assertIsNone(self.w.authority.get(session['id'])['run_id'])
                    self.assertEqual(app.calls.inspect(session['organization'],run),[])

    def test_model_environment_cannot_be_linked_to_fixture_work(self):
        session=self.unlinked('mode-downgrade','model');app=self.app(session)
        run=app.start(session['organization'],session['id'],as_of='2026-10-26')
        before=durable_rows(app)
        with self.assertRaises(Conflict):self.w.authority.save(session|{'run_id':run})
        self.assertEqual(durable_rows(app),before)

    def test_unsourced_conversation_rejects_a_different_audience_behind_the_same_claim(self):
        root=self.root/'conversation-audience';compat=Workspace(root,real_clock=lambda:self.now)
        cid=compat.create_conversation('chat','Saved proposal')['id']
        compat.message_conversation(cid,'message',0,FIXTURE_MESSAGE)
        plan=compat.plan_conversation_fixture(cid,'plan',1)['current_plan']['result']
        compat._conversation_app().admissions.store.seal_legacy_writes()
        selected=Workspace(root,real_clock=lambda:self.now)
        with patch.object(selected,'_project_session',side_effect=OSError('projection interrupted')):
            with self.assertRaises(OSError):selected.draft_conversation(cid,'draft',1,plan['id'])
        sid='workspace_'+digest({'conversation_id':cid,'plan_id':plan['id']})[:24]
        session=selected.authority.get(sid);app=selected._app(session)
        day=datetime.fromtimestamp(session['clock'],timezone.utc).date().isoformat()
        refs={'plan_id':plan['id'],'snapshot_id':app.audiences.put(generate(session['organization'],20,42,day))}
        entry={'method':'start-conversation','plan':plan,'as_of':day,'selected_audience':False}
        run=app.admissions.workflow(session['organization'],sid,'conversation-campaign',entry,lambda:refs,allow_model=False,config=None)
        self.assertTrue(app.tasks.inspect(session['organization'],run)['admission']['binding_valid'])
        before=durable_rows(app)
        with self.assertRaises(Conflict):selected.authority.save(session|{'run_id':run})
        self.assertEqual(durable_rows(app),before)

    def test_selected_dataset_uses_its_frozen_provenance_instead_of_the_synthetic_recipe(self):
        root=self.root/'selected-audience';compat=Workspace(root,real_clock=lambda:self.now)
        cid=compat.create_conversation('chat','Selected proposal')['id']
        compat.message_conversation(cid,'message',0,FIXTURE_MESSAGE)
        plan=compat.plan_conversation_fixture(cid,'plan',1)['current_plan']['result']
        entry=compat.audience_catalogue()['entries'][0]
        receipt=compat.select_conversation_audience(cid,request_id='select',expected_revision=1,plan_id=plan['id'],
            dataset_id=entry['dataset_id'],version=entry['version'],checksum=entry['checksum'],manifest_id=entry['id'])['audience_receipt']
        compat._conversation_app().admissions.store.seal_legacy_writes()
        selected=Workspace(root,real_clock=lambda:self.now)
        with patch('acquisition.bootstrap.generated_snapshot_identity',side_effect=AssertionError('Selected dataset was regenerated')):
            result=selected.draft_conversation(cid,'draft',1,plan['id'])
        session=selected._session(result['session']['id']);app=selected._app(session)
        self.assertEqual(session['audience_selection'],receipt)
        snapshot_id=result['tasks']['tasks'][0]['inputs']['snapshot_id']
        self.assertEqual(len(app.audiences.get(session['organization'],snapshot_id).records),100)
        self.assertEqual(result['tasks']['admission']['status'],'paused')

    def test_manual_child_rejects_a_valid_standalone_run_with_its_own_key(self):
        parent=self.create();self.seed_clock_source(parent)
        sibling=self.w.create('sibling','fixture',parent['id'])['session']
        for key,other_parent in (('standalone',None),('another-parent',sibling['run_id'])):
            with self.subTest(key=key):
                child=self.unlinked(key,parent_id=parent['id']);app=self.app(child)
                run=app.start(child['organization'],child['id'],as_of='2026-10-26',parent_run_id=other_parent)
                self.assertEqual(app.admissions.store.get_request(child['organization'],child['id']).parent_run_id,other_parent)
                before=durable_rows(app)
                with self.assertRaises(Conflict):self.w.authority.save(child|{'run_id':run})
                self.assertEqual(durable_rows(app),before)

    def test_malformed_projection_rows_cannot_hide_owned_sessions_or_conversations(self):
        session=self.create();cid,prep=self.prepare();app=self.app(session);before=durable_rows(app)
        malformed=('{}','[]','null','{broken',canonical({'id':'wrong','created_at':self.now}),
                   canonical(session|{'id':'bad-clock','created_at':None}),
                   canonical(session|{'id':'bad-plan','conversation_plan':[]}),
                   canonical(session|{'id':'null-plan','conversation_plan':None}), '['*1100+']'*1100)
        with self.w.control() as db:
            db.execute("UPDATE sessions SET payload='{broken' WHERE id=?",(session['id'],))
            for i,payload in enumerate(malformed):
                if 5<=i<=7:payload=canonical(json.loads(payload)|{'id':'broken-'+str(i)})
                db.execute('INSERT INTO sessions VALUES(?,?,?)',('broken-'+str(i),'unused',payload))
        for workspace in (self.w,Workspace(self.root,real_clock=lambda:self.now)):
            self.assertEqual(workspace.listing()['sessions'],[{k:session[k] for k in ('id','name','mode','created_at','case_id')}])
            self.assertEqual(workspace._session(session['id']),session)
            self.assertEqual(workspace.conversation(cid)['preparations'][0]['id'],prep['id'])
            self.assertEqual(workspace.action_context(cid,1)['target']['conversation_id'],cid)
        self.assertEqual(durable_rows(app),before)

    def test_conversation_environment_rejects_a_valid_standalone_source(self):
        root=self.root/'conversation-mismatch';compat=Workspace(root,real_clock=lambda:self.now)
        cid=compat.create_conversation('chat','Saved proposal')['id']
        compat.message_conversation(cid,'message',0,FIXTURE_MESSAGE)
        plan=compat.plan_conversation_fixture(cid,'plan',1)['current_plan']['result']
        compat._conversation_app().admissions.store.seal_legacy_writes()
        selected=Workspace(root,real_clock=lambda:self.now)
        with patch.object(selected,'_project_session',side_effect=OSError('projection interrupted')):
            with self.assertRaises(OSError):selected.draft_conversation(cid,'draft',1,plan['id'])
        sid='workspace_'+digest({'conversation_id':cid,'plan_id':plan['id']})[:24]
        session=selected.authority.get(sid);app=selected._app(session)
        run=app.start(session['organization'],sid,as_of='2026-10-25')
        before=durable_rows(app)
        with self.assertRaises(Conflict):selected.authority.save(session|{'run_id':run})
        self.assertEqual(durable_rows(app),before)

    def test_routing_mode_clock_and_domain_links_ignore_poisoned_projection(self):
        for mode in ('fixture','model'):
            with self.subTest(mode=mode):
                session=self.create(mode,mode);app=self.app(session);before=durable_rows(app)
                fake=session|{'organization':'some-other-org','database_scope':'conversations','mode':'model' if mode=='fixture' else 'fixture',
                              'clock':self.now+90*86400,'clock_mode':'SIMULATED','run_id':'wrong-run','case_id':'wrong-case','name':'Poisoned'}
                with self.w.control() as db:db.execute('UPDATE sessions SET payload=? WHERE id=?',(canonical(fake),session['id']))
                self.assertEqual(self.w._session(session['id']),session)
                with patch('acquisition.workspace.OpenRouter',side_effect=AssertionError('Loaded provider')):
                    routed=self.w._app(fake,with_model=True)
                self.assertEqual(routed.tasks.database.path,app.tasks.database.path)
                self.assertEqual(routed.clock(),max(self.now,session['clock']) if mode=='model' else session['clock'])
                self.assertEqual(self.w.view(session['id'])['session'],{k:v for k,v in session.items() if k!='organization'})
                self.assertEqual(durable_rows(app),before)
                self.assertNotEqual(next(s for s in self.w.listing()['sessions'] if s['id']==session['id'])['name'],'Poisoned')

    def test_model_creation_replay_preserves_original_environment_and_uses_live_time(self):
        session=self.create(mode='model');app=self.app(session);before=durable_rows(app)
        self.now+=500
        with patch('acquisition.bootstrap.Application._model_inputs',side_effect=AssertionError('Rebuilt model inputs')):
            replay=self.w._session(self.w.create('root','model')['session']['id'])
        self.assertEqual(replay,session)
        self.assertEqual(self.app(replay).clock(),self.now)
        self.assertEqual(durable_rows(app),before)
        with self.assertRaises(Conflict):self.w.create('root','fixture')
        self.assertEqual(durable_rows(app),before)

    def test_existing_environment_cannot_acquire_an_unrelated_creation_command(self):
        session=self.create();app=self.app(session);before=durable_rows(app)
        initial=session|{'run_id':None,'case_id':None,'cohort_id':None}
        with self.assertRaises(Conflict):self.w.authority.create(initial,'conversation','another-chat','alias',{'plan_id':'unrelated'})
        with self.assertRaises(Conflict):self.w.authority.create(initial,'root','root','different',{'mode':'fixture','parent_id':None})
        self.assertEqual(durable_rows(app),before)

    def test_missing_projection_keeps_owned_sessions_preparation_and_time_readable(self):
        session=self.create();cid,prep=self.prepare();app=self.app(session)
        root_app=self.w._conversation_app();owned_before=durable_rows(app);root_before=durable_rows(root_app)
        for suffix in ('','-wal','-shm'):
            (self.root/('workspace.sqlite'+suffix)).unlink(missing_ok=True)
        reopened=Workspace(self.root,real_clock=lambda:self.now)
        self.assertEqual(reopened._session(session['id']),session)
        self.assertEqual(reopened.preparations.store.get('local-conversations',prep['id']),prep)
        self.assertEqual(reopened.conversation(cid)['preparations'][0]['generation']['run_id'],prep['run_id'])
        self.assertEqual(reopened.listing()['sessions'][0]['id'],session['id'])
        self.assertEqual(reopened._app(session).clock(),session['clock'])
        self.assertEqual(durable_rows(app),owned_before)
        self.assertEqual(durable_rows(root_app),root_before)

    def test_interruption_after_environment_commit_before_projection_does_not_lose_intent(self):
        with patch.object(self.w,'_project_session',side_effect=OSError('Projection unavailable')):
            with self.assertRaises(OSError):self.w.create('root','fixture')
        sid='workspace_'+digest({'request_id':'root'})[:24]
        original=self.w.authority.get(sid);self.assertIsNotNone(original);self.assertIsNone(original['run_id'])
        reopened=Workspace(self.root,real_clock=lambda:self.now+100)
        result=reopened.create('root','fixture')['session']
        self.assertEqual(result['clock'],original['clock']);self.assertEqual(result['created_at'],original['created_at'])
        self.assertIsNotNone(result['run_id'])
        app=reopened._app(result);before=durable_rows(app)
        self.assertEqual(reopened.create('root','fixture')['session'],result)
        self.assertEqual(durable_rows(app),before)

    def test_runtime_commit_before_environment_link_recovers_original_model_run(self):
        with patch.object(self.w.authority,'save',side_effect=OSError('Link write interrupted')):
            with self.assertRaises(OSError):self.w.create('model','model')
        sid='workspace_'+digest({'request_id':'model'})[:24]
        original=self.w.authority.get(sid);self.assertIsNone(original['run_id'])
        app=self.w._app(original);run=app.tasks.find_run(original['organization'],sid)
        self.assertIsNotNone(run)
        before_calls=app.calls.inspect(original['organization'],run)
        reopened=Workspace(self.root,real_clock=lambda:self.now)
        with patch('acquisition.bootstrap.Application._model_inputs',side_effect=AssertionError('Repeated generation input work')):
            result=reopened.prepare(sid)['session']
        self.assertEqual(result['run_id'],run)
        self.assertEqual(app.calls.inspect(original['organization'],run),before_calls)
        self.assertEqual(app.worker.drain(original['organization'],run_id=run),0)

    def test_preparation_commits_frozen_consent_before_plan_and_survives_restart(self):
        cid=self.w.create_conversation('chat','Recover intent')['id']
        self.w.message_conversation(cid,'message',0,FIXTURE_MESSAGE)
        with patch.object(self.w,'admit_preparation_plan',side_effect=OSError('Plan admission unavailable')):
            with self.assertRaises(OSError):self.w.start_preparation(cid,'original',1,False,False)
        saved=self.w.preparations.store.for_revision('local-conversations',cid,1)
        self.assertEqual(saved['status'],'admitting');self.assertFalse(saved['inputs']['allow_model_copy'])
        with self.w.control() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM preparations').fetchone()[0],0)
        reopened=Workspace(self.root,real_clock=lambda:self.now)
        with patch.object(reopened,'freeze_preparation_plan',side_effect=AssertionError('Rebuilt frozen context')):
            reopened.start_preparation(cid,'original',1,False,False)
            reopened.advance_preparations()
        actual=reopened.preparations.store.for_revision('local-conversations',cid,1)
        for key in ('inputs','planning_context','planning_context_id','plan_request_id','request_id'):
            self.assertEqual(actual[key],saved[key])
        self.assertIsNotNone(actual['run_id'])
        with self.assertRaises(Conflict):reopened.start_preparation(cid,'original',1,False,True)
        with self.assertRaises(NotFound):reopened.preparations.store.get('other-org',saved['id'])

    def test_preparation_projection_cannot_replace_intent_or_redirect_a_run(self):
        cid,saved=self.prepare();other=self.create()
        forged=saved|{'inputs':saved['inputs']|{'allow_model_copy':True},'run_id':other['run_id']}
        with self.w.control() as db:
            db.execute('INSERT INTO preparations VALUES(?,?,?,?,?,?,?)',('local-conversations',saved['id'],saved['request_id'],cid,1,0,canonical(forged)))
        self.assertEqual(self.w.preparations.store.get('local-conversations',saved['id']),saved)
        app=self.w._conversation_app()
        with app.tasks.database.transaction() as db:
            db.execute('UPDATE workflow_preparations SET progress=? WHERE organization=? AND id=?',
                       (canonical({'status':'planning','detail':None,'run_id':other['run_id']}),'local-conversations',saved['id']))
        with self.assertRaises(Conflict):self.w.preparations.store.get('local-conversations',saved['id'])

    def test_preparation_status_cannot_override_frozen_fields(self):
        _,saved=self.prepare();app=self.w._conversation_app()
        with self.assertRaises(NotFound):self.w.preparation_generation('other-org',saved)
        with app.tasks.database.transaction() as db:
            db.execute('UPDATE workflow_preparations SET progress=? WHERE organization=? AND id=?',
                (canonical({'status':'planning','detail':None,'run_id':saved['run_id'],'inputs':saved['inputs']}),'local-conversations',saved['id']))
        with self.assertRaises(Conflict):self.w.preparations.store.get('local-conversations',saved['id'])

    def test_environment_rejects_unverified_run_links_and_projection_clock_writes(self):
        session=self.create();other=self.create('other');app=self.app(session);before=durable_rows(app)
        with self.assertRaises(Conflict):self.w.authority.save(session|{'run_id':other['run_id']})
        with self.assertRaises(Conflict):self.w.authority.save(session|{'clock':session['clock']+1})
        with self.assertRaises(Conflict):self.w.authority.save(session|{'database_scope':'conversations'})
        self.assertEqual(durable_rows(app),before)
        with app.tasks.database.transaction() as db:
            with self.assertRaises(sqlite3.IntegrityError):db.execute('UPDATE campaign_environments SET clock=clock-1 WHERE organization=?',(session['organization'],))
            with self.assertRaises(sqlite3.IntegrityError):db.execute("UPDATE campaign_environments SET clock_mode='REAL' WHERE organization=?",(session['organization'],))

    def test_unlinked_environment_rejects_another_verified_operation_in_its_own_store(self):
        with patch.object(self.w,'_project_session',side_effect=OSError('projection interrupted')):
            with self.assertRaises(OSError):self.w.create('unlinked','fixture')
        sid='workspace_'+digest({'request_id':'unlinked'})[:24];session=self.w.authority.get(sid)
        app=self.w._app(session);other=app.start(session['organization'],'another-operation',size=20)
        before=durable_rows(app)
        with self.assertRaises(Conflict):self.w.authority.save(session|{'run_id':other})
        self.assertEqual(durable_rows(app),before)

    def test_missing_or_replaced_owned_store_is_not_recreated_or_trusted(self):
        session=self.create();path=self.app(session).tasks.database.path;backup=path.with_suffix('.saved')
        path.rename(backup)
        with self.assertRaises(Conflict):self.w.authority.get(session['id'])
        self.assertFalse(path.exists())
        alien=self.root/'alien.sqlite';build(alien)
        shutil.copyfile(alien,path)
        with self.assertRaisesRegex(Conflict,'different application store'):self.w.authority.get(session['id'])
        path.unlink();backup.rename(path)
        self.assertEqual(self.w.authority.get(session['id']),session)

    def test_clock_reads_do_not_take_a_nested_write_lock(self):
        session=self.create();app=self.app(session)
        with app.tasks.database.transaction() as db:
            db.execute('UPDATE campaign_environments SET epoch=epoch WHERE organization=?',(session['organization'],))
            self.assertEqual(self.w.authority.clock(session['id'],self.now),session['clock'])
            self.assertEqual(self.w._session(session['id']),session)

    def test_compatibility_session_read_does_not_migrate_under_an_active_domain_transaction(self):
        root=self.root/'compat-lock';compat=Workspace(root,real_clock=lambda:self.now)
        session=compat.create('legacy','fixture')['session'];app=compat._conversation_app()
        with app.tasks.database.transaction():
            self.assertEqual(compat._session(session['id'])['id'],session['id'])

    def seed_clock_source(self,session):
        # Independent committed-fact fixture for the clock boundary only. New
        # verified runs remain paused; this does not simulate their activation.
        app=self.app(session);org=session['organization'];start=self.now+86400
        with app.tasks.database.transaction() as db:
            db.execute('INSERT INTO review_cases VALUES(?,?,?,?)',(org,'case',session['run_id'],'subject'))
            db.execute('INSERT INTO review_subjects VALUES(?,?,?,?,?,?)',(org,'subject','case',1,'{}',self.now))
            db.execute('INSERT INTO review_decisions(organization,id,case_id,subject_id,payload) VALUES(?,?,?,?,?)',
                       (org,'approval','case','subject','{}'))
            db.execute('INSERT INTO simulated_agency_jobs VALUES(?,?,?,?,?,?)',(org,'case','job','approval','subject','{}'))
            db.execute('INSERT INTO learning_cohorts VALUES(?,?,?,?,?,?,?)',
                       (org,'cohort','job',canonical({'window_start':start,'window_end':start+30*86400}),self.now,self.now,'{}'))
        self.w.authority.save(session|{'case_id':'case','cohort_id':'cohort'})
        return app,start

    def test_command_identity_and_clock_advance_commit_together_and_replay_without_effect(self):
        session=self.create();app,start=self.seed_clock_source(session);org=session['organization']
        before=durable_rows(app)
        with app.tasks.database.transaction() as db:
            db.execute("CREATE TRIGGER fail_command BEFORE INSERT ON workspace_commands BEGIN SELECT RAISE(ABORT,'injected boundary'); END")
        with self.assertRaises(sqlite3.IntegrityError):self.w.authority.begin(session['id'],'observe',{'request_id':'observe'})
        self.assertEqual(durable_rows(app),before)
        with app.tasks.database.transaction() as db:db.execute('DROP TRIGGER fail_command')
        self.assertFalse(self.w.authority.begin(session['id'],'observe',{'request_id':'observe'}))
        self.assertEqual(self.w.authority.get(session['id'])['clock'],start+7*86400)
        admitted=durable_rows(app)
        with self.assertRaises(Conflict):self.w.authority.begin(session['id'],'finalize',{'request_id':'observe'})
        self.assertEqual(durable_rows(app),admitted)
        self.assertFalse(self.w.authority.begin(session['id'],'observe',{'request_id':'observe'}))
        self.assertEqual(durable_rows(app),admitted)
        self.w.authority.complete(session['id'],'observe');completed=durable_rows(app)
        self.assertTrue(self.w.authority.begin(session['id'],'observe',{'request_id':'observe'}))
        self.assertEqual(durable_rows(app),completed)
        app.reviews.store.register_actor(org,'local-operator',('operator',),False)
        disabled=durable_rows(app)
        with self.assertRaises(ActorUnavailable):self.w.authority.begin(session['id'],'finalize',{'request_id':'finalize'})
        self.assertEqual(durable_rows(app),disabled)

    def test_clock_requires_scoped_accepted_cohort_and_finite_window(self):
        session=self.create();app=self.app(session);before=durable_rows(app)
        with self.assertRaises(Conflict):self.w.authority.begin(session['id'],'observe',{'request_id':'missing'})
        self.assertEqual(durable_rows(app),before)
        self.seed_clock_source(session)
        with app.tasks.database.transaction() as db:
            db.execute('UPDATE learning_cohorts SET payload=? WHERE organization=?',(json.dumps({'window_start':float('inf'),'window_end':float('inf')}),session['organization']))
        invalid=durable_rows(app)
        with self.assertRaises(ValueError):self.w.authority.begin(session['id'],'observe',{'request_id':'invalid'})
        self.assertEqual(durable_rows(app),invalid)

    def test_manual_child_inherits_owned_store_parent_and_time_without_projection(self):
        parent=self.create();app,_=self.seed_clock_source(parent)
        self.w.authority.begin(parent['id'],'finalize',{'request_id':'mature'})
        parent=self.w.authority.get(parent['id'])
        with self.w.control() as db:db.execute('DELETE FROM sessions')
        child=self.w.create('child','fixture',parent['id'])['session']
        actual=self.w._session(child['id']);routed=self.w._app(actual)
        self.assertEqual(routed.tasks.database.path,app.tasks.database.path)
        self.assertEqual(actual['organization'],parent['organization'])
        self.assertEqual(actual['clock'],parent['clock'])
        state=routed.tasks.inspect(actual['organization'],actual['run_id'])
        self.assertEqual(state['admission']['status'],'paused')
        with app.tasks.database.connect() as db:
            owner=json.loads(db.execute('SELECT payload FROM execution_admissions WHERE organization=? AND run_id=?',
                                        (actual['organization'],actual['run_id'])).fetchone()[0])
        self.assertEqual(owner['parent_run_id'],parent['run_id'])

    def test_fresh_process_reads_owned_intents_after_projection_loss_without_execution(self):
        session=self.create();cid,prep=self.prepare();app=self.app(session);before=durable_rows(app)
        (self.root/'workspace.sqlite').unlink()
        code='''import json,sys
from acquisition.workspace import Workspace
w=Workspace(sys.argv[1],real_clock=lambda:1792972800.)
print(json.dumps({'session':w._session(sys.argv[2]),'preparation':w.preparations.store.get('local-conversations',sys.argv[3])}))'''
        result=subprocess.run([sys.executable,'-c',code,str(self.root),session['id'],prep['id']],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout),{'session':session,'preparation':prep})
        self.assertEqual(durable_rows(app),before)

    def test_owned_locator_rejects_a_store_symlink_outside_its_root(self):
        session=self.create();path=self.app(session).tasks.database.path;backup=path.with_suffix('.saved')
        path.rename(backup)
        with tempfile.TemporaryDirectory() as elsewhere:
            outside=Path(elsewhere)/'campaign.sqlite';shutil.copyfile(backup,outside);path.symlink_to(outside)
            with self.assertRaisesRegex(Conflict,'server-owned root'):self.w.authority.get(session['id'])
        path.unlink();backup.rename(path)

    def test_conversation_mapping_is_owned_and_replays_after_projection_loss(self):
        root=self.root/'conversation-source';compat=Workspace(root,real_clock=lambda:self.now)
        cid=compat.create_conversation('chat','Saved proposal')['id']
        compat.message_conversation(cid,'message',0,FIXTURE_MESSAGE)
        plan=compat.plan_conversation_fixture(cid,'plan',1)['current_plan']['result']
        compat._conversation_app().admissions.store.seal_legacy_writes()
        selected=Workspace(root,real_clock=lambda:self.now)
        draft=selected.draft_conversation(cid,'draft',1,plan['id'])
        sid=draft['session']['id'];session=selected._session(sid);app=selected._app(session)
        self.assertEqual(session['conversation_plan'],plan)
        self.assertEqual(session['database_scope'],'conversations')
        self.assertEqual(draft['tasks']['admission']['status'],'paused')
        before=durable_rows(app)
        (root/'workspace.sqlite').unlink()
        reopened=Workspace(root,real_clock=lambda:self.now)
        self.assertEqual(reopened._draft_session_id(cid,'draft'),sid)
        self.assertEqual(reopened.draft_conversation(cid,'draft',1,plan['id'])['session'],draft['session'])
        self.assertEqual(durable_rows(app),before)
        with self.assertRaises(Conflict):reopened.draft_conversation(cid,'draft',2,plan['id'])
        self.assertEqual(durable_rows(app),before)

    def test_preparation_intent_is_sql_immutable_and_rejects_extra_admission_fields(self):
        _,saved=self.prepare();app=self.w._conversation_app();before=durable_rows(app)
        with app.tasks.database.transaction() as db:
            with self.assertRaises(sqlite3.IntegrityError):db.execute("UPDATE workflow_preparations SET intent='{}' WHERE organization=?",('local-conversations',))
        from acquisition.conversations import preparation_record
        value={k:v for k,v in saved.items() if k not in {'epoch','request_id'}}
        value|={'run_id':None,'status':'admitting','detail':None,'unexpected':'not a supported authority input'}
        with self.assertRaises(ValueError):preparation_record('local-conversations','other',value)
        self.assertEqual(durable_rows(app),before)

    def test_new_verified_work_does_not_promote_legacy_projection_intent(self):
        root=self.root/'compat';legacy=Workspace(root,real_clock=lambda:self.now)
        session=legacy.create('legacy','fixture')['session']
        legacy._conversation_app().admissions.store.seal_legacy_writes()
        selected=Workspace(root,real_clock=lambda:self.now)
        self.assertIsNone(selected.authority.get(session['id']))
        shown=selected.view(session['id'])['session']
        self.assertEqual(shown,session|{'clock':self.now})
        owned=selected.create('owned','fixture')['session']
        with selected.control() as db:db.execute("INSERT INTO sessions VALUES('broken','unused','{}')")
        self.assertEqual({s['id'] for s in selected.listing()['sessions']},{session['id'],owned['id']})
        with self.assertRaisesRegex(Conflict,'migration'):selected.create('legacy','fixture')
        with self.assertRaises(Conflict):selected.action(session['id'],'approve',{'request_id':'new','subject_id':selected.view(session['id'])['review']['subject']['id'],'reason':'Cannot use projected clock as authority.'})

    def test_non_finite_environment_time_fails_before_persistence(self):
        session=self.create();base=dict(session);base|={'run_id':None,'case_id':None,'cohort_id':None}
        for value in (float('inf'),float('nan'),-1,10**1000,True):
            with self.subTest(value=str(value)[:12]),self.assertRaises(ValueError):EnvironmentIntent.freeze(base|{'clock':value})
        with self.assertRaises(ValueError):self.w.authority.clock(session['id'],float('inf'))


class FrozenFollowupLinkPolicyTests(unittest.TestCase):
    """Actual frozen follow-up contracts, without activating verified execution."""
    setUp=followups.FollowupTests.setUp
    approve=followups.FollowupTests.approve
    accept=followups.FollowupTests.accept

    def check_mode(self,model):
        from acquisition.campaigns import brief_from
        from acquisition.workflows.workspace_state import validate_environment_run
        p=followups.FollowupTests.finalized(self)
        parent=self.w._session(self.sid);app=self.w._app(parent);app.admissions.store.seal_legacy_writes()
        sid='workspace_'+digest({'followup':p['id']})[:24]
        brief=brief_from(p['brief']|{'campaign_id':sid,'followup_id':p['id']})
        if model:
            app=build(app.tasks.database.path,clock=app.clock,model_config=ModelConfig(**p['model_config']))
            run=app.start_model(self.scope,sid,snapshot_override=app.audiences.get(self.scope,p['snapshot_id']),
                                brief_override=brief,contexts_override=p['contexts'])
        else:run=app.start_followup(self.scope,sid,p['snapshot_id'],brief)
        admitted=app.admissions.store.get_request(self.scope,sid)
        with app.tasks.database.connect() as db:
            row=db.execute('SELECT inputs,source FROM admission_requests WHERE organization=? AND request_id=?',(self.scope,sid)).fetchone()
        session=parent|{'id':sid,'mode':'model' if model else 'fixture','parent_id':self.sid,'followup_id':p['id']}
        creation={'kind':'followup','inputs':canonical({'parent':self.sid,'proposal':p['id'],'mode':session['mode'],'allow_model_copy':model})}
        before=durable_rows(app)
        def no_synthetic_override(*args):raise AssertionError('Follow-up must retain its frozen proposal audience')
        validate_environment_run(session,creation,admitted,json.loads(row['inputs']),json.loads(row['source']),parent,
                                 synthetic_snapshot_id=no_synthetic_override)
        with self.assertRaises(Conflict):
            validate_environment_run(session|{'followup_id':'another-source'},creation,admitted,json.loads(row['inputs']),json.loads(row['source']),parent,
                                     synthetic_snapshot_id=no_synthetic_override)
        self.assertEqual(durable_rows(app),before)
        self.assertEqual(app.worker.drain(self.scope,run_id=run),0)

    def test_frozen_fixture_followup_matches_its_original_command(self):self.check_mode(False)
    def test_frozen_model_followup_matches_its_original_command(self):self.check_mode(True)
