import json
from dataclasses import asdict

from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.creative import Creative

from .database import Database
from .writing_preferences import change_preference, preferences, versions


class SqliteCreative:
    def __init__(self, database: Database, preference_organization=None):
        self.database, self.preference_organization = database, preference_organization

    def preferences(self, organization):
        with self.database.connect() as db:
            history = {}
            for item in versions(db, organization):
                history.setdefault(item['id'], []).append(item)
            return [items[-1] | {'history': items} for items in reversed(list(history.values()))]

    def change_preference(self, *args, **kwargs):
        return change_preference(self.database, *args, **kwargs)

    def remember(self, organization: str, segment: str, preferred: str, avoid: str, reason: str) -> str:
        if segment not in {"inventory", "contractors"} or not organization:
            raise ValueError("Known organization and segment required")
        if any(type(value) is not str or not 1 <= len(value.strip()) <= 600 for value in (preferred, avoid, reason)):
            raise ValueError("Editorial examples require bounded nonempty text")
        payload = {"kind": "local_reviewer_preference_not_outcome", "segment": segment,
                   "preferred": preferred, "avoid": avoid, "reason": reason}
        identity = "memory_" + digest({"organization": organization, **payload})
        with self.database.transaction() as connection:
            connection.execute("INSERT OR IGNORE INTO editorial_memories VALUES(?,?,?,?)",
                               (organization, identity, segment, canonical(payload)))
        return identity

    def examples(self, organization: str, segment: str) -> list[dict]:
        return self.examples_snapshot(organization, (segment,))[segment]

    def examples_snapshot(self, organization, segments):
        with self.database.connect() as connection:
            connection.execute('BEGIN')
            current = preferences(connection, self.preference_organization or organization)
            result = {}
            for segment in segments:
                rows = connection.execute("SELECT * FROM editorial_memories WHERE organization=? AND segment=? ORDER BY rowid DESC LIMIT 3",
                                          (organization, segment)).fetchall()
                confirmed = [{k: item[k] for k in ('preferred', 'avoid', 'reason', 'source', 'source_organization', 'revision')}
                             | {'id': item['id'] + ':v' + str(item['revision']), 'segment': segment,
                                'kind': 'local_reviewer_preference_not_outcome'}
                             for item in current
                             if item['status'] == 'active' and segment in item['segments']]
                result[segment] = (confirmed + [json.loads(row["payload"]) | {"id": row["id"]} for row in rows])[:3]
            return result

    def put_context(self, organization: str, context: dict) -> str:
        identity = "context_" + digest({"organization": organization, **context})
        with self.database.transaction() as connection:
            connection.execute("INSERT OR IGNORE INTO creative_contexts VALUES(?,?,?)", (organization, identity, canonical(context)))
        return identity

    def get_context(self, organization: str, context_id: str) -> dict:
        with self.database.connect() as connection:
            row = connection.execute("SELECT payload FROM creative_contexts WHERE organization=? AND id=?", (organization, context_id)).fetchone()
        if row is None:
            raise NotFound("Creative context not found in this organization")
        context = json.loads(row[0])
        if "context_" + digest({"organization": organization, **context}) != context_id:
            raise Conflict("Creative context integrity failure")
        return context

    def get_catalogue(self, organization: str, operation_id: str) -> tuple[Creative, ...] | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT payload FROM generated_catalogues WHERE organization=? AND operation_id=?",
                                     (organization, operation_id)).fetchone()
        if not row:
            return None
        return tuple(Creative(**(item | {"evidence_ids": tuple(item.get("evidence_ids", []))})) for item in json.loads(row[0]))

    def put_catalogue(self, organization: str, operation_id: str, variants: tuple[Creative, ...]) -> None:
        payload = canonical([asdict(item) for item in variants])
        with self.database.transaction() as connection:
            row = connection.execute("SELECT payload FROM generated_catalogues WHERE organization=? AND operation_id=?",
                                     (organization, operation_id)).fetchone()
            if row and row[0] != payload:
                raise Conflict("Generated operation already binds different copy")
            connection.execute("INSERT OR IGNORE INTO generated_catalogues VALUES(?,?,?)", (organization, operation_id, payload))
