import json
from dataclasses import asdict

from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.creative import Creative

from .database import Database


class SqliteCreative:
    def __init__(self, database: Database):
        self.database = database

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
        with self.database.connect() as connection:
            rows = connection.execute("SELECT * FROM editorial_memories WHERE organization=? AND segment=? ORDER BY rowid DESC LIMIT 3",
                                      (organization, segment)).fetchall()
        return [json.loads(row["payload"]) | {"id": row["id"]} for row in rows]

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
