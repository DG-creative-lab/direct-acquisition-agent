"""The real guarded HTTP path returns the same native draft/review/export state."""
import hashlib
import http.client
import json
import os
import subprocess
import sys
from urllib.parse import urlsplit
from unittest.mock import patch
import unittest

from acquisition.bootstrap import build_workspace, build_youtube, build
from acquisition.youtube import YouTubeError
import test_workspace as workspace_tests


class WorkspaceYouTubeHttpTests(unittest.TestCase):
    setUp = workspace_tests.WorkspaceHttpTests.setUp
    stop = workspace_tests.WorkspaceHttpTests.stop

    def request(self, path, payload=None, headers=None):
        headers = dict(headers or {})
        if payload is not None:
            headers.setdefault('X-YouTube-Store', self.server.workspace.youtube.campaigns.store_identity())
        return workspace_tests.WorkspaceHttpTests.request(self, path, payload, headers)

    def start(self):
        status, raw, _ = self.request('/api/conversations', {'request_id': 'chat', 'title': 'YouTube brief'})
        self.assertEqual(status, 200, raw)
        self.conversation = json.loads(raw)['id']
        self.message = {'request_id': 'message', 'expected_revision': 0,
                        'content': 'Prepare YouTube placements for video editing', 'draft_permission': 'placements'}
        status, raw, _ = self.request('/api/conversations/' + self.conversation + '/youtube-messages', self.message)
        self.assertEqual(status, 200, raw)
        self.campaign = json.loads(raw)['youtube_interactions'][0]['campaign_id']
        status, raw, _ = self.request('/api/youtube/campaigns/' + self.campaign)
        self.assertEqual(status, 200, raw)
        return json.loads(raw)

    def test_browser_command_path_preserves_exact_export_and_real_media_links(self):
        view = self.start()
        approval_command = {'request_id': 'approve', 'campaign_id': self.campaign, 'subject': view['review']['subject']}
        status, raw, _ = self.request('/api/youtube/approve', approval_command)
        self.assertEqual(status, 200, raw)
        approval = json.loads(raw)['approval']
        command = {'request_id': 'export', 'campaign_id': self.campaign, 'subject': view['review']['subject'],
                   'approval_id': approval['id']}
        status, raw, headers = self.request('/api/youtube/export', command)
        self.assertEqual(status, 200, raw)
        self.assertEqual(headers['Cache-Control'], 'no-store')
        data = json.loads(raw)['command_receipt']['result']
        self.assertEqual(hashlib.sha256(data['content'].encode()).hexdigest(), data['sha256'])
        artifact = json.loads(data['content'])
        self.assertEqual(artifact['payload'], view['review']['payload'])
        group = artifact['payload']['package']['groups'][0]
        for url, expected_type in ((group['viewer_path'], 'text/html'), (group['content']['takes'][0]['url'], 'video/mp4')):
            parsed = urlsplit(url)
            self.assertEqual(parsed.netloc, urlsplit(self.base).netloc)
            status, body, response_headers = self.request(parsed.path + '?' + parsed.query)
            self.assertEqual(status, 200, body[:100])
            self.assertTrue(response_headers['Content-Type'].startswith(expected_type))
            if expected_type == 'text/html':
                self.assertIn(b'No playback or choice events are collected', body)
        self.assertEqual(self.request('/api/youtube/campaigns/' + self.campaign, headers={'X-Workspace-Token': ''})[0], 403)
        self.assertEqual(self.request('/youtube/media/unknown?sha256=' + '0'*64)[0], 409)

    def test_lost_message_and_approval_response_replay_original_durable_results(self):
        conversation = self.server.workspace.create_conversation('chat', 'YouTube')['id']
        path = '/api/conversations/' + conversation + '/youtube-messages'
        message = {'request_id': 'message', 'expected_revision': 0, 'content': 'Prepare YouTube placements',
                   'draft_permission': 'placements'}
        with patch.object(self.server.workspace, 'conversation', side_effect=OSError('Lost response')):
            self.assertEqual(self.request(path, message)[0], 500)
        status, raw, _ = self.request(path, message)
        self.assertEqual(status, 200, raw)
        result = json.loads(raw)
        self.assertEqual(result['revision'], 1)
        self.assertEqual(len(result['youtube_interactions']), 1)
        campaign = result['youtube_interactions'][0]['campaign_id']
        app = self.server.workspace.youtube.campaigns
        view = app.read(campaign)
        approve = {'request_id': 'approve', 'campaign_id': campaign, 'subject': view['review']['subject']}
        with patch.object(app, 'read', side_effect=OSError('Lost approval response')):
            self.assertEqual(self.request('/api/youtube/approve', approve)[0], 500)
        status, raw, _ = self.request('/api/youtube/approve', approve)
        self.assertEqual(status, 200, raw)
        self.assertTrue(json.loads(raw)['command_receipt']['replayed'])
        with app.store.database.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM youtube_revisions').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count(*) FROM youtube_approvals').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count(*) FROM model_calls').fetchone()[0], 0)

    def test_scope_headers_funding_and_duplicate_json_are_denied_without_effect(self):
        conversation = self.server.workspace.create_conversation('chat', 'YouTube')['id']
        path = '/api/conversations/' + conversation + '/youtube-messages'
        message = {'request_id': 'message', 'expected_revision': 0, 'content': 'Prepare YouTube placements',
                   'draft_permission': 'placements'}
        for header in ({'Host': 'attacker.invalid'}, {'Origin': 'https://attacker.invalid'},
                       {'X-Workspace-Token': ''}):
            self.assertEqual(self.request(path, message, header)[0], 403)
        for field in ('organization', 'actor', 'model', 'role', 'funding'):
            self.assertEqual(self.request(path, message | {field: 'forged'})[0], 400)
        for header in ({'Authorization': 'Bearer rejected-test-key'}, {'X-OpenRouter-Handle': 'rejected'},
                       {'X-OpenRouter-Session': 'rejected'}):
            self.assertEqual(self.request(path, message, header)[0], 400)
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        body = json.dumps(message)[:-1] + ',"draft_permission":"none"}'
        conn.request('POST', path, body, {'Content-Type': 'application/json', 'Origin': self.base,
            'X-Workspace-Token': self.server.token, 'X-YouTube-Store': self.server.workspace.youtube.campaigns.store_identity()})
        response = conn.getresponse()
        self.assertEqual(response.status, 400, response.read())
        conn.close()
        current = self.server.workspace.conversation(conversation)
        self.assertEqual(current['revision'], 0)
        self.assertEqual(current['youtube_interactions'], [])

    def test_original_store_identity_and_foreign_ids_cannot_be_retargeted(self):
        view = self.start()
        original = self.server.workspace
        store = original.youtube.campaigns.store_identity()
        command = {'request_id': 'approve', 'campaign_id': self.campaign, 'subject': view['review']['subject']}
        replacement = build_workspace(self.root / 'other')
        self.server.workspace = self.server._http.workspace = replacement
        status, raw, _ = self.request('/api/youtube/approve', command, {'X-YouTube-Store': store})
        self.assertEqual(status, 409, raw)
        self.assertEqual(json.loads(raw)['code'], 'store_mismatch')
        self.server.workspace = self.server._http.workspace = original
        foreign_db = self.root / 'data' / 'conversations.sqlite'
        native = build(foreign_db)
        conversation = native.conversations.create('foreign', 'chat', 'Private')['id']
        foreign = build_youtube(foreign_db, organization='foreign')
        foreign.message({'request_id': 'message', 'conversation_id': conversation, 'expected_revision': 0,
                         'content': 'Prepare YouTube placements', 'draft_permission': 'placements'})
        campaign = foreign.campaigns.interactions(conversation)[0]['campaign_id']
        self.assertEqual(self.request('/api/youtube/campaigns/' + campaign)[0], 404)
        self.assertIsNone(original.youtube.campaigns.read(self.campaign)['approval'])

    def test_existing_message_and_followup_routes_keep_youtube_out_of_postal_validation(self):
        conversation = self.server.workspace.create_conversation('route','YouTube')['id']
        status, raw, _ = self.request('/api/conversations/' + conversation + '/messages',
            {'request_id':'message','expected_revision':0,'content':'Suggest YouTube contexts for a video editor'})
        self.assertEqual(status,200,raw)
        view = json.loads(raw)
        self.assertEqual(view['youtube_interactions'][0]['status'],'completed')
        self.assertEqual(view['plans'],[])
        status, raw, _ = self.request('/api/conversations/' + conversation + '/actions',
            {'request_id':'followup','expected_revision':1,'content':'Prepare the same YouTube contexts','allow_model_copy':True})
        self.assertEqual(status,202,raw)
        view = json.loads(raw)
        self.assertIsNone(view['youtube_interactions'][-1]['campaign_id'])
        self.assertEqual(view['actions'],[])
        self.assertEqual(view['plans'],[])

    def test_stale_message_is_definitely_rejected_but_post_commit_failure_stays_unknown(self):
        self.start()
        path = '/api/conversations/' + self.conversation + '/youtube-messages'
        stale = self.message | {'request_id': 'stale'}
        status, raw, _ = self.request(path, stale)
        self.assertEqual(status, 409, raw)
        self.assertTrue(json.loads(raw)['message_not_saved'])
        current = stale | {'request_id': 'next', 'expected_revision': 1}
        with patch.object(self.server.workspace.youtube.worker, 'drain', side_effect=RuntimeError('Lost worker reply')):
            status, raw, _ = self.request(path, current)
            self.assertEqual(status, 500, raw)
            self.assertNotIn('message_not_saved', json.loads(raw))
        status, raw, _ = self.request(path, current)
        self.assertEqual(status, 200, raw)
        self.assertEqual(json.loads(raw)['revision'], 2)
        self.assertEqual(len(json.loads(raw)['youtube_interactions']), 2)

    def test_shared_reviewer_disable_and_reenable_cannot_renew_cached_youtube_approval(self):
        # Capability construction, store reads and unrelated chat inspection are
        # read-only. Local actor defaults belong to an explicit YouTube use.
        app = self.server.workspace.youtube.campaigns
        with app.store.database.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM review_actors').fetchone()[0], 0)
        c = self.server.workspace.create_conversation('inspect', 'Inspect only')['id']
        self.server.workspace.conversation(c)
        self.request('/api/youtube/store')
        with app.store.database.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM review_actors').fetchone()[0], 0)
        view = self.start()
        app = self.server.workspace.youtube.campaigns
        command = {'request_id': 'approved', 'campaign_id': self.campaign, 'subject': view['review']['subject']}
        status, raw, _ = self.request('/api/youtube/approve', command)
        self.assertEqual(status, 200, raw)
        approval = json.loads(raw)['approval']
        self.assertEqual(approval['actor'], 'local-reviewer')
        export = {'request_id': 'exported', 'campaign_id': self.campaign, 'subject': view['review']['subject'], 'approval_id': approval['id']}
        self.assertEqual(self.request('/api/youtube/export', export)[0], 200)
        roles = build(app.store.database.path).reviews.store
        roles.register_actor('local-conversations', 'local-reviewer', ('reviewer',), False)
        self.assertIsNone(app.read(self.campaign)['approval'])
        self.assertEqual(self.request('/api/youtube/export', export)[0], 409)
        current = app.read(self.campaign)
        status, raw, _ = self.request('/api/youtube/approve', command | {'request_id': 'disabled', 'subject': current['review']['subject']})
        self.assertEqual(status, 409, raw)
        self.assertEqual(json.loads(raw)['code'], 'authority_unavailable')
        # A new composition must retain administration, rather than reset a RAM grant.
        reopened = build_youtube(app.store.database.path, origin=self.base).campaigns
        self.assertIsNone(reopened.read(self.campaign)['approval'])
        child = subprocess.run([sys.executable, '-c',
            "import json,sys;from acquisition.bootstrap import build_youtube;app=build_youtube(sys.argv[1],origin=sys.argv[3],read_only=True);print(json.dumps(app.campaigns.read(sys.argv[2])['approval']))",
            str(app.store.database.path), self.campaign, self.base],
            env=dict(os.environ, PYTHONPATH='src'), capture_output=True, text=True, timeout=20)
        self.assertEqual(child.returncode, 0, child.stderr)
        self.assertIsNone(json.loads(child.stdout))
        roles.register_actor('local-conversations', 'local-reviewer', ('reviewer',), True)
        self.assertIsNone(reopened.read(self.campaign)['approval'])
        with self.assertRaises(YouTubeError) as rejected:
            reopened.command('export', export)
        self.assertIn('changed', str(rejected.exception))
        fresh = reopened.read(self.campaign)
        reopened.command('approve', command | {'request_id': 'fresh', 'subject': fresh['review']['subject']})
        self.assertIsNotNone(reopened.read(self.campaign)['approval'])
