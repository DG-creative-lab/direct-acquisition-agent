"""Scoped local coordinator journal, separate from domain authorization records."""

import json
import sqlite3
from contextlib import contextmanager

from acquisition.contracts import Conflict, NotFound, canonical
from acquisition.conversations import identity


class SqlitePreparations:
    def __init__(self, path):
        self.path = path
        with self.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS preparations (
                organization TEXT NOT NULL, id TEXT NOT NULL, request_id TEXT NOT NULL,
                conversation_id TEXT NOT NULL, revision INTEGER NOT NULL,
                epoch INTEGER NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY(organization,id), UNIQUE(organization,request_id),
                UNIQUE(organization,conversation_id,revision))''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()

    def request(self, organization, request_id):
        identity(organization), identity(request_id)
        with self.connect() as db:
            row = db.execute("SELECT payload FROM preparations WHERE organization=? AND request_id=?", (organization, request_id)).fetchone()
        return json.loads(row[0]) if row else None

    def for_revision(self, organization, conversation_id, revision):
        return next((r for r in self.listing(organization, conversation_id) if r["inputs"]["revision"] == revision), None)

    def create(self, organization, request_id, value):
        value = value | {"request_id": request_id, "epoch": 0}
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                old = db.execute("SELECT payload FROM preparations WHERE organization=? AND request_id=?", (organization, request_id)).fetchone()
                if old:
                    old = json.loads(old[0])
                    if old["inputs"] != value["inputs"]:
                        raise Conflict("Preparation request already binds different inputs or consent")
                    return old
                db.execute("INSERT INTO preparations VALUES(?,?,?,?,?,0,?)", (organization, value["id"], request_id,
                    value["inputs"]["conversation_id"], value["inputs"]["revision"], canonical(value)))
                db.commit()
            except sqlite3.IntegrityError:
                raise Conflict("This revision already has a preparation request") from None
            finally:
                if db.in_transaction:
                    db.rollback()
        return value

    def get(self, organization, preparation_id):
        identity(organization), identity(preparation_id)
        with self.connect() as db:
            row = db.execute("SELECT payload FROM preparations WHERE organization=? AND id=?", (organization, preparation_id)).fetchone()
        if row is None:
            raise NotFound("Preparation not found in this organization")
        return json.loads(row[0])

    def listing(self, organization, conversation_id=None):
        identity(organization)
        if conversation_id:
            identity(conversation_id)
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT payload FROM preparations WHERE organization=?" +
                (" AND conversation_id=?" if conversation_id else "") + " ORDER BY rowid", (organization, conversation_id) if conversation_id else (organization,))]

    def update(self, organization, prior, status, detail, *, run_id=None):
        value = prior | {"status": status, "detail": detail, "epoch": prior["epoch"] + 1}
        if run_id is not None:
            value["run_id"] = run_id
        with self.connect() as db:
            changed = db.execute("UPDATE preparations SET epoch=?,payload=? WHERE organization=? AND id=? AND epoch=?",
                (value["epoch"], canonical(value), organization, prior["id"], prior["epoch"])).rowcount
        return value if changed else self.get(organization, prior["id"])
