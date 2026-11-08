"""Absolute budget replies preserve native identity, scope and request replay."""
import copy
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from acquisition.adapters.sqlite.conversations import SqliteConversations

from acquisition.contracts import Conflict, canonical
from acquisition.conversations import BUDGET_POLICY, budget_clarification, budget_response, validate_result
from acquisition.workspace import Workspace
import test_conversations as conversations
import test_preparations as preparations


class BudgetRuleTests(unittest.TestCase):
    def frozen(self, *contents):
        return {'conversation_id': 'conversation_budget', 'request_id': 'plan', 'revision': len(contents),
                'knowledge_id': 'knowledge_budget', 'budget_policy': BUDGET_POLICY,
                'messages': [{'id': 'm' + str(i), 'revision': i + 1, 'content': c} for i, c in enumerate(contents)]}

    def test_ambiguous_relative_and_invalid_totals_need_confirmation_not_arithmetic(self):
        for text in ('Use £437 or £683.', 'Reduce that budget by £37.', 'Halve the budget.', 'Budget £437-683.',
                     'Use 400 instead.', 'Budget £600k.', 'Budget $400.', 'Budget £0.', 'Budget £10,001.'):
            with self.subTest(text=text):
                frozen = self.frozen('A UK contractor postal experiment with £437.', text)
                question = budget_response(frozen)
                self.assertEqual(question['outcome'], 'clarification')
                self.assertIsNone(question['budget_pence'])
                self.assertIn('budget', question['question'])
                with self.assertRaises(ValueError):
                    validate_result(conversations.proposal(budget_pence=40000), frozen, 'one')
                result = validate_result(question, frozen, 'one')
                self.assertEqual(result['budget_clarification']['message_id'], 'm1')
                self.assertEqual(result['approval'], 'not_granted')
        for total in ('£0.01', 'GBP 400', '£10,000'):
            self.assertIsNone(budget_response(self.frozen('Use £437 or £683.', 'Use ' + total + ' in total.')))
        frozen = self.frozen('Use £437 or £683.', 'Use £400 in total.', 'Keep the tone concise.')
        self.assertIsNone(budget_response(frozen))
        self.assertEqual(validate_result(conversations.proposal(budget_pence=40000), frozen, 'one')['budget_evidence']['message_id'], 'm1')

    def test_non_total_amounts_cannot_supply_a_campaign_total(self):
        references = ('Budget £400 per month.', 'The monthly budget is GBP 400.', 'Use £400 per recipient.',
                      'GBP 400 per audience.', 'Budget £400 a week.', 'Budget £400/month.',
                      'The budget is £400 daily.', '£400 per quarter.', '£400 is not the total budget.',
                      '£400 is not my campaign budget.', '£400 is not an absolute total.',
                      '£400 is not the final budget.', '£400 is a non-total amount.', '£400 is only the deposit.',
                      '£400 is half of the total budget.', 'The unit cost is £400.',
                      '£400 is the unit price.', 'Do not treat £400 as the total budget.')
        for reference in references:
            with self.subTest(reference=reference):
                frozen = self.frozen(reference)
                question = budget_response(frozen)
                self.assertIsNotNone(question)
                self.assertIsNone(question['budget_pence'])
                self.assertEqual(validate_result(question, frozen, 'one')['budget_clarification']['reason'], 'non_total')
                with self.assertRaises(ValueError):
                    validate_result(conversations.proposal(budget_pence=40000), frozen, 'one')
                corrected = self.frozen(reference, 'Use GBP 400 as the total for the whole campaign.')
                self.assertIsNone(budget_response(corrected))
                self.assertEqual(validate_result(conversations.proposal(budget_pence=40000), corrected, 'one')['budget_evidence']['message_id'], 'm1')
        for qualification in ('That amount is per month.', 'That is not a total budget.', 'Per recipient.'):
            with self.subTest(qualification=qualification):
                frozen = self.frozen('Use £400.', qualification)
                self.assertIsNotNone(budget_response(frozen))
        for total in ('Use £400 as the total campaign budget.', 'Use £400 total, not per month.',
                      'Use £400 as the whole campaign cap.', 'Use £400 total, not a monthly budget.',
                      'Budget £400. Please provide monthly reports.',
                      'Use £400 total. The unit cost is 85p.'):
            with self.subTest(total=total):
                self.assertIsNone(budget_response(self.frozen(total)))
        self.assertIsNone(budget_response(self.frozen('Use £400 total.', 'Please include monthly reports.')))

    def test_grouped_recipient_quantities_still_require_a_total(self):
        for rate in ('£400 per 1,000 recipients', 'GBP 400 per 10,000 businesses',
                     '£400 per 1,000,000 contacts', '£400 per 1000 recipients', '£400/1,000 recipients'):
            with self.subTest(rate=rate):
                frozen = self.frozen('Prepare a contractor campaign with ' + rate + '.')
                question = budget_response(frozen)
                self.assertIsNotNone(question)
                self.assertEqual(validate_result(question, frozen, 'one')['budget_clarification']['reason'], 'non_total')
                with self.assertRaises(ValueError):
                    validate_result(conversations.proposal(budget_pence=40000), frozen, 'one')
        self.assertIsNotNone(budget_response(self.frozen('Use £400.', 'That amount is per 1,000 recipients.')))

    def test_delivery_and_reporting_rates_do_not_qualify_the_budget(self):
        for request in ('Use £400 total. Send one letter per recipient.',
                        'Use £400 total and send one letter per recipient.',
                        'Budget £400; provide one report per week.',
                        'Use £400 for the whole campaign, with one mailing per business.',
                        'Use £400 total. The response target is one per 1,000 recipients.',
                        'Use £400 total. The reporting rate is per week.'):
            with self.subTest(request=request):
                frozen = self.frozen(request)
                self.assertIsNone(budget_response(frozen))
                self.assertEqual(validate_result(conversations.proposal(budget_pence=40000), frozen, 'one')['budget_pence'], 40000)
        self.assertIsNone(budget_response(self.frozen('Use £400 total.', 'Send one letter per recipient.')))
        self.assertIsNone(budget_response(self.frozen('Use £400 total.', 'That report is weekly, one per audience.')))

    def test_version_and_historical_behavior_are_explicit(self):
        frozen = self.frozen('Use £437 or £683.')
        old = {k: v for k, v in frozen.items() if k != 'budget_policy'}
        self.assertIsNone(budget_response(old))
        for version in (None, 'absolute-gbp/future'):
            with self.assertRaises(ValueError):
                budget_clarification(frozen | {'budget_policy': version})
        self.assertIsNone(budget_response(self.frozen('Prepare a contractor campaign.')))
        previous = self.frozen('Use £400 per month or £500.') | {'budget_policy': 'absolute-gbp/v1'}
        self.assertEqual(budget_clarification(previous)['reason'], 'unconfirmed_total')
        self.assertEqual(budget_clarification(previous | {'budget_policy': BUDGET_POLICY})['reason'], 'non_total')


class BudgetReplyTests(unittest.TestCase):
    setUp = preparations.PreparationTests.setUp
    open = preparations.PreparationTests.open
    finish = preparations.PreparationTests.finish

    def question(self, relative=False, cid=None):
        cid = cid or self.c
        texts = ['Prepare a UK postal response experiment for contractors with £437 or £683.']
        if relative:
            texts = ['Prepare a UK postal contractor response experiment with £437.', 'Reduce that budget by £37.']
        for i, text in enumerate(texts):
            self.w.message_conversation(cid, 'm' + str(i), i, text)
        self.w.start_preparation(cid, 'question-' + cid, len(texts), False, False)
        for _ in range(5):
            self.w.advance_preparations()
        view = self.w.conversation(cid)
        self.assertEqual(view['preparations'][-1]['status'], 'needs_input')
        self.assertEqual(view['current_plan']['result']['outcome'], 'clarification')
        self.assertIsNone(view['current_plan']['result']['budget_pence'])
        self.assertEqual(view['execution']['used'], 0)
        self.assertEqual(view['campaigns'], [])
        return view['current_plan']

    def counts(self):
        with self.w._conversation_app().tasks.database.connect() as db:
            return {t: db.execute('SELECT count(*) FROM ' + t).fetchone()[0]
                    for t in ('conversation_messages', 'conversation_action_commands', 'tasks', 'drafts', 'model_calls')}

    def test_reply_and_lost_admission_replay_keep_one_new_revision_and_one_campaign(self):
        plan = self.question()
        original = copy.deepcopy(plan['result'])
        self.assertEqual(self.model.planner.requests, [])
        response = self.w.reply_budget_conversation(self.c, 'answer', 1, original['id'], 'Use GBP 400 as the total budget.')
        self.assertEqual(response['revision'], 2)
        self.assertEqual(response['messages'][-1]['content'], 'Use GBP 400 as the total budget.')
        self.model.planner.results = [conversations.proposal(budget_pence=40000)]
        admitted = self.w.start_preparation(self.c, 'reply-prepare', 2, False, False)
        preparation = admitted['preparations'][-1]
        self.w = self.open()
        replay = self.w.reply_budget_conversation(self.c, 'answer', 1, original['id'], 'Use GBP 400 as the total budget.')
        self.assertTrue(replay['message_receipt']['replayed'])
        self.assertEqual(self.w.start_preparation(self.c, 'reply-prepare', 2, False, False)['preparations'][-1]['id'], preparation['id'])
        for _ in range(8):
            self.w.advance_preparations()
        state = self.w.conversation(self.c)
        self.assertEqual(state['preparations'][-1]['status'], 'review_ready')
        self.assertEqual(len(state['messages']), 2)
        self.assertEqual(len(state['campaigns']), 1)
        self.assertEqual(state['plans'][0]['result'], original)
        self.assertFalse(state['plans'][0]['current'])
        result = state['current_plan']['result']
        self.assertEqual(result['budget_pence'], 40000)
        self.assertEqual(result['budget_evidence']['message_id'], response['message_receipt']['id'])
        self.assertEqual(result['requested_scope']['requirements'], original['requested_scope']['requirements'])
        review = self.w.view(state['campaigns'][0]['session_id'])['review']
        self.assertTrue(review['candidate_valid'])
        self.assertFalse(review['approval_valid'])
        self.assertIsNone(review['handoff'])
        self.assertEqual(len(self.model.planner.requests), 1)
        self.assertEqual(self.model.copy.requests, [])
        self.assertEqual(state['execution']['used'], 1)
        for key, revision, target, content in [('answer', 1, original['id'], 'Use £500.'),
                                               ('changed-key', 2, original['id'], 'Use £400.'),
                                               ('answer', 1, 'brief_other', 'Use GBP 400 as the total budget.')]:
            with self.assertRaises(Conflict):
                self.w.reply_budget_conversation(self.c, key, revision, target, content)

    def test_relative_budget_reply_resumes_the_original_admission_after_process_restart(self):
        plan = self.question(relative=True)
        reply = self.w.reply_budget_conversation(self.c, 'answer', 2, plan['result']['id'], 'The total budget is £400.')
        pending = self.w.start_preparation(self.c, 'reply-prepare', 3, False, False)['preparations'][-1]
        code = """import json,sys
from unittest.mock import patch
from acquisition.workspace import Workspace
from test_preparations import CombinedModel
from test_conversations import proposal
model=CombinedModel(proposal(budget_pence=40000))
with patch('acquisition.workspace.openrouter_key',return_value='offline-fake'),patch('acquisition.workspace.OpenRouter',return_value=model):
 w=Workspace(sys.argv[1],real_clock=lambda:1792972800.)
 replay=w.reply_budget_conversation(sys.argv[2],'answer',2,sys.argv[3],'The total budget is £400.')
 assert replay['message_receipt']['replayed']
 same=w.start_preparation(sys.argv[2],'reply-prepare',3,False,False)['preparations'][-1]
 assert same['id']==sys.argv[4]
 for _ in range(8):w.advance_preparations()
 v=w.conversation(sys.argv[2]);review=w.view(v['campaigns'][0]['session_id'])['review']
 assert review['manifest']['brief']['budget_pence']==40000
 assert not review['approval_valid'] and review['handoff'] is None
 print(json.dumps({'status':v['preparations'][-1]['status'],'messages':len(v['messages']),'calls':len(model.planner.requests),'used':v['execution']['used']}))
"""
        process = subprocess.run([sys.executable, '-c', code, str(self.root), self.c, plan['result']['id'], pending['id']],
                                 env=dict(os.environ, PYTHONPATH=os.pathsep.join((str(Path('src').resolve()), str(Path('tests').resolve())))),
                                 text=True, capture_output=True, timeout=25)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout), {'status': 'review_ready', 'messages': 3, 'calls': 1, 'used': 1})
        self.assertEqual(self.w.conversation(self.c)['messages'][-1]['id'], reply['message_receipt']['id'])

    def test_concurrent_replies_and_foreign_question_cannot_append_twice(self):
        plan = self.question()
        other = self.w.create_conversation('second', 'Second pending budget')['id']
        other_plan = self.question(cid=other)
        before = self.counts()
        with self.assertRaises(Conflict):
            self.w.reply_budget_conversation(self.c, 'foreign', 1, other_plan['result']['id'], 'Use £400.')
        self.assertEqual(self.counts(), before)
        database = self.w._conversation_app().tasks.database
        with database.connect() as db:
            rows = {r['conversation_id']: r['payload'] for r in db.execute(
                'SELECT conversation_id,payload FROM conversation_plans WHERE organization=?', ('local-conversations',))}
        try:
            with database.transaction() as db:
                db.execute('UPDATE conversation_plans SET payload=? WHERE organization=? AND conversation_id=?',
                           (rows[other], 'local-conversations', self.c))
            with self.assertRaises(Conflict):
                self.w.reply_budget_conversation(self.c, 'substituted-native-question', 1, other_plan['result']['id'], 'Use £400.')
            self.assertEqual(self.counts(), before)
        finally:
            with database.transaction() as db:
                db.execute('UPDATE conversation_plans SET payload=? WHERE organization=? AND conversation_id=?',
                           (rows[self.c], 'local-conversations', self.c))
        def answer(key):
            try:
                return self.w.reply_budget_conversation(self.c, key, 1, plan['result']['id'], 'Use £400.')['revision']
            except Conflict:
                return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(list(pool.map(answer, ('first', 'second'))), [2, 'conflict'])
        self.assertEqual(len(self.w.conversation(self.c)['messages']), 2)

    def test_non_total_request_and_reply_wait_for_a_whole_campaign_total(self):
        self.model.planner.results = [conversations.proposal(budget_pence=40000)]
        self.w.message_conversation(self.c, 'rate', 0, 'Prepare a UK postal contractor response experiment with £400 per 1,000 recipients.')
        self.w.start_preparation(self.c, 'rate-question', 1, False, False)
        for _ in range(6):
            self.w.advance_preparations()
        state = self.w.conversation(self.c)
        self.assertEqual(state['preparations'][-1]['status'], 'needs_input')
        self.assertEqual(state['execution']['used'], 0)
        self.assertEqual(state['campaigns'], [])
        first = state['current_plan']['result']
        self.w.reply_budget_conversation(self.c, 'rate-reply', 1, first['id'], '£400 is per audience, not the total budget.')
        self.w.start_preparation(self.c, 'rate-reply-question', 2, False, False)
        for _ in range(4):
            self.w.advance_preparations()
        again = self.w.conversation(self.c)
        self.assertEqual(again['preparations'][-1]['status'], 'needs_input')
        self.assertEqual(again['execution']['used'], 0)
        self.assertEqual(again['campaigns'], [])
        second = again['current_plan']['result']
        self.w.reply_budget_conversation(self.c, 'whole-total', 2, second['id'], 'Use GBP 400 as the total for the whole campaign. Send one letter per recipient and report once per week.')
        self.w.start_preparation(self.c, 'whole-total-prepare', 3, False, False)
        for _ in range(8):
            self.w.advance_preparations()
        final = self.w.conversation(self.c)
        self.assertEqual(final['preparations'][-1]['status'], 'review_ready')
        self.assertEqual(final['current_plan']['result']['budget_pence'], 40000)
        self.assertEqual(final['execution']['used'], 1)
        self.assertEqual(len(final['campaigns']), 1)
        self.assertEqual(final['plans'][0]['result'], first)
        self.assertEqual(final['plans'][1]['result'], second)

    def test_a_question_completed_during_projection_is_visible_with_terminal_preparation(self):
        self.w.message_conversation(self.c, 'rate', 0, 'Prepare a UK postal contractor response experiment with £400 per month.')
        self.w.start_preparation(self.c, 'question', 1, False, False)
        original = self.w.preparation_progress
        def completed(conversation_id):
            for _ in range(4):
                self.w.advance_preparations()
            return original(conversation_id)
        with patch.object(self.w, 'preparation_progress', completed):
            view = self.w.conversation(self.c)
        self.assertEqual(view['preparations'][-1]['status'], 'needs_input')
        self.assertEqual(view['current_plan']['status'], 'succeeded')
        self.assertEqual(view['current_plan']['result']['budget_clarification']['reason'], 'non_total')
        self.assertEqual(view['execution']['used'], 0)
        self.assertEqual(view['campaigns'], [])

    def test_a_model_budget_question_can_receive_an_exact_budget_reply(self):
        self.w.message_conversation(self.c, 'missing-budget', 0, 'Prepare a UK postal response experiment for contractors.')
        self.model.planner.results = [conversations.proposal(outcome='clarification', budget_pence=None,
                                                           question='What total GBP budget should I use?')]
        self.w.start_preparation(self.c, 'ask-missing', 1, False, False)
        for _ in range(4):
            self.w.advance_preparations()
        plan = self.w.conversation(self.c)['current_plan']
        self.assertEqual(plan['result']['budget_clarification']['reason'], 'missing')
        self.w.reply_budget_conversation(self.c, 'confirmed-missing', 1, plan['result']['id'], 'Use £400 in total.')
        self.model.planner.results = [conversations.proposal(budget_pence=40000)]
        self.w.start_preparation(self.c, 'prepare-missing-reply', 2, False, False)
        for _ in range(8):
            self.w.advance_preparations()
        state = self.w.conversation(self.c)
        self.assertEqual(state['preparations'][-1]['status'], 'review_ready')
        self.assertEqual(state['current_plan']['result']['budget_pence'], 40000)
        self.assertEqual(state['execution']['used'], 2)
        self.assertEqual(state['plans'][0]['result'], plan['result'])

    def test_a_reply_without_an_absolute_gbp_total_asks_again_without_inference(self):
        plan = self.question()
        self.w.reply_budget_conversation(self.c, 'unconfirmed-answer', 1, plan['result']['id'], 'Use 400 instead.')
        self.w.start_preparation(self.c, 'unconfirmed-prepare', 2, False, False)
        for _ in range(4):
            self.w.advance_preparations()
        current = self.w.conversation(self.c)
        self.assertEqual(current['preparations'][-1]['status'], 'needs_input')
        self.assertEqual(current['current_plan']['result']['outcome'], 'clarification')
        self.assertIsNone(current['current_plan']['result']['budget_pence'])
        self.assertEqual(current['execution']['used'], 0)
        self.assertEqual(current['campaigns'], [])
        self.assertEqual(self.model.planner.requests, [])
        self.assertEqual(current['plans'][0]['result'], plan['result'])

    def test_reply_rolls_back_if_question_or_saved_message_changes_during_writes(self):
        plan = self.question()
        database = self.w._conversation_app().tasks.database
        before = self.counts()
        for revision in (1, 2):
            with self.subTest(revision=revision):
                with database.connect() as db:
                    db.execute("CREATE TRIGGER alter_budget_reply AFTER INSERT ON conversation_action_commands BEGIN "
                               "UPDATE conversation_messages SET content='Substituted total £999.' WHERE organization='local-conversations' "
                               "AND conversation_id='" + self.c + "' AND revision=" + str(revision) + '; END')
                try:
                    with self.assertRaises(Conflict):
                        self.w.reply_budget_conversation(self.c, 'atomic-reply', 1, plan['result']['id'], 'Use £400.')
                    self.assertEqual(self.counts(), before)
                    self.assertEqual(self.w.conversation(self.c)['current_plan']['result'], plan['result'])
                finally:
                    with database.connect() as db:
                        db.execute('DROP TRIGGER alter_budget_reply')


class HistoricalBudgetTests(unittest.TestCase):
    setUp = conversations.ConversationTests.setUp
    message = conversations.ConversationTests.message
    plan = conversations.ConversationTests.plan
    finish = conversations.ConversationTests.finish
    open = conversations.ConversationTests.open

    def test_saved_policy_questions_keep_their_identity_and_accept_replies_after_restart(self):
        cases = [('absolute-gbp/v1', 'Prepare a UK contractor postal experiment with £400 per month or £500.', 'unconfirmed_total'),
                 ('absolute-gbp/v2', 'Prepare a UK contractor postal experiment with £400 total. Send one letter per recipient.', 'non_total')]
        for policy, content, reason in cases:
            with self.subTest(policy=policy):
                self.id = self.service.create('one', 'history-' + policy.rsplit('/', 1)[-1])['id']
                self.message(content)
                calls_before = len(self.model.requests)
                original = SqliteConversations.admit
                def historical_admission(store, *args, **kwargs):
                    frozen = original(store, *args, **kwargs)
                    frozen['budget_policy'] = policy
                    with store.database.transaction() as db:
                        db.execute('UPDATE conversation_plans SET payload=? WHERE organization=? AND conversation_id=?',
                                   (canonical(frozen), 'one', self.id))
                    return frozen
                with patch.object(SqliteConversations, 'admit', historical_admission):
                    run = self.plan()
                question = self.finish()
                self.assertEqual(question['budget_clarification']['reason'], reason)
                self.assertEqual(len(self.model.requests), calls_before)
                self.app = self.open()
                self.service = self.app.conversations
                self.assertEqual(self.plan(), run)
                self.assertEqual(self.service.view('one', self.id)['current_plan']['result'], question)
                reply = self.service.reply_budget('one', self.id, 'confirmed', 1, question['id'], 'Use £400 as the total campaign budget.')
                self.assertEqual(reply['revision'], 2)
                self.assertTrue(self.service.reply_budget('one', self.id, 'confirmed', 1, question['id'],
                                                        'Use £400 as the total campaign budget.')['message_receipt']['replayed'])
                self.model.results = [conversations.proposal(budget_pence=40000)]
                current_run = self.service.plan('one', self.id, 'confirmed-plan', 2)
                self.app.worker.drain('one', run_id=current_run)
                view = self.service.view('one', self.id)
                self.assertEqual(view['plans'][0]['result'], question)
                self.assertEqual(view['current_plan']['result']['budget_pence'], 40000)
                self.assertEqual(view['current_plan']['result']['budget_evidence']['message_id'], reply['message_receipt']['id'])
                frozen = self.service.store.snapshot('one', self.id)['admissions'][-1]
                self.assertEqual(frozen['budget_policy'], BUDGET_POLICY)

    def test_pre_policy_non_total_proposal_is_historical_not_fresh_authority(self):
        from acquisition.adapters.sqlite.conversation_provenance import require_requested_scope
        from acquisition.campaigns import CampaignScope, conversation_brief_from_plan
        owner = 'local-conversations'
        cid = self.service.create(owner, 'old-non-total')['id']
        self.service.message(owner, cid, 'rate', 0, 'Prepare a UK postal contractor experiment with £400 per 1,000 recipients.')
        original = SqliteConversations.admit
        def old_admission(store, *args, **kwargs):
            frozen = original(store, *args, **kwargs)
            frozen.pop('budget_policy')
            with store.database.transaction() as db:
                db.execute('UPDATE conversation_plans SET payload=? WHERE organization=? AND conversation_id=?',
                           (canonical(frozen), owner, cid))
            return frozen
        self.model.results = [conversations.proposal(budget_pence=40000)]
        with patch.object(SqliteConversations, 'admit', old_admission):
            run = self.service.plan(owner, cid, 'old-rate-plan', 1)
        self.app.worker.drain(owner, run_id=run)
        historical = self.service.view(owner, cid)['current_plan']['result']
        self.assertEqual(historical['budget_pence'], 40000)
        brief = conversation_brief_from_plan(historical, 'historical-rate')
        with self.app.tasks.database.connect() as db:
            with self.assertRaises(Conflict):
                require_requested_scope(db, asdict(brief), asdict(CampaignScope()))
        self.assertEqual(self.open().conversations.view(owner, cid)['current_plan']['result'], historical)
        self.service.message(owner, cid, 'whole', 1, 'Use £400 as the total for the whole campaign. Send one letter per recipient.')
        current_run = self.service.plan(owner, cid, 'whole-plan', 2)
        self.app.worker.drain(owner, run_id=current_run)
        current = self.service.view(owner, cid)['current_plan']['result']
        current_brief = conversation_brief_from_plan(current, 'confirmed-whole-total')
        with self.app.tasks.database.connect() as db:
            require_requested_scope(db, asdict(current_brief), asdict(CampaignScope()))
        self.assertEqual(self.service.view(owner, cid)['plans'][0]['result'], historical)

    def test_pre_policy_admission_replays_its_original_two_call_repair_contract(self):
        self.message('Use £437 or £683 for a UK contractor postal experiment.')
        original = SqliteConversations.admit
        def old_admission(store, *args, **kwargs):
            frozen = original(store, *args, **kwargs)
            frozen.pop('budget_policy')
            with store.database.transaction() as db:
                db.execute('UPDATE conversation_plans SET payload=? WHERE organization=? AND conversation_id=?',
                           (canonical(frozen), 'one', self.id))
            return frozen
        with patch.object(SqliteConversations, 'admit', old_admission):
            run = self.plan()
        self.model.results = [conversations.proposal(budget_pence=43700), conversations.proposal(outcome='clarification', budget_pence=None, question='What exact GBP budget should I use?')]
        result = self.finish()
        self.assertEqual(len(self.model.requests), 2)
        self.assertNotIn('budget_clarification', result)
        reopened = self.open()
        self.assertEqual(reopened.conversations.plan('one', self.id, 'plan', 1), run)
        self.assertEqual(reopened.conversations.view('one', self.id)['current_plan']['result'], result)
