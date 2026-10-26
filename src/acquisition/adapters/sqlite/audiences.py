import json
from dataclasses import asdict

from acquisition.audiences import Business, Snapshot
from acquisition.contracts import Conflict, NotFound, canonical

from .database import Database


class SqliteAudiences:
    def __init__(self, database: Database):
        self.database = database

    def put(self, snapshot: Snapshot) -> str:
        payload = canonical(asdict(snapshot))
        with self.database.transaction() as connection:
            row = connection.execute("SELECT payload FROM audiences WHERE organization=? AND id=?",
                                     (snapshot.organization, snapshot.id)).fetchone()
            if row and row[0] != payload:
                raise Conflict("Snapshot identity already binds different bytes")
            connection.execute("INSERT OR IGNORE INTO audiences VALUES(?,?,?)",
                               (snapshot.organization, snapshot.id, payload))
        return snapshot.id

    def get(self, organization: str, snapshot_id: str) -> Snapshot:
        with self.database.connect() as connection:
            row = connection.execute("SELECT payload FROM audiences WHERE organization=? AND id=?",
                                     (organization, snapshot_id)).fetchone()
        if row is None:
            raise NotFound("Audience not found in this organization")
        data = json.loads(row[0])
        records = tuple(Business(**record) for record in data.pop("records"))
        snapshot = Snapshot(records=records, **data)
        if snapshot.id != snapshot_id or snapshot.organization != organization:
            raise Conflict("Stored audience integrity failure")
        return snapshot
