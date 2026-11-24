"""Native command invariants with real SQLite, leases and fresh-process reads."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from acquisition.bootstrap import build, build_youtube, build_admissions
from acquisition.contracts import Conflict, NotFound
from acquisition.adapters.youtube_fixture import LocalYouTubeAuthority, BundledComparisonAssets
from acquisition.youtube import YouTubeError, YouTubeTools
from acquisition.workflows.youtube_preparation import AuthoredYouTubeHandler


class YouTubeFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = self.enterContext(TemporaryDirectory())
        self.root = Path(self.temp)
        self.db = self.root / 'application.sqlite'
        self.now = [1795543200.]
        self.clock = lambda: self.now[0]
        self.authority = LocalYouTubeAuthority('A')
        self.media = self.root / 'media'
        shutil.copytree(Path('examples/youtube-media'), self.media)
        self.assets = BundledComparisonAssets(self.media, 'http://127.0.0.1:8768')
        self.app = self.open()
        self.native = build(self.db, clock=self.clock)
        self.conversation = self.native.conversations.create('A', 'chat', 'YouTube brief')['id']

    def open(self, **kwargs):
        return build_youtube(self.db, self.clock, organization='A', authority=self.authority, assets=self.assets, **kwargs)

    def prepare(self, request='message', content='Prepare YouTube placements for video editors and audiobook narrators.', permission='placements'):
        self.message = {'request_id': request, 'conversation_id': self.conversation, 'expected_revision': 0,
                        'content': content, 'draft_permission': permission}
        self.receipt = self.app.message(self.message)
        row = self.app.campaigns.interactions(self.conversation)[-1]
        self.campaign = row['campaign_id']
        return self.app.campaigns.read(self.campaign) if self.campaign else row

    def approve(self, view, request='approve'):
        command = {'request_id': request, 'campaign_id': self.campaign, 'subject': view['review']['subject']}
        result = self.app.campaigns.command('approve', command)
        return result['result']['approval_id'], command

    def export(self, view, approval, request='export'):
        command = {'request_id': request, 'campaign_id': self.campaign,
                   'subject': view['review']['subject'], 'approval_id': approval}
        return self.app.campaigns.command('export', command), command

    def count(self, table):
        with self.app.campaigns.store.database.connect() as db:
            return db.execute('SELECT count(*) FROM ' + table).fetchone()[0]

    def test_prepare_review_edit_approve_exact_export_and_restart(self):
        view = self.prepare()
        self.assertEqual(view['campaign']['revision'], 1)
        self.assertIsNone(view['approval'])
        self.assertEqual(len(view['campaign']['draft']['placements']), 4)
        self.assertEqual(view['review']['blockers'], [])
        with self.assertRaisesRegex(YouTubeError, 'Approve this exact'):
            self.export(view, 'unknown')
        draft = view['campaign']['draft'] | {'title': 'Reviewed YouTube experiment'}
        save = {'request_id': 'edit', 'campaign_id': self.campaign, 'expected_revision': 1, 'draft': draft}
        self.app.campaigns.command('save', save)
        view = self.app.campaigns.read(self.campaign)
        self.assertEqual(view['campaign']['revision'], 2)
        approval, _ = self.approve(view)
        exported, command = self.export(view, approval)
        blob = exported['result']['content']
        artifact = json.loads(blob)
        self.assertEqual(artifact['schema'], 'youtube-manual-export/v1')
        self.assertEqual(artifact['payload'], view['review']['payload'])
        self.assertEqual(artifact['review_receipt']['subject'], view['review']['subject'])
        self.assertEqual(artifact['payload']['package']['revision'], 2)
        self.assertEqual(artifact['payload']['package']['groups'][0]['placements'][0]['label'], 'Fictional placement')
        reopened = self.open()
        self.assertEqual(reopened.campaigns.command('export', command)['result']['content'], blob)
        self.assertEqual(self.count('youtube_revisions'), 2)
        self.assertEqual(self.count('youtube_approvals'), 1)
        for table in ('model_calls', 'drafts', 'review_decisions', 'simulated_agency_jobs'):
            self.assertEqual(self.count(table), 0, table)
        child = subprocess.run([sys.executable, '-c',
            "import json,sys;from acquisition.bootstrap import build_youtube;from acquisition.adapters.youtube_fixture import LocalYouTubeAuthority;app=build_youtube(sys.argv[1],lambda:1795543200.,organization='A',authority=LocalYouTubeAuthority('A'),read_only=True);print(json.dumps(app.campaigns.read(sys.argv[2])['campaign']))",
            str(self.db), self.campaign], env=dict(os.environ, PYTHONPATH='src'),
            capture_output=True, text=True, timeout=20)
        self.assertEqual(child.returncode, 0, child.stderr)
        self.assertEqual(json.loads(child.stdout), view['campaign'])

    def test_permission_routing_and_tools_make_no_unapproved_writes(self):
        row = self.prepare(permission='none')
        self.assertEqual(row['status'], 'completed')
        self.assertIsNone(row['campaign_id'])
        self.assertEqual(self.count('youtube_revisions'), 0)
        self.assertEqual(self.count('runs'), 0)
        with self.assertRaises(YouTubeError):
            YouTubeTools(self.app.campaigns).save_placement_draft({})
        other = self.native.conversations.create('A', 'ambiguous', 'Ambiguous')['id']
        self.app.message(self.message | {'request_id': 'ambiguous', 'conversation_id': other,
            'content': 'Prepare YouTube and email campaigns', 'draft_permission': 'placements'})
        self.assertIn('Which channel', self.app.campaigns.interactions(other)[0]['response'])
        self.assertEqual(self.count('runs'), 0)

    def test_exact_replay_and_new_key_cannot_double_publish_same_revision(self):
        view = self.prepare()
        self.assertTrue(self.app.message(self.message)['replayed'])
        self.assertEqual(self.count('youtube_revisions'), 1)
        with self.assertRaises(Conflict):
            self.app.message(self.message | {'content': 'Prepare YouTube audiobook placements'})
        with self.assertRaises(Conflict):
            self.app.message(self.message | {'request_id': 'different-key'})
        approval, command = self.approve(view)
        self.assertEqual(self.app.campaigns.command('approve', command)['result']['approval_id'], approval)
        self.assertEqual(self.count('youtube_approvals'), 1)

    def test_stale_subject_media_delivery_revocation_and_expiry_block_export_replay(self):
        view = self.prepare()
        approval, _ = self.approve(view)
        _, export = self.export(view, approval)
        original = self.assets.origin
        self.assets.origin = 'http://127.0.0.1:9999'
        with self.assertRaisesRegex(YouTubeError, 'changed'):
            self.app.campaigns.command('export', export)
        self.assets.origin = original
        self.media.joinpath('editing-a.mp4').write_bytes(b'changed')
        with self.assertRaisesRegex(YouTubeError, 'changed'):
            self.app.campaigns.command('export', export)
        shutil.copyfile(Path('examples/youtube-media/editing-a.mp4'), self.media / 'editing-a.mp4')
        self.app.campaigns.command('revoke', {'request_id': 'revoke', 'campaign_id': self.campaign, 'approval_id': approval})
        with self.assertRaisesRegex(YouTubeError, 'revoked'):
            self.app.campaigns.command('export', export)
        self.assertIsNone(self.app.campaigns.read(self.campaign)['approval'])
        new, _ = self.approve(view, 'approve-again')
        self.now[0] += 86401
        with self.assertRaisesRegex(YouTubeError, 'expired'):
            self.export(view, new, 'expired-export')

    def test_foreign_campaign_and_approval_are_not_accepted(self):
        view = self.prepare()
        native = build(self.db, clock=self.clock)
        conversation = native.conversations.create('B', 'chat', 'Foreign')['id']
        other = build_youtube(self.db, self.clock, organization='B')
        other.message(self.message | {'conversation_id': conversation})
        row = other.campaigns.interactions(conversation)[0]
        foreign = other.campaigns.read(row['campaign_id'])
        receipt = other.campaigns.command('approve', {'request_id': 'approve', 'campaign_id': row['campaign_id'],
                                                    'subject': foreign['review']['subject']})
        with self.assertRaises(NotFound):
            self.app.campaigns.read(row['campaign_id'])
        with self.assertRaises(YouTubeError):
            self.export(view, receipt['result']['approval_id'])
        self.assertEqual(self.count('youtube_requests'), 3)  # Two messages and the foreign approval only.

    def test_approval_write_rolls_back_and_identical_retry_saves_once(self):
        view = self.prepare()
        real = self.authority.require
        calls = []
        def fail_at_commit(scope, actor, operation):
            if operation == 'approve':
                calls.append(operation)
                if len(calls) == 2:
                    raise OSError('Injected failure before commit')
            return real(scope, actor, operation)
        with patch.object(self.authority, 'require', side_effect=fail_at_commit):
            with self.assertRaisesRegex(OSError, 'Injected'):
                self.approve(view)
        self.assertEqual(self.count('youtube_approvals'), 0)
        self.assertIsNone(self.open().campaigns.read(self.campaign)['approval'])
        self.approve(view)
        self.assertEqual(self.count('youtube_approvals'), 1)

    def test_concurrent_edits_and_noop_save_preserve_revision_and_approval_identity(self):
        view = self.prepare()
        self.approve(view)
        base = {'campaign_id': self.campaign, 'expected_revision': 1, 'draft': view['campaign']['draft']}
        noop = self.app.campaigns.command('save', base | {'request_id': 'noop'})
        self.assertEqual(noop['result']['revision'], 1)
        def save(name):
            try:
                return self.app.campaigns.command('save', base | {'request_id': name,
                    'draft': base['draft'] | {'title': name}})
            except Conflict:
                return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(save, ['first', 'second']))
        self.assertEqual(results.count('conflict'), 1)
        self.assertEqual(self.count('youtube_revisions'), 2)
        self.assertIsNone(self.app.campaigns.read(self.campaign)['approval'])
        with self.assertRaises(YouTubeError):
            self.approve(view, 'stale-approval')

    def test_forged_catalogue_and_incomplete_package_cannot_be_approved(self):
        view = self.prepare()
        draft = view['campaign']['draft']
        base = {'request_id': 'edit', 'campaign_id': self.campaign, 'expected_revision': 1}
        wrong = dict(draft['placements'][0], title='Invented provenance')
        with self.assertRaises(YouTubeError):
            self.app.campaigns.command('save', base | {'draft': draft | {'placements': [wrong]}})
        self.app.campaigns.command('save', base | {'draft': draft | {'placements': []}})
        latest = self.app.campaigns.read(self.campaign)
        self.assertEqual(len(latest['review']['blockers']), 2)
        with self.assertRaisesRegex(YouTubeError, 'Add placements'):
            self.approve(latest)
        self.assertEqual(self.count('youtube_approvals'), 0)

    def test_cancelled_superseded_or_expired_task_cannot_publish(self):
        command = {'request_id': 'pending', 'conversation_id': self.conversation, 'expected_revision': 0,
                   'content': 'Prepare YouTube placements', 'draft_permission': 'placements'}
        receipt = self.app.campaigns.message(command)
        claim = self.app.tasks.claim('A', self.clock(), 60, run_id=receipt['result']['run_id'])
        handler = AuthoredYouTubeHandler(self.app.campaigns.store, self.app.campaigns.store.fixture)
        output = handler.prepare(claim)
        self.native.conversations.message('A', self.conversation, 'new-message', 1, 'Stop the previous request')
        with self.assertRaises(YouTubeError):
            self.app.tasks.settle(claim, output, self.clock())
        self.assertEqual(self.count('youtube_revisions'), 0)
        self.assertEqual(self.count('youtube_results'), 0)
        self.now[0] += 61
        from acquisition.runtime import LeaseLost
        with self.assertRaises(LeaseLost):
            self.app.tasks.settle(claim, output, self.clock())
        self.assertEqual(self.count('youtube_revisions'), 0)

    def test_verified_pause_read_only_and_revoked_authority_preserve_fences(self):
        view = self.prepare()
        with self.assertRaises(YouTubeError):
            self.open(read_only=True).campaigns.command('save', {'request_id': 'read-only', 'campaign_id': self.campaign,
                'expected_revision': 1, 'draft': view['campaign']['draft']})
        self.authority.enabled = False
        with self.assertRaises(PermissionError):
            self.app.campaigns.read(self.campaign)
        self.authority.enabled = True
        build_admissions(self.db, self.clock, verified_admissions=True)
        with self.assertRaises(YouTubeError):
            self.app.message(self.message | {'request_id': 'paused', 'expected_revision': 1})
        self.assertEqual(self.count('youtube_revisions'), 1)
        self.assertEqual(self.native.conversations.store.snapshot('A', self.conversation)['revision'], 1)

    def test_plain_workspace_worker_cannot_steal_youtube_preparation(self):
        command = {'request_id': 'pending', 'conversation_id': self.conversation, 'expected_revision': 0,
                   'content': 'Prepare YouTube placements', 'draft_permission': 'placements'}
        receipt = self.app.campaigns.message(command)
        self.assertEqual(self.native.worker.drain('A'), 0)
        self.app.worker.drain('A', run_id=receipt['result']['run_id'])
        self.assertEqual(self.count('youtube_revisions'), 1)

    def test_expired_local_claim_resumes_original_operation_and_stop_blocks_publication(self):
        command = {'request_id':'pending','conversation_id':self.conversation,'expected_revision':0,
                   'content':'Prepare YouTube placements','draft_permission':'placements'}
        receipt = self.app.campaigns.message(command)
        operation = self.app.campaigns.interactions(self.conversation)[0]['operation_id']
        self.app.tasks.claim('A',self.clock(),60,run_id=receipt['result']['run_id'])
        self.now[0] += 61
        self.app.resume(operation,self.conversation)
        self.app.resume(operation,self.conversation)
        self.assertEqual(self.count('youtube_revisions'),1)
        self.assertEqual(self.count('runs'),1)
        self.assertEqual(self.native.conversations.store.snapshot('A',self.conversation)['revision'],1)
        other = self.native.conversations.create('A','stop-chat','Stop test')['id']
        receipt = self.app.campaigns.message(command | {'request_id':'stop-pending','conversation_id':other})
        claim = self.app.tasks.claim('A',self.clock(),60,run_id=receipt['result']['run_id'])
        handler = AuthoredYouTubeHandler(self.app.campaigns.store,self.app.campaigns.store.fixture)
        result = handler.prepare(claim)
        self.native.execution.stop('A',other,'stop',1)
        with self.assertRaisesRegex(Conflict,'stopped'):
            self.app.tasks.settle(claim,result,self.clock())
        self.assertEqual(self.count('youtube_revisions'),1)

    def test_native_history_rejects_replace_and_export_receipt_failure_rolls_back(self):
        view = self.prepare()
        approval, _ = self.approve(view)
        with self.app.campaigns.store.database.transaction() as db:
            db.execute("CREATE TRIGGER fail_export BEFORE INSERT ON youtube_requests WHEN NEW.operation='export' BEGIN SELECT RAISE(ABORT,'fail export'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.export(view, approval)
        with self.app.campaigns.store.database.transaction() as db:
            db.execute('DROP TRIGGER fail_export')
        exported, command = self.export(view, approval)
        self.assertEqual(self.open().campaigns.command('export', command)['result'], exported['result'])
        with self.assertRaises(sqlite3.IntegrityError):
            with self.app.campaigns.store.database.transaction() as db:
                db.execute('INSERT OR REPLACE INTO youtube_approvals SELECT * FROM youtube_approvals LIMIT 1')

    def test_schema24_upgrade_rolls_back_and_preserves_existing_history(self):
        from acquisition.adapters.sqlite.database import Database
        from acquisition.adapters.sqlite.youtube import YOUTUBE
        # Reconstruct a genuine schema-24 store by omitting the additive migration.
        path = self.root / 'schema24.sqlite'
        with patch('acquisition.adapters.sqlite.youtube.YOUTUBE', ''), patch('acquisition.adapters.sqlite.youtube.validate_youtube_schema'):
            old = build(path, clock=self.clock)
            chat = old.conversations.create('A', 'old-chat', 'Preserved conversation')['id']
            old.conversations.message('A', chat, 'old-message', 0, 'Preserved original brief')
        with sqlite3.connect(path) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 24)
            before = db.execute('SELECT * FROM conversation_messages').fetchall()
        with patch('acquisition.adapters.sqlite.youtube.YOUTUBE', YOUTUBE.replace('PRAGMA user_version=25;', 'SELECT * FROM missing_migration_table;')):
            with self.assertRaises(sqlite3.OperationalError):
                Database(path)
        with sqlite3.connect(path) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 24)
            self.assertEqual(db.execute("SELECT name FROM sqlite_schema WHERE name LIKE 'youtube_%'").fetchall(), [])
            self.assertEqual(db.execute('SELECT * FROM conversation_messages').fetchall(), before)
        Database(path)
        with sqlite3.connect(path) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 25)
            self.assertEqual(db.execute('SELECT * FROM conversation_messages').fetchall(), before)
