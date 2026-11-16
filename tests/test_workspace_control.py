"""Atomic legacy admission, exact replay and recoverable control-store failures."""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

from acquisition.adapters.sqlite.workspace_control import SqliteWorkspaceControl, SqliteWorkspaceFaults
from acquisition.application.workspace import WorkspaceStorageUnavailable
from acquisition.contracts import Conflict, canonical


class WorkspaceControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.faults = SqliteWorkspaceFaults()
        self.store = SqliteWorkspaceControl(self.root, self.faults)

    def sql(self, statement, params=()):
        # This deliberately bypasses the port only to inject historical damage.
        with closing(sqlite3.connect(self.root / 'workspace.sqlite', isolation_level=None)) as db:
            return db.execute(statement, params).fetchall()

    def session(self, identity='campaign', organization='one', clock=10):
        return {'id': identity, 'organization': organization, 'clock': clock,
                'created_at': clock, 'run_id': None, 'case_id': None, 'cohort_id': None}

    def test_draft_admission_rolls_back_session_if_mapping_write_fails(self):
        self.sql("CREATE TRIGGER fail_draft BEFORE INSERT ON conversation_draft_requests BEGIN SELECT RAISE(ABORT,'disk fault'); END")
        with self.assertRaises(WorkspaceStorageUnavailable):
            self.store.admit_draft('conversation', 'request', 'original', self.session())
        self.assertIsNone(self.store.session('campaign'))
        self.assertIsNone(self.store.draft_request('conversation', 'request'))
        self.sql('DROP TRIGGER fail_draft')
        self.store.admit_draft('conversation', 'request', 'original', self.session())
        self.store.admit_draft('conversation', 'request', 'original', self.session(clock=99))
        self.assertEqual(json.loads(self.store.session('campaign')['payload'])['clock'], 10)
        with self.assertRaises(Conflict):
            self.store.admit_draft('conversation', 'request', 'changed', self.session('different'))
        self.assertIsNone(self.store.session('different'))

    def test_followup_admission_rollback_replay_and_organization_scope(self):
        child = self.session('child')
        self.sql("CREATE TRIGGER fail_followup BEFORE INSERT ON followup_prepare_requests BEGIN SELECT RAISE(ABORT,'disk fault'); END")
        with self.assertRaises(WorkspaceStorageUnavailable):
            self.store.admit_followup('one', 'request', 'inputs', 'child', 'session-inputs', child)
        self.assertIsNone(self.store.session('child'))
        self.sql('DROP TRIGGER fail_followup')
        self.store.admit_followup('one', 'request', 'inputs', 'child', 'session-inputs', child)
        self.store.admit_followup('one', 'new-request', 'inputs', 'child', 'session-inputs', None)
        self.store.admit_followup('two', 'request', 'other', 'other-child', 'other-inputs', self.session('other-child', 'two'))
        with self.assertRaises(Conflict):
            self.store.admit_followup('two', 'cross-scope', 'inputs', 'child', 'session-inputs', None)
        with self.assertRaises(Conflict):
            self.store.admit_followup('one', 'request', 'changed', 'child', 'session-inputs', None)
        self.assertEqual(self.sql('SELECT COUNT(*) FROM followup_prepare_requests')[0][0], 3)

    def test_report_clock_and_pending_command_commit_or_rollback_together(self):
        self.store.create_session('campaign', 'initial', self.session())
        self.sql("CREATE TRIGGER fail_command BEFORE INSERT ON commands BEGIN SELECT RAISE(ABORT,'disk fault'); END")
        with self.assertRaises(WorkspaceStorageUnavailable):
            self.store.begin_command('one', 'campaign', 'advance', 'exact-inputs', next_due=20)
        self.assertEqual(json.loads(self.store.session('campaign')['payload'])['clock'], 10)
        self.assertIsNone(self.store.command('one', 'campaign', 'advance'))
        self.sql('DROP TRIGGER fail_command')
        self.assertEqual(self.store.begin_command('one', 'campaign', 'advance', 'exact-inputs', next_due=20), {'clock': 20, 'done': False})
        self.store.complete_command('one', 'campaign', 'advance')
        self.assertEqual(self.store.begin_command('one', 'campaign', 'advance', 'exact-inputs', next_due=999), {'clock': 20, 'done': True})
        with self.assertRaises(Conflict):
            self.store.begin_command('one', 'campaign', 'advance', 'changed', next_due=999)
        for operation in (lambda: self.store.command('two', 'campaign', 'advance'),
                          lambda: self.store.begin_command('two', 'campaign', 'advance', 'exact-inputs'),
                          lambda: self.store.complete_command('two', 'campaign', 'advance')):
            with self.assertRaises(Conflict): operation()
        self.assertEqual(json.loads(self.store.session('campaign')['payload'])['clock'], 20)

    def test_concurrent_connections_admit_one_exact_session_and_mapping(self):
        other = SqliteWorkspaceControl(self.root, self.faults)
        barrier = threading.Barrier(2)
        def admit(item):
            store, fingerprint, clock = item
            barrier.wait(timeout=5)
            try:
                store.admit_draft('conversation', 'request', fingerprint, self.session(clock=clock))
                return fingerprint
            except Conflict:
                return None
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(admit, [(self.store, 'first', 10), (other, 'second', 20)]))
        winners = [value for value in results if value is not None]
        self.assertEqual(len(winners), 1)
        row = self.store.session('campaign')
        self.assertEqual(row['request_hash'], winners[0])
        self.assertEqual(self.store.draft_request('conversation', 'request')['request_hash'], winners[0])
        self.assertEqual(json.loads(row['payload'])['clock'], 10 if winners[0] == 'first' else 20)
        self.assertEqual(len(self.store.sessions()), 1)

    def test_session_replay_preserves_original_time_and_projection_preserves_fingerprint(self):
        self.store.create_session('campaign', 'initial', self.session())
        self.store.create_session('campaign', 'initial', self.session(clock=100))
        self.assertEqual(json.loads(self.store.session('campaign')['payload'])['created_at'], 10)
        with self.assertRaises(Conflict):
            self.store.create_session('campaign', 'changed', self.session(clock=100))
        self.store.project_session(self.session(clock=20))
        self.assertEqual(self.store.session('campaign')['request_hash'], 'initial')
        self.sql("UPDATE sessions SET payload='corrupt' WHERE id='campaign'")
        self.assertEqual(self.store.sessions()[0]['payload'], 'corrupt')
        self.store.project_session(self.session(clock=30))
        self.assertEqual(self.store.session('campaign')['payload'], canonical(self.session(clock=30)))

    def test_scoped_blockers_and_case_restoration_cannot_mutate_another_organization(self):
        self.store.create_session('campaign', 'initial', self.session())
        with self.assertRaises(Conflict):
            self.store.restore_case_links('two', 'campaign', 'run', 'case')
        self.store.restore_case_links('one', 'campaign', 'run', 'case')
        with self.assertRaises(Conflict):
            self.store.restore_case_links('one', 'campaign', 'other-run', 'other-case')
        with self.assertRaises(Conflict):
            self.store.save_session(self.session(organization='two'))
        self.assertEqual(json.loads(self.store.session('campaign')['payload'])['run_id'], 'run')
        for get, set_block in ((self.store.checkpoint_block, self.store.set_checkpoint_block),
                               (self.store.revision_block, self.store.set_revision_block)):
            set_block('one', 'same-id', 'storage-unavailable')
            set_block('two', 'same-id', 'authority-unavailable')
            set_block('one', 'same-id', None)
            self.assertIsNone(get('one', 'same-id'))
            self.assertEqual(get('two', 'same-id'), 'authority-unavailable')

    def test_fresh_process_retains_replay_receipts_without_authority_initialization(self):
        self.store.create_session('campaign', 'initial', self.session())
        self.store.begin_command('one', 'campaign', 'request', 'inputs', next_due=20)
        self.store.complete_command('one', 'campaign', 'request')
        journal = self.sql('SELECT * FROM workspace_identity')
        code = '''import json,sys
from acquisition.adapters.sqlite.workspace_control import SqliteWorkspaceControl, SqliteWorkspaceFaults
store=SqliteWorkspaceControl(sys.argv[1],SqliteWorkspaceFaults())
store.create_session('campaign','initial',None)
print(json.dumps(store.begin_command('one','campaign','request','inputs',next_due=999)))
'''
        result = subprocess.run([sys.executable, '-c', code, str(self.root)],
                                env=dict(os.environ, PYTHONPATH=str(Path('src').resolve())),
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {'done': True, 'clock': 20})
        self.assertEqual(self.sql('SELECT * FROM workspace_identity'), journal)
        self.assertFalse((self.root / 'conversations.sqlite').exists())
        # No transaction or lock escapes a completed operation.
        with closing(sqlite3.connect(self.root / 'workspace.sqlite', timeout=0)) as db:
            db.execute('BEGIN IMMEDIATE')

    def test_only_storage_errors_are_translated_and_recovery_retains_original_record(self):
        self.store.create_session('campaign', 'initial', self.session())
        self.sql('ALTER TABLE sessions RENAME TO unavailable_sessions')
        with self.assertRaises(WorkspaceStorageUnavailable) as failure:
            self.store.session('campaign')
        self.assertIsInstance(failure.exception.__cause__, sqlite3.Error)
        self.sql('ALTER TABLE unavailable_sessions RENAME TO sessions')
        self.assertEqual(json.loads(self.store.session('campaign')['payload']), self.session())
        for error in (ValueError('bad subject'), Conflict('stopped'), KeyboardInterrupt()):
            with self.assertRaises(type(error)) as propagated:
                with self.faults.guard(): raise error
            self.assertIs(propagated.exception, error)
