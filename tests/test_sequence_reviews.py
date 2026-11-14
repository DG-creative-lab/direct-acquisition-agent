"""Exact approval and truthful output boundaries, exercised through real SQLite."""

import copy
from contextlib import closing
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_sequences as fixtures
from acquisition.adapters.sqlite.database import Database
from acquisition.adapters.sqlite.reviews import SqliteReviews
from acquisition.adapters.sqlite.simulated_delivery import SqliteSimulatedDelivery
from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.reviews import sequence_validation, SEQUENCE_CHECKS, validate_sequence_output


class SequenceReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.SequenceTests.setUpClass()
        cls.templates = fixtures.SequenceTests.templates

    @classmethod
    def tearDownClass(cls): fixtures.SequenceTests.tearDownClass()

    setUp = fixtures.SequenceTests.setUp
    copy_template = fixtures.SequenceTests.copy_template
    app = fixtures.SequenceTests.app
    request = fixtures.SequenceTests.request
    prepare = fixtures.SequenceTests.prepare
    approve = fixtures.SequenceTests.approve
    start = fixtures.SequenceTests.start
    counts = fixtures.SequenceTests.counts

    def roles(self, app):
        roles = SqliteReviews(app.campaigns.store.database,lambda:self.now,SqliteSimulatedDelivery)
        roles.register_actor('one','operator',('operator',))
        roles.register_actor('one','reviewer',('reviewer',))
        return roles

    def reviewed(self, key='review', **changes):
        app=self.app();proposal=self.prepare(app,key,**changes)
        approval=self.approve(app,proposal,key)
        return app,proposal,approval

    def durable_counts(self):
        with closing(sqlite3.connect(self.path)) as db:
            names = [r[0] for r in db.execute("SELECT name FROM sqlite_schema WHERE type='table' AND (name LIKE 'sequence_review_%' OR name='sequence_simulation_approvals')")]
            return {name:db.execute('SELECT count(*) FROM '+name).fetchone()[0] for name in names} | self.counts()

    def test_absent_purpose_and_other_proposal_approvals_never_admit_simulation(self):
        app,proposal,approval=self.reviewed()
        other=self.prepare(app,'other')
        before=self.durable_counts()
        for identity in (None,'confidence_0.99','validation_passed','skill_contextual-email/v1','decision_postal',approval['id']):
            with self.subTest(identity=identity),self.assertRaises((Conflict,NotFound)):
                app.engagements.start('one','blocked',other['proposal_id'],identity)
            self.assertEqual(self.durable_counts(),before)
        with self.assertRaises(NotFound):app.reviews.view('two',approval['subject_id'])
        with self.assertRaises(NotFound):app.reviews.decide('one','wrong-purpose','subject_postal','reviewer','approve','reviewed',100)
        app.engagements.start('one','exact',proposal['proposal_id'],approval['id'])
        self.assertEqual(self.counts()['engagement_enrollments'],2)

    def test_one_approval_covers_both_arms_and_controls_across_restart(self):
        app,proposal,approval=self.reviewed(decision_request='controlled')
        simulation=app.engagements.start('one','start',proposal['proposal_id'],approval['id'])['simulation_id']
        first=app.engagements.advance('one',simulation)
        self.assertEqual(first['totals']['accepted'],1)
        self.assertEqual(len(first['enrollments']),2)
        self.now+=20
        calls=self.app().engagements.advance('one',simulation)
        task=next(s for s in calls['steps'] if s['channel']=='human_call')
        self.app().engagements.observe('one','completed',simulation,task['id'],task['submission']['provider_effect_id'],'task_completed',self.now)
        self.now+=20
        complete=self.app().engagements.advance('one',simulation)
        self.assertEqual(complete['totals']['accepted'],3)
        self.assertEqual(complete['status'],'submissions_complete')
        self.assertEqual({s['contact_id'] for s in complete['steps']},{m['contact_id'] for m in proposal['saved']['population'] if m['arm']!='no_contact'})
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM sequence_review_decisions').fetchone()[0],1)
        # A new process can read and replay, but never submit a second effect.
        code='''import json,sys
from acquisition.bootstrap import build_sequence_simulation
app=build_sequence_simulation(sys.argv[1],'one','fielddesk',lambda:1794614440.)
print(json.dumps(app.engagements.advance('one',sys.argv[2])))'''
        process=subprocess.run([sys.executable,'-c',code,str(self.path),simulation],cwd=fixtures.ROOT,text=True,capture_output=True)
        self.assertEqual(process.returncode,0,process.stderr)
        self.assertEqual(json.loads(process.stdout),complete)

    def test_required_membership_and_all_nonpassing_statuses_withhold_substantive_output(self):
        app,proposal,approval=self.reviewed()
        store=app.reviews.store
        with store.database.connect() as db: subject=store._subject(db,'one',approval['subject_id'])
        passed=[{'id':name,'required':True,'status':'passed'} for name in sorted(SEQUENCE_CHECKS)]
        for name in sorted(SEQUENCE_CHECKS):
            for status in ('failed','unknown','not_evaluated','omitted'):
                with self.subTest(check=name,status=status):
                    checks=[c|{'status':status} if c['id']==name else c for c in passed if status!='omitted' or c['id']!=name]
                    report=sequence_validation(subject,checks,self.now)
                    self.assertFalse(report['review_ready'])
                    self.assertEqual({c['id'] for c in report['checks']},set(SEQUENCE_CHECKS))
                    with self.assertRaises(Conflict):validate_sequence_output(subject,report,{})
            downgraded=[c|{'required':False} if c['id']==name else c for c in passed]
            with self.assertRaises(ValueError):sequence_validation(subject,downgraded,self.now)
        with patch.object(store,'_payloads',side_effect=RuntimeError('checker crashed')):
            view=app.reviews.view('one',approval['subject_id'])
            self.assertFalse(view['validation']['review_ready']);self.assertFalse(view['approval_valid'])
            self.assertIsNone(view['summary']);self.assertIsNone(view['sequence'])
            check=next(c for c in view['validation']['checks'] if c['id']=='recipient_payloads')
            self.assertEqual(check['status'],'unknown')
            before=self.durable_counts()
            with self.assertRaises(Conflict):app.reviews.decide('one','crashed',approval['subject_id'],'reviewer','approve','No unchecked approval',100)
            self.assertEqual(self.durable_counts(),before)
            with self.assertRaises(Conflict):app.engagements.start('one','crashed',proposal['proposal_id'],approval['id'])

    def test_exact_operator_facts_reject_praise_missing_population_and_stale_subject(self):
        app,proposal,approval=self.reviewed()
        view=app.reviews.view('one',approval['subject_id']);output=view['summary']
        self.assertEqual(app.reviews.validate_output('one',approval['subject_id'],output),output)
        for mutation in ('praise','count','cost','subject','missing'):
            changed=copy.deepcopy(output)
            if mutation=='praise':changed['summary']='Everything is ready. Excellent campaign.'
            if mutation=='count':changed['counts']['controls']+=1
            if mutation=='cost':changed['limits']['maximum_cost_pence']=0
            if mutation=='subject':changed['subject_id']='another-subject'
            if mutation=='missing':del changed['counts']
            with self.subTest(mutation=mutation),self.assertRaises(Conflict):app.reviews.validate_output('one',approval['subject_id'],changed)
        contacts=app.campaigns.store.contacts
        person=proposal['saved']['population'][0]['contact_id']
        from acquisition.bootstrap import build_contact_directory
        build_contact_directory(self.path,'one','fielddesk',lambda:self.now).object('one','objection',person,'email','acquisition','Stop')
        with self.assertRaises(Conflict):app.reviews.validate_output('one',approval['subject_id'],output)
        stale=app.reviews.view('one',approval['subject_id'])
        self.assertTrue(stale['content_withheld']);self.assertIsNone(stale['summary'])
        self.assertEqual(stale['proposal_id'],proposal['proposal_id'])

    def test_reviewer_disable_reenable_and_expiry_block_stale_authority(self):
        for reason in ('generation','expiry','revocation','later_reject'):
            with self.subTest(reason=reason):
                self.path=Path(self.temp.name)/(reason+'.sqlite');self.copy_template();self.now=fixtures.NOW
                app,proposal,approval=self.reviewed()
                simulation=app.engagements.start('one','start',proposal['proposal_id'],approval['id'])['simulation_id']
                if reason=='generation':
                    roles=self.roles(app)
                    roles.register_actor('one','reviewer',('reviewer',),False)
                    roles.register_actor('one','reviewer',('reviewer',),True)
                elif reason=='expiry':self.now=approval['expires_at']
                elif reason=='revocation':app.reviews.revoke('one','revoke',approval['id'],'reviewer','Stop sequence')
                else:app.reviews.decide('one','reject',approval['subject_id'],'reviewer','reject','Withheld approval',100)
                current=self.app().reviews.view('one',approval['subject_id'])
                self.assertFalse(current['approval_valid'])
                with patch.object(app.engagements.email,'submit',side_effect=AssertionError('unauthorized provider call')) as provider:
                    result=app.engagements.advance('one',simulation)
                self.assertEqual(provider.call_count,0)
                self.assertEqual(result['totals']['accepted'],0)
                self.assertEqual(result['totals']['states']['blocked'],6)
                replay=app.reviews.decide('one','review-approve',approval['subject_id'],'reviewer','approve','Exact synthetic population and sequence reviewed',7*86400)
                self.assertEqual(replay['observation'],'historical_receipt')
                with self.assertRaises(Conflict):app.engagements.start('one','reuse',proposal['proposal_id'],approval['id'])

    def test_changed_sender_account_or_scope_and_materialized_byte_prevent_effects(self):
        for change in ('sender','account','scope','payload'):
            with self.subTest(change=change):
                self.path=Path(self.temp.name)/(change+'.sqlite');self.copy_template();self.now=fixtures.NOW
                app,proposal,approval=self.reviewed();simulation=app.engagements.start('one','start',proposal['proposal_id'],approval['id'])['simulation_id']
                store=app.campaigns.store
                if change!='payload':
                    field={'sender':'destination','account':'account','scope':'profile_key'}[change]
                    store.connections['email']=replace(store.connections['email'],**{field:'other'})
                    view=app.reviews.view('one',approval['subject_id'])
                else:
                    # Corrupt a durable payload under its original identity. No saved status can excuse a changed byte.
                    with store.database.transaction() as db:
                        db.execute('DROP TRIGGER channel_artifacts_immutable_update')
                        row=db.execute('SELECT id,payload FROM channel_artifacts LIMIT 1').fetchone()
                        data=json.loads(row['payload']);data['rendered'][0]['id']='changed'
                        db.execute('UPDATE channel_artifacts SET payload=? WHERE id=?',(canonical(data),row['id']))
                    view=app.reviews.view('one',approval['subject_id'])
                self.assertFalse(view['validation']['review_ready']);self.assertTrue(view['content_withheld'])
                result=app.engagements.advance('one',simulation)
                self.assertEqual(result['totals']['accepted'],0);self.assertEqual(self.counts()['engagement_dispatches'],0)

    def test_revocation_during_submission_keeps_observation_but_blocks_completion_and_next_effect(self):
        app,proposal,approval=self.reviewed();simulation=app.engagements.start('one','start',proposal['proposal_id'],approval['id'])['simulation_id']
        submit=app.engagements.email.submit
        def revoke(intent):
            app.reviews.revoke('one','in-flight',approval['id'],'reviewer','Stop')
            return submit(intent)
        with patch.object(app.engagements.email,'submit',side_effect=revoke) as provider:
            result=app.engagements.advance('one',simulation)
        self.assertEqual(provider.call_count,1)
        self.assertEqual(result['totals']['accepted'],1)
        self.assertEqual(result['totals']['states']['blocked'],6)
        observed=next(s for s in result['steps'] if s['submission'])
        self.assertEqual(observed['status'],'blocked');self.assertEqual(observed['submission']['status'],'accepted')
        self.assertEqual(self.app().engagements.advance('one',simulation)['totals']['accepted'],1)

    def test_evidence_epochs_do_not_resurrect_when_pack_bytes_are_restored(self):
        from acquisition.reviews import ReviewPolicy
        pack=json.loads((fixtures.ROOT/'config/iwoca-product-facts-v1.json').read_text())
        # Product authority exists before assessments freeze its suppression epoch.
        # Build a separate fixture rather than rewriting historical assessment bytes.
        class ReviewedTemplates(fixtures.SequenceTests): pass
        contacts=fixtures.build_contact_directory
        def with_authority(path,org,profile,clock):
            directory=contacts(path,org,profile,clock)
            roles=SqliteReviews(directory.store.database,clock,SqliteSimulatedDelivery)
            roles.register_actor(org,'operator',('operator',))
            roles.activate(org,'operator','original',pack,ReviewPolicy())
            return directory
        with patch.object(fixtures,'build_contact_directory',side_effect=with_authority):ReviewedTemplates.setUpClass()
        self.addCleanup(ReviewedTemplates.tearDownClass)
        with closing(sqlite3.connect(ReviewedTemplates.templates['fielddesk'])) as source,closing(sqlite3.connect(self.path)) as target:
            source.backup(target)
        app=self.app();roles=self.roles(app)
        proposal=self.prepare(app);approval=self.approve(app,proposal)
        old=app.reviews.view('one',approval['subject_id'])['summary']
        roles.activate('one','operator','changed',pack|{'version':'new-review'},ReviewPolicy())
        roles.activate('one','operator','restored',pack,ReviewPolicy())
        view=app.reviews.view('one',approval['subject_id'])
        self.assertFalse(view['approval_valid']);self.assertTrue(view['content_withheld'])
        check=next(c for c in view['validation']['checks'] if c['id']=='current_epochs')
        self.assertEqual(check['status'],'failed')
        with self.assertRaises(Conflict):app.reviews.validate_output('one',approval['subject_id'],old)
        with self.assertRaises(Conflict):app.engagements.start('one','stale',proposal['proposal_id'],approval['id'])
        fresh=app.reviews.open('one','refresh',proposal['proposal_id'],'operator')
        self.assertNotEqual(fresh['subject_id'],approval['subject_id'])
        current=app.reviews.decide('one','fresh-approval',fresh['subject_id'],'reviewer','approve','Current evidence reviewed',100)
        app.engagements.start('one','current',proposal['proposal_id'],current['id'])

    def test_rehashed_copy_and_missing_inference_receipts_cannot_self_certify_validation(self):
        app,proposal,approval=self.reviewed();store=app.campaigns.store.channels
        artifact=store._artifact
        def forged(db,org,identity):
            bundle=copy.deepcopy(artifact(db,org,identity))
            row=bundle['rendered'][0]
            if row['channel']=='email':row['email']['text']+='\nUnsupported promise'
            else:row['call']['discovery'].append('Unsupported promise')
            row['id']='channel_recipient_'+digest({k:v for k,v in row.items() if k!='id'})
            bundle['screen']['candidate_hash']=digest(bundle['rendered'])
            return bundle
        with patch.object(store,'_artifact',side_effect=forged):
            view=app.reviews.view('one',approval['subject_id'])
            self.assertFalse(view['validation']['review_ready'])
            self.assertEqual(next(c for c in view['validation']['checks'] if c['id']=='recipient_payloads')['status'],'failed')
        with store.database.transaction() as db:
            db.execute("DELETE FROM model_calls WHERE organization='one'")
        view=app.reviews.view('one',approval['subject_id'])
        self.assertFalse(view['validation']['review_ready']);self.assertTrue(view['content_withheld'])
        diagnostic=app.reviews.preview('one',proposal['proposal_id'])
        self.assertIsNone(diagnostic['summary']);self.assertTrue(diagnostic['validation']['checks'])

    def test_expiry_during_approval_and_reservation_rolls_back_authority(self):
        app=self.app();proposal=self.prepare(app);self.roles(app)
        subject=app.reviews.open('one','open',proposal['proposal_id'],'operator');store=app.reviews.store
        event=store._event;before=self.durable_counts()
        def expire_approval(db,org,kind,value):
            event(db,org,kind,value)
            if kind=='sequence_review_approve':self.now+=101
        with patch.object(store,'_event',side_effect=expire_approval),self.assertRaises(Conflict):
            app.reviews.decide('one','expiring',subject['subject_id'],'reviewer','approve','Reviewed',100)
        self.assertEqual(self.durable_counts(),before)
        self.now=fixtures.NOW
        approval=app.reviews.decide('one','valid',subject['subject_id'],'reviewer','approve','Reviewed',100)
        simulation=app.engagements.start('one','start',proposal['proposal_id'],approval['id'])['simulation_id']
        engagements=app.engagements.store;event=engagements._event;before=self.durable_counts()
        def expire_reservation(db,org,sim,kind,**data):
            event(db,org,sim,kind,**data)
            if kind=='step_reserved':self.now=approval['expires_at']
        with patch.object(engagements,'_event',side_effect=expire_reservation),self.assertRaises(Conflict):
            app.engagements.advance('one',simulation)
        self.assertEqual(self.durable_counts(),before)

    def test_admission_and_approval_commit_failure_leave_no_partial_rows(self):
        app=self.app();proposal=self.prepare(app);self.roles(app)
        subject=app.reviews.open('one','open',proposal['proposal_id'],'operator');store=app.reviews.store
        before=self.durable_counts();event=store._event
        def crash(db,org,kind,value):
            event(db,org,kind,value)
            if kind=='sequence_review_approve':raise OSError('crash after decision write')
        with patch.object(store,'_event',side_effect=crash),self.assertRaises(OSError):
            app.reviews.decide('one','approve',subject['subject_id'],'reviewer','approve','Reviewed',100)
        self.assertEqual(self.durable_counts(),before)
        approval=app.reviews.decide('one','approve',subject['subject_id'],'reviewer','approve','Reviewed',100)
        before=self.durable_counts();engagements=app.engagements.store;event=engagements._event
        def revoke_after_enrollment(db,org,sim,kind,**data):
            event(db,org,sim,kind,**data)
            if kind=='simulation_enrolled':self.now=approval['expires_at']
        with patch.object(engagements,'_event',side_effect=revoke_after_enrollment),self.assertRaises(Conflict):
            app.engagements.start('one','start',proposal['proposal_id'],approval['id'])
        self.assertEqual(self.durable_counts(),before)

    def test_schema_21_migration_preserves_history_and_cannot_authorize_legacy_simulation(self):
        app,proposal,approval=self.reviewed();simulation=app.engagements.start('one','start',proposal['proposal_id'],approval['id'])['simulation_id']
        database=app.campaigns.store.database
        # Represent the prior writer: historical sequence data, no review tables or grants.
        tables=('sequence_simulation_approvals','sequence_review_commands','sequence_review_events',
            'sequence_review_revocations','sequence_review_decisions','sequence_review_subjects')
        with database.transaction() as db:
            for table in tables:db.execute('DROP TABLE '+table)
            db.execute('PRAGMA user_version=21')
            names=[r[0] for r in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")]
            baseline={name:[tuple(r) for r in db.execute('SELECT * FROM '+name)] for name in names}
        apply=Database._apply_migration
        def crash(db,script):
            apply(db,script)
            if 'CREATE TABLE IF NOT EXISTS sequence_review_subjects' in script:raise OSError('migration interrupted')
        with patch.object(Database,'_apply_migration',side_effect=crash),self.assertRaises(OSError):Database(self.path)
        with database.connect() as db:self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],21)
        legacy=self.app(read_only=True)
        self.assertEqual(len(legacy.engagements.inspect('one',simulation)['steps']),6)
        self.assertEqual(legacy.campaigns.inspect('one',proposal['proposal_id'])['saved'],proposal['saved'])
        with self.assertRaises(Conflict):legacy.engagements.advance('one',simulation)
        with self.assertRaises(Conflict):legacy.reviews.preview('one',proposal['proposal_id'])
        Database(self.path);Database(self.path)
        with database.connect() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],22)
            for table,rows in baseline.items():self.assertEqual([tuple(r) for r in db.execute('SELECT * FROM '+table)],rows,table)
            self.assertEqual(db.execute('SELECT count(*) FROM sequence_review_decisions').fetchone()[0],0)
        historical=self.app().engagements.inspect('one',simulation)
        self.assertEqual(len(historical['steps']),6)
        result=self.app().engagements.advance('one',simulation)
        self.assertEqual(result['totals']['states']['blocked'],6)
        self.assertEqual(self.counts()['engagement_dispatches'],0)


if __name__=='__main__':unittest.main()
