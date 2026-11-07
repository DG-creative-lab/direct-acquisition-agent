"""The fresh verified fixture journey runs with durable stop and lease fences."""
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from acquisition.bootstrap import build, build_workspace_checkpoint, initialize_fixture_workspace
from acquisition.campaigns import CampaignService, DraftLease, brief_from
from acquisition.contracts import Conflict, NotFound, canonical
from acquisition.conversations import FIXTURE_MESSAGE
from acquisition.creative import fixture_catalog
from acquisition.reasoning import CallScope, ModelConfig, ModelError
from acquisition.reviews import ActorUnavailable
from acquisition.runtime import LeaseLost, Outcome
from acquisition.workspace import Workspace
from test_workspace_checkpoint import tree


OWNER = 'local-conversations'


class FixtureActivationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.parent = Path(temporary.name)
        self.root = self.parent / 'fixture'
        self.now = 1793016000.
        result = self.process('-m', 'acquisition.workspace_fixture', '--root', self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.w = self.workspace()
        gateway = patch('acquisition.workspace.OpenRouter', side_effect=AssertionError('Provider initialized'))
        gateway.start()
        self.addCleanup(gateway.stop)

    def process(self, *args):
        return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, timeout=25,
                              env=dict(os.environ, PYTHONPATH=str(Path('src').resolve())))

    def workspace(self):
        return Workspace(self.root, real_clock=lambda: self.now)

    def conversation(self, key='chat', content=FIXTURE_MESSAGE):
        cid = self.w.create_conversation(key, 'Verified fixture campaign')['id']
        self.w.message_conversation(cid, key + '-message', 0, content)
        return cid

    def start_campaign(self):
        cid = self.conversation()
        first = self.w.start_preparation(cid, 'prepare', 1, True, False)
        self.assertEqual(first['preparations'][0]['status'], 'planning')
        self.w.advance_preparations()
        self.w.advance_preparations()
        campaign, = self.w.conversation(cid)['campaigns']
        session = self.w.authority.get(campaign['session_id'])
        self.assertIsNone(session['case_id'])
        return cid, session

    def test_offline_journey_restarts_after_draft_commit_and_finishes_once(self):
        cid, session = self.start_campaign()
        sid, run, scope = session['id'], session['run_id'], session['organization']
        interrupted = self.process('-c', """
import os,sys
from unittest.mock import patch
from acquisition.workspace import Workspace
from acquisition.adapters.sqlite.tasks import SqliteTasks

def exit_after_draft(self, claim, outcome, now):
    assert claim.capability == 'campaigns.build_conversation.v1'
    assert outcome.data['draft_id']
    os._exit(91)

with patch.object(SqliteTasks, 'settle', exit_after_draft):
    Workspace(sys.argv[1], real_clock=lambda: float(sys.argv[2])).advance_preparations()
""", self.root, self.now)
        self.assertEqual(interrupted.returncode, 91, interrupted.stderr)
        app = self.w._app(session)
        pending = app.tasks.inspect(scope, run)
        self.assertEqual(pending['tasks'][1]['status'], 'running')
        with app.tasks.database.connect() as db:
            draft_id, = db.execute('SELECT draft_id FROM draft_operations WHERE organization=?', (scope,)).fetchone()

        self.now += 61
        self.w = self.workspace()
        replay = self.w.start_preparation(cid, 'prepare', 1, True, False)
        self.assertEqual(replay['campaigns'][0]['session_id'], sid)
        for _ in range(4):
            self.w.advance_preparations()
        review_ready = self.w.view(sid)
        self.assertEqual(self.w.conversation(cid)['preparations'][0]['status'], 'review_ready')
        self.assertEqual(review_ready['tasks']['run']['id'], run)
        self.assertEqual(review_ready['tasks']['admission']['status'], 'fixture')
        self.assertEqual(review_ready['tasks']['tasks'][1]['attempts'], 2)
        self.assertEqual(review_ready['review']['subject']['draft_id'], draft_id)
        self.assertFalse(review_ready['review']['approval_valid'])
        self.assertIsNone(review_ready['review']['handoff'])
        self.assertEqual(self.w.authority.get(sid)['clock'], session['clock'])

        # Stopping at the waiting checkpoint preserves review without granting approval.
        stopped = self.w.stop_execution(cid, 'stop-at-review', 1)
        self.assertTrue(stopped['execution']['stopped'])
        self.w = self.workspace()
        self.w.recover_execution()
        waiting = self.w.view(sid)
        self.assertEqual(waiting['review']['subject'], review_ready['review']['subject'])
        self.assertFalse(waiting['review']['approval_valid'])
        with self.assertRaises(Conflict):
            app.tasks.acknowledge(scope, run, draft_id, self.now)
        subject = waiting['review']['subject']['id']
        with self.assertRaises(Conflict):
            self.w.action(sid, 'approve', {'request_id': 'wrong-subject', 'subject_id': 'wrong', 'reason': 'Review'})
        approved = self.w.action(sid, 'approve', {'request_id': 'approve', 'subject_id': subject, 'reason': 'Reviewed exact fixture'})
        handoff_command = {'request_id': 'handoff', 'approval_id': approved['review']['approval']['id']}
        accepted = self.w.action(sid, 'handoff', handoff_command)['review']['handoff']
        self.assertEqual(accepted['mode'], 'SYNTHETIC_NO_PRINT_NO_SEND')
        handoff_id = accepted['id']
        opened = self.w.action(sid, 'open-learning', {'request_id': 'open', 'handoff_id': handoff_id})
        cohort_id = opened['session']['cohort_id']
        targets = {'handoff_id': handoff_id, 'cohort_id': cohort_id}
        early = self.w.action(sid, 'observe', {'request_id': 'observe', **targets})
        self.assertEqual(early['learning']['status'], 'observing')
        self.assertGreater(early['learning']['missing'], 0)
        self.assertEqual(early['learning']['beliefs'], [])
        complete = self.w.action(sid, 'finalize', {'request_id': 'finalize', **targets})
        self.assertEqual(complete['learning']['status'], 'finalized')
        self.assertEqual(complete['learning']['missing'], 0)
        self.assertTrue(complete['learning']['beliefs'])

        self.w = self.workspace()
        replayed = self.w.action(sid, 'finalize', {'request_id': 'finalize', **targets})
        self.assertTrue(replayed['command_replayed'])
        self.assertEqual(replayed['learning']['events'], complete['learning']['events'])
        self.assertEqual(self.w.action(sid, 'handoff', handoff_command)['review']['handoff'], accepted)
        with app.tasks.database.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM draft_operations WHERE organization=?', (scope,)).fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count(*) FROM simulated_agency_jobs WHERE organization=?', (scope,)).fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count(*) FROM model_calls').fetchone()[0], 0)

    def test_stopped_claim_cannot_publish_or_resume_after_restart(self):
        cid, session = self.start_campaign()
        run, scope = session['run_id'], session['organization']
        app = self.w._app(session)
        claim = app.tasks.claim(scope, self.now, 60, run_id=run)
        self.assertEqual(claim.capability, 'campaigns.build_conversation.v1')
        self.w.stop_execution(cid, 'stop-in-flight', 1)
        with self.assertRaises((Conflict, LeaseLost)):
            app.worker.capabilities[claim.capability](claim)
        with self.assertRaises(LeaseLost):
            app.tasks.settle(claim, Outcome('succeeded', {}), self.now)
        with app.tasks.database.connect() as db:
            with self.assertRaisesRegex(sqlite3.IntegrityError, 'fixture execution authority'):
                db.execute("UPDATE tasks SET status='running' WHERE id=?", (claim.task_id,))
            self.assertEqual(db.execute('SELECT count(*) FROM drafts').fetchone()[0], 0)

        self.now += 61
        self.w = self.workspace()
        self.w.recover_execution()
        self.w.advance_preparations()
        state = self.w.conversation(cid)
        self.assertEqual(state['preparations'][0]['status'], 'cancelled')
        self.assertTrue(state['execution']['stopped'])
        self.assertEqual(self.w.stop_execution(cid, 'stop-in-flight', 1)['execution_receipt']['run_ids'], [run])
        self.assertEqual(self.w._app(session).worker.drain(scope, run_id=run), 0)
        self.assertEqual(self.w._app(session).tasks.inspect(scope, run)['run']['status'], 'cancelled')

    def test_expired_fixture_lease_cannot_publish_a_draft(self):
        _, session = self.start_campaign()
        app = self.w._app(session)
        scope, run = session['organization'], session['run_id']
        claim = app.tasks.claim(scope, self.now, 60, run_id=run)
        self.now += 61
        with self.assertRaises(LeaseLost):
            app.worker.capabilities[claim.capability](claim)
        with self.assertRaises(LeaseLost):
            app.tasks.settle(claim, Outcome('succeeded', {}), self.now - 61)
        with app.tasks.database.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM drafts').fetchone()[0], 0)
        self.assertTrue(app.worker.tick(scope, run_id=run))
        draft = app.tasks.inspect(scope, run)['tasks'][1]['output']['draft_id']
        operation = run + ':draft'
        with self.assertRaises(LeaseLost):
            app.drafts.put(scope, operation, app.drafts.get(scope, draft))
        with self.assertRaises(LeaseLost):
            app.drafts.put(scope, operation, app.drafts.get(scope, draft),
                           lease=DraftLease(run, claim.task_id, claim.token))

    def test_alternate_operation_cannot_publish_without_a_fixture_lease(self):
        _, session = self.start_campaign()
        app = self.w._app(session)
        scope, run = session['organization'], session['run_id']
        claim = app.tasks.claim(scope, self.now, 60, run_id=run)
        self.now += 60
        brief = brief_from(claim.inputs['brief'])
        catalogue = tuple(c for c in fixture_catalog() if c.segment in brief.segments)
        with self.assertRaises(LeaseLost):
            CampaignService(app.audiences, app.drafts, fixture_catalog()).prepare_with_catalogue(
                scope, claim.inputs['snapshot_id'], brief, 'alternate', catalogue)
        self.assert_no_draft(app)

    def test_leased_publication_rejects_substituted_fixture_creatives(self):
        _, session = self.start_campaign()
        app = self.w._app(session)
        scope, run = session['organization'], session['run_id']
        claim = app.tasks.claim(scope, self.now, 60, run_id=run)
        brief = brief_from(claim.inputs['brief'])
        catalogue = fixture_catalog()
        selected = next(item for item in catalogue if item.segment in brief.segments)
        replacement = replace(selected, opening='DEMO: Substituted fixture copy.')
        changed = tuple(replacement if item == selected else item for item in catalogue)
        altered = tuple(item for item in changed if item.segment in brief.segments)
        campaigns = CampaignService(app.audiences, app.drafts, catalogue)
        args = (scope, claim.inputs['snapshot_id'], brief, run + ':draft', altered)
        lease = DraftLease(run, claim.task_id, claim.token)
        with self.assertRaises(Conflict):
            campaigns.prepare_with_catalogue(*args, lease=lease)
        with patch('acquisition.adapters.sqlite.drafts.fixture_catalog', return_value=changed):
            with self.assertRaises(Conflict):
                campaigns.prepare_with_catalogue(*args, lease=lease)
        self.assert_no_draft(app)
        result = app.worker.capabilities[claim.capability](claim)
        self.assertEqual(app.drafts.get(scope, result.data['draft_id']).manifest['snapshot_id'], claim.inputs['snapshot_id'])

    def assert_no_draft(self, app):
        with app.tasks.database.connect() as db:
            for table in ('drafts', 'draft_operations'):
                self.assertEqual(db.execute(f'SELECT count(*) FROM {table}').fetchone()[0], 0)

    @contextmanager
    def expire_during_insert(self, database, table):
        original = database.connect

        def advance_clock():
            self.now += 60
            return self.now

        @contextmanager
        def connect():
            with original() as db:
                db.create_function('advance_clock', 0, advance_clock)
                db.execute(f'CREATE TEMP TRIGGER expire_lease AFTER INSERT ON {table} BEGIN SELECT advance_clock(); END')
                yield db

        with patch.object(database, 'connect', connect):
            yield

    def test_fixture_draft_lease_expiring_during_write_rolls_back_publication(self):
        _, session = self.start_campaign()
        app = self.w._app(session)
        scope, run = session['organization'], session['run_id']
        claim = app.tasks.claim(scope, self.now, 60, run_id=run)
        with self.expire_during_insert(app.tasks.database, 'draft_operations'), self.assertRaises(LeaseLost):
            app.worker.capabilities[claim.capability](claim)
        self.assert_no_draft(app)
        self.assertTrue(app.worker.tick(scope, run_id=run))
        self.assertEqual(app.tasks.inspect(scope, run)['tasks'][1]['attempts'], 2)

    def test_fixture_lease_expiring_during_write_rolls_back_task_and_event(self):
        _, session = self.start_campaign()
        app = self.w._app(session)
        scope, run = session['organization'], session['run_id']
        for operation in ('settle', 'fail'):
            with self.subTest(operation=operation):
                claim = app.tasks.claim(scope, self.now, 60, run_id=run)
                before = app.tasks.inspect(scope, run)
                with self.expire_during_insert(app.tasks.database, 'events'), self.assertRaises(LeaseLost):
                    if operation == 'settle':
                        app.tasks.settle(claim, Outcome('succeeded', {}), self.now)
                    else:
                        app.tasks.fail(claim, 'failure', False, self.now)
                self.assertEqual(app.tasks.inspect(scope, run), before)
                with app.tasks.database.connect() as db:
                    self.assertEqual(db.execute('SELECT token FROM tasks WHERE id=?', (claim.task_id,)).fetchone()[0], claim.token)

    def test_fixture_review_refresh_uses_operator_authority_and_exact_subject(self):
        _, session = self.start_campaign()
        for _ in range(3):
            self.w.advance_preparations()
        app = self.w._app(session)
        scope = session['organization']
        review = self.w.view(session['id'])['review']
        args = (scope, review['case_id'], review['subject']['id'])
        with self.assertRaises(ActorUnavailable):
            app.reviews.refresh(*args, 'local-reviewer', 'refresh:draft')
        original = app.drafts.get(scope, review['subject']['draft_id'])
        recipient = original.mailing_csv.splitlines()[1].split(',')[0]
        app.reviews.store.suppress(scope, 'local-operator', 'suppress', recipient, 'Fixture test')
        with app.tasks.database.connect() as db:
            db.execute("""CREATE TRIGGER interrupted_refresh BEFORE INSERT ON review_events
                WHEN NEW.kind='proposal_revised' BEGIN SELECT RAISE(ABORT, 'refresh interrupted'); END""")
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'refresh interrupted'):
            app.reviews.refresh(*args, 'local-operator', 'refresh:draft')
        self.assertEqual(app.reviews.store.view(scope, args[1])['subject']['id'], args[2])
        with app.tasks.database.connect() as db:
            for table in ('drafts', 'draft_operations'):
                self.assertEqual(db.execute(f'SELECT count(*) FROM {table}').fetchone()[0], 1)
            db.execute('DROP TRIGGER interrupted_refresh')
        receipt = app.reviews.refresh(*args, 'local-operator', 'refresh:draft')
        self.assertNotEqual(receipt['subject_id'], review['subject']['id'])
        refreshed = app.drafts.get(scope, receipt['draft_id'])
        self.assertNotEqual(refreshed.id, original.id)
        self.assertEqual(refreshed.manifest['creatives'], original.manifest['creatives'])
        self.assertNotIn(recipient, refreshed.mailing_csv)
        with self.assertRaises(Conflict):
            app.reviews.refresh(*args, 'local-operator', 'stale-refresh')
        self.assertEqual(app.reviews.refresh(*args, 'local-operator', 'refresh:draft'), receipt)

    def test_paid_work_stays_paused_in_the_activated_database(self):
        cid = self.conversation('model', 'Plan a £600 direct-mail experiment for UK contractors.')
        state = self.w.plan_conversation(cid, 'paid-plan', 1)
        run = state['current_plan']['run_id']

        class Provider:
            def complete(self, request):
                raise AssertionError('Paid inference was dispatched')

        app = build(self.root / 'conversations.sqlite', clock=lambda: self.now, gateway=Provider(),
                    model_config=ModelConfig('test/paid', force_tool_choice=True))
        self.assertEqual(app.worker.drain(OWNER, run_id=run), 0)
        view = app.tasks.inspect(OWNER, run)
        self.assertEqual(view['admission']['status'], 'paused')
        task = view['tasks'][0]
        self.assertEqual(task['attempts'], 0)
        with app.tasks.database.connect() as db:
            with self.assertRaisesRegex(sqlite3.IntegrityError, 'fixture execution authority'):
                db.execute("UPDATE tasks SET status='running' WHERE id=?", (task['id'],))
        fixture = self.conversation('fixture')
        fixture_run = app.conversations.plan_fixture(OWNER, fixture, 'fixture-plan', 1)
        claim = app.tasks.claim(OWNER, self.now, 60, run_id=fixture_run)
        with self.assertRaisesRegex(ModelError, 'execution_admission_paused'):
            app.calls.reserve(CallScope(OWNER, fixture_run, claim.task_id, claim.token), 'paid', 'hash', 1, self.now)
        with app.tasks.database.connect() as db:
            with self.assertRaisesRegex(sqlite3.IntegrityError, 'inference remains paused'):
                db.execute('INSERT INTO model_calls VALUES(?,?,?,?,?,?,?,?,?)',
                           (OWNER, fixture_run, 'paid', claim.task_id, claim.token, 'hash', 'reserved', None, None))

    def test_artifact_comments_bind_exact_copy_and_replay_after_restart_without_inference(self):
        cid, session = self.start_campaign()
        for _ in range(3):
            self.w.advance_preparations()
        review = self.w.view(session['id'])['review']
        creative = review['manifest']['creatives'][1]
        inputs = dict(session_id=session['id'], expected_subject=review['subject']['id'],
                      target_id=creative['id'], expected_revision=1, feedback='Make this opening more direct.',
                      request_id='copy-comment')
        saved = self.w.comment_artifact(cid, **inputs)
        comment, = saved['artifact_comments']
        self.assertEqual((comment['target_id'], comment['subject_id'], comment['feedback']),
                         (creative['id'], review['subject']['id'], inputs['feedback']))
        self.assertEqual(comment['copy_mode'], 'fixture')
        reopened = self.workspace()
        self.assertEqual(reopened.comment_artifact(cid, **inputs)['artifact_comments'], [comment])
        observed = self.process('-c', """
import sys
from acquisition.workspace import Workspace
comments = Workspace(sys.argv[1]).conversation(sys.argv[2])['artifact_comments']
assert len(comments) == 1 and comments[0]['request_id'] == 'copy-comment'
""", self.root, cid)
        self.assertEqual(observed.returncode, 0, observed.stderr)
        app = reopened._app(session)
        self.assertEqual(app.reviews.store.view(session['organization'], review['case_id'])['subject'], review['subject'])
        with app.tasks.database.connect() as db:
            for table in ('model_calls', 'review_decisions', 'simulated_agency_jobs'):
                self.assertEqual(db.execute(f'SELECT count(*) FROM {table}').fetchone()[0], 0)
        with self.assertRaises(Conflict):
            reopened.comment_artifact(cid, **(inputs | {'feedback': 'Changed comment'}))
        with self.assertRaises(Conflict):
            reopened.comment_artifact(cid, **(inputs | {'request_id': 'forged', 'target_id': 'other-creative'}))
        other = self.conversation('other')
        with self.assertRaises(Conflict):
            reopened.comment_artifact(other, **(inputs | {'request_id': 'foreign'}))
        app.reviews.refresh(session['organization'], review['case_id'], review['subject']['id'], 'local-operator', 'refresh-comment')
        with self.assertRaises(Conflict):
            reopened.comment_artifact(cid, **(inputs | {'request_id': 'stale'}))
        self.assertEqual(reopened.comment_artifact(cid, **inputs)['artifact_comments'], [comment])

    def test_artifact_comment_audit_failure_rolls_back_receipt_and_disabled_actor_cannot_comment(self):
        cid, session = self.start_campaign()
        for _ in range(3):
            self.w.advance_preparations()
        review = self.w.view(session['id'])['review']
        app = self.w._app(session)
        inputs = dict(session_id=session['id'], expected_subject=review['subject']['id'],
                      target_id=review['manifest']['creatives'][0]['id'], expected_revision=1,
                      feedback='Review this opening.', request_id='atomic-comment')
        with app.tasks.database.connect() as db:
            db.execute("""CREATE TRIGGER reject_comment BEFORE INSERT ON review_events
                WHEN NEW.kind='artifact_commented' BEGIN SELECT RAISE(ABORT,'comment interrupted'); END""")
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'comment interrupted'):
            self.w.comment_artifact(cid, **inputs)
        self.assertEqual(self.w.conversation(cid)['artifact_comments'], [])
        with app.tasks.database.connect() as db:
            db.execute('DROP TRIGGER reject_comment')
        app.reviews.store.register_actor(session['organization'], 'local-operator', ('operator',), False)
        with self.assertRaises(ValueError):
            self.w.comment_artifact(cid, **inputs)
        app.reviews.store.register_actor(session['organization'], 'local-operator', ('operator',), True)
        self.assertEqual(len(self.w.comment_artifact(cid, **inputs)['artifact_comments']), 1)

    def preference_source(self, feedback='Use a concrete opening.'):
        cid, session = self.start_campaign()
        for _ in range(3):
            self.w.advance_preparations()
        review = self.w.view(session['id'])['review']
        creative = review['manifest']['creatives'][0]
        self.w.comment_artifact(cid, session['id'], review['subject']['id'], creative['id'], 1,
                                feedback, 'preference-comment')
        inputs = dict(session_id=session['id'], comment_id='preference-comment', preference_id='', action='confirm',
                      expected_revision=0, segments=[creative['segment']], preferred='Use a concrete situation.',
                      avoid='Vague promises.', reason='Explicit editorial guidance.', confirmed=True, request_id='remember')
        return cid, session, review, inputs

    def test_confirmed_preferences_scope_future_contexts_and_preserve_immutable_history_after_restart(self):
        cid, session, review, inputs = self.preference_source()
        self.assertEqual(self.w.conversation(cid)['writing_preferences'], [])
        self.assertEqual(self.w._app(session).memory.preferences(OWNER), [])
        first = self.w.change_writing_preference(cid, **inputs)['preference_receipt']
        memory = self.w._app(session).memory
        segment = inputs['segments'][0]
        other = 'contractors' if segment == 'inventory' else 'inventory'
        self.assertEqual(first['source']['target_id'], review['manifest']['creatives'][0]['id'])
        self.assertEqual(first['source']['feedback'], 'Use a concrete opening.')
        examples = memory.examples(session['organization'], segment)
        self.assertEqual(examples[0]['id'], first['id'] + ':v1')
        self.assertFalse(any(e['id'].startswith(first['id']) for e in memory.examples(session['organization'], other)))
        context = {'memory': examples, 'segment': segment}
        frozen = memory.put_context(session['organization'], context)
        corrected = inputs | dict(preference_id=first['id'], action='correct', expected_revision=1,
            preferred='Keep openings concise.', segments=[other], reason='Correct the audience and wording.', request_id='correct')
        second = self.w.change_writing_preference(cid, **corrected)['preference_receipt']
        self.assertEqual(second['revision'], 2)
        self.assertFalse(any(e['id'].startswith(first['id']) for e in memory.examples(session['organization'], segment)))
        self.assertEqual(memory.examples(session['organization'], other)[0]['preferred'], second['preferred'])
        # Another conversation campaign has a distinct internal campaign scope,
        # while explicitly confirmed guidance belongs to the local workspace organization.
        other_cid = self.conversation('next-campaign')
        self.w.start_preparation(other_cid, 'prepare-next', 1, True, False)
        for _ in range(5): self.w.advance_preparations()
        other_sid = self.w.conversation(other_cid)['campaigns'][0]['session_id']
        other_session = self.w._session(other_sid)
        self.assertNotEqual(other_session['organization'], session['organization'])
        self.assertEqual(self.w._app(other_session).memory.examples(other_session['organization'], other)[0]['preferred'], second['preferred'])
        retirement = corrected | dict(action='retire', expected_revision=2, reason='No longer our writing direction.', request_id='retire')
        retired = self.w.change_writing_preference(cid, **retirement)['preference_receipt']
        self.assertEqual(retired['status'], 'retired')
        reopened = self.workspace()
        self.assertEqual(reopened.change_writing_preference(cid, **inputs)['preference_receipt'], first)
        history, = reopened.conversation(cid)['writing_preferences']
        self.assertEqual([v['action'] for v in history['history']], ['confirm', 'correct', 'retire'])
        self.assertEqual(reopened._app(session).memory.get_context(session['organization'], frozen), context)
        self.assertFalse(any(e['id'].startswith(first['id']) for e in memory.examples(session['organization'], other)))
        self.assertEqual(self.w.view(session['id'])['review']['subject'], review['subject'])
        with memory.database.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM model_calls').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM review_decisions').fetchone()[0], 0)
            with self.assertRaisesRegex(sqlite3.IntegrityError, 'history is immutable'):
                db.execute('DELETE FROM writing_preference_versions')
        observed = self.process('-c', """
import sys
from acquisition.workspace import Workspace
p, = Workspace(sys.argv[1]).conversation(sys.argv[2])['writing_preferences']
assert p['status'] == 'retired' and len(p['history']) == 3
""", self.root, cid)
        self.assertEqual(observed.returncode, 0, observed.stderr)

    def test_preference_confirmation_rejects_missing_evidence_cross_scope_and_stale_edits(self):
        cid, session, review, inputs = self.preference_source()
        for changes in ({'confirmed': False}, {'segments': []}, {'segments': ['unknown']}, {'segments': [[]]},
                        {'comment_id': 'not-saved'}, {'expected_revision': True}):
            with self.subTest(changes=changes), self.assertRaises((ValueError, Conflict, NotFound)):
                self.w.change_writing_preference(cid, **(inputs | changes))
        other = self.conversation('foreign')
        with self.assertRaises(Conflict): self.w.change_writing_preference(other, **inputs)
        app = self.w._app(session)
        with self.assertRaises(NotFound):
            app.memory.change_preference('foreign-org', session['organization'], cid, 'preference-comment', '',
                'confirm', 0, inputs['segments'], inputs['preferred'], inputs['avoid'], inputs['reason'], True,
                'local-operator', 'foreign-scope', self.now)
        app.reviews.store.register_actor(session['organization'], 'local-operator', ('operator',), False)
        with self.assertRaises(ValueError): self.w.change_writing_preference(cid, **inputs)
        app.reviews.store.register_actor(session['organization'], 'local-operator', ('operator',), True)
        with app.tasks.database.transaction() as db:
            saved = db.execute("SELECT * FROM review_events WHERE kind='artifact_commented'").fetchone()
            db.execute("DELETE FROM review_events WHERE kind='artifact_commented'")
        with self.assertRaisesRegex(Conflict, 'audit evidence'): self.w.change_writing_preference(cid, **inputs)
        with app.tasks.database.transaction() as db:
            db.execute('INSERT INTO review_events VALUES(' + ','.join('?' for _ in saved) + ')', tuple(saved))
        first = self.w.change_writing_preference(cid, **inputs)['preference_receipt']
        with self.assertRaises(Conflict): self.w.change_writing_preference(cid, **(inputs | {'preferred': 'Changed inputs.'}))
        correction = inputs | dict(action='correct', preference_id=first['id'], expected_revision=1, request_id='edit')
        altered = first['source'] | {'feedback': 'Substituted feedback.'}
        with app.tasks.database.transaction() as db:
            db.execute('UPDATE review_commands SET receipt=? WHERE organization=? AND request_id=?',
                       (canonical(altered), session['organization'], inputs['comment_id']))
            db.execute("UPDATE review_events SET payload=? WHERE organization=? AND kind='artifact_commented'",
                       (canonical(altered), session['organization']))
        with self.assertRaisesRegex(Conflict, 'original saved request'):
            self.w.change_writing_preference(cid, **correction)
        with app.tasks.database.transaction() as db:
            db.execute('UPDATE review_commands SET receipt=? WHERE organization=? AND request_id=?',
                       (canonical(first['source']), session['organization'], inputs['comment_id']))
            db.execute("UPDATE review_events SET payload=? WHERE organization=? AND kind='artifact_commented'",
                       (canonical(first['source']), session['organization']))
        self.w.change_writing_preference(cid, **correction)
        with self.assertRaises(Conflict): self.w.change_writing_preference(cid, **(correction | {'request_id': 'stale'}))
        with self.assertRaises(Conflict): self.w.change_writing_preference(cid, **(inputs | {'request_id': 'confirm-again'}))
        with app.tasks.database.transaction() as db:
            db.execute("CREATE TRIGGER reject_preference BEFORE INSERT ON writing_preference_versions BEGIN SELECT RAISE(ABORT,'preference interrupted'); END")
        retry = correction | dict(expected_revision=2, request_id='atomic')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'preference interrupted'):
            self.w.change_writing_preference(cid, **retry)
        self.assertEqual(self.w.conversation(cid)['writing_preferences'][0]['revision'], 2)
        with app.tasks.database.transaction() as db: db.execute('DROP TRIGGER reject_preference')
        self.assertEqual(self.w.change_writing_preference(cid, **retry)['preference_receipt']['revision'], 3)

    def test_preference_checkpoint_restore_is_inspection_only_and_preserves_history(self):
        from acquisition.bootstrap import build_workspace_checkpoint
        cid, session, review, inputs = self.preference_source()
        self.w.change_writing_preference(cid, **inputs)
        checkpoints = build_workspace_checkpoint()
        bundle = self.parent / 'preference-checkpoint'
        restored = self.parent / 'preference-restore'
        checkpoint = checkpoints.create(self.root, bundle)
        checkpoints.restore(bundle, restored, checkpoint['checkpoint_id'])
        before = tree(restored)
        with self.assertRaisesRegex(Conflict, 'inspection-only'):
            Workspace(restored, real_clock=lambda: self.now)
        inspection = build(restored / 'conversations.sqlite', clock=lambda: self.now)
        self.assertEqual(inspection.memory.preferences(OWNER), self.w.conversation(cid)['writing_preferences'])
        with self.assertRaisesRegex(Conflict, 'inspection-only'):
            inspection.memory.change_preference(OWNER, session['organization'], cid, inputs['comment_id'], '',
                'confirm', 0, inputs['segments'], inputs['preferred'], inputs['avoid'], inputs['reason'], True,
                'local-operator', inputs['request_id'], self.now)
        self.assertEqual(tree(restored), before)

    def test_preference_context_snapshot_and_concurrent_corrections_never_mix_versions(self):
        from concurrent.futures import ThreadPoolExecutor
        cid, session, review, inputs = self.preference_source()
        inputs |= {'segments': ['inventory', 'contractors']}
        first = self.w.change_writing_preference(cid, **inputs)['preference_receipt']
        app = self.w._app(session)
        correction = inputs | dict(preference_id=first['id'], action='correct', expected_revision=1,
                                  preferred='Keep the revised preference.', request_id='concurrent-edit')
        original = app.memory.examples_snapshot
        snapshots = []
        def corrected_after_snapshot(organization, segments, fallbacks=None):
            result = original(organization, segments, fallbacks)
            if len(segments) == 2 and not snapshots:
                snapshots.append(result)
                self.w.change_writing_preference(cid, **correction)
            return result
        with patch.object(app.memory, 'examples_snapshot', side_effect=corrected_after_snapshot):
            _, contexts = app._model_inputs(session['organization'], 'freeze-both', size=20)
        for context_id in contexts.values():
            context = app.memory.get_context(session['organization'], context_id)
            self.assertEqual(context['memory'][0]['id'], first['id'] + ':v1')
            sources = context['agent_assets']['sources']
            self.assertTrue(any(s['kind'] == 'reviewer_preference' for s in sources))
        self.assertEqual(app.memory.examples(session['organization'], 'inventory')[0]['id'], first['id'] + ':v2')
        def race(key):
            try:
                return self.w.change_writing_preference(cid, **(correction | dict(expected_revision=2, request_id=key)))['preference_receipt']
            except Conflict:
                return None
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(race, ('correction-a', 'correction-b')))
        self.assertEqual(sum(result is not None for result in results), 1)
        winner = next(result for result in results if result)
        self.assertEqual(winner['revision'], 3)
        # A projection failure happens after the native commit and cannot claim
        # the decision was rejected or permit replacement of its saved inputs.
        from acquisition.conversations import MessageRejectedConflict
        lost = correction | dict(expected_revision=3, request_id='lost-read')
        with patch.object(self.w, 'conversation', side_effect=Conflict('projection interrupted')):
            with self.assertRaises(Conflict) as error:
                self.w.change_writing_preference(cid, **lost)
        self.assertNotIsInstance(error.exception, MessageRejectedConflict)
        self.assertEqual(self.w.change_writing_preference(cid, **lost)['preference_receipt']['revision'], 4)

    def test_schema_14_checkpoint_inspection_does_not_create_preference_storage(self):
        database = self.w._conversation_app().memory.database
        with database.transaction() as db:
            db.execute('DROP TABLE writing_preference_versions')
            db.execute('PRAGMA user_version=14')
        checkpoint = build_workspace_checkpoint()
        bundle = self.parent / 'old-checkpoint'
        checkpoint.create(self.root, bundle)
        before = tree(bundle)
        inspection = build(bundle / 'conversations.sqlite', clock=lambda: self.now)
        self.assertEqual(inspection.memory.preferences(OWNER), [])
        self.assertEqual(inspection.memory.examples(OWNER, 'inventory'), [])
        self.assertEqual(tree(bundle), before)

    def test_missing_schema_15_preference_history_is_blocked_instead_of_reported_empty(self):
        cid, session, review, inputs = self.preference_source()
        self.w.change_writing_preference(cid, **inputs)
        memory = self.w._app(session).memory
        with memory.database.transaction() as db:
            db.execute('DROP TABLE writing_preference_versions')
        with self.assertRaisesRegex(Conflict, 'history is unavailable'):
            memory.preferences(OWNER)
        with self.assertRaisesRegex(Conflict, 'history is unavailable'):
            build_workspace_checkpoint().create(self.root, self.parent / 'missing-history-checkpoint')

    def test_preference_source_prose_is_audit_only_in_the_actual_model_exchange(self):
        from test_model_copy import FakeModel
        original_feedback = 'SOURCE_DIRECTION_REMOVED_FROM_CONFIRMED_GUIDANCE'
        cid, session, review, inputs = self.preference_source(original_feedback)
        first = self.w.change_writing_preference(cid, **inputs)['preference_receipt']
        correction = inputs | dict(preference_id=first['id'], action='correct', expected_revision=1,
            preferred='Ask one concrete question.', reason='Use only this confirmed direction.', request_id='edit-projection')
        current = self.w.change_writing_preference(cid, **correction)['preference_receipt']
        app = self.w._app(session)
        _, contexts = app._model_inputs(session['organization'], 'freeze-wire', size=20)
        frozen = {segment: app.memory.get_context(session['organization'], context_id) for segment, context_id in contexts.items()}
        source_context = frozen[inputs['segments'][0]]
        self.assertEqual(source_context['memory'][0]['source']['feedback'], original_feedback)
        self.assertEqual(app.memory.preferences(OWNER)[0]['source'], current['source'])
        # Exercise preflight and dispatch through the normal copy worker with a
        # fake provider in a separate unsealed test database. The verified root
        # retains its paid pause and records no inference calls.
        model = FakeModel()
        fake = build(self.parent / 'fake-wire.sqlite', clock=lambda: self.now, gateway=model,
                     model_config=ModelConfig('test/model', max_calls=10))
        for segment, context in frozen.items():
            self.assertEqual(fake.memory.put_context(session['organization'], context), contexts[segment])
        run = fake.start_model(session['organization'], 'wire', size=20, contexts_override=contexts)
        fake.worker.drain(session['organization'])
        self.assertEqual(fake.tasks.inspect(session['organization'], run)['run']['status'], 'waiting')
        self.assertEqual(len(model.requests), 6)
        wire = canonical(model.requests)
        self.assertIn(correction['preferred'], wire)
        self.assertNotIn(original_feedback, wire)
        self.assertNotIn(inputs['preferred'], wire)
        self.assertIn(current['source']['subject_id'], wire)
        for segment, context_id in contexts.items():
            self.assertEqual(app.memory.get_context(session['organization'], context_id), frozen[segment])
        with app.memory.database.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM model_calls').fetchone()[0], 0)

    def test_preference_versions_reject_replace_for_both_keys_and_replay_the_original_receipt(self):
        cid, session, review, inputs = self.preference_source()
        first = self.w.change_writing_preference(cid, **inputs)['preference_receipt']
        memory = self.w._app(session).memory
        before = memory.preferences(OWNER)
        # Also repair a live schema-15 store created by the earlier feature
        # commit, without rewriting any recorded preference version.
        with memory.database.transaction() as db:
            db.execute('DROP TRIGGER writing_preference_no_replace')
        memory = build(memory.database.path, clock=lambda: self.now).memory
        with memory.database.connect() as db:
            self.assertEqual(db.execute('PRAGMA recursive_triggers').fetchone()[0], 0)
            original = dict(db.execute('SELECT * FROM writing_preference_versions').fetchone())
        for changes in ({'request_id': 'replacement-version'}, {'id': 'replacement-id', 'revision': 99}):
            substituted = original | changes | {'payload': canonical(first | {'preferred': 'Substituted history.'})}
            with self.subTest(changes=changes), memory.database.transaction() as db:
                with self.assertRaisesRegex(sqlite3.IntegrityError, 'history is immutable'):
                    db.execute('INSERT OR REPLACE INTO writing_preference_versions VALUES(?,?,?,?,?,?)', tuple(substituted.values()))
            self.assertEqual(memory.preferences(OWNER), before)
            self.assertEqual(self.w.change_writing_preference(cid, **inputs)['preference_receipt'], first)
        correction = inputs | dict(preference_id=first['id'], action='correct', expected_revision=1, request_id='legitimate-edit')
        self.assertEqual(self.w.change_writing_preference(cid, **correction)['preference_receipt']['revision'], 2)

    def test_retirement_during_context_selection_uses_authored_fallback_for_every_audience(self):
        from acquisition.creative import GroundedCopyAgent
        cid, session, review, inputs = self.preference_source()
        app = self.w._app(session)
        segments = ('inventory', 'contractors')
        for name in ('campaign', 'followup'):
            if name == 'followup':
                creative = review['manifest']['creatives'][0]
                self.w.comment_artifact(cid, session['id'], review['subject']['id'], creative['id'], 1,
                                        'Another source comment.', 'second-preference-comment')
                inputs |= {'comment_id': 'second-preference-comment', 'request_id': 'second-preference'}
            inputs |= {'segments': list(segments)}
            first = self.w.change_writing_preference(cid, **inputs)['preference_receipt']
            retire = inputs | dict(preference_id=first['id'], action='retire', expected_revision=1,
                                   request_id='retire-' + name)
            selected = []
            original = app.memory.examples_snapshot
            def retire_before_snapshot(organization, required_segments, fallbacks=None):
                # In the old sequence each audience saw the active preference
                # and skipped seeding, then retirement preceded the final read.
                if len(required_segments) == 2 and not selected:
                    selected.append(True)
                    with app.memory.database.connect() as db:
                        self.assertEqual(db.execute('SELECT count(*) FROM editorial_memories').fetchone()[0], 0)
                    self.w.change_writing_preference(cid, **retire)
                return original(organization, required_segments, fallbacks)
            with patch.object(app.memory, 'examples_snapshot', side_effect=retire_before_snapshot):
                if name == 'campaign':
                    _, contexts = app._model_inputs(session['organization'], 'retirement-race', size=20)
                else:
                    snapshot = app.audiences.get(session['organization'], review['subject']['snapshot_id'])
                    learning = app.learning.store.memory_snapshot(session['organization'], segments)
                    contexts = app.followup_contexts(session['organization'], snapshot, segments, learning, 'Advisory test only.')
            self.assertTrue(selected)
            for segment, context_id in contexts.items():
                context = app.memory.get_context(session['organization'], context_id)
                self.assertTrue(context['memory'])
                self.assertEqual(context['memory'][0]['preferred'], context['guidance']['reviewer_examples'][segment]['preferred'])
                _, _, _, submit = GroundedCopyAgent.request(context)
                self.assertTrue(submit['function']['parameters']['properties']['memory_id']['enum'])

    def test_failed_grant_insert_rolls_back_admission_and_retry_keeps_original_request(self):
        cid = self.conversation()
        app = self.w._conversation_app()
        with app.tasks.database.connect() as db:
            db.execute("""CREATE TRIGGER interrupted_grant BEFORE INSERT ON fixture_execution_grants
                BEGIN SELECT RAISE(ABORT, 'grant interrupted'); END""")
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'grant interrupted'):
            app.conversations.plan_fixture(OWNER, cid, 'fixture-plan', 1)
        with app.tasks.database.connect() as db:
            saved, = db.execute('SELECT fingerprint FROM admission_requests WHERE organization=?', (OWNER,)).fetchone()
            for table in ('runs', 'execution_admissions', 'fixture_execution_grants', 'conversation_plans'):
                self.assertEqual(db.execute(f'SELECT count(*) FROM {table}').fetchone()[0], 0)
            db.execute('DROP TRIGGER interrupted_grant')
        run = app.conversations.plan_fixture(OWNER, cid, 'fixture-plan', 1)
        self.assertEqual(app.conversations.plan_fixture(OWNER, cid, 'fixture-plan', 1), run)
        with app.tasks.database.connect() as db:
            grant, = db.execute('SELECT fingerprint FROM fixture_execution_grants WHERE organization=? AND run_id=?',
                                (OWNER, run)).fetchone()
            self.assertEqual(grant, saved)
            with self.assertRaisesRegex(sqlite3.IntegrityError, 'grant is immutable'):
                db.execute('INSERT OR REPLACE INTO fixture_execution_grants VALUES(?,?,?)', (OWNER, run, 'changed'))
        self.assertEqual(app.worker.drain(OWNER, run_id=run), 1)

    def test_restored_fixture_grants_are_inspection_only_and_initialization_requires_fresh_root(self):
        cid = self.conversation()
        run = self.w._conversation_app().conversations.plan_fixture(OWNER, cid, 'queued', 1)
        bundle, restored = self.parent / 'bundle', self.parent / 'restored'
        checkpoint = build_workspace_checkpoint()
        manifest = checkpoint.create(self.root, bundle)
        checkpoint.restore(bundle, restored, manifest['checkpoint_id'])
        before = tree(restored)
        worker = self.process('-m', 'acquisition', '--db', restored / 'conversations.sqlite', '--organization', OWNER, 'work')
        self.assertEqual(worker.returncode, 2, worker.stderr)
        self.assertIn('inspection-only', worker.stderr)
        with self.assertRaisesRegex(Conflict, 'inspection-only'):
            initialize_fixture_workspace(restored)
        observed = build(restored / 'conversations.sqlite').tasks.inspect(OWNER, run)
        self.assertEqual(observed['admission']['status'], 'paused')
        self.assertEqual(observed['run']['status'], 'queued')
        self.assertEqual(tree(restored), before)
        with self.assertRaisesRegex(Conflict, 'fresh workspace'):
            initialize_fixture_workspace(self.root)
        paused = self.parent / 'paused'
        workspace = Workspace(paused, real_clock=lambda: self.now, verified_admissions=True)
        workspace.create_conversation('old', 'Paused workspace')
        old = tree(paused)
        # The lock file may already exist or be created for this inspection.
        with self.assertRaisesRegex(Conflict, 'fresh workspace'):
            initialize_fixture_workspace(paused)
        self.assertEqual({key: value for key, value in tree(paused).items() if key != 'server.lock'}, old)
