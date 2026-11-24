"""Saved-source planning: exact provenance, bounded reasoning and no campaign effects."""

import copy
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from acquisition.bootstrap import build, build_intake
from acquisition.campaigns import CampaignBriefDraft
from acquisition.contracts import Conflict, NotFound
from acquisition.creative import CompanyDraft, CompanyClaimDraft
from acquisition.reasoning import ModelConfig
from acquisition.adapters.sqlite.database import Database
from test_model_copy import reply


class IntakeModel:
    def __init__(self, *results):
        self.requests = []
        self.results = list(results) or [{'outcome':'proposal', 'summary':'Explore a bounded consultancy campaign.',
            'approach':['Compare two qualified messages for the supplied retail audience.'],
            'questions':[], 'limitations':['The supplied claims need independent verification.']}]

    def complete(self, request):
        self.requests.append(copy.deepcopy(request))
        result = self.results.pop(0) if len(self.results) > 1 else self.results[0]
        if isinstance(result, Exception):
            raise result
        return reply('submit_intake_plan', result)


class IntakePlanningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'app.sqlite'
        self.model = IntakeModel()
        self.config = ModelConfig('test/model',max_calls=2,force_tool_choice=True)
        self.app = build(self.path,clock=lambda:1000.,gateway=self.model,model_config=self.config)
        self.intake = build_intake(self.path,clock=lambda:1000.)
        self.company = self.intake.save_company('one','writer','company',CompanyDraft(
            company_name='Aster Consultancy',product_name='Retail operations advice',
            description='User assertion \u2014 unchanged.',claims=(CompanyClaimDraft('A source claim','UK only'),)))['snapshot']
        self.brief = self.intake.save_brief('one','writer','brief',CampaignBriefDraft(
            self.company['id'],1,objective='Find retail clients',audience='Independent UK retailers',
            country='UK',currency='GBP',budget_minor=12345,channels=('email',),constraints=('Keep exact qualifications',)))['snapshot']

    def request(self, key='plan', revision=1):
        return self.app.intake_planning.request('one','writer',key,self.brief['id'],revision)

    def finish(self, run, key='plan'):
        self.app.worker.drain('one',run_id=run)
        return self.app.intake_planning.view('one',key)

    def test_source_survives_model_envelope_result_restart_and_original_replay(self):
        run = self.request()
        result = self.finish(run)
        self.assertEqual(result['plan']['status'],'succeeded',result)
        self.assertEqual(len(self.model.requests),1)
        source = result['source']
        self.assertEqual(source['company'],self.company)
        self.assertEqual(source['brief'],self.brief)
        payload = json.loads(self.model.requests[0]['messages'][1]['content'])
        self.assertEqual(payload['source']['company'],self.company)
        self.assertEqual(payload['source']['brief'],self.brief)
        self.assertNotIn('iwoca',json.dumps(payload['knowledge']).lower())
        proposal = result['plan']['result']
        self.assertEqual(proposal['requirements'],self.brief['draft'])
        self.assertEqual(proposal['authority'],'none')
        self.assertEqual(proposal['execution'],'unavailable')
        self.assertTrue(result['current'])
        self.assertEqual(self.app.conversations.store.listing('one'),[])
        with self.assertRaises(Conflict):
            self.app.conversations.plan('one',source['conversation_id'],'bypass',source['revision'])
        with self.assertRaises(Conflict):
            self.app.conversations.message('one',source['conversation_id'],'bypass',source['revision'],'Prepare it now')
        with self.assertRaises(Conflict):
            self.app.conversations.planning_context('one',source['conversation_id'],'bypass',source['revision'],False)
        self.app = build(self.path,clock=lambda:1001.,gateway=self.model,model_config=self.config)
        self.assertEqual(self.request(),run)
        self.assertEqual(self.finish(run)['plan']['result'],proposal)
        self.assertEqual(len(self.model.requests),1)
        with self.assertRaises(Conflict):
            self.request('replacement')
        other = build(self.path,gateway=self.model,model_config=replace(self.config,max_output_tokens=1400))
        with self.assertRaises(Conflict):
            other.intake_planning.request('one','writer','plan',self.brief['id'],1)
        with self.assertRaises(NotFound):
            self.app.intake_planning.view('foreign','plan')
        with Database(self.path).connect() as db:
            for table in ('drafts','review_cases','review_decisions','simulated_agency_jobs','learning_beliefs'):
                self.assertEqual(db.execute('SELECT count(*) FROM '+table).fetchone()[0],0,table)

    def test_readiness_preserves_missing_and_unsupported_requirements_without_calls(self):
        original = CampaignBriefDraft(**{**self.brief['draft'],'channels':tuple(self.brief['draft']['channels']),
                                        'constraints':tuple(self.brief['draft']['constraints'])})
        self.intake.save_brief('one','writer','edit',replace(original,country='France',currency='EUR',channels=('video',)),
                               brief_id=self.brief['id'],expected_revision=1)
        view = self.finish(self.request('unsupported',2),'unsupported')
        self.assertEqual(view['plan']['status'],'succeeded',view)
        self.assertEqual(view['plan']['result']['outcome'],'unsupported')
        self.assertEqual(view['plan']['result']['requirements']['country'],'France')
        self.assertEqual(view['plan']['result']['requirements']['currency'],'EUR')
        self.assertEqual(view['plan']['result']['requirements']['channels'],['video'])
        self.intake.save_brief('one','writer','edit-again',replace(original,objective='',budget_minor=None),
                               brief_id=self.brief['id'],expected_revision=2)
        view = self.finish(self.request('missing',3),'missing')
        self.assertEqual(view['plan']['result']['outcome'],'clarification')
        self.assertTrue(view['plan']['result']['questions'])
        self.assertEqual(self.model.requests,[])

    def test_verified_admission_rechecks_original_source_before_execution(self):
        path = Path(self.temp.name)/'verified.sqlite'
        Database(path,verified_admissions=True,fixture_execution=True,clock=lambda:1000.)
        app = build(path,clock=lambda:1000.,gateway=self.model,model_config=self.config,verified_admissions=True)
        intake = build_intake(path,clock=lambda:1000.,verified_admissions=True)
        company = intake.save_company('one','writer','company',CompanyDraft(company_name='Aster',description='User assertion'))['snapshot']
        brief = intake.save_brief('one','writer','brief',CampaignBriefDraft(company['id'],1,objective='Explore',audience='Retailers',
                    country='UK',currency='GBP',budget_minor=12345,channels=('email',)))['snapshot']
        run = app.intake_planning.request('one','writer','plan',brief['id'],1)
        app.worker.drain('one',run_id=run)
        view = app.intake_planning.view('one','plan')
        self.assertEqual(view['plan']['status'],'queued',view)
        self.assertIsNone(view['plan']['result'])
        self.assertEqual(self.model.requests,[])
        self.assertEqual(view['source']['brief']['draft'],brief['draft'])
        with app.tasks.database.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM admission_requests').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM intake_planning_sources').fetchone()[0],1)
        later = CampaignBriefDraft(company['id'],1,objective='Explore a later brief',audience='Retailers',
                    country='UK',currency='GBP',budget_minor=12345,channels=('email',))
        intake.save_brief('one','writer','edit',later,brief_id=brief['id'],expected_revision=1)
        self.assertNotEqual(app.intake_planning.request('one','writer','later-plan',brief['id'],2),run)
        self.assertEqual(app.intake_planning.request('one','writer','plan',brief['id'],1),run)
        self.assertEqual(self.model.requests,[])  # A queued native run suffices; verified execution stays paused.

    def saved_draft(self):
        values = self.brief['draft']
        return CampaignBriefDraft(**(values | {'channels':tuple(values['channels']), 'constraints':tuple(values['constraints'])}))

    def test_edits_preserve_old_source_and_make_results_historical(self):
        first = self.finish(self.request())
        original = copy.deepcopy(first['plan']['result'])
        self.intake.save_company('one','writer','company-edit',CompanyDraft(company_name='Changed company',description='Changed wording'),
                                 company_id=self.company['id'],expected_revision=1)
        self.intake.save_brief('one','writer','brief-edit',replace(self.saved_draft(),objective='A revised objective'),
                               brief_id=self.brief['id'],expected_revision=1)
        prior = self.app.intake_planning.view('one','plan')
        self.assertFalse(prior['current'])
        self.assertEqual(prior['source']['company'],self.company)
        self.assertEqual(prior['plan']['result'],original)
        self.assertEqual(self.request(),first['plan']['run_id'])
        later = self.finish(self.request('later',2),'later')
        self.assertEqual(later['source']['company_revision'],1)  # The brief still pins the original company.
        self.assertEqual(later['plan']['result']['requirements']['objective'],'A revised objective')
        self.assertEqual(len(self.model.requests),2)
        self.assertEqual(len(self.app.intake_planning.listing('one',self.brief['id'])),2)

    def test_staging_failure_and_concurrent_original_requests_converge(self):
        from concurrent.futures import ThreadPoolExecutor
        from unittest.mock import patch
        store = self.app.intake_planning.store
        with patch.object(self.app.conversations,'plan_intake',side_effect=OSError('lost after staging')):
            with self.assertRaises(OSError):self.request()
        staged = store.request('one','plan')
        self.assertEqual(staged['brief'],self.brief)
        self.assertEqual(self.model.requests,[])
        def admit(_):
            return build(self.path,clock=lambda:1000.,gateway=self.model,model_config=self.config).intake_planning.request(
                'one','writer','plan',self.brief['id'],1)
        with ThreadPoolExecutor(2) as pool:
            runs = list(pool.map(admit,range(2)))
        self.assertEqual(runs[0],runs[1])
        self.finish(runs[0])
        self.assertEqual(len(self.model.requests),1)
        with Database.existing(self.path).connect() as db:
            for table in ('intake_planning_sources','conversations','conversation_messages','conversation_plans','runs'):
                self.assertEqual(db.execute('SELECT count(*) FROM '+table).fetchone()[0],1,table)

    def test_new_key_cannot_skip_partial_admission_or_exceed_six_requests(self):
        from unittest.mock import patch
        with patch.object(self.app.conversations,'plan_intake',side_effect=OSError('partial')):
            with self.assertRaises(OSError):self.request()
        self.intake.save_brief('one','writer','edit-2',replace(self.saved_draft(),objective='Second'),
                               brief_id=self.brief['id'],expected_revision=1)
        with self.assertRaisesRegex(Conflict,'original staged'):self.request('skip',2)
        self.finish(self.request())
        for revision in range(2,7):
            if revision > 2:
                self.intake.save_brief('one','writer','edit-'+str(revision),replace(self.saved_draft(),objective='Revision '+str(revision)),
                                       brief_id=self.brief['id'],expected_revision=revision-1)
            self.finish(self.request('plan-'+str(revision),revision),'plan-'+str(revision))
        self.intake.save_brief('one','writer','edit-7',replace(self.saved_draft(),objective='Seventh'),
                               brief_id=self.brief['id'],expected_revision=6)
        with self.assertRaisesRegex(ValueError,'six planning'):self.request('seventh',7)
        self.assertEqual(len(self.model.requests),6)
        self.assertEqual(len(self.app.intake_planning.listing('one',self.brief['id'])),6)

    def test_uncertain_model_outcome_is_not_repeated_after_restart(self):
        from acquisition.reasoning import ModelError
        self.model = IntakeModel(ModelError('provider_outcome_unknown'))
        self.app = build(self.path,clock=lambda:1000.,gateway=self.model,model_config=self.config)
        run = self.request()
        self.finish(run)
        self.assertEqual(len(self.model.requests),1)
        self.app = build(self.path,clock=lambda:10000.,gateway=self.model,model_config=self.config)
        self.assertEqual(self.request(),run)
        self.finish(run)
        self.assertEqual(len(self.model.requests),1)

    def test_stop_during_inference_fences_publication_without_repeating_the_call(self):
        original = self.model.complete
        def stopping(request):
            response = original(request)
            source = self.app.intake_planning.store.request('one','plan')
            self.app.execution.stop('one',source['conversation_id'],'stop',source['revision'])
            return response
        self.model.complete = stopping
        view = self.finish(self.request())
        self.assertIsNone(view['plan']['result'])
        self.assertEqual(view['plan']['status'],'cancelled')
        self.finish(self.request())
        self.assertEqual(len(self.model.requests),1)

    def test_model_repair_is_bounded_and_never_accepts_authority_fields(self):
        invalid = self.model.results[0] | {'authority':'approved'}
        self.model.results = [invalid,invalid]
        view = self.finish(self.request())
        self.assertEqual(view['plan']['status'],'failed')
        self.assertEqual(len(self.model.requests),2)
        self.assertIsNone(view['plan']['result'])
        self.finish(self.request())
        self.assertEqual(len(self.model.requests),2)

    def test_schema24_upgrade_rollback_preserves_intake_and_store_identity(self):
        from unittest.mock import patch
        from acquisition.adapters.sqlite.intake_planning import INTAKE_PLANNING
        with Database.existing(self.path).transaction() as db:
            db.execute('DROP TABLE intake_planning_sources')
            db.execute('PRAGMA user_version=24')
            original_id = db.execute('SELECT id FROM application_store_identity').fetchone()[0]
            before = [tuple(row) for row in db.execute('SELECT * FROM intake_requests ORDER BY request_id')]
        apply = Database._apply_migration
        def fail(db, script):
            apply(db,script)
            if script == INTAKE_PLANNING:raise OSError('interrupted additive DDL')
        with patch.object(Database,'_apply_migration',side_effect=fail),self.assertRaises(OSError):Database(self.path)
        with Database.existing(self.path).connect() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],24)
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_schema WHERE name='intake_planning_sources'").fetchone())
            self.assertEqual([tuple(row) for row in db.execute('SELECT * FROM intake_requests ORDER BY request_id')],before)
        Database(self.path)
        with Database.existing(self.path).connect() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],25)
            self.assertEqual(db.execute('SELECT id FROM application_store_identity').fetchone()[0],original_id)
            self.assertEqual([tuple(row) for row in db.execute('SELECT * FROM intake_requests ORDER BY request_id')],before)
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_preflight_failure_has_no_staged_source_and_source_history_is_immutable(self):
        import sqlite3
        from unittest.mock import patch
        from acquisition.reasoning import ModelError
        with patch.object(self.app.conversations,'preflight',side_effect=ModelError('input_limit_exceeded')):
            with self.assertRaises(Conflict):self.request()
        with Database.existing(self.path).connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM intake_planning_sources').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM conversations').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM runs').fetchone()[0],0)
        self.request()
        with Database.existing(self.path).transaction() as db:
            for sql in ("UPDATE intake_planning_sources SET brief_revision=2", "DELETE FROM intake_planning_sources",
                        "INSERT OR REPLACE INTO intake_planning_sources SELECT * FROM intake_planning_sources"):
                with self.assertRaises(sqlite3.IntegrityError):db.execute(sql)

    def test_consistently_rehashed_source_cannot_replace_independent_intake_evidence(self):
        from unittest.mock import patch
        from acquisition.contracts import canonical, digest
        from acquisition.conversations import intake_source_message
        with patch.object(self.app.conversations,'plan_intake',side_effect=OSError('partial')):
            with self.assertRaises(OSError):self.request()
        source = self.app.intake_planning.store.request('one','plan')
        forged = copy.deepcopy(source)
        forged['company']['draft']['description'] = 'An invented verified product fact'
        forged['fingerprint'] = digest({k:v for k,v in forged.items() if k != 'fingerprint'})
        with Database.existing(self.path).transaction() as db:
            db.execute('DROP TRIGGER intake_planning_no_update')  # Model an independently corrupt/old writer.
            db.execute('UPDATE intake_planning_sources SET source=? WHERE organization=? AND request_id=?',
                       (canonical(forged),'one','plan'))
            db.execute('UPDATE conversation_messages SET content=? WHERE organization=? AND conversation_id=? AND revision=?',
                       (intake_source_message(forged),'one',source['conversation_id'],source['revision']))
        with self.assertRaises(Conflict):self.request()
        with self.assertRaises(Conflict):self.app.conversations.plan_intake(forged)
        with Database.existing(self.path).connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM runs').fetchone()[0],0)
        self.assertEqual(self.model.requests,[])

    def test_process_exit_after_plan_reservation_or_receipt_preserves_original_request(self):
        import os
        import subprocess
        import sys
        for point in ('plan','reservation','receipt'):
            with self.subTest(point=point):
                path = Path(self.temp.name)/(point+'.sqlite')
                intake = build_intake(path,clock=lambda:1000.)
                company = intake.save_company('one','writer','company',CompanyDraft(company_name='Aster',description='Source assertion'))['snapshot']
                brief = intake.save_brief('one','writer','brief',CampaignBriefDraft(company['id'],1,objective='Explore retail',audience='UK retailers',
                    country='UK',currency='GBP',channels=('email',),budget_minor=12345))['snapshot']
                program = '''
import os,sys
from acquisition.bootstrap import build
from acquisition.reasoning import ModelConfig
from test_model_copy import reply
class Model:
 def complete(self, request):
  if sys.argv[3]=='reservation':os._exit(73)
  return reply('submit_intake_plan',{'outcome':'proposal','summary':'Completed receipt preserved.',
   'approach':['Use the supplied audience and qualifications.'],'questions':[],'limitations':['User claims remain unverified.']})
app=build(sys.argv[1],clock=lambda:1000.,gateway=Model(),model_config=ModelConfig('test/model',max_calls=2,force_tool_choice=True))
if sys.argv[3]=='plan':app.tasks.create=lambda *args:os._exit(75)
run=app.intake_planning.request('one','writer','original',sys.argv[2],1)
if sys.argv[3]=='receipt':app.tasks.settle=lambda *args:os._exit(74)
app.worker.drain('one',run_id=run)
'''
                child = subprocess.run([sys.executable,'-c',program,str(path),brief['id'],point],
                                       env=dict(os.environ,PYTHONPATH='src:tests'),capture_output=True,text=True,timeout=20)
                self.assertEqual(child.returncode,{'plan':75,'reservation':73,'receipt':74}[point],child.stderr)
                model = IntakeModel()
                app = build(path,clock=lambda:10000.,gateway=model,model_config=self.config)
                original = app.intake_planning.view('one','original')
                if point=='plan':
                    self.assertIsNone(original['plan']['run_id'])
                    from acquisition.runtime import TaskSpec
                    with app.tasks.database.connect() as db:
                        frozen = json.loads(db.execute('SELECT payload FROM conversation_plans').fetchone()[0])
                    app.tasks.create('foreign',frozen['run_request_id'],[TaskSpec('unrelated',{})],10000.)
                    later = CampaignBriefDraft(company['id'],1,objective='Later saved brief',audience='UK retailers',
                        country='UK',currency='GBP',channels=('email',),budget_minor=12345)
                    intake.save_brief('one','writer','later-brief',later,brief_id=brief['id'],expected_revision=1)
                    with self.assertRaisesRegex(Conflict,'original staged'):
                        app.intake_planning.request('one','writer','later-plan',brief['id'],2)
                    with app.tasks.database.connect() as db:
                        self.assertEqual(db.execute('SELECT revision FROM conversations WHERE organization=?',('one',)).fetchone()[0],1)
                        self.assertEqual(db.execute('SELECT count(*) FROM intake_planning_sources').fetchone()[0],1)
                        self.assertEqual(db.execute('SELECT count(*) FROM conversation_plans').fetchone()[0],1)
                        self.assertEqual(db.execute('SELECT count(*) FROM runs WHERE organization=?',('one',)).fetchone()[0],0)
                    self.assertEqual(model.requests,[])
                run = app.intake_planning.request('one','writer','original',brief['id'],1)
                if point!='plan':self.assertEqual(run,original['plan']['run_id'])
                app.worker.drain('one',run_id=run)
                recovered = app.intake_planning.view('one','original')
                self.assertEqual(recovered['source'],original['source'])
                self.assertEqual(len(model.requests),1 if point=='plan' else 0)
                self.assertEqual(len(app.calls.inspect('one',run)),1)
                if point=='plan':
                    self.assertEqual(recovered['plan']['status'],'succeeded')
                    self.assertEqual(recovered['plan']['result']['requirements'],brief['draft'])
                    self.assertEqual(app.intake_planning.request('one','writer','original',brief['id'],1),run)
                    # Once the original runtime run exists, later selections remain available.
                    self.assertNotEqual(app.intake_planning.request('one','writer','later-plan',brief['id'],2),run)
                    self.assertEqual(app.intake_planning.request('one','writer','original',brief['id'],1),run)
                    self.assertEqual(len(model.requests),1)
                elif point=='receipt':
                    self.assertEqual(recovered['plan']['result']['summary'],'Completed receipt preserved.')
                else:
                    self.assertIsNone(recovered['plan']['result'])
                    self.assertEqual(recovered['plan']['status'],'failed')

    def test_encoded_source_limit_rejects_before_staging_or_inference(self):
        wide = self.intake.save_company('one','writer','wide-company',CompanyDraft(company_name='Wide source',
            description='x'*8000,claims=tuple(CompanyClaimDraft('x'*3000) for _ in range(6))))['snapshot']
        draft = replace(self.saved_draft(),company_id=wide['id'],company_revision=1)
        self.intake.save_brief('one','writer','wide-brief',draft,brief_id=self.brief['id'],expected_revision=1)
        with self.assertRaises(Conflict):self.request('too-wide',2)
        self.assertEqual(self.model.requests,[])
        with Database.existing(self.path).connect() as db:
            for table in ('intake_planning_sources','conversations','conversation_plans','runs','model_calls'):
                self.assertEqual(db.execute('SELECT count(*) FROM '+table).fetchone()[0],0,table)
