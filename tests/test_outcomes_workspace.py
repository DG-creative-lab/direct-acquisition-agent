"""Company binding, exact evidence and durable recovery over real SQLite and HTTP."""
import json
import os
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
import unittest
from pathlib import Path
from unittest.mock import patch

from acquisition.bootstrap import build_intake, build_outcomes
from acquisition.campaigns import CampaignBriefDraft
from acquisition.creative import CompanyDraft
from acquisition.contracts import Conflict, NotFound, canonical
from acquisition.application.workspace.outcomes import WorkspaceOutcomes
from acquisition.adapters.sqlite.reviews import SqliteReviews
from test_external_outcomes import NOW, manifest, report, event
import test_workspace as http

ORG='local-conversations'

class OutcomeWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'conversations.sqlite';self.now=NOW
        self.intake=build_intake(self.path,clock=lambda:self.now)
        self.company=self.intake.save_company(ORG,'local-operator','company',CompanyDraft(company_name='Fielddesk'))['snapshot']
        self.brief=self.intake.save_brief(ORG,'local-operator','brief',CampaignBriefDraft(company_id=self.company['id'],company_revision=1))['snapshot']
        self.selection={'brief_id':self.brief['id'],'brief_revision':1}
        self.app=build_outcomes(self.path,clock=lambda:self.now,local_operator=True)
        self.web=WorkspaceOutcomes(self.app);self.m=manifest(ORG)
    def register(self,key='register'):
        payload={'source':canonical(self.m),'selection':self.selection}
        self.preview=self.web.preview('register',payload)
        self.command=payload|{'request_id':key,'preview_id':self.preview['preview_id']}
        self.receipt=self.web.command('register',self.command)
        self.c=self.app.view(ORG,self.receipt['result']['cohort_id'])['cohort']
        return self.receipt
    def import_report(self,p):
        data={'source':canonical(p),'cohort_id':self.c['id']}
        preview=self.web.preview('import',data)
        return self.web.command('import',data|{'request_id':p['report_id'],'preview_id':preview['preview_id']})
    def test_company_binding_is_atomic_immutable_and_survives_a_fresh_process(self):
        self.register();self.intake.save_company(ORG,'local-operator','edit',CompanyDraft(company_name='Changed'),company_id=self.company['id'],expected_revision=1)
        context=self.web.view(self.c['id'])['company_context']
        self.assertEqual(context['company'],self.company)
        self.assertEqual(self.web.command('register',self.command),self.receipt)
        self.assertEqual(self.web.listing(company_id=self.company['id'])['items'][0]['company_context'],context)
        self.assertEqual(self.app.listing('foreign')['items'],[])
        program='from acquisition.bootstrap import build_outcomes; import sys,json; print(json.dumps(build_outcomes(sys.argv[1],read_only=True).view(sys.argv[2],sys.argv[3])["company_context"]))'
        child=subprocess.run([sys.executable,'-c',program,str(self.path),ORG,self.c['id']],env=dict(os.environ,PYTHONPATH='src'),capture_output=True,text=True,timeout=20)
        self.assertEqual(child.returncode,0,child.stderr);self.assertEqual(json.loads(child.stdout),context)
        db=self.app.store.database
        with db.connect() as conn:
            for table in ('runs','model_calls','learning_beliefs','learning_cohorts','review_decisions'):
                self.assertEqual(conn.execute('SELECT count(*) FROM '+table).fetchone()[0],0,table)
    def test_binding_and_role_initialization_roll_back_with_registration(self):
        with patch.object(self.app.store,'audit',side_effect=RuntimeError('stopped during native audit')):
            with self.assertRaises(RuntimeError):self.register()
        with self.app.store.database.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM learning_commands').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM review_actors').fetchone()[0],0)
        self.register()
        roles=SqliteReviews(self.app.store.database,lambda:self.now,None)
        roles.register_actor(ORG,'local-operator',('operator',),enabled=False)
        with self.assertRaises(ValueError):self.web.command('register',self.command)
        with self.app.store.database.connect() as db:self.assertEqual(db.execute('SELECT enabled FROM review_actors').fetchone()[0],0)
    def test_removed_operator_cannot_be_recreated_by_replay_or_later_registration(self):
        self.register()
        # Reopening and a different request key must not reset local authority.
        with self.app.store.database.transaction() as db:
            db.execute('DELETE FROM review_actors WHERE organization=? AND id=?',(ORG,'local-operator'))
        reopened=WorkspaceOutcomes(build_outcomes(self.path,clock=lambda:self.now,local_operator=True))
        later=json.loads(canonical(self.m));later['campaign_id']='later-campaign'
        for member in later['assignments']:
            member['business_id']+='-later';member['outcome_record_id']+='-later'
            if member['dispatch']:member['dispatch']['id']+='-later'
        data={'source':canonical(later),'selection':self.selection}
        preview=reopened.preview('register',data)
        attempts=[self.command,self.command|{'request_id':'another-key'},
            data|{'request_id':'later','preview_id':preview['preview_id']}]
        def durable():
            with self.app.store.database.connect() as db:
                return {table:[tuple(row) for row in db.execute('SELECT * FROM '+table+' WHERE organization=? ORDER BY rowid',(ORG,))]
                    for table in ('review_actors','review_events','learning_commands','learning_events')}
        before=durable()
        for command in attempts:
            with self.subTest(request=command['request_id']):
                with self.assertRaises(ValueError):reopened.command('register',command)
                self.assertEqual(durable(),before)
        self.assertEqual(reopened.receipt('register','register')['result']['cohort_id'],self.c['id'])
        self.assertEqual(reopened.view(self.c['id'])['company_context']['company'],self.company)
        # Even deletion of the authority audit must not make existing outcome
        # records look like a first-time setup for a different campaign.
        with self.app.store.database.transaction() as db:
            db.execute('DELETE FROM review_events WHERE organization=?',(ORG,))
            db.execute('DELETE FROM learning_events WHERE organization=?',(ORG,))
        before=durable()
        with self.assertRaises(ValueError):reopened.command('register',attempts[-1])
        self.assertEqual(durable(),before)

    def test_local_bootstrap_respects_prior_authority_and_organization_scope(self):
        roles=SqliteReviews(self.app.store.database,lambda:self.now,None)
        roles.initialize_actor('foreign','local-operator',('operator',))
        # A rejected first request is not an established local setup.
        self.assertTrue(self.web.not_committed('register','rejected-before-setup'))
        self.register()
        with self.app.store.database.connect() as db:
            self.assertEqual(db.execute('SELECT generation FROM review_actors WHERE organization=? AND id=?',(ORG,'local-operator')).fetchone()[0],1)
        for history in ('reviewer_exists','operator_removed_before_first_outcome'):
            with self.subTest(history=history):
                other=build_outcomes(Path(self.temp.name)/(history+'.sqlite'),clock=lambda:self.now,local_operator=True)
                admin=SqliteReviews(other.store.database,lambda:self.now,None)
                actor='local-reviewer' if history=='reviewer_exists' else 'local-operator'
                admin.initialize_actor(ORG,actor,('reviewer',) if actor=='local-reviewer' else ('operator',))
                if actor=='local-operator':
                    with other.store.database.transaction() as db:db.execute('DELETE FROM review_actors WHERE organization=? AND id=?',(ORG,actor))
                with self.assertRaises(ValueError):other.register(ORG,'local-operator','first',self.m)
                with other.store.database.connect() as db:
                    self.assertIsNone(db.execute('SELECT 1 FROM review_actors WHERE organization=? AND id=?',(ORG,'local-operator')).fetchone())
                    self.assertEqual(db.execute('SELECT count(*) FROM learning_commands WHERE organization=?',(ORG,)).fetchone()[0],0)

    def test_missing_company_binding_cannot_silently_become_unassociated_history(self):
        self.register()
        from acquisition.adapters.sqlite.external_outcomes import record_key
        with self.app.store.database.transaction() as db:
            db.execute('DELETE FROM learning_commands WHERE organization=? AND request_id=?',(ORG,record_key('context',self.c['id'])))
        with self.assertRaises(Conflict):self.web.view(self.c['id'])
        with self.assertRaises(Conflict):self.web.command('register',self.command)

    def test_stale_preview_and_foreign_context_have_no_registration_effect(self):
        data={'source':canonical(self.m),'selection':self.selection}
        p=self.web.preview('register',data)
        with self.assertRaises(Conflict):self.web.command('register',data|{'request_id':'bad','preview_id':'other-store'})
        with self.assertRaises(NotFound):self.app.preview('foreign','register',payload=manifest('foreign'),selection=self.selection)
        with self.app.store.database.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM learning_commands').fetchone()[0],0)
        # Identical manifests in another store cannot reuse a displayed preview.
        other=build_outcomes(Path(self.temp.name)/'other.sqlite',local_operator=True)
        self.assertNotEqual(other.store_identity(),self.app.store_identity())
    def test_finalization_rechecks_displayed_evidence_and_exact_retry(self):
        self.register();self.now=self.c['window_end']
        rows=[event(m,'qualified_enquiry' if i==0 else 'no_qualified_enquiry',self.now-1 if i==0 else self.now) for i,m in enumerate(self.c['assignments'])]
        self.import_report(report(self.c,rows,final=True,identity='complete'))
        old=self.web.preview('finalize',{'cohort_id':self.c['id']})
        self.import_report(report(self.c,[event(self.c['assignments'][0],'opened',self.now-1)],source='send',identity='later-diagnostic',watermark=self.now))
        command={'request_id':'final','cohort_id':self.c['id'],'preview_id':old['preview_id']}
        with self.assertRaises(Conflict):self.web.command('finalize',command)
        self.assertIsNone(self.web.view(self.c['id'])['finalization'])
        fresh=self.web.preview('finalize',{'cohort_id':self.c['id']});self.assertTrue(fresh['eligible'])
        command['preview_id']=fresh['preview_id'];result=self.web.command('finalize',command)
        replay=self.web.command('finalize',command)
        self.assertEqual(replay['result']['original_receipt'],result['result'])
        self.assertEqual(self.web.view(self.c['id'])['posterior_groups'][0]['trials'],2)
    def test_rejection_fence_prevents_a_late_original_request_and_never_erases_a_commit(self):
        data={'source':canonical(self.m),'selection':self.selection}
        p=self.web.preview('register',data);command=data|{'request_id':'rejected','preview_id':p['preview_id']}
        self.assertTrue(self.web.not_committed('register','rejected'))
        with self.assertRaises(Conflict):self.web.command('register',command)
        self.register()
        self.assertFalse(self.web.not_committed('register','register'))
        self.assertEqual(self.web.command('register',self.command),self.receipt)
        with self.app.store.database.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM learning_events WHERE kind='external_registration'").fetchone()[0],1)
    def test_committed_writer_wins_a_concurrent_rejection_fence(self):
        data={'source':canonical(self.m),'selection':self.selection}
        preview=self.web.preview('register',data)
        command=data|{'request_id':'racing','preview_id':preview['preview_id']}
        entered=threading.Event();release=threading.Event()
        original=self.app.store.check_writer
        def paused(*args):
            entered.set()
            if not release.wait(10):raise RuntimeError('Writer was not released')
            return original(*args)
        with ThreadPoolExecutor(max_workers=2) as pool, patch.object(self.app.store,'check_writer',side_effect=paused):
            writer=pool.submit(self.web.command,'register',command)
            try:
                self.assertTrue(entered.wait(10))
                fence=pool.submit(self.web.not_committed,'register','racing')
            finally:release.set()
            result=writer.result(timeout=15)
            self.assertFalse(fence.result(timeout=15))
        self.assertEqual(self.web.receipt('register','racing')['result']['cohort_id'],result['result']['cohort_id'])

    def test_legacy_cohorts_inspectable_but_cannot_be_rebound_or_finalized_in_browser(self):
        roles=SqliteReviews(self.app.store.database,lambda:self.now,None);roles.initialize_actor(ORG,'local-operator',('operator',))
        value=self.app.register(ORG,'local-operator','old',self.m)
        self.assertIsNone(self.web.view(value['cohort_id'])['company_context'])
        self.assertEqual(len(self.web.listing()['items']),1)
        with self.assertRaises(Conflict):self.register()
        self.assertFalse(self.web.preview('finalize',{'cohort_id':value['cohort_id']})['writable'])
    def test_strict_raw_document_and_paused_verified_format(self):
        with self.assertRaises(ValueError):self.web.preview('register',{'source':'{"schema":"a","schema":"b"}','selection':self.selection})
        self.register()
        from acquisition.bootstrap import build_admissions
        build_admissions(self.path,verified_admissions=True)
        self.assertFalse(self.web.preview('register',{'source':canonical(self.m),'selection':self.selection})['writable'])
        with self.assertRaises(Conflict):self.web.command('register',self.command)
        self.assertEqual(self.web.view(self.c['id'])['company_context']['company'],self.company)

class OutcomeHttpTests(unittest.TestCase):
    setUp=http.WorkspaceHttpTests.setUp
    stop=http.WorkspaceHttpTests.stop
    request=http.WorkspaceHttpTests.request
    def test_preview_security_store_binding_raw_validation_and_fenced_failure(self):
        code,body,_=self.request('/api/outcomes/store');self.assertEqual(code,200,body)
        identity=json.loads(body)['store_id']
        data={'source':'{"x":1,"x":2}','selection':{'brief_id':'absent','brief_revision':1}}
        headers={'X-Outcomes-Store':identity}
        self.assertEqual(self.request('/api/outcomes/register-preview',data,headers)[0],400)
        for wrong in ({'Host':'evil.invalid'},{'Origin':'https://evil.invalid'},{'X-Workspace-Token':''}):
            self.assertEqual(self.request('/api/outcomes/register-preview',data,headers|wrong)[0],403)
        self.assertEqual(self.request('/api/outcomes/register-preview',data,headers|{'Authorization':'Bearer unused'})[0],400)
        code,body,_=self.request('/api/outcomes/register',data|{'request_id':'bad','preview_id':'invalid'},headers|{'X-Outcomes-Store':'other'})
        self.assertEqual(code,409);self.assertEqual(json.loads(body)['code'],'store_mismatch')
        code,body,_=self.request('/api/outcomes/register',data|{'request_id':'bad','preview_id':'invalid'},headers)
        self.assertEqual(code,409,body);self.assertTrue(json.loads(body)['outcomes_not_saved'])
        self.assertEqual(self.request('/api/outcomes/cohorts?organization=forged')[0],409)
        self.assertEqual(json.loads(self.request('/api/outcomes/cohorts')[1])['items'],[])
