"""Intake conservation across scope, revision, transaction failure and process loss."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from acquisition.adapters.sqlite.database import Database
from acquisition.adapters.sqlite.intake import SqliteCampaignIntake, INTAKE
from acquisition.bootstrap import build_intake
from acquisition.campaigns import CampaignBriefDraft, CampaignIntake
from acquisition.contracts import Conflict, NotFound
from acquisition.creative import CompanyDraft, CompanyClaimDraft


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'application.sqlite'
        self.app = build_intake(self.path, clock=lambda: 123)

    def company(self, app=None, org='one', key='company', draft=None):
        return (app or self.app).save_company(org, 'writer', key, draft or CompanyDraft(
            company_name='Example', product_name='Product', website='https://example.invalid',
            claims=(CompanyClaimDraft('User claim', 'Qualification', ('https://example.invalid/source',)),)))

    def brief(self, company, **changes):
        return CampaignBriefDraft(company['id'], company['revision'], objective='Find customers',
                                  audience='Small businesses', **changes)

    def rows(self):
        with Database.existing(self.path).connect() as db:
            return {t: [tuple(r) for r in db.execute('SELECT * FROM '+t+' ORDER BY rowid')]
                    for t in ('intake_company_revisions', 'intake_brief_revisions', 'intake_requests')}

    def test_reopen_history_pinned_brief_and_no_execution_effects(self):
        source = 'Fast, flexible funding \u2014 subject to eligibility.'
        company = CompanyDraft(
            company_name='Example \u2014 Company', product_name='Product \u2014 One',
            description=source, official_cta='Learn more \u2014 apply',
            claims=(CompanyClaimDraft(source, 'Eligibility \u2014 UK businesses only'),))
        first = self.company(draft=company)['snapshot']
        draft = replace(self.brief(first, country='France', currency='EUR', channels=('video',), budget_minor=12345),
                        objective=source, audience='Small businesses \u2014 growing teams',
                        constraints=('Keep qualifications \u2014 do not shorten',))
        saved = self.app.save_brief('one', 'writer', 'brief', draft)['snapshot']
        second = self.app.save_company('one', 'editor', 'edit', CompanyDraft(company_name='New wording'),
                                       company_id=first['id'], expected_revision=1)['snapshot']
        reopened = build_intake(self.path)
        self.assertEqual(reopened.company('one', first['id']), second)
        self.assertEqual(reopened.company('one', first['id'], 1), first)
        self.assertEqual(reopened.brief('one', saved['id']), saved)
        company_input = reopened.company('one', first['id'], 1)['draft']
        self.assertEqual(company_input['company_name'], 'Example \u2014 Company')
        self.assertEqual(company_input['product_name'], 'Product \u2014 One')
        self.assertEqual(company_input['description'], source)
        self.assertEqual(company_input['official_cta'], 'Learn more \u2014 apply')
        self.assertEqual(company_input['claims'], [{'statement': source,
                         'qualification': 'Eligibility \u2014 UK businesses only', 'source_urls': []}])
        brief_input = reopened.brief('one', saved['id'])['draft']
        self.assertEqual(brief_input['objective'], source)
        self.assertEqual(brief_input['audience'], 'Small businesses \u2014 growing teams')
        self.assertEqual(brief_input['constraints'], ['Keep qualifications \u2014 do not shorten'])
        # A fresh interpreter must observe the same original source wording.
        program = '''
import json, sys
from acquisition.bootstrap import build_intake
app = build_intake(sys.argv[1], read_only=True)
print(json.dumps([app.company('one', sys.argv[2], 1), app.brief('one', sys.argv[3])]))
'''
        result = subprocess.run([sys.executable, '-c', program, str(self.path), first['id'], saved['id']],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [first, saved])
        self.assertEqual(reopened.save_company('one', 'writer', 'company', company)['snapshot'], first)
        self.assertEqual(reopened.save_brief('one', 'writer', 'brief', draft)['snapshot'], saved)
        with self.assertRaises(Conflict):
            reopened.save_brief('one', 'writer', 'brief', replace(draft, objective=source.replace('\u2014', '-')))
        self.assertEqual(saved['draft']['company_revision'], 1)
        self.assertEqual(saved['draft']['country'], 'France')
        self.assertEqual(saved['draft']['channels'], ['video'])
        self.assertEqual(saved['execution_readiness'], 'not_assessed')
        self.assertEqual(saved['authority'], 'none')
        self.assertEqual(first['provenance'], 'user_supplied_unverified')
        self.assertEqual(second['actor'], 'editor')
        with Database.existing(self.path).connect() as db:
            for table in ('runs', 'tasks', 'model_calls', 'drafts', 'review_decisions', 'simulated_agency_jobs'):
                self.assertEqual(db.execute('SELECT count(*) FROM '+table).fetchone()[0], 0, table)

    def test_exact_request_replay_remains_original_after_later_edits(self):
        original = self.company()
        first = original['snapshot']
        self.app.save_company('one', 'writer', 'edit', CompanyDraft(company_name='Later'),
                              company_id=first['id'], expected_revision=1)
        before = self.rows()
        self.assertEqual(self.company(), original | {'replayed': True})
        brief = self.brief(first)
        receipt = self.app.save_brief('one', 'writer', 'brief', brief)
        self.app.save_brief('one', 'writer', 'brief-edit', replace(brief, objective='New objective'),
                           brief_id=receipt['snapshot']['id'], expected_revision=1)
        self.assertEqual(self.app.save_brief('one', 'writer', 'brief', brief), receipt | {'replayed': True})
        after = self.rows()
        with self.assertRaises(Conflict):
            self.company(draft=CompanyDraft(company_name='Changed'))
        with self.assertRaises(Conflict):
            self.app.save_company('one', 'other-actor', 'company', CompanyDraft())
        with self.assertRaises(Conflict):
            self.app.save_brief('one', 'writer', 'company', brief)
        with self.assertRaises(Conflict):
            self.app.save_brief('one', 'writer', 'brief', replace(brief, company_revision=2))
        self.assertEqual(self.rows(), after)
        self.assertEqual(before['intake_company_revisions'], after['intake_company_revisions'])

    def test_cross_organization_reads_edits_and_company_reference_substitution(self):
        one = self.company()['snapshot']
        two = self.company(org='two')['snapshot']
        b = self.app.save_brief('one', 'writer', 'brief', self.brief(one))['snapshot']
        self.assertNotEqual(one['id'], two['id'])
        before = self.rows()
        for read, identity in ((self.app.company, one['id']), (self.app.brief, b['id'])):
            for revision in (None, 1):
                with self.assertRaises(NotFound):read('two', identity, revision)
        with self.assertRaises(NotFound):
            self.app.save_company('two', 'writer', 'foreign-edit', CompanyDraft(), company_id=one['id'], expected_revision=1)
        with self.assertRaises(NotFound):
            self.app.save_brief('two', 'writer', 'foreign-brief-edit', self.brief(two), brief_id=b['id'], expected_revision=1)
        with self.assertRaises(NotFound):
            self.app.save_brief('two', 'writer', 'foreign-reference', self.brief(one))
        with self.assertRaises(NotFound):
            self.app.save_brief('one', 'writer', 'missing-revision', replace(self.brief(one), company_revision=2))
        self.assertEqual(self.rows(), before)
        self.assertEqual(self.app.companies('two'), [two])
        self.assertEqual(self.app.briefs('two'), [])

    def test_concurrent_duplicate_creates_and_stale_edits_have_one_effect(self):
        gate = threading.Barrier(2)
        def create(_):
            app = build_intake(self.path)
            gate.wait(timeout=5)
            return self.company(app)
        with ThreadPoolExecutor(2) as pool:
            created = list(pool.map(create, range(2)))
        self.assertEqual(created[0]['snapshot'], created[1]['snapshot'])
        self.assertEqual(sorted(r['replayed'] for r in created), [False, True])
        first = created[0]['snapshot']
        brief = self.app.save_brief('one', 'writer', 'brief', self.brief(first))['snapshot']
        for kind, snapshot in (('company', first), ('brief', brief)):
            gate = threading.Barrier(2)
            def edit(index):
                app = build_intake(self.path)
                gate.wait(timeout=5)
                try:
                    if kind == 'company':
                        return app.save_company('one', 'writer', 'edit-'+str(index), CompanyDraft(company_name=str(index)),
                                                 company_id=snapshot['id'], expected_revision=1)
                    return app.save_brief('one', 'writer', 'brief-edit-'+str(index), replace(self.brief(first), objective=str(index)),
                                           brief_id=snapshot['id'], expected_revision=1)
                except Conflict:return 'conflict'
            with ThreadPoolExecutor(2) as pool:
                results = list(pool.map(edit, range(2)))
            self.assertEqual(results.count('conflict'), 1)
            read = self.app.company if kind == 'company' else self.app.brief
            self.assertEqual(read('one', snapshot['id'])['revision'], 2)

    def test_failure_before_receipt_rolls_back_revision_and_retry_succeeds(self):
        first = self.company()['snapshot']
        before = self.rows()
        with Database.existing(self.path).transaction() as db:
            db.execute("CREATE TRIGGER fail_intake BEFORE INSERT ON intake_requests BEGIN SELECT RAISE(ABORT,'injected'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.app.save_brief('one', 'writer', 'brief', self.brief(first))
        self.assertEqual(self.rows(), before)
        with Database.existing(self.path).transaction() as db:db.execute('DROP TRIGGER fail_intake')
        self.assertEqual(self.app.save_brief('one', 'writer', 'brief', self.brief(first))['snapshot']['revision'], 1)

    def test_process_exit_before_commit_rolls_back_and_after_commit_replays(self):
        for exit_after_commit in (False, True):
            key = 'committed' if exit_after_commit else 'uncommitted'
            program = '''
import os
from contextlib import contextmanager
from acquisition.bootstrap import build_intake
from acquisition.creative import CompanyDraft
app=build_intake(os.environ['INTAKE_PATH'],clock=lambda:123)
database=app.store.database
original=database.transaction
@contextmanager
def transaction():
    with original() as db:
        yield db
        if os.environ['AFTER']=='False':os._exit(91)
    os._exit(92)
database.transaction=transaction
app.save_company('one','writer',os.environ['KEY'],CompanyDraft(company_name='Restart'))
'''
            env = dict(os.environ, INTAKE_PATH=str(self.path), KEY=key, AFTER=str(exit_after_commit), PYTHONPATH='src')
            result = subprocess.run([sys.executable, '-c', program], env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 92 if exit_after_commit else 91, result.stderr)
            reopened = build_intake(self.path, clock=lambda:999)
            receipt = reopened.save_company('one', 'writer', key, CompanyDraft(company_name='Restart'))
            self.assertEqual(receipt['replayed'], exit_after_commit)
            self.assertEqual(receipt['snapshot']['saved_at'], 123 if exit_after_commit else 999)
            self.assertEqual(receipt['snapshot']['revision'], 1)

    def test_history_rejects_update_delete_and_replace(self):
        first = self.company()['snapshot']
        self.app.save_brief('one', 'writer', 'brief', self.brief(first))
        before = self.rows()
        for table, rows in before.items():
            for sql, args in ((f"UPDATE {table} SET organization='changed'", ()),
                              (f'DELETE FROM {table}', ()),
                              (f'INSERT OR REPLACE INTO {table} VALUES('+','.join('?' for _ in rows[0])+')', rows[0])):
                with self.assertRaises(sqlite3.IntegrityError), Database.existing(self.path).transaction() as db:
                    db.execute(sql, args)
        self.assertEqual(self.rows(), before)

    def test_schema23_upgrade_rollback_retry_and_historical_rows_unchanged(self):
        with Database.existing(self.path).transaction() as db:
            for table in ('intake_requests', 'intake_brief_revisions', 'intake_company_revisions'):
                db.execute('DROP TABLE '+table)
            db.execute('PRAGMA user_version=23')
            db.execute("INSERT INTO conversations VALUES('old','chat','request','Preserved',0,123)")
            identity = db.execute('SELECT * FROM application_store_identity').fetchall()
        original = Database._apply_migration
        def fail(db, script):
            original(db, script)
            if script == INTAKE:raise OSError('after intake DDL')
        with patch.object(Database, '_apply_migration', side_effect=fail):
            with self.assertRaises(OSError):Database(self.path)
        with Database.existing(self.path).connect() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 23)
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='intake_requests'").fetchone())
        build_intake(self.path)
        with Database.existing(self.path).connect() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 25)
            self.assertEqual([tuple(r) for r in db.execute('SELECT * FROM conversations')], [('old','chat','request','Preserved',0,123)])
            self.assertEqual([tuple(r) for r in db.execute('SELECT * FROM application_store_identity')], [tuple(r) for r in identity])
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_partial_drafts_pagination_input_bounds_and_inspection_opening(self):
        for index in range(3):self.company(key='company-'+str(index), draft=CompanyDraft())
        page = self.app.companies('one', limit=2)
        tail = self.app.companies('one', after_id=page[-1]['id'], limit=2)
        self.assertEqual(len(page+tail), 3)
        self.assertEqual(len({r['id'] for r in page+tail}), 3)
        inspection = build_intake(self.path, read_only=True)
        self.assertEqual(inspection.companies('one'), page+tail)
        with self.assertRaises(Conflict):self.company(inspection)
        for kwargs in ({'budget_minor': True}, {'budget_minor': -1}, {'company_revision': True}, {'channels': ['email']}, {'contact_source':'crm'}):
            with self.assertRaises(ValueError):CampaignBriefDraft(**({'company_id':'company', 'company_revision':1} | kwargs))
        for kwargs in ({'website':'https://token@example.invalid'}, {'website':'javascript:alert(1)'}, {'claims':[]},
                       {'company_name':'x'*601}, {'company_name':'Line\x00Break'}, {'company_name':' Example '}):
            with self.assertRaises(ValueError):CompanyDraft(**kwargs)
        for args in ({'expected_revision':True}, {'expected_revision':1}, {'company_id':'one','expected_revision':0}):
            with self.assertRaises(ValueError):self.app.save_company('one','writer','bad',CompanyDraft(),**args)
        with self.assertRaises(ValueError):
            self.company(draft=CompanyDraft(description='é'*8000, claims=tuple(CompanyClaimDraft('x'*4000) for _ in range(20))))


if __name__ == '__main__':
    unittest.main()
