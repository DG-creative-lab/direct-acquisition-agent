"""Conversation-to-effect invariants, with cheap interpretation cases and shared real-store templates."""

from collections import Counter
from contextlib import closing
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from acquisition.bootstrap import build, build_channel_preparation, build_sequence_journeys
from acquisition.creative import SYNTHETIC_CHANNEL_ADMISSION
from channel_history import start_legacy_channel
from acquisition.adapters.contact_fixtures import RecordedContactSource
from acquisition.adapters.sequence_interpreter import OfflineSequenceInterpreter
from acquisition.audiences import contact_snapshot_from
from acquisition.adapters.sqlite.admission_guard import binding
from acquisition.adapters.sqlite.database import Database
from acquisition.adapters.sqlite.intake import INTAKE
from acquisition.adapters.sqlite.youtube import YOUTUBE
from acquisition.adapters.sqlite.intake_planning import INTAKE_PLANNING
from acquisition.adapters.sqlite.preparation_context import PREPARATION_CONTEXTS
from acquisition.adapters.sqlite.sequence_journeys import SEQUENCE_JOURNEYS
from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.conversations import journey_request, journey_commands
from acquisition.bootstrap import build_workspace as Workspace
from acquisition.reasoning import ModelError

NOW=1794700800.
ROOT=Path(__file__).resolve().parents[1]
OBJECTIVE='Prepare a {profile} email and human call sequence for UK contacts with a £100 total budget.'


class SequenceIntentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.catalogue=build_sequence_journeys(Path(cls.temp.name)/'app.sqlite',lambda:NOW).host.catalogue('one')

    def interpret(self,*texts):
        return OfflineSequenceInterpreter().interpret([{'id':str(i),'content':t} for i,t in enumerate(texts)],self.catalogue)

    def test_unique_fuzzy_and_material_ambiguity(self):
        self.assertEqual(self.interpret(OBJECTIVE.format(profile='Fielddsek'))['profile_key'],'fielddesk')
        self.assertEqual(self.interpret(OBJECTIVE.format(profile='Fielddsek'))['outcome'],'sequence')
        self.assertEqual(self.interpret('Prepare an email sequence with a £100 budget.')['outcome'],'clarification')
        self.assertEqual(self.interpret(OBJECTIVE.format(profile='Iwoca or Fielddesk'))['outcome'],'clarification')
        self.assertEqual(self.interpret('Prepare an email sequence with a £100 budget.','Fielddesk')['outcome'],'sequence')
        self.assertEqual(self.interpret(OBJECTIVE.format(profile='Fielddesk')+' Use primary CRM and secondary CRM.')['outcome'],'clarification')

    def test_unsupported_scope_is_not_substituted_and_complete_replacement_recovers(self):
        base=OBJECTIVE.format(profile='Fielddesk')
        for addition in (' Use SMS.',' In Germany.',' provider: resend',' audience: VIP',' Exactly two contacts.',' Email only.',' Use autonomous voice.',' strategy: predictive',' Target healthcare.'):
            with self.subTest(addition=addition):self.assertEqual(self.interpret(base+addition)['outcome'],'unsupported')
        self.assertEqual(self.interpret('Prepare an email-only campaign with £100')['outcome'],'unsupported')
        self.assertEqual(self.interpret(base+' In Germany.','£200')['outcome'],'unsupported')
        self.assertEqual(self.interpret(base+' In Germany.',base)['outcome'],'sequence')
        self.assertEqual(self.interpret(base,'Change budget to £200')['budget_pence'],20000)

    def test_postal_routing_requires_an_affirmative_unambiguous_channel(self):
        from acquisition.conversations import postal_request
        for body,expected in (
            ('Prepare a £600 postal response experiment.',True),
            ('Use direct mail instead.',True),
            ('Prepare a postal campaign, not email.',True),
            ('Prepare an email campaign, not postal.',False),
            ('Prepare postal and email campaigns.',False),
            ('Prepare postal and emails.',False),
            ('Prepare postal and human call scripts.',False),
            ('Prepare postal without emails.',True),
            ('Prepare an email and human call sequence.',False),
            ('Fielddesk',False),('status?',False),('Show the postal plan',False),
            ('What is the postal budget?',False),('Please show the postal plan',False),
            ('Can you show the postal plan?',False),('Please prepare a postal campaign.',True),
            ('Now use postal.',True)):
            with self.subTest(body=body):self.assertEqual(postal_request(body),expected)

    def test_interpreter_output_cannot_change_literal_company_source_budget_or_country(self):
        base=OBJECTIVE.format(profile='Fielddesk');proposal=self.interpret(base)
        for changed in (proposal|{'profile_key':'iwoca','connection_key':'iwoca-crm-a'},proposal|{'connection_key':'fielddesk-crm-b'},proposal|{'budget_pence':5000}):
            with self.subTest(changed=changed),self.assertRaises(Conflict):
                journey_request('one','conv',1,'request',[{'id':'m','content':base}],self.catalogue,changed,True,NOW)
        with self.assertRaises(Conflict):journey_request('one','conv',1,'request',[{'id':'m','content':base+' In Germany.'}],self.catalogue,proposal,True,NOW)


class SequenceRoutingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.w=Workspace(self.root,real_clock=lambda:NOW)

    def test_postal_request_leaves_current_sequence_and_historical_rows_do_not_capture_followups(self):
        from acquisition.conversations import FIXTURE_MESSAGE
        for entry in ('messages','actions'):
            with self.subTest(entry=entry):
                c=self.w.create_conversation('conversation-'+entry,'Return to postal')['id']
                first=self.w.message_conversation(c,'sequence-'+entry,0,OBJECTIVE.format(profile='iwoca'))
                journey=first['sequence_journeys'][0]['id']
                frozen=self.w.sequence_journeys.store.get('local-conversations',journey)['inputs']
                returned=(self.w.message_conversation(c,'postal-'+entry,1,FIXTURE_MESSAGE) if entry=='messages'
                    else self.w.route_followup(c,'postal-'+entry,1,FIXTURE_MESSAGE,False))
                self.assertEqual(returned['revision'],2)
                current=self.w.conversation(c)
                self.assertEqual(len(current['sequence_journeys']),1)
                self.assertFalse(current['sequence_journeys'][0]['current'])
                self.assertEqual(returned['messages'][-1]['content'],FIXTURE_MESSAGE)
                self.assertEqual(self.w.sequence_journeys.store.get('local-conversations',journey)['inputs'],frozen)
                reopened=Workspace(self.root,real_clock=lambda:NOW)
                replay=(reopened.message_conversation(c,'postal-'+entry,1,FIXTURE_MESSAGE) if entry=='messages'
                    else reopened.route_followup(c,'postal-'+entry,1,FIXTURE_MESSAGE,False))
                self.assertEqual(replay['revision'],2)
                self.assertEqual(replay['message_receipt']['revision'],2)
                status=reopened.route_followup(c,'postal-status-'+entry,2,'status?',False)
                self.assertEqual(status['revision'],2)
                self.assertEqual(len(status['actions']),1)
                self.assertEqual(status['sequence_interactions'],[])
                self.assertEqual(status['execution']['used'],0)
                from acquisition.conversations import ActionNotSaved
                with self.assertRaises(ActionNotSaved):reopened.route_followup(c,'empty-'+entry,2,'',False)
                # The original bare clarification can still replay after switching.
                replay_sequence=reopened.message_conversation(c,'sequence-'+entry,0,OBJECTIVE.format(profile='iwoca'))
                self.assertEqual(replay_sequence['revision'],2)
                self.assertEqual(replay_sequence['message_receipt']['revision'],1)

    def test_postal_preparation_uses_existing_services_after_channel_change(self):
        from acquisition.conversations import FIXTURE_MESSAGE
        from test_preparations import CombinedModel
        from test_conversations import proposal
        c=self.w.create_conversation('conversation','Sequence then postal')['id']
        first=self.w.message_conversation(c,'sequence',0,OBJECTIVE.format(profile='iwoca'))
        self.w.message_conversation(c,'postal',1,FIXTURE_MESSAGE)
        model=CombinedModel(proposal())
        self.w=Workspace(self.root,real_clock=lambda:NOW,gateway_factory=lambda:model)
        self.w.start_preparation(c,'postal-preparation',2,False,False)
        for _ in range(8):
            self.w.advance_preparations()
            view=self.w.conversation(c)
            if view['preparations'][0]['status']=='review_ready':break
        self.assertEqual(view['preparations'][0]['status'],'review_ready')
        self.assertEqual(len(view['sequence_journeys']),1)
        self.assertFalse(view['sequence_journeys'][0]['current'])
        self.assertEqual(view['campaigns'][0]['revision'],2)
        self.assertEqual(view['execution']['used'],1)
        review=self.w.view(view['campaigns'][0]['session_id'])['review']
        self.assertFalse(review['approval_valid'])
        self.assertIsNone(review['handoff'])
        before=view['execution']['used']
        self.w.sequence_journeys.advance('local-conversations',first['sequence_journeys'][0]['id'])
        self.assertEqual(self.w.conversation(c)['execution']['used'],before)


class SequenceJourneyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.fixture.cleanup)
        cls.templates={}
        for profile in ('fielddesk','iwoca'):
            path=Path(cls.fixture.name)/(profile+'.sqlite')
            native=build(path,clock=lambda:NOW)
            conversation=native.conversations.create('one','conversation','Sequence')['id']
            app=build_sequence_journeys(path,lambda:NOW)
            row=app.send('one',conversation,'message',0,OBJECTIVE.format(profile=profile))
            for _ in range(20):
                row=app.advance('one',row['id'])
                if row['status'] not in {'preparing'}:break
            if row['status']!='ready':raise AssertionError(row)
            cls.templates[profile]=(path,conversation,row['id'])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'app.sqlite';self.now=NOW
        self.copy_template()

    def copy_template(self,profile='fielddesk'):
        path,self.conversation,self.journey=self.templates[profile]
        with closing(sqlite3.connect(path)) as source,closing(sqlite3.connect(self.path)) as target:source.backup(target)
        self.app=build_sequence_journeys(self.path,lambda:self.now)

    def counts(self):
        with closing(sqlite3.connect(self.path)) as db:
            return {table:db.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in ('runs','model_calls','sequence_journeys','sequence_review_decisions','engagement_simulations','engagement_dispatches','engagement_observations','sequence_journey_events')}

    def test_both_companies_one_confirmation_completes_and_reads_never_repeat_effects(self):
        for profile in ('fielddesk','iwoca'):
            with self.subTest(profile=profile):
                self.copy_template(profile)
                view=self.app.view('one',self.journey)
                self.assertTrue(view['review']['validation']['review_ready'])
                self.assertFalse(view['review']['approval_valid'])
                self.assertEqual(self.counts()['sequence_review_decisions'],0)
                before=self.counts()
                self.app.view('one',self.journey);self.app.listing('one',self.conversation)
                self.assertEqual(before,self.counts())
                self.app.approve('one',self.journey,'approval',1,view['review']['subject_id'],'Reviewed exact synthetic proposal.')
                observed=set();interrupted=False
                for _ in range(20):
                    original=self.app.store.progress
                    def fail_after_native_observation(organization,prior,result):
                        nonlocal interrupted
                        if profile=='fielddesk' and not interrupted and result.get('outputs',{}).get('task_observations'):
                            interrupted=True
                            raise OSError('Native observation and clock committed; continuation acknowledgement lost')
                        return original(organization,prior,result)
                    try:
                        with patch.object(self.app.store,'progress',side_effect=fail_after_native_observation):
                            row=self.app.advance('one',self.journey)
                    except OSError:
                        self.app=build_sequence_journeys(self.path,lambda:self.now)
                        # A stale tab repeats one completed task under a new key
                        # after virtual time has advanced. It must remain one observation.
                        self.app.observe_task('one',self.journey,'stale-tab-task',1,sorted(observed)[0])
                        continue
                    if row['status']=='complete':break
                    if row['status']=='awaiting_human':
                        simulation=self.app.view('one',self.journey)['simulation']
                        for step in simulation['steps']:
                            if step['channel']=='human_call' and step['status']=='accepted' and step['id'] not in observed:
                                self.app.observe_task('one',self.journey,'completed-'+str(len(observed)),1,step['id']);observed.add(step['id'])
                self.assertEqual(row['status'],'complete')
                if profile=='fielddesk':self.assertTrue(interrupted)
                self.assertLessEqual(self.counts()['model_calls'],15)
                self.assertEqual(self.counts()['sequence_review_decisions'],1)
                account=build(self.path,clock=lambda:self.now).execution.view('one',self.conversation)
                self.assertEqual(account['used'],self.counts()['model_calls'])
                self.assertTrue(account['accounting_complete'])
                before=self.counts();restarted=build_sequence_journeys(self.path,lambda:self.now)
                restarted.approve('one',self.journey,'approval',1,view['review']['subject_id'],'Reviewed exact synthetic proposal.')
                restarted.advance('one',self.journey);restarted.view('one',self.journey)
                self.assertEqual(before,self.counts())
                with closing(sqlite3.connect(self.path)) as db:
                    native = row['inputs']['native_organization']
                    admissions = db.execute("""SELECT a.run_id, json_extract(a.payload,'$.workflow_version'),
                        e.owner_organization,e.conversation_id,e.revision
                        FROM execution_admissions a JOIN execution_runs e
                        ON e.organization=a.organization AND e.run_id=a.run_id
                        WHERE a.organization=?""",(native,)).fetchall()
                    self.assertCountEqual(admissions,[(row['outputs'][stage+'-run'],SYNTHETIC_CHANNEL_ADMISSION,
                        'one',self.conversation,1) for stage in ('initial','call','followup')])
                    self.assertEqual(db.execute("SELECT count(*) FROM engagement_observations WHERE json_extract(payload,'$.kind') IN ('replied','objected')").fetchone()[0],0)
                simulation=restarted.view('one',self.journey)['simulation']
                last=next(s for s in simulation['steps'] if s['channel']=='email' and s['ordinal']==2)
                app=restarted.host.capabilities(row['inputs'],False)
                native_before=canonical(simulation)
                try:
                    restarted.observe_reply('one',self.journey,'final-reply',1,last['id'])
                except Conflict as error:
                    self.fail(f'A current completed journey must accept its final email reply: {error}')
                with patch.object(restarted.host,'capabilities',return_value=app), \
                     patch.object(app.sequence.engagements,'advance',side_effect=AssertionError('Completed submissions cannot dispatch again')):
                    completed=restarted.advance('one',self.journey)
                self.assertEqual(completed['status'],'complete')
                after=restarted.view('one',self.journey)['simulation']
                self.assertEqual(after['steps'],simulation['steps'])
                self.assertEqual(after['totals']['accepted'],simulation['totals']['accepted'])
                self.assertEqual(after['totals']['responded'],1)
                self.assertEqual(after['observations'][:-1],simulation['observations'])
                self.assertEqual(after['observations'][-1]['kind'],'replied')
                self.assertEqual(after['observations'][-1]['step_id'],last['id'])
                restarted.observe_reply('one',self.journey,'final-reply',1,last['id'])
                restarted.observe_reply('one',self.journey,'final-reply-second-key',1,last['id'])
                restarted=build_sequence_journeys(self.path,lambda:self.now)
                restarted.advance('one',self.journey)
                self.assertEqual(restarted.view('one',self.journey)['simulation'],after)
                self.assertNotEqual(canonical(after),native_before)

    def test_reply_pauses_only_its_account_and_recovers_original_observation(self):
        for profile in ('fielddesk','iwoca'):
            with self.subTest(profile=profile):
                self.copy_template(profile)
                subject=self.app.view('one',self.journey)['review']['subject_id']
                self.app.approve('one',self.journey,'approval',1,subject,'Reviewed exact proposal.')
                for _ in range(10):
                    self.app.advance('one',self.journey)
                    view=self.app.view('one',self.journey)
                    simulation=view['simulation']
                    if simulation and any(s['channel']=='email' and s['submission'] for s in simulation['steps']):break
                target=next(s for s in simulation['steps'] if s['channel']=='email' and s['submission'])
                pending=next(s for s in simulation['steps'] if s['status']=='pending')
                with self.assertRaises(Conflict):
                    self.app.observe_reply('one',self.journey,'pending-reply',1,pending['id'])
                with self.assertRaises((Conflict,NotFound)):
                    self.app.observe_reply('foreign',self.journey,'foreign-reply',1,target['id'])
                with self.app.store.database.transaction() as db:
                    db.execute("""CREATE TRIGGER fail_reply_fence AFTER INSERT ON engagement_stops
                        BEGIN SELECT RAISE(ABORT,'reply fence failed'); END""")
                try:
                    with self.assertRaisesRegex(sqlite3.IntegrityError,'reply fence failed'):
                        self.app.observe_reply('one',self.journey,'interrupted-reply',1,target['id'])
                    with self.app.store.database.connect() as db:
                        self.assertIsNone(db.execute('SELECT 1 FROM sequence_journey_commands WHERE organization=? AND request_id=?',
                                                    ('one','interrupted-reply')).fetchone())
                        self.assertIsNone(db.execute('SELECT 1 FROM engagement_stops').fetchone())
                finally:
                    with self.app.store.database.transaction() as db:
                        db.execute('DROP TRIGGER fail_reply_fence')
                stale=self.app.store.current('one',self.journey)
                self.now=min(s['due_at'] for s in simulation['steps']
                             if s['account_id']==target['account_id'] and s['status']=='pending')
                original_intents=self.app.store.task_intents
                def save_after_intent_read(organization,journey_id):
                    intents=original_intents(organization,journey_id)
                    self.app.observe_reply('one',self.journey,'reply',1,target['id'])
                    return intents
                with patch.object(self.app.store,'task_intents',side_effect=save_after_intent_read):
                    self.app.advance('one',self.journey)
                raced_simulation=self.app.view('one',self.journey)['simulation']
                self.assertFalse(any(o['kind']=='replied' for o in raced_simulation['observations']))
                self.assertTrue(all(s['submission'] is None for s in raced_simulation['steps']
                    if s['account_id']==target['account_id'] and s['ordinal']>target['ordinal']))
                raced=self.app.store.progress('one',stale,{'status':'awaiting_human'})
                self.assertEqual(raced['status'],'simulating')
                with self.assertRaises(Conflict):
                    self.app.observe_reply('one',self.journey,'reply',1,pending['id'])
                def lose_ack(*args):
                    raise OSError('lost acknowledgement after native observation')
                with patch.object(self.app.store,'progress',side_effect=lose_ack),self.assertRaises(OSError):
                    self.app.advance('one',self.journey)
                self.app=build_sequence_journeys(self.path,lambda:self.now)
                self.app.observe_reply('one',self.journey,'reply',1,target['id'])
                self.app.observe_reply('one',self.journey,'second-tab-reply',1,target['id'])
                resumed=self.app.advance('one',self.journey)
                simulation=self.app.view('one',self.journey)['simulation']
                if any(s['account_id']!=target['account_id'] and s['status']=='pending' for s in simulation['steps']):
                    self.assertNotEqual(resumed['status'],'blocked')
                observations=[o for o in simulation['observations'] if o['kind']=='replied']
                self.assertEqual(len(observations),1)
                self.assertEqual(observations[0]['step_id'],target['id'])
                own=[s for s in simulation['steps'] if s['account_id']==target['account_id'] and s['ordinal']>target['ordinal']]
                self.assertTrue(own)
                self.assertEqual({s['status'] for s in own},{'paused'})
                for _ in range(10):
                    other=[s for s in simulation['steps'] if s['account_id']!=target['account_id']]
                    if any(s['channel']=='human_call' and s['submission'] for s in other):break
                    self.app.advance('one',self.journey)
                    simulation=self.app.view('one',self.journey)['simulation']
                if other:
                    self.assertTrue(any(s['channel']=='human_call' and s['submission'] for s in other))
                if profile=='iwoca':self.assertTrue(other)
                self.assertTrue(all(s['status']=='paused' for s in simulation['steps']
                                    if s['account_id']==target['account_id'] and s['ordinal']>target['ordinal']))
                before=self.counts()
                self.app.view('one',self.journey);self.app.listing('one',self.conversation)
                self.assertEqual(self.counts(),before)
                self.app.stop('one',self.journey,'stop',1)
                self.app.observe_reply('one',self.journey,'reply',1,target['id'])
                with self.assertRaises(Conflict):
                    self.app.observe_reply('one',self.journey,'after-stop',1,target['id'])

    def test_unfinished_call_only_holds_its_own_followup_across_restart(self):
        self.copy_template('iwoca')
        subject=self.app.view('one',self.journey)['review']['subject_id']
        self.app.approve('one',self.journey,'approval',1,subject,'Reviewed exact proposal.')
        for _ in range(10):
            row=self.app.advance('one',self.journey)
            simulation=self.app.view('one',self.journey)['simulation']
            if simulation and any(s['channel']=='human_call' and s['status']=='accepted' for s in simulation['steps']):break
        calls=sorted((s for s in simulation['steps'] if s['channel']=='human_call'),key=lambda s:s['due_at'])
        self.assertEqual(len(calls),2)
        first,second=calls
        self.assertLess(first['due_at'],second['due_at'])
        self.assertEqual(first['status'],'accepted')
        self.assertEqual(second['status'],'pending')
        self.assertEqual(row['status'],'simulating','An unfinished call must not stop an independent scheduled call')
        self.app=build_sequence_journeys(self.path,lambda:self.now)
        for _ in range(10):
            row=self.app.advance('one',self.journey)
            if row['status']=='awaiting_human':break
        simulation=self.app.view('one',self.journey)['simulation']
        self.assertEqual(row['status'],'awaiting_human')
        self.assertTrue(all(s['status']=='accepted' for s in simulation['steps'] if s['channel']=='human_call'))
        self.assertEqual(simulation['observations'],[])
        self.assertEqual(self.app.store.simulation_time('one',self.journey),second['due_at'])
        self.app.observe_task('one',self.journey,'second-call-complete',1,second['id'])
        self.app=build_sequence_journeys(self.path,lambda:self.now)
        for _ in range(10):
            row=self.app.advance('one',self.journey)
            if row['status']=='awaiting_human':break
        simulation=self.app.view('one',self.journey)['simulation']
        followups={s['enrollment_id']:s for s in simulation['steps'] if s['ordinal']==2}
        self.assertEqual(row['status'],'awaiting_human')
        self.assertEqual(followups[first['enrollment_id']]['status'],'pending')
        self.assertEqual(followups[first['enrollment_id']]['waiting_on'],'human_task_completion')
        self.assertEqual(followups[second['enrollment_id']]['status'],'accepted')
        self.assertEqual([(o['step_id'],o['kind']) for o in simulation['observations']],[(second['id'],'task_completed')])
        before=self.counts()
        self.app.advance('one',self.journey);self.app.view('one',self.journey)
        self.assertEqual(before,self.counts(),'Waiting and inspection must not repeat submissions or fabricate completion')
        self.app.observe_task('one',self.journey,'first-call-complete',1,first['id'])
        self.assertEqual(self.app.advance('one',self.journey)['status'],'complete')
        self.assertEqual(self.counts()['engagement_dispatches'],6)
        self.assertEqual(self.counts()['engagement_observations'],2)
        self.assertEqual(self.counts()['model_calls'],before['model_calls'])

    def test_lost_acknowledgement_restart_uses_original_approval_and_simulation_commands(self):
        subject=self.app.view('one',self.journey)['review']['subject_id']
        self.app.approve('one',self.journey,'approval',1,subject,'Reviewed exact proposal.')
        # A subprocess supplies the recovery boundary. No browser state or cached host survives.
        code="from acquisition.bootstrap import build_sequence_journeys; import sys; a=build_sequence_journeys(sys.argv[1],lambda:1794700800.); a.advance('one',sys.argv[2]); a.advance('one',sys.argv[2])"
        subprocess.run([sys.executable,'-c',code,str(self.path),self.journey],env=__import__('os').environ|{'PYTHONPATH':str(ROOT/'src')},check=True,capture_output=True)
        self.assertEqual(self.counts()['sequence_review_decisions'],1)
        self.assertEqual(self.counts()['engagement_simulations'],1)
        before=self.counts()
        self.app.approve('one',self.journey,'approval',1,subject,'Reviewed exact proposal.')
        self.assertEqual(before,self.counts())
        with self.assertRaises(Conflict):self.app.approve('one',self.journey,'approval',1,subject,'Different reason.')

    def test_material_edit_obsoletes_ready_approval_and_prevents_detached_native_work(self):
        row=self.app.store.get('one',self.journey);native=row['inputs']['native_organization']
        view=self.app.view('one',self.journey);subject=view['review']['subject_id']
        from acquisition.bootstrap import build_channel_preparation
        channels=build_channel_preparation(self.path,native,'fielddesk',lambda:self.now)
        before=self.counts()
        with self.assertRaises(Conflict):channels.start(native,'new-key','fielddesk',row['outputs']['email-contexts'],'email')
        self.assertEqual(before,self.counts())
        # New context keys must not detach an assessment from its journey.
        from acquisition.bootstrap import build_recipient_contexts
        contexts=build_recipient_contexts(self.path,native,'fielddesk',lambda:self.now)
        # Emulate contexts already saved by the old writer. Channel admission
        # independently follows their assessment provenance before reserving work.
        derived=[]
        with patch('acquisition.adapters.sqlite.sequence_journeys.recipient_journey_origin',return_value=None):
            for index,key in enumerate(row['outputs']['email-contexts']):
                request=contexts.inspect(native,key)['saved']['request']
                key='previously-derived-'+str(index)
                contexts.prepare(native,key,request['assessment_id'],request['contact_id'],request['source_key'],request['source_version'])
                derived.append(key)
        for state in ('active','stopped'):
            with self.subTest(derived_context=state):
                if state=='stopped':self.app.stop('one',self.journey,'stop-derived-context',1)
                before=self.counts()
                with self.assertRaises(Conflict):
                    channels.start(native,'detached-derived-'+state,'fielddesk',derived,'email')
                self.assertEqual(before,self.counts())
                with closing(sqlite3.connect(self.path)) as db:
                    count=db.execute('SELECT count(*) FROM recipient_context_commands').fetchone()[0]
                for index,key in enumerate(row['outputs']['email-contexts']):
                    request=contexts.inspect(native,key)['saved']['request']
                    with self.assertRaises(Conflict):
                        contexts.prepare(native,'derived-'+state+'-'+str(index),
                            request['assessment_id'],request['contact_id'],request['source_key'],request['source_version'])
                self.assertEqual(before,self.counts())
                with closing(sqlite3.connect(self.path)) as db:
                    self.assertEqual(db.execute('SELECT count(*) FROM recipient_context_commands').fetchone()[0],count)
        self.copy_template()
        self.app.send('one',self.conversation,'edit',1,'Change budget to £200')
        self.assertFalse(self.app.view('one',self.journey)['current'])
        self.assertEqual(self.app.view('one',self.journey)['status'],'historical')
        with self.assertRaises(Conflict):self.app.approve('one',self.journey,'stale',1,subject,'Old proposal.')
        # Even a valid native request cannot move the frozen content to a new command.
        from acquisition.bootstrap import build_sequence_simulation
        from acquisition.campaigns import SequenceRequest
        native_app=build_sequence_simulation(self.path,native,'fielddesk',lambda:self.now)
        request=SequenceRequest(**view['review']['sequence']['request'])
        before=self.counts()
        with self.assertRaises(Conflict):native_app.campaigns.prepare(native,'detached',request)
        self.assertEqual(before,self.counts())
        with self.assertRaises(NotFound):self.app.store.get('other',self.journey)

    def test_reassessment_keeps_frozen_source_ownership_and_standalone_sources_remain_usable(self):
        from acquisition.bootstrap import build_contact_directory, build_recipient_contexts, build_channel_preparation
        row=self.app.store.get('one',self.journey);native=row['inputs']['native_organization']
        self.app.stop('one',self.journey,'stop-reassessment',1)
        self.now+=60
        directory=build_contact_directory(self.path,native,'fielddesk',lambda:self.now)
        before=self.counts()
        with closing(sqlite3.connect(self.path)) as db:
            assessments=db.execute('SELECT count(*) FROM contact_assessments').fetchone()[0]
        for version in (1,2):
            with self.subTest(source_version=version), self.assertRaises(Conflict):
                directory.prepare(native,'refreshed-assessment-'+str(version),'fielddesk-crm-a',version,'email')
        original = directory.source.read(native,'fielddesk-crm-a',1)
        alias_key = 'fielddesk-crm-alias'
        alias = contact_snapshot_from(json.loads(canonical(asdict(original)).replace(original.connection.key,alias_key)))
        self.assertEqual(alias.connection.id,original.connection.id)
        self.assertNotEqual(alias.id,original.id)
        source = RecordedContactSource(native,(original,alias))
        with patch.object(directory,'source',source),patch.object(directory.store,'source',source),self.assertRaises(Conflict):
            directory.prepare(native,'aliased-assessment',alias_key,1,'email')
        self.assertEqual(before,self.counts())
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM contact_assessments').fetchone()[0],assessments)
        # Emulate a later assessment and context saved by the earlier writer.
        with patch('acquisition.adapters.sqlite.sequence_journeys.assessment_journey_origin',return_value=None):
            refreshed=directory.prepare(native,'old-refreshed','fielddesk-crm-a',1,'email')
        self.assertNotEqual(refreshed['assessment_id'],row['outputs']['email-assessment'])
        contexts=build_recipient_contexts(self.path,native,'fielddesk',lambda:self.now)
        person=refreshed['report']['eligible'][0]
        before=self.counts()
        with self.assertRaises(Conflict):
            contexts.prepare(native,'new-refreshed-context',refreshed['assessment_id'],person,'reviewed-context-a',1)
        self.assertEqual(before,self.counts())
        with patch('acquisition.adapters.sqlite.sequence_journeys.recipient_journey_origin',return_value=None):
            contexts.prepare(native,'old-refreshed-context',refreshed['assessment_id'],person,'reviewed-context-a',1)
        before=self.counts()
        channels=build_channel_preparation(self.path,native,'fielddesk',lambda:self.now)
        with self.assertRaises(Conflict):
            channels.start(native,'detached-refreshed-content','fielddesk',['old-refreshed-context'],'email')
        self.assertEqual(before,self.counts())
        # An unowned connection in the same scope, and the same connection in an
        # independent scope, remain genuinely standalone and can generate.
        used=build(self.path,clock=lambda:self.now).execution.view('one',self.conversation)['used']
        for organization,connection in ((native,'fielddesk-crm-b'),('standalone','fielddesk-crm-a')):
            with self.subTest(standalone=(organization,connection)):
                directory=build_contact_directory(self.path,organization,'fielddesk',lambda:self.now)
                assessment=directory.prepare(organization,'standalone-assessment',connection,1,'email')
                contexts=build_recipient_contexts(self.path,organization,'fielddesk',lambda:self.now)
                contexts.prepare(organization,'standalone-context',assessment['assessment_id'],assessment['report']['eligible'][0],'reviewed-context-a',1)
                channels=build_channel_preparation(self.path,organization,'fielddesk',lambda:self.now)
                result=channels.prepare(organization,'standalone-content','fielddesk',['standalone-context'],'email')
                self.assertTrue(result['ready_for_review'])
                self.assertEqual(len(result['model_calls']),3)
        self.assertEqual(build(self.path,clock=lambda:self.now).execution.view('one',self.conversation)['used'],used)

    def test_earlier_detached_run_rechecks_source_before_resume_reservation_and_publication(self):
        from acquisition.bootstrap import build_recipient_contexts, build_channel_preparation
        from acquisition.reasoning import CallScope
        for stage in ('resume','reservation','cached','publication','uncertain','in-flight'):
            with self.subTest(stage=stage):
                self.copy_template()
                row=self.app.store.get('one',self.journey);native=row['inputs']['native_organization']
                contexts=build_recipient_contexts(self.path,native,'fielddesk',lambda:self.now)
                original=contexts.inspect(native,row['outputs']['email-contexts'][0])['saved']['request']
                # Save exactly what the earlier writer allowed, without rewriting
                # any immutable context or run after it has been admitted.
                with patch('acquisition.adapters.sqlite.sequence_journeys.recipient_journey_origin',return_value=None):
                    contexts.prepare(native,'old-detached-recipient',original['assessment_id'],original['contact_id'],original['source_key'],original['source_version'])
                channels=build_channel_preparation(self.path,native,'fielddesk',lambda:self.now)
                def detached_origin(db, organization, request_id, command, *, recipient_origins=None, **kwargs):
                    if recipient_origins is not None:
                        recipient_origins.extend([None]*len(command.recipient_requests))
                    return None
                with patch('acquisition.adapters.sqlite.sequence_journeys.channel_journey_origin',side_effect=detached_origin):
                    run=start_legacy_channel(channels,native,'old-detached-run','fielddesk',['old-detached-recipient'],'email')
                    if stage!='resume':
                        claim=channels.tasks.claim(native,self.now,180,run_id=run)
                        scope=CallScope(native,run,claim.task_id,claim.token)
                        handler=channels.worker.capabilities[claim.capability]
                        if stage=='publication':outcome=handler(claim)
                        if stage in {'cached','in-flight'}:
                            journal=channels.inference.journal
                            self.assertIsNone(journal.reserve(scope,'recorded-probe',digest('fixture request'),5,self.now))
                            if stage=='cached':
                                journal.record(scope,'recorded-probe',{'observation':'synthetic fixture'},None)
                        if stage=='uncertain':
                            with patch.object(channels.inference.gateway,'complete',side_effect=ModelError('provider_timeout')), self.assertRaises(ModelError):
                                handler(claim)
                self.app.stop('one',self.journey,'stop-old-detached',1)
                if stage=='resume':
                    conversation=build(self.path,clock=lambda:self.now).conversations.create('one','another-owner','Later journey')['id']
                    later=self.app.send('one',conversation,'another-owner-message',0,OBJECTIVE.format(profile='fielddesk'))
                    self.app.stop('one',later['id'],'stop-another-owner',1)
                execution=build(self.path,clock=lambda:self.now).execution
                usage=execution.view('one',self.conversation)
                has_detached_receipt=stage in {'cached','publication','uncertain','in-flight'}
                self.assertEqual(usage['accounting_complete'],not has_detached_receipt)
                self.assertEqual(usage['used'],9)
                self.assertEqual(usage['remaining'],None if has_detached_receipt else usage['limit']-9)
                before=self.counts()
                if stage!='resume':
                    with self.assertRaises(Conflict):
                        key='recorded-probe' if stage=='cached' else 'new-call'
                        channels.inference.journal.reserve(scope,key,digest('fixture request'),5,self.now)
                if stage=='in-flight':
                    channels.inference.journal.record(scope,'recorded-probe',{'observation':'late synthetic receipt'},None)
                elif stage=='publication':
                    with self.assertRaises(Conflict):channels.tasks.settle(claim,outcome,self.now)
                elif stage in {'resume','uncertain'}:
                    self.now+=181
                    restarted=build_channel_preparation(self.path,native,'fielddesk',lambda:self.now)
                    restarted.worker.drain(native,run_id=run)
                self.assertEqual(self.counts()['model_calls'],before['model_calls'])
                with closing(sqlite3.connect(self.path)) as db:
                    self.assertEqual(db.execute('SELECT count(*) FROM channel_artifacts WHERE organization=? AND run_id=?',(native,run)).fetchone()[0],0)
                view=channels.inspect(native,'old-detached-run')
                self.assertEqual(channels.ownership(native,run)['status'],'unresolved')
                with self.assertRaises(Conflict):
                    channels.reconcile_ownership(native,run,'0'*64)
                recovered_usage=execution.view('one',self.conversation)
                for field in ('used','remaining','accounting_complete'):
                    self.assertEqual(recovered_usage[field],usage[field])
                self.assertEqual(view['run_id'],run)
                self.assertFalse(view['currently_applicable'])
                self.assertEqual(channels.start(native,'old-detached-run','fielddesk',['old-detached-recipient'],'email'),run)
                if stage=='uncertain':
                    self.assertEqual([r['status'] for r in view['model_calls']],['unknown'])
                if stage=='in-flight':
                    with closing(sqlite3.connect(self.path)) as db:
                        calls=db.execute('SELECT call_key,status,response FROM model_calls WHERE organization=? AND run_id=?',
                                         (native,run)).fetchall()
                    self.assertEqual(calls,[('recorded-probe','recorded',canonical({'observation':'late synthetic receipt'}))])
                    process=subprocess.run([sys.executable,'-m','acquisition.channel_cli','--db',str(self.path),
                        '--organization',native,'--profile','fielddesk','ownership','--run',run],
                        cwd=ROOT,text=True,capture_output=True,timeout=20)
                    self.assertEqual(process.returncode,0,process.stderr)
                    self.assertEqual(json.loads(process.stdout),channels.ownership(native,run))

    def test_standalone_admission_precedes_later_journey_without_losing_its_run(self):
        from acquisition.bootstrap import build_contact_directory, build_recipient_contexts, build_channel_preparation
        cases=tuple(('fielddesk',stage) for stage in ('queued','bound','unknown','legacy-queued','legacy-ambiguous','paused','paused-legacy'))
        for profile,stage in (*cases,('iwoca','queued')):
            with self.subTest(profile=profile,stage=stage):
                path=Path(self.temp.name)/(profile+'-'+stage+'.sqlite')
                journeys=build_sequence_journeys(path,lambda:self.now)
                native=next(p['organization'] for p in journeys.host.catalogue('one')['profiles'] if p['key']==profile)
                connection=profile+'-crm-a'
                directory=build_contact_directory(path,native,profile,lambda:self.now)
                assessment=directory.prepare(native,'independent-assessment',connection,1,'email')
                contexts=build_recipient_contexts(path,native,profile,lambda:self.now)
                contexts.prepare(native,'independent-context',assessment['assessment_id'],assessment['report']['eligible'][0],'reviewed-context-a',1)
                paused=stage.startswith('paused')
                channels=build_channel_preparation(path,native,profile,lambda:self.now,stage_ownership=paused)
                if paused or stage in {'bound','unknown'}:
                    run=channels.start(native,'independent-run',profile,['independent-context'],'email')
                else:
                    run=start_legacy_channel(channels,native,'independent-run',profile,['independent-context'],'email')
                if paused:
                    admitted=channels.ownership(native,run)
                    self.assertEqual(admitted['status'],'bound')
                if stage=='queued':
                    proof=channels.ownership(native,run)
                    self.assertEqual(proof['status'],'legacy_proven')
                    receipt=channels.reconcile_ownership(native,run,proof['fingerprint'])
                if stage=='unknown':
                    with patch.object(channels.inference.gateway,'complete',side_effect=ModelError('provider_timeout')):
                        channels.worker.drain(native,run_id=run)
                conversation=build(path,clock=lambda:self.now).conversations.create('one','later','Later journey')['id']
                if stage=='legacy-queued':self.now+=1
                original_event=journeys.store._event
                def legacy_event(db,organization,kind,value):
                    if stage.startswith('legacy-') or stage=='paused-legacy':
                        value={k:v for k,v in value.items() if k!='prior_channel_runs'}
                    return original_event(db,organization,kind,value)
                with patch.object(journeys.store,'_event',side_effect=legacy_event):
                    later=journeys.send('one',conversation,'later-message',0,OBJECTIVE.format(profile=profile))
                if stage.startswith('legacy-'):journeys.stop('one',later['id'],'stop-later',1)
                restarted=build_channel_preparation(path,native,profile,lambda:self.now)
                restarted.worker.drain(native,run_id=run)
                view=restarted.inspect(native,'independent-run')
                self.assertEqual(view['currently_applicable'],not stage.startswith('legacy-'))
                self.assertEqual(view['run_id'],run)
                self.assertEqual(restarted.start(native,'independent-run',profile,['independent-context'],'email'),run)
                if stage.startswith('legacy-'):
                    self.assertEqual(restarted.ownership(native,run)['status'],'unresolved')
                if stage=='queued':
                    self.assertEqual(restarted.ownership(native,run)['status'],'legacy_reconciled')
                    self.assertEqual(restarted.reconcile_ownership(native,run,proof['fingerprint']),receipt)
                    self.assertTrue(view['ready_for_review'])
                    self.assertEqual(len(view['model_calls']),3)
                elif stage=='bound':
                    self.assertEqual(restarted.ownership(native,run)['status'],'bound')
                    self.assertTrue(view['ready_for_review'])
                    self.assertEqual(len(view['model_calls']),3)
                else:
                    self.assertFalse(view['ready_for_review'])
                    self.assertEqual([r['status'] for r in view['model_calls']],['unknown'] if stage=='unknown' else [])
                if paused:
                    database = channels.store.database
                    with database.connect() as db:
                        intent = binding(db,native,run)
                    self.assertEqual(intent.ownership.kind,'standalone')
                    self.assertEqual(restarted.ownership(native,run),admitted)
                    self.assertEqual(view['run_status'],'queued')
                    with database.transaction() as db:
                        db.execute('DROP TRIGGER sequence_journey_bindings_no_delete')
                    for request_id,role in (('independent-run','initial'),('independent-context','email-context-0')):
                        with self.subTest(conflicting_binding=role):
                            with database.transaction() as db:
                                db.execute('INSERT INTO sequence_journey_bindings VALUES(?,?,?,?,?)',
                                           (native,request_id,'one',later['id'],role))
                            try:
                                with database.connect() as db,self.assertRaises(Conflict):
                                    binding(db,native,run)
                                self.assertEqual(restarted.ownership(native,run)['status'],'unresolved')
                                damaged = restarted.inspect(native,'independent-run')
                                self.assertFalse(damaged['currently_applicable'])
                                self.assertEqual(damaged['model_calls'],[])
                                self.assertFalse(restarted.tasks.inspect(native,run)['admission']['binding_valid'])
                                with self.assertRaises(Conflict):
                                    restarted.start(native,'independent-run',profile,['independent-context'],'email')
                                self.assertIsNone(restarted.tasks.claim(native,self.now,10,run_id=run))
                            finally:
                                with database.transaction() as db:
                                    db.execute('DELETE FROM sequence_journey_bindings WHERE organization=? AND request_id=?',
                                               (native,request_id))
                    with database.connect() as db:
                        self.assertEqual(binding(db,native,run),intent)
                    self.assertTrue(restarted.inspect(native,'independent-run')['currently_applicable'])
                if not stage.startswith('legacy-'):
                    usage=build(path,clock=lambda:self.now).execution.view('one',conversation)
                    self.assertTrue(usage['accounting_complete'])
                    self.assertEqual(usage['used'],0)
                    advanced=build_sequence_journeys(path,lambda:self.now).advance('one',later['id'])
                    self.assertEqual(advanced['stage'],1)
                    self.assertEqual(advanced['status'],'preparing')
                    if paused:
                        continue
                    recovered=build_sequence_journeys(path,lambda:self.now)
                    for _ in range(20):
                        advanced=recovered.advance('one',later['id'])
                        if advanced['status']!='preparing':break
                    self.assertEqual(advanced['status'],'ready')
                    usage=build(path,clock=lambda:self.now).execution.view('one',conversation)
                    self.assertTrue(usage['accounting_complete'])
                    self.assertEqual(usage['used'],9)
                    review=recovered.view('one',later['id'])['review']
                    self.assertTrue(review['validation']['review_ready'])
                    self.assertFalse(review['approval_valid'])
                    if stage in {'queued','bound'}:
                        journey_runs={advanced['outputs'][name+'-run'] for name in ('initial','call','followup')}
                        self.assertEqual(len(journey_runs),3)
                        with closing(sqlite3.connect(path)) as db:
                            calls=db.execute("""SELECT c.run_id,c.status,e.owner_organization,e.conversation_id,e.revision
                                FROM model_calls c LEFT JOIN execution_runs e
                                ON e.organization=c.organization AND e.run_id=c.run_id
                                WHERE c.organization=?""",(native,)).fetchall()
                            artifacts={r[0] for r in db.execute(
                                'SELECT run_id FROM channel_artifacts WHERE organization=?',(native,))}
                            self.assertIsNone(db.execute(
                                'SELECT 1 FROM sequence_review_decisions WHERE organization=?',(native,)).fetchone())
                        expected=Counter({(r,'recorded','one',conversation,1):3 for r in journey_runs})
                        expected[run,'recorded',None,None,None]=3
                        self.assertEqual(Counter(calls),expected)
                        self.assertEqual(artifacts,journey_runs | {run})
                        self.assertEqual(restarted.inspect(native,'independent-run')['context_id'],view['context_id'])
                    journeys.stop('one',later['id'],'stop-later',1)
                with self.assertRaises(Conflict):
                    directory.prepare(native,'detached-after-journey',connection,1,'email')

    def test_paused_journey_channel_binds_original_owner_and_rechecks_stop_at_commit(self):
        for profile in ('fielddesk','iwoca'):
            with self.subTest(profile=profile):
                path = Path(self.temp.name)/(profile+'-paused.sqlite')
                native = build(path,clock=lambda:self.now)
                conversation = native.conversations.create('one','stage-test','Stage test')['id']
                journeys = build_sequence_journeys(path,lambda:self.now,stage_ownership=True)
                row = journeys.send('one',conversation,'staged-message',0,OBJECTIVE.format(profile=profile))
                for _ in range(3):
                    row = journeys.advance('one',row['id'])
                self.assertEqual(row['stage'],3)
                frozen = row['inputs']
                organization = frozen['native_organization']
                key = journey_commands(row['id'])['initial']
                recipients = row['outputs']['email-contexts']
                channels = journeys.host.capabilities(frozen,False).channels
                db = channels.store.database
                with self.assertRaises(Conflict):
                    channels.start(organization,'unbound-key',profile,recipients,'email')

                def count(connection):
                    return tuple(connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                                 for table in ('runs','tasks','execution_runs','channel_preparations',
                                               'admission_requests','execution_admissions','creative_contexts'))
                with db.connect() as connection:
                    before = count(connection)
                failures = (
                    ("AFTER INSERT ON execution_runs", "SELECT RAISE(ABORT,'late link fault')",
                     sqlite3.IntegrityError, 'late link fault'),
                    ("AFTER INSERT ON channel_preparations", """UPDATE sequence_journeys
                    SET state=json_set(state,'$.status','cancelled')""", Conflict, 'stopped'),
                    ("AFTER INSERT ON channel_preparations", """UPDATE conversations
                    SET revision=revision+1 WHERE organization='one'""", Conflict, 'changed'),
                )
                for event,statement,error,message in failures:
                    with self.subTest(event=event,error=message):
                        with db.transaction() as connection:
                            connection.execute(f'CREATE TRIGGER interrupt_channel {event} BEGIN {statement}; END')
                        try:
                            with self.assertRaisesRegex(error,message):
                                channels.start(organization,key,profile,recipients,'email')
                            with db.connect() as connection:
                                self.assertEqual(count(connection),before)
                        finally:
                            with db.transaction() as connection:
                                connection.execute('DROP TRIGGER interrupt_channel')

                advanced = journeys.advance('one',row['id'])
                run = advanced['outputs']['initial-run']
                with db.connect() as connection:
                    intent = binding(connection,organization,run)
                    receipt = connection.execute('SELECT receipt FROM execution_admissions WHERE run_id=?',(run,)).fetchone()[0]
                    self.assertEqual(intent.ownership.account_key,('conversation','one',conversation))
                    self.assertEqual(intent.ownership.revision,1)
                    self.assertEqual(intent.model_config.payload(),frozen['model_config'])
                    self.assertEqual(count(connection),tuple(value+1 for value in before))
                self.assertEqual(native.execution.view('one',conversation)['used'],0)
                self.assertEqual(advanced['stage'],3)
                self.assertEqual(channels.ownership(organization,run)['status'],'bound')
                self.assertTrue(channels.inspect(organization,key)['currently_applicable'])
                with db.transaction() as connection:
                    connection.execute('DROP TRIGGER sequence_journey_bindings_no_delete')
                    connection.execute('DROP TRIGGER sequence_journey_bindings_no_update')
                assessment_key = journey_commands(row['id'])['email-assessment']
                for binding_key,damage in ((recipients[0],'missing'),(recipients[0],'conflicting'),(assessment_key,'missing')):
                    with self.subTest(binding_key=binding_key,damage=damage):
                        with db.transaction() as connection:
                            original = tuple(connection.execute(
                                'SELECT * FROM sequence_journey_bindings WHERE organization=? AND request_id=?',
                                (organization,binding_key)).fetchone())
                            if damage=='missing':
                                connection.execute('DELETE FROM sequence_journey_bindings WHERE organization=? AND request_id=?',
                                                   (organization,binding_key))
                            else:
                                connection.execute("UPDATE sequence_journey_bindings SET role='initial' WHERE organization=? AND request_id=?",
                                                   (organization,binding_key))
                        try:
                            with db.connect() as connection,self.assertRaises(Conflict):
                                binding(connection,organization,run)
                            self.assertEqual(channels.ownership(organization,run)['status'],'unresolved')
                            view = channels.inspect(organization,key)
                            self.assertFalse(view['currently_applicable'])
                            self.assertEqual(view['model_calls'],[])
                            self.assertFalse(channels.tasks.inspect(organization,run)['admission']['binding_valid'])
                            self.assertIsNone(channels.tasks.claim(organization,self.now,10,run_id=run))
                        finally:
                            with db.transaction() as connection:
                                connection.execute('DELETE FROM sequence_journey_bindings WHERE organization=? AND request_id=?',
                                                   (organization,binding_key))
                                connection.execute('INSERT INTO sequence_journey_bindings VALUES(?,?,?,?,?)',original)
                self.assertEqual(channels.ownership(organization,run)['status'],'bound')
                journeys.stop('one',row['id'],'stopped',1)
                restarted = build_channel_preparation(path,organization,profile,lambda:self.now)
                self.assertEqual(restarted.start(organization,key,profile,recipients,'email'),run)
                view = restarted.inspect(organization,key)
                self.assertFalse(view['currently_applicable'])
                self.assertEqual(view['model_calls'],[])
                self.assertIsNone(restarted.tasks.claim(organization,self.now,10,run_id=run))
                with db.connect() as connection:
                    self.assertEqual(binding(connection,organization,run),intent)
                    self.assertEqual(connection.execute('SELECT receipt FROM execution_admissions WHERE run_id=?',(run,)).fetchone()[0],receipt)

    def test_stop_after_confirmation_and_disabled_reviewer_cannot_dispatch(self):
        subject=self.app.view('one',self.journey)['review']['subject_id']
        self.app.approve('one',self.journey,'approval',1,subject,'Reviewed exact proposal.')
        self.app.stop('one',self.journey,'stop',1)
        before=self.counts();self.app.advance('one',self.journey)
        self.assertEqual(self.app.store.get('one',self.journey)['status'],'cancelled')
        self.assertEqual(before,self.counts())
        self.copy_template()
        self.app.approve('one',self.journey,'approval',1,subject,'Reviewed exact proposal.')
        from acquisition.adapters.sqlite.reviews import SqliteReviews
        from acquisition.adapters.sqlite.simulated_delivery import SqliteSimulatedDelivery
        native=self.app.store.get('one',self.journey)['inputs']['native_organization']
        roles=SqliteReviews(Database(self.path),lambda:self.now,SqliteSimulatedDelivery)
        roles.register_actor(native,'local-reviewer',('reviewer',),enabled=False)
        self.assertEqual(self.app.advance('one',self.journey)['status'],'blocked')
        self.assertEqual(self.counts()['sequence_review_decisions'],0)
        self.assertEqual(self.counts()['engagement_dispatches'],0)

    def test_atomic_message_admission_consent_and_exact_replay(self):
        native=build(self.path,clock=lambda:self.now);conv=native.conversations.create('one','second','Other request')['id']
        original=self.app.store._event
        def fail(db,organization,kind,value):
            if kind=='requested':raise OSError('storage interruption before admission commit')
            return original(db,organization,kind,value)
        with patch.object(self.app.store,'_event',side_effect=fail),self.assertRaises(OSError):
            self.app.send('one',conv,'original',0,OBJECTIVE.format(profile='fielddesk'))
        self.assertEqual(native.conversations.view('one',conv)['revision'],0)
        row=self.app.send('one',conv,'original',0,OBJECTIVE.format(profile='fielddesk'),False)
        self.assertEqual(row['status'],'consent_required')
        self.assertEqual(self.app.send('one',conv,'original',0,OBJECTIVE.format(profile='fielddesk'),False)['id'],row['id'])
        with self.assertRaises(Conflict):self.app.send('one',conv,'original',0,OBJECTIVE.format(profile='fielddesk'),True)
        with self.assertRaises(Conflict):self.app.request('one',conv,'new-key',1,True)
        before=self.counts();self.app.advance('one',row['id']);self.assertEqual(before,self.counts())

    def test_interruption_or_unknown_call_keeps_original_usage_without_publication(self):
        for kind in ('cancel','edit','unknown'):
            with self.subTest(kind=kind):
                native=build(self.path,clock=lambda:self.now)
                conv=native.conversations.create('one','during-'+kind,'Interrupted generation')['id']
                row=self.app.send('one',conv,'message-'+kind,0,OBJECTIVE.format(profile='fielddesk'))
                for _ in range(3):row=self.app.advance('one',row['id'])
                self.assertEqual(row['stage'],3)
                original=self.app.host.capabilities;called=[]
                def capabilities(frozen,inspection):
                    result=original(frozen,inspection)
                    gateway=result.channels.inference.gateway
                    class Interrupt:
                        def complete(inner,request):
                            called.append(request)
                            if kind=='cancel':self.app.stop('one',row['id'],'stop-in-call',1)
                            elif kind=='edit':self.app.send('one',conv,'edit-in-call',1,'Change budget to £200')
                            else:raise ModelError('provider_timeout')
                            return gateway.complete(request)
                    if not inspection:result.channels.inference.gateway=Interrupt()
                    return result
                before=self.counts()['model_calls']
                with patch.object(self.app.host,'capabilities',side_effect=capabilities):self.app.advance('one',row['id'])
                after=self.counts();self.assertEqual(len(called),1)
                self.assertEqual(after['model_calls'],before+1)
                usage=build(self.path,clock=lambda:self.now).execution.view('one',conv)
                self.assertTrue(usage['accounting_complete'])
                self.assertEqual(usage['used'],1)
                self.assertEqual(usage['remaining'],usage['limit']-1)
                self.assertEqual([call['revision'] for call in usage['calls']],[1])
                self.app.advance('one',row['id'])
                self.assertEqual(after,self.counts())
                with closing(sqlite3.connect(self.path)) as db:
                    self.assertEqual(db.execute('SELECT status FROM model_calls WHERE run_id=(SELECT run_id FROM channel_preparations WHERE organization=? AND request_id=?)',
                        (row['inputs']['native_organization'],journey_commands(row['id'])['initial'])).fetchone()[0],'unknown' if kind=='unknown' else 'recorded')
                    self.assertFalse(db.execute("SELECT 1 FROM channel_artifacts WHERE organization=? AND json_extract(payload,'$.context_id') IN (SELECT context_id FROM channel_preparations WHERE request_id=?)",
                        (row['inputs']['native_organization'],journey_commands(row['id'])['initial'])).fetchall())

    def test_frozen_journey_finds_receipts_after_task_origin_index_and_account_loss(self):
        for lose_account in (False,True):
            with self.subTest(lose_account=lose_account):
                self.copy_template()
                native=self.app.store.get('one',self.journey)['inputs']['native_organization']
                with Database(self.path).transaction() as db:
                    db.execute('DELETE FROM execution_runs WHERE organization=?',(native,))
                    db.execute("UPDATE tasks SET inputs=json_remove(inputs,'$.journey') WHERE run_id IN (SELECT id FROM runs WHERE organization=?)",(native,))
                    if lose_account:db.execute('DELETE FROM conversation_execution WHERE organization=? AND conversation_id=?',('one',self.conversation))
                before=self.counts()
                app=build(self.path,clock=lambda:self.now)
                usage=app.execution.view('one',self.conversation)
                self.assertFalse(usage['accounting_complete'])
                self.assertIsNone(usage['remaining'])
                with self.assertRaises(Conflict):self.app.send('one',self.conversation,'new-request',1,'Change budget to £200')
                self.assertEqual(app.conversations.view('one',self.conversation)['revision'],1)
                self.assertEqual(before,self.counts())

    def test_verified_admissions_remain_paused_before_message_or_task_commit(self):
        path=Path(self.temp.name)/'verified.sqlite'
        native=build(path,clock=lambda:self.now,verified_admissions=True)
        conv=native.conversations.create('one','new','Paused workspace')['id']
        journeys=build_sequence_journeys(path,lambda:self.now)
        with self.assertRaises(Conflict):journeys.send('one',conv,'message',0,OBJECTIVE.format(profile='fielddesk'))
        self.assertEqual(native.conversations.view('one',conv)['revision'],0)
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM sequence_journeys').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM runs').fetchone()[0],0)

    def test_workspace_routes_questions_without_revision_or_model_changes(self):
        root=Path(self.temp.name)/'workspace';w=Workspace(root,real_clock=lambda:self.now)
        c=w.create_conversation('conversation','Email sequence')['id']
        first=w.message_conversation(c,'message',0,'Prepare an email sequence with a £100 budget.')
        self.assertEqual(first['sequence_journeys'][0]['status'],'clarification')
        answered=w.route_followup(c,'company',1,'Fielddesk',False)
        self.assertEqual(answered['revision'],2)
        self.assertEqual(answered['sequence_journeys'][-1]['status'],'preparing')
        view=w.route_followup(c,'question',2,'What is the status?',False)
        self.assertEqual(view['revision'],2)
        self.assertEqual(view['sequence_interactions'][0]['content'],'What is the status?')
        self.assertEqual(Workspace(root,real_clock=lambda:self.now).route_followup(c,'question',2,'What is the status?',False)['revision'],2)
        self.assertFalse(view['actions'])
        other=w.create_conversation('other','Independent sequence')['id']
        second=w.message_conversation(other,'other-message',0,OBJECTIVE.format(profile='iwoca'))
        original=w.sequence_journeys.advance
        first_id=answered['sequence_journeys'][-1]['id']
        def interrupted(organization,journey_id):
            if journey_id==first_id:raise OSError('One unavailable job')
            return original(organization,journey_id)
        with patch.object(w.sequence_journeys,'advance',side_effect=interrupted):w.advance_preparations()
        second_id=second['sequence_journeys'][-1]['id']
        self.assertEqual(w.sequence_journeys.store.get('local-conversations',second_id)['stage'],1)
        stopped=w.route_followup(c,'stop-text',2,'stop',False)
        self.assertEqual(stopped['revision'],2)
        self.assertEqual(stopped['sequence_journeys'][-1]['status'],'cancelled')
        self.assertEqual(len(stopped['sequence_interactions']),2)

    def test_schema_22_upgrade_preserves_exact_history_and_cutoff(self):
        # A real preceding schema, not a latest database relabeled as an old one.
        path=Path(self.temp.name)/'previous.sqlite';apply=Database._apply_migration
        def previous(db,script):
            if script not in {SEQUENCE_JOURNEYS, INTAKE, INTAKE_PLANNING, YOUTUBE, PREPARATION_CONTEXTS}:return apply(db,script)
        with patch.object(Database,'_apply_migration',side_effect=previous),patch.object(Database,'_validate_sequence_journey_schema'), patch('acquisition.adapters.sqlite.intake.validate_intake_schema'), patch('acquisition.adapters.sqlite.intake_planning.validate_intake_planning_schema'), patch('acquisition.adapters.sqlite.preparation_context.validate_preparation_context_schema'), patch('acquisition.adapters.sqlite.youtube.validate_youtube_schema'):
            old=Database(path)
        with old.transaction() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],22)
            db.execute("INSERT INTO audiences VALUES('old','artifact','{\"frozen\":\"Historical wording\"}')")
            before=db.execute('SELECT * FROM legacy_task_admissions').fetchall()
        def interrupted(db,script):
            apply(db,script)
            if script==SEQUENCE_JOURNEYS:raise OSError('interrupted after new DDL')
        with patch.object(Database,'_apply_migration',side_effect=interrupted),self.assertRaises(OSError):Database(path)
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],22)
            self.assertIsNone(db.execute("SELECT name FROM sqlite_schema WHERE name='sequence_journeys'").fetchone())
        Database(path)
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],27)
            self.assertEqual(db.execute('SELECT payload FROM audiences').fetchone()[0],'{"frozen":"Historical wording"}')
            self.assertEqual([tuple(r) for r in before],db.execute('SELECT * FROM legacy_task_admissions').fetchall())


if __name__=='__main__':unittest.main()
