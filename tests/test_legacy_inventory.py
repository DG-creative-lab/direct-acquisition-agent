"""Migration planning observes history without granting or repairing authority."""
import fcntl
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timezone

from acquisition.bootstrap import build, build_legacy_migration_inventory
from acquisition.contracts import Conflict, canonical, digest
from acquisition.conversations import FIXTURE_MESSAGE
from acquisition.conversations.legacy_migration import classify_inventory
from acquisition.adapters.sqlite.database import Database
from acquisition.adapters.sqlite.legacy_inventory import SqliteLegacyInventory
from acquisition.reasoning import ModelConfig, ModelError
from acquisition.workspace import Workspace
from test_conversations import PlannerModel


def rows(path):
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as db:
        tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        return (db.execute('PRAGMA user_version').fetchone()[0],
                {t:sorted(db.execute('SELECT * FROM "'+t.replace('"','""')+'"').fetchall(),key=repr) for t in tables})


class LegacyInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.now=1792972800.
        self.w=Workspace(self.root,real_clock=lambda:self.now)

    def inspect(self):return build_legacy_migration_inventory(self.root).inspect()

    def facts(self):
        return {str(p.relative_to(self.root)):rows(p) for p in self.root.rglob('*.sqlite')}

    def byte_facts(self):
        return {str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*')
                if p.is_file() and p.name != 'server.lock' and not p.name.endswith('-shm')}

    def cli(self,*args,code=None):
        command=[sys.executable,'-c',code,str(self.root)] if code else [sys.executable,'-m','acquisition.legacy_migration','--root',str(self.root),*args]
        return subprocess.run(command,capture_output=True,text=True,timeout=25,
                              env=dict(os.environ,PYTHONPATH=str(Path('src').resolve())))

    def planner(self,key='one',model=None):
        cid=self.w.create_conversation(key,'Historical brief')['id']
        self.w.message_conversation(cid,'message',0,FIXTURE_MESSAGE)
        if model is None:
            plan=self.w.plan_conversation_fixture(cid,'plan',1)['current_plan']
            app=self.w._conversation_app()
        else:
            app=build(self.root/'conversations.sqlite',clock=lambda:self.now,gateway=model,
                      model_config=ModelConfig('test/planner',max_calls=10,force_tool_choice=True))
            app.conversations.plan('local-conversations',cid,'plan',1)
            with app.tasks.database.connect() as db:
                native=json.loads(db.execute('SELECT payload FROM conversation_plans WHERE conversation_id=?',(cid,)).fetchone()[0])
            run=app.tasks.find_run('local-conversations',native['run_request_id'])
            app.worker.drain('local-conversations',run_id=run)
            return cid,app,run
        with app.tasks.database.connect() as db:
            native=json.loads(db.execute('SELECT payload FROM conversation_plans WHERE conversation_id=?',(cid,)).fetchone()[0])
        return cid,app,app.tasks.find_run('local-conversations',native['run_request_id'])

    @staticmethod
    def run_record(report,run):return next(r for r in report['records'] if r['kind']=='run' and r['key']==run)

    def test_native_plan_evidence_is_stable_read_only_and_never_executable(self):
        cid,app,run=self.planner();before=self.facts();binary=self.byte_facts()
        with patch.object(Database,'transaction',side_effect=AssertionError('write')), \
             patch('acquisition.bootstrap.agent_catalogue',side_effect=AssertionError('current guidance')), \
             patch('acquisition.workspace.Workspace',side_effect=AssertionError('workspace construction')):
            report=self.inspect();self.assertEqual(report,self.inspect())
        item=self.run_record(report,run)
        self.assertEqual(item['classification'],'supported',item)
        self.assertEqual(item['owners'],[['local-conversations','conversation',cid,1]])
        self.assertFalse(item['executable']);self.assertEqual(item['preserve']['recorded_calls'],0)
        self.assertTrue(any(e['table']=='conversation_plans' for e in item['evidence']))
        for key in ('apply_available','execution_activation','legacy_certification','migration_ready','billing_verified','backup_completeness_verified'):
            self.assertIs(report[key],False)
        self.assertEqual(report['schema'],'legacy-migration-plan/v1')
        self.assertEqual(self.facts(),before);self.assertEqual(self.byte_facts(),binary)

    def test_verified_environment_and_preparation_remain_paused_without_projection_authority(self):
        self.w=Workspace(self.root,real_clock=lambda:self.now,verified_admissions=True)
        session=self.w._session(self.w.create('owned','fixture')['session']['id']);app=self.w._app(session)
        cid=self.w.create_conversation('chat','Owned brief')['id']
        self.w.message_conversation(cid,'message',0,FIXTURE_MESSAGE)
        self.w.start_preparation(cid,'prepare',1,True,False)
        with self.w.control() as db:
            db.execute('UPDATE sessions SET payload=? WHERE id=?',('{bad projection',session['id']))
        before=self.facts();report=self.inspect()
        item=self.run_record(report,session['run_id'])
        self.assertEqual(item['classification'],'supported',item)
        self.assertEqual(item['format'],'verified')
        projection=next(r for r in report['records'] if r['kind']=='session')
        self.assertEqual(projection['classification'],'supported',projection)
        self.assertEqual(projection['proposed_step'],'rebuild_disposable_projection')
        self.assertTrue(any(r['kind']=='preparation' and r['classification']=='supported' for r in report['records']))
        self.assertEqual(app.worker.drain(session['organization'],run_id=session['run_id']),0)
        self.assertEqual(self.facts(),before)

    def owned(self,key):
        self.w=Workspace(self.root,real_clock=lambda:self.now,verified_admissions=True)
        session=self.w._session(self.w.create(key,'fixture')['session']['id'])
        return session,self.w._app(session)

    def assert_environment_conflict_is_read_only(self,session):
        with self.assertRaises((Conflict,ValueError)):
            self.w.authority.get(session['id'])
        before=self.facts();binary=self.byte_facts()
        with patch.object(Database,'transaction',side_effect=AssertionError('inspection write')), \
             patch('acquisition.bootstrap.agent_catalogue',side_effect=AssertionError('current guidance')), \
             patch('acquisition.workspace.OpenRouter',side_effect=AssertionError('provider')):
            report=self.inspect()
        for kind in ('environment','session'):
            item=next(r for r in report['records'] if r['kind']==kind and r['key']==session['id'])
            self.assertEqual(item['classification'],'conflicting',item)
            self.assertEqual(item['proposed_step'],'preserve_and_reconcile')
            self.assertFalse(item['executable'])
        self.assertEqual(self.facts(),before);self.assertEqual(self.byte_facts(),binary)

    def seed_owned_case_and_cohort(self,session,app):
        # Committed-fact fixture only. These paused runs acquire no approval authority.
        org=session['organization']
        with app.tasks.database.transaction() as db:
            db.execute('INSERT INTO review_cases VALUES(?,?,?,?)',(org,'case',session['run_id'],'subject'))
            db.execute('INSERT INTO review_subjects VALUES(?,?,?,?,?,?)',(org,'subject','case',1,'{}',self.now))
            db.execute('INSERT INTO review_decisions(organization,id,case_id,subject_id,payload) VALUES(?,?,?,?,?)',
                       (org,'approval','case','subject','{}'))
            db.execute('INSERT INTO simulated_agency_jobs VALUES(?,?,?,?,?,?)',(org,'case','job','approval','subject','{}'))
            db.execute('INSERT INTO learning_cohorts VALUES(?,?,?,?,?,?,?)',
                       (org,'cohort','job','{}',self.now,self.now,'{}'))
        return self.w.authority.save(session|{'case_id':'case','cohort_id':'cohort'})

    def test_inventory_rejects_missing_foreign_and_wrong_run_review_case_links(self):
        healthy,_=self.owned('healthy')
        for variant in ('missing','foreign','wrong-run'):
            with self.subTest(variant=variant):
                session,app=self.owned('bad-case-'+variant);org=session['organization']
                other=app.start(org,'other',size=20)
                with app.tasks.database.transaction() as db:
                    if variant!='missing':
                        db.execute('INSERT INTO review_cases VALUES(?,?,?,?)',
                                   ('foreign-org' if variant=='foreign' else org,'bad-case',other,'subject'))
                    db.execute('UPDATE campaign_environments SET case_id=? WHERE organization=? AND id=?',('bad-case',org,session['id']))
                self.assert_environment_conflict_is_read_only(session)
        item=next(r for r in self.inspect()['records'] if r['kind']=='environment' and r['key']==healthy['id'])
        self.assertEqual(item['classification'],'supported')

    def test_inventory_rejects_missing_and_wrong_case_learning_cohort_links(self):
        for variant in ('missing','wrong-case'):
            with self.subTest(variant=variant):
                session,app=self.owned('bad-cohort-'+variant);org=session['organization']
                session=self.seed_owned_case_and_cohort(session,app)
                self.assertEqual(next(r for r in self.inspect()['records'] if r['kind']=='environment' and r['key']==session['id'])['classification'],'supported')
                with app.tasks.database.transaction() as db:
                    if variant=='missing':
                        db.execute('UPDATE campaign_environments SET cohort_id=? WHERE organization=? AND id=?',('missing',org,session['id']))
                    else:
                        db.execute('UPDATE simulated_agency_jobs SET case_id=? WHERE organization=?',('another-case',org))
                self.assert_environment_conflict_is_read_only(session)

    def test_inventory_rejects_clock_rollback_and_incompatible_clock_mode(self):
        for variant in ('rollback','mode'):
            with self.subTest(variant=variant):
                session,app=self.owned('bad-clock-'+variant)
                with app.tasks.database.transaction() as db:
                    db.execute('DROP TRIGGER environment_time_monotonic')
                    db.execute('UPDATE campaign_environments SET clock=?,clock_mode=? WHERE organization=? AND id=?',
                               (session['clock']-1 if variant=='rollback' else session['clock'],
                                'REAL' if variant=='mode' else 'SIMULATED',session['organization'],session['id']))
                self.assert_environment_conflict_is_read_only(session)

    def test_inventory_rejects_valid_run_with_same_key_but_different_mode_or_source(self):
        for variant in ('mode','source'):
            with self.subTest(variant=variant):
                self.w=Workspace(self.root,real_clock=lambda:self.now,verified_admissions=True)
                with patch.object(self.w,'_project_session',side_effect=OSError('interrupted creation')),self.assertRaises(OSError):
                    self.w.create('wrong-run-'+variant,'fixture')
                sid='workspace_'+digest({'request_id':'wrong-run-'+variant})[:24]
                session=self.w.authority.get(sid)
                path=self.w._app(session).tasks.database.path
                app=build(path,clock=lambda:self.now,model_config=ModelConfig('openai/gpt-oss-120b',max_calls=10,force_tool_choice=True))
                day=datetime.fromtimestamp(session['clock'],timezone.utc).date().isoformat()
                run=(app.start_model if variant=='mode' else app.start)(session['organization'],sid,size=1000 if variant=='mode' else 40,as_of=day)
                self.assertTrue(app.tasks.inspect(session['organization'],run)['admission']['binding_valid'])
                with app.tasks.database.transaction() as db:
                    db.execute('UPDATE campaign_environments SET run_id=? WHERE organization=? AND id=?',(run,session['organization'],sid))
                with self.w.control() as db:
                    db.execute('INSERT INTO sessions VALUES(?,?,?)',(sid,'projection',canonical(session|{'run_id':run})))
                self.assert_environment_conflict_is_read_only(session)

    def test_legacy_preparation_rejects_nonboolean_choices_without_exporting_their_values(self):
        cid=self.w.create_conversation('choices','Old choices')['id']
        self.w.message_conversation(cid,'message',0,FIXTURE_MESSAGE)
        self.w.start_preparation(cid,'prepare',1,True,False)
        with self.w.control() as db:original=json.loads(db.execute('SELECT payload FROM preparations').fetchone()[0])
        marker='private-credential-shaped-value'
        for key in ('fixture','allow_model_copy','use_audience_catalogue'):
            for value in (marker,{'private':marker},[marker],1,None):
                with self.subTest(key=key,value=value):
                    payload=original|{'inputs':original['inputs']|{key:value}}
                    with self.w.control() as db:db.execute('UPDATE preparations SET payload=?',(canonical(payload),))
                    before=self.facts();binary=self.byte_facts();report=self.inspect()
                    item=next(r for r in report['records'] if r['kind']=='preparation')
                    self.assertEqual(item['classification'],'conflicting',item)
                    self.assertNotIn('generation_choices_observed',item['preserve'])
                    self.assertNotIn(marker,json.dumps(report))
                    self.assertEqual(self.facts(),before);self.assertEqual(self.byte_facts(),binary)
                    if key=='use_audience_catalogue' and value==marker:
                        result=self.cli('inspect');self.assertEqual(result.returncode,0,result.stderr)
                        self.assertNotIn(marker,result.stdout+result.stderr)

    def test_legacy_preparation_preserves_valid_optional_boolean_choices(self):
        cid=self.w.create_conversation('boolean-choices','Old choices')['id']
        self.w.message_conversation(cid,'message',0,FIXTURE_MESSAGE)
        self.w.start_preparation(cid,'prepare',1,True,False)
        with self.w.control() as db:original=json.loads(db.execute('SELECT payload FROM preparations').fetchone()[0])
        for value in (True,False):
            with self.subTest(value=value):
                payload=original|{'inputs':original['inputs']|{'use_audience_catalogue':value}}
                with self.w.control() as db:db.execute('UPDATE preparations SET payload=?',(canonical(payload),))
                before=self.facts();item=next(r for r in self.inspect()['records'] if r['kind']=='preparation')
                self.assertEqual(item['classification'],'incomplete',item)
                self.assertIs(item['preserve']['generation_choices_observed']['use_audience_catalogue'],value)
                self.assertEqual(self.facts(),before)

    def legacy_session(self,run=None):
        return {'id':'legacy-session','organization':'local-conversations',
                'mode':'fixture','database_scope':'conversations','clock':self.now,
                'clock_mode':'SIMULATED','run_id':run,'case_id':None,'cohort_id':None,'parent_id':None}

    def put_legacy_session(self,payload,key='legacy-session'):
        with self.w.control() as db:
            db.execute('DELETE FROM sessions')
            db.execute('INSERT INTO sessions VALUES(?,?,?)',(key,'original-fingerprint',json.dumps(payload)))

    def assert_legacy_session_redacted(self,marker,healthy_run):
        before=self.facts();binary=self.byte_facts();report=self.inspect()
        session=next(r for r in report['records'] if r['kind']=='session')
        self.assertEqual(session['classification'],'conflicting')
        self.assertEqual(session['preserve'],{})
        self.assertFalse(session['executable'])
        self.assertTrue(session['evidence'][0]['fingerprint'])
        self.assertNotIn(marker,json.dumps(report))
        self.assertEqual(self.run_record(report,healthy_run)['classification'],'supported')
        self.assertEqual(self.facts(),before);self.assertEqual(self.byte_facts(),binary)

    def test_legacy_session_clock_modes_are_validated_before_report_or_cli_export(self):
        cid,app,run=self.planner();marker='sk-or-v1-private-test-value'
        for mode in (marker,{'private':marker},[marker],None,False,1):
            with self.subTest(mode=mode):
                self.put_legacy_session(self.legacy_session(run)|{'clock_mode':mode})
                self.assert_legacy_session_redacted(marker,run)
                if mode==marker:
                    result=self.cli('inspect');self.assertEqual(result.returncode,0,result.stderr)
                    self.assertNotIn(marker,result.stdout+result.stderr)
        self.put_legacy_session(self.legacy_session(run)|{'clock_mode':'REAL'})
        self.assert_legacy_session_redacted(marker,run)

    def test_legacy_session_identifiers_are_validated_before_any_metadata_export(self):
        cid,app,run=self.planner();marker='sk-or-v1-private-test-value'
        for field in ('id','organization','run_id','case_id','cohort_id','parent_id'):
            for value in (marker*8,{'private':marker},[marker],1):
                with self.subTest(field=field,value=value):
                    payload=self.legacy_session(run)|{field:value}
                    key=value if field=='id' and isinstance(value,str) else 'legacy-session'
                    self.put_legacy_session(payload,key)
                    self.assert_legacy_session_redacted(marker,run)
                    if field=='id' and isinstance(value,str):
                        result=self.cli('inspect');self.assertEqual(result.returncode,0,result.stderr)
                        self.assertNotIn(marker,result.stdout+result.stderr)

    def test_malformed_legacy_conversation_hints_cannot_taint_the_original_run(self):
        cid,app,run=self.planner();marker='sk-or-v1-private-test-value'
        plan={'id':'brief-original','conversation_id':cid,'revision':1}
        for changed in ({'id':marker*8},{'conversation_id':marker*8},
                        {'conversation_id':{'private':marker}},{'revision':marker},
                        {'revision':True},{'revision':0}):
            with self.subTest(changed=changed):
                self.put_legacy_session(self.legacy_session(run)|{'conversation_plan':plan|changed})
                self.assert_legacy_session_redacted(marker,run)
        self.put_legacy_session(self.legacy_session(run)|{'conversation_plan':marker})
        self.assert_legacy_session_redacted(marker,run)

    def test_valid_legacy_session_metadata_and_missing_clock_mode_remain_inspectable(self):
        cid,app,run=self.planner()
        for mode,clock_mode in (('fixture','SIMULATED'),('model','REAL'),('model','SIMULATED'),('fixture',None)):
            with self.subTest(mode=mode,clock_mode=clock_mode):
                payload=self.legacy_session(run)|{'mode':mode,'clock_mode':clock_mode,
                    'id':'workspace_'+'1'*24,'case_id':'case_'+digest('original-case'),
                    'cohort_id':'cohort_'+digest('original-cohort'),'parent_id':'workspace_'+'2'*24}
                if clock_mode is None:payload.pop('clock_mode')
                self.put_legacy_session(payload,payload['id']);before=self.facts();report=self.inspect()
                session=next(r for r in report['records'] if r['kind']=='session')
                self.assertEqual(session['classification'],'incomplete',session)
                self.assertFalse(session['executable'])
                expected={k:payload[k] for k in ('mode','clock','clock_mode','run_id','case_id','cohort_id','parent_id') if k in payload}
                self.assertEqual(session['preserve'],expected)
                self.assertEqual(self.facts(),before)

    def test_realistic_credential_length_identifiers_are_opaque_in_report_and_cli(self):
        from acquisition.conversations import identity
        cid,app,run=self.planner();marker='sk-or-v1-'+'a'*64
        self.assertLess(len(marker),120)
        self.assertEqual(identity(marker),marker)
        for field in ('id','organization','run_id','case_id','cohort_id','parent_id'):
            with self.subTest(field=field):
                payload=self.legacy_session(run)|{field:marker}
                self.put_legacy_session(payload,marker if field=='id' else payload['id'])
                before=self.facts();binary=self.byte_facts();report=self.inspect()
                session=next(r for r in report['records'] if r['kind']=='session')
                self.assertEqual(session['classification'],'incomplete')
                self.assertNotIn(marker,json.dumps(report))
                public=session['key'] if field=='id' else session['organization'] if field=='organization' else session['preserve'][field]
                self.assertTrue(public.startswith('opaque_'))
                self.assertIn('unverified_legacy_reference:'+field,session['reasons'])
                self.assertTrue(all(r['executable'] is False for r in report['records']))
                result=self.cli('inspect');self.assertEqual(result.returncode,0,result.stderr)
                self.assertNotIn(marker,result.stdout+result.stderr)
                self.assertEqual(self.facts(),before);self.assertEqual(self.byte_facts(),binary)
        native=app.conversations.view('local-conversations',cid)['current_plan']['result']
        for field in ('id','conversation_id'):
            with self.subTest(hint=field):
                self.put_legacy_session(self.legacy_session(run)|{'conversation_plan':native|{field:marker}})
                before=self.facts();report=self.inspect()
                self.assertNotIn(marker,json.dumps(report))
                self.assertEqual(self.run_record(report,run)['classification'],'supported')
                session=next(r for r in report['records'] if r['kind']=='session')
                self.assertIn('unverified_legacy_conversation_hint',session['reasons'])
                result=self.cli('inspect');self.assertEqual(result.returncode,0,result.stderr)
                self.assertNotIn(marker,result.stdout+result.stderr)
                self.assertEqual(self.facts(),before)

    def test_non_native_legacy_aliases_remain_inspectable_as_fingerprint_references(self):
        cid,app,run=self.planner()
        payload=self.legacy_session(run)|{'case_id':'case-original','cohort_id':'cohort-original','parent_id':'legacy-parent'}
        self.put_legacy_session(payload);before=self.facts();report=self.inspect()
        session=next(r for r in report['records'] if r['kind']=='session')
        self.assertEqual(session['classification'],'incomplete')
        self.assertEqual(session['preserve']['run_id'],run)
        self.assertEqual(session['preserve']['clock_mode'],'SIMULATED')
        for field in ('case_id','cohort_id','parent_id'):
            self.assertTrue(session['preserve'][field].startswith('opaque_'))
            self.assertNotIn(payload[field],json.dumps(report))
        self.assertTrue(session['key'].startswith('opaque_'))
        self.assertEqual(self.facts(),before)

    def test_unowned_legacy_run_and_historical_independence_never_prove_standalone(self):
        app=build(self.root/'conversations.sqlite',clock=lambda:self.now)
        run=app.start('old-org','unbound',size=20)
        receipt={'kind':'independent_execution_resolution','run_id':run}
        with app.tasks.database.transaction() as db:
            db.execute('INSERT INTO execution_commands VALUES(?,?,?,?)',('old-org','independent:'+run,canonical(receipt),canonical(receipt)))
        before=self.facts();item=self.run_record(self.inspect(),run)
        self.assertEqual(item['classification'],'incomplete',item)
        self.assertEqual(item['owners'],[])
        self.assertIn('positive_ownership_evidence_is_missing',item['reasons'])
        self.assertIsNone(item['preserve']['remaining_allowance']);self.assertFalse(item['preserve']['billing_verified'])
        self.assertTrue(item['preserve']['historical_independence_receipt'])
        self.assertEqual(self.facts(),before)

    def test_account_index_can_expose_conflicts_but_cannot_supply_missing_ownership(self):
        cid,app,run=self.planner()
        other=app.conversations.create('local-conversations','other')['id']
        app.execution.view('local-conversations',other)
        with app.tasks.database.transaction() as db:
            db.execute('UPDATE execution_runs SET conversation_id=? WHERE organization=? AND run_id=?',(other,'local-conversations',run))
        item=self.run_record(self.inspect(),run)
        self.assertEqual(item['classification'],'conflicting',item)
        self.assertIn('recorded_account_differs_from_source',item['reasons'])
        standalone=app.start('old-org','unowned',size=20)
        with app.tasks.database.transaction() as db:
            db.execute('INSERT INTO execution_runs VALUES(?,?,?,?,?)',('old-org',standalone,'local-conversations',cid,1))
        self.assertEqual(self.run_record(self.inspect(),standalone)['classification'],'incomplete')

    def test_provider_unknown_and_interrupted_reservations_are_uncertain_without_retry(self):
        model=PlannerModel(ModelError('provider_request_failed'))
        cid,app,run=self.planner(model=model)
        before=self.facts();report=self.inspect();item=self.run_record(report,run)
        self.assertEqual(item['classification'],'uncertain',item)
        self.assertIn('provider_outcome_requires_reconciliation',item['reasons'])
        self.assertEqual(item['preserve']['recorded_calls'],1)
        self.assertEqual(len(model.requests),1);self.assertEqual(self.facts(),before)
        with app.tasks.database.transaction() as db:
            db.execute("UPDATE model_calls SET status='reserved',error=NULL WHERE organization=? AND run_id=?",('local-conversations',run))
        self.assertEqual(self.run_record(self.inspect(),run)['classification'],'uncertain')

    def test_definitive_provider_rejection_does_not_claim_unknown_billing_or_revalidate_guidance(self):
        cid,app,run=self.planner(model=PlannerModel(ModelError('provider_http_401')))
        item=self.run_record(self.inspect(),run)
        self.assertEqual(item['classification'],'supported',item)
        self.assertFalse(item['preserve']['billing_verified'])
        self.assertIsNone(item['preserve']['remaining_allowance'])

    def test_recorded_model_result_retains_frozen_settings_without_provider_bodies(self):
        model=PlannerModel();cid,app,run=self.planner(model=model)
        item=self.run_record(self.inspect(),run)
        self.assertEqual(item['classification'],'supported',item)
        self.assertEqual(item['preserve']['provider_observations'][0]['state'],'recorded')
        self.assertTrue(item['preserve']['model_config_fingerprint'])
        self.assertNotIn('response',json.dumps(item));self.assertEqual(len(model.requests),1)

    def test_partial_native_admission_and_staged_new_request_are_inspected_without_resuming(self):
        cid=self.w.create_conversation('partial','Partial')['id'];app=self.w._conversation_app()
        self.w.message_conversation(cid,'message',0,FIXTURE_MESSAGE)
        with patch.object(app.conversations.tasks,'create',side_effect=OSError('interrupted runtime write')),self.assertRaises(OSError):
            app.conversations.plan_fixture('local-conversations',cid,'partial-plan',1)
        # A separate staged verified request has no committed runtime either.
        other=app.conversations.create('local-conversations','staged')['id']
        app.conversations.message('local-conversations',other,'message',0,FIXTURE_MESSAGE)
        context=app.conversations.planning_context('local-conversations',other,'staged-plan',1,True)
        app.admissions.store.request_planning('local-conversations',other,'staged-plan',1,context,fixture=True,allow_model=False)
        before=self.facts();report=self.inspect()
        pending=[r for r in report['records'] if r['kind']=='pending_admission']
        self.assertEqual(len(pending),2,pending)
        self.assertEqual({r['format'] for r in pending},{'legacy','verified'})
        self.assertTrue(all(r['classification']=='incomplete' and not r['executable'] for r in pending))
        self.assertEqual(self.facts(),before)

    def test_preparation_request_ids_are_opaque_in_both_journals(self):
        for verified in (False, True):
            with self.subTest(verified=verified):
                marker = 'sk-or-v1-' + ('a' if verified else 'b') * 64
                if verified:
                    self.w = Workspace(self.root, real_clock=lambda: self.now, verified_admissions=True)
                cid = self.w.create_conversation('prepare-'+str(verified), 'Preparation')['id']
                self.w.message_conversation(cid, 'message', 0, FIXTURE_MESSAGE)
                self.w.start_preparation(cid, marker, 1, True, False)
                before = self.facts()
                result = self.cli('inspect')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn(marker, result.stdout + result.stderr)
                report = json.loads(result.stdout)
                preparations = [r for r in report['records'] if r['kind']=='preparation']
                self.assertTrue(any(r['format']==('verified' if verified else 'legacy')
                                    and r['preserve']['request_id'].startswith('opaque_') for r in preparations))
                self.assertEqual(self.facts(), before)

    def test_request_ids_stay_opaque_in_runtime_and_admission_evidence(self):
        org = 'local-conversations'
        markers = ['sk-or-v1-' + digit * 64 for digit in 'cdef']
        completed_key, pending_key, staged_key, runtime_key = markers
        cid = self.w.create_conversation('completed', 'Completed plan')['id']
        self.w.message_conversation(cid, 'message', 0, FIXTURE_MESSAGE)
        self.w.plan_conversation_fixture(cid, completed_key, 1)
        pending = self.w.create_conversation('pending', 'Pending plan')['id']
        self.w.message_conversation(pending, 'message', 0, FIXTURE_MESSAGE)
        app = self.w._conversation_app()
        with patch.object(app.conversations.tasks, 'create', side_effect=OSError('interrupted runtime write')):
            with self.assertRaises(OSError):
                app.conversations.plan_fixture(org, pending, pending_key, 1)
        staged = app.conversations.create(org, 'staged')['id']
        app.conversations.message(org, staged, 'message', 0, FIXTURE_MESSAGE)
        context = app.conversations.planning_context(org, staged, staged_key, 1, True)
        app.admissions.store.request_planning(org, staged, staged_key, 1, context, fixture=True, allow_model=False)
        run = app.start(org, runtime_key, size=20)
        before = self.facts()
        report = self.inspect()
        for marker in markers:
            self.assertNotIn(marker, json.dumps(report))
        item = self.run_record(report, run)
        self.assertTrue(item['native_request_id'].startswith('opaque_'))
        self.assertEqual(sum(r['kind'] == 'pending_admission' for r in report['records']), 2)
        self.assertFalse(item['executable'])
        self.assertEqual(self.facts(), before)

    def test_verified_standalone_scope_does_not_expose_caller_campaign_identity(self):
        marker = 'sk-or-v1-' + '7' * 64
        app = build(self.root/'conversations.sqlite', clock=lambda: self.now, verified_admissions=True)
        run = app.start('local-conversations', 'ordinary-request', campaign_id=marker, size=20)
        before = self.facts()
        report = self.inspect()
        self.assertNotIn(marker, json.dumps(report))
        item = self.run_record(report, run)
        self.assertEqual(item['classification'], 'supported')
        org, kind, scope, revision = item['owners'][0]
        self.assertEqual((org, kind, revision), ('local-conversations', 'standalone', None))
        self.assertTrue(scope.startswith('opaque_'))
        self.assertFalse(item['executable'])
        self.assertEqual(self.facts(), before)

    def test_caller_organizations_are_opaque_across_records_evidence_and_inherited_owners(self):
        organizations = ['sk-or-v1-' + digit * 64 for digit in 'ab']
        app = build(self.root/'conversations.sqlite', clock=lambda: self.now, verified_admissions=True)
        first, second = [app.start(org, 'shared-key', size=20) for org in organizations]
        child = app.start(organizations[0], 'child-key', size=20, parent_run_id=first)
        before = self.facts()
        result = self.cli('inspect')
        self.assertEqual(result.returncode, 0, result.stderr)
        for organization in organizations:
            self.assertNotIn(organization, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        parent, other, descendant = [self.run_record(report, run) for run in (first, second, child)]
        self.assertNotEqual(parent['organization'], other['organization'])
        for item in (parent, other, descendant):
            self.assertEqual(item['classification'], 'supported')
            self.assertRegex(item['organization'], r'^opaque_[0-9a-f]{64}$')
            self.assertEqual(item['owners'][0][0], item['organization'])
            self.assertTrue(item['evidence'])
            self.assertTrue(all(ref['organization'] == item['organization'] for ref in item['evidence']))
        self.assertIn(parent['id'], descendant['dependencies'])
        self.assertEqual(descendant['owners'], parent['owners'])
        self.assertEqual(report, self.inspect())
        self.assertEqual(self.facts(), before)

    def test_inventory_export_selects_typed_metadata_without_forwarding_source_fields(self):
        from acquisition.adapters.sqlite.legacy_sources import record
        marker = 'sk-or-v1-' + 'e' * 64
        source = record('conversations.sqlite', 'run', 'local-conversations', 'run_' + 'a' * 32)
        source['private_note'] = marker
        source['state'] = marker
        source['preserve'] = {'new_source_field': marker, 'recorded_calls': 2,
                              'recorded_execution_account': {'policy': marker, 'call_limit': 3, 'extra': marker}}
        source['evidence'] = [{'store': 'conversations.sqlite', 'table': 'runs', 'key': source['key'],
                               'fingerprint': 'b' * 64, 'extra': marker}]
        report = classify_inventory({'records': [source], 'fingerprint': 'source', 'issues': [],
                                     'files': [{'key': 'conversations.sqlite', 'role': 'application',
                                                'state': 'conflicting', 'recorded_policy': marker, 'extra': marker}]})
        self.assertNotIn(marker, json.dumps(report))
        item = report['records'][0]
        self.assertEqual(item['state'], 'unsupported')
        self.assertEqual(item['preserve']['recorded_calls'], 2)
        self.assertEqual(item['preserve']['recorded_execution_account'], {'policy': 'unsupported', 'call_limit': 3})
        self.assertEqual(report['files'][0]['recorded_policy'], 'unsupported')

    def test_original_native_task_plan_change_is_conflicting_not_repaired(self):
        cid,app,run=self.planner()
        with app.tasks.database.transaction() as db:
            db.execute("UPDATE tasks SET inputs='{}' WHERE run_id=?",(run,))
        before=self.facts();item=self.run_record(self.inspect(),run)
        self.assertEqual(item['classification'],'conflicting',item)
        self.assertEqual(self.facts(),before)
        # An internally consistent replacement still cannot replace the native source.
        from acquisition.adapters.sqlite.database import stored_plan_hash
        with app.tasks.database.transaction() as db:
            db.execute('UPDATE runs SET request_hash=? WHERE id=?',(stored_plan_hash(db,run),run))
        self.assertEqual(self.run_record(self.inspect(),run)['classification'],'conflicting')

    def test_missing_or_different_bound_journal_is_reported_without_creation(self):
        cid,app,run=self.planner()
        with self.w.control() as db:identity=dict(db.execute('SELECT * FROM workspace_identity').fetchone())
        receipt={'kind':'workspace_journal_binding','journal_id':identity['journal_id'],'database_kind':'conversations.sqlite','basis':'before_first_run','witness':None}
        with app.tasks.database.transaction() as db:
            db.execute('INSERT OR REPLACE INTO execution_commands VALUES(?,?,?,?)',('local-conversations','workspace:journal:v1',canonical(receipt),canonical(receipt)))
        matching=self.run_record(self.inspect(),run)
        self.assertEqual(matching['preserve']['journal_association'],'identity_match_completeness_unproven')
        path=self.root/'workspace.sqlite';path.rename(self.root/'original.saved')
        report=self.inspect();item=self.run_record(report,run)
        self.assertFalse(path.exists())
        self.assertEqual(item['classification'],'conflicting',item)
        Workspace(self.root,real_clock=lambda:self.now)
        self.assertEqual(self.run_record(self.inspect(),run)['classification'],'conflicting')

    def test_stale_populated_same_identity_journal_never_proves_independence(self):
        cid,app,planner=self.planner()
        backup=self.root/'old.saved';shutil.copyfile(self.root/'workspace.sqlite',backup)
        independent=app.start('old-org','later-cli',size=20)
        with self.w.control() as db:
            db.execute('INSERT INTO sessions VALUES(?,?,?)',('later','hash','{"parent_id":"known-parent"}'))
        shutil.copyfile(backup,self.root/'workspace.sqlite')
        item=self.run_record(self.inspect(),independent)
        self.assertEqual(item['classification'],'incomplete',item)
        self.assertEqual(item['owners'],[])

    def test_malformed_legacy_projection_and_binary_data_are_preserved_and_isolated(self):
        cid,app,run=self.planner()
        with self.w.control() as db:
            db.execute('INSERT INTO sessions VALUES(?,?,?)',('opaque','hash','{secret-bad-json'))
            db.execute('INSERT INTO preparations VALUES(?,?,?,?,?,?,?)',('old','opaque','request','chat',1,0,'secret-invalid-consent'))
            db.execute('CREATE TABLE opaque_binary(value BLOB)')
            db.execute('INSERT INTO opaque_binary VALUES(?)',(b'\x00\xffnever print',))
        before=self.facts();binary=self.byte_facts();report=self.inspect()
        self.assertEqual(self.run_record(report,run)['classification'],'supported')
        self.assertEqual(report['summary']['conflicting'],2)
        self.assertEqual(self.facts(),before);self.assertEqual(self.byte_facts(),binary)
        self.assertNotIn('never print',json.dumps(report));self.assertNotIn('secret-',json.dumps(report))

    def test_old_and_future_schemas_are_observed_without_upgrade_or_sealing(self):
        path=self.root/'conversations.sqlite'
        with sqlite3.connect(path) as db:
            db.executescript('PRAGMA user_version=1; CREATE TABLE runs(id TEXT, organization TEXT, request_id TEXT, request_hash TEXT,status TEXT,created_at REAL); CREATE TABLE tasks(run_id TEXT);')
        before=self.byte_facts();report=self.inspect()
        self.assertEqual(next(f for f in report['files'] if f['key']=='conversations.sqlite')['schema_version'],1)
        self.assertEqual(self.byte_facts(),before)
        with sqlite3.connect(path) as db:db.execute('PRAGMA user_version=999')
        before=self.byte_facts();report=self.inspect()
        self.assertIn({'source':'conversations.sqlite','code':'unsupported_source_schema'},report['issues'])
        self.assertEqual(self.byte_facts(),before)

    def test_unreadable_and_missing_sources_are_not_recovered_or_initialized(self):
        path=self.root/'conversations.sqlite';path.write_bytes(b'original opaque database')
        before=self.byte_facts();report=self.inspect()
        self.assertIn({'source':'conversations.sqlite','code':'source_requires_separate_sqlite_recovery'},report['issues'])
        self.assertEqual(self.byte_facts(),before)
        path.unlink();report=self.inspect()
        self.assertFalse(path.exists());self.assertEqual(report['inspection_state'],'has_unresolved_sources')

    def test_source_identity_mismatch_and_unsafe_route_cannot_grant_support(self):
        self.w=Workspace(self.root,real_clock=lambda:self.now,verified_admissions=True)
        session=self.w._session(self.w.create('root','fixture')['session']['id']);path=self.w._app(session).tasks.database.path
        path.unlink();shutil.copyfile(self.root/'conversations.sqlite',path)
        report=self.inspect()
        self.assertTrue(any(i['code']=='registered_store_identity_mismatch' for i in report['issues']))
        with self.w.control() as db:
            db.execute('INSERT INTO sessions VALUES(?,?,?)',('unsafe','hash',canonical({'id':'unsafe','organization':'../outside','mode':'fixture','clock':self.now})))
        self.assertTrue(any('legacy_session_or_route_is_invalid' in r['reasons'] for r in self.inspect()['records']))

    def test_active_server_lock_prevents_inspection_and_errors_release_lock(self):
        self.planner();before=self.facts()
        with (self.root/'server.lock').open('a+') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            result=self.cli('inspect')
        self.assertEqual(result.returncode,2);self.assertIn('Stop the workspace server',result.stderr)
        service=build_legacy_migration_inventory(self.root)
        with patch.object(service.source,'snapshot',side_effect=Conflict('injected inspection failure')),self.assertRaises(Conflict):service.inspect()
        with (self.root/'server.lock').open('a+') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(lock,fcntl.LOCK_UN)
        self.assertEqual(self.facts(),before)

    def test_change_during_inspection_invalidates_the_proposal(self):
        cid,app,run=self.planner();service=build_legacy_migration_inventory(self.root);original=service.source.snapshot
        count=[0]
        def changed():
            result=original();count[0]+=1
            if count[0]==1:
                with app.tasks.database.transaction() as db:
                    db.execute('UPDATE conversations SET revision=revision+1 WHERE organization=? AND id=?',('local-conversations',cid))
            return result
        with patch.object(service.source,'snapshot',side_effect=changed),self.assertRaisesRegex(Conflict,'changed during inspection'):service.inspect()

    def test_fresh_process_report_redacts_prompts_and_has_no_apply_or_activation(self):
        cid,app,run=self.planner();before=self.facts();result=self.cli('inspect')
        self.assertEqual(result.returncode,0,result.stderr);report=json.loads(result.stdout)
        self.assertEqual(report,self.inspect());self.assertNotIn(FIXTURE_MESSAGE,result.stdout)
        self.assertNotIn('planning_context',result.stdout);self.assertNotIn('response',result.stdout)
        for command in ('apply','activate','rebuild'):
            rejected=self.cli(command);self.assertEqual(rejected.returncode,2)
        self.assertEqual(self.facts(),before)

    def test_domain_descendant_keeps_positive_parentage_without_workspace_hint(self):
        cid,app,parent=self.planner()
        # A recorded domain parent is independent of the disposable journal.
        app.execution.descendant('local-conversations','child',parent)
        child=app.start('local-conversations','child',size=20)
        item=self.run_record(self.inspect(),child)
        self.assertEqual(item['classification'],'supported',item)
        self.assertEqual(item['owners'],[['local-conversations','conversation',cid,1]])
        self.assertTrue(item['dependencies'])
        self.assertFalse(item['executable'])

    def test_journal_parent_hint_does_not_supply_an_allowance_owner(self):
        app=build(self.root/'conversations.sqlite',clock=lambda:self.now)
        child=app.start('local-conversations','child',size=20)
        session={'id':'child','organization':'local-conversations','mode':'fixture','clock':self.now,
                 'run_id':None,'parent_id':'alleged-parent','database_scope':'conversations'}
        with self.w.control() as db:db.execute('INSERT INTO sessions VALUES(?,?,?)',('child','hash',canonical(session)))
        item=self.run_record(self.inspect(),child)
        self.assertEqual(item['classification'],'incomplete',item)
        self.assertIn('workspace_parent_claim_requires_domain_evidence',item['reasons'])
        self.assertEqual(item['owners'],[])

    def test_source_symlink_and_distinct_registered_paths_to_one_file_are_not_trusted(self):
        with tempfile.TemporaryDirectory() as outside:
            path=Path(outside)/'outside.sqlite';Database(path)
            before=path.read_bytes();(self.root/'conversations.sqlite').symlink_to(path)
            report=self.inspect()
            self.assertTrue(any(i['code']=='source_path_alias_is_unavailable' for i in report['issues']))
            self.assertEqual(path.read_bytes(),before)
        (self.root/'conversations.sqlite').unlink()
        self.w=Workspace(self.root,real_clock=lambda:self.now,verified_admissions=True)
        session=self.w._session(self.w.create('root','fixture')['session']['id']);path=self.w._app(session).tasks.database.path
        path.unlink();os.link(self.root/'conversations.sqlite',path)
        self.assertTrue(any(i['code']=='distinct_source_paths_alias_one_file' for i in self.inspect()['issues']))

    def test_hot_application_journal_is_preserved_for_separate_recovery(self):
        self.planner();code='''import os,sqlite3,sys
from pathlib import Path
db=sqlite3.connect(Path(sys.argv[1])/'conversations.sqlite')
db.execute('PRAGMA journal_mode=DELETE')
db.execute('CREATE TABLE crash_data(value TEXT)')
db.executemany('INSERT INTO crash_data VALUES(?)',[('original'*1000,)]*100)
db.commit()
db.execute('PRAGMA cache_size=2')
db.execute('BEGIN IMMEDIATE')
db.execute("UPDATE crash_data SET value='interrupted'")
os._exit(17)
'''
        self.assertEqual(self.cli(code=code).returncode,17)
        before=self.byte_facts();result=self.cli('inspect')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(any(i['code']=='source_requires_separate_sqlite_recovery' for i in json.loads(result.stdout)['issues']))
        self.assertEqual(self.byte_facts(),before)

    def test_native_routing_preserves_its_own_permission_and_never_borrows_copy_consent(self):
        from test_legacy_action_replay import LegacyRoutingReplayTests
        fixture=LegacyRoutingReplayTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        app,org,row,run=fixture.legacy()
        before=rows(fixture.root/'conversations.sqlite')
        report=build_legacy_migration_inventory(fixture.root).inspect();item=self.run_record(report,run)
        self.assertEqual(item['classification'],'supported',item)
        self.assertEqual(item['preserve']['permission_scope'],'routing_only')
        self.assertFalse(item['executable']);self.assertEqual(fixture.gateway.routing_requests,[])
        self.assertEqual(rows(fixture.root/'conversations.sqlite'),before)

    def test_conversation_campaign_retains_original_planner_and_is_not_an_approval(self):
        cid,app,planner=self.planner()
        proposal=app.conversations.view('local-conversations',cid)['current_plan']['result']
        result=self.w.draft_conversation(cid,'draft',1,proposal['id'])
        session=self.w._session(result['session']['id']);before=self.facts()
        item=self.run_record(self.inspect(),session['run_id'])
        self.assertEqual(item['classification'],'supported',item)
        self.assertEqual(item['preserve']['permission_scope'],'fixture_only')
        self.assertEqual(item['owners'],[['local-conversations','conversation',cid,1]])
        self.assertTrue(item['dependencies']);self.assertFalse(item['executable'])
        self.assertEqual(self.facts(),before)

    def test_legacy_preparation_exports_choices_and_hashes_without_arbitrary_input_fields(self):
        cid=self.w.create_conversation('prepare','Old coordinator')['id']
        self.w.message_conversation(cid,'message',0,FIXTURE_MESSAGE)
        self.w.start_preparation(cid,'prepare',1,True,False)
        with self.w.control() as db:
            raw=db.execute('SELECT * FROM preparations').fetchone();payload=json.loads(raw['payload'])
            payload['inputs']['private_note']='private-credential-do-not-export'
            db.execute('UPDATE preparations SET payload=?',(canonical(payload),))
        before=self.facts();report=self.inspect()
        preparation=next(r for r in report['records'] if r['kind']=='preparation')
        self.assertEqual(preparation['classification'],'incomplete',preparation)
        self.assertEqual(preparation['preserve']['generation_choices_observed'],{'fixture':True,'allow_model_copy':False})
        self.assertNotIn('private-credential',json.dumps(report));self.assertEqual(self.facts(),before)

    def test_native_copy_revision_preserves_parent_and_receipt_without_approval_or_retry(self):
        from test_legacy_action_replay import LegacyRevisionReplayTests
        from test_copy_revisions import CopyRevisionTests
        fixture=LegacyRevisionReplayTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        marker = 'sk-or-v1-' + '9' * 64
        CopyRevisionTests.admit(fixture, request=marker)
        receipt = fixture.app.reviews.store.revision_request(fixture.scope, marker)
        app = fixture.w._app(fixture.w._session(fixture.sid), with_model=True)
        run = app.revisions.reconcile(fixture.scope, receipt)
        app.admissions.store.seal_legacy_writes()
        path=app.tasks.database.path
        # The fixture uses conversations.sqlite, a known canonical source.
        root=path.parent
        before=rows(path);report=build_legacy_migration_inventory(root).inspect();item=self.run_record(report,run)
        self.assertNotIn(marker, json.dumps(report))
        self.assertEqual(item['preserve']['permission_scope'],'exact_copy_revision_only',item)
        self.assertTrue(item['dependencies']);self.assertFalse(item['executable'])
        self.assertEqual(fixture.model.revision_calls,[]);self.assertEqual(rows(path),before)

    def test_parent_graph_requires_positive_facts_and_detects_cycles_and_conflicting_owners(self):
        from acquisition.adapters.sqlite.legacy_sources import record
        parent_key = 'run_' + 'a' * 32
        child_key = 'run_' + 'b' * 32
        parent=record('store','run','org',parent_key);parent['permission_recorded']=True
        parent['owners']=[['org','conversation','chat',1]]
        child=record('store','run','org',child_key);child['permission_recorded']=True;child['parents']=[parent['id']]
        def report():return classify_inventory({'records':[parent,child],'fingerprint':'source','files':[],'issues':[]})
        resolved = report()
        self.assertTrue(self.run_record(resolved,parent_key)['owners'])
        self.assertEqual(self.run_record(resolved,child_key)['owners'],self.run_record(resolved,parent_key)['owners'])
        child['owners']=[['org','conversation','other',1]]
        self.assertEqual(self.run_record(report(),child_key)['classification'],'conflicting')
        child['owners']=[];parent['parents']=[child['id']]
        self.assertEqual(report()['summary']['conflicting'],2)
        parent['parents']=['missing-parent']
        self.assertEqual(self.run_record(report(),child_key)['classification'],'incomplete')
