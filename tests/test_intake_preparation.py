"""Selected grounding, exact offline drafts and atomic original-request recovery."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import asdict, replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from acquisition.bootstrap import build_intake
from acquisition.campaigns import CampaignBriefDraft, PreparationReview, GroundedPreparationRequest
from acquisition.creative import CompanyDraft, CompanyClaimDraft, SourceEvidenceReview
from acquisition.contracts import Conflict, NotFound, canonical
from acquisition.adapters.sqlite.database import Database
from acquisition.adapters.sqlite.intake_preparation import PREFIX, CONTEXT_PREFIX
from acquisition.reviews.domain import validate_population
from acquisition.adapters.sqlite.drafts import read_draft

NOW = datetime(2026,11,25,12,tzinfo=timezone.utc).timestamp()


class IntakePreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'app.sqlite'
        self.now = NOW
        self.app = build_intake(self.path, clock=lambda:self.now)
        self.seed()

    def seed(self, brand='Aster', organization='one', suffix=''):
        self.organization = organization
        self.company_draft = CompanyDraft(company_name=brand,product_name=brand+' advice',
            description=brand+' provides retail advice.',
            claims=(CompanyClaimDraft(brand+' offers a retail advice package.','Subject to the published terms.',
                                    ('https://'+brand.lower()+'.invalid/product',)),
                    CompanyClaimDraft('UNSELECTED CLAIM MUST NEVER REACH COPY','Unselected qualification.',
                                      ('https://unselected.invalid/claim',))),
            official_cta='Read '+brand+' terms.',cta_url='https://'+brand.lower()+'.invalid/terms',
            source_urls=('https://'+brand.lower()+'.invalid/product',))
        self.company = self.app.save_company(organization,'operator','company'+suffix,self.company_draft)['snapshot']
        self.brief_draft = CampaignBriefDraft(self.company['id'],1,objective='Compare retail responses.',
            audience='Independent retail businesses',country='UK',currency='GBP',channels=('postal',),
            budget_minor=12345,max_candidates=30,constraints=('Keep every qualification.',),contact_source='synthetic')
        self.brief = self.app.save_brief(organization,'operator','brief'+suffix,self.brief_draft)['snapshot']
        self.context_request = 'review'+suffix
        self.review_inputs()

    def review_inputs(self, revision=1, **changes):
        p=self.app.preparation.preview(self.organization,self.brief['id'],revision)
        review=PreparationReview(self.brief['id'],revision,p['id'],p['context_revision'],
            (p['claims'][0]['id'],),False,True,7,'Selected the exact inputs.',confirmed=True)
        self.context = self.app.preparation.confirm(self.organization,'operator',self.context_request,replace(review,**changes))['context']

    def preview(self):return self.app.grounded.preview(self.organization,self.context_request)
    def command(self, preview=None):
        p=preview or self.preview()
        return GroundedPreparationRequest(self.context_request,p['id'], SourceEvidenceReview(
            tuple(r['id'] for r in p['references']),p['checked_on'],7,
            'Inspected the official pages and exact wording, including qualifications and CTA.',True,True),True)
    def prepare(self,key='prepare',request=None):
        return self.app.grounded.prepare(self.organization,'operator',key,request or self.command())
    def counts(self):
        with self.app.store.database.connect() as db:
            return {t:db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in
                ('audiences','creative_contexts','generated_catalogues','drafts','draft_operations','runs','tasks',
                 'model_calls','review_cases','review_decisions','simulated_agency_jobs')}

    def test_two_products_preserve_their_selected_wording_qualification_cta_and_requirements(self):
        before=self.counts(); preview=self.preview()
        self.assertEqual(self.counts(),before)
        self.assertEqual(preview['blockers'],[])
        self.assertNotIn('UNSELECTED',canonical(preview)); self.assertNotIn('context',preview)
        results=[]
        for brand,suffix in [('Aster',''),('Birch','-birch')]:
            if suffix:self.seed(brand,suffix=suffix)
            result=self.prepare('prepare'+suffix);results.append(result)
            self.assertTrue(result['current']);self.assertEqual(result['model_calls'],0)
            self.assertEqual(result['grounding']['requirements'],self.context['requirements'])
            self.assertEqual(result['manifest']['counts']['input'],30)
            self.assertEqual(result['manifest']['brief']['budget_pence'],12345)
            self.assertEqual(result['product_evidence']['facts'][0]['copy'],brand+' offers a retail advice package.')
            self.assertEqual(result['product_evidence']['facts'][0]['qualification'],'Subject to the published terms.')
            self.assertEqual(result['product_evidence']['cta'],'Read '+brand+' terms.')
            frozen=canonical(result)
            for forbidden in ('UNSELECTED','unselected.invalid','iwoca.co.uk','Flexi-Loan'):
                self.assertNotIn(forbidden,frozen)
            self.assertEqual(result['product_evidence']['verification'],'operator_attested_sources_not_independently_verified')
            self.assertEqual(result['grounding']['settings']['targeting'],'synthetic_not_matched_to_user_audience')
            for creative in result['manifest']['creatives']:
                self.assertIn(brand+' offers a retail advice package. Subject to the published terms.',creative['opening'])
                self.assertIn('Read '+brand+' terms.',creative['opening'])
                self.assertEqual(creative['status'],'synthetic_profile_fixture_unapproved')
            with self.app.store.database.connect() as db:
                draft=read_draft(db,self.organization,result['draft_id'])
                with self.assertRaises(Conflict):validate_population(draft,None,set())
        self.assertNotEqual(results[0]['draft_id'],results[1]['draft_id'])
        counts=self.counts();self.assertEqual(counts['drafts'],2)
        for t in ('runs','tasks','model_calls','review_cases','review_decisions','simulated_agency_jobs'):
            self.assertEqual(counts[t],0,t)

    def test_source_review_requires_exact_references_confirmation_and_today(self):
        command=self.command()
        variants=[replace(command,evidence=replace(command.evidence,reference_ids=command.evidence.reference_ids[:1])),
                  replace(command,evidence=replace(command.evidence,reference_ids=('foreign-reference',))),
                  replace(command,evidence=replace(command.evidence,checked_on='2026-11-24')),
                  replace(command,preview_id='eligibility_foreign')]
        for c in variants:
            with self.subTest(command=c),self.assertRaises(ValueError):self.prepare(request=c)
        for change in ({'confirmed_official_sources':False},{'confirmed_exact_wording':False},{'note':''},{'review_days':31}):
            with self.subTest(change=change),self.assertRaises(ValueError):replace(command.evidence,**change)
        with self.assertRaises(ValueError):replace(command,confirmed_synthetic_preparation=False)
        self.assertEqual(self.counts()['drafts'],0)

    def test_current_sources_and_expiry_block_new_work_but_original_receipt_remains_exact(self):
        request=self.command();first=self.prepare(request=request);before=self.counts()
        self.app.save_company('one','operator','edit',replace(self.company_draft,description='New source assertion.'),
                              company_id=self.company['id'],expected_revision=1)
        self.now+=8*86400
        replay=self.prepare(request=request)
        self.assertTrue(replay['replayed']);self.assertFalse(replay['current'])
        for k in ('draft_id','manifest','grounding','product_evidence'):self.assertEqual(first[k],replay[k])
        self.assertTrue(self.preview()['blockers'])
        with self.assertRaises(Conflict):self.prepare('new',request)
        with self.assertRaises(Conflict):self.prepare(request=replace(request,evidence=replace(request.evidence,note='Different review.')))
        self.assertEqual(self.counts(),before)

    def test_stale_preview_after_source_edit_new_review_and_changed_brief(self):
        old=self.command()
        self.app.save_brief('one','operator','brief-edit',replace(self.brief_draft,budget_minor=20000),
                            brief_id=self.brief['id'],expected_revision=1)
        with self.assertRaises(Conflict):self.prepare(request=old)
        self.context_request='review-two';self.review_inputs(2)
        result=self.prepare('new')
        self.assertEqual(result['manifest']['brief']['budget_pence'],20000)
        self.assertEqual(result['grounding']['requirements']['audience'],'Independent retail businesses')
        self.assertEqual(self.counts()['drafts'],1)

    def test_missing_evidence_questions_unsupported_scope_and_unselected_material_never_default(self):
        changes=[{'country':'France'},{'currency':'EUR'},{'channels':('email',)}, {'contact_source':'unspecified'},
                 {'objective':''},{'budget_minor':0},{'budget_minor':1_000_001}]
        for i,change in enumerate(changes):
            with self.subTest(change=change):
                revision=i+2
                self.app.save_brief('one','operator','edit-'+str(i),replace(self.brief_draft,**change),
                                    brief_id=self.brief['id'],expected_revision=revision-1)
                self.context_request='review-'+str(i);self.review_inputs(revision)
                p=self.preview();self.assertTrue(p['blockers'])
                for k,v in change.items():self.assertEqual(p['requirements'][k],list(v) if type(v) is tuple else v)
                with self.assertRaises(Conflict):self.prepare('blocked-'+str(i))
        self.assertEqual(self.counts()['drafts'],0)

    def test_source_punctuation_is_preserved_and_incompatible_factual_copy_is_explained(self):
        source=replace(self.company_draft,claims=(CompanyClaimDraft('Advice \u2014 exactly as supplied.',
            'Terms apply.',('https://aster.invalid/product',)),))
        self.app.save_company('one','operator','edit',source,company_id=self.company['id'],expected_revision=1)
        self.app.save_brief('one','operator','brief-edit',replace(self.brief_draft,company_revision=2,
            objective='Compare responses \u2014 source objective.'),brief_id=self.brief['id'],expected_revision=1)
        self.context_request='review-two';self.review_inputs(2)
        p=self.preview();self.assertEqual(p['selected_inputs']['claims'][0]['statement'],'Advice \u2014 exactly as supplied.')
        self.assertTrue(any('Source wording was preserved' in b for b in p['blockers']))
        self.assertEqual(self.app.company('one',self.company['id'],2)['draft']['claims'][0]['statement'],'Advice \u2014 exactly as supplied.')
        with self.assertRaises(Conflict):self.prepare()

    def test_commit_rechecks_source_and_expiry_and_rolls_back_every_intermediate_row(self):
        original=self.app.grounded.store.publish
        request=self.command()
        def edit_then_publish(*args):
            self.app.save_company('one','operator','edit',replace(self.company_draft,description='Changed before commit.'),
                                  company_id=self.company['id'],expected_revision=1)
            return original(*args)
        with patch.object(self.app.grounded.store,'publish',side_effect=edit_then_publish),self.assertRaises(Conflict):
            self.prepare(request=request)
        self.assertEqual(self.counts()['drafts'],0)
        # A fresh input review explicitly sees the newer source head.
        self.context_request='new-review';self.review_inputs()
        self.app.grounded.store.clock=lambda:self.context['review_expires_at']
        with self.assertRaises(Conflict):self.prepare()
        self.assertEqual(self.counts()['audiences'],0)

    def test_fault_after_artifact_write_rolls_back_then_original_retry_recovers(self):
        request=self.command();store=self.app.grounded.store
        before=self.counts();real=store._result
        def fail(*args,**kwargs):
            value=real(*args,**kwargs)
            if not args[-1]:raise OSError('after artifact and command, before commit')
            return value
        with patch.object(store,'_result',side_effect=fail),self.assertRaises(OSError):self.prepare(request=request)
        self.assertEqual(self.counts(),before)
        first=self.prepare(request=request)
        self.assertEqual(self.prepare(request=request)['draft_id'],first['draft_id'])
        self.assertEqual(self.counts()['drafts'],1)

    def test_lost_commit_ack_reconciles_original_without_duplicate_or_renewed_review(self):
        request=self.command();db=self.app.store.database;real=db.transaction
        @contextmanager
        def lose_ack():
            with real() as conn:yield conn
            raise OSError('committed but acknowledgement lost')
        with patch.object(db,'transaction',lose_ack),self.assertRaises(OSError):self.prepare(request=request)
        self.now+=20
        result=self.prepare(request=request)
        self.assertTrue(result['replayed']);self.assertEqual(result['grounding']['prepared_at'],NOW)
        self.assertEqual(self.counts()['drafts'],1)
        self.assertEqual(self.counts()['model_calls'],0)

    def test_two_competing_invocations_converge_and_new_key_cannot_repeat_same_review(self):
        request=self.command()
        def run(_):return build_intake(self.path,clock=lambda:NOW).grounded.prepare('one','operator','prepare',request)
        # Two lightweight contenders are the explicit concurrency case, not parallel test suites.
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,range(2)))
        self.assertEqual(results[0]['draft_id'],results[1]['draft_id'])
        with self.assertRaises(Conflict):self.prepare('another-key',request)
        self.assertEqual(self.counts()['drafts'],1)
        with self.assertRaises(NotFound):self.app.grounded.request('foreign','prepare')
        with self.assertRaises(NotFound):self.app.grounded.preview('foreign','review')

    def test_fresh_process_and_inspection_open_recover_exact_bytes_but_not_write_authority(self):
        first=self.prepare();before=self.counts()
        program='''import json,sys
from acquisition.bootstrap import build_intake
app=build_intake(sys.argv[1],clock=lambda:float(sys.argv[2]),read_only=True)
print(json.dumps(app.grounded.request('one','prepare')))
'''
        child=subprocess.run([sys.executable,'-c',program,str(self.path),str(NOW+20)],
            env=dict(os.environ,PYTHONPATH='src'),capture_output=True,text=True,timeout=20)
        self.assertEqual(child.returncode,0,child.stderr)
        recovered=json.loads(child.stdout)
        self.assertEqual(recovered['manifest'],first['manifest'])
        inspection=build_intake(self.path,clock=lambda:NOW,read_only=True)
        self.assertTrue(inspection.grounded.preview('one','review')['blockers'])
        with self.assertRaises(Conflict):inspection.grounded.prepare('one','operator','new',self.command())
        self.assertEqual(self.counts(),before)

    def test_questions_missing_sources_and_missing_qualifications_block_without_rewriting(self):
        original=self.context_request
        for i,changes in enumerate(({'issues':('Resolve contradictory product descriptions.',)},
                                   {'include_cta':False}, {'selected_claim_ids':()})):
            self.context_request='blocked-review-'+str(i)
            self.review_inputs(**changes)
            self.assertTrue(self.preview()['blockers'])
            with self.assertRaises(Conflict):self.prepare('blocked-'+str(i))
        self.assertEqual(self.counts()['drafts'],0)

    def test_other_organization_cannot_substitute_a_same_named_review_or_request(self):
        first_request=self.command();first=self.prepare(request=first_request)
        self.seed('Birch',organization='two')
        with self.assertRaises(Conflict):self.prepare(request=first_request)
        second=self.prepare()
        self.assertNotEqual(first['draft_id'],second['draft_id'])
        self.assertNotIn('Aster',canonical(second))
        self.assertNotIn('Birch',canonical(self.app.grounded.request('one','prepare')))

    def test_source_expiry_between_writes_and_final_check_rolls_back_complete_bundle(self):
        store=self.app.grounded.store;real=store._result;before=self.counts()
        def expire_at_final_read(db,organization,request_id,draft,now,replayed):
            return real(db,organization,request_id,draft,self.context['review_expires_at'],replayed)
        with patch.object(store,'_result',side_effect=expire_at_final_read),self.assertRaises(Conflict):self.prepare()
        self.assertEqual(self.counts(),before)

    def test_missing_or_substituted_durable_bundle_members_fail_original_receipt_integrity(self):
        self.prepare();store=self.app.grounded.store
        for table,predicate in (('generated_catalogues',"organization='one'"),('creative_contexts',"organization='one'"),
                                ('draft_operations',"organization='one' AND operation_id LIKE 'intake-preparation-context:%'")):
            with self.subTest(table=table):
                with self.app.store.database.connect() as db:
                    db.execute('BEGIN IMMEDIATE')
                    db.execute('DELETE FROM '+table+' WHERE '+predicate)
                    # Use this same transaction for the read so the fault remains isolated.
                    with patch.object(store.database,'connect') as connect:
                        @contextmanager
                        def scoped():yield db
                        connect.side_effect=scoped
                        with self.assertRaises((Conflict,NotFound)):self.app.grounded.request('one','prepare')
                    db.rollback()
        self.assertTrue(self.app.grounded.request('one','prepare')['replayed'])

    def test_verified_store_execution_remains_paused(self):
        build_intake(self.path,clock=lambda:NOW,verified_admissions=True)
        self.assertTrue(self.preview()['blockers'])
        with self.assertRaises(Conflict):self.prepare()
        self.assertEqual(self.counts()['drafts'],0)


class RemoteIntakePreparationTests(unittest.TestCase):
    seed=IntakePreparationTests.seed
    review_inputs=IntakePreparationTests.review_inputs
    preview=IntakePreparationTests.preview
    command=IntakePreparationTests.command
    prepare=IntakePreparationTests.prepare
    counts=IntakePreparationTests.counts

    def test_hrana_competing_sessions_lost_commit_ack_and_restart_keep_one_original_draft(self):
        from test_turso_storage import Wire
        from acquisition.adapters.turso import CommitUncertain
        from acquisition.adapters.turso.transport import RemoteUnavailable
        with tempfile.TemporaryDirectory() as directory:
            wire=Wire(Path(directory)/'remote.sqlite')
            try:
                database=wire.database(True);self.now=NOW
                def open_app(db):
                    with patch('acquisition.bootstrap.build_database',return_value=db):
                        return build_intake(None,clock=lambda:self.now)
                self.app=open_app(database);self.seed();request=self.command()
                # A lost COMMIT response is a remote ambiguity, not permission to repeat work.
                send=database.send
                def lose_ack(payload):
                    result=send(payload)
                    if any(s.get('stmt',{}).get('sql')=='COMMIT' for r in payload['requests'] for s in r.get('batch',{}).get('steps',[])):
                        raise RemoteUnavailable('lost grounding commit acknowledgement')
                    return result
                database.send=lose_ack
                with self.assertRaises(CommitUncertain):self.prepare(request=request)
                database.send=send
                reopened=open_app(wire.database())
                first=reopened.grounded.prepare('one','operator','prepare',request)
                self.assertTrue(first['replayed']);self.assertEqual(first['grounding']['prepared_at'],NOW)
                self.assertEqual(first['product_evidence']['facts'][0]['copy'],'Aster offers a retail advice package.')
                self.assertEqual(self.counts()['drafts'],1)
                with self.assertRaises(NotFound):reopened.grounded.request('foreign','prepare')
                self.seed('Birch',suffix='-birch');request=self.command()
                apps=[open_app(wire.database()),open_app(wire.database())]
                with ThreadPoolExecutor(max_workers=2) as pool:
                    futures=[pool.submit(app.grounded.prepare,'one','operator','birch',request) for app in apps]
                    results=[f.result(timeout=30) for f in futures]
                self.assertEqual(results[0]['draft_id'],results[1]['draft_id'])
                self.assertEqual(self.counts()['drafts'],2)
                self.assertEqual(self.counts()['model_calls'],0)
            finally:wire.close()


class WorkspaceGroundedPreparationTests(unittest.TestCase):
    import test_workspace as _workspace
    setUp=_workspace.WorkspaceHttpTests.setUp
    stop=_workspace.WorkspaceHttpTests.stop
    request=_workspace.WorkspaceHttpTests.request
    seed=IntakePreparationTests.seed
    review_inputs=IntakePreparationTests.review_inputs
    command=IntakePreparationTests.command
    preview=IntakePreparationTests.preview

    def test_guarded_workspace_preview_prepare_replay_and_authority_substitution(self):
        self.now=NOW
        self.app=build_intake(self.root/'data'/'conversations.sqlite',clock=lambda:self.now)
        self.seed(organization='local-conversations')
        path='/api/intake/eligibility?context_request_id=review'
        status,body,_=self.request(path);self.assertEqual(status,200,body)
        p=json.loads(body);self.assertEqual(p['blockers'],[])
        self.assertNotIn('UNSELECTED',body.decode())
        command={'request_id':'prepare',**asdict(self.command(p))}
        headers={'X-Intake-Store':p['store_id']}
        for bad in ({'Host':'attacker.invalid'},{'Origin':'https://attacker.invalid'},{'X-Workspace-Token':''}):
            self.assertEqual(self.request('/api/intake/preparations',command,headers|bad)[0],403)
        for bad in ({'Authorization':'Bearer test-only'},{'X-OpenRouter-Handle':'test-only'},{'X-Intake-Store':'another-store'}):
            self.assertIn(self.request('/api/intake/preparations',command,headers|bad)[0],(400,409))
        for field in ('actor','organization','model'):
            self.assertEqual(self.request('/api/intake/preparations',command|{field:'forged'},headers)[0],409)
        status,body,_=self.request('/api/intake/preparations',command,headers)
        self.assertEqual(status,200,body);first=json.loads(body)
        self.assertEqual(first['grounding']['actor'],'local-operator')
        self.assertEqual(first['approval'],'not_granted')
        status,body,_=self.request('/api/intake/preparations/requests/prepare')
        self.assertEqual(status,200,body)
        self.assertEqual(json.loads(body)['manifest'],first['manifest'])
        status,body,_=self.request('/api/intake/preparations',command,headers)
        self.assertEqual(status,200,body);self.assertTrue(json.loads(body)['replayed'])
        status,body,_=self.request(path)
        self.assertEqual(json.loads(body)['original_preparation_request_id'],'prepare')
        self.assertEqual(self.request(path+'&context_request_id=other')[0],400)
