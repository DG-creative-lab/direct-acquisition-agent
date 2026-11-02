"""Natural-language copy edits preserve native revision and approval authority."""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

from acquisition.contracts import Conflict, NotFound
from acquisition.reasoning import ModelError
from acquisition.workspace import Workspace
from test_copy_revisions import RevisionModel
from test_model_copy import reply


class CopyRoutingModel(RevisionModel):
    def __init__(self):
        super().__init__()
        self.action='revise_copy'
        self.routing_requests=[]

    def complete(self,request):
        if request['tools'][0]['function']['name']=='propose_conversation_action':
            self.routing_requests.append(request)
            return reply('propose_conversation_action',{'action':self.action})
        return super().complete(request)


class ConversationalCopyRevisionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.now=1793404800.
        self.model=CopyRoutingModel()
        for p in (patch('acquisition.workspace.openrouter_key',return_value='fixture'),
                  patch('acquisition.workspace.OpenRouter',return_value=self.model)):
            p.start();self.addCleanup(p.stop)
        self.w=Workspace(self.root,real_clock=lambda:self.now)
        self.c=self.w.create_conversation('copy-chat','Copy campaign')['id']
        self.w.message_conversation(self.c,'m',0,'Prepare a £600 contractor campaign with model copy.')
        self.w.start_preparation(self.c,'prepare',1,False,True,True)
        for _ in range(3):self.w.advance_preparations()
        view=self.w.conversation(self.c);entry=view['preparations'][0]['audience_candidates']['entries'][0]
        self.w.select_conversation_audience(self.c,request_id='source',expected_revision=1,plan_id=view['current_plan']['result']['id'],
            dataset_id=entry['dataset_id'],version=entry['version'],checksum=entry['checksum'],manifest_id=entry['id'])
        for _ in range(6):self.w.advance_preparations()
        self.sid=self.w.conversation(self.c)['campaigns'][0]['session_id']
        self.base=self.w.view(self.sid)

    def route(self,content='Make variant B more direct. Keep variant A and the audience unchanged.',request='edit'):
        self.w.route_followup(self.c,request,1,content,False)
        self.w.advance_actions()
        return self.w.conversation(self.c)['actions'][-1]

    def confirm(self,action,request='confirm',consent=True):
        return self.w.confirm_copy_followup(self.c,action['id'],request,action['result']['id'],1,consent)

    def test_copy_proposal_waits_for_explicit_consent_then_reuses_native_revision(self):
        subject=self.base['review']['subject']['id']
        self.w.action(self.sid,'approve',{'request_id':'approval','subject_id':subject,'reason':'Reviewed exact base draft.'})
        action=self.route()
        self.assertEqual(action['result']['copy_revision']['status'],'ready')
        self.assertEqual(action['result']['copy_revision']['target']['arm'],'B')
        self.assertTrue(self.w.view(self.sid)['review']['approval_valid'])
        self.assertEqual(self.model.revision_calls,[])
        with self.assertRaises(ValueError):self.confirm(action,consent=False)
        self.confirm(action)
        self.assertEqual(self.model.revision_calls,[])
        self.assertFalse(self.w.view(self.sid)['review']['approval_valid'])
        self.assertEqual(self.w.conversation(self.c)['revision'],1)
        for _ in range(5):self.w.advance_copy_revisions()
        revised=self.w.view(self.sid)
        self.assertEqual(revised['copy_revisions'][-1]['status'],'complete')
        self.assertNotEqual(revised['review']['subject']['id'],subject)
        self.assertFalse(revised['review']['approval_valid'])
        old_a=next(c for c in self.base['review']['manifest']['creatives'] if c['arm']=='A')
        new_a=next(c for c in revised['review']['manifest']['creatives'] if c['arm']=='A')
        for field in ("id","headline","opening","hypothesis","locked_block","fact_id"):
            self.assertEqual(old_a[field],new_a[field])
        self.assertEqual(revised['review']['manifest']['brief'],self.base['review']['manifest']['brief'])
        self.assertEqual(revised['review']['manifest']['counts'],self.base['review']['manifest']['counts'])
        self.assertEqual(self.w.conversation(self.c)['revision'],1)
        self.assertEqual(self.w.conversation(self.c)['actions'][-1]['copy_revision_progress']['status'],'complete')

    def test_missing_variant_clarifies_and_retains_the_exact_feedback(self):
        first=self.route('Make the copy more direct.')
        self.assertEqual(first['result']['copy_revision']['status'],'needs_target')
        self.assertFalse(first['result']['requires_confirmation'])
        with self.assertRaises(Conflict):self.confirm(first)
        action=self.route('B',request='target-answer')
        proposal=action['result']['copy_revision']
        self.assertEqual(proposal['status'],'ready')
        self.assertEqual(proposal['target']['arm'],'B')
        self.assertEqual(proposal['feedback'],'Make the copy more direct. / B')
        self.assertEqual(proposal['messages'][0]['action_id'],first['id'])
        wire=json.loads(self.model.routing_requests[-1]['messages'][-1]['content'])
        self.assertEqual(wire['dialogue']['copy_exchange'][0]['content'],'Make the copy more direct.')
        self.assertEqual(self.model.revision_calls,[])
        self.confirm(action)
        session=self.w._session(self.sid);app=self.w._app(session)
        receipt=app.reviews.store.revision_request(session['organization'],action['id']+':copy')
        self.assertEqual(receipt['inputs']['feedback'],proposal['feedback'])
        self.assertEqual(receipt['task_inputs']['model_config']['max_calls'],5)
        self.assertEqual(len(self.w.conversation(self.c)['messages']),1)

    def test_selector_only_question_remembers_variant_when_feedback_arrives(self):
        selected=self.route('B',request='select-variant')
        self.assertEqual(selected['result']['copy_revision']['status'],'needs_feedback')
        self.route('status?',request='inspection-between-answers')
        self.w=Workspace(self.root,real_clock=lambda:self.now)
        action=self.route('Make it more direct.',request='wording-answer')
        proposal=action['result']['copy_revision']
        self.assertEqual(proposal['status'],'ready')
        self.assertEqual(proposal['target']['arm'],'B')
        self.assertEqual(proposal['feedback'],'B / Make it more direct.')
        self.assertEqual(proposal['messages'][0]['action_id'],selected['id'])
        self.confirm(action)
        self.assertEqual(self.w.view(self.sid)['copy_revisions'][0]['feedback'],'B / Make it more direct.')
        self.assertEqual(self.w.conversation(self.c)['revision'],1)

    def test_ready_edit_does_not_supply_feedback_for_independent_target(self):
        first=self.route('Make variant B more formal.',request='formal-b')
        self.assertEqual(first['result']['copy_revision']['status'],'ready')
        action=self.route('Make variant A more casual.',request='casual-a')
        proposal=action['result']['copy_revision']
        self.assertEqual(proposal['status'],'ready')
        self.assertEqual(proposal['target']['arm'],'A')
        self.assertEqual(proposal['feedback'],'Make variant A more casual.')
        self.assertEqual(proposal['messages'],[{'action_id':None,'content':'Make variant A more casual.','response':None}])
        self.confirm(action)
        self.assertEqual(self.w.view(self.sid)['copy_revisions'][0]['feedback'],'Make variant A more casual.')
        self.assertIsNone(self.w.conversation(self.c)['actions'][0]['confirmed'])

    def test_complete_edit_replaces_an_earlier_unresolved_request(self):
        first=self.route('Make the copy more formal.',request='unclear-formal')
        self.assertEqual(first['result']['copy_revision']['status'],'needs_target')
        action=self.route('Make variant A more casual.',request='complete-new-edit')
        self.assertEqual(action['result']['copy_revision']['feedback'],'Make variant A more casual.')
        self.assertEqual(len(action['result']['copy_revision']['messages']),1)
        self.confirm(action)
        self.assertEqual(self.w.view(self.sid)['copy_revisions'][0]['feedback'],'Make variant A more casual.')

    def test_reply_after_ready_proposal_starts_a_new_clarification_chain(self):
        self.route('Make variant B more formal.',request='ready-formal')
        next_edit=self.route('Make it more direct.',request='new-wording')
        self.assertEqual(next_edit['result']['copy_revision']['status'],'needs_target')
        action=self.route('B',request='new-variant-answer')
        self.assertEqual(action['result']['copy_revision']['status'],'ready')
        self.assertEqual(action['result']['copy_revision']['feedback'],'Make it more direct. / B')
        self.confirm(action)
        self.assertEqual(self.w.view(self.sid)['copy_revisions'][0]['feedback'],'Make it more direct. / B')

    def test_old_cross_target_ready_carry_is_rejected_without_rewriting_saved_result(self):
        from acquisition.contracts import digest
        first=self.route('Make variant B more formal.',request='old-formal-b')
        original=self.w.action_context
        def old_context(*args,**kwargs):
            value=original(*args,**kwargs)
            value['dialogue']['version']='routing-dialogue/v3'
            value['dialogue']['copy_exchange']=[{'action_id':first['id'],'content':first['content'],
                'response':{k:first['result'][k] for k in ('id','kind','text')}}]
            return value|{'id':'action_context_'+digest({k:v for k,v in value.items() if k!='id'})}
        with patch.object(self.w,'action_context',side_effect=old_context):
            action=self.route('Make variant A more casual.',request='old-casual-a')
        self.assertEqual(action['result']['copy_revision']['feedback'],'Make variant B more formal. / Make variant A more casual.')
        app=self.w._conversation_app();saved=app.actions.store.get('local-conversations',action['id'])
        with self.assertRaises(Conflict):self.confirm(action)
        self.assertEqual(app.actions.store.get('local-conversations',action['id']),saved)
        self.assertEqual(self.w.view(self.sid)['copy_revisions'],[])

    def test_invalid_feedback_does_not_persist_as_selector_context(self):
        invalid='Make variant B more direct'+chr(0x2014)+'please.'
        first=self.route(invalid,request='invalid-feedback')
        self.assertEqual(first['result']['copy_revision']['status'],'needs_feedback')
        action=self.route('Make variant A more casual.',request='valid-restatement')
        self.assertEqual(action['result']['copy_revision']['feedback'],'Make variant A more casual.')
        self.assertEqual(len(action['result']['copy_revision']['messages']),1)
        self.confirm(action)
        self.assertEqual(self.w.view(self.sid)['copy_revisions'][0]['feedback'],'Make variant A more casual.')

    def test_dialogue_v3_same_target_recorded_request_replays_without_rewriting_feedback(self):
        from acquisition.adapters.sqlite.tasks import SqliteTasks
        from acquisition.contracts import digest
        original_context=self.w.action_context
        def legacy_context(*args,**kwargs):
            value=original_context(*args,**kwargs)
            value['dialogue']['version']='routing-dialogue/v3'
            return value|{'id':'action_context_'+digest({k:v for k,v in value.items() if k!='id'})}
        with patch.object(self.w,'action_context',side_effect=legacy_context):
            first=self.route('Make variant B more formal.',request='legacy-formal')
        def legacy_carry(*args,**kwargs):
            value=legacy_context(*args,**kwargs)
            value['dialogue']['copy_exchange']=[{'action_id':first['id'],'content':first['content'],
                'response':{k:first['result'][k] for k in ('id','kind','text')}}]
            return value|{'id':'action_context_'+digest({k:v for k,v in value.items() if k!='id'})}
        with patch.object(self.w,'action_context',side_effect=legacy_carry):
            self.w.route_followup(self.c,'legacy-direct',1,'Make variant B more direct.',False)
        original_settle=SqliteTasks.settle
        def interrupt(store,claim,outcome,now):
            if claim.capability=='conversations.route.v2':raise KeyboardInterrupt()
            return original_settle(store,claim,outcome,now)
        with patch.object(SqliteTasks,'settle',new=interrupt):
            with self.assertRaises(KeyboardInterrupt):self.w.advance_actions()
        original_request=json.dumps(self.model.routing_requests[-1],sort_keys=True)
        app=self.w._conversation_app()
        frozen=app.actions.store.request('local-conversations',self.c,'legacy-direct')
        self.w=Workspace(self.root,real_clock=lambda:self.now);self.w.recover_actions();self.now+=181
        self.w.advance_actions()
        action=self.w.conversation(self.c)['actions'][-1]
        self.assertEqual(action['status'],'succeeded')
        self.assertEqual(action['result']['copy_revision']['feedback'],'Make variant B more formal. / Make variant B more direct.')
        self.assertEqual(len(self.model.routing_requests),2)
        self.assertEqual(json.dumps(self.model.routing_requests[-1],sort_keys=True),original_request)
        self.assertEqual(app.actions.store.get('local-conversations',frozen['id']),frozen)
        self.confirm(action)
        self.assertEqual(self.w.view(self.sid)['copy_revisions'][0]['feedback'],'Make variant B more formal. / Make variant B more direct.')

    def test_consent_requires_true_and_cannot_be_inherited_from_routing(self):
        self.w.route_followup(self.c,'edit',1,'Make variant B more direct.',True)
        self.w.advance_actions()
        action=self.w.conversation(self.c)['actions'][-1]
        for value in (False,None,1,'true'):
            with self.assertRaises(ValueError):self.confirm(action,consent=value)
        self.assertEqual(self.w.view(self.sid)['copy_revisions'],[])
        self.assertIsNone(self.w.conversation(self.c)['actions'][-1]['confirmed'])
        self.assertEqual(self.model.revision_calls,[])

    def test_wrong_result_subject_or_conversation_cannot_be_confirmed(self):
        action=self.route()
        with self.assertRaises(Conflict):
            self.w.confirm_copy_followup(self.c,action['id'],'wrong-result','action_result_wrong',1,True)
        other=self.w.create_conversation('other','Other conversation')['id']
        with self.assertRaises(NotFound):
            self.w.confirm_copy_followup(other,action['id'],'wrong-chat',action['result']['id'],1,True)
        self.w.message_conversation(self.c,'changed',1,'Use £700 instead.')
        with self.assertRaises(Conflict):self.confirm(action)
        self.assertEqual(self.w.view(self.sid)['copy_revisions'],[])

    def test_manual_revision_changes_invalidate_the_frozen_chat_target(self):
        action=self.route()
        target=action['result']['copy_revision']['target']
        self.w.request_copy_revision(self.sid,'manual',target['subject_id'],target['id'],'Make B more direct.',True)
        for _ in range(5):self.w.advance_copy_revisions()
        before=len(self.model.revision_calls)
        with self.assertRaises(Conflict):self.confirm(action)
        view=self.w.conversation(self.c)
        self.assertFalse(view['actions'][-1]['target_current'])
        self.assertIsNone(view['actions'][-1]['confirmed'])
        self.assertEqual(len(self.model.revision_calls),before)
        new=self.route('B',request='old-question-reply')
        self.assertEqual(new['result']['copy_revision']['status'],'needs_feedback')

    def test_confirmation_and_native_admission_rollback_with_approval_rejection(self):
        subject=self.base['review']['subject']['id']
        self.w.action(self.sid,'approve',{'request_id':'approval','subject_id':subject,'reason':'Reviewed exact draft.'})
        action=self.route()
        app=self.w._app(self.w._session(self.sid))
        for name,sql in (
            ('fail_copy_confirm',"BEFORE UPDATE OF confirmed ON conversation_actions"),
            ('fail_copy_alias',"BEFORE INSERT ON conversation_action_commands"),
        ):
            with self.subTest(stage=name):
                with app.tasks.database.connect() as db:db.execute(f"CREATE TRIGGER {name} {sql} BEGIN SELECT RAISE(ABORT,'fault'); END")
                with self.assertRaises(sqlite3.IntegrityError):self.confirm(action)
                self.assertTrue(self.w.view(self.sid)['review']['approval_valid'])
                self.assertEqual(self.w.view(self.sid)['copy_revisions'],[])
                self.assertIsNone(self.w.conversation(self.c)['actions'][-1]['confirmed'])
                with app.tasks.database.connect() as db:db.execute(f'DROP TRIGGER {name}')
        self.confirm(action)
        self.assertFalse(self.w.view(self.sid)['review']['approval_valid'])
        self.assertEqual(len(self.w.view(self.sid)['copy_revisions']),1)
        self.assertEqual(self.model.revision_calls,[])

    def test_lost_confirmation_response_and_restart_replay_the_same_revision(self):
        action=self.route()
        with patch.object(self.w,'conversation',side_effect=OSError('response lost after commit')):
            with self.assertRaises(OSError):self.confirm(action)
        self.w=Workspace(self.root,real_clock=lambda:self.now)
        for _ in range(5):self.w.advance_preparations()
        before=len(self.model.revision_calls)
        with patch('acquisition.workspace.openrouter_key',side_effect=ValueError('key removed')):
            replay=self.confirm(action)
            alias=self.confirm(action,request='another-observation')
        self.assertEqual(replay['actions'][-1]['confirmed'],alias['actions'][-1]['confirmed'])
        self.assertEqual(len(self.w.view(self.sid)['copy_revisions']),1)
        self.assertEqual(len(self.model.revision_calls),before)
        self.assertEqual(self.w.conversation(self.c)['revision'],1)

    def test_concurrent_confirmation_creates_one_native_effect(self):
        action=self.route()
        with ThreadPoolExecutor(max_workers=2) as pool:
            views=list(pool.map(lambda key:self.confirm(action,request=key),('one','two')))
        self.assertEqual(views[0]['actions'][-1]['confirmed'],views[1]['actions'][-1]['confirmed'])
        state=self.w.view(self.sid)
        self.assertEqual(len(state['copy_revisions']),1)
        self.assertEqual(sum(e['kind']=='copy_revision_requested' for e in state['review']['events']),1)
        self.assertEqual(self.model.revision_calls,[])

    def test_missing_key_blocks_the_saved_revision_and_restoration_resumes_it(self):
        action=self.route()
        with patch('acquisition.workspace.openrouter_key',side_effect=ValueError('key missing')):
            self.confirm(action)
            self.w.advance_copy_revisions()
            progress=self.w.conversation(self.c)['actions'][-1]['copy_revision_progress']
            self.assertEqual(progress['status'],'blocked')
            self.assertEqual(progress['block']['code'],'configuration_unavailable')
            self.assertEqual(self.model.revision_calls,[])
        for _ in range(5):self.w.advance_copy_revisions()
        progress=self.w.conversation(self.c)['actions'][-1]['copy_revision_progress']
        self.assertEqual(progress['status'],'complete')
        self.assertEqual(len(self.w.view(self.sid)['copy_revisions']),1)

    def test_uncertain_revision_remains_visible_and_is_never_repeated(self):
        action=self.route();self.confirm(action)
        with patch.object(self.model,'complete',side_effect=ModelError('provider_request_failed')) as failed:
            self.w.advance_copy_revisions()
            self.assertEqual(failed.call_count,1)
        for _ in range(3):self.w.advance_copy_revisions()
        progress=self.w.conversation(self.c)['actions'][-1]['copy_revision_progress']
        self.assertEqual(progress['status'],'uncertain')
        self.assertTrue(progress['generation']['outcome_uncertain'])
        self.assertEqual(self.model.revision_calls,[])

    def test_read_only_routing_cannot_enter_the_copy_confirmation_path(self):
        action=self.route('status?')
        self.assertEqual(action['result']['kind'],'inspect_progress')
        with self.assertRaises(Conflict):self.confirm(action)
        self.assertEqual(self.w.view(self.sid)['copy_revisions'],[])

    def test_capability_substitution_cannot_dispatch_a_new_routing_admission(self):
        self.w.route_followup(self.c,'edit',1,'Make variant B more direct.',False)
        app=self.w._conversation_app(with_model=True)
        row=app.actions.store.request('local-conversations',self.c,'edit')
        run=app.tasks.find_run('local-conversations',row['run_request_id'])
        with app.tasks.database.transaction() as db:
            db.execute("UPDATE tasks SET capability='conversations.route.v1' WHERE run_id=?",(run,))
        app.worker.tick('local-conversations',run_id=run)
        self.assertEqual(self.model.routing_requests,[])
        self.assertEqual(app.calls.inspect('local-conversations',run),[])

    def test_native_feedback_limit_can_be_recovered_by_a_complete_restatement(self):
        first=self.route('Make variant B more direct. '+('x'*500))
        self.assertEqual(first['result']['copy_revision']['status'],'needs_feedback')
        action=self.route('Make variant B more direct.',request='shorter')
        self.assertEqual(action['result']['copy_revision']['status'],'ready')
        self.assertEqual(action['result']['copy_revision']['feedback'],'Make variant B more direct.')
        self.confirm(action)
        self.assertEqual(len(self.w.view(self.sid)['copy_revisions']),1)

    def test_frozen_preview_must_match_the_actual_creative_at_confirmation(self):
        original=self.w.action_context
        def wrong_preview(*args,**kwargs):
            from acquisition.contracts import digest
            value=original(*args,**kwargs)
            target=next(c for c in value['copy_revision_targets']['creatives'] if c['arm']=='B')
            target['headline']='A different displayed headline?'
            return value|{'id':'action_context_'+digest({k:v for k,v in value.items() if k!='id'})}
        with patch.object(self.w,'action_context',side_effect=wrong_preview):action=self.route()
        with self.assertRaisesRegex(Conflict,'preview'):self.confirm(action)
        self.assertEqual(self.w.view(self.sid)['copy_revisions'],[])
        self.assertIsNone(self.w.conversation(self.c)['actions'][-1]['confirmed'])

    def test_changed_clarification_cannot_supply_feedback_to_confirmation(self):
        first=self.route('Make the copy more direct.')
        action=self.route('B',request='target')
        app=self.w._conversation_app()
        with app.tasks.database.transaction() as db:
            row=app.actions.store.get('local-conversations',first['id'])
            changed={k:v for k,v in row.items() if k!='confirmed'}
            changed['inputs']['content']='Different feedback.'
            db.execute('UPDATE conversation_actions SET payload=? WHERE organization=? AND id=?',
                (json.dumps(changed),'local-conversations',first['id']))
        with self.assertRaises(Conflict):self.confirm(action)
        session=self.w._session(self.sid)
        self.assertEqual(self.w._app(session).revisions.view(session['organization'],session['case_id']),[])
        self.assertIsNone(app.actions.store.get('local-conversations',action['id'])['confirmed'])

    def test_confirmation_key_cannot_be_reused_for_another_copy_proposal(self):
        first=self.route('Make variant B more direct.')
        self.confirm(first,request='shared')
        for _ in range(5):self.w.advance_copy_revisions()
        second=self.route('Make variant A more direct.',request='second')
        self.assertEqual(second['result']['copy_revision']['status'],'ready')
        with self.assertRaises(Conflict):self.confirm(second,request='shared')
        self.assertEqual(len(self.w.view(self.sid)['copy_revisions']),1)

    def test_multiple_segment_variants_require_the_segment_name(self):
        from test_conversations import proposal
        self.model.planner.results=[proposal(segments=['inventory','contractors'],copy_mode='model')]
        c=self.w.create_conversation('combined','Combined campaign')['id']
        self.w.message_conversation(c,'combined-m',0,'Prepare a £600 inventory and contractor experiment with model copy.')
        self.w.start_preparation(c,'combined-prep',1,False,True,True)
        for _ in range(3):self.w.advance_preparations()
        view=self.w.conversation(c);entry=view['preparations'][0]['audience_candidates']['entries'][0]
        self.w.select_conversation_audience(c,request_id='combined-source',expected_revision=1,plan_id=view['current_plan']['result']['id'],
            dataset_id=entry['dataset_id'],version=entry['version'],checksum=entry['checksum'],manifest_id=entry['id'])
        for _ in range(8):self.w.advance_preparations()
        self.w.route_followup(c,'which-b',1,'Make variant B more direct.',False);self.w.advance_actions()
        self.assertEqual(self.w.conversation(c)['actions'][-1]['result']['copy_revision']['status'],'needs_target')
        self.w.route_followup(c,'inventory-answer',1,'inventory',False);self.w.advance_actions()
        proposal=self.w.conversation(c)['actions'][-1]['result']['copy_revision']
        self.assertEqual(proposal['status'],'ready')
        self.assertEqual((proposal['target']['segment'],proposal['target']['arm']),('inventory','B'))
        self.assertEqual(self.model.revision_calls,[])

    def test_fixture_campaigns_cannot_be_silently_converted_to_model_revisions(self):
        from acquisition.conversations import FIXTURE_MESSAGE
        c=self.w.create_conversation('offline','Offline campaign')['id']
        self.w.message_conversation(c,'offline-m',0,FIXTURE_MESSAGE)
        self.w.start_preparation(c,'offline-p',1,True,False,False)
        for _ in range(8):self.w.advance_preparations()
        self.w.route_followup(c,'offline-edit',1,'Make variant B more direct.',False);self.w.advance_actions()
        action=self.w.conversation(c)['actions'][-1]
        self.assertEqual(action['result']['copy_revision']['status'],'unavailable')
        with self.assertRaises(Conflict):
            self.w.confirm_copy_followup(c,action['id'],'offline-confirm',action['result']['id'],1,True)
        self.assertEqual(self.model.revision_calls,[])

    def test_direct_native_admission_must_bind_the_exact_routing_result(self):
        action=self.route()
        target=action['result']['copy_revision']['target']
        reference={'organization':'local-conversations','conversation_id':self.c,'action_id':action['id'],
                   'result_id':'action_result_different','revision':1}
        session=self.w._session(self.sid);app=self.w._app(session,revision_admission=True)
        with self.assertRaises(Conflict):
            app.revisions.admit(session['organization'],session['case_id'],action['id']+':copy',target['subject_id'],
                target['id'],action['result']['copy_revision']['feedback'],True,
                conversation_action=reference,confirmation_request_id='direct-wrong-result')
        self.assertEqual(app.revisions.view(session['organization'],session['case_id']),[])

    def test_carried_feedback_must_match_the_independent_original_action(self):
        self.route('Make the copy more direct.')
        original=self.w.action_context
        def substituted(*args,**kwargs):
            from acquisition.contracts import digest
            value=original(*args,**kwargs)
            value['dialogue']['copy_exchange'][0]['content']='Use a different editorial instruction.'
            return value|{'id':'action_context_'+digest({k:v for k,v in value.items() if k!='id'})}
        with patch.object(self.w,'action_context',side_effect=substituted):action=self.route('B',request='answer')
        with self.assertRaises(Conflict):self.confirm(action)
        self.assertEqual(self.w.view(self.sid)['copy_revisions'],[])
