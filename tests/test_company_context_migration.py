"""New-work defaults and old-subject recovery use different, durable contracts."""
import json
import os
import subprocess
import sys
import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch
from pathlib import Path

from acquisition.bootstrap import build_workspace, build, build_intake, build_profile_preparation
from acquisition.adapters.sqlite.database import Database
from acquisition.campaigns import CampaignBriefDraft
from acquisition.creative import CompanyDraft
from acquisition.contracts import Conflict, canonical
from acquisition.conversations import CAPABILITY, FIXTURE_MESSAGE
from acquisition.reasoning import ModelConfig, ModelError
from test_conversations import PlannerModel
from test_intake_planning import IntakeModel
from acquisition.conversations import (
    COMPANY_CONTEXT_CONTRACT, LEGACY_COMPANY_CONTRACT, CompanyContextRequired,
)


NOW = 1794528000.0


class CompanyContextMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def workspace(self, **options):
        return build_workspace(self.root, real_clock=lambda: NOW, **options)

    def test_new_workspace_has_no_finance_product_default(self):
        workspace = self.workspace()
        self.assertNotIn('iwoca', json.dumps(workspace.knowledge()).lower())
        self.assertEqual(workspace.knowledge()['company_context']['status'], 'source_required')
        conversation = workspace.create_conversation('new', 'New campaign')
        self.assertEqual(conversation['product_contract'], COMPANY_CONTEXT_CONTRACT)
        with self.assertRaises(CompanyContextRequired):
            workspace.create('implicit-fixed-product', 'fixture')
        self.assertEqual(workspace.listing()['sessions'], [])

    def test_new_conversation_cannot_admit_the_fixed_product_planner(self):
        workspace = self.workspace()
        conversation = workspace.create_conversation('new', 'My product')
        workspace.message_conversation(conversation['id'], 'message', 0,
            'Prepare a £600 postal response experiment for my scheduling software.')
        with self.assertRaises(CompanyContextRequired):
            workspace.plan_conversation_fixture(conversation['id'], 'plan', 1)
        with closing(sqlite3.connect(self.root / 'conversations.sqlite')) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM model_calls').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM conversation_plans').fetchone()[0], 0)

    def test_saved_legacy_approval_and_create_replay_survive_current_defaults(self):
        legacy = self.workspace(new_work_contract=LEGACY_COMPANY_CONTRACT)
        original = legacy.create('existing', 'fixture')
        session = original['session']['id']
        subject = original['review']['subject']['id']
        approved = legacy.action(session, 'approve', {
            'request_id': 'approval', 'subject_id': subject,
            'reason': 'Reviewed the exact historical synthetic package.',
        })
        current = self.workspace()
        recovered = current.view(session)
        self.assertEqual(recovered['review']['subject'], approved['review']['subject'])
        self.assertEqual(recovered['review']['approval'], approved['review']['approval'])
        self.assertTrue(recovered['review']['approval_valid'])
        self.assertEqual(current.create('existing', 'fixture')['session']['id'], session)
        with self.assertRaises(CompanyContextRequired):
            current.create('different-new-request', 'fixture')

    def test_creation_replay_does_not_upgrade_a_legacy_conversation(self):
        legacy = self.workspace(new_work_contract=LEGACY_COMPANY_CONTRACT)
        original = legacy.create_conversation('existing', 'Saved conversation')
        current = self.workspace().create_conversation('existing', 'Saved conversation')
        self.assertEqual(current['id'], original['id'])
        self.assertEqual(current['product_contract'], LEGACY_COMPANY_CONTRACT)


    def downgrade_conversations_to_27(self, path):
        # Physical pre-migration layout, not a schema number on a current table.
        with closing(sqlite3.connect(path)) as db, db:
            db.execute('DROP TRIGGER conversation_company_contract_immutable')
            db.execute('DROP TRIGGER conversation_company_contract_no_replace')
            db.execute('ALTER TABLE conversations DROP COLUMN product_contract')
            db.execute('PRAGMA user_version=27')

    def test_schema27_migration_is_atomic_and_preserves_original_rows(self):
        path=self.root/'conversations.sqlite'
        app=build(path,clock=lambda:NOW)
        old=app.conversations.create('one','old','Historical')
        self.downgrade_conversations_to_27(path)
        with closing(sqlite3.connect(path)) as db:
            original=db.execute('SELECT * FROM conversations').fetchall()
        apply=Database._apply_migration
        def fail(db, script):
            apply(db,script)
            if 'user_version=28' in script:raise OSError('interrupted migration')
        with patch.object(Database,'_apply_migration',side_effect=fail):
            with self.assertRaises(OSError):Database(path)
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],27)
            self.assertEqual(db.execute('SELECT * FROM conversations').fetchall(),original)
        Database(path)
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],28)
            self.assertEqual(db.execute('SELECT organization,id,request_id,title,revision,created_at FROM conversations').fetchall(),original)
            self.assertEqual(db.execute('SELECT product_contract FROM conversations').fetchone()[0],LEGACY_COMPANY_CONTRACT)
        self.assertEqual(build(path).conversations.view('one',old['id'])['id'],old['id'])

    def test_contract_cannot_be_downgraded_by_update_or_replace(self):
        c=self.workspace().create_conversation('new','New company')
        path=self.root/'conversations.sqlite'
        with closing(sqlite3.connect(path)) as db:
            for replacement in (LEGACY_COMPANY_CONTRACT,None,'unsupported/v3'):
                with self.subTest(replacement=replacement):
                    # NULL must be rejected before OR REPLACE can apply the v1 default.
                    with self.assertRaises(sqlite3.IntegrityError):
                        db.execute('UPDATE OR REPLACE conversations SET product_contract=? WHERE id=?',(replacement,c['id']))
                    with self.assertRaises(sqlite3.IntegrityError):
                        db.execute("INSERT OR REPLACE INTO conversations SELECT organization,id,request_id,title,revision,created_at,? FROM conversations WHERE id=?",(replacement,c['id']))
        self.assertEqual(self.workspace().conversation(c['id'])['product_contract'],COMPANY_CONTEXT_CONTRACT)

    def test_native_planning_cannot_bypass_new_workspace_policy(self):
        w=self.workspace();c=w.create_conversation('new','New company')['id']
        w.message_conversation(c,'message',0,FIXTURE_MESSAGE)
        native=w._conversation_app()
        with self.assertRaises(CompanyContextRequired):
            native.conversations.plan_fixture('local-conversations',c,'bypass',1)
        with self.assertRaises(Conflict):
            w.route_followup(c,'route',1,'Prepare the campaign',False)
        self.assertIsNone(native.conversations.view('local-conversations',c)['current_plan'])

    def test_saved_provider_receipt_recovers_after_schema_upgrade_without_another_call(self):
        now=[NOW];model=PlannerModel();config=ModelConfig('test/model',max_calls=2,force_tool_choice=True)
        path=self.root/'conversations.sqlite'
        old=build(path,clock=lambda:now[0],gateway=model,model_config=config)
        c=old.conversations.create('local-conversations','old','Pinned old campaign')['id']
        old.conversations.message('local-conversations',c,'message',0,FIXTURE_MESSAGE)
        run=old.conversations.plan('local-conversations',c,'plan',1)
        claim=old.tasks.claim('local-conversations',now[0],60)
        output=old.worker.capabilities[CAPABILITY](claim)
        request=canonical(model.requests[0])
        with old.tasks.database.connect() as db:
            ledger=[tuple(r) for r in db.execute('SELECT request_hash,status,response FROM model_calls')]
            plan=db.execute('SELECT payload FROM conversation_plans').fetchone()[0]
        self.downgrade_conversations_to_27(path)
        now[0]+=61
        current=build_workspace(self.root,real_clock=lambda:now[0],gateway_factory=lambda:model)
        app=current._conversation_app(with_model=True,model_config=config)
        self.assertEqual(app.conversations.plan('local-conversations',c,'plan',1),run)
        app.worker.drain('local-conversations')
        self.assertEqual(app.tasks.inspect('local-conversations',run)['tasks'][0]['output'],output.data)
        self.assertEqual(len(model.requests),1)
        self.assertEqual(canonical(model.requests[0]),request)
        with app.tasks.database.connect() as db:
            self.assertEqual([tuple(r) for r in db.execute('SELECT request_hash,status,response FROM model_calls')],ledger)
            self.assertEqual(db.execute('SELECT payload FROM conversation_plans').fetchone()[0],plan)

    def test_current_company_intake_plans_with_its_own_sources(self):
        model=IntakeModel();w=self.workspace(gateway_factory=lambda:model)
        intake=build_intake(self.root/'conversations.sqlite',clock=lambda:NOW)
        company=intake.save_company('local-conversations','local-operator','company',CompanyDraft(
            company_name='Aster Consultancy',description='Operations advice supplied by the user.'))['snapshot']
        brief=intake.save_brief('local-conversations','local-operator','brief',CampaignBriefDraft(
            company['id'],1,objective='Find operations consulting clients',audience='UK retailers',
            country='UK',currency='GBP',budget_minor=5000,channels=('email',)))['snapshot']
        result=w.request_intake_plan('plan',brief['id'],1,True)
        self.assertEqual(result['plan']['status'],'succeeded',result)
        self.assertEqual(result['source']['company'],company)
        # The pinned intake/v1 system prompt retains its original negative example.
        self.assertNotIn('iwoca',model.requests[0]['messages'][1]['content'].lower())
        with intake.store.database.connect() as db:
            self.assertEqual(db.execute('SELECT product_contract FROM conversations').fetchone()[0],COMPANY_CONTEXT_CONTRACT)
            self.assertEqual(db.execute('SELECT count(*) FROM review_decisions').fetchone()[0],0)

    def test_fictional_profile_v2_is_a_distinct_unapproved_proposal(self):
        from datetime import datetime,timezone
        current=datetime(2026,11,27,12,tzinfo=timezone.utc).timestamp()
        app=build_profile_preparation(self.root/'fictional.sqlite','one','fielddesk',clock=lambda:current,profile_version='v2')
        proposal=app.prepare('one','proposal','fielddesk','v2',objective='response_experiment',budget_pence=5000,
            segments=('maintenance','installations'),country='UK',currency='GBP',channel='direct_mail',size=20,seed=42)
        self.assertNotIn('iwoca',canonical(proposal).lower())
        self.assertEqual(proposal['plan']['profile']['version'],'v2')
        with app.proposals.database.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM review_decisions').fetchone()[0],0)


    def test_new_sequence_prepares_current_fielddesk_and_recovers_its_version(self):
        from datetime import datetime,timezone
        current=datetime(2026,11,27,12,tzinfo=timezone.utc).timestamp()
        w=build_workspace(self.root,real_clock=lambda:current)
        c=w.create_conversation('demo','Fictional sequence')['id']
        view=w.message_conversation(c,'message',0,
            'Prepare a £60 Fielddesk email, human call and followup sequence using the primary CRM.')
        journey=w.sequence_journeys.store.get('local-conversations',view['sequence_journeys'][0]['id'])
        self.assertEqual(journey['inputs']['interpretation']['outcome'],'sequence',journey)
        self.assertEqual([p['key'] for p in journey['inputs']['catalogue']['profiles']],['fielddesk'])
        self.assertEqual(journey['inputs']['catalogue']['profiles'][0]['profile_version'],'v2')
        for _ in range(15):
            w.sequence_journeys.advance('local-conversations',journey['id'])
            row=w.sequence_journeys.store.get('local-conversations',journey['id'])
            if row['status'] in {'ready','blocked'}:break
        self.assertEqual(row['status'],'ready',row)
        reopened=build_workspace(self.root,real_clock=lambda:current)
        saved=reopened.sequence_journeys.view('local-conversations',journey['id'])
        self.assertEqual(saved['status'],'ready',saved)
        self.assertEqual(reopened.sequence_journeys.store.get('local-conversations',journey['id'])['inputs'],journey['inputs'])


    def test_legacy_catalogue_substitution_rolls_back_the_new_message(self):
        from acquisition.bootstrap import build_sequence_journeys
        w=self.workspace();c=w.create_conversation('new','New campaign')['id']
        legacy=build_sequence_journeys(self.root/'conversations.sqlite',lambda:NOW)
        with self.assertRaisesRegex(Conflict,'current fictional catalogue'):
            legacy.send('local-conversations',c,'bypass',0,
                'Prepare a £60 iwoca email and human call sequence using primary CRM.')
        self.assertEqual(w.conversation(c)['revision'],0)
        with legacy.store.database.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM sequence_journeys').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM model_calls').fetchone()[0],0)

    def test_unknown_provider_result_is_not_repeated_after_upgrade(self):
        now=[NOW];model=PlannerModel();config=ModelConfig('test/model',max_calls=2,force_tool_choice=True)
        calls=[]
        def uncertain(request):
            calls.append(request)
            raise ModelError('provider_outcome_unknown')
        model.complete=uncertain
        path=self.root/'conversations.sqlite'
        app=build(path,clock=lambda:now[0],gateway=model,model_config=config)
        c=app.conversations.create('local-conversations','old','Old uncertain request')['id']
        app.conversations.message('local-conversations',c,'message',0,FIXTURE_MESSAGE)
        run=app.conversations.plan('local-conversations',c,'plan',1)
        app.worker.drain('local-conversations',run_id=run)
        self.assertEqual(len(calls),1)
        self.downgrade_conversations_to_27(path)
        now[0]+=1000
        current=build_workspace(self.root,real_clock=lambda:now[0],gateway_factory=lambda:model)
        recovered=current._conversation_app(with_model=True,model_config=config)
        self.assertEqual(recovered.conversations.plan('local-conversations',c,'plan',1),run)
        recovered.worker.drain('local-conversations',run_id=run)
        self.assertEqual(len(calls),1)
        self.assertIsNone(recovered.conversations.view('local-conversations',c)['current_plan']['result'])


    def test_cli_defaults_to_fictional_proposal_and_requires_legacy_creation_opt_in(self):
        path=self.root/'cli.sqlite'
        program="""
import acquisition.bootstrap as b
from acquisition.entrypoints.cli import main
from unittest.mock import patch
original=b.build_profile_preparation
with patch.object(b,'build_profile_preparation',side_effect=lambda *a,**kw:original(*a,clock=lambda:1795780800.,**kw)):
 main()
"""
        env=dict(os.environ,PYTHONPATH=str(Path('src').resolve()),OPENROUTER_API_KEY='offline-must-not-call')
        def cli(*args):
            return subprocess.run([sys.executable,'-c',program,'--db',str(path),*args],
                capture_output=True,text=True,env=env,timeout=30)
        rejected=cli('create')
        self.assertEqual(rejected.returncode,2,rejected.stderr)
        self.assertIn('legacy-product-contract',rejected.stderr)
        self.assertFalse(path.exists())
        first=cli('demo','--size','20')
        self.assertEqual(first.returncode,0,first.stderr)
        result=json.loads(first.stdout)
        self.assertEqual(result['contract'],COMPANY_CONTEXT_CONTRACT)
        self.assertEqual(result['proposal']['approval'],'not_granted')
        again=cli('demo','--size','20')
        self.assertEqual(again.returncode,0,again.stderr)
        self.assertEqual(json.loads(again.stdout)['proposal']['draft_id'],result['proposal']['draft_id'])
        with closing(sqlite3.connect(path)) as db:
            for table in ('runs','model_calls','review_decisions','simulated_agency_jobs'):
                self.assertEqual(db.execute('SELECT count(*) FROM '+table).fetchone()[0],0)


    def test_crm_mapping_change_cannot_renew_legacy_recipient_evidence(self):
        from dataclasses import asdict
        from acquisition.audiences import contact_snapshot_from
        from acquisition.bootstrap import build_contact_directory
        from acquisition.adapters.recipient_fixtures import synthetic_recipient_evidence
        directory=build_contact_directory(self.root/'old.sqlite','one','fielddesk',lambda:NOW)
        original=directory.source.read('one','fielddesk-crm-a',1)
        remapped=contact_snapshot_from(json.loads(canonical(asdict(original)).replace('mapping-v1','mapping-v2')))
        # The mapping label is not an authored product/context version selector.
        first=next(synthetic_recipient_evidence(original))
        second=next(synthetic_recipient_evidence(remapped))
        self.assertEqual((first.observed_at,first.expires_at),(second.observed_at,second.expires_at))


if __name__ == '__main__':
    unittest.main()
