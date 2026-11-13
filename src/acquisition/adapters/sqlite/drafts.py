import hashlib
import json
import math
import time

from acquisition.campaigns import Draft, DraftLease, brief_from, build_draft
from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.creative import creative_record, fixture_catalog
from acquisition.runtime import LeaseLost

from .audiences import read_snapshot
from .conversation_provenance import require_current_conversation
from .database import Database
from .execution import require_brief_active
from .fixture_execution import DRAFT_CAPABILITIES, fixture_active, fixture_enabled, require_fixture_deadline
from .followups import require_followup
from .selected_audience import require_selected_audience


def verify(organization: str, draft: Draft) -> None:
    manifest = draft.manifest
    if manifest.get("schema") not in {"draft/v1", "profile-draft/v1"} or manifest.get("organization") != organization:
        raise Conflict("Unsupported or cross-organization artifact")
    if (hashlib.sha256(draft.mailing_csv.encode()).hexdigest() != manifest.get("mailing_sha256")
            or hashlib.sha256(draft.assignments_csv.encode()).hexdigest() != manifest.get("assignments_sha256")):
        raise Conflict("Artifact bytes do not match manifest")


def read_draft(db, organization: str, draft_id: str) -> Draft:
    row = db.execute("SELECT * FROM drafts WHERE organization=? AND id=?", (organization, draft_id)).fetchone()
    if row is None:
        raise NotFound("Draft not found in this organization")
    draft = Draft(json.loads(row["manifest"]), row["mailing"], row["assignments"])
    verify(organization, draft)
    if draft.id != draft_id:
        raise Conflict("Artifact manifest integrity failure")
    return draft


def write_draft(db, organization: str, operation_id: str, draft: Draft, now: float) -> str:
    verify(organization, draft)
    if draft.manifest['schema'] != 'draft/v1':
        raise Conflict('Profile proposals require their dedicated validated preparation port')
    brief = draft.manifest["brief"]
    require_brief_active(db, organization, brief)
    require_current_conversation(db, brief, draft.manifest.get('campaign_scope'))
    require_selected_audience(db, organization, brief, draft.manifest["snapshot_id"], now)
    draft_id = draft.id
    require_followup(db, organization, draft.manifest, draft_id)
    old = db.execute("SELECT draft_id FROM draft_operations WHERE organization=? AND operation_id=?",
                     (organization, operation_id)).fetchone()
    if old and old[0] != draft_id:
        raise Conflict("Operation already produced different content")
    db.execute("INSERT OR IGNORE INTO drafts VALUES(?,?,?,?,?)",
               (organization, draft_id, canonical(draft.manifest), draft.mailing_csv, draft.assignments_csv))
    db.execute("INSERT OR IGNORE INTO draft_operations VALUES(?,?,?)", (organization, operation_id, draft_id))
    # Check the exact bytes of an existing artifact before committing an operation that refers to it.
    if read_draft(db, organization, draft_id) != draft:
        raise Conflict("Artifact identity conflict")
    if any(key in brief for key in ('requested_scope', 'conversation_id', 'followup_id')):
        require_current_conversation(db, brief, draft.manifest.get('campaign_scope'))
        require_followup(db, organization, draft.manifest, draft_id)
    return draft_id


class SqliteDrafts:
    """SQLite owns exact bytes; filesystem exports are reproducible projections."""

    def __init__(self, database: Database, clock=time.time, *, execution_clock=None):
        self.database, self.clock = database, clock
        self.execution_clock = execution_clock or clock

    def put(self, organization: str, operation_id: str, draft: Draft, *, lease: DraftLease | None = None) -> str:
        with self.database.transaction() as connection:
            deadline = None
            if fixture_enabled(connection) or lease is not None:
                deadline = self._fixture_lease(connection, organization, operation_id, draft, lease)
            draft_id = write_draft(connection, organization, operation_id, draft, self.clock())
            if deadline is not None:
                require_fixture_deadline(deadline, self.execution_clock())
            return draft_id

    def _fixture_lease(self, db, organization, operation_id, draft, lease):
        if lease is None or operation_id != lease.run_id + ':draft' or not fixture_active(db, organization, lease.run_id):
            raise LeaseLost('Fixture publication requires its active admitted task')
        task = db.execute("""SELECT t.* FROM tasks t JOIN runs r ON r.id=t.run_id
            WHERE r.organization=? AND r.id=? AND r.status='running' AND t.id=? AND t.status='running'""",
                          (organization, lease.run_id, lease.task_id)).fetchone()
        now = self.execution_clock()
        if (task is None or task['capability'] not in DRAFT_CAPABILITIES or task['token'] != lease.token
                or not math.isfinite(now) or task['lease_until'] is None or task['lease_until'] <= now):
            raise LeaseLost('Fixture publication lease expired, stopped or superseded')
        inputs = json.loads(task['inputs'])
        if (inputs['snapshot_id'] != draft.manifest['snapshot_id']
                or canonical(inputs['brief']) != canonical(draft.manifest['brief'])):
            raise Conflict('Fixture draft differs from the admitted campaign inputs')
        catalogue = fixture_catalog()
        if digest([creative_record(item) for item in catalogue]) != inputs['creative_catalogue_hash']:
            raise Conflict('Fixture catalogue differs from the admitted version')
        brief = brief_from(inputs['brief'])
        snapshot = read_snapshot(db, organization, inputs['snapshot_id'])
        creatives = tuple(item for item in catalogue if item.segment in brief.segments)
        if draft != build_draft(snapshot, brief, creatives):
            raise Conflict('Fixture draft differs from the admitted catalogue and audience')
        return task['lease_until']

    def get(self, organization: str, draft_id: str) -> Draft:
        with self.database.connect() as connection:
            return read_draft(connection, organization, draft_id)
