"""Offline migration effects through real application and journal stores."""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from unittest.mock import patch

from acquisition.adapters.sqlite.legacy_migration import MigrationTransaction
from acquisition.adapters.sqlite.database import Database
from acquisition.bootstrap import build, build_legacy_migration_inventory
from acquisition.contracts import Conflict, canonical, digest
from acquisition.conversations import FIXTURE_MESSAGE
from acquisition.reasoning import ModelConfig, ModelError
from acquisition.workspace import Workspace
from test_conversations import PlannerModel
from test_legacy_inventory import rows


ORG = 'local-conversations'


class LegacyMigrationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.path = self.root / 'conversations.sqlite'
        self.journal = self.root / 'workspace.sqlite'
        self.now = 1792972800.
        self.workspace = Workspace(self.root, real_clock=lambda: self.now)
        self.migration = build_legacy_migration_inventory(self.root)
        self.model = PlannerModel()
        self.app = build(self.path, clock=lambda: self.now, gateway=self.model,
                         model_config=ModelConfig('test/planner', max_calls=10, force_tool_choice=True),
                         workspace_organization=ORG)

    def planner(self, request, *, fixture=True):
        cid = self.app.conversations.create(ORG, request)['id']
        self.app.conversations.message(ORG, cid, 'message', 0, FIXTURE_MESSAGE)
        plan = self.app.conversations.plan_fixture if fixture else self.app.conversations.plan
        return cid, plan(ORG, cid, 'plan', 1)

    def seal(self):
        self.app.admissions.store.seal_legacy_writes()
        return self.migration.inspect()

    def snapshot(self):
        return rows(self.path), rows(self.journal)

    def child_process(self, *args):
        return subprocess.run([sys.executable, *args], capture_output=True, text=True, timeout=30,
                              env=dict(os.environ, PYTHONPATH=str(Path('src').resolve())))

    def cli_plan(self, operation, plan):
        return self.child_process('-m', 'acquisition.legacy_migration', '--root', str(self.root),
                                  operation, '--plan-id', plan['plan_id'])

    def cli_apply(self, plan):
        return self.cli_plan('apply', plan)

    def test_bind_exact_legacy_owners_and_preserve_the_original_records(self):
        cid, parent = self.planner('model', fixture=False)
        self.app.worker.drain(ORG, run_id=parent)
        proposal = self.app.conversations.view(ORG, cid)['current_plan']['result']
        packet = self.workspace.draft_conversation(cid, 'draft', 1, proposal['id'])
        session = self.workspace._session(packet['session']['id'])
        review = packet['review']
        approval = self.workspace.action(session['id'], 'approve', {
            'request_id': 'approve', 'subject_id': review['subject']['id'],
            'reason': 'Reviewed the exact synthetic campaign.'})['review']['approval']
        self.workspace.action(session['id'], 'handoff', {'request_id': 'handoff', 'approval_id': approval['id']})
        self.workspace.action(session['id'], 'open-learning', {'request_id': 'open'})
        self.workspace.action(session['id'], 'finalize', {'request_id': 'finalize'})
        self.app.execution.stop(ORG, cid, 'stop', 1)
        _, queued = self.planner('queued')
        unknown = self.app.start(ORG, 'unknown-cli', size=20)
        with self.app.tasks.database.transaction() as db:
            db.execute('INSERT INTO execution_pending_origins VALUES(?,?)', (ORG, unknown))
        self.seal()
        verified = self.app.start('another-org', 'new-paused', size=20)
        plan = self.migration.inspect()
        self.assertTrue(plan['apply_available'])
        before, journal_before = self.snapshot()
        report = self.migration.apply(plan['plan_id'])
        self.assertFalse(report['execution_activation'])
        candidates = {r['key']: r for r in plan['records'] if r['kind'] == 'run'}
        self.assertEqual(set(report['bound_records']), {candidates[run]['id'] for run in (parent, session['run_id'], queued)})
        self.assertEqual(candidates[unknown]['classification'], 'incomplete')
        self.assertEqual(candidates[verified]['format'], 'verified')
        after, journal_after = self.snapshot()
        self.assertEqual(after[0], before[0])
        self.assertEqual(journal_after, journal_before)
        changed = {name for name, value in before[1].items() if after[1][name] != value}
        self.assertEqual(changed, set())
        self.assertIn((ORG, parent, ORG, cid, 1), after[1]['execution_runs'])
        self.assertEqual(after[1]['execution_pending_origins'], [(ORG, unknown)])
        self.assertEqual(len(after[1]['legacy_run_bindings']), 3)
        accounting = self.app.execution.view(ORG, cid)
        self.assertEqual((accounting['used'], accounting['stopped_through']), (1, 1))
        self.assertEqual(self.app.worker.drain(ORG), 0)
        self.assertEqual(len(self.model.requests), 1)
        self.assertFalse(self.migration.inspect()['apply_available'])
        replay = self.cli_apply(plan)
        self.assertEqual(replay.returncode, 0, replay.stderr)
        self.assertEqual(json.loads(replay.stdout), report)
        self.assertEqual(self.snapshot(), (after, journal_after))

    def test_unsealed_store_cannot_apply_even_with_an_exact_plan(self):
        self.planner('legacy')
        plan = self.migration.inspect()
        self.assertFalse(plan['apply_available'])
        before = self.snapshot()
        with self.assertRaisesRegex(Conflict, 'already sealed'):
            self.migration.apply(plan['plan_id'])
        self.assertEqual(self.snapshot(), before)

    def test_changed_journal_invalidates_the_reviewed_plan(self):
        self.planner('legacy')
        plan = self.seal()
        with self.workspace.control() as db:
            db.execute("CREATE TABLE extra_history (payload TEXT)")
            db.execute("INSERT INTO extra_history VALUES ('new history')")
        before = self.snapshot()
        with self.assertRaisesRegex(Conflict, 'evidence changed'):
            self.migration.apply(plan['plan_id'])
        self.assertEqual(self.snapshot(), before)
        self.assertTrue(self.migration.inspect()['apply_available'])

    def test_missing_journal_never_creates_a_replacement_or_writes_bindings(self):
        self.planner('legacy')
        plan = self.seal()
        self.journal.rename(self.root / 'saved-journal.sqlite')
        before = rows(self.path)
        self.assertFalse(self.migration.inspect()['apply_available'])
        result = self.cli_apply(plan)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.journal.exists())
        self.assertEqual(rows(self.path), before)

    def test_committed_receipt_replays_read_only_after_source_journal_loss(self):
        self.planner('legacy')
        plan = self.seal()
        before = self.snapshot()
        missing = self.cli_plan('receipt', plan)
        self.assertEqual(missing.returncode, 2)
        self.assertIn('No committed migration receipt', missing.stderr)
        self.assertEqual(self.snapshot(), before)
        original = self.migration.apply(plan['plan_id'])
        self.journal.rename(self.root / 'saved-journal.sqlite')
        lock = self.root / 'server.lock'
        lock.unlink()
        before = rows(self.path)
        for operation in ('receipt', 'apply'):
            result = self.cli_plan(operation, plan)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), original)
        self.assertFalse(self.journal.exists())
        self.assertFalse(lock.exists())
        self.assertEqual(rows(self.path), before)

    def add_conflicting_session(self, run, other):
        identity = 'workspace_' + 'f' * 24
        session = {'id': identity, 'organization': ORG, 'database_scope': 'conversations',
                   'mode': 'fixture', 'clock': self.now, 'run_id': run,
                   'conversation_plan': {'id': 'brief_' + 'b' * 64, 'conversation_id': other, 'revision': 1}}
        with self.workspace.control() as db:
            db.execute('INSERT INTO sessions VALUES(?,?,?)', (identity, 'legacy', canonical(session)))

    def test_cutover_entrypoints_preserve_existing_quarantine_before_sealing(self):
        for entry in ('cli', 'cli_flag', 'workspace', 'workspace_authority', 'builder'):
            with self.subTest(entry=entry), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                path = root / 'conversations.sqlite'
                workspace = Workspace(root, real_clock=lambda: self.now)
                app = build(path, clock=lambda: self.now, workspace_organization=ORG)
                cid = app.conversations.create(ORG, 'cutover')['id']
                app.conversations.message(ORG, cid, 'message', 0, FIXTURE_MESSAGE)
                run = app.conversations.plan_fixture(ORG, cid, 'plan', 1)
                other = app.conversations.create(ORG, 'other')['id']
                identity = 'workspace_' + 'd' * 24
                session = {'id': identity, 'organization': ORG, 'database_scope': 'conversations',
                           'mode': 'fixture', 'clock': self.now, 'run_id': run,
                           'conversation_plan': {'id': 'brief_' + 'b' * 64,
                                                 'conversation_id': other, 'revision': 1}}
                with workspace.control() as db:
                    db.execute('INSERT INTO sessions VALUES(?,?,?)', (identity, 'legacy', canonical(session)))
                with app.tasks.database.transaction() as db:
                    db.execute("DELETE FROM execution_commands WHERE organization=? AND request_id='workspace:journal:v1'", (ORG,))
                    db.execute('INSERT OR IGNORE INTO execution_pending_origins VALUES(?,?)', (ORG, run))
                before = rows(path)[1]
                if entry in {'cli', 'cli_flag'}:
                    command = [sys.executable, '-m', 'acquisition', '--db', str(path), '--organization', ORG]
                    command += (['admission-cutover'] if entry == 'cli' else
                                ['--verified-admissions', 'status', '--run', run])
                    result = subprocess.run(command, capture_output=True, text=True, timeout=30,
                                            env=dict(os.environ, PYTHONPATH=str(Path('src').resolve())))
                    self.assertEqual(result.returncode, 0, result.stderr)
                elif entry == 'workspace':
                    Workspace(root, real_clock=lambda: self.now, verified_admissions=True).listing()
                elif entry == 'workspace_authority':
                    selected = Workspace(root, real_clock=lambda: self.now, verified_admissions=True)
                    selected.authority
                    selected.listing()
                else:
                    build(path, clock=lambda: self.now, verified_admissions=True)
                after = rows(path)[1]
                self.assertEqual(after['execution_pending_origins'], before['execution_pending_origins'])
                self.assertEqual(after['execution_runs'], before['execution_runs'])
                reopened = build(path, clock=lambda: self.now)
                self.assertIsNone(reopened.execution.view(ORG, cid)['remaining'])
                self.assertEqual(reopened.worker.drain(ORG), 0)
                plan = build_legacy_migration_inventory(root).inspect()
                item = next(r for r in plan['records'] if r['kind'] == 'run' and r['key'] == run)
                self.assertEqual(item['classification'], 'conflicting')

    def test_cutover_restores_quarantine_for_weak_independence_receipts(self):
        anchor, _ = self.planner('anchor')
        _, weak = self.planner('weak-receipt')
        other_org = 'other-org'
        strong = self.app.start(other_org, 'independent', size=20)
        with self.workspace.control() as db:
            journal_id = db.execute('SELECT journal_id FROM workspace_identity').fetchone()[0]
        original = {}
        with self.app.tasks.database.transaction() as db:
            row = db.execute("SELECT receipt FROM execution_commands WHERE organization=? AND request_id='workspace:journal:v1'",
                             (ORG,)).fetchone()
            weak_binding = json.loads(row[0]) | {'basis': 'legacy_root_witness', 'witness': {'run_id': weak}}
            db.execute("UPDATE execution_commands SET inputs=?,receipt=? WHERE organization=? AND request_id='workspace:journal:v1'",
                       (canonical(weak_binding), canonical(weak_binding), ORG))
            strong_binding = {'kind': 'workspace_journal_binding', 'journal_id': journal_id,
                              'database_kind': 'conversations.sqlite', 'basis': 'before_first_run', 'witness': None}
            db.execute('INSERT INTO execution_commands VALUES(?,?,?,?)',
                       (other_org, 'workspace:journal:v1', canonical(strong_binding), canonical(strong_binding)))
            for org, run in ((ORG, weak), (other_org, strong)):
                db.execute('DELETE FROM execution_runs WHERE organization=? AND run_id=?', (org, run))
                inputs = {'run_id': run, 'fingerprint': '0' * 64, 'actor': 'local-operator',
                          'reason': 'Historical independence decision.'}
                request_hash = db.execute('SELECT request_hash FROM runs WHERE organization=? AND id=?',
                                          (org, run)).fetchone()[0]
                receipt = {'kind': 'independent_execution_resolution', 'inputs': inputs, 'request_hash': request_hash,
                           'known_calls': 0, 'actor_generation': 1, 'at': self.now}
                for key in ('independent:' + run, 'resolution:old-resolution'):
                    db.execute('INSERT INTO execution_commands VALUES(?,?,?,?)',
                               (org, key, canonical(inputs), canonical(receipt)))
                original[org] = (inputs, receipt)
        for entry in ('cli', 'cli_flag', 'workspace', 'builder', 'already_sealed'):
            with self.subTest(entry=entry), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for name in ('conversations.sqlite', 'workspace.sqlite'):
                    with closing(sqlite3.connect(self.root / name)) as source, closing(sqlite3.connect(root / name)) as target:
                        source.backup(target)
                path = root / 'conversations.sqlite'
                if entry == 'already_sealed':
                    with closing(sqlite3.connect(path)) as db, db:
                        db.execute("INSERT INTO admission_store_policy VALUES(1,'verified-paused/v1',?)", (self.now,))
                before = rows(path)[1]
                if entry in {'cli', 'cli_flag'}:
                    command = (['admission-cutover'] if entry == 'cli' else
                               ['--verified-admissions', 'status', '--run', weak])
                    result = self.child_process('-m', 'acquisition', '--db', str(path), '--organization', ORG, *command)
                    self.assertEqual(result.returncode, 0, result.stderr)
                elif entry == 'workspace':
                    Workspace(root, real_clock=lambda: self.now, verified_admissions=True).listing()
                elif entry == 'already_sealed':
                    build(path, clock=lambda: self.now)
                else:
                    build(path, clock=lambda: self.now, verified_admissions=True)
                after = rows(path)[1]
                self.assertEqual(after['execution_pending_origins'], [(ORG, weak)])
                for table in ('execution_runs', 'execution_commands', 'model_calls', 'tasks', 'events'):
                    self.assertEqual(after[table], before[table])
                reopened = build(path, clock=lambda: self.now)
                self.assertIsNone(reopened.execution.view(ORG, anchor)['remaining'])
                self.assertEqual(reopened.worker.drain(ORG), 0)
                inputs, receipt = original[ORG]
                self.assertEqual(reopened.execution.resolve_independent(
                    ORG, 'old-resolution', weak, inputs['fingerprint'], inputs['actor'], inputs['reason']), receipt)
                self.assertTrue(reopened.execution.pending(ORG, weak))
                self.assertFalse(reopened.execution.pending(other_org, strong))
                build(path, clock=lambda: self.now, verified_admissions=True)
                self.assertEqual(rows(path)[1], after)

    def test_requarantine_rolls_back_if_cutover_is_rejected(self):
        _, run = self.planner('blocked-cutover')
        self.app.tasks.claim(ORG, self.now, 60, run_id=run)
        inputs = {'run_id': run}
        with self.app.tasks.database.transaction() as db:
            db.execute('DELETE FROM execution_runs WHERE organization=? AND run_id=?', (ORG, run))
            db.execute("DELETE FROM execution_commands WHERE organization=? AND request_id='workspace:journal:v1'", (ORG,))
            db.execute('INSERT INTO execution_commands VALUES(?,?,?,?)',
                       (ORG, 'independent:' + run, canonical(inputs), canonical(inputs)))
        before = self.snapshot()
        result = self.child_process('-m', 'acquisition', '--db', str(self.path), 'admission-cutover')
        self.assertEqual(result.returncode, 2)
        self.assertIn('Quiesce', result.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_failed_cutover_keeps_quarantine_and_does_not_select_policy(self):
        _, run = self.planner('running')
        self.app.tasks.claim(ORG, self.now, 60, run_id=run)
        with self.app.tasks.database.transaction() as db:
            db.execute('INSERT OR IGNORE INTO execution_pending_origins VALUES(?,?)', (ORG, run))
        before = self.snapshot()
        result = self.child_process('-m', 'acquisition', '--db', str(self.path), 'admission-cutover')
        self.assertEqual(result.returncode, 2)
        self.assertIn('Quiesce', result.stderr)
        self.assertEqual(self.snapshot(), before)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertIsNone(db.execute('SELECT policy FROM admission_store_policy').fetchone())

    def test_workspace_cutover_preserves_quarantine_in_existing_sandbox_store(self):
        request = 'orphaned-sandbox'
        identity = 'workspace_' + digest({'request_id': request})[:24]
        path = self.root / identity / 'campaign.sqlite'
        legacy = build(path, clock=lambda: self.now)
        cid = legacy.conversations.create(ORG, 'legacy')['id']
        legacy.conversations.message(ORG, cid, 'message', 0, FIXTURE_MESSAGE)
        run = legacy.conversations.plan_fixture(ORG, cid, 'plan', 1)
        with legacy.tasks.database.transaction() as db:
            db.execute('INSERT OR IGNORE INTO execution_pending_origins VALUES(?,?)', (ORG, run))
        workspace = Workspace(self.root, real_clock=lambda: self.now, verified_admissions=True)
        workspace.create(request, 'fixture')
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute('SELECT policy FROM admission_store_policy').fetchone()[0],
                             'verified-paused/v1')
            self.assertIsNotNone(db.execute(
                'SELECT 1 FROM execution_pending_origins WHERE organization=? AND run_id=?', (ORG, run)).fetchone())
        reopened = build(path, clock=lambda: self.now)
        self.assertIsNone(reopened.execution.view(ORG, cid)['remaining'])

    def test_cutover_serializes_a_concurrent_ordinary_database_open(self):
        cid, run = self.planner('concurrent')
        with self.app.tasks.database.transaction() as db:
            db.execute('INSERT OR IGNORE INTO execution_pending_origins VALUES(?,?)', (ORG, run))
        entered, release, opening = Event(), Event(), Event()

        def clock():
            entered.set()
            if not release.wait(10):
                raise TimeoutError('Cutover was not released')
            return self.now

        def reopen():
            opening.set()
            return Database(self.path)

        with ThreadPoolExecutor(max_workers=2) as pool:
            cutover = pool.submit(Database, self.path, verified_admissions=True, clock=clock)
            self.assertTrue(entered.wait(10))
            with closing(sqlite3.connect(self.path, timeout=0)) as writer:
                with self.assertRaisesRegex(sqlite3.OperationalError, 'locked'):
                    writer.execute('BEGIN IMMEDIATE')
            other = pool.submit(reopen)
            self.assertTrue(opening.wait(10))
            release.set()
            cutover.result(timeout=20)
            other.result(timeout=20)
        with self.app.tasks.database.connect() as db:
            self.assertEqual(db.execute('SELECT policy FROM admission_store_policy').fetchone()[0],
                             'verified-paused/v1')
            self.assertIsNotNone(db.execute(
                'SELECT 1 FROM execution_pending_origins WHERE organization=? AND run_id=?', (ORG, run)).fetchone())
        reopened = build(self.path, clock=lambda: self.now)
        self.assertIsNone(reopened.execution.view(ORG, cid)['remaining'])

    def test_cutover_from_pre_v10_schema_with_history_requires_reconciliation(self):
        _, run = self.planner('old-schema')
        for version in (0, 8, 9):
            with self.subTest(version=version):
                path = self.root / f'old-{version}.sqlite'
                with closing(sqlite3.connect(self.path)) as source, closing(sqlite3.connect(path)) as db:
                    source.backup(db)
                    cutoff = db.execute('SELECT * FROM legacy_task_admissions ORDER BY rowid').fetchall()
                    tables = (('execution_pending_origins', 'execution_commands', 'execution_runs', 'conversation_execution')
                              if version < 9 else ('execution_pending_origins',))
                    for table in tables:
                        db.execute('DROP TABLE ' + table)
                    db.execute(f'PRAGMA user_version={version}')
                    db.commit()
                with self.assertRaisesRegex(Conflict, 'pre-v10 store'):
                    Database(path, verified_admissions=True, clock=lambda: self.now)
                with closing(sqlite3.connect(path)) as db:
                    self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], version)
                    self.assertIsNotNone(db.execute('SELECT 1 FROM runs WHERE organization=? AND id=?', (ORG, run)).fetchone())
                    self.assertIsNone(db.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='execution_pending_origins'").fetchone())
                    self.assertEqual(db.execute('SELECT * FROM legacy_task_admissions ORDER BY rowid').fetchall(), cutoff)

    def test_recreated_unbound_journal_cannot_clear_quarantine(self):
        cid, run = self.planner('quarantined')
        other, _ = self.planner('other')
        self.add_conflicting_session(run, other)
        self.seal()
        with self.app.tasks.database.transaction() as db:
            db.execute("DELETE FROM execution_commands WHERE organization=? AND request_id='workspace:journal:v1'", (ORG,))
            db.execute('INSERT INTO execution_pending_origins VALUES(?,?)', (ORG, run))
        item = next(r for r in self.migration.inspect()['records'] if r['key'] == run)
        self.assertEqual(item['classification'], 'conflicting')
        self.journal.rename(self.root / 'saved-journal.sqlite')
        Workspace(self.root, real_clock=lambda: self.now)
        plan = self.migration.inspect()
        item = next(r for r in plan['records'] if r['key'] == run)
        self.assertEqual(item['classification'], 'incomplete')
        self.assertIn('original_journal_binding_requires_reconciliation', item['reasons'])
        before = self.snapshot()
        with self.assertRaisesRegex(Conflict, 'supported legacy bindings'):
            self.migration.apply(plan['plan_id'])
        self.assertEqual(self.snapshot(), before)
        with self.workspace.control() as db:
            journal_id = db.execute('SELECT journal_id FROM workspace_identity').fetchone()[0]
        witness = {'kind': 'workspace_journal_binding', 'journal_id': journal_id, 'database_kind': 'conversations.sqlite',
                   'basis': 'legacy_root_witness', 'witness': run}
        with self.app.tasks.database.transaction() as db:
            db.execute('INSERT INTO execution_commands VALUES(?,?,?,?)',
                       (ORG, 'workspace:journal:v1', canonical(witness), canonical(witness)))
        plan = self.migration.inspect()
        self.assertFalse(plan['apply_available'])
        self.assertIn('original_journal_binding_requires_reconciliation',
                      next(r for r in plan['records'] if r['key'] == run)['reasons'])
        reopened = build(self.path, clock=lambda: self.now)
        self.assertIsNone(reopened.execution.view(ORG, cid)['remaining'])

    def test_matching_stale_journal_cannot_clear_quarantine(self):
        cid, run = self.planner('quarantined')
        other, safe = self.planner('other')
        backup = self.root / 'saved-journal.sqlite'
        with closing(sqlite3.connect(self.journal)) as source, closing(sqlite3.connect(backup)) as target:
            source.backup(target)
        self.add_conflicting_session(run, other)
        self.seal()
        with self.app.tasks.database.transaction() as db:
            db.execute('INSERT INTO execution_pending_origins VALUES(?,?)', (ORG, run))
        with closing(sqlite3.connect(backup)) as source, closing(sqlite3.connect(self.journal)) as target:
            source.backup(target)
        plan = self.migration.inspect()
        records = {r['key']: r for r in plan['records'] if r['kind'] == 'run'}
        self.assertEqual(records[run]['preserve']['journal_association'], 'identity_match_completeness_unproven')
        self.assertEqual(records[run]['classification'], 'incomplete')
        self.assertIn('execution_origin_requires_reconciliation', records[run]['reasons'])
        self.assertEqual(self.migration.apply(plan['plan_id'])['bound_records'], [records[safe]['id']])
        self.assertEqual(rows(self.path)[1]['execution_pending_origins'], [(ORG, run)])
        reopened = build(self.path, clock=lambda: self.now)
        self.assertIsNone(reopened.execution.view(ORG, cid)['remaining'])
        with self.assertRaisesRegex(Conflict, 'requires verified admission'):
            reopened.execution.descendant(ORG, 'manual', safe)
        with self.assertRaisesRegex(Conflict, 'requires verified admission'):
            reopened.execution.resolve_independent(ORG, 'attest', run, 'a' * 64, 'operator', 'Claimed independent.')
        self.assertEqual(rows(self.path)[1]['execution_pending_origins'], [(ORG, run)])

    def test_missing_execution_account_is_not_recreated_with_a_fresh_allowance(self):
        cid, lost = self.planner('missing-account')
        _, safe = self.planner('safe')
        self.seal()
        with self.app.tasks.database.transaction() as db:
            db.execute('DELETE FROM execution_runs WHERE organization=? AND run_id=?', (ORG, lost))
            db.execute('DELETE FROM conversation_execution WHERE organization=? AND conversation_id=?', (ORG, cid))
        plan = self.migration.inspect()
        records = {r['key']: r for r in plan['records'] if r['kind'] == 'run'}
        self.assertIn('original_execution_account_requires_reconciliation', records[lost]['reasons'])
        self.assertEqual(self.migration.apply(plan['plan_id'])['bound_records'], [records[safe]['id']])
        self.assertNotIn(cid, {r[1] for r in rows(self.path)[1]['conversation_execution']})

    def test_stopped_account_loss_and_recreation_stay_unresolved(self):
        cid, lost = self.planner('lost-stopped-account')
        _, safe = self.planner('healthy-account')
        stop = self.app.execution.stop(ORG, cid, 'stop', 1)
        self.seal()
        # A partial restore can leave a dangling execution index.
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('PRAGMA foreign_keys=OFF')
            db.execute('DELETE FROM conversation_execution WHERE organization=? AND conversation_id=?', (ORG, cid))
        for recreated in (False, True):
            with self.subTest(recreated=recreated):
                if recreated:
                    with self.app.tasks.database.transaction() as db:
                        db.execute('INSERT INTO conversation_execution VALUES(?,?,?,?,0)',
                                   (ORG, cid, 'conversation-execution/v1', 48))
                before = rows(self.path)
                state = Workspace(self.root, real_clock=lambda: self.now).conversation(cid)['execution']
                self.assertTrue(state['account_unresolved'])
                self.assertTrue(state['stopped'])
                self.assertEqual(state['stopped_through'], 1)
                self.assertIsNone(state['remaining'])
                self.assertFalse(state['cost_complete'])
                self.assertEqual(self.app.execution.stop(ORG, cid, 'stop', 1), stop)
                self.assertEqual(rows(self.path), before)
                plan = self.migration.inspect()
                records = {r['key']: r for r in plan['records'] if r['kind'] == 'run'}
                self.assertIn('original_execution_account_requires_reconciliation', records[lost]['reasons'])
                self.assertEqual(records[lost]['classification'], 'incomplete')
        receipt = self.migration.apply(plan['plan_id'])
        self.assertEqual(receipt['bound_records'], [records[safe]['id']])
        self.assertEqual(rows(self.path)[1]['conversation_execution'], before[1]['conversation_execution'])

    def test_existing_account_blocks_when_a_paid_run_loses_its_execution_link(self):
        cid, run = self.planner('lost-link', fixture=False)
        self.app.worker.drain(ORG, run_id=run)
        self.assertEqual(len(self.model.requests), 1)
        self.assertEqual(self.app.execution.view(ORG, cid)['remaining'], 47)
        other = self.app.conversations.create(ORG, 'unrelated-chat')['id']
        self.app.conversations.message(ORG, cid, 'next-brief', 1, FIXTURE_MESSAGE)
        queued = self.app.conversations.plan(ORG, cid, 'queued-plan', 2)
        with self.app.tasks.database.transaction() as db:
            link = tuple(db.execute('SELECT * FROM execution_runs WHERE organization=? AND run_id=?', (ORG, run)).fetchone())
            db.execute('DELETE FROM execution_runs WHERE organization=? AND run_id=?', (ORG, run))
        before = rows(self.path)

        reopened = Workspace(self.root, real_clock=lambda: self.now)
        state = reopened.conversation(cid)['execution']
        self.assertTrue(state['account_unresolved'])
        self.assertIsNone(state['remaining'])
        self.assertFalse(state['accounting_complete'])
        self.assertFalse(state['cost_complete'])
        self.assertEqual(rows(self.path)[1]['conversation_execution'], before[1]['conversation_execution'])
        self.assertEqual(reopened.conversation(other)['execution']['remaining'], 48)
        self.app.worker.drain(ORG, run_id=queued)
        self.assertEqual(len(self.model.requests), 1)
        self.assertEqual(rows(self.path)[1]['model_calls'], before[1]['model_calls'])

        self.app.conversations.message(ORG, cid, 'later-brief', 2, FIXTURE_MESSAGE)
        before = rows(self.path)
        with self.assertRaisesRegex(Conflict, 'Restore the original execution account'):
            self.app.conversations.plan(ORG, cid, 'later-plan', 3)
        self.assertEqual(rows(self.path), before)

        self.app.conversations.message(ORG, other, 'brief', 0, FIXTURE_MESSAGE)
        with self.app.tasks.database.transaction() as db:
            db.execute('INSERT INTO execution_runs VALUES(?,?,?,?,?)', (ORG, run, ORG, other, 1))
        for affected in (cid, other):
            with self.subTest(conversation=affected):
                self.assertIsNone(reopened.conversation(affected)['execution']['remaining'])

        with self.app.tasks.database.transaction() as db:
            db.execute('UPDATE execution_runs SET conversation_id=? WHERE organization=? AND run_id=?', (link[3], ORG, run))
        restored = reopened.conversation(cid)['execution']
        self.assertTrue(restored['accounting_complete'])
        self.assertEqual(restored['used'], 1)
        self.assertEqual(restored['remaining'], 47)

    def test_native_planning_history_blocks_a_fresh_allowance_without_account_or_index(self):
        cid, run = self.planner('unstopped-history', fixture=False)
        self.app.worker.drain(ORG, run_id=run)
        self.assertEqual(len(self.model.requests), 1)
        self.assertEqual(len(self.app.calls.inspect(ORG, run)), 1)
        with self.app.tasks.database.transaction() as db:
            db.execute('DELETE FROM execution_runs WHERE organization=? AND run_id=?', (ORG, run))
            db.execute('DELETE FROM conversation_execution WHERE organization=? AND conversation_id=?', (ORG, cid))

        before = rows(self.path)
        state = Workspace(self.root, real_clock=lambda: self.now).conversation(cid)['execution']
        self.assertTrue(state['account_unresolved'])
        self.assertIsNone(state['remaining'])
        self.assertFalse(state['cost_complete'])
        self.assertEqual(rows(self.path), before)

        other = self.app.conversations.create(ORG, 'intact-receipt-scope')['id']
        self.assertEqual(self.app.execution.view(ORG, other)['remaining'], 48)
        self.app.conversations.message(ORG, cid, 'new-brief', 1, 'Keep the £600 campaign for UK contractors.')
        before = rows(self.path)
        with self.assertRaisesRegex(Conflict, 'Restore the original execution account'):
            self.app.conversations.plan(ORG, cid, 'second-plan', 2)
        self.assertEqual(self.app.worker.drain(ORG), 0)
        self.assertEqual(len(self.model.requests), 1)
        self.assertEqual(rows(self.path), before)

        # If the native request and run are also absent, the original task and
        # scoped call receipt still identify the damaged account.
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('DELETE FROM conversation_plans WHERE organization=? AND conversation_id=?', (ORG, cid))
            db.execute('DELETE FROM runs WHERE organization=? AND id=?', (ORG, run))
        before = rows(self.path)
        state = self.app.execution.view(ORG, cid)
        self.assertTrue(state['account_unresolved'])
        self.assertIsNone(state['remaining'])
        self.assertEqual(rows(self.path), before)

        with self.app.tasks.database.transaction() as db:
            db.execute("UPDATE tasks SET inputs='{}' WHERE run_id=?", (run,))
        before = rows(self.path)
        self.assertTrue(self.app.execution.view(ORG, cid)['account_unresolved'])
        with self.assertRaisesRegex(Conflict, 'Restore the original execution account'):
            self.app.conversations.plan(ORG, cid, 'second-plan', 2)
        self.assertEqual(self.app.worker.drain(ORG), 0)
        self.assertEqual(len(self.model.requests), 1)
        self.assertEqual(rows(self.path), before)

    def test_native_routing_history_blocks_a_fresh_allowance_without_a_plan(self):
        from test_conversation_actions import ActionGateway
        model = ActionGateway()
        cid = self.workspace.create_conversation('route-history', 'Routing history')['id']
        self.workspace.message_conversation(cid, 'brief', 0, FIXTURE_MESSAGE)
        with patch('acquisition.workspace.openrouter_key', return_value='fixture'), \
             patch('acquisition.workspace.OpenRouter', return_value=model):
            self.workspace.route_followup(cid, 'route', 1, 'Please use £500 instead.', False)
            self.workspace.advance_actions()
        self.assertEqual(len(model.routing_requests), 1)
        with self.app.tasks.database.transaction() as db:
            db.execute('DELETE FROM execution_runs WHERE owner_organization=? AND conversation_id=?', (ORG, cid))
            db.execute('DELETE FROM conversation_execution WHERE organization=? AND conversation_id=?', (ORG, cid))
        before = rows(self.path)
        self.assertEqual(before[1]['conversation_plans'], [])
        state = self.workspace.conversation(cid)['execution']
        self.assertTrue(state['account_unresolved'])
        self.assertIsNone(state['remaining'])
        self.assertEqual(rows(self.path), before)

    def test_orphaned_call_without_run_or_task_blocks_allowance_initialization(self):
        cid, run = self.planner('orphaned-call', fixture=False)
        self.app.worker.drain(ORG, run_id=run)
        self.assertEqual(len(self.model.requests), 1)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('DELETE FROM execution_runs WHERE organization=? AND run_id=?', (ORG, run))
            db.execute('DELETE FROM conversation_execution WHERE organization=? AND conversation_id=?', (ORG, cid))
            db.execute('DELETE FROM tasks WHERE run_id=?', (run,))
            db.execute('DELETE FROM runs WHERE organization=? AND id=?', (ORG, run))

        before = rows(self.path)
        self.assertEqual(len(before[1]['conversation_plans']), 1)
        self.assertEqual(len(before[1]['model_calls']), 1)
        state = Workspace(self.root, real_clock=lambda: self.now).conversation(cid)['execution']
        self.assertTrue(state['account_unresolved'])
        self.assertIsNone(state['remaining'])
        self.assertFalse(state['cost_complete'])
        with self.assertRaisesRegex(Conflict, 'Restore the original execution account'):
            self.app.conversations.plan(ORG, cid, 'plan', 1)
        self.assertEqual(rows(self.path), before)

        self.app.conversations.message(ORG, cid, 'new-brief', 1, 'Keep the £600 campaign for UK contractors.')
        before = rows(self.path)
        with self.assertRaisesRegex(Conflict, 'Restore the original execution account'):
            self.app.conversations.plan(ORG, cid, 'second-plan', 2)
        self.assertEqual(self.app.worker.drain(ORG), 0)
        self.assertEqual(len(self.model.requests), 1)
        self.assertEqual(rows(self.path), before)

        another = self.app.conversations.create(ORG, 'new-chat')['id']
        self.assertIsNone(self.app.execution.view(ORG, another)['remaining'])
        other = self.app.conversations.create('other-org', 'new-chat')['id']
        self.assertEqual(self.app.execution.view('other-org', other)['remaining'], 48)

    def test_conflicting_and_uncertain_runs_stay_out_of_the_migration(self):
        _, safe = self.planner('safe')
        _, altered = self.planner('altered')
        _, uncertain = self.planner('uncertain', fixture=False)
        self.model.results = [ModelError('provider_request_failed')]
        self.app.worker.drain(ORG, run_id=uncertain)
        with self.app.tasks.database.transaction() as db:
            db.execute("UPDATE tasks SET inputs='{}' WHERE run_id=?", (altered,))
        plan = self.seal()
        records = {r['key']: r for r in plan['records'] if r['kind'] == 'run'}
        self.assertEqual(records[altered]['classification'], 'conflicting')
        self.assertEqual(records[uncertain]['classification'], 'uncertain')
        report = self.migration.apply(plan['plan_id'])
        self.assertEqual(report['bound_records'], [records[safe]['id']])
        self.assertEqual(self.app.worker.drain(ORG), 0)
        self.assertEqual(len(self.model.requests), 1)

    def test_manual_child_requires_its_original_domain_parent_even_with_a_journal_claim(self):
        cid, _ = self.planner('parent')
        self.app.worker.drain(ORG)
        plan = self.app.conversations.view(ORG, cid)['current_plan']['result']
        parent = self.workspace.draft_conversation(cid, 'draft', 1, plan['id'])['session']
        identity = 'workspace_' + 'f' * 24
        org = self.workspace._session(parent['id'])['organization']
        self.app.execution.descendant(org, identity, parent['run_id'])
        run = self.app.start(org, identity, size=20)
        child = {'id': identity, 'organization': org, 'database_scope': 'conversations',
                 'mode': 'fixture', 'clock': self.now, 'run_id': run, 'parent_id': parent['id']}
        with self.workspace.control() as db:
            db.execute('INSERT INTO sessions VALUES(?,?,?)', (identity, 'legacy', canonical(child)))
        cid, _ = self.planner('other')
        self.app.worker.drain(ORG)
        plan = self.app.conversations.view(ORG, cid)['current_plan']['result']
        other = self.workspace.draft_conversation(cid, 'other-draft', 1, plan['id'])['session']
        self.seal()
        item = next(r for r in self.migration.inspect()['records'] if r['key'] == child['run_id'])
        self.assertEqual(item['proposed_step'], 'migrate_paused_ownership')
        with self.workspace.control() as db:
            db.execute('UPDATE sessions SET payload=? WHERE id=?',
                       (canonical(child | {'parent_id': other['id']}), child['id']))
        plan = self.migration.inspect()
        item = next(r for r in plan['records'] if r['key'] == child['run_id'])
        self.assertIn('workspace_parent_claim_differs_from_domain_evidence', item['reasons'])
        self.assertNotIn(item['id'], self.migration.apply(plan['plan_id'])['bound_records'])

    def test_crash_before_commit_rolls_back_and_another_process_can_apply(self):
        self.planner('first')
        self.planner('second')
        plan = self.seal()
        before = self.snapshot()
        code = """
import os, sys
from acquisition.bootstrap import build_legacy_migration_inventory
from acquisition.adapters.sqlite.legacy_migration import MigrationTransaction
save = MigrationTransaction.save
def crash(self, bindings, receipt):
    save(self, bindings, receipt)
    os._exit(17)
MigrationTransaction.save = crash
build_legacy_migration_inventory(sys.argv[1]).apply(sys.argv[2])
"""
        result = self.child_process('-c', code, str(self.root), plan['plan_id'])
        self.assertEqual(result.returncode, 17, result.stderr)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.migration.inspect(), plan)
        committed = self.cli_apply(plan)
        self.assertEqual(committed.returncode, 0, committed.stderr)
        self.assertEqual(len(json.loads(committed.stdout)['bound_records']), 2)
        self.assertEqual(json.loads(self.cli_apply(plan).stdout), json.loads(committed.stdout))

    def test_source_writes_are_fenced_until_the_target_commits(self):
        self.planner('legacy')
        plan = self.seal()
        save = MigrationTransaction.save

        def probe(transaction, bindings, receipt):
            for path in (self.path, self.journal):
                with closing(sqlite3.connect(path, timeout=0)) as writer:
                    with self.assertRaisesRegex(sqlite3.OperationalError, 'locked'):
                        writer.execute('BEGIN IMMEDIATE')
            return save(transaction, bindings, receipt)

        with patch.object(MigrationTransaction, 'save', probe):
            self.migration.apply(plan['plan_id'])
        for path in (self.path, self.journal):
            with closing(sqlite3.connect(path, timeout=0)) as writer:
                writer.execute('BEGIN IMMEDIATE')

    def test_migration_journal_rejects_updates_deletes_and_replace(self):
        self.planner('legacy')
        plan = self.seal()
        original = self.migration.apply(plan['plan_id'])
        for table, payload in (('legacy_migration_receipts', 'receipt'), ('legacy_run_bindings', 'binding')):
            with self.subTest(table=table):
                for sql in (f"UPDATE {table} SET {payload}='{{}}'", f'DELETE FROM {table}',
                            f'INSERT OR REPLACE INTO {table} SELECT * FROM {table}'):
                    with self.app.tasks.database.transaction() as db:
                        with self.assertRaisesRegex(sqlite3.IntegrityError, 'immutable'):
                            db.execute(sql)
        self.assertEqual(self.migration.apply(plan['plan_id']), original)
