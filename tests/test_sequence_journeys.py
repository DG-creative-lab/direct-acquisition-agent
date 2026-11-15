"""Conversation-to-effect invariants, with cheap interpretation cases and shared real-store templates."""

from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from acquisition.bootstrap import build, build_sequence_journeys
from acquisition.adapters.sequence_interpreter import OfflineSequenceInterpreter
from acquisition.adapters.sqlite.database import Database
from acquisition.adapters.sqlite.sequence_journeys import SEQUENCE_JOURNEYS
from acquisition.contracts import Conflict, NotFound
from acquisition.conversations import journey_request, journey_commands
from acquisition.workspace import Workspace
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
        with patch('acquisition.workspace.openrouter_key',return_value='fixture'),patch('acquisition.workspace.OpenRouter',return_value=model):
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
                before=self.counts();restarted=build_sequence_journeys(self.path,lambda:self.now)
                restarted.approve('one',self.journey,'approval',1,view['review']['subject_id'],'Reviewed exact synthetic proposal.')
                restarted.advance('one',self.journey);restarted.view('one',self.journey)
                self.assertEqual(before,self.counts())
                with closing(sqlite3.connect(self.path)) as db:
                    self.assertEqual(db.execute("SELECT count(*) FROM engagement_observations WHERE json_extract(payload,'$.kind') IN ('replied','objected')").fetchone()[0],0)

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
            if script!=SEQUENCE_JOURNEYS:return apply(db,script)
        with patch.object(Database,'_apply_migration',side_effect=previous),patch.object(Database,'_validate_sequence_journey_schema'):
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
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],23)
            self.assertEqual(db.execute('SELECT payload FROM audiences').fetchone()[0],'{"frozen":"Historical wording"}')
            self.assertEqual([tuple(r) for r in before],db.execute('SELECT * FROM legacy_task_admissions').fetchall())


if __name__=='__main__':unittest.main()
