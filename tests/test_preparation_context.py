"""Reviewed intake is exact, scoped, recoverable source selection, never fact authority."""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

from acquisition.bootstrap import build_intake
from acquisition.campaigns import CampaignBriefDraft, PreparationReview
from acquisition.creative import CompanyDraft, CompanyClaimDraft, validate_fact_pack
from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.adapters.sqlite.database import Database
from acquisition.adapters.sqlite.preparation_context import PREPARATION_CONTEXTS


class PreparationContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'app.sqlite';self.now=1000.
        self.app = build_intake(self.path,clock=lambda:self.now)
        self.company = self.app.save_company('one','writer','company',CompanyDraft(
            company_name='Aster Consultancy',product_name='Retail advice',description='Original wording \u2014 unchanged.',
            claims=(CompanyClaimDraft('A source claim','Subject to eligibility.',('https://aster.invalid/source',)),
                    CompanyClaimDraft('A second claim','Never implied by the first.',())),
            official_cta='Read the supplied terms',cta_url='https://aster.invalid/terms',
            source_urls=('https://aster.invalid/product',)))['snapshot']
        self.draft = CampaignBriefDraft(self.company['id'],1,objective='Find consultancy clients',audience='UK retail businesses',
            country='UK',currency='GBP',budget_minor=12345,channels=('email',),constraints=('Keep every qualification.',))
        self.brief = self.app.save_brief('one','writer','brief',self.draft)['snapshot']

    def preview(self, revision=1):
        return self.app.preparation.preview('one',self.brief['id'],revision)

    def review(self, preview=None, **values):
        p = preview or self.preview()
        return PreparationReview(p['brief']['id'],p['brief']['revision'],p['id'],p['context_revision'],
            tuple(c['id'] for c in p['claims'][:1]),True,True,7,'Checked the selected source wording.',confirmed=True,**values)

    def confirm(self, key='review', review=None):
        return self.app.preparation.confirm('one','writer',key,review or self.review())

    def count(self):
        with self.app.store.database.connect() as db:
            return db.execute('SELECT count(*) FROM preparation_contexts').fetchone()[0]

    def test_exact_selected_inputs_reopen_original_replay_and_no_execution_authority(self):
        review=self.review();first=self.confirm(review=review);context=first['context']
        self.assertTrue(first['current']);self.assertFalse(first['replayed'])
        self.assertEqual(context['selected_inputs']['description'],self.company['draft']['description'])
        self.assertEqual([c['statement'] for c in context['selected_inputs']['claims']],['A source claim'])
        self.assertEqual(context['selected_inputs']['claims'][0]['qualification'],'Subject to eligibility.')
        self.assertEqual(context['requirements'],self.brief['draft'])
        self.assertEqual(context['selected_inputs']['cta']['wording'],'Read the supplied terms')
        self.assertTrue(all(r['verification']=='reference_only_not_fetched' and r['checked_on'] is None for r in context['references']))
        self.assertEqual((context['verification'],context['approval'],context['generation'],context['authority']),
                         ('user_supplied_unverified','not_granted','unavailable','none'))
        with self.assertRaises(ValueError):validate_fact_pack(context,__import__('datetime').date(2026,11,24))
        self.app=build_intake(self.path,clock=lambda:1001.)
        replay=self.confirm(review=review);self.assertTrue(replay['replayed']);self.assertEqual(replay['context'],context)
        with self.assertRaises(Conflict):self.confirm(review=replace(review,review_note='Changed command'))
        self.assertEqual(self.count(),1)
        with self.app.store.database.connect() as db:
            for table in ('runs','tasks','model_calls','drafts','review_cases','review_decisions','simulated_agency_jobs'):
                self.assertEqual(db.execute('SELECT count(*) FROM '+table).fetchone()[0],0,table)

    def test_company_and_brief_changes_fence_preview_and_keep_old_context_historical(self):
        old=self.review()
        self.app.save_company('one','writer','edit',CompanyDraft(company_name='Changed company'),
                              company_id=self.company['id'],expected_revision=1)
        with self.assertRaises(Conflict):self.confirm(review=old)
        fresh=self.preview();self.assertEqual(fresh['company']['revision'],1);self.assertEqual(fresh['company_head_revision'],2)
        first=self.confirm(review=self.review(fresh));context=first['context']
        self.app.save_company('one','writer','edit-again',CompanyDraft(company_name='Another company edit'),
                              company_id=self.company['id'],expected_revision=2)
        changed=self.app.preparation.request('one','review')
        self.assertFalse(changed['current']);self.assertIn('Company information changed after this review.',changed['review_required'])
        self.app.save_brief('one','writer','edit-brief',replace(self.draft,objective='A new objective'),
                            brief_id=self.brief['id'],expected_revision=1)
        with self.assertRaises(Conflict):self.confirm('stale',self.review(fresh))
        self.assertFalse(self.app.preparation.request('one','review')['current'])
        self.assertEqual(self.confirm(review=self.review(fresh))['context'],context)
        second=self.confirm('new-review',self.review(self.preview(2)))
        self.assertEqual(second['context']['revision'],2)
        self.assertEqual(second['context']['source']['company'],self.company)
        self.assertEqual(context['requirements']['objective'],'Find consultancy clients')
        self.assertEqual(second['context']['requirements']['objective'],'A new objective')
        self.assertFalse(self.app.preparation.request('one','review')['current'])

    def test_questions_partial_input_unsupported_scope_and_unreferenced_claims_remain_visible(self):
        self.app.save_brief('one','writer','edit',replace(self.draft,objective='',country='France',currency='EUR',channels=('video',)),
                            brief_id=self.brief['id'],expected_revision=1)
        p=self.preview(2);review=replace(self.review(p),selected_claim_ids=tuple(c['id'] for c in p['claims']),
                                       issues=('The two supplied descriptions need clarification.',))
        r=self.confirm(review=review)['context']
        self.assertEqual(r['review_status'],'recorded_with_questions')
        self.assertTrue(r['missing_evidence']);self.assertTrue(r['requirements_readiness']['unsupported'])
        self.assertEqual((r['requirements']['country'],r['requirements']['currency'],r['requirements']['channels']),('France','EUR',['video']))
        self.assertEqual(r['reviewer_questions'],['The two supplied descriptions need clarification.'])
        self.assertEqual(r['verification'],'user_supplied_unverified')

    def test_foreign_sources_claims_and_consistently_forged_preview_have_no_effect(self):
        second=self.app.save_company('one','writer','other-company',CompanyDraft(company_name='Other',claims=(CompanyClaimDraft('Another claim'),)))['snapshot']
        b=self.app.save_brief('one','writer','other-brief',replace(self.draft,company_id=second['id']))['snapshot']
        other=self.app.preparation.preview('one',b['id'],1)
        for review in (replace(self.review(),selected_claim_ids=(other['claims'][0]['id'],)),
                       replace(self.review(),preview_id=other['id']),
                       replace(self.review(),expected_context_revision=4)):
            with self.subTest(review=review),self.assertRaises((Conflict,ValueError)):self.confirm(review=review)
        with self.assertRaises(NotFound):self.app.preparation.preview('foreign',self.brief['id'],1)
        with self.assertRaises(NotFound):self.app.preparation.confirm('foreign','writer','review',self.review())
        self.assertEqual(self.count(),0)
        second_review=replace(self.review(other),include_description=False,include_cta=False)
        second_context=self.confirm('other-review',second_review)['context']
        first_context=self.confirm()['context']
        self.assertNotEqual(first_context['id'],second_context['id'])
        self.assertEqual(first_context['selected_inputs']['company_name'],'Aster Consultancy')
        self.assertEqual(second_context['selected_inputs']['company_name'],'Other')
        self.assertEqual(second_context['selected_inputs']['claims'][0]['statement'],'Another claim')
        self.assertNotIn('iwoca',canonical(second_context).lower())

    def test_expiry_and_explicit_rereview_never_renew_a_replayed_receipt(self):
        review=self.review();original=self.confirm(review=review)['context']
        self.now=original['review_expires_at']
        replay=self.confirm(review=review);self.assertFalse(replay['current']);self.assertEqual(replay['context'],original)
        with self.assertRaises(Conflict):self.confirm('different-key',review)
        renewed=self.confirm('explicit-review',self.review(self.preview()))
        self.assertEqual(renewed['context']['revision'],2);self.assertGreater(renewed['context']['review_expires_at'],original['review_expires_at'])
        self.assertEqual(self.app.preparation.history('one',self.brief['id'])[1]['context'],original)

    def test_competing_process_stores_reconcile_same_request_and_fence_changed_review(self):
        from concurrent.futures import ThreadPoolExecutor
        import threading
        review=self.review();gate=threading.Barrier(2)
        def confirm(index):
            a=build_intake(self.path,clock=lambda:1000.);gate.wait(timeout=5)
            try:return a.preparation.confirm('one','writer','review',review)
            except Conflict:return 'conflict'
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(confirm,range(2)))
        self.assertEqual(sum(r['replayed'] for r in results),1);self.assertEqual(results[0]['context'],results[1]['context'])
        review=self.review(self.preview());gate=threading.Barrier(2)
        def competing(index):
            a=build_intake(self.path,clock=lambda:1001.);gate.wait(timeout=5)
            try:return a.preparation.confirm('one','writer','review-'+str(index),review)
            except Conflict:return 'conflict'
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(competing,range(2)))
        self.assertEqual(results.count('conflict'),1);self.assertEqual(self.count(),2)

    def test_process_exit_before_and_after_commit_replays_original_context(self):
        for point in ('before','after'):
            with self.subTest(point=point):
                path=Path(self.temp.name)/(point+'.sqlite');a=build_intake(path,clock=lambda:1000.)
                c=a.save_company('one','writer','c',CompanyDraft(company_name='Other product',description='Exact source.'))['snapshot']
                b=a.save_brief('one','writer','b',replace(self.draft,company_id=c['id']))['snapshot']
                p=a.preparation.preview('one',b['id'],1);review=replace(self.review(),brief_id=b['id'],preview_id=p['id'],selected_claim_ids=(),include_cta=False)
                program='''
import json,sys,os
from acquisition.bootstrap import build_intake
from acquisition.campaigns import PreparationReview
app=build_intake(sys.argv[1],clock=lambda:1000.)
data=json.loads(sys.argv[3]);data['selected_claim_ids']=tuple(data['selected_claim_ids']);data['issues']=tuple(data['issues'])
if sys.argv[2]=='before':app.preparation.store._view=lambda *args:os._exit(71)
app.preparation.confirm('one','writer','original',PreparationReview(**data))
os._exit(72)
'''
                proc=subprocess.run([sys.executable,'-c',program,str(path),point,canonical(asdict(review))],
                    env={**os.environ,'PYTHONPATH':'src'},capture_output=True,text=True,timeout=20)
                self.assertEqual(proc.returncode,71 if point=='before' else 72,proc.stderr)
                restarted=build_intake(path,clock=lambda:1001.)
                with restarted.store.database.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM preparation_contexts').fetchone()[0],0 if point=='before' else 1)
                r=restarted.preparation.confirm('one','writer','original',review)
                self.assertEqual(r['replayed'],point=='after')
                self.assertEqual(r['context']['reviewed_at'],1001. if point=='before' else 1000.)
                self.assertEqual(restarted.preparation.confirm('one','writer','original',review)['context'],r['context'])

    def test_immutable_history_and_independent_source_reconstruction_reject_rehashed_corruption(self):
        context=self.confirm()['context']
        with self.app.store.database.transaction() as db:
            for sql in ('UPDATE preparation_contexts SET revision=2','DELETE FROM preparation_contexts',
                        'INSERT OR REPLACE INTO preparation_contexts SELECT * FROM preparation_contexts'):
                with self.assertRaises(sqlite3.IntegrityError):db.execute(sql)
        from acquisition.campaigns import preparation_preview, reviewed_preparation
        company=json.loads(canonical(self.company));company['draft']['description']='An invented verified fact'
        preview=preparation_preview(company,self.brief,context['store_id'],1,0)
        review=replace(self.review(),preview_id=preview['id'],expected_context_revision=0)
        forged=reviewed_preparation(preview,review,'writer','review',1000.)
        with self.app.store.database.transaction() as db:
            db.execute('DROP TRIGGER preparation_context_no_update')
            db.execute('UPDATE preparation_contexts SET inputs=?,payload=?',
                       (canonical({'actor':'writer','review':asdict(review)}),canonical(forged)))
        with self.assertRaises(Conflict):self.app.preparation.request('one','review')

    def test_schema26_rollback_and_inspection_preserve_sources_and_store_identity(self):
        identity=self.app.store_identity()
        with self.app.store.database.transaction() as db:
            db.execute('DROP TABLE preparation_contexts');db.execute('PRAGMA user_version=26')
        apply=Database._apply_migration
        def fault(db,script):
            apply(db,script)
            if script==PREPARATION_CONTEXTS:raise OSError('after preparation DDL')
        with patch.object(Database,'_apply_migration',side_effect=fault),self.assertRaises(OSError):build_intake(self.path)
        with Database.existing(self.path).connect() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],26)
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_schema WHERE name='preparation_contexts'").fetchone())
        self.app=build_intake(self.path,clock=lambda:1000.)
        self.assertEqual(self.app.store_identity(),identity);self.assertEqual(self.app.company('one',self.company['id']),self.company)
        receipt=self.confirm();opened=build_intake(self.path,clock=lambda:1001.,read_only=True)
        self.assertEqual(opened.preparation.request('one','review')['context'],receipt['context'])
        self.assertFalse(opened.preparation.not_committed('one','missing'))
        with self.assertRaises(Conflict):opened.preparation.confirm('one','writer','new',self.review())

    def test_unpublished_preparation_schema26_preserves_original_receipt_through_atomic_upgrade(self):
        from acquisition.adapters.sqlite.youtube import YOUTUBE
        from acquisition.adapters.sqlite.preparation_context import legacy_preparation_preview
        review=self.review();original=self.confirm(review=review)['context'];identity=self.app.store_identity()
        with self.app.store.database.transaction() as db:
            for table in ('youtube_revocations','youtube_approvals','youtube_results','youtube_interactions',
                          'youtube_preparations','youtube_requests','youtube_revisions'):
                db.execute('DROP TABLE '+table)
            db.execute('PRAGMA user_version=26')
            payload=db.execute('SELECT payload FROM preparation_contexts').fetchone()[0]
            self.assertTrue(legacy_preparation_preview(db))
        inspection=build_intake(self.path,clock=lambda:1001.,read_only=True)
        self.assertEqual(inspection.preparation.request('one','review')['context'],original)
        apply=Database._apply_migration
        for stop in (YOUTUBE,PREPARATION_CONTEXTS):
            def fail(db,script):
                apply(db,script)
                if script==stop:raise OSError('after integrated migration DDL')
            with self.subTest(stop=stop),patch.object(Database,'_apply_migration',side_effect=fail),self.assertRaises(OSError):
                build_intake(self.path)
            with sqlite3.connect(self.path) as db:
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],26)
                self.assertEqual(db.execute('SELECT payload FROM preparation_contexts').fetchone()[0],payload)
                self.assertEqual(db.execute("SELECT name FROM sqlite_schema WHERE name LIKE 'youtube_%'").fetchall(),[])
        reopened=build_intake(self.path,clock=lambda:1002.)
        self.assertEqual(reopened.store_identity(),identity)
        replay=reopened.preparation.confirm('one','writer','review',review)
        self.assertTrue(replay['replayed']);self.assertEqual(replay['context'],original)
        with reopened.store.database.connect() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],27)
            self.assertEqual(db.execute('SELECT payload FROM preparation_contexts').fetchone()[0],payload)
            self.assertEqual(db.execute('SELECT count(*) FROM youtube_revisions').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM model_calls').fetchone()[0],0)

    def test_partial_or_modified_schema26_preview_is_rejected_without_migration(self):
        from acquisition.adapters.sqlite.preparation_context import legacy_preparation_preview
        self.confirm()
        for corruption in ('DROP TRIGGER preparation_context_no_update','CREATE TABLE youtube_partial(value TEXT)'):
            path=Path(self.temp.name)/('altered-'+str(len(corruption))+'.sqlite')
            with sqlite3.connect(self.path) as original,sqlite3.connect(path) as db:
                original.backup(db)
                for table in ('youtube_revocations','youtube_approvals','youtube_results','youtube_interactions',
                              'youtube_preparations','youtube_requests','youtube_revisions'):
                    db.execute('DROP TABLE '+table)
                db.execute('PRAGMA user_version=26');db.execute(corruption)
                before=db.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()
                self.assertFalse(legacy_preparation_preview(db))
            with self.subTest(corruption=corruption),self.assertRaises(sqlite3.DatabaseError):build_intake(path)
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],26)
                self.assertEqual(db.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall(),before)
