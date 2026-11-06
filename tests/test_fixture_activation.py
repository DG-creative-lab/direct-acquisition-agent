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
from acquisition.contracts import Conflict
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
