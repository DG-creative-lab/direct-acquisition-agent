"""Persist unapproved profile proposals, without admitting tasks or review authority."""

from dataclasses import asdict
from datetime import datetime, timezone

from acquisition.campaigns import ProfiledBrief, brief_from, build_draft
from acquisition.contracts import Conflict, canonical, digest
from acquisition.reviews import creatives_from

from .admission_guard import verified_required
from .audiences import read_snapshot, write_snapshot
from .creative import read_context
from .drafts import verify, read_draft


class SqliteProfileDrafts:
    def __init__(self, database, profiles, copy, clock):
        self.database, self.profiles, self.copy, self.clock = database, profiles, copy, clock

    def _validate(self, db, organization, draft):
        verify(organization, draft)
        if draft.manifest.get('schema') != 'profile-draft/v1':
            raise Conflict('This port only prepares unapproved profile proposals')
        brief = brief_from(draft.manifest['brief'])
        if type(brief) is not ProfiledBrief:
            raise Conflict('Profile proposal lost its versioned brief')
        installed = self.profiles.campaign_profile(organization, brief.profile.key, brief.profile.version)
        if installed != brief.profile:
            raise Conflict('Proposal differs from the installed reviewed profile')
        snapshot = read_snapshot(db, organization, draft.manifest['snapshot_id'])
        creatives = creatives_from(draft)
        if build_draft(snapshot, brief, creatives) != draft:
            raise Conflict('Proposal differs from its exact frozen inputs')
        contexts = {item.context_id: read_context(db, organization, item.context_id) for item in creatives}
        self.copy.validate(organization, creatives, contexts, installed.product_profile_id, brief.plan['id'],
                           datetime.fromtimestamp(self.clock(), timezone.utc).date())
        for segment in brief.segments:
            saved = db.execute('SELECT payload FROM generated_catalogues WHERE organization=? AND operation_id=?',
                               (organization, brief.plan['id'] + ':' + segment)).fetchone()
            expected = canonical([asdict(item) for item in creatives if item.segment == segment])
            if saved is None or saved[0] != expected:
                raise Conflict('Stored profile catalogue differs from the proposal')

    def publish(self, organization, request_id, snapshot, bundles, draft):
        operation_id = 'profile:' + request_id
        with self.database.transaction() as db:
            if verified_required(db):
                raise Conflict('Profile preparation has no verified admission capability; execution stays paused')
            if snapshot.organization != organization:
                raise Conflict('Profile audience belongs to another organization')
            brief = brief_from(draft.manifest['brief'])
            if type(brief) is not ProfiledBrief or brief.plan['request_id'] != request_id:
                raise Conflict('Proposal differs from the original preparation request')
            provided = {'context_' + digest({'organization': organization, **context}) for context, _ in bundles}
            required = {item.context_id for item in creatives_from(draft)}
            if len(bundles) != len(brief.segments) or provided != required:
                raise Conflict('Profile inputs must cover exactly the proposal contexts')
            old = db.execute('SELECT draft_id FROM draft_operations WHERE organization=? AND operation_id=?',
                             (organization, operation_id)).fetchone()
            if old and old[0] != draft.id:
                raise Conflict('Profile request already binds different exact inputs')
            write_snapshot(db, snapshot)
            for context, pair in bundles:
                context_id = 'context_' + digest({'organization': organization, **context})
                db.execute('INSERT OR IGNORE INTO creative_contexts VALUES(?,?,?)',
                           (organization, context_id, canonical(context)))
                key = context['plan_id'] + ':' + context['segment']
                payload = canonical([asdict(item) for item in pair])
                saved = db.execute('SELECT payload FROM generated_catalogues WHERE organization=? AND operation_id=?',
                                   (organization, key)).fetchone()
                if saved and saved[0] != payload:
                    raise Conflict('Profile catalogue request already binds different content')
                db.execute('INSERT OR IGNORE INTO generated_catalogues VALUES(?,?,?)', (organization, key, payload))
            self._validate(db, organization, draft)
            db.execute('INSERT OR IGNORE INTO drafts VALUES(?,?,?,?,?)',
                       (organization, draft.id, canonical(draft.manifest), draft.mailing_csv, draft.assignments_csv))
            db.execute('INSERT OR IGNORE INTO draft_operations VALUES(?,?,?)', (organization, operation_id, draft.id))
            # Repeat validation after writes: in-transaction source changes cannot publish a proposal.
            self._validate(db, organization, read_draft(db, organization, draft.id))
        return draft.id

    def get(self, organization, identity):
        with self.database.connect() as db:
            return read_draft(db, organization, identity)

    def find(self, organization, request_id):
        with self.database.connect() as db:
            row = db.execute('SELECT draft_id FROM draft_operations WHERE organization=? AND operation_id=?',
                             (organization, 'profile:' + request_id)).fetchone()
            return read_draft(db, organization, row[0]) if row else None
