"""Exact approval and truthful output boundaries, exercised through real SQLite."""

import copy
from contextlib import closing, contextmanager
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
        class ReviewTemplates(fixtures.SequenceTests):
            profiles = ('fielddesk',)
        ReviewTemplates.setUpClass()
        cls.base_templates = ReviewTemplates
        cls.templates = ReviewTemplates.templates
        cls.indirect_templates = {}

    @classmethod
    def tearDownClass(cls):
        for template in cls.indirect_templates.values(): template.tearDownClass()
        cls.base_templates.tearDownClass()

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

    @contextmanager
    def indirect_fixture(self, kind):
        """Attested source variants, never edits to immutable saved artifacts."""
        from acquisition.adapters import contact_fixtures, recipient_fixtures
        from acquisition.creative import RecipientContexts
        from acquisition.bootstrap import build_sequence_simulation
        base=build_sequence_simulation(self.templates['fielddesk'],'one','fielddesk',lambda:fixtures.NOW,read_only=True)
        snapshot=base.campaigns.store.contacts.source.read('one','fielddesk-crm-a',1)
        with base.campaigns.store.database.connect() as db:
            decision=json.loads(db.execute("SELECT receipt FROM contact_commands WHERE organization='one' AND request_id='decision'").fetchone()[0])['decision']
        selected={r['contact_id'] for r in decision['plan']['allocations']}
        omitted=next(p.ref.id for p in snapshot.contacts if p.ref.id not in selected)
        if kind=='pressure':omitted=snapshot.contacts[-1].ref.id
        pressure_unit=next(p.experiment_unit for p in snapshot.pressure if p.contact.id==omitted)
        deadline=fixtures.NOW+100
        contacts,recipients,prepare=(contact_fixtures.synthetic_contact_snapshots,
            recipient_fixtures.synthetic_recipient_evidence,RecipientContexts.prepare)
        def contact_sources(organization,profile):
            for item in contacts(organization,profile):
                if kind.startswith('population') and profile.key=='fielddesk':
                    item=replace(item,permissions=tuple(replace(p,expires_at=deadline)
                        if p.contact.id==omitted and p.channel=='email' else p for p in item.permissions))
                if kind=='pressure' and profile.key=='fielddesk':
                    item=replace(item,pressure=tuple(replace(p,expires_at=deadline)
                        if p.experiment_unit==pressure_unit else p for p in item.pressure))
                yield item
        def recipient_sources(source):
            for item in recipients(source):
                if source.connection.key.startswith('fielddesk-'):
                    if kind=='extra_recipient' and item.target.contact.id==omitted:
                        item=replace(item,expires_at=deadline)
                    if kind=='history' and item.source_key=='reviewed-context-b':
                        item=replace(item,expires_at=deadline)
                    if kind=='omitted_fact':
                        item=replace(item,facts=tuple(replace(f,expires_at=deadline)
                            if f.slot=='account_activity' else f for f in item.facts))
                yield item
        def prepare_context(service,*args,**kwargs):
            if kind=='omitted_fact':kwargs['slots']=('contact_role','prior_interaction','account_activity')
            return prepare(service,*args,**kwargs)
        class IndirectTemplates(fixtures.SequenceTests):
            profiles = ('fielddesk',)
        with patch.object(contact_fixtures,'synthetic_contact_snapshots',side_effect=contact_sources),\
                patch.object(recipient_fixtures,'synthetic_recipient_evidence',side_effect=recipient_sources),\
                patch.object(RecipientContexts,'prepare',prepare_context):
            variant = 'population' if kind.startswith('population') else kind
            if variant not in self.indirect_templates:
                try:
                    IndirectTemplates.setUpClass()
                except BaseException:
                    IndirectTemplates.tearDownClass()
                    raise
                self.indirect_templates[variant] = IndirectTemplates
            template = self.indirect_templates[variant]
            self.path=Path(self.temp.name)/(kind+'-indirect.sqlite')
            with closing(sqlite3.connect(template.templates['fielddesk'])) as source,closing(sqlite3.connect(self.path)) as target:
                source.backup(target)
            if kind=='history':
                from acquisition.bootstrap import build_recipient_contexts
                contexts=build_recipient_contexts(self.path,'one','fielddesk',lambda:self.now)
                with contexts.store.contacts.database.connect() as db:
                    assessment=json.loads(db.execute("SELECT receipt FROM contact_commands WHERE organization='one' AND request_id='email-assessment'").fetchone()[0])['assessment_id']
                contexts.prepare('one','corroborating-history',assessment,next(iter(selected)),'reviewed-context-b',1)
            yield omitted,deadline

    def test_full_readiness_basis_expiry_withholds_outputs_even_when_selected_payloads_remain_valid(self):
        for kind in ('population','population_controls','pressure','extra_recipient','omitted_fact'):
            self.now=fixtures.NOW
            with self.subTest(kind=kind),self.indirect_fixture(kind) as (omitted,deadline):
                changes={}
                if kind in {'population_controls','pressure'}:
                    from acquisition.bootstrap import build_audience_decisions
                    decisions=build_audience_decisions(self.path,'one','fielddesk',clock=lambda:self.now)
                    with decisions.store.contacts.database.connect() as db:
                        assessment=json.loads(db.execute("SELECT receipt FROM contact_commands WHERE organization='one' AND request_id='email-assessment'").fetchone()[0])['assessment_id']
                    snapshot=decisions.store.contacts.source.read('one','fielddesk-crm-a',1)
                    def buckets(seed):
                        return [int(digest({'algorithm':'contact-account-hash/v1','organization':'one',
                            'profile':snapshot.profile_id,'channel':'email','seed':seed,'unit':a.experiment_unit}),16)%10 for a in snapshot.accounts]
                    seed=next(s for s in range(10000) if (all(b==0 for b in buckets(s))
                        if kind=='population_controls' else all(b!=0 for b in buckets(s))))
                    decisions.prepare('one','basis-decision',assessment,budget_pence=1000,unit_cost_pence=1,
                        max_candidates=1 if kind=='pressure' else 6,seed=seed)
                    changes['decision_request']='basis-decision'
                app,proposal,approval=self.reviewed(expires_at=fixtures.NOW+1000,**changes)
                self.assertNotIn(omitted,{m['contact_id'] for m in proposal['saved']['population']})
                steps=[s for m in proposal['saved']['population'] for s in m['steps']]
                if kind=='population_controls':self.assertEqual(steps,[])
                else:self.assertGreater(min(s['content']['valid_until'] for s in steps),deadline)
                store=app.reviews.store
                original=app.reviews.view('one',approval['subject_id'])
                self.assertTrue(original['validation']['review_ready'])
                self.now=deadline-1
                before_expiry=app.reviews.view('one',approval['subject_id'])
                self.assertTrue(before_expiry['validation']['review_ready'])
                self.assertTrue(before_expiry['approval_valid'])
                self.now=deadline
                self.assertFalse(app.reviews.view('one',approval['subject_id'])['validation']['review_ready'])
                before=self.durable_counts()
                # A passed report is time-bounded evidence, not authority to return
                # approval after a later epoch or reviewer lookup crosses its end.
                import acquisition.adapters.sqlite.sequence_reviews as review_adapter
                ready,basis,actor=store._ready,store._basis,review_adapter.require_actor
                for phase in ('report','epochs','reviewer'):
                    self.now=fixtures.NOW;completed=[False]
                    def checked_ready(*args,**kwargs):
                        result=ready(*args,**kwargs)
                        self.assertTrue(result['review_ready']);completed[0]=True
                        if phase=='report':self.now=deadline
                        return result
                    def checked_basis(*args,**kwargs):
                        result=basis(*args,**kwargs)
                        if completed[0] and phase=='epochs':self.now=deadline
                        return result
                    def checked_actor(*args,**kwargs):
                        result=actor(*args,**kwargs)
                        if completed[0] and phase=='reviewer':self.now=deadline
                        return result
                    with self.subTest(authority_phase=phase),patch.object(store,'_ready',side_effect=checked_ready),\
                            patch.object(store,'_basis',side_effect=checked_basis),\
                            patch.object(review_adapter,'require_actor',side_effect=checked_actor),\
                            store.database.connect() as db:
                        db.execute('BEGIN')
                        with self.assertRaises(Conflict):
                            store.authorize(db,'one',proposal['proposal_id'],approval['id'])
                    self.assertEqual(self.durable_counts(),before)
                for phase in ('_campaign','_decision'):
                    checked=getattr(store,phase)
                    def cross_expiry(*args,**kwargs):
                        result=checked(*args,**kwargs);self.now=deadline;return result
                    for reader in ('view','preview'):
                        self.now=fixtures.NOW
                        identity=approval['subject_id'] if reader=='view' else proposal['proposal_id']
                        with self.subTest(phase=phase,reader=reader),patch.object(store,phase,side_effect=cross_expiry):
                            view=getattr(app.reviews,reader)('one',identity)
                            self.assertFalse(view['validation']['review_ready'])
                            self.assertTrue(view['content_withheld'])
                            self.assertIsNone(view['summary']);self.assertIsNone(view['sequence'])
                            self.assertFalse(view['approval_valid'])
                            basis=next(c for c in view['validation']['checks'] if c['id']=='current_epochs')
                            self.assertEqual(basis['status'],'failed')
                            self.assertEqual(basis['validity']['until'],deadline)
                self.now=fixtures.NOW
                checked=store._campaign
                def expire_output(*args,**kwargs):
                    checked(*args,**kwargs);self.now=deadline
                with patch.object(store,'_campaign',side_effect=expire_output),self.assertRaises(Conflict):
                    app.reviews.validate_output('one',approval['subject_id'],original['summary'])
                self.assertEqual(self.durable_counts(),before)
                variant = 'population' if kind.startswith('population') else kind
                template = self.indirect_templates[variant].templates['fielddesk']
                with closing(sqlite3.connect(template)) as db:
                    for table in ('sequence_proposals','sequence_review_decisions','engagement_simulations'):
                        self.assertEqual(db.execute('SELECT count(*) FROM '+table).fetchone()[0],0)

    def test_past_history_boundaries_do_not_prevent_fresh_complete_revalidation(self):
        with self.indirect_fixture('history') as (_,deadline):
            app,proposal,approval=self.reviewed(expires_at=fixtures.NOW+1000)
            before=self.durable_counts();checked=app.reviews.store._campaign
            def cross_expiry(*args,**kwargs):
                checked(*args,**kwargs);self.now=deadline
            with patch.object(app.reviews.store,'_campaign',side_effect=cross_expiry):
                stale=app.reviews.view('one',approval['subject_id'])
            self.assertFalse(stale['validation']['review_ready']);self.assertIsNone(stale['summary'])
            fresh=app.reviews.view('one',approval['subject_id'])
            self.assertTrue(fresh['validation']['review_ready']);self.assertTrue(fresh['approval_valid'])
            window=next(c for c in fresh['validation']['checks'] if c['id']=='current_epochs')['validity']
            self.assertEqual(window['from'],deadline);self.assertGreater(window['until'],deadline)
            self.assertEqual(self.durable_counts(),before)

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
        for check in passed:
            if check['id']=='current_epochs':
                check['validity']={'subject_id':subject['id'],'from':self.now,'until':self.now+100}
        self.assertTrue(sequence_validation(subject,passed,self.now)['review_ready'])
        missing=[{k:v for k,v in c.items() if k!='validity'} for c in passed]
        incomplete=sequence_validation(subject,missing,self.now)
        self.assertFalse(incomplete['review_ready'])
        self.assertEqual(next(c for c in incomplete['checks'] if c['id']=='current_epochs')['status'],'unknown')
        for window in ({'subject_id':'another','from':self.now,'until':self.now+100},
                {'subject_id':subject['id'],'from':self.now,'until':float('nan')},
                {'subject_id':subject['id'],'from':self.now+1,'until':self.now}):
            changed=[c|{'validity':window} if c['id']=='current_epochs' else c for c in passed]
            self.assertFalse(sequence_validation(subject,changed,self.now)['review_ready'])
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
        with patch.object(store,'_readiness_window',side_effect=RuntimeError('basis checker crashed')):
            view=app.reviews.view('one',approval['subject_id'])
            self.assertFalse(view['validation']['review_ready']);self.assertIsNone(view['summary'])
            self.assertEqual(next(c for c in view['validation']['checks'] if c['id']=='current_epochs')['status'],'unknown')

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

    def test_readiness_rechecks_sequence_and_evidence_expiry_before_output(self):
        for boundary in ('sequence','evidence'):
            self.path=Path(self.temp.name)/(boundary+'-readiness.sqlite');self.copy_template()
            self.now=fixtures.NOW
            end=fixtures.NOW+(100 if boundary=='sequence' else 14*86400)
            app,proposal,approval=self.reviewed(expires_at=end)
            deadline=end if boundary=='sequence' else min(s['content']['valid_until']
                for m in proposal['saved']['population'] for s in m['steps'])
            if boundary=='evidence':self.assertLess(deadline,end)
            store=app.reviews.store
            original=app.reviews.view('one',approval['subject_id'])
            self.assertTrue(original['validation']['review_ready'])
            self.now=deadline-1
            self.assertTrue(app.reviews.view('one',approval['subject_id'])['validation']['review_ready'])
            self.now=fixtures.NOW
            before=self.durable_counts()
            for phase in ('_campaign','_decision'):
                check=getattr(store,phase)
                def cross_expiry(*args,**kwargs):
                    value=check(*args,**kwargs)
                    self.now=deadline
                    return value
                for reader in ('view','preview'):
                    with self.subTest(boundary=boundary,phase=phase,reader=reader):
                        self.now=fixtures.NOW
                        identity=approval['subject_id'] if reader=='view' else proposal['proposal_id']
                        with patch.object(store,phase,side_effect=cross_expiry):
                            view=getattr(app.reviews,reader)('one',identity)
                        self.assertEqual(view['validation']['evaluated_at'],deadline)
                        self.assertFalse(view['validation']['review_ready'])
                        self.assertTrue(view['content_withheld'])
                        self.assertIsNone(view['summary']);self.assertIsNone(view['sequence'])
                        self.assertFalse(view['approval_valid'])
                        self.assertEqual(next(c for c in view['validation']['checks']
                            if c['id']=='sequence_contract')['status'],'failed')
            self.now=fixtures.NOW
            campaign=store._campaign
            def expire_after_validation(*args,**kwargs):
                campaign(*args,**kwargs);self.now=deadline
            with patch.object(store,'_campaign',side_effect=expire_after_validation),self.assertRaises(Conflict):
                app.reviews.validate_output('one',approval['subject_id'],original['summary'])
            if boundary=='evidence':
                # A shorter approval expiry changes approval validity, not whether
                # still-current material can be presented for accountable review.
                self.now=fixtures.NOW;authorize=store.authorize
                def expire_after_authorization(*args,**kwargs):
                    value=authorize(*args,**kwargs);self.now=approval['expires_at'];return value
                with patch.object(store,'authorize',side_effect=expire_after_authorization):
                    view=app.reviews.view('one',approval['subject_id'])
                self.assertTrue(view['validation']['review_ready'])
                self.assertIsNotNone(view['summary']);self.assertFalse(view['approval_valid'])
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
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],23)
            for table,rows in baseline.items():self.assertEqual([tuple(r) for r in db.execute('SELECT * FROM '+table)],rows,table)
            self.assertEqual(db.execute('SELECT count(*) FROM sequence_review_decisions').fetchone()[0],0)
        historical=self.app().engagements.inspect('one',simulation)
        self.assertEqual(len(historical['steps']),6)
        result=self.app().engagements.advance('one',simulation)
        self.assertEqual(result['totals']['states']['blocked'],6)
        self.assertEqual(self.counts()['engagement_dispatches'],0)


class SequenceReadinessDomainTests(unittest.TestCase):
    def test_domain_time_boundaries_include_pressure_coverage_and_product_calendar(self):
        from acquisition.campaigns import contact_eligibility, contact_readiness_boundaries
        from acquisition.creative import channel_readiness_boundaries
        from acquisition.reviews import readiness_window
        from acquisition.adapters.local_profiles import LocalProfiles
        from acquisition.adapters.contact_fixtures import synthetic_contact_snapshots
        profile=LocalProfiles('one','fielddesk',fixtures.ROOT/'config/profiles').campaign_profile('one','fielddesk','v1')
        source=next(synthetic_contact_snapshots('one',profile))
        subject={'id':'pure-window-subject'}
        shifted=replace(source,pressure=tuple(replace(p,window_start=fixtures.NOW-90*86400+100) for p in source.pressure))
        for offset,expected in ((99,False),(100,True)):
            report=contact_eligibility(shifted,profile,'email','acquisition',
                fixtures.NOW+offset,set(),set(),set(),set(),set())
            self.assertEqual(report['ready_for_proposal'],expected)
        window=readiness_window(subject,contact_readiness_boundaries((shifted,)),fixtures.NOW)
        self.assertEqual(window['until'],fixtures.NOW+100)
        dates=channel_readiness_boundaries(({'product_facts':{'checked_on':'2026-11-13','review_by':'2026-11-14'}},))
        self.assertEqual(readiness_window(subject,dates,fixtures.NOW)['until'],fixtures.NOW+86400)


if __name__=='__main__':unittest.main()
