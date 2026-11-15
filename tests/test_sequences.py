"""Frozen strategy membership and synthetic effect lifecycle through real SQLite and restarts."""

from dataclasses import asdict, replace
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import copy
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from acquisition.bootstrap import (build_contact_directory,build_recipient_contexts,build_channel_preparation,
                                   build_audience_decisions,build_sequence_simulation)
from acquisition.campaigns import SequenceRequest
from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.engagements import SimulationReceipt, validate_step_transition
from acquisition.runtime import LeaseLost
from acquisition.adapters.sqlite.database import Database
from acquisition.adapters.contact_fixtures import RecordedContactSource
from acquisition.adapters.recipient_fixtures import RecordedRecipientContextSource, synthetic_recipient_evidence
from acquisition.audiences import ContactDirectory
from acquisition.creative import RecipientContexts


ROOT=Path(__file__).resolve().parents[1]
NOW=1794614400.


class SequenceTests(unittest.TestCase):
    profiles = ('fielddesk','iwoca')
    @classmethod
    def setUpClass(cls):
        cls.fixture=tempfile.TemporaryDirectory()
        cls.templates={}
        for profile in cls.profiles:
            path=Path(cls.fixture.name)/(profile+'.sqlite');clock=lambda:NOW;org='one'
            contacts=build_contact_directory(path,org,profile,clock)
            contexts=build_recipient_contexts(path,org,profile,clock)
            channels=build_channel_preparation(path,org,profile,clock)
            for channel in ('email','human_call'):
                assessment=contacts.prepare(org,channel+'-assessment',profile+'-crm-a',1,channel)
                keys=[]
                for i,person in enumerate(assessment['report']['eligible']):
                    key=channel+'-'+str(i);keys.append(key)
                    contexts.prepare(org,key,assessment['assessment_id'],person,'reviewed-context-a',1)
                first=channels.prepare(org,channel,profile,keys,channel)
                if not first['ready_for_review']: raise AssertionError(first)
                if channel=='email':
                    email_assessment=assessment
                    channels.prepare(org,'followup',profile,keys,channel,parent_id=first['artifact_id'],style='practical')
            snapshot=contacts.source.read(org,profile+'-crm-a',1)
            profile_id=contacts.store._profile(org).id
            units=[a.experiment_unit for a in snapshot.accounts]
            found={}
            for seed in range(100):
                buckets=[int(digest({'algorithm':'contact-account-hash/v1','organization':org,'profile':profile_id,
                    'channel':'email','seed':seed,'unit':unit}),16)%10 for unit in units]
                arms={'no_contact' if b==0 else 'A' if b%2 else 'B' for b in buckets}
                if arms=={'A','B'}: found.setdefault('decision',seed)
                if 'no_contact' in arms and len(arms)==2: found.setdefault('controlled',seed)
                if len(found)==2: break
            decisions=build_audience_decisions(path,org,profile,clock=clock)
            for key,seed in found.items():
                decisions.prepare(org,key,email_assessment['assessment_id'],budget_pence=1000,unit_cost_pence=1,max_candidates=6,seed=seed)
            cls.templates[profile]=path

    @classmethod
    def tearDownClass(cls): cls.fixture.cleanup()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'application.sqlite';self.now=NOW
        self.copy_template()

    def copy_template(self, profile='fielddesk'):
        with closing(sqlite3.connect(self.templates[profile])) as source, closing(sqlite3.connect(self.path)) as dest: source.backup(dest)

    def app(self, profile='fielddesk', **options):
        return build_sequence_simulation(self.path,'one',profile,lambda:self.now,**options)

    def request(self, profile='fielddesk', **changes):
        return replace(SequenceRequest(profile,'decision','email','human_call','followup',NOW,NOW+7*86400,1000,6,18,
            call_delay_seconds=10,followup_delay_seconds=30,arm_b_call_delay_seconds=20,arm_b_followup_delay_seconds=40),**changes)

    def prepare(self, app=None, key='proposal', **changes):
        app=app or self.app();return app.campaigns.prepare('one',key,self.request(**changes))

    def approve(self, app, proposal, key='review'):
        from acquisition.adapters.sqlite.reviews import SqliteReviews
        from acquisition.adapters.sqlite.simulated_delivery import SqliteSimulatedDelivery
        roles=SqliteReviews(app.campaigns.store.database,lambda:self.now,SqliteSimulatedDelivery)
        roles.register_actor('one','operator',('operator',));roles.register_actor('one','reviewer',('reviewer',))
        subject=app.reviews.open('one',key+'-open',proposal['proposal_id'],'operator')
        return app.reviews.decide('one',key+'-approve',subject['subject_id'],'reviewer','approve',
            'Exact synthetic population and sequence reviewed',7*86400)

    def start(self, app=None, key='proposal', **changes):
        app=app or self.app();proposal=self.prepare(app,key,**changes)
        approval=self.approve(app,proposal,key)
        return app,proposal,app.engagements.start('one','start-'+key,proposal['proposal_id'],approval['id'])['simulation_id']

    def counts(self):
        with closing(sqlite3.connect(self.path)) as db:
            return {name:db.execute('SELECT count(*) FROM '+name).fetchone()[0] for name in (
                'sequence_proposals','sequence_commands','engagement_simulations','engagement_enrollments',
                'engagement_steps','engagement_dispatches','engagement_observations','engagement_commands','engagement_events',
                'review_decisions','simulated_agency_jobs','learning_cohorts','model_calls')}

    def event(self, app, simulation, step, kind, key=None):
        return app.engagements.observe('one',key or kind+'-'+step['id'],simulation,step['id'],
            step['submission']['provider_effect_id'],kind,self.now)

    def merged_sources(self, original, scope, selected):
        # Re-keying the connection cannot erase its attested native merge ancestry.
        connection=replace(original.connection,key='fielddesk-crm-alias',mapping_version='mapping-v2')
        def ref(value):return replace(value,connection=connection)
        alias=replace(original,connection=connection,
            accounts=tuple(replace(a,ref=ref(a.ref)) for a in original.accounts),
            contacts=tuple(replace(p,ref=ref(p.ref),accounts=tuple(ref(a) for a in p.accounts)) for p in original.contacts),
            permissions=tuple(replace(p,contact=ref(p.contact)) for p in original.permissions),
            pressure=tuple(replace(p,contact=ref(p.contact)) for p in original.pressure))
        if scope=='contact':
            old=next(p for p in alias.contacts if p.ref.id==selected['contact_id'])
            peer=next(p for p in alias.contacts if p.ref.id!=old.ref.id and p.accounts==old.accounts)
            second=replace(alias,version=2,observed_at=alias.observed_at+60,
                contacts=tuple(replace(p,state='merged',merged_into=peer.ref) if p.ref==old.ref else p for p in alias.contacts))
            newcomer=replace(peer,ref=replace(peer.ref,native_id='4'))
            third=replace(second,version=3,observed_at=alias.observed_at+120,declared_contacts=4,
                contacts=(*tuple(replace(p,state='merged',merged_into=newcomer.ref) if p.ref==peer.ref else p for p in second.contacts),newcomer),
                permissions=(*second.permissions,*tuple(replace(p,contact=newcomer.ref) for p in second.permissions if p.contact==peer.ref)),
                pressure=(*second.pressure,*tuple(replace(p,contact=newcomer.ref) for p in second.pressure if p.contact==peer.ref)))
            return (original,alias,second,third),newcomer.ref.id,old.accounts[0].id
        old=next(a for a in alias.accounts if a.ref.id==selected['account_id'])
        survivor=next(a for a in alias.accounts if a.ref.id!=old.ref.id)
        second=replace(alias,version=2,observed_at=alias.observed_at+60,
            accounts=tuple(replace(a,state='merged',merged_into=survivor.ref) if a.ref==old.ref else a for a in alias.accounts))
        person=next(p for p in second.contacts if p.accounts==(survivor.ref,))
        return (original,alias,second),person.ref.id,survivor.ref.id

    def fresh_merged_request(self, app, snapshots, prefix):
        store=app.campaigns.store;contacts=store.contacts
        contacts.source=RecordedContactSource('one',snapshots)
        directory=ContactDirectory(contacts.source,contacts)
        for index,snapshot in enumerate(snapshots[1:]):
            directory.refresh('one',prefix+'-refresh-'+str(index),snapshot.connection.key,snapshot.version)
        channel=build_channel_preparation(self.path,'one','fielddesk',lambda:self.now)
        channel.store.recipients.contacts=contacts
        evidence={}
        for snapshot in snapshots:
            for item in synthetic_recipient_evidence(snapshot):evidence.setdefault((item.target.id,item.source_key,item.version),item)
        source=RecordedRecipientContextSource('one',tuple(evidence.values()))
        channel.store.recipients.source=source
        contexts=RecipientContexts(source,channel.store.recipients,channel.store.recipients.guidance)
        final=snapshots[-1]
        for kind in ('email','human_call'):
            assessment=directory.prepare('one',prefix+'-assessment-'+kind,final.connection.key,final.version,kind)
            if kind=='email':email=assessment
            keys=[]
            for i,person in enumerate(assessment['report']['eligible']):
                key=prefix+'-context-'+kind+str(i);keys.append(key)
                contexts.prepare('one',key,assessment['assessment_id'],person,'reviewed-context-a',1)
            result=channel.prepare('one',prefix+'-content-'+kind,'fielddesk',keys,kind)
            self.assertTrue(result['ready_for_review'])
        decisions=build_audience_decisions(self.path,'one','fielddesk',clock=lambda:self.now)
        decisions.store.contacts=contacts
        units={r['experiment_unit'] for r in email['report']['rows'] if r['eligible_for_preparation']}
        seed=next(s for s in range(100) if all(int(digest({'algorithm':'contact-account-hash/v1','organization':'one',
            'profile':final.profile_id,'channel':'email','seed':s,'unit':u}),16)%10!=0 for u in units))
        decision=decisions.prepare('one',prefix+'-decision',email['assessment_id'],budget_pence=1000,unit_cost_pence=1,max_candidates=6,seed=seed)
        store.channels=channel.store;store.decisions=decisions.store
        return self.request(decision_request=prefix+'-decision',initial_content=prefix+'-content-email',
            call_content=prefix+'-content-human_call',followup_content=prefix+'-content-email'),decision

    def test_contact_objection_follows_transitive_merges_across_connection_alias_and_restart(self):
        app,proposal,simulation=self.start(stop_scope='contact');view=app.engagements.advance('one',simulation)
        original=app.campaigns.store.contacts.source.read('one','fielddesk-crm-a',1)
        account=original.accounts[0].ref.id
        selected=next(s for s in view['steps'] if s['ordinal']==0 and s['account_id']==account)
        self.event(app,simulation,selected,'objected')
        snapshots,survivor,_=self.merged_sources(original,'contact',selected)
        request,decision=self.fresh_merged_request(app,snapshots,'contact-merge')
        self.assertIn(survivor,{r['contact_id'] for r in decision['decision']['plan']['allocations']})
        before=self.counts()
        with self.assertRaises(Conflict):app.campaigns.prepare('one','after-contact-merge',request)
        self.assertEqual(self.counts(),before)
        self.assertEqual(app.campaigns.inspect('one',proposal['proposal_id'])['saved'],proposal['saved'])
        code='''
import json,sqlite3,sys
from contextlib import closing
from pathlib import Path
from test_sequences import SequenceTests,NOW
from acquisition.audiences import contact_snapshot_from
from acquisition.contracts import Conflict
h=SequenceTests('test_contact_objection_follows_transitive_merges_across_connection_alias_and_restart')
h.path=Path(sys.argv[1]);h.now=NOW
with closing(sqlite3.connect(h.path)) as db:
 snapshots=[contact_snapshot_from(json.loads(r[0])) for r in db.execute('SELECT payload FROM contact_sources')]
snapshots.sort(key=lambda s:(s.connection.key!='fielddesk-crm-a',s.version))
a=h.app();request,_=h.fresh_merged_request(a,tuple(snapshots),'contact-merge')
try:a.campaigns.prepare('one','after-contact-merge',request)
except Conflict:print(json.dumps({'blocked':True,'counts':h.counts()}))
else:raise AssertionError('Merge ancestry lost after restart')
'''
        process=subprocess.run([sys.executable,'-c',code,str(self.path)],cwd=ROOT,text=True,capture_output=True,
            env=dict(os.environ,PYTHONPATH=os.pathsep.join((str(ROOT/'src'),str(ROOT/'tests')))))
        self.assertEqual(process.returncode,0,process.stderr)
        self.assertTrue(json.loads(process.stdout)['blocked'])
        self.assertEqual(json.loads(process.stdout)['counts'],before)

    def test_account_merge_carries_late_objection_to_surviving_pending_sequence_and_new_proposals(self):
        for timing in ('before','after'):
            self.path=Path(self.temp.name)/(timing+'.sqlite');self.copy_template()
            app,proposal,simulation=self.start();view=app.engagements.advance('one',simulation)
            original=app.campaigns.store.contacts.source.read('one','fielddesk-crm-a',1)
            unrelated=app.campaigns.store.contacts.source.read('one','fielddesk-crm-b',1)
            selected=next(s for s in view['steps'] if s['ordinal']==0 and s['account_id']==original.accounts[0].ref.id)
            if timing=='before':self.event(app,simulation,selected,'objected')
            snapshots,survivor,account=self.merged_sources(original,'account',selected)
            request,decision=self.fresh_merged_request(app,snapshots,'account-merge')
            self.assertIn(survivor,{r['contact_id'] for r in decision['decision']['plan']['allocations']})
            if timing=='after':
                fresh=app.campaigns.prepare('one','before-late-objection',request)
                self.assertEqual({m['contact_id'] for m in fresh['saved']['population']},{survivor})
                pending=app.engagements.start('one','surviving-account',fresh['proposal_id'],self.approve(app,fresh,'survivor')['id'])['simulation_id']
                self.event(app,simulation,selected,'objected')
                current=app.engagements.inspect('one',pending)
                self.assertEqual({s['status'] for s in current['steps']},{'stopped'})
                self.assertEqual(current['totals']['accepted'],0)
            else:
                current=app.engagements.advance('one',simulation)
                self.assertEqual({s['status'] for s in current['steps'] if s['ordinal']>0},{'stopped'})
                self.assertEqual(current['totals']['accepted_call_tasks'],0)
            with self.assertRaises(Conflict):app.campaigns.prepare('one','after-account-merge',request)
            with app.campaigns.store.database.connect() as db:
                stop=db.execute('SELECT subject_id,payload FROM engagement_stops WHERE organization=?',('one',)).fetchone()
                self.assertEqual(stop['subject_id'],selected['account_id'])
                self.assertEqual(json.loads(stop['payload'])['step_id'],selected['id'])
                from acquisition.adapters.sqlite.engagement_stops import native_engagement_stop
                self.assertIsNone(native_engagement_stop(db,app.campaigns.store.contacts,'one',None,
                    unrelated.contacts[0].ref.id,unrelated.accounts[0].ref.id))
            self.assertEqual(app.campaigns.inspect('one',proposal['proposal_id'])['saved'],proposal['saved'])

    def test_two_profiles_full_strategy_keeps_exact_units_arms_costs_capacity_and_distinct_observations(self):
        for profile in ('fielddesk','iwoca'):
            self.now=NOW
            if profile!='fielddesk':
                self.path=Path(self.temp.name)/(profile+'.sqlite');self.copy_template(profile)
            app=self.app(profile);request=self.request(profile)
            proposal=app.campaigns.prepare('one','proposal',request)
            saved=proposal['saved'];self.assertEqual(saved['counts'],{'enrolled':2,'controls':0,'treatment':2,'email_steps':4,'call_tasks':2,'steps':6})
            self.assertEqual({m['arm'] for m in saved['population']},{'A','B'})
            self.assertEqual(saved['limits']['maximum_cost_pence'],208)
            for member in saved['population']:
                expected=[0,10,30] if member['arm']=='A' else [0,20,40]
                self.assertEqual([s['due_at']-NOW for s in member['steps']],expected)
                self.assertEqual({s['content']['target']['experiment_unit'] for s in member['steps']},{member['experiment_unit']})
                self.assertEqual(member['steps'][1]['assignee'],'DEMO ONLY representative '+profile+'-rep-1')
            simulation=app.engagements.start('one','start',proposal['proposal_id'],self.approve(app,proposal)['id'])['simulation_id']
            view=app.engagements.advance('one',simulation)
            self.assertEqual(view['totals']['accepted'],2);self.assertEqual(view['totals']['delivered'],0)
            self.assertEqual(view['totals']['responded'],0);self.assertEqual(view['totals']['confirmed_cost_pence'],4)
            for step in view['steps']:
                if step['ordinal']==0:self.event(app,simulation,step,'delivered')
            self.now=NOW+20;view=app.engagements.advance('one',simulation)
            self.assertEqual(view['totals']['accepted_call_tasks'],2)
            self.assertEqual(view['totals']['completed_call_tasks'],0)
            self.now=NOW+40;waiting=app.engagements.advance('one',simulation)
            self.assertEqual(waiting['totals']['accepted'],4)
            self.assertEqual(waiting['status'],'waiting_for_human_completion')
            for step in waiting['steps']:
                if step['channel']=='human_call':self.event(app,simulation,step,'task_completed')
            view=app.engagements.advance('one',simulation)
            self.assertEqual(view['status'],'submissions_complete')
            self.assertEqual(view['totals']['accepted'],6);self.assertEqual(view['totals']['delivered'],2)
            self.assertEqual(view['totals']['confirmed_cost_pence'],208)
            self.assertEqual(view['totals']['reserved_call_capacity'],2)
            self.assertEqual(view['totals']['reserved_step_capacity'],6)
            self.assertEqual(len({e['experiment_unit'] for e in view['enrollments']}),2)
            before=self.counts();self.assertEqual(app.engagements.advance('one',simulation),view);self.assertEqual(self.counts(),before)
            for table in ('review_decisions','simulated_agency_jobs','learning_cohorts'):self.assertEqual(before[table],0)

    def test_controls_are_enrolled_but_never_receive_a_step_or_charge(self):
        app,proposal,simulation=self.start(decision_request='controlled')
        self.assertEqual(proposal['saved']['counts']['controls'],1)
        view=app.engagements.advance('one',simulation)
        controls={m['contact_id'] for m in view['assignments'] if m['arm']=='no_contact'}
        self.assertTrue(controls);self.assertTrue(controls.isdisjoint(s['contact_id'] for s in view['steps']))
        self.assertEqual(len(view['enrollments']),2);self.assertEqual(len(view['steps']),3)
        self.assertEqual(view['totals']['maximum_cost_pence'],104)

    def test_budget_capacity_bounds_missing_call_content_and_target_substitution_cannot_publish(self):
        app=self.app();before=self.counts()
        for changes in ({'budget_pence':207},{'call_capacity':1},{'step_capacity':5},{'call_content':'email'},
                        {'starts_at':NOW+11*86400,'expires_at':NOW+13*86400}):
            with self.assertRaises(Conflict):self.prepare(app,'bad-'+str(changes),**changes)
            self.assertEqual(self.counts(),before)
        store=app.campaigns.store;material=store._material
        def swap(db,org,key):
            rows=copy.deepcopy(material(db,org,key))
            for row in rows:row['target']['account_id']='another-account'
            return rows
        with patch.object(store,'_material',side_effect=swap),self.assertRaises(Conflict):self.prepare(app,'swapped')
        self.assertEqual(self.counts(),before)

    def test_exact_request_replay_and_new_simulation_key_do_not_repeat_enrollments_or_steps(self):
        app,proposal,simulation=self.start();before=self.counts()
        replay=self.prepare(app);self.assertEqual(replay['saved'],proposal['saved']);self.assertEqual(self.counts(),before)
        with self.assertRaises(Conflict):self.prepare(app,budget_pence=999)
        again=app.engagements.start('one','new-key',proposal['proposal_id'])
        self.assertEqual(again['simulation_id'],simulation)
        for table in ('engagement_enrollments','engagement_steps','engagement_simulations'):
            self.assertEqual(self.counts()[table],before[table])
        with self.assertRaises(Conflict):app.engagements.start('one','start-proposal','different-proposal')

    def test_new_process_replay_and_advance_preserve_one_logical_effect(self):
        app,proposal,simulation=self.start();first=app.engagements.advance('one',simulation);before=self.counts()
        code='''
import json,sys
from unittest.mock import patch
from acquisition.bootstrap import build_sequence_simulation
with patch('acquisition.adapters.simulated_engagements.SyntheticEngagementTransport.submit',side_effect=AssertionError('repeat')):
 a=build_sequence_simulation(sys.argv[1],'one','fielddesk',lambda:1794614400.)
 print(json.dumps(a.engagements.advance('one',sys.argv[2])))
'''
        process=subprocess.run([sys.executable,'-c',code,str(self.path),simulation],cwd=ROOT,text=True,capture_output=True)
        self.assertEqual(process.returncode,0,process.stderr)
        self.assertEqual(json.loads(process.stdout),first);self.assertEqual(self.counts(),before)
        self.now=NOW+20
        with self.assertRaises(Conflict):self.app(call_scenario='rejection').engagements.advance('one',simulation)
        self.assertEqual(self.counts(),before)

    def test_replies_pause_only_the_selected_account_pending_steps_and_objections_stop_them(self):
        app,proposal,simulation=self.start();view=app.engagements.advance('one',simulation)
        target=next(s for s in view['steps'] if s['ordinal']==0)
        self.event(app,simulation,target,'replied')
        view=app.engagements.inspect('one',simulation)
        own=[s for s in view['steps'] if s['account_id']==target['account_id'] and s['ordinal']>0]
        others=[s for s in view['steps'] if s['account_id']!=target['account_id'] and s['ordinal']>0]
        self.assertEqual({s['status'] for s in own},{'paused'});self.assertEqual({s['status'] for s in others},{'pending'})
        self.assertEqual(view['totals']['responded'],1)
        self.event(app,simulation,target,'objected')
        self.now=NOW+20;view=app.engagements.advance('one',simulation)
        self.assertEqual({s['status'] for s in view['steps'] if s['account_id']==target['account_id'] and s['ordinal']>0},{'stopped'})
        # The objection invalidates the whole exact reviewed population. Unrelated
        # pending work now needs a new proposal and review rather than stale authority.
        self.assertEqual(view['totals']['accepted_call_tasks'],0)
        self.assertEqual({s['status'] for s in view['steps'] if s['account_id']!=target['account_id'] and s['ordinal']>0},{'blocked'})
        # A new proposal cannot evade an organization-wide native-account objection.
        with self.assertRaises(Conflict):self.prepare(app,'new-proposal')
        self.assertFalse(app.campaigns.inspect('one',proposal['proposal_id'])['currently_applicable'])

    def test_bounce_cannot_authorize_an_ineligible_human_call(self):
        app,proposal,simulation=self.start();view=app.engagements.advance('one',simulation)
        target=next(s for s in view['steps'] if s['ordinal']==0)
        self.event(app,simulation,target,'bounced')
        contacts=build_contact_directory(self.path,'one','fielddesk',lambda:self.now)
        contacts.object('one','cannot-call',target['contact_id'],'human_call','acquisition','stop')
        self.now=NOW+20;view=app.engagements.advance('one',simulation)
        self.assertEqual(view['totals']['accepted_call_tasks'],0)
        self.assertTrue(any(s['channel']=='human_call' and s['status']=='blocked' for s in view['steps']))

    def test_timeout_partial_and_rejection_preserve_uncertainty_without_automatic_retry(self):
        for scenario,status,cost in (('timeout','unknown',None),('partial','partial',None),('rejection','rejected',0)):
            app=self.app(email_scenario=scenario);app,proposal,simulation=self.start(app,key=scenario)
            model=app.engagements.email
            with patch.object(model,'submit',wraps=model.submit) as submitted:
                view=app.engagements.advance('one',simulation);self.assertEqual(submitted.call_count,2)
                self.assertEqual({s['status'] for s in view['steps'] if s['ordinal']==0},{status})
                self.assertEqual(view['totals']['confirmed_cost_pence'],0)
                self.assertEqual(view['totals']['unresolved_maximum_cost_pence'],0 if cost==0 else 4)
                app.engagements.advance('one',simulation);self.assertEqual(submitted.call_count,2)
                self.now=NOW+20;view=app.engagements.advance('one',simulation)
                self.assertEqual(view['totals']['accepted_call_tasks'],2 if scenario=='rejection' else 0)
                self.assertEqual(submitted.call_count,2)
            restarted=self.app(email_scenario=scenario)
            with patch.object(restarted.engagements.email,'submit',side_effect=AssertionError('no retry')):
                self.assertEqual(restarted.engagements.advance('one',simulation),view)
            with self.assertRaises(Conflict):self.app(email_scenario='success').engagements.advance('one',simulation)
            self.now=NOW

    def test_crash_after_reservation_leaves_unknown_and_never_repeats_the_provider(self):
        app,proposal,simulation=self.start();store=app.engagements.store
        claim=store.claim('one',simulation,app.engagements.configuration(),1)
        self.assertIsNotNone(claim)
        self.now+=2
        restarted=self.app();provider=restarted.engagements.email
        with patch.object(provider,'submit',wraps=provider.submit) as submitted:
            view=restarted.engagements.advance('one',simulation)
        self.assertEqual(submitted.call_count,1)
        lost=next(s for s in view['steps'] if s['id']==claim.step_id)
        self.assertEqual(lost['status'],'unknown');self.assertIsNone(lost['submission'])
        self.assertEqual(view['totals']['unresolved_maximum_cost_pence'],2)
        self.assertEqual(self.counts()['engagement_dispatches'],2)

    def test_lost_acknowledgement_after_recorded_submission_never_repeats_effect(self):
        app,proposal,simulation=self.start();store=app.engagements.store
        claim=store.claim('one',simulation,app.engagements.configuration(),1)
        receipt=app.engagements.email.submit(claim.intent)
        with patch.object(store,'_settle',side_effect=OSError('process loss')):
            with self.assertRaises(OSError):store.settle(claim,receipt)
        self.now+=2;view=self.app().engagements.advance('one',simulation)
        lost=next(s for s in view['steps'] if s['id']==claim.step_id)
        self.assertEqual(lost['status'],'unknown');self.assertEqual(lost['submission'],asdict(receipt))
        self.assertEqual(view['totals']['confirmed_cost_pence'],4)

    def test_stop_during_provider_work_preserves_observation_without_continuation_authority(self):
        app,proposal,simulation=self.start();submit=app.engagements.email.submit
        def stopped(intent):
            app.engagements.stop('one','stop',simulation)
            return submit(intent)
        with patch.object(app.engagements.email,'submit',side_effect=stopped) as called:
            view=app.engagements.advance('one',simulation)
        self.assertEqual(called.call_count,1);self.assertEqual(view['status'],'stopped')
        self.assertEqual(view['totals']['accepted'],1);self.assertEqual(view['totals']['confirmed_cost_pence'],2)
        self.assertEqual(view['totals']['states']['stopped'],6)
        app,proposal,second=self.start(key='reply-in-flight')
        initial=app.engagements.advance('one',second);self.now=NOW+20
        call_submit=app.engagements.calls.submit
        def reply(intent):
            email=next(s for s in initial['steps'] if s['ordinal']==0 and s['contact_id']==intent['contact_id'])
            self.event(app,second,email,'replied')
            return call_submit(intent)
        with patch.object(app.engagements.calls,'submit',side_effect=reply):
            replied=app.engagements.advance('one',second,max_steps=1)
        paused=next(s for s in replied['steps'] if s['channel']=='human_call' and s['submission'])
        self.assertEqual(paused['status'],'paused');self.assertEqual(paused['submission']['status'],'accepted')
        self.assertEqual(replied['totals']['states']['paused'],2)
        app,proposal,third=self.start(key='revoked-in-flight')
        email_submit=app.engagements.email.submit
        contacts=build_contact_directory(self.path,'one','fielddesk',lambda:self.now)
        def revoked(intent):
            contacts.object('one','revoke-email',intent['contact_id'],'email','acquisition','stop')
            return email_submit(intent)
        with patch.object(app.engagements.email,'submit',side_effect=revoked):
            blocked=app.engagements.advance('one',third,max_steps=1)
        completed=next(s for s in blocked['steps'] if s['submission'])
        self.assertEqual(completed['status'],'blocked');self.assertEqual(completed['submission']['status'],'accepted')

    def test_forged_and_substituted_provider_receipts_do_not_settle_a_step(self):
        app,proposal,simulation=self.start();store=app.engagements.store
        claim=store.claim('one',simulation,app.engagements.configuration(),180)
        receipt=app.engagements.email.submit(claim.intent)
        for attack in (replace(receipt,effect_key='other-effect'),replace(receipt,request_hash='other-hash'),
            replace(receipt,connection_id='other-connection'),replace(receipt,confirmed_cost_pence=0)):
            with self.assertRaises(Conflict):store.settle(claim,attack)
        self.assertEqual(app.engagements.inspect('one',simulation)['totals']['accepted'],0)
        store.settle(claim,receipt);before=self.counts();store.settle(claim,receipt)
        self.assertEqual(self.counts(),before)

    def test_observations_bind_effect_and_time_and_deduplicate_across_request_keys(self):
        app,proposal,simulation=self.start();view=app.engagements.advance('one',simulation)
        step=next(s for s in view['steps'] if s['ordinal']==0)
        for effect,kind,when in (('other-effect','delivered',self.now),(step['submission']['provider_effect_id'],'task_completed',self.now),
                                (step['submission']['provider_effect_id'],'delivered',self.now+1)):
            with self.assertRaises(Conflict):app.engagements.observe('one','bad',simulation,step['id'],effect,kind,when)
        first=self.event(app,simulation,step,'delivered');before=self.counts()
        second=self.event(app,simulation,step,'delivered','new-key')
        self.assertEqual(second,first)
        for name in ('engagement_observations','engagement_events'):self.assertEqual(self.counts()[name],before[name])
        with self.assertRaises(Conflict):self.event(app,simulation,step,'bounced')
        self.now=NOW+20;view=app.engagements.advance('one',simulation)
        call=next(s for s in view['steps'] if s['channel']=='human_call' and s['contact_id']==step['contact_id'])
        self.event(app,simulation,step,'replied');self.event(app,simulation,call,'replied')
        totals=app.engagements.inspect('one',simulation)['totals']
        self.assertEqual(totals['responded'],1);self.assertEqual(totals['response_observations'],2)

    def test_lease_expiry_after_result_write_rolls_back_transition_but_keeps_provider_observation(self):
        app,proposal,simulation=self.start();store=app.engagements.store
        claim=store.claim('one',simulation,app.engagements.configuration(),1);receipt=app.engagements.email.submit(claim.intent)
        transition=store._transition
        def expire(*args):transition(*args);self.now+=2
        with patch.object(store,'_transition',side_effect=expire),self.assertRaises(LeaseLost):store.settle(claim,receipt)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT status FROM engagement_steps WHERE id=?',(claim.step_id,)).fetchone()[0],'dispatching')
            self.assertFalse(any(json.loads(r[0])['kind']=='step_accepted' for r in db.execute('SELECT payload FROM engagement_events')))
        view=app.engagements.inspect('one',simulation)
        self.assertEqual(view['totals']['accepted'],1);self.assertEqual(view['totals']['states']['unknown'],1)

    def test_scope_paused_roots_and_historical_proposal_replay_preserve_boundaries(self):
        app,proposal,simulation=self.start();before=self.counts()
        for read in (lambda:app.campaigns.inspect('other',proposal['proposal_id']),lambda:app.engagements.inspect('other',simulation)):
            with self.assertRaises(NotFound):read()
        readonly=self.app(read_only=True)
        with self.assertRaises(Conflict):readonly.engagements.advance('one',simulation)
        with self.assertRaises(Conflict):self.prepare(readonly,'readonly')
        self.assertEqual(self.counts(),before)
        from acquisition.adapters.sqlite.admission_guard import seal_legacy_writes
        with app.campaigns.store.database.transaction() as db:seal_legacy_writes(db,lambda:self.now)
        with self.assertRaises(Conflict):app.engagements.advance('one',simulation)
        # A separate restored template exercises expiry without modifying the sealed history.
        self.path=Path(self.temp.name)/'expiry.sqlite';self.copy_template()
        app,proposal,simulation=self.start()
        self.now=NOW+8*86400
        replay=self.prepare(app);self.assertEqual(replay['saved'],proposal['saved'])
        self.assertFalse(app.campaigns.inspect('one',proposal['proposal_id'])['currently_applicable'])
        with self.assertRaises(Conflict):self.prepare(app,'expired')
        self.assertTrue(all(s['status']=='blocked' for s in app.engagements.advance('one',simulation)['steps']))

    def test_claim_and_completion_reject_substituted_intent_and_preserve_immutable_step_inputs(self):
        app,proposal,simulation=self.start();store=app.engagements.store
        claim=store.claim('one',simulation,app.engagements.configuration(),180)
        receipt=app.engagements.email.submit(claim.intent)
        altered=copy.deepcopy(claim.intent);altered['contact_id']='another-contact'
        with self.assertRaises(Conflict):store.settle(replace(claim,intent=altered),receipt)
        with store.database.transaction() as db:
            with self.assertRaises(sqlite3.IntegrityError):db.execute('UPDATE engagement_steps SET due_at=due_at+1 WHERE id=?',(claim.step_id,))
            with self.assertRaises(sqlite3.IntegrityError):db.execute('DELETE FROM engagement_steps WHERE id=?',(claim.step_id,))
        store.settle(claim,receipt)
        self.assertEqual(app.engagements.inspect('one',simulation)['totals']['accepted'],1)
        # Terminal facts cannot be requeued into a new logical effect.
        for terminal in ('accepted','rejected','partial','unknown','stopped','blocked'):
            for next_state in ('pending','dispatching'):
                with self.assertRaises(Conflict):validate_step_transition(terminal,next_state)
        with self.assertRaises(Conflict):validate_step_transition('paused','dispatching')

    def test_schema_20_migration_failure_is_atomic_and_preserves_history_and_legacy_cutoff(self):
        database=Database(self.path)
        tables=('sequence_proposals','sequence_commands','engagement_simulations','engagement_enrollments',
            'engagement_steps','engagement_dispatches','engagement_observations','engagement_stops','engagement_commands','engagement_events')
        with database.transaction() as db:
            original_bytes=[tuple(r) for r in db.execute('SELECT * FROM channel_artifacts ORDER BY id')]
            db.execute("INSERT INTO runs VALUES('old','one','old','old-hash','succeeded',?)",(NOW,))
            db.execute("INSERT INTO legacy_task_admissions VALUES('one','old','old-hash')")
            for table in tables:db.execute('DROP TABLE '+table)
            db.execute('PRAGMA user_version=20')
        apply=Database._apply_migration
        def fail(db,script):
            apply(db,script)
            if 'CREATE TABLE IF NOT EXISTS sequence_proposals' in script:raise OSError('injected migration failure')
        with patch.object(Database,'_apply_migration',side_effect=fail),self.assertRaises(OSError):Database(self.path)
        with database.connect() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],20)
            self.assertIsNone(db.execute("SELECT name FROM sqlite_schema WHERE name='engagement_steps'").fetchone())
            self.assertEqual([tuple(r) for r in db.execute('SELECT * FROM channel_artifacts ORDER BY id')],original_bytes)
        Database(self.path)
        with database.connect() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],22)
            self.assertEqual([tuple(r) for r in db.execute('SELECT * FROM channel_artifacts ORDER BY id')],original_bytes)
            self.assertEqual(tuple(db.execute('SELECT * FROM legacy_task_admissions').fetchone()),('one','old','old-hash'))

    def test_concurrent_start_and_claim_preserve_one_enrollment_and_one_dispatch_per_step(self):
        app=self.app();proposal=self.prepare(app)
        approval=self.approve(app,proposal)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda key:app.engagements.start('one',key,proposal['proposal_id'],approval['id']),('start-one','start-two')))
        self.assertEqual(len({r['simulation_id'] for r in results}),1)
        simulation=results[0]['simulation_id']
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _:app.engagements.advance('one',simulation,max_steps=1),range(2)))
        view=app.engagements.inspect('one',simulation)
        self.assertEqual(len(view['enrollments']),2);self.assertEqual(len(view['steps']),6)
        self.assertEqual(view['totals']['accepted'],2)
        self.assertEqual(self.counts()['engagement_dispatches'],2)

    def test_reservation_expiry_and_postwrite_stop_roll_back_authority_transitions(self):
        app,proposal,simulation=self.start();store=app.engagements.store;event=store._event
        before=self.counts()
        def expire(db,org,sim,kind,**data):
            event(db,org,sim,kind,**data)
            if kind=='step_reserved':self.now+=181
        with patch.object(store,'_event',side_effect=expire),self.assertRaises(LeaseLost):
            app.engagements.advance('one',simulation)
        self.assertEqual(self.counts(),before)
        claim=store.claim('one',simulation,app.engagements.configuration(),180)
        receipt=app.engagements.email.submit(claim.intent);transition=store._transition
        def stop_after_write(db,row,status):
            transition(db,row,status)
            payload={'scope':'account','subject_id':row['account_id'],'action':'stop','source':'injected-objection'}
            db.execute('INSERT INTO engagement_stops VALUES(?,?,NULL,?,?,?,?)',
                ('one','engagement_stop_'+digest(payload),'account',row['account_id'],'stop',canonical(payload)))
        with patch.object(store,'_transition',side_effect=stop_after_write),self.assertRaises(Conflict):store.settle(claim,receipt)
        with store.database.connect() as db:
            self.assertEqual(db.execute('SELECT status FROM engagement_steps WHERE id=?',(claim.step_id,)).fetchone()[0],'dispatching')
            self.assertEqual(db.execute('SELECT count(*) FROM engagement_stops').fetchone()[0],0)
        self.assertEqual(app.engagements.inspect('one',simulation)['totals']['accepted'],1)


if __name__=='__main__':unittest.main()
