"""Native channel transactions over the existing application database."""
import hashlib
import json
from math import isfinite

from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.youtube import (CAPABILITY, YouTubeScope, YouTubeError, draft_rows, review_for,
                                 exact_subject, export_bytes, select_contexts, route_youtube, text, authored_draft)
from .admission_guard import verified_required
from .conversations import append_message, scoped_conversation
from .tasks import SqliteTasks, insert_run
from .database import stored_plan_hash
from .execution import require_active


YOUTUBE = """
CREATE TABLE IF NOT EXISTS youtube_revisions(
 organization TEXT NOT NULL, profile TEXT NOT NULL, campaign TEXT NOT NULL,
 revision INTEGER NOT NULL CHECK(revision>0), payload TEXT NOT NULL,
 PRIMARY KEY(organization,profile,campaign,revision));
CREATE TABLE IF NOT EXISTS youtube_requests(
 organization TEXT NOT NULL, actor TEXT NOT NULL, operation TEXT NOT NULL, request TEXT NOT NULL,
 inputs TEXT NOT NULL, receipt TEXT NOT NULL, PRIMARY KEY(organization,actor,operation,request));
CREATE TABLE IF NOT EXISTS youtube_preparations(
 organization TEXT NOT NULL, profile TEXT NOT NULL, id TEXT NOT NULL, conversation TEXT NOT NULL,
 revision INTEGER NOT NULL, run TEXT NOT NULL REFERENCES runs(id), payload TEXT NOT NULL,
 PRIMARY KEY(organization,profile,id), UNIQUE(organization,conversation,revision),
 FOREIGN KEY(organization,conversation) REFERENCES conversations(organization,id));
CREATE TABLE IF NOT EXISTS youtube_interactions(
 organization TEXT NOT NULL, profile TEXT NOT NULL, conversation TEXT NOT NULL, revision INTEGER NOT NULL,
 operation TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(organization,conversation,revision),
 FOREIGN KEY(organization,conversation) REFERENCES conversations(organization,id));
CREATE TABLE IF NOT EXISTS youtube_results(
 organization TEXT NOT NULL, profile TEXT NOT NULL, operation TEXT NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(organization,profile,operation));
CREATE TABLE IF NOT EXISTS youtube_approvals(
 organization TEXT NOT NULL, profile TEXT NOT NULL, id TEXT NOT NULL, campaign TEXT NOT NULL,
 payload TEXT NOT NULL, PRIMARY KEY(organization,profile,id));
CREATE TABLE IF NOT EXISTS youtube_revocations(
 organization TEXT NOT NULL, profile TEXT NOT NULL, approval TEXT NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(organization,profile,approval),
 FOREIGN KEY(organization,profile,approval) REFERENCES youtube_approvals(organization,profile,id));
"""
for _table in ('youtube_revisions', 'youtube_requests', 'youtube_preparations',
               'youtube_interactions', 'youtube_results', 'youtube_approvals', 'youtube_revocations'):
    YOUTUBE += f"""
CREATE TRIGGER IF NOT EXISTS {_table}_no_update BEFORE UPDATE ON {_table}
 BEGIN SELECT RAISE(ABORT,'YouTube history is immutable'); END;
CREATE TRIGGER IF NOT EXISTS {_table}_no_delete BEFORE DELETE ON {_table}
 BEGIN SELECT RAISE(ABORT,'YouTube history is immutable'); END;
"""
    _keys = {
        'youtube_revisions': ('profile', 'campaign', 'revision'),
        'youtube_requests': ('actor', 'operation', 'request'),
        'youtube_preparations': ('profile', 'id'),
        'youtube_interactions': ('conversation', 'revision'),
        'youtube_results': ('profile', 'operation'),
        'youtube_approvals': ('profile', 'id'),
        'youtube_revocations': ('profile', 'approval'),
    }[_table]
    _condition = ' AND '.join(key + '=NEW.' + key for key in ('organization', *_keys))
    YOUTUBE += f"""
CREATE TRIGGER IF NOT EXISTS {_table}_no_replace BEFORE INSERT ON {_table}
 WHEN EXISTS(SELECT 1 FROM {_table} WHERE {_condition})
 BEGIN SELECT RAISE(ABORT,'YouTube history is immutable'); END;
"""
YOUTUBE += 'PRAGMA user_version=25;'


def validate_youtube_schema(db):
    columns = {
        'youtube_revisions': 'organization,profile,campaign,revision,payload',
        'youtube_requests': 'organization,actor,operation,request,inputs,receipt',
        'youtube_preparations': 'organization,profile,id,conversation,revision,run,payload',
        'youtube_interactions': 'organization,profile,conversation,revision,operation,payload',
        'youtube_results': 'organization,profile,operation,payload',
        'youtube_approvals': 'organization,profile,id,campaign,payload',
        'youtube_revocations': 'organization,profile,approval,payload',
    }
    for table, names in columns.items():
        db.execute('SELECT ' + names + ' FROM ' + table + ' LIMIT 0')


class SqliteYouTubeAuthority:
    """Resolve the existing platform actors, without a second role registry."""
    def __init__(self, database, organization, profile, operator, reviewer):
        self.database, self.organization, self.profile = database, organization, profile
        self.operator, self.reviewer = operator, reviewer

    def require(self, scope, actor, operation):
        from .actors import require_actor
        from acquisition.reviews import ActorUnavailable
        if scope.organization != self.organization or scope.profile_id != self.profile:
            raise PermissionError('YouTube scope is unavailable to this operator')
        allowed = {'read': {self.operator, self.reviewer}, 'draft': {self.operator},
                   'approve': {self.reviewer}, 'revoke': {self.reviewer}, 'export': {self.operator}}
        if actor not in allowed.get(operation, set()):
            raise PermissionError('YouTube operation is unavailable to this actor')
        with self.database.connect() as db:
            try:
                require_actor(db, scope.organization, actor, 'operator' if actor == self.operator else 'reviewer')
            except ActorUnavailable as error:
                raise YouTubeError('authority_unavailable', str(error)) from error
            rows = [dict(row) for row in db.execute(
                'SELECT id,roles,enabled,generation FROM review_actors WHERE organization=? AND id IN (?,?) ORDER BY id',
                (scope.organization, self.operator, self.reviewer))]
            # Both current role generations bind every subject, irrespective of
            # which trusted local actor is inspecting or approving it.
            return int(digest(rows), 16)


class SqliteYouTube:
    def __init__(self, database, authority, assets, fixture, clock, compose, *, read_only=False):
        self.database, self.authority, self.assets = database, authority, assets
        self.fixture, self.clock, self.compose, self.read_only = fixture, clock, compose, read_only

    def _guard(self, db, scope, actor, operation, *, mutation=False):
        if not isfinite(self.clock()):
            raise YouTubeError('clock_unavailable', 'A current clock is required for this operation')
        generation = self.authority.require(scope, actor, operation)
        if mutation and (self.read_only or verified_required(db)):
            raise YouTubeError('capability_unavailable', 'YouTube authored preparation is unavailable in an inspection or verified-paused store')
        return generation

    def store_identity(self):
        with self.database.connect() as db:
            return db.execute('SELECT id FROM application_store_identity WHERE singleton=1').fetchone()[0]

    def preview(self, scope, actor, context, fingerprint):
        self.authority.require(scope, actor, 'read')
        if type(context) is not str or context not in self.fixture['contexts']:
            raise NotFound('Bundled comparison unavailable')
        manifest = self.assets.manifest([context])
        content = manifest['comparisons'][context]
        if manifest['blockers'] or digest({key: value for key, value in content.items() if key != 'viewer_path'}) != fingerprint:
            raise YouTubeError('media_unavailable', 'This bundled preview changed or is unavailable')
        return content

    def media(self, scope, actor, name, fingerprint):
        self.authority.require(scope, actor, 'read')
        data = self.assets.media(name)
        if hashlib.sha256(data).hexdigest() != fingerprint:
            raise YouTubeError('media_unavailable', 'This bundled asset changed')
        return data

    @staticmethod
    def _request(db, scope, actor, operation, command):
        row = db.execute('SELECT inputs,receipt FROM youtube_requests WHERE organization=? AND actor=? AND operation=? AND request=?',
                         (scope.organization, actor, operation, command['request_id'])).fetchone()
        if row is not None:
            if row['inputs'] != canonical({'profile': scope.profile_id, 'command': command}):
                raise YouTubeError('request_conflict', 'This request already binds different YouTube inputs')
            return json.loads(row['receipt']) | {'replayed': True}
        return None

    @staticmethod
    def _receipt(db, scope, actor, operation, command, result):
        receipt = {'schema': 'youtube-command-receipt/v1', 'request_id': command['request_id'],
                   'operation': operation, 'result': result}
        db.execute('INSERT INTO youtube_requests VALUES(?,?,?,?,?,?)',
                   (scope.organization, actor, operation, command['request_id'],
                    canonical({'profile': scope.profile_id, 'command': command}), canonical(receipt)))
        return receipt | {'replayed': False}

    def _campaign(self, db, scope, campaign_id):
        row = db.execute('SELECT payload FROM youtube_revisions WHERE organization=? AND profile=? AND campaign=? ORDER BY revision DESC LIMIT 1',
                         (scope.organization, scope.profile_id, campaign_id)).fetchone()
        if row is None:
            raise NotFound('YouTube campaign unavailable in this workspace')
        campaign = json.loads(row['payload'])
        if campaign['context_fingerprint'] != digest(self.fixture):
            raise YouTubeError('context_changed', 'The installed authored context changed; retain this campaign for historical inspection')
        return campaign

    def _review(self, db, scope, actor, campaign):
        generation = self._guard(db, scope, actor, 'read')
        return review_for(scope, campaign, self.assets.manifest(campaign['draft']['contexts']), self.fixture, generation)

    def _approval(self, db, scope, approval_id, campaign_id):
        row = db.execute('SELECT payload FROM youtube_approvals WHERE organization=? AND profile=? AND id=? AND campaign=?',
                         (scope.organization, scope.profile_id, approval_id, campaign_id)).fetchone()
        if row is None:
            raise YouTubeError('approval_required', 'Approve this exact package before exporting')
        approval = json.loads(row['payload'])
        revoked = db.execute('SELECT 1 FROM youtube_revocations WHERE organization=? AND profile=? AND approval=?',
                             (scope.organization, scope.profile_id, approval_id)).fetchone()
        if revoked or approval['expires_at'] <= self.clock():
            raise YouTubeError('approval_revoked', 'This approval was revoked or expired; review the package again')
        return approval

    def read(self, scope, actor, campaign_id):
        with self.database.connect() as db:
            db.execute('BEGIN')
            self._guard(db, scope, actor, 'read')
            campaign = self._campaign(db, scope, campaign_id)
            review = self._review(db, scope, actor, campaign)
            approvals = [json.loads(row[0]) for row in db.execute(
                'SELECT payload FROM youtube_approvals WHERE organization=? AND profile=? AND campaign=? ORDER BY rowid DESC',
                (scope.organization, scope.profile_id, campaign_id))]
            approval = None
            for candidate in approvals:
                if candidate['subject'] == review['subject']:
                    try:
                        approval = self._approval(db, scope, candidate['id'], campaign_id)
                    except YouTubeError:
                        pass
                    if approval is not None:
                        break
            return {'channel': 'youtube', 'campaign': campaign, 'review': review, 'approval': approval,
                    'catalogue': self.fixture['catalogue'], 'context': self.fixture,
                    'mode': 'OFFLINE_AUTHORED', 'hosted_authentication': False}

    def interactions(self, scope, actor, conversation_id):
        with self.database.connect() as db:
            scoped_conversation(db, scope.organization, conversation_id)
            rows = list(db.execute('SELECT * FROM youtube_interactions WHERE organization=? AND profile=? AND conversation=? ORDER BY revision',
                                   (scope.organization, scope.profile_id, conversation_id)))
            if rows:
                self._guard(db, scope, actor, 'read')
            values = []
            for row in rows:
                value = json.loads(row['payload'])
                result = db.execute('SELECT payload FROM youtube_results WHERE organization=? AND profile=? AND operation=?',
                                    (scope.organization, scope.profile_id, row['operation'])).fetchone()
                if result:
                    value.update(json.loads(result[0]))
                elif value.get('run_id'):
                    run = db.execute('SELECT status FROM runs WHERE organization=? AND id=?', (scope.organization, value['run_id'])).fetchone()
                    value['status'] = run['status']
                    if run['status'] in {'failed', 'cancelled'}:
                        value['response'] = 'The authored preparation did not complete. No draft was published.'
                values.append(value)
            return values

    def message(self, scope, actor, command):
        command = json.loads(canonical(command))
        with self.database.transaction() as db:
            self._guard(db, scope, actor, 'read', mutation=True)
            old = self._request(db, scope, actor, 'message', command)
            if old:
                return old
            conversation_id = command['conversation_id']
            scoped_conversation(db, scope.organization, conversation_id)
            prior = list(db.execute('SELECT payload FROM youtube_interactions WHERE organization=? AND profile=? AND conversation=? ORDER BY revision DESC',
                                    (scope.organization, scope.profile_id, conversation_id)))
            route = route_youtube(command['content'], bound=bool(prior))
            if route == 'other':
                raise YouTubeError('capability_unavailable', 'Choose an explicit YouTube request for this command')
            receipt = append_message(db, scope.organization, conversation_id, command['request_id'],
                                     command['expected_revision'], command['content'], self.clock())
            operation = 'yto_' + digest({'scope': [scope.organization, scope.profile_id], 'actor': actor, 'request': command['request_id']})
            value = {'revision': receipt['revision'], 'operation_id': operation, 'status': 'completed',
                     'response': 'Which channel should I prepare: YouTube or the other requested channel?',
                     'campaign_id': None, 'run_id': None, 'activity': ['Read the authored YouTube capability']}
            if route == 'ambiguous':
                value.update(status='waiting', reason_code='channel_ambiguous')
            wants_draft = any(word in command['content'].lower() for word in ('prepare', 'draft', 'create', 'build', 'save'))
            denied = any(word in command['content'].lower() for word in ('do not draft', 'without drafting', 'advice only', 'review only'))
            if route != 'ambiguous':
                contexts = select_contexts(command['content'], self.fixture)
                value['response'] = ('Suggested contexts: ' + ', '.join(self.fixture['contexts'][key]['title'] for key in contexts)
                                     + '. Authored examples only. Allow a placement draft and ask me to prepare it when ready.')
                if command['draft_permission'] == 'instruction_test':
                    value['response'] = 'Instruction-test preparation follows with viewer and learning migration in #133. No draft was created.'
                elif command['draft_permission'] == 'placements' and wants_draft and not denied:
                    self._guard(db, scope, actor, 'draft', mutation=True)
                    latest = db.execute('SELECT payload FROM youtube_results WHERE organization=? AND profile=? AND operation IN '
                        '(SELECT operation FROM youtube_interactions WHERE organization=? AND profile=? AND conversation=?) ORDER BY rowid DESC LIMIT 1',
                        (scope.organization, scope.profile_id, scope.organization, scope.profile_id, conversation_id)).fetchone()
                    campaign_id = json.loads(latest[0])['campaign_id'] if latest else 'ytc_' + digest({'scope': scope.organization, 'profile': scope.profile_id, 'conversation': conversation_id})
                    existing = self._campaign(db, scope, campaign_id) if latest else None
                    frozen = {'command': command, 'actor': actor, 'profile_id': scope.profile_id, 'contexts': contexts,
                              'campaign_id': campaign_id, 'expected_campaign_revision': existing['revision'] if existing else 0,
                              'context_fingerprint': digest(self.fixture), 'source_revision': receipt['revision']}
                    intent = self.compose(scope, operation, frozen)
                    run = insert_run(db, scope.organization, operation, list(intent.tasks), self.clock(),
                                     run_id='run_yt_' + digest({'scope': scope.organization, 'operation': operation}))
                    db.execute('INSERT INTO youtube_preparations VALUES(?,?,?,?,?,?,?)',
                               (scope.organization, scope.profile_id, operation, conversation_id, receipt['revision'], run,
                                canonical({'frozen': frozen, 'admission': intent.payload()})))
                    value.update(run_id=run, status='queued', response='Preparing an authored YouTube placement draft.')
            db.execute('INSERT INTO youtube_interactions VALUES(?,?,?,?,?,?)',
                       (scope.organization, scope.profile_id, conversation_id, receipt['revision'], operation, canonical(value)))
            self._guard(db, scope, actor, 'read', mutation=True)
            return self._receipt(db, scope, actor, 'message', command, {'message_receipt': receipt, 'run_id': value['run_id']})

    def load_operation(self, organization, operation):
        with self.database.connect() as db:
            row = db.execute('SELECT payload FROM youtube_preparations WHERE organization=? AND id=?',
                             (organization, operation)).fetchone()
            if row is None:
                raise NotFound('YouTube preparation unavailable')
            return json.loads(row[0])

    def resume_command(self, scope, actor, operation_id, conversation_id):
        with self.database.connect() as db:
            self._guard(db, scope, actor, 'draft')
            row = db.execute('SELECT payload FROM youtube_preparations WHERE organization=? AND profile=? AND id=? AND conversation=?',
                             (scope.organization, scope.profile_id, operation_id, conversation_id)).fetchone()
            if row is None:
                raise NotFound('YouTube preparation unavailable')
            frozen = json.loads(row[0])['frozen']
            if frozen['actor'] != actor:
                raise NotFound('YouTube preparation unavailable')
            return frozen['command']

    def publish(self, db, claim, outcome):
        row = db.execute('SELECT * FROM youtube_preparations WHERE organization=? AND run=?',
                         (claim.organization, claim.run_id)).fetchone()
        if row is None:
            raise YouTubeError('source_changed', 'YouTube preparation has no native source')
        source = json.loads(row['payload'])
        frozen = source['frozen']
        scope = YouTubeScope(claim.organization, row['profile'])
        self._guard(db, scope, frozen['actor'], 'draft', mutation=True)
        require_active(db, scope.organization, row['conversation'], row['revision'])
        if (source['admission']['tasks'][0]['inputs'] != claim.inputs
                or frozen['context_fingerprint'] != digest(self.fixture)
                or scoped_conversation(db, claim.organization, row['conversation'])['revision'] != row['revision']):
            raise YouTubeError('source_changed', 'The original YouTube request or context changed')
        expected = self.compose(scope, row['id'], frozen)
        if expected.payload() != source['admission'] or frozen['command']['draft_permission'] != 'placements':
            raise YouTubeError('source_changed', 'YouTube admission integrity failed')
        if stored_plan_hash(db, claim.run_id) != digest(source['admission']['tasks']):
            raise YouTubeError('source_changed', 'The runtime plan differs from the admitted YouTube plan')
        current = db.execute('SELECT MAX(revision) FROM youtube_revisions WHERE organization=? AND profile=? AND campaign=?',
                             (scope.organization, scope.profile_id, frozen['campaign_id'])).fetchone()[0] or 0
        if current != frozen['expected_campaign_revision']:
            raise YouTubeError('revision_conflict', 'This campaign changed while preparation was running')
        draft = authored_draft(frozen, self.fixture)
        if outcome.data != {'draft': draft}:
            raise YouTubeError('source_changed', 'Authored preparation returned an unexpected artifact')
        campaign = {'id': frozen['campaign_id'], 'revision': current + 1, 'profile_id': scope.profile_id,
                    'context_id': 'yt_context_' + digest(self.fixture), 'context_fingerprint': digest(self.fixture),
                    'conversation_id': row['conversation'], 'conversation_revision': row['revision'],
                    'draft': draft, 'saved_at': self.clock(), 'actor': frozen['actor']}
        db.execute('INSERT INTO youtube_revisions VALUES(?,?,?,?,?)',
                   (scope.organization, scope.profile_id, campaign['id'], campaign['revision'], canonical(campaign)))
        result = {'status': 'completed', 'campaign_id': campaign['id'], 'campaign_revision': campaign['revision'],
                  'response': 'Prepared an unapproved YouTube placement draft from authored context. Review the exact package below.',
                  'activity': ['Read authored context and catalogue', 'Selected matching contexts',
                               'Validated fictional placement provenance', 'Saved one unapproved revision']}
        db.execute('INSERT INTO youtube_results VALUES(?,?,?,?)', (scope.organization, scope.profile_id, row['id'], canonical(result)))
        self._guard(db, scope, frozen['actor'], 'draft', mutation=True)

    def command(self, scope, actor, operation, command):
        command = json.loads(canonical(command))
        permission = {'save': 'draft', 'approve': 'approve', 'export': 'export', 'revoke': 'revoke'}[operation]
        with self.database.transaction() as db:
            self._guard(db, scope, actor, permission, mutation=True)
            campaign = self._campaign(db, scope, command['campaign_id'])
            review = self._review(db, scope, actor, campaign)
            if operation == 'export':
                exact_subject(review['subject'], command['subject'])
                approval = self._approval(db, scope, command['approval_id'], campaign['id'])
                exact_subject(approval['subject'], command['subject'])
                if review['blockers']:
                    raise YouTubeError('media_unavailable', ' '.join(review['blockers']))
            old = self._request(db, scope, actor, operation, command)
            if old:
                return old
            now = self.clock()
            if operation == 'save':
                if campaign['revision'] != command['expected_revision']:
                    raise YouTubeError('revision_conflict', 'The YouTube draft changed. Reload before editing.')
                draft = command['draft']
                contexts = draft['contexts']
                if (type(contexts) is not list or not contexts or len(contexts) > 2
                        or any(type(key) is not str for key in contexts)
                        or len(set(contexts)) != len(contexts) or any(key not in self.fixture['contexts'] for key in contexts)):
                    raise ValueError('Select installed YouTube comparison contexts')
                draft = {'title': text(draft['title'], 120), 'goal': text(draft['goal'], 500), 'contexts': contexts,
                         'placements': draft_rows(draft['placements'], contexts, self.fixture)}
                if campaign['draft'] != draft:
                    campaign = campaign | {'revision': campaign['revision'] + 1, 'draft': draft, 'saved_at': now, 'actor': actor}
                    db.execute('INSERT INTO youtube_revisions VALUES(?,?,?,?,?)',
                               (scope.organization, scope.profile_id, campaign['id'], campaign['revision'], canonical(campaign)))
                result = {'campaign_id': campaign['id'], 'revision': campaign['revision']}
            elif operation == 'approve':
                exact_subject(review['subject'], command['subject'])
                if review['blockers']:
                    raise YouTubeError('package_incomplete', ' '.join(review['blockers']))
                approval = {'id': 'yta_' + digest({'scope': [scope.organization, scope.profile_id], 'actor': actor,
                                                'request': command['request_id'], 'subject': command['subject']}),
                            'subject': review['subject'], 'actor': actor, 'decision': 'approved',
                            'approved_at': now, 'expires_at': now + 86400, 'payload': review['payload']}
                db.execute('INSERT INTO youtube_approvals VALUES(?,?,?,?,?)',
                           (scope.organization, scope.profile_id, approval['id'], campaign['id'], canonical(approval)))
                result = {'approval_id': approval['id']}
            elif operation == 'revoke':
                approval = self._approval(db, scope, command['approval_id'], campaign['id'])
                db.execute('INSERT INTO youtube_revocations VALUES(?,?,?,?)',
                           (scope.organization, scope.profile_id, approval['id'], canonical({'actor': actor, 'at': now})))
                result = {'revoked': approval['id']}
            else:
                data = export_bytes(approval['payload'], {key: value for key, value in approval.items() if key != 'payload'})
                result = {'filename': 'youtube-' + campaign['id'] + '-r' + str(campaign['revision']) + '.json',
                          'content_type': 'application/json', 'content': data.decode(),
                          'sha256': hashlib.sha256(data).hexdigest()}
            # Fresh native content and authority checks apply even after writes.
            if operation in {'approve', 'export'}:
                exact_subject(self._review(db, scope, actor, campaign)['subject'], command['subject'])
            self._guard(db, scope, actor, permission, mutation=True)
            return self._receipt(db, scope, actor, operation, command, result)


class SqliteYouTubeTasks(SqliteTasks):
    def __init__(self, database, store, clock):
        super().__init__(database, execution_clock=clock)
        self.youtube_store = store

    def settle(self, claim, outcome, now):
        with self.database.transaction() as db:
            self._owned(db, claim, self.execution_clock())
            if claim.capability != CAPABILITY or outcome.status != 'succeeded':
                raise YouTubeError('source_changed', 'Unsupported YouTube task settlement')
            self.youtube_store.publish(db, claim, outcome)
            self.settle_in_transaction(db, claim, outcome, self.execution_clock())
