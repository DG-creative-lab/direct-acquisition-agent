"""Inspection continuity and confirmed amendments through real SQLite and journals."""
import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from unittest.mock import patch

from acquisition.bootstrap import build
from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.conversations import ActionNotSaved, FIXTURE_MESSAGE
from acquisition.reasoning import ModelConfig, ModelError
from acquisition.workspace import Workspace
from test_model_copy import reply
from test_preparations import CombinedModel


class ActionGateway(CombinedModel):
    def __init__(self):
        super().__init__();self.action='amend_brief';self.routing_requests=[];self.during_route=None
    def complete(self,request):
        if request['tools'][0]['function']['name']=='propose_conversation_action':
            self.routing_requests.append(request)
            if self.during_route:self.during_route()
            return reply('propose_conversation_action',{'action':self.action})
        return super().complete(request)


class ConversationActionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.now=1793404800.
        self.w=Workspace(self.root,real_clock=lambda:self.now);self.gateway=ActionGateway()
        for p in (patch('acquisition.workspace.openrouter_key',return_value='fixture'),
                  patch('acquisition.workspace.OpenRouter',return_value=self.gateway)):
            p.start();self.addCleanup(p.stop)
        self.c=self.w.create_conversation('c','Follow-up continuity')['id']
        self.w.message_conversation(self.c,'m',0,FIXTURE_MESSAGE)
        self.w.start_preparation(self.c,'prepare',1,True,False,True)
        for _ in range(3):self.w.advance_preparations()
        view=self.w.conversation(self.c);entry=view['preparations'][0]['audience_candidates']['entries'][0]
        self.w.select_conversation_audience(self.c,request_id='source',expected_revision=1,plan_id=view['current_plan']['result']['id'],
            dataset_id=entry['dataset_id'],version=entry['version'],checksum=entry['checksum'],manifest_id=entry['id'])
        for _ in range(6):self.w.advance_preparations()
        self.sid=self.w.conversation(self.c)['campaigns'][0]['session_id']
        self.base=self.w.view(self.sid)

    def ask(self,content='status?',key='question',consent=False):
        return self.w.route_followup(self.c,key,1,content,consent)

    def routed(self,content='Change the budget to £400.',key='change',consent=False):
        self.ask(content,key,consent);self.w.advance_actions()
        action=self.w.conversation(self.c)['actions'][-1]
        self.assertEqual(action['status'],'succeeded')
        return action

    def confirm(self,action,key='confirm'):
        return self.w.confirm_followup(self.c,action['id'],key,action['result']['target']['id'],1)

    def test_read_questions_preserve_revision_source_approval_and_original_preparation(self):
        subject=self.base['review']['subject']['id']
        approved=self.w.action(self.sid,'approve',{'request_id':'approve','subject_id':subject,'reason':'Reviewed the exact synthetic campaign.'})
        for i,question in enumerate(('status?','Why did you choose this audience?','Why were these businesses excluded?','Explain validation')):
            view=self.ask(question,str(i))
            self.assertEqual(view['revision'],1)
            self.assertEqual(len(view['messages']),1)
            self.assertEqual(len(view['preparations']),1)
            self.assertIsNotNone(view['actions'][-1]['result'])
        current=self.w.view(self.sid)
        self.assertEqual(current['review']['subject']['id'],subject)
        self.assertEqual(current['review']['manifest']['brief']['audience_source'],self.base['review']['manifest']['brief']['audience_source'])
        self.assertTrue(current['review']['approval_valid'])
        self.assertEqual(self.gateway.routing_requests,[]);self.assertEqual(self.gateway.copy.requests,[])

    def test_fuzzy_inspection_uses_one_bounded_call_and_saved_evidence(self):
        self.gateway.action='explain_exclusions'
        action=self.routed('What kept some of the records out of the shortlist?')
        self.assertEqual(len(self.gateway.routing_requests),1)
        self.assertEqual(action['result']['evidence']['exclusion_reasons'],self.base['review']['manifest']['exclusion_reasons'])
        self.assertIn(str(self.base['review']['manifest']['counts']['excluded']),action['result']['text'])
        self.assertEqual(self.w.conversation(self.c)['revision'],1)
        self.w.advance_actions();self.assertEqual(len(self.gateway.routing_requests),1)
        app=self.w._conversation_app();row=app.actions.store.get('local-conversations',action['id'])
        self.assertEqual(row['model_config']['max_calls'],1)
        self.assertEqual(row['context']['agent_assets']['skills'][0]['id'],'route-followup/v2')
        self.assertIn('task_observation',{s['kind'] for s in row['context']['agent_assets']['sources']})

    def test_short_budget_answer_routes_with_the_actual_planner_question_before_confirmation(self):
        from test_conversations import proposal
        question='What total GBP budget should I use for this contractor campaign?'
        original='Prepare an offline direct-mail experiment for UK contractors.'
        self.gateway.planner.results=[proposal(outcome='clarification',budget_pence=None,question=question)]
        c=self.w.create_conversation('budget-chat','Budget clarification')['id']
        self.w.message_conversation(c,'budget-request',0,original)
        self.w.start_preparation(c,'budget-plan',1,False,False,True)
        for _ in range(3):self.w.advance_preparations()
        before=self.w.conversation(c)
        self.assertEqual(before['preparations'][0]['status'],'needs_input')
        self.w.route_followup(c,'budget-answer',1,'£600',False)
        self.w.advance_actions()
        payload=json.loads(self.gateway.routing_requests[-1]['messages'][-1]['content'])
        self.assertEqual(payload['message'],'£600')
        self.assertEqual(payload['dialogue']['messages'],[
            {'id':'budget-request','revision':1,'role':'user','content':original}])
        response=payload['dialogue']['planner_response']
        self.assertEqual(response['question'],question)
        self.assertEqual(response['id'],before['current_plan']['result']['id'])
        self.assertEqual(response['outcome'],'clarification')
        self.assertTrue(response['current'])
        action=self.w.conversation(c)['actions'][0]
        self.assertEqual(self.w.conversation(c)['revision'],1)
        self.assertEqual(self.w.conversation(c)['campaigns'],[])
        self.gateway.planner.results=[proposal()]
        confirmed=self.w.confirm_followup(c,action['id'],'confirm-budget',action['result']['target']['id'],1)
        self.assertEqual(confirmed['revision'],2)
        self.assertEqual(confirmed['messages'][-1]['content'],'£600')
        for _ in range(3):self.w.advance_preparations()
        planned=self.w.conversation(c)
        self.assertEqual(planned['current_plan']['result']['budget_pence'],60000)
        self.assertEqual(planned['current_plan']['result']['budget_evidence']['quote'],'£600')
        self.assertEqual(planned['preparations'][-1]['status'],'selecting_audience')
        self.assertEqual(len(self.gateway.routing_requests),1)

    def test_dialogue_stays_frozen_on_replay_and_marks_an_older_question_historical(self):
        from test_conversations import proposal
        question='Should I use offline copy fixtures?'
        self.gateway.planner.results=[proposal(outcome='clarification',question=question)]
        c=self.w.create_conversation('copy-chat','Copy clarification')['id']
        self.w.message_conversation(c,'copy-request',0,'Prepare a £600 UK contractor experiment.')
        self.w.start_preparation(c,'copy-plan',1,False,False,True)
        for _ in range(3):self.w.advance_preparations()
        self.w.route_followup(c,'copy-answer',1,'yes',False)
        app=self.w._conversation_app()
        old=app.actions.store.listing('local-conversations',c)[0]
        self.assertEqual(old['context']['dialogue']['planner_response']['question'],question)
        self.assertTrue(old['context']['dialogue']['planner_response']['current'])
        self.w.message_conversation(c,'intervening',1,'Use £700 instead.')
        self.w=Workspace(self.root,real_clock=lambda:self.now)
        self.w.route_followup(c,'copy-answer',1,'yes',False)
        current=self.w.action_context(c,2)['dialogue']
        self.assertFalse(current['planner_response']['current'])
        self.assertEqual([m['id'] for m in current['messages']],['copy-request','intervening'])
        self.w.advance_actions()
        self.assertEqual(self.gateway.routing_requests,[])
        self.assertEqual(app.actions.store.get('local-conversations',old['id']),old)

    def test_two_maximum_length_messages_and_full_question_are_preflighted_before_dispatch(self):
        from test_conversations import proposal
        question='What GBP budget should I use? '+('q'*570)
        self.gateway.planner.results=[proposal(outcome='clarification',budget_pence=None,question=question)]
        c=self.w.create_conversation('long-chat','Bounded clarification')['id']
        messages=['Prepare a UK contractor experiment. '+('x'*1964), 'Keep the copy concise. '+('y'*1977)]
        self.assertEqual([len(m) for m in messages],[2000,2000])
        for i,message in enumerate(messages):self.w.message_conversation(c,'long-'+str(i),i,message)
        self.w.start_preparation(c,'long-plan',2,False,False,True)
        for _ in range(3):self.w.advance_preparations()
        self.w.route_followup(c,'long-answer',2,'£600',False)
        self.w.advance_actions()
        request=self.gateway.routing_requests[-1]
        dialogue=json.loads(request['messages'][-1]['content'])['dialogue']
        self.assertEqual([m['content'] for m in dialogue['messages']],messages)
        self.assertEqual(dialogue['planner_response']['question'],question)
        self.assertLessEqual(len(canonical(request).encode()),24000)

    def test_amendment_proposal_has_no_effect_until_exact_confirmation(self):
        subject=self.base['review']['subject']['id']
        self.w.action(self.sid,'approve',{'request_id':'approve','subject_id':subject,'reason':'Reviewed exact draft.'})
        action=self.routed()
        self.assertTrue(action['result']['requires_confirmation'])
        self.assertEqual(self.w.conversation(self.c)['revision'],1)
        self.assertTrue(self.w.view(self.sid)['review']['approval_valid'])
        value=self.confirm(action)
        self.assertEqual(value['revision'],2)
        self.assertEqual(value['messages'][-1]['content'],'Change the budget to £400.')
        self.assertFalse(self.w.view(self.sid)['review']['approval_valid'])
        self.assertEqual(len(value['preparations']),2)
        self.assertFalse(value['preparations'][-1]['inputs']['allow_model_copy'])
        self.assertEqual(self.gateway.copy.requests,[])

    def test_router_clarification_carries_exact_request_and_reply_into_budget_replanning(self):
        from test_conversations import proposal
        original='Change the budget to £400 and explain the audience'
        subject=self.base['review']['subject']['id']
        self.w.action(self.sid,'approve',{'request_id':'approve-context','subject_id':subject,'reason':'Reviewed exact draft.'})
        self.gateway.action='clarify'
        question=self.routed(original,'mixed')
        self.gateway.action='amend_brief'
        action=self.routed('Change it','answer')
        payload=json.loads(self.gateway.routing_requests[-1]['messages'][-1]['content'])
        exchange=payload['dialogue']['clarification_exchange']
        self.assertEqual(exchange,[{'action_id':question['id'],'content':original,
            'response':{k:question['result'][k] for k in ('id','kind','text')}}])
        self.assertEqual(action['result']['amendment_exchange'][:-1],exchange)
        self.assertEqual(action['result']['amendment_exchange'][-1]['content'],'Change it')
        self.assertTrue(self.w.view(self.sid)['review']['approval_valid'])
        self.assertEqual(len(self.w.conversation(self.c)['messages']),1)
        self.gateway.planner.results=[proposal(budget_pence=40000)]
        confirmed=self.confirm(action)
        self.assertEqual(confirmed['revision'],3)
        self.assertEqual([m['content'] for m in confirmed['messages']], [FIXTURE_MESSAGE,original,'Change it'])
        self.assertFalse(self.w.view(self.sid)['review']['approval_valid'])
        self.assertEqual(self.confirm(action)['revision'],3)
        self.assertEqual(self.confirm(action,'semantic-replay')['revision'],3)
        for _ in range(3):self.w.advance_preparations()
        planned=self.w.conversation(self.c)
        self.assertEqual(planned['current_plan']['result']['budget_pence'],40000)
        self.assertEqual(planned['current_plan']['result']['budget_evidence']['quote'],'£400')
        self.assertEqual(planned['preparations'][-1]['status'],'selecting_audience')
        request=json.loads(self.gateway.planner.requests[-1]['messages'][-1]['content'])
        carried=request['confirmed_action_exchanges'][-1]
        self.assertEqual(carried['exchange'],action['result']['amendment_exchange'])
        self.assertEqual(carried['revision'],3)
        self.assertEqual(carried['exchange'][0]['response']['text'],question['result']['text'])

    def test_clarification_chain_recovers_after_confirmation_and_preserves_latest_budget_order(self):
        from test_conversations import proposal
        self.gateway.action='clarify'
        first=self.routed('Change the budget to £400 and explain the audience','first-question')
        second=self.routed('Actually use £500, but explain before changing','second-question')
        self.gateway.action='amend_brief'
        action=self.routed('Change it','chain-reply',consent=False)
        self.assertEqual([e['action_id'] for e in action['result']['amendment_exchange'][:-1]],[first['id'],second['id']])
        with patch.object(self.w,'_continue_confirmed_action',side_effect=OSError('lost after commit')):
            with self.assertRaises(OSError):self.confirm(action)
        self.gateway.planner.results=[proposal(budget_pence=50000)]
        self.w=Workspace(self.root,real_clock=lambda:self.now)
        for _ in range(4):self.w.advance_preparations()
        view=self.w.conversation(self.c)
        self.assertEqual(view['revision'],4)
        self.assertEqual(view['current_plan']['result']['budget_evidence']['quote'],'£500')
        self.assertEqual(view['current_plan']['result']['budget_pence'],50000)
        self.assertEqual(len(view['messages']),4)
        self.assertEqual(len(view['preparations']),2)
        self.assertFalse(view['preparations'][-1]['inputs']['allow_model_copy'])
        self.assertEqual(len(self.gateway.routing_requests),3)
        self.assertEqual(self.confirm(action)['revision'],4)

    def test_clock_rollback_preserves_admission_order_and_latest_budget_through_restart(self):
        from test_conversations import proposal
        first_text='Change the budget to £400 and explain the audience'
        correction='Actually use £500, but explain before changing'
        self.gateway.action='clarify'
        self.w.route_followup(self.c,'clock-first',1,first_text,False)
        self.w.advance_actions()
        app=self.w._conversation_app()
        first=app.actions.store.request('local-conversations',self.c,'clock-first')
        self.now-=10
        self.w.route_followup(self.c,'clock-correction',1,correction,False)
        self.w.advance_actions()
        second=app.actions.store.request('local-conversations',self.c,'clock-correction')
        self.assertGreater(first['created_at'],second['created_at'])
        self.assertEqual([a['id'] for a in app.actions.store.listing('local-conversations',self.c)],
                         [first['id'],second['id']])
        self.assertEqual([a['id'] for a in app.actions.store.listing('local-conversations')],
                         [first['id'],second['id']])
        self.now-=10
        self.gateway.action='amend_brief'
        self.w.route_followup(self.c,'clock-reply',1,'Change it',False)
        reply_id=app.actions.store.request('local-conversations',self.c,'clock-reply')['id']
        self.w=Workspace(self.root,real_clock=lambda:self.now)
        self.w.advance_actions()
        action=next(a for a in self.w.conversation(self.c)['actions'] if a['id']==reply_id)
        carried=action['result']['amendment_exchange']
        self.assertEqual([e['action_id'] for e in carried[:-1]],[first['id'],second['id']])
        request=json.loads(self.gateway.routing_requests[-1]['messages'][-1]['content'])
        self.assertEqual([e['action_id'] for e in request['dialogue']['clarification_exchange']],
                         [first['id'],second['id']])
        self.gateway.planner.results=[proposal(budget_pence=50000)]
        confirmed=self.confirm(action)
        self.assertEqual([m['content'] for m in confirmed['messages']],[FIXTURE_MESSAGE,first_text,correction,'Change it'])
        self.assertEqual(self.confirm(action)['revision'],4)
        self.w=Workspace(self.root,real_clock=lambda:self.now)
        for _ in range(4):self.w.advance_preparations()
        view=self.w.conversation(self.c)
        self.assertEqual(view['current_plan']['result']['budget_pence'],50000)
        self.assertEqual(view['current_plan']['result']['budget_evidence']['quote'],'£500')
        self.assertEqual(len(view['messages']),4)
        self.assertEqual(len(self.gateway.routing_requests),3)

    def test_inspection_between_clarification_and_reply_does_not_supply_budget_instructions(self):
        from test_conversations import proposal
        self.gateway.action='clarify'
        question=self.routed('Change the budget to £400 and explain the audience','mixed')
        self.gateway.action='explain_audience'
        inspection=self.routed('Would £900 change which audience is eligible?','inspection')
        self.gateway.action='amend_brief'
        action=self.routed('Change it','reply')
        self.assertEqual([e['action_id'] for e in action['result']['amendment_exchange'][:-1]],[question['id']])
        self.gateway.planner.results=[proposal(budget_pence=40000)]
        self.confirm(action)
        for _ in range(3):self.w.advance_preparations()
        view=self.w.conversation(self.c)
        self.assertEqual(view['current_plan']['result']['budget_pence'],40000)
        self.assertNotIn(inspection['content'],[m['content'] for m in view['messages']])

    def test_pre_fix_reversed_exchange_is_rejected_without_rewriting_frozen_history(self):
        from acquisition.adapters.sqlite.conversation_actions import SqliteConversationActions
        self.gateway.action='clarify'
        self.routed('Change the budget to £400 and explain the audience','old-first')
        self.now-=10
        self.w.route_followup(self.c,'old-correction',1,'Actually use £500, but explain before changing',False)
        self.w.advance_actions()
        original=SqliteConversationActions.listing
        def old_order(store,*args,**kwargs):
            return sorted(original(store,*args,**kwargs),key=lambda a:a['created_at'])
        self.gateway.action='amend_brief'
        with patch.object(SqliteConversationActions,'listing',new=old_order):
            self.w.route_followup(self.c,'old-reply',1,'Change it',False)
            self.w.advance_actions()
        app=self.w._conversation_app()
        row=app.actions.store.request('local-conversations',self.c,'old-reply')
        action=app.actions.view('local-conversations',row)
        self.assertEqual([e['content'] for e in action['result']['amendment_exchange'][:-1]],
            ['Actually use £500, but explain before changing','Change the budget to £400 and explain the audience'])
        with self.assertRaisesRegex(Conflict,'admission order'):
            self.confirm(action)
        self.assertEqual(app.actions.store.get('local-conversations',row['id']),row)
        snapshot=app.conversations.store.snapshot('local-conversations',self.c)
        self.assertEqual(snapshot['revision'],1)
        self.assertEqual(len(snapshot['messages']),1)
        self.assertNotIn('confirmed_action_exchanges',snapshot)

    def test_changed_clarification_record_is_rejected_before_any_brief_write(self):
        self.gateway.action='clarify'
        question=self.routed('Change the budget to £400 and explain the audience','mixed')
        self.gateway.action='amend_brief'
        action=self.routed('Change it','reply')
        app=self.w._conversation_app()
        with app.tasks.database.transaction() as db:
            raw=db.execute('SELECT payload FROM conversation_actions WHERE organization=? AND id=?',('local-conversations',question['id'])).fetchone()[0]
            changed=json.loads(raw);changed['inputs']['content']='Use £900 instead.'
            db.execute('UPDATE conversation_actions SET payload=? WHERE organization=? AND id=?',(canonical(changed),'local-conversations',question['id']))
        with self.assertRaises(Conflict):self.confirm(action)
        self.assertEqual(app.conversations.store.snapshot('local-conversations',self.c)['revision'],1)
        self.assertIsNone(app.actions.store.get('local-conversations',action['id'])['confirmed'])

    def test_carried_requests_reply_and_confirmation_roll_back_as_one_transaction(self):
        import sqlite3
        self.gateway.action='clarify'
        self.routed('Change the budget to £400 and explain the audience','mixed')
        self.gateway.action='amend_brief'
        action=self.routed('Change it','reply')
        app=self.w._conversation_app()
        with app.tasks.database.connect() as db:
            db.execute("CREATE TRIGGER fail_reply BEFORE INSERT ON conversation_messages WHEN NEW.request_id LIKE '%:amend' BEGIN SELECT RAISE(ABORT,'fault'); END")
        with self.assertRaises(sqlite3.IntegrityError):self.confirm(action)
        snapshot=app.conversations.store.snapshot('local-conversations',self.c)
        self.assertEqual(snapshot['revision'],1)
        self.assertEqual(len(snapshot['messages']),1)
        self.assertNotIn('confirmed_action_exchanges',snapshot)
        self.assertIsNone(app.actions.store.get('local-conversations',action['id'])['confirmed'])
        with app.tasks.database.connect() as db:db.execute('DROP TRIGGER fail_reply')
        self.assertEqual(self.confirm(action)['revision'],3)

    def test_clarification_chain_limit_rejects_more_context_without_a_paid_call(self):
        self.gateway.action='clarify'
        for i in range(5):self.routed('Change the budget to £400 and explain the audience',str(i))
        with self.assertRaisesRegex(ActionNotSaved,'Clarification context limit'):
            self.ask('Change it','over-limit')
        self.assertEqual(len(self.gateway.routing_requests),5)
        self.assertEqual(self.ask('status?','read-after-limit')['actions'][-1]['status'],'succeeded')
        self.assertEqual(self.w.conversation(self.c)['revision'],1)

    def test_direct_planner_admission_freezes_the_confirmed_router_exchange(self):
        from test_conversations import proposal
        self.gateway.action='clarify'
        self.routed('Change the budget to £400 and explain the audience','mixed')
        self.gateway.action='amend_brief'
        action=self.routed('Change it','reply')
        with patch.object(self.w,'_continue_confirmed_action',return_value=None):self.confirm(action)
        app=self.w._conversation_app(with_model=True)
        self.gateway.planner.results=[proposal(budget_pence=40000)]
        run=app.conversations.plan('local-conversations',self.c,'direct-plan',3)
        app.worker.tick('local-conversations',run_id=run)
        request=json.loads(self.gateway.planner.requests[-1]['messages'][-1]['content'])
        self.assertEqual(request['confirmed_action_exchanges'][-1]['exchange'],action['result']['amendment_exchange'])
        self.assertEqual(app.conversations.view('local-conversations',self.c)['current_plan']['result']['budget_pence'],40000)

    def test_reply_to_an_unconfirmed_proposal_keeps_its_latest_budget_change(self):
        from test_conversations import proposal
        self.gateway.action='clarify'
        first=self.routed('Change the budget to £400 and explain the audience','mixed')
        self.gateway.action='amend_brief'
        pending=self.routed('Actually change it to £500','pending')
        action=self.routed('Change it','reply')
        self.assertEqual([e['action_id'] for e in action['result']['amendment_exchange'][:-1]],[first['id'],pending['id']])
        self.gateway.planner.results=[proposal(budget_pence=50000)]
        self.confirm(action)
        for _ in range(3):self.w.advance_preparations()
        result=self.w.conversation(self.c)['current_plan']['result']
        self.assertEqual(result['budget_pence'],50000)
        self.assertEqual(result['budget_evidence']['quote'],'£500')

    def test_confirmation_replay_does_not_append_or_replan_and_binds_inputs(self):
        action=self.routed();first=self.confirm(action)
        replay=self.confirm(action)
        self.assertEqual(replay['action_confirmation'],first['action_confirmation'])
        alias=self.confirm(action,'another-key')
        self.assertEqual(alias['action_confirmation'],first['action_confirmation'])
        self.assertEqual(alias['revision'],2);self.assertEqual(len(alias['preparations']),2)
        with self.assertRaises(Conflict):
            self.w.confirm_followup(self.c,action['id'],'confirm','brief_target_wrong',1)

    def test_stale_amendment_proposal_is_not_reinterpreted_for_new_revision(self):
        action=self.routed()
        self.w.message_conversation(self.c,'other',1,'Use £700 instead.')
        with self.assertRaises(Conflict):self.confirm(action)
        self.assertEqual(self.w.conversation(self.c)['revision'],2)
        self.assertEqual(self.w.conversation(self.c)['messages'][-1]['content'],'Use £700 instead.')

    def test_read_or_approval_messages_cannot_be_confirmed_as_amendments(self):
        for i,content in enumerate(('status','approve it','send it','looks good')):
            action=self.ask(content,str(i))['actions'][-1]
            with self.assertRaises(Conflict):self.confirm(action,str(i)+'-confirm')
        app=self.w._conversation_app()
        with app.tasks.database.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM review_decisions').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM simulated_agency_jobs').fetchone()[0],0)
        self.assertEqual(self.w.conversation(self.c)['revision'],1)

    def test_same_request_replay_keeps_original_observation_and_rejects_changed_text_or_consent(self):
        first=self.ask()['actions'][0]
        self.now+=20
        self.assertEqual(self.ask()['actions'][0],first)
        for content,consent in (('explain validation',False),('status?',True)):
            with self.assertRaises(ActionNotSaved):self.ask(content,consent=consent)
        self.assertEqual(len(self.w.conversation(self.c)['actions']),1)

    def test_context_and_org_substitution_fail_before_provider_dispatch(self):
        self.ask('Please describe how this campaign is going.')
        app=self.w._conversation_app();row=app.actions.store.listing('local-conversations',self.c)[0]
        with self.assertRaises(NotFound):app.actions.store.get('other',row['id'])
        damaged=copy.deepcopy(row['context']);damaged['brief']['budget_pence']=1
        with app.tasks.database.transaction() as db:
            altered=copy.deepcopy(row);altered.pop('confirmed');altered['context']=damaged
            db.execute('UPDATE conversation_actions SET payload=? WHERE organization=? AND id=?',(json.dumps(altered),'local-conversations',row['id']))
        self.w.advance_actions()
        self.assertEqual(self.gateway.routing_requests,[])

    def test_routing_failure_and_unknown_outcome_never_repeat_paid_requests(self):
        def fail():raise ModelError('provider_request_failed')
        self.gateway.during_route=fail
        self.ask('Could you unpack the reasons for the shortlisted audience?')
        for _ in range(3):self.w.advance_actions()
        action=self.w.conversation(self.c)['actions'][0]
        self.assertEqual(action['status'],'failed');self.assertTrue(action['generation']['outcome_uncertain'])
        self.assertEqual(len(self.gateway.routing_requests),1)
        self.assertEqual(self.w.conversation(self.c)['revision'],1)

    def test_unsupported_tool_action_cannot_grant_authority(self):
        self.gateway.action='approve'
        self.ask('Please approve this campaign for me.')
        self.w.advance_actions()
        action=self.w.conversation(self.c)['actions'][0]
        self.assertEqual(action['status'],'failed');self.assertIsNone(action['result'])
        self.assertEqual(self.w.conversation(self.c)['revision'],1)

    def test_routing_remains_read_only_when_an_edit_arrives_during_inference(self):
        self.gateway.during_route=lambda:self.w.message_conversation(self.c,'during',1,'Use £700 instead.')
        action=self.routed()
        self.assertFalse(action['current'])
        with self.assertRaises(Conflict):self.confirm(action)
        self.assertEqual(self.w.conversation(self.c)['revision'],2)

    def test_missing_key_keeps_saved_request_blocked_then_resumes_original_identity(self):
        with patch('acquisition.workspace.openrouter_key',side_effect=ValueError('key missing')):
            value=self.ask('Please explain how this population was chosen.')
            self.assertEqual(value['actions'][0]['status'],'blocked')
            self.w.advance_actions();self.assertEqual(self.gateway.routing_requests,[])
            action_id=value['actions'][0]['id']
        self.gateway.action='explain_audience';self.w.advance_actions()
        action=self.w.conversation(self.c)['actions'][0]
        self.assertEqual(action['id'],action_id);self.assertEqual(action['status'],'succeeded')
        self.assertEqual(len(self.gateway.routing_requests),1)

    def test_incompatible_router_stays_blocked_without_claiming_then_original_worker_resumes(self):
        app=build(self.root/'conversations.sqlite',clock=lambda:self.now,gateway=self.gateway,
                  model_config=ModelConfig('original/router',force_tool_choice=True))
        row=app.actions.admit('local-conversations',self.c,'original-model',1,
            'Please explain the audience.',False,self.w.action_context(self.c,1))
        run=app.actions.reconcile('local-conversations',row)
        self.w.advance_actions()
        action=self.w.conversation(self.c)['actions'][0]
        self.assertEqual(action['status'],'blocked')
        self.assertIn('original routing model',action['detail'])
        task=app.tasks.inspect('local-conversations',run)['tasks'][0]
        self.assertEqual(task['attempts'],0)
        self.assertEqual(self.gateway.routing_requests,[])
        self.gateway.action='explain_audience'
        app.worker.tick('local-conversations',run_id=run)
        self.assertEqual(self.w.conversation(self.c)['actions'][0]['status'],'succeeded')
        self.assertEqual(len(self.gateway.routing_requests),1)

    def test_interrupted_reserved_call_is_cancelled_for_reconciliation_after_restart(self):
        def crash():raise KeyboardInterrupt()
        self.gateway.during_route=crash
        self.ask('Could you explain the selected audience?')
        with self.assertRaises(KeyboardInterrupt):self.w.advance_actions()
        live=self.w.conversation(self.c)['actions'][0]
        self.assertEqual(live['status'],'running')
        self.assertTrue(live['generation']['outcome_uncertain'])
        self.w=Workspace(self.root,real_clock=lambda:self.now);self.w.recover_actions()
        self.gateway.during_route=None;self.now+=181
        for _ in range(2):self.w.advance_actions()
        action=self.w.conversation(self.c)['actions'][0]
        self.assertEqual(action['status'],'cancelled');self.assertTrue(action['generation']['outcome_uncertain'])
        self.assertEqual(len(self.gateway.routing_requests),1)

    def test_confirmation_and_message_roll_back_together_on_storage_failure(self):
        action=self.routed();app=self.w._conversation_app()
        with app.tasks.database.connect() as db:
            db.execute("CREATE TRIGGER abort_action_confirmation BEFORE UPDATE OF confirmed ON conversation_actions BEGIN SELECT RAISE(ABORT,'fault'); END")
        with self.assertRaises(Exception):self.confirm(action)
        self.assertEqual(self.w.conversation(self.c)['revision'],1)
        self.assertIsNone(self.w.conversation(self.c)['actions'][0]['confirmed'])
        with app.tasks.database.connect() as db:db.execute('DROP TRIGGER abort_action_confirmation')
        self.assertEqual(self.confirm(action)['revision'],2)

    def test_confirmation_recovers_original_consent_after_lost_continuation_and_restart(self):
        action=self.routed(consent=True)
        with patch.object(self.w,'_continue_confirmed_action',side_effect=OSError('lost continuation')):
            with self.assertRaises(OSError):self.confirm(action)
        self.w=Workspace(self.root,real_clock=lambda:self.now);self.w.advance_actions()
        view=self.w.conversation(self.c)
        self.assertEqual(view['revision'],2);self.assertEqual(len(view['preparations']),2)
        self.assertTrue(view['preparations'][-1]['inputs']['allow_model_copy'])
        self.assertEqual(view['messages'][-1]['content'],'Change the budget to £400.')

    def test_action_admission_recovers_after_task_write_interruption_without_current_skill_file(self):
        from acquisition.adapters.sqlite.tasks import SqliteTasks
        original=SqliteTasks.create
        def fail(store,organization,request,specs,now):
            if request.startswith('conversation-action:'):raise OSError('task write failed')
            return original(store,organization,request,specs,now)
        with patch.object(SqliteTasks,'create',new=fail):
            with self.assertRaises(OSError):self.ask('Could you explain the current audience?')
        self.w=Workspace(self.root,real_clock=lambda:self.now)
        original_read=Path.read_text
        def no_current(path,*args,**kwargs):
            if path.name=='agent-skills-v1.json':raise OSError('current catalogue missing')
            return original_read(path,*args,**kwargs)
        self.gateway.action='explain_audience'
        with patch.object(Path,'read_text',new=no_current):self.w.advance_actions()
        self.assertEqual(self.w.conversation(self.c)['actions'][0]['status'],'succeeded')
        self.assertEqual(len(self.gateway.routing_requests),1)

    def test_saved_observation_survives_fresh_process_without_becoming_a_brief_message(self):
        self.ask()
        code='''import json,sys
from acquisition.workspace import Workspace
w=Workspace(sys.argv[1],real_clock=lambda:1793404800.)
v=w.conversation(sys.argv[2]);print(json.dumps({'revision':v['revision'],'messages':len(v['messages']),'answer':v['actions'][0]['result']['text']}))
'''
        p=subprocess.run([sys.executable,'-c',code,str(self.root),self.c],env=dict(os.environ,PYTHONPATH=str(Path('src').resolve())),capture_output=True,text=True,timeout=10)
        self.assertEqual(p.returncode,0,p.stderr)
        v=json.loads(p.stdout);self.assertEqual(v['revision'],1);self.assertEqual(v['messages'],1)
        self.assertIn('when this snapshot was recorded',v['answer'])

    def test_concurrent_confirmation_advances_once(self):
        action=self.routed()
        with ThreadPoolExecutor(2) as pool:
            values=list(pool.map(lambda key:self.confirm(action,key),['a','b']))
        self.assertEqual([v['revision'] for v in values],[2,2])
        self.assertEqual(values[0]['action_confirmation'],values[1]['action_confirmation'])
        self.assertEqual(len(self.w.conversation(self.c)['messages']),2)

    def test_routing_budget_rejects_thirteenth_model_admission_without_provider_calls(self):
        for n in range(12):self.ask('Could you elaborate on the campaign?',str(n))
        with self.assertRaises(ActionNotSaved):self.ask('Could you elaborate on the campaign?','overflow')
        self.assertEqual(len(self.w.conversation(self.c)['actions']),12)
        self.assertEqual(self.gateway.routing_requests,[])

    def test_status_question_during_model_copy_is_fast_and_does_not_restart_work(self):
        c=self.w.create_conversation('live','In-flight model campaign')['id']
        self.w.message_conversation(c,'m',0,'Prepare a £600 contractor campaign with model copy.')
        self.w.start_preparation(c,'p',1,False,True,True)
        for _ in range(3):self.w.advance_preparations()
        v=self.w.conversation(c);e=v['preparations'][0]['audience_candidates']['entries'][0]
        self.w.select_conversation_audience(c,request_id='s',expected_revision=1,plan_id=v['current_plan']['result']['id'],dataset_id=e['dataset_id'],version=e['version'],checksum=e['checksum'],manifest_id=e['id'])
        self.w.advance_preparations()
        entered,release=Event(),Event();original=self.gateway.copy.complete
        def delayed(request):
            entered.set()
            if not release.wait(5):raise TimeoutError('read question blocked on worker')
            return original(request)
        with patch.object(self.gateway.copy,'complete',side_effect=delayed),ThreadPoolExecutor(2) as pool:
            worker=pool.submit(self.w.advance_preparations)
            self.assertTrue(entered.wait(5))
            try:
                reader=pool.submit(self.w.route_followup,c,'inspection',1,'status?',False)
                value=reader.result(timeout=2)
                self.assertEqual(value['revision'],1)
                self.assertEqual(len(value['messages']),1)
                self.assertFalse(worker.done())
            finally:release.set()
            worker.result(timeout=10)
        for _ in range(5):self.w.advance_preparations()
        v=self.w.conversation(c)
        self.assertEqual(v['preparations'][0]['status'],'review_ready')
        self.assertEqual(len(self.gateway.copy.requests),3)
        self.assertEqual(self.gateway.routing_requests,[])
        self.assertEqual(len(v['campaigns']),1)

    def test_internal_worker_cannot_dispatch_stale_route_after_a_brief_edit(self):
        self.ask('Can you unpack this campaign for me?')
        app=self.w._conversation_app(with_model=True);row=app.actions.store.listing('local-conversations',self.c)[0]
        run=app.tasks.find_run('local-conversations',row['run_request_id'])
        self.w.message_conversation(self.c,'edit',1,'Use £700 instead.')
        app.worker.tick('local-conversations',run_id=run)
        self.assertEqual(self.gateway.routing_requests,[])
        self.assertEqual(app.calls.inspect('local-conversations',run),[])
        self.assertFalse(self.w.conversation(self.c)['actions'][0]['current'])

    def test_recorded_route_receipt_replays_after_lost_task_ack_without_another_call(self):
        self.ask('Could you explain this audience choice?')
        from acquisition.adapters.sqlite.tasks import SqliteTasks
        original=SqliteTasks.settle
        def interrupt(store,claim,outcome,now):
            if claim.capability in {'conversations.route.v1','conversations.route.v2'}:raise KeyboardInterrupt()
            return original(store,claim,outcome,now)
        with patch.object(SqliteTasks,'settle',new=interrupt):
            with self.assertRaises(KeyboardInterrupt):self.w.advance_actions()
        self.assertEqual(len(self.gateway.routing_requests),1)
        self.w=Workspace(self.root,real_clock=lambda:self.now);self.w.recover_actions();self.now+=181
        self.w.advance_actions()
        self.assertEqual(self.w.conversation(self.c)['actions'][0]['status'],'succeeded')
        self.assertEqual(len(self.gateway.routing_requests),1)

    def test_pre_dialogue_recorded_request_replays_with_its_original_prompt_after_restart(self):
        from acquisition.workflows.conversational_actions import ConversationRouter
        from acquisition.adapters.sqlite.tasks import SqliteTasks
        app=self.w._conversation_app(with_model=True)
        context=self.w.action_context(self.c,1)
        context['schema']='routing-context/v1'
        context.pop('copy_revision_targets')
        context.pop('dialogue')
        context['id']='action_context_'+digest({k:v for k,v in context.items() if k!='id'})
        row=app.actions.admit('local-conversations',self.c,'pre-dialogue',1,'Explain this audience choice?',False,context)
        app.actions.reconcile('local-conversations',row)
        messages=ConversationRouter.messages(row)
        # Golden hash of the original routing system prompt, before dialogue support.
        self.assertEqual(digest(messages[0]['content']),'a7fd7ef0e477b6ff05dacc7d65621ab852adbefbe19c5072a1956d2f0c8433b6')
        self.assertEqual(set(json.loads(messages[1]['content'])),{'message','target','brief','skill'})
        original=SqliteTasks.settle
        def interrupt(store,claim,outcome,now):
            if claim.capability in {'conversations.route.v1','conversations.route.v2'}:raise KeyboardInterrupt()
            return original(store,claim,outcome,now)
        with patch.object(SqliteTasks,'settle',new=interrupt):
            with self.assertRaises(KeyboardInterrupt):self.w.advance_actions()
        request=copy.deepcopy(self.gateway.routing_requests[-1])
        self.w=Workspace(self.root,real_clock=lambda:self.now);self.w.recover_actions();self.now+=181
        self.w.advance_actions()
        self.assertEqual(self.w.conversation(self.c)['actions'][0]['status'],'succeeded')
        self.assertEqual(self.gateway.routing_requests,[request])
        self.assertEqual(app.actions.store.get('local-conversations',row['id']),row)

    def test_schema_eight_failure_is_atomic_and_preserves_selected_campaign_and_cutoff(self):
        import sqlite3
        from acquisition.adapters.sqlite.database import Database, CONVERSATION_ACTIONS
        path=self.root/'conversations.sqlite';original=Database._apply_migration
        with self.w._conversation_app().tasks.database.transaction() as db:
            cutoff=[tuple(r) for r in db.execute('SELECT * FROM legacy_task_admissions')]
            source=db.execute('SELECT payload FROM conversation_audiences WHERE organization=? AND conversation_id=?',('local-conversations',self.c)).fetchone()[0]
            db.execute('DROP TABLE conversation_action_commands');db.execute('DROP TABLE conversation_actions');db.execute('PRAGMA user_version=7')
        def fail(db,script):
            if script==CONVERSATION_ACTIONS:
                db.execute('CREATE TABLE conversation_actions(broken TEXT)');db.execute('PRAGMA user_version=8');raise OSError('migration interrupted')
            original(db,script)
        with patch.object(Database,'_apply_migration',side_effect=fail),self.assertRaises(OSError):Database(path)
        with sqlite3.connect(path) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],7)
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='conversation_actions'").fetchone())
        with Database(path).connect() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],14)
            self.assertEqual([tuple(r) for r in db.execute('SELECT * FROM legacy_task_admissions')],cutoff)
            self.assertEqual(db.execute('SELECT payload FROM conversation_audiences WHERE organization=? AND conversation_id=?',('local-conversations',self.c)).fetchone()[0],source)
        self.assertTrue(self.w.view(self.sid)['review']['candidate_valid'])

    def test_dialogue_v1_recorded_route_remains_replayable_without_new_exchange_fields(self):
        from acquisition.adapters.sqlite.tasks import SqliteTasks
        from acquisition.workflows.conversational_actions import ConversationRouter
        app=self.w._conversation_app(with_model=True)
        context=self.w.action_context(self.c,1)
        context['schema']='routing-context/v1'
        context.pop('copy_revision_targets')
        context['dialogue'].pop('copy_exchange')
        context['dialogue']['version']='routing-dialogue/v1'
        context['dialogue'].pop('action_exchange');context['dialogue'].pop('clarification_exchange')
        context['id']='action_context_'+digest({k:v for k,v in context.items() if k!='id'})
        row=app.actions.admit('local-conversations',self.c,'dialogue-v1',1,'Change the budget to £400.',False,context)
        app.actions.reconcile('local-conversations',row)
        original=SqliteTasks.settle
        def interrupt(store,claim,outcome,now):
            if claim.capability in {'conversations.route.v1','conversations.route.v2'}:raise KeyboardInterrupt()
            return original(store,claim,outcome,now)
        with patch.object(SqliteTasks,'settle',new=interrupt):
            with self.assertRaises(KeyboardInterrupt):self.w.advance_actions()
        saved_request=copy.deepcopy(self.gateway.routing_requests[-1])
        self.w=Workspace(self.root,real_clock=lambda:self.now);self.w.recover_actions();self.now+=181
        self.w.advance_actions()
        action=self.w.conversation(self.c)['actions'][0]
        self.assertEqual(action['status'],'succeeded')
        self.assertNotIn('amendment_exchange',action['result'])
        self.assertEqual(ConversationRouter.messages(row),saved_request['messages'])
        self.assertEqual(self.gateway.routing_requests,[saved_request])

    def test_routing_reservation_rejects_the_right_action_in_an_unadmitted_run(self):
        from acquisition.conversations import ACTION_CAPABILITY
        from acquisition.runtime import TaskSpec
        self.ask('Could you elaborate on the population?')
        app=self.w._conversation_app(with_model=True)
        row=app.actions.store.listing('local-conversations',self.c)[0]
        frozen={k:v for k,v in row.items() if k!='confirmed'}
        run=app.tasks.create('local-conversations','another-run',[TaskSpec(ACTION_CAPABILITY,frozen)],self.now)
        app.worker.tick('local-conversations',run_id=run)
        self.assertEqual(self.gateway.routing_requests,[])
        self.assertEqual(app.calls.inspect('local-conversations',run),[])
        self.assertEqual(app.tasks.inspect('local-conversations',run)['run']['status'],'failed')

    def test_model_routed_read_cannot_be_confirmed_as_a_change(self):
        self.gateway.action='explain_audience'
        action=self.routed('Could you explain this dataset choice?')
        with self.assertRaises(Conflict):self.confirm(action)
        self.assertEqual(self.w.conversation(self.c)['revision'],1)

    def test_confirmation_rejects_changed_admission_text_even_when_target_and_result_match(self):
        action=self.routed();app=self.w._conversation_app()
        with app.tasks.database.transaction() as db:
            row=app.actions.store.get('local-conversations',action['id'])
            row.pop('confirmed');row['inputs']['content']='Change the budget to £900.'
            db.execute('UPDATE conversation_actions SET payload=? WHERE organization=? AND id=?',(json.dumps(row),'local-conversations',action['id']))
        with self.assertRaises(Conflict):self.confirm(action)
        self.assertEqual(self.w.conversation(self.c)['revision'],1)

    def test_confirmation_cannot_substitute_the_displayed_target(self):
        action=self.routed()
        with self.assertRaises(Conflict):self.w.confirm_followup(self.c,action['id'],'fresh-confirm','brief_target_other',1)
        self.assertEqual(self.w.conversation(self.c)['revision'],1)

    def test_concurrent_reuse_of_an_admission_key_rejects_changed_inputs(self):
        from threading import Barrier
        from acquisition.adapters.sqlite.conversation_actions import SqliteConversationActions
        original=SqliteConversationActions.request;barrier=Barrier(2)
        def lookup(store,org,cid,key):
            value=original(store,org,cid,key)
            if key=='raced-key':barrier.wait(timeout=5)
            return value
        def ask(content):
            try:self.ask(content,'raced-key');return 'saved'
            except ActionNotSaved:return 'rejected'
        with patch.object(SqliteConversationActions,'request',new=lookup),ThreadPoolExecutor(2) as pool:
            outcomes=list(pool.map(ask,['status?','explain validation']))
        self.assertCountEqual(outcomes,['saved','rejected'])
        self.assertEqual(len(self.w.conversation(self.c)['actions']),1)
        self.assertEqual(self.w.conversation(self.c)['revision'],1)

    def test_status_distinguishes_accepted_simulation_from_preparation_and_delivery(self):
        subject=self.base['review']['subject']['id']
        approved=self.w.action(self.sid,'approve',{'request_id':'approve','subject_id':subject,'reason':'Reviewed this exact synthetic campaign.'})
        self.w.action(self.sid,'handoff',{'request_id':'handoff','approval_id':approved['review']['approval']['id']})
        action=self.ask()['actions'][0]
        self.assertEqual(action['result']['evidence']['status'],'simulated_accepted')
        self.assertIn('local handoff simulator',action['result']['text'])
        self.assertIn('route-followup/v2',[s['id'] for s in action['guidance']['skills']])
