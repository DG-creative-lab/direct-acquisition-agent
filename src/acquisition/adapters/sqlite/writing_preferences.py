"""Immutable editorial decisions. Each version is its own effect, audit and receipt."""
import json
import math

from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.creative import writing_preference
from .actors import require_actor
from .drafts import read_draft


def versions(db, organization):
    # Schema-14 cold restores remain readable without migration or writes.
    if db.execute("SELECT 1 FROM sqlite_schema WHERE name='writing_preference_versions'").fetchone() is None:
        if db.execute('PRAGMA user_version').fetchone()[0] >= 15:
            raise Conflict('Writing preference history is unavailable')
        return []
    return [json.loads(row[0]) for row in db.execute(
        'SELECT payload FROM writing_preference_versions WHERE organization=? ORDER BY rowid', (organization,))]


def preferences(db, organization):
    result = {}
    for item in versions(db, organization):
        result.pop(item['id'], None)
        result[item['id']] = item
    return list(reversed(list(result.values())))


def source_comment(db, organization, source_organization, conversation_id, comment_id):
    if db.execute('SELECT 1 FROM conversations WHERE organization=? AND id=?',
                  (organization, conversation_id)).fetchone() is None:
        raise NotFound('Source conversation not found in this organization')
    row = db.execute('SELECT receipt,request_hash FROM review_commands WHERE organization=? AND request_id=?',
                     (source_organization, comment_id)).fetchone()
    if row is None:
        raise NotFound('Saved copy comment not found')
    comment = json.loads(row[0])
    if comment.get('kind') != 'artifact_comment' or comment.get('conversation_id') != conversation_id:
        raise Conflict('Select a saved copy comment from this conversation')
    inputs = dict(case_id=comment['case_id'], expected_subject=comment['subject_id'], target_id=comment['target_id'],
                  conversation_id=conversation_id, expected_revision=comment['conversation_revision'], feedback=comment['feedback'])
    if (comment.get('request_id') != comment_id
            or digest({'actor': comment['actor'], 'kind': 'artifact_comment', 'payload': inputs}) != row['request_hash']):
        raise Conflict('The comment differs from its original saved request')
    event = db.execute("SELECT payload FROM review_events WHERE organization=? AND case_id=? AND kind='artifact_commented'",
                       (source_organization, comment['case_id'])).fetchall()
    if not any(json.loads(item[0]) == comment for item in event):
        raise Conflict('The saved comment is missing its audit evidence')
    draft = read_draft(db, source_organization, comment['draft_id'])
    brief = draft.manifest['brief']
    creative = next((c for c in draft.manifest['creatives'] if c['id'] == comment['target_id']), None)
    subject = db.execute('SELECT payload FROM review_subjects WHERE organization=? AND id=?',
                         (source_organization, comment['subject_id'])).fetchone()
    proposal = json.loads(subject[0]) if subject else {}
    if (proposal.get('id') != comment['subject_id']
            or 'subject_' + digest({k: v for k, v in proposal.items() if k != 'id'}) != comment['subject_id']
            or proposal.get('draft_id') != draft.id or proposal.get('case_id') != comment['case_id']
            or proposal.get('revision') != comment['subject_revision']
            or brief.get('conversation_id') != conversation_id
            or brief.get('conversation_revision') != comment['conversation_revision']
            or creative is None or (creative['segment'], creative['arm']) != (comment['segment'], comment['arm'])):
        raise Conflict('The comment differs from its original copy provenance')
    return comment


def change_preference(database, organization, source_organization, conversation_id, comment_id,
                      preference_id, action, expected_revision, segments, preferred, avoid, reason,
                      confirmed, actor, request_id, now):
    guidance = writing_preference(action, expected_revision, segments, preferred, avoid, reason, confirmed)
    for key in (organization, source_organization, conversation_id, comment_id, actor, request_id):
        if type(key) is not str or not 1 <= len(key) <= 160 or not key.isprintable():
            raise ValueError('Use bounded preference identities')
    if type(preference_id) is not str or len(preference_id) > 160 or not math.isfinite(now):
        raise ValueError('Invalid preference identity or time')
    inputs = dict(source_organization=source_organization, conversation_id=conversation_id, comment_id=comment_id,
                  preference_id=preference_id, action=action, expected_revision=expected_revision,
                  segments=segments, preferred=preferred, avoid=avoid, reason=reason, confirmed=confirmed, actor=actor)
    fingerprint = digest(inputs)
    with database.transaction() as db:
        require_actor(db, source_organization, actor, 'operator')
        cached = db.execute('SELECT fingerprint,payload FROM writing_preference_versions WHERE organization=? AND request_id=?',
                            (organization, request_id)).fetchone()
        if cached:
            if cached['fingerprint'] != fingerprint:
                raise Conflict('Preference request already binds different inputs')
            return json.loads(cached['payload'])
        source = source_comment(db, organization, source_organization, conversation_id, comment_id)
        identity = 'preference_' + digest({'organization': organization, 'source_organization': source_organization,
                                           'comment_id': comment_id})
        old = db.execute('SELECT payload FROM writing_preference_versions WHERE organization=? AND id=? ORDER BY revision DESC LIMIT 1',
                         (organization, identity)).fetchone()
        previous = json.loads(old[0]) if old else None
        if previous is not None and previous['source'] != source:
            raise Conflict('The original preference source changed')
        if action == 'confirm':
            if preference_id or expected_revision != 0 or previous:
                raise Conflict('This comment already has a writing preference; correct its current version')
        elif (previous is None or preference_id != identity or previous['revision'] != expected_revision
              or previous['status'] != 'active'):
            raise Conflict('The writing preference changed; inspect its latest version')
        if action == 'retire' and any(guidance[k] != previous[k] for k in ('segments', 'preferred', 'avoid')):
            raise Conflict('Retirement must bind the displayed writing preference')
        revision = expected_revision + 1
        record = dict(id=identity, revision=revision, status='retired' if action == 'retire' else 'active',
                      kind='confirmed_writing_preference_not_outcome', action=action, **guidance,
                      source_organization=source_organization, source=source, actor=actor, at=now, request_id=request_id)
        db.execute('INSERT INTO writing_preference_versions VALUES(?,?,?,?,?,?)',
                   (organization, identity, revision, request_id, fingerprint, canonical(record)))
        return record
