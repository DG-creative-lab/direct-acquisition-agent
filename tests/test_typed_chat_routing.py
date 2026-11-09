"""Typed chat proposals, exact consent and recovery against real workspace stores."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from acquisition.bootstrap import initialize_fixture_workspace
from acquisition.contracts import Conflict, NotFound, digest
from acquisition.conversations import FIXTURE_MESSAGE
from acquisition.workspace import Workspace
from test_conversation_actions import _set_up_workspace
from test_conversations import proposal
import test_conversation_learning as learning_tests


def restart(test, conversation_id, action_id, *, confirmed=False):
    script = """
import json, sys
from acquisition.workspace import Workspace
root, cid, action_id, clock, confirm = sys.argv[1:]
w = Workspace(root, real_clock=lambda: float(clock))
if confirm == 'True':
    saved = next(a for a in w.conversation(cid)['actions'] if a['id'] == action_id)
    w.confirm_typed_action(cid, action_id, 'confirm', saved['result']['id'], saved['revision'])
w.advance_actions()
for _ in range(6):
    w.advance_preparations()
print(json.dumps(w.conversation(cid)))
"""
    run = subprocess.run([sys.executable, '-c', script, str(test.root), conversation_id, action_id,
                          str(test.now), str(confirmed)], env=dict(os.environ, PYTHONPATH=str(Path('src').resolve())),
                         capture_output=True, text=True, timeout=25)
    test.assertEqual(run.returncode, 0, run.stderr)
    return json.loads(run.stdout)


class TypedPrepareTests(unittest.TestCase):
    setUp = _set_up_workspace

    @staticmethod
    def choose(w, cid, choice):
        candidates = choice['audience_candidates']
        entry = candidates['entries'][0]
        return w.select_conversation_audience(cid, request_id='audience', expected_revision=1,
            plan_id=candidates['plan_id'], dataset_id=entry['dataset_id'], version=entry['version'],
            checksum=entry['checksum'], manifest_id=entry['id'])['audience_receipt']

    def test_saved_confirmation_resumes_original_fixture_preparation_in_fresh_process(self):
        cid = self.w.create_conversation('prepare-chat', 'Fixture brief')['id']
        self.w.message_conversation(cid, 'brief', 0, FIXTURE_MESSAGE)
        view = self.w.route_followup(cid, 'route', 1, 'Prepare this campaign', False)
        action = view['actions'][0]
        self.assertEqual(action['result']['kind'], 'prepare_campaign')
        self.assertEqual(view['preparations'], [])
        self.assertEqual(view['revision'], 1)
        with self.assertRaises(Conflict):
            self.w.confirm_typed_action(cid, action['id'], 'bad', 'another-result', 1)
        with self.assertRaises(Conflict):
            self.w._conversation_app().actions.store.confirm_typed(
                'local-conversations', cid, action['id'], 'bad-store', 'another-result', 1)
        other = self.w.create_conversation('other', 'Unrelated')['id']
        with self.assertRaises(NotFound):
            self.w.confirm_typed_action(other, action['id'], 'foreign', action['result']['id'], 1)
        with patch.object(self.w, '_continue_typed_action', side_effect=OSError('interrupted')), self.assertRaises(OSError):
            self.w.confirm_typed_action(cid, action['id'], 'confirm', action['result']['id'], 1)
        saved = self.w.conversation(cid)
        self.assertTrue(saved['actions'][0]['continuation_pending'])
        self.assertEqual(saved['preparations'], [])
        waiting = restart(self, cid, action['id'], confirmed=True)
        self.assertEqual(waiting['campaigns'], [])
        self.assertEqual(waiting['preparations'][0]['status'], 'selecting_audience')
        selection = self.choose(self.w, cid, waiting['preparations'][0])
        final = restart(self, cid, action['id'])
        self.assertEqual(final['execution']['used'], 0)
        self.assertEqual(len(final['preparations']), 1)
        self.assertEqual(final['preparations'][0]['status'], 'review_ready')
        self.assertEqual(final['actions'][0]['typed_effect']['preparation_id'], final['preparations'][0]['id'])
        self.assertEqual(final['actions'][0]['confirmed'], saved['actions'][0]['confirmed'])
        self.assertEqual(len(final['campaigns']), 1)
        self.assertEqual(final['messages'], saved['messages'])
        review = self.w.view(final['campaigns'][0]['session_id'])['review']
        self.assertEqual(review['manifest']['brief']['audience_source'], selection)
        self.assertFalse(review['approval_valid'])
        self.assertIsNone(review['handoff'])

    def test_model_routes_saved_inventory_brief_and_preserves_generation_permission(self):
        cid = self.w.create_conversation('inventory', 'Inventory brief')['id']
        self.w.message_conversation(cid, 'brief', 0, 'Prepare a £600 UK postal response experiment for inventory.')
        self.gateway.action = 'prepare_campaign'
        self.gateway.planner.results = [proposal(segments=['inventory'], budget_pence=60000, copy_mode='fixture')]
        self.w.route_followup(cid, 'route', 1, 'Could you go ahead and prepare the campaign we discussed?', False)
        self.w.advance_actions()
        action = self.w.conversation(cid)['actions'][0]
        self.assertEqual(action['result']['kind'], 'prepare_campaign')
        self.assertEqual(self.w.conversation(cid)['preparations'], [])
        self.assertEqual(len(self.gateway.routing_requests), 1)
        self.assertEqual(len(self.gateway.planner.requests), 0)
        confirmed = self.w.confirm_typed_action(cid, action['id'], 'confirm', action['result']['id'], 1)
        preparation = confirmed['preparations'][0]
        self.assertFalse(preparation['inputs']['allow_model_copy'])
        for _ in range(4):
            self.w.advance_preparations()
        view = self.w.conversation(cid)
        self.assertEqual(view['current_plan']['result']['segments'], ['inventory'])
        self.assertEqual(view['preparations'][0]['status'], 'selecting_audience')
        self.assertEqual(view['execution']['used'], 2)
        self.assertEqual(len(self.gateway.copy.requests), 0)

    def test_model_cannot_bind_a_qualified_request_to_the_current_brief(self):
        cid = self.w.create_conversation('other-scope', 'Saved UK brief')['id']
        self.w.message_conversation(cid, 'brief', 0, FIXTURE_MESSAGE)
        self.gateway.action = 'prepare_campaign'
        self.w.route_followup(cid, 'route', 1, 'Prepare this campaign for France instead.', False)
        self.w.advance_actions()
        action = self.w.conversation(cid)['actions'][0]
        self.assertFalse(action['result']['requires_confirmation'])
        self.assertEqual(action['result']['evidence'], {})
        with self.assertRaises(Conflict):
            self.w.confirm_typed_action(cid, action['id'], 'confirm', action['result']['id'], 1)
        self.assertEqual(self.w.conversation(cid)['preparations'], [])
        self.assertEqual(self.gateway.planner.requests, [])

    def test_earlier_brief_or_stop_blocks_confirmed_preparation_recovery(self):
        for stop in (False, True):
            with self.subTest(stop=stop):
                cid = self.w.create_conversation('stale-' + str(stop), 'Fixture brief')['id']
                self.w.message_conversation(cid, 'brief', 0, FIXTURE_MESSAGE)
                action = self.w.route_followup(cid, 'route', 1, 'Prepare this campaign', False)['actions'][0]
                with patch.object(self.w, '_continue_typed_action', side_effect=OSError('interrupted')), self.assertRaises(OSError):
                    self.w.confirm_typed_action(cid, action['id'], 'confirm-' + str(stop), action['result']['id'], 1)
                if stop:
                    self.w.stop_execution(cid, 'stop', 1)
                else:
                    self.w.message_conversation(cid, 'amend', 1, 'Use £450 as the total.')
                final = restart(self, cid, action['id'])
                self.assertEqual(final['preparations'], [])
                self.assertEqual(final['campaigns'], [])
                self.assertFalse(final['actions'][0]['continuation_pending'])
                self.assertEqual(final['execution']['used'], 0)

    def test_prepare_can_use_a_saved_plan_without_replanning(self):
        cid = self.w.create_conversation('saved-plan', 'Planned brief')['id']
        self.w.message_conversation(cid, 'brief', 0, FIXTURE_MESSAGE)
        plan = self.w.plan_conversation_fixture(cid, 'plan', 1)['current_plan']['result']
        action = self.w.route_followup(cid, 'route', 1, 'Prepare the current brief', False)['actions'][0]
        self.assertEqual(action['result']['evidence']['plan_id'], plan['id'])
        waiting = self.w.confirm_typed_action(cid, action['id'], 'confirm', action['result']['id'], 1)
        self.assertEqual(waiting['campaigns'], [])
        with self.assertRaises(Conflict):
            self.w.draft_conversation(cid, 'skip-audience', 1, plan['id'])
        reopened = restart(self, cid, action['id'])
        self.assertEqual(reopened['campaigns'], [])
        selection = self.choose(self.w, cid, reopened['actions'][0]['audience_choice'])
        final = restart(self, cid, action['id'], confirmed=True)
        self.assertEqual(len(final['plans']), 1)
        self.assertEqual(final['plans'][0]['result'], plan)
        self.assertEqual(len(final['campaigns']), 1)
        self.assertEqual(final['execution']['used'], 0)
        review = self.w.view(final['campaigns'][0]['session_id'])['review']
        self.assertEqual(review['manifest']['brief']['audience_source'], selection)

    def test_pending_fixture_preparation_without_catalogue_flag_waits_for_selection(self):
        cid = self.w.create_conversation('early-chat', 'Fixture brief')['id']
        self.w.message_conversation(cid, 'brief', 0, FIXTURE_MESSAGE)
        action = self.w.route_followup(cid, 'route', 1, 'Prepare this campaign', False)['actions'][0]
        with patch.object(self.w, '_continue_typed_action'):
            confirmed = self.w.confirm_typed_action(cid, action['id'], 'confirm', action['result']['id'], 1)
        request = confirmed['action_confirmation']['effect_request_id']
        self.w.preparations.admit('local-conversations', cid, request, 1, True, False)
        waiting = restart(self, cid, action['id'])
        self.assertEqual(waiting['campaigns'], [])
        self.assertEqual(waiting['preparations'][0]['status'], 'selecting_audience')
        self.assertEqual(waiting['preparations'][0]['request_id'], request)
        selection = self.choose(self.w, cid, waiting['preparations'][0])
        final = restart(self, cid, action['id'])
        review = self.w.view(final['campaigns'][0]['session_id'])['review']
        self.assertEqual(review['manifest']['brief']['audience_source'], selection)

    def test_stop_at_saved_plan_session_creation_leaves_no_campaign_or_request(self):
        for verified in (False, True):
            with self.subTest(verified=verified), tempfile.TemporaryDirectory() as root:
                if verified:
                    initialize_fixture_workspace(root, clock=lambda: self.now)
                w = Workspace(root, real_clock=lambda: self.now)
                cid = w.create_conversation('stopped-plan', 'Planned brief')['id']
                w.message_conversation(cid, 'brief', 0, FIXTURE_MESSAGE)
                plan = w.plan_conversation_fixture(cid, 'plan', 1)['current_plan']['result']
                action = w.route_followup(cid, 'route', 1, 'Prepare the current brief', False)['actions'][0]
                waiting = w.confirm_typed_action(cid, action['id'], 'confirm', action['result']['id'], 1)
                self.choose(w, cid, waiting['actions'][0]['audience_choice'])
                request = waiting['action_confirmation']['effect_request_id']
                draft = w.draft_conversation

                def stop_before_draft(*args, **kwargs):
                    w.stop_execution(cid, 'stop', 1)
                    return draft(*args, **kwargs)

                with patch.object(w, 'draft_conversation', side_effect=stop_before_draft) as attempted, self.assertRaises(Conflict):
                    w.confirm_typed_action(cid, action['id'], 'confirm', action['result']['id'], 1)
                attempted.assert_called_once()
                reopened = Workspace(root, real_clock=lambda: self.now)
                reopened.advance_preparations()
                view = reopened.conversation(cid)
                self.assertEqual(view['current_plan']['result'], plan)
                self.assertTrue(view['execution']['stopped'])
                self.assertEqual(view['campaigns'], [])
                self.assertIsNone(reopened._draft_session_id(cid, request))
                self.assertEqual(reopened.listing()['sessions'], [])
                self.assertFalse(view['actions'][0]['continuation_pending'])
                if verified:
                    sid = 'workspace_' + digest({'conversation_id': cid, 'plan_id': plan['id']})[:24]
                    self.assertIsNone(reopened.authority.store.location(sid))

    def test_verified_creation_rolls_back_if_confirmation_disappears_during_writes(self):
        with tempfile.TemporaryDirectory() as root:
            initialize_fixture_workspace(root, clock=lambda: self.now)
            w = Workspace(root, real_clock=lambda: self.now)
            cid = w.create_conversation('commit-chat', 'Planned brief')['id']
            w.message_conversation(cid, 'brief', 0, FIXTURE_MESSAGE)
            plan = w.plan_conversation_fixture(cid, 'plan', 1)['current_plan']['result']
            action = w.route_followup(cid, 'route', 1, 'Prepare the current brief', False)['actions'][0]
            waiting = w.confirm_typed_action(cid, action['id'], 'confirm', action['result']['id'], 1)
            self.choose(w, cid, waiting['actions'][0]['audience_choice'])
            db = w._conversation_app().tasks.database
            with db.transaction() as connection:
                connection.execute('''CREATE TRIGGER drop_confirmation_after_session_write AFTER INSERT ON workspace_requests
                    WHEN NEW.kind='conversation' BEGIN
                        UPDATE conversation_actions SET confirmed=NULL WHERE organization=NEW.organization AND conversation_id=NEW.scope;
                    END''')
            with self.assertRaisesRegex(Conflict, 'original confirmed routing action'):
                w.confirm_typed_action(cid, action['id'], 'confirm', action['result']['id'], 1)
            self.assertEqual(w.conversation(cid)['campaigns'], [])
            request = waiting['action_confirmation']['effect_request_id']
            self.assertIsNone(w.authority.request('conversation', cid, request))
            sid = 'workspace_' + digest({'conversation_id': cid, 'plan_id': plan['id']})[:24]
            self.assertIsNone(w.authority.store.location(sid))
            self.assertEqual(w.conversation(cid)['actions'][0]['confirmed'], waiting['action_confirmation'])


class TypedExperimentTests(unittest.TestCase):
    setUp = learning_tests.ConversationLearningTests.setUp
    approve = learning_tests.ConversationLearningTests.approve
    accept = learning_tests.ConversationLearningTests.accept
    now = 1792972800.0

    def finalize(self):
        self.accept()
        self.w.action(self.sid, 'open-learning', {'request_id': 'open'})
        return self.w.action(self.sid, 'finalize', {'request_id': 'final'})

    def test_next_experiment_replays_committed_proposal_after_lost_response_and_restart(self):
        unavailable = self.w.route_followup(self.c, 'before', 1, 'Propose the next experiment', False)['actions'][0]
        self.assertFalse(unavailable['result']['requires_confirmation'])
        parent = self.finalize()
        view = self.w.route_followup(self.c, 'next', 1, 'Propose the next experiment', False)
        action = view['actions'][-1]
        self.assertEqual(action['result']['kind'], 'propose_next_experiment')
        self.assertEqual(action['result']['evidence']['cohort_id'], parent['learning']['cohort']['id'])
        self.assertEqual(self.w.view(self.sid)['followups'], [])
        propose = self.w.propose_followup
        def lost(*args, **kwargs):
            propose(*args, **kwargs)
            raise OSError('reply lost')
        with patch.object(self.w, 'propose_followup', side_effect=lost), self.assertRaises(OSError):
            self.w.confirm_typed_action(self.c, action['id'], 'confirm', action['result']['id'], 1)
        saved = self.w.view(self.sid)['followups'][0]
        final = restart(self, self.c, action['id'], confirmed=True)
        self.assertEqual(final['actions'][-1]['typed_effect']['proposal_id'], saved['id'])
        self.assertEqual(len(self.w.view(self.sid)['followups']), 1)
        self.assertEqual(len(final['campaigns']), 1)
        self.assertEqual(final['execution']['used'], 0)
        self.assertEqual(self.w.view(self.sid)['review']['handoff'], parent['review']['handoff'])
        self.assertIsNone(saved['session_id'])

    def test_source_revision_changes_during_proposal_commit_and_blocks_effect(self):
        self.finalize()
        action = self.w.route_followup(self.c, 'next', 1, 'Propose the next experiment', False)['actions'][-1]
        from acquisition.adapters.sqlite.followups import SqliteFollowups
        put = SqliteFollowups.put
        def edit(store, *args, **kwargs):
            self.w.message_conversation(self.c, 'interposed', 1, 'Use £450 in the next campaign.')
            return put(store, *args, **kwargs)
        with patch.object(SqliteFollowups, 'put', edit), self.assertRaises(Conflict):
            self.w.confirm_typed_action(self.c, action['id'], 'confirm', action['result']['id'], 1)
        self.assertEqual(self.w.view(self.sid)['followups'], [])
        final = restart(self, self.c, action['id'])
        self.assertEqual(final['revision'], 2)
        self.assertEqual(self.w.view(self.sid)['followups'], [])
        self.assertFalse(final['actions'][-1]['continuation_pending'])


    def test_stop_between_confirmation_and_proposal_commit_blocks_new_work(self):
        self.finalize()
        action = self.w.route_followup(self.c, 'next', 1, 'Propose the next experiment', False)['actions'][-1]
        from acquisition.adapters.sqlite.followups import SqliteFollowups
        put = SqliteFollowups.put
        def stop(store, *args, **kwargs):
            self.w.stop_execution(self.c, 'stop', 1)
            return put(store, *args, **kwargs)
        with patch.object(SqliteFollowups, 'put', stop), self.assertRaises(Conflict):
            self.w.confirm_typed_action(self.c, action['id'], 'confirm', action['result']['id'], 1)
        self.assertEqual(self.w.view(self.sid)['followups'], [])
        final = restart(self, self.c, action['id'])
        self.assertTrue(final['execution']['stopped'])
        self.assertFalse(final['actions'][-1]['continuation_pending'])
        self.assertEqual(self.w.view(self.sid)['followups'], [])
