from .followups import require_followup
import hashlib
import json

from acquisition.campaigns import Draft
from acquisition.contracts import Conflict, NotFound, canonical

from .database import Database
from .conversation_provenance import require_current_conversation


def verify(organization: str, draft: Draft) -> None:
    manifest = draft.manifest
    if manifest.get("schema") != "draft/v1" or manifest.get("organization") != organization:
        raise Conflict("Unsupported or cross-organization artifact")
    if (hashlib.sha256(draft.mailing_csv.encode()).hexdigest() != manifest.get("mailing_sha256")
            or hashlib.sha256(draft.assignments_csv.encode()).hexdigest() != manifest.get("assignments_sha256")):
        raise Conflict("Artifact bytes do not match manifest")


class SqliteDrafts:
    """SQLite owns exact bytes; filesystem exports are reproducible projections."""

    def __init__(self, database: Database):
        self.database = database

    def put(self, organization: str, operation_id: str, draft: Draft) -> str:
        verify(organization, draft)
        with self.database.transaction() as connection:
            require_current_conversation(connection, draft.manifest["brief"])
            require_followup(connection, organization, draft.manifest, draft.id)
            old = connection.execute("SELECT draft_id FROM draft_operations WHERE organization=? AND operation_id=?",
                                     (organization, operation_id)).fetchone()
            if old and old[0] != draft.id:
                raise Conflict("Operation already produced different content")
            connection.execute("INSERT OR IGNORE INTO drafts VALUES(?,?,?,?,?)",
                               (organization, draft.id, canonical(draft.manifest), draft.mailing_csv, draft.assignments_csv))
            connection.execute("INSERT OR IGNORE INTO draft_operations VALUES(?,?,?)",
                               (organization, operation_id, draft.id))
        # A retry also checks the original committed bytes instead of trusting a hash alone.
        existing = self.get(organization, draft.id)
        if existing != draft:
            raise Conflict("Artifact identity conflict")
        return draft.id

    def get(self, organization: str, draft_id: str) -> Draft:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM drafts WHERE organization=? AND id=?",
                                     (organization, draft_id)).fetchone()
        if row is None:
            raise NotFound("Draft not found in this organization")
        draft = Draft(json.loads(row["manifest"]), row["mailing"], row["assignments"])
        verify(organization, draft)
        if draft.id != draft_id:
            raise Conflict("Artifact manifest integrity failure")
        return draft
