"""Checkpoint publication preserves history without carrying forward authority."""
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing, contextmanager
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from acquisition.bootstrap import build, build_workspace_checkpoint, build_contact_directory, build_recipient_contexts
from acquisition.contracts import Conflict, canonical
from acquisition.conversations import FIXTURE_MESSAGE
from acquisition.learning_demo import run_learning_demo
from acquisition.reasoning import CallScope
from acquisition.workspace import Workspace
from test_conversations import PlannerModel
from test_workspace_projection import records


MARKER = '.acquisition-checkpoint.json'


def tree(path):
    return {str(file.relative_to(path)): file.read_bytes() for file in path.rglob('*') if file.is_file()}


class WorkspaceCheckpointTests(TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.parent = Path(temporary.name).resolve()
        self.source = self.parent / 'source'
        self.bundle = self.parent / 'bundle'
        self.restore = self.parent / 'restored'
        self.now = 1792972800.
        self.workspace = Workspace(self.source, real_clock=lambda: self.now, verified_admissions=True)
        session = self.workspace.create('campaign', 'fixture')['session']
        self.campaign = session['id'] + '/campaign.sqlite'
        self.checkpoint = build_workspace_checkpoint()

    def cli(self, *args, module='acquisition.workspace_checkpoint'):
        return subprocess.run([sys.executable, '-m', module, *map(str, args)],
                              capture_output=True, text=True, timeout=20)

    def command(self, *args, module='acquisition.workspace_checkpoint'):
        result = self.cli(*args, module=module)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def python(self, code, *args):
        return subprocess.run([sys.executable, '-c', code, *map(str, args)],
                              capture_output=True, text=True, timeout=20)

    @contextmanager
    def held_by_process(self, code, path):
        with subprocess.Popen([sys.executable, '-c', code, str(path)], text=True,
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE) as process:
            try:
                self.assertEqual(process.stdout.readline().strip(), 'locked')
                yield
            finally:
                process.communicate(input='release\n', timeout=10)
                self.assertEqual(process.returncode, 0)

    def test_round_trip_preserves_scoped_authority_and_opaque_history(self):
        # A legacy-only store holds a real scripted approval, acceptance, and
        # finalized synthetic cohort. It also holds independently queued work.
        legacy_key = 'workspace_' + '1' * 24 + '/campaign.sqlite'
        learning = run_learning_demo(str(self.source / legacy_key), 'backup', 'history', self.parent / 'exports')
        legacy = build(self.source / legacy_key, clock=lambda: self.now)
        queued = legacy.start('another-org', 'pending', size=20)
        contacts = build_contact_directory(self.source / legacy_key,'contact-scope','fielddesk',lambda:1794528000.)
        contact_assessment = contacts.prepare('contact-scope','contact-request','fielddesk-crm-a',1,'email')
        recipient_contexts = build_recipient_contexts(self.source / legacy_key,'contact-scope','fielddesk',lambda:1794528000.)
        recipient_context = recipient_contexts.prepare('contact-scope','context-request',contact_assessment['assessment_id'],
            contact_assessment['report']['eligible'][0],'reviewed-context-a',1)
        # Seed a paid historical conversation via a fake provider, then seal.
        paid_root = self.parent / 'paid'
        w = Workspace(paid_root, real_clock=lambda: self.now)
        cid = w.create_conversation('chat', 'Scoped history')['id']
        w.message_conversation(cid, 'brief', 0, FIXTURE_MESSAGE)
        with patch('acquisition.workspace.openrouter_key', return_value='fake'), \
             patch('acquisition.workspace.OpenRouter', return_value=PlannerModel()):
            w.plan_conversation(cid, 'original-paid-plan', 1)
        w.stop_execution(cid, 'stop', 1)
        paid_app = w._conversation_app()
        execution = paid_app.execution.view('local-conversations', cid)
        self.assertGreater(execution['used'], 0)
        self.assertTrue(execution['stopped'])
        paid_app.admissions.store.seal_legacy_writes()
        paid = self.checkpoint.create(paid_root, self.parent / 'paid-checkpoint')
        self.assertEqual(paid['stores']['conversations.sqlite']['recorded_policy'], 'verified-paused/v1')

        # The main root includes a fresh paid admission with exact consent.
        conversation = self.workspace.create_conversation('chat', 'Frozen consent')['id']
        self.workspace.message_conversation(conversation, 'brief', 0, FIXTURE_MESSAGE)
        self.workspace.start_preparation(conversation, 'plan', 1, False, True)
        self.workspace.stop_execution(conversation, 'stop', 1)
        with self.workspace.control() as db:
            db.execute('CREATE TABLE opaque_history (value BLOB)')
            db.execute('INSERT INTO opaque_history VALUES(?)', (b'\x00\xff original',))
        (self.source / '.env.local').write_text('EXAMPLE_NON_DATABASE_FILE')
        paths = ('conversations.sqlite', 'workspace.sqlite', self.campaign, legacy_key)
        expected = {key: records(self.source / key) for key in paths}
        self.assertTrue(expected['conversations.sqlite']['admission_requests'])
        self.assertTrue(expected['conversations.sqlite']['execution_commands'])
        self.assertTrue(expected[legacy_key]['review_decisions'])
        self.assertTrue(expected[legacy_key]['learning_outcomes'])
        with closing(sqlite3.connect(self.source / 'conversations.sqlite')) as reader:
            reader.execute('BEGIN')
            reader.execute('SELECT id FROM conversations').fetchall()
            # This commit cannot be checkpointed past the pinned WAL reader.
            latest = self.workspace.create_conversation('wal-message', 'WAL-only history')['id']
            self.assertGreater((self.source / 'conversations.sqlite-wal').stat().st_size, 0)
            expected['conversations.sqlite'] = records(self.source / 'conversations.sqlite')
            created = self.command('create', '--root', self.source, '--bundle', self.bundle)

        later = self.workspace.create_conversation('after-checkpoint', 'Later work')['id']
        self.assertTrue(any(later in row for row in records(self.source / 'conversations.sqlite')['conversations']))
        manifest = created['manifest']
        self.assertEqual(set(manifest['stores']), set(paths))
        self.assertEqual(manifest['stores'][legacy_key]['role'], 'legacy-application')
        self.assertEqual(manifest['stores'][legacy_key]['recorded_policy'], 'unsealed')
        before = tree(self.bundle)
        self.assertEqual(self.command('verify', '--bundle', self.bundle)['manifest'], manifest)
        self.restore.mkdir()
        restored = self.command('restore', '--bundle', self.bundle, '--root', self.restore,
                                '--checkpoint-id', manifest['checkpoint_id'])
        self.assertEqual(restored['post_checkpoint_effects'], 'unknown')
        self.assertEqual(tree(self.restore), before)
        self.assertEqual(tree(self.bundle), before)
        self.assertEqual({key: records(self.restore / key) for key in paths}, expected)
        restored_conversations = records(self.restore / 'conversations.sqlite')['conversations']
        self.assertTrue(any(latest in row for row in restored_conversations))
        self.assertFalse(any(later in row for row in restored_conversations))
        status = self.command('--db', self.restore / legacy_key, '--organization', 'another-org',
                              'status', '--run', queued, module='acquisition')
        self.assertEqual(status['run']['status'], 'queued')
        reopened = build(self.restore / legacy_key)
        view = reopened.learning.store.view(learning['organization'], learning['cohort_id'])
        self.assertEqual(view['status'], 'finalized')
        self.assertEqual(view['recommendations'], learning['recommendations'])
        contact_view = self.command('--db',self.restore / legacy_key,'--organization','contact-scope',
            '--profile','fielddesk','inspect','--assessment-id',contact_assessment['assessment_id'],module='acquisition.contact_cli')
        self.assertEqual(contact_view['saved']['report'],contact_assessment['report'])
        recipient_view = self.command('--db',self.restore / legacy_key,'--organization','contact-scope',
            '--profile','fielddesk','inspect','--request-id','context-request',module='acquisition.recipient_cli')
        self.assertEqual(recipient_view['saved']['context'],recipient_context['context'])
        refused_context = self.cli('--db',self.restore / legacy_key,'--organization','contact-scope','--profile','fielddesk',
            'prepare','--request-id','restored-context','--assessment-id',contact_assessment['assessment_id'],
            '--contact-id',contact_assessment['report']['eligible'][0],'--source','reviewed-context-a',
            '--source-version','1','--slots','contact_role',module='acquisition.recipient_cli')
        self.assertNotEqual(refused_context.returncode,0)
        refused = self.cli('--db',self.restore / legacy_key,'--organization','contact-scope','--profile','fielddesk',
            'prepare','--request-id','restored-contact','--connection','fielddesk-crm-a','--version','1','--channel','email',
            module='acquisition.contact_cli')
        self.assertNotEqual(refused.returncode,0)
        self.assertEqual(tree(self.restore), before)

        paid_restore = self.parent / 'paid-restored'
        self.checkpoint.restore(self.parent / 'paid-checkpoint', paid_restore, paid['checkpoint_id'])
        originals = records(paid_root / 'conversations.sqlite')
        recovered = records(paid_restore / 'conversations.sqlite')
        for name in ('model_calls', 'execution_runs', 'conversation_execution', 'execution_commands'):
            self.assertTrue(originals[name])
            self.assertEqual(recovered[name], originals[name])

    def test_fresh_processes_refuse_dispatch_and_mutation_in_legacy_and_verified_stores(self):
        legacy_key = 'workspace_' + '2' * 24 + '/campaign.sqlite'
        source = build(self.source / legacy_key, clock=lambda: self.now)
        pending = source.start('legacy-scope', 'queued', size=20)
        manifest = self.checkpoint.create(self.source, self.bundle)
        self.checkpoint.restore(self.bundle, self.restore, manifest['checkpoint_id'])
        before = tree(self.restore)

        # The worker and direct transaction both fail before a capability runs.
        # The same queued work is executable in the original unsealed store.
        code = """import sqlite3, sys
from acquisition.bootstrap import build
from acquisition.contracts import Conflict
from acquisition.reasoning import CallScope, Inference, ModelConfig
from acquisition.adapters.sqlite.database import Database
from acquisition.adapters.sqlite.preparations import SqlitePreparations
from pathlib import Path
root, key, pending = sys.argv[1:]
root = Path(root)
class Provider:
    def complete(self, request):
        raise AssertionError('A restored root attempted a provider request')

app = build(root / key, clock=lambda: 1792972800.)
inference = Inference(Provider(), app.calls, ModelConfig('fixture/model'), app.clock)
task = app.tasks.inspect('legacy-scope', pending)['tasks'][0]
scope = CallScope('legacy-scope', pending, task['id'], 'original-token')
for action in (
    lambda: app.worker.drain('legacy-scope'),
    lambda: inference.call(scope, 'call', [{'role': 'user', 'content': 'fixture'}], []),
    lambda: app.reviews.store.register_actor('legacy-scope', 'operator', ('operator',)),
    lambda: app.learning.store.finalize('legacy-scope', 'operator', 'req', 'cohort', 1792972800.),
    lambda: Database(root / 'new' / 'new.sqlite'),
    lambda: SqlitePreparations(root / 'workspace.sqlite'),
):
    try:
        action()
    except Conflict as exc:
        assert 'inspection-only' in str(exc), str(exc)
    else:
        raise AssertionError('Restored effect was not fenced')
try:
    with app.tasks.database.connect() as db:
        db.execute("DELETE FROM events")
except sqlite3.OperationalError as exc:
    assert 'readonly' in str(exc), str(exc)
else:
    raise AssertionError('Inspection connection was writable')
"""
        result = self.python(code, self.restore, legacy_key, pending)
        self.assertEqual(result.returncode, 0, result.stderr)
        commands = [
            ('acquisition', ('--db', self.restore / self.campaign, '--model', 'fake/model', 'work')),
            ('acquisition.workspace_server', ('--root', self.restore)),
            ('acquisition.conversation_cli', ('--root', self.restore, 'new', '--request-id', 'new')),
            ('acquisition.workspace_rebuild', ('--root', self.restore, 'rebuild')),
            ('acquisition.legacy_migration', ('--root', self.restore, 'apply', '--plan-id', 'migration_plan_' + '0' * 64)),
        ]
        for module, args in commands:
            with self.subTest(module=module):
                result = self.cli(*args, module=module)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn('inspection-only', result.stderr)
        self.assertEqual(tree(self.restore), before)
        self.assertGreater(source.worker.drain('legacy-scope'), 0)

    def test_malformed_missing_unsupported_and_mixed_bundles_never_publish(self):
        manifest = self.checkpoint.create(self.source, self.bundle)
        original = tree(self.bundle)
        second_root = self.parent / 'other'
        other = Workspace(second_root, real_clock=lambda: self.now, verified_admissions=True)
        other.create('campaign', 'fixture')
        second_bundle = self.parent / 'other-bundle'
        self.checkpoint.create(second_root, second_bundle)

        def change_manifest(bundle, change):
            path = bundle / MARKER
            content = json.loads(path.read_bytes())
            change(content)
            del content['checkpoint_id']
            payload = canonical(content).encode()
            content['checkpoint_id'] = hashlib.sha256(payload).hexdigest()
            path.write_text(canonical(content))

        def replace_registered(bundle):
            path = bundle / self.campaign
            shutil.copyfile(second_bundle / self.campaign, path)
            new = json.loads((second_bundle / MARKER).read_text())['stores'][self.campaign]
            change_manifest(bundle, lambda content: content['stores'].update({self.campaign: new}))

        def flip_byte(bundle):
            path = bundle / 'conversations.sqlite'
            data = path.read_bytes()
            path.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))

        def remove_registered(bundle):
            shutil.rmtree((bundle / self.campaign).parent)
            change_manifest(bundle, lambda content: content['stores'].pop(self.campaign))

        mutations = {
            'missing': lambda bundle: (bundle / 'workspace.sqlite').unlink(),
            'digest': flip_byte,
            'schema': lambda bundle: change_manifest(bundle, lambda data: data.update(format='workspace-checkpoint/v2')),
            'omitted': remove_registered,
            'mixed': replace_registered,
            'alias': lambda bundle: os.link(bundle / 'workspace.sqlite', self.parent / 'hardlink'),
            'sidecar': lambda bundle: (bundle / 'conversations.sqlite-wal').touch(),
            'traversal': lambda bundle: change_manifest(bundle, lambda data: data['stores'].update({'../source': {}})),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                bundle = self.parent / name
                shutil.copytree(self.bundle, bundle)
                mutate(bundle)
                result = self.cli('verify', '--bundle', bundle)
                self.assertEqual(result.returncode, 2, result.stdout)
                unchanged = tree(bundle)
                result = self.cli('restore', '--bundle', bundle, '--root', self.restore,
                                  '--checkpoint-id', manifest['checkpoint_id'])
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertFalse(self.restore.exists())
                self.assertEqual(tree(bundle), unchanged)
        self.assertEqual(tree(self.bundle), original)

    def test_registered_store_identity_is_checked_independently_of_manifest_hashes(self):
        manifest = self.checkpoint.create(self.source, self.bundle)
        store = self.bundle / self.campaign
        with closing(sqlite3.connect(store)) as db:
            db.execute('DROP TRIGGER application_identity_no_update')
            db.execute("UPDATE application_store_identity SET id=?", ('store_' + '0' * 32,))
            db.commit()
        info = manifest['stores'][self.campaign]
        info.update(identity='store_' + '0' * 32, sha256=hashlib.sha256(store.read_bytes()).hexdigest(),
                    bytes=store.stat().st_size)
        del manifest['checkpoint_id']
        manifest['checkpoint_id'] = hashlib.sha256(canonical(manifest).encode()).hexdigest()
        (self.bundle / MARKER).write_text(canonical(manifest))
        with self.assertRaisesRegex(Conflict, 'different identity'):
            self.checkpoint.verify(self.bundle)

    def test_inconsistent_index_blocks_capture_verification_and_restore(self):
        from acquisition.adapters.sqlite import workspace_checkpoint as storage

        def damage_tasks_index(path):
            # Keep a valid B-tree and the original entry count, but build
            # the keys in a different column order from the stored schema.
            with closing(sqlite3.connect(path)) as db:
                definition = db.execute(
                    "SELECT sql FROM sqlite_schema WHERE name='tasks_ready'"
                ).fetchone()[0]
                db.execute('DROP INDEX tasks_ready')
                db.execute('CREATE INDEX tasks_ready ON tasks(available_at,status)')
                db.execute('PRAGMA writable_schema=ON')
                db.execute("UPDATE sqlite_schema SET sql=? WHERE name='tasks_ready'", (definition,))
                db.commit()
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute('PRAGMA quick_check').fetchall(), [('ok',)])
                self.assertTrue(any('missing from index tasks_ready' in row[0]
                                    for row in db.execute('PRAGMA integrity_check')))

        manifest = self.checkpoint.create(self.source, self.bundle)
        snapshot_sqlite = storage.snapshot_sqlite

        def damaged_snapshot(source, target):
            snapshot_sqlite(source, target)
            if target.name == 'campaign.sqlite':
                damage_tasks_index(target)

        destination = self.parent / 'rejected'
        with patch.object(storage, 'snapshot_sqlite', side_effect=damaged_snapshot):
            with self.assertRaisesRegex(Conflict, 'SQLite integrity'):
                self.checkpoint.create(self.source, destination)
        self.assertFalse(destination.exists())

        damage_tasks_index(self.source / self.campaign)
        with patch.object(storage, 'snapshot_sqlite', wraps=snapshot_sqlite) as copy:
            with self.assertRaisesRegex(Conflict, 'SQLite integrity'):
                self.checkpoint.create(self.source, destination)
            copy.assert_not_called()
        self.assertFalse(destination.exists())

        # An older producer could have published this damage with valid hashes.
        store = self.bundle / self.campaign
        damage_tasks_index(store)
        manifest['stores'][self.campaign].update(
            sha256=hashlib.sha256(store.read_bytes()).hexdigest(), bytes=store.stat().st_size
        )
        del manifest['checkpoint_id']
        manifest['checkpoint_id'] = hashlib.sha256(canonical(manifest).encode()).hexdigest()
        (self.bundle / MARKER).write_text(canonical(manifest))
        before = tree(self.bundle)
        for operation, args in (
            ('verify', ()),
            ('restore', ('--root', self.restore, '--checkpoint-id', manifest['checkpoint_id'])),
        ):
            with self.subTest(operation=operation):
                result = self.cli(operation, '--bundle', self.bundle, *args)
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertIn('SQLite integrity', result.stderr)
                self.assertFalse(self.restore.exists())
                self.assertEqual(tree(self.bundle), before)

    def test_requires_original_checkpoint_id_and_refuses_nonempty_destination(self):
        manifest = self.checkpoint.create(self.source, self.bundle)
        with self.assertRaisesRegex(Conflict, 'requested checkpoint identity'):
            self.checkpoint.restore(self.bundle, self.restore, '0' * 64)
        self.assertFalse(self.restore.exists())
        self.restore.mkdir()
        marker = self.restore / 'existing'
        marker.write_text('preserve this root')
        with self.assertRaisesRegex(Conflict, 'empty destination'):
            self.checkpoint.restore(self.bundle, self.restore, manifest['checkpoint_id'])
        self.assertEqual(tree(self.restore), {'existing': b'preserve this root'})
        with self.assertRaisesRegex(Conflict, 'disjoint'):
            self.checkpoint.create(self.source, self.source / 'nested')

    def test_active_root_and_direct_sqlite_writer_are_excluded(self):
        flock = """import sys, fcntl
with open(sys.argv[1], 'a+') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    print('locked', flush=True)
    input()
"""
        transaction = """import sys, sqlite3
db = sqlite3.connect(sys.argv[1], isolation_level=None)
db.execute('BEGIN IMMEDIATE')
print('locked', flush=True)
input()
db.rollback()
db.close()
"""
        for code, path in ((flock, self.source / 'server.lock'),
                           (transaction, self.source / self.campaign)):
            with self.subTest(path=path.name), self.held_by_process(code, path):
                result = self.cli('create', '--root', self.source, '--bundle', self.bundle)
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertFalse(self.bundle.exists())
        self.command('create', '--root', self.source, '--bundle', self.bundle)

    def test_running_leases_and_unresolved_reservations_block_cold_capture(self):
        legacy_key = 'workspace_' + '3' * 24 + '/campaign.sqlite'
        app = build(self.source / legacy_key, clock=lambda: self.now)
        run = app.start('legacy-scope', 'pending', size=20)
        claim = app.tasks.claim('legacy-scope', self.now, 60)
        with self.assertRaisesRegex(Conflict, 'Quiesce running tasks'):
            self.checkpoint.create(self.source, self.bundle)
        # A stop can cancel the lease while its provider observation is pending.
        app.calls.reserve(self.scope(claim),
                          'still-pending', 'request-hash', 2, self.now)
        app.tasks.cancel('legacy-scope', run, self.now)
        with self.assertRaisesRegex(Conflict, 'reconcile reserved inference'):
            self.checkpoint.create(self.source, self.bundle)
        self.assertFalse(self.bundle.exists())
        app.calls.record(self.scope(claim), 'still-pending', None, 'provider_request_failed')
        self.checkpoint.create(self.source, self.bundle)
        self.assertEqual(records(self.bundle / legacy_key)['model_calls'][0][6:], (
            'unknown', None, 'provider_request_failed'))

    @staticmethod
    def scope(claim):
        return CallScope(claim.organization, claim.run_id, claim.task_id, claim.token)

    def test_restore_revalidates_the_staged_copy(self):
        from acquisition.adapters.sqlite import workspace_checkpoint as storage

        manifest = self.checkpoint.create(self.source, self.bundle)
        before = tree(self.bundle)
        original = storage.copy_snapshot

        def damaged_copy(source, target, size):
            original(source, target, size)
            if source.name == 'workspace.sqlite':
                with target.open('r+b') as stream:
                    stream.seek(-1, os.SEEK_END)
                    last = stream.read(1)
                    stream.seek(-1, os.SEEK_END)
                    stream.write(bytes([last[0] ^ 1]))

        with patch.object(storage, 'copy_snapshot', side_effect=damaged_copy):
            with self.assertRaisesRegex(Conflict, 'differs from its manifest'):
                self.checkpoint.restore(self.bundle, self.restore, manifest['checkpoint_id'])
        self.assertFalse(self.restore.exists())
        self.assertEqual(tree(self.bundle), before)

    def test_process_loss_leaves_destination_unpublished_and_retries_safely(self):
        crash = """import os, sys
from unittest.mock import patch
from acquisition.adapters.sqlite import workspace_checkpoint as implementation
from acquisition.bootstrap import build_workspace_checkpoint
mode, root, bundle, expected = sys.argv[1:]
checkpoint = build_workspace_checkpoint()
method = 'snapshot_sqlite' if mode == 'create' else 'copy_snapshot'
original = getattr(implementation, method)
def interrupt(*args):
    original(*args)
    os._exit(91)
with patch.object(implementation, method, interrupt):
    if mode == 'create':
        checkpoint.create(root, bundle)
    else:
        checkpoint.restore(bundle, root, expected)
"""
        before = {key: records(self.source / key) for key in ('workspace.sqlite', 'conversations.sqlite', self.campaign)}
        result = self.python(crash, 'create', self.source, self.bundle, '-')
        self.assertEqual(result.returncode, 91, result.stderr)
        self.assertFalse(self.bundle.exists())
        manifest = self.command('create', '--root', self.source, '--bundle', self.bundle)['manifest']
        frozen = tree(self.bundle)
        self.restore.mkdir()
        result = self.python(crash, 'restore', self.restore, self.bundle, manifest['checkpoint_id'])
        self.assertEqual(result.returncode, 91, result.stderr)
        self.assertEqual(list(self.restore.iterdir()), [])
        for partial in self.parent.glob('.acquisition-checkpoint-*'):
            self.assertTrue((partial / MARKER).exists())
            result = self.cli('verify', '--bundle', partial)
            self.assertEqual(result.returncode, 2, result.stdout)
        self.command('restore', '--bundle', self.bundle, '--root', self.restore,
                     '--checkpoint-id', manifest['checkpoint_id'])
        self.assertEqual(tree(self.restore), frozen)
        self.assertEqual(tree(self.bundle), frozen)
        self.assertEqual({key: records(self.source / key) for key in before}, before)
