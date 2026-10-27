import json

from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.conversations import identity, revision_number, text

from .database import Database
from .tasks import finite_time


def scoped_conversation(connection, organization, conversation_id):
    row = connection.execute("SELECT * FROM conversations WHERE organization=? AND id=?", (organization, conversation_id)).fetchone()
    if row is None:
        raise NotFound("Conversation not found in this organization")
    return row


def messages(connection, organization, conversation_id):
    return [{"id": row["request_id"], "revision": row["revision"], "role": "user", "content": row["content"], "created_at": row["created_at"]}
            for row in connection.execute("SELECT * FROM conversation_messages WHERE organization=? AND conversation_id=? ORDER BY revision",
                                          (organization, conversation_id))]


class SqliteConversations:
    def __init__(self, database: Database):
        self.database = database

    def create(self, organization, request_id, title, now):
        identity(organization), identity(request_id), text(title, 120), finite_time(now)
        conversation_id = "conversation_" + digest({"organization": organization, "request_id": request_id})[:32]
        with self.database.transaction() as db:
            old = db.execute("SELECT * FROM conversations WHERE organization=? AND request_id=?", (organization, request_id)).fetchone()
            if old and old["title"] != title:
                raise Conflict("Conversation request already binds a different title")
            if old is None:
                db.execute("INSERT INTO conversations VALUES(?,?,?,?,0,?)", (organization, conversation_id, request_id, title, now))
        return conversation_id

    def listing(self, organization):
        identity(organization)
        with self.database.connect() as db:
            return [dict(r) for r in db.execute("SELECT id,title,revision,created_at FROM conversations WHERE organization=? ORDER BY created_at DESC,id LIMIT 50", (organization,))]

    def snapshot(self, organization, conversation_id):
        identity(organization), identity(conversation_id)
        with self.database.connect() as db:
            db.execute("BEGIN")
            conversation = dict(scoped_conversation(db, organization, conversation_id))
            conversation.pop("organization")
            conversation.pop("request_id")
            return conversation | {"messages": messages(db, organization, conversation_id),
                                   "admissions": [json.loads(r[0]) for r in db.execute("SELECT payload FROM conversation_plans WHERE organization=? AND conversation_id=? ORDER BY revision", (organization, conversation_id))]}

    def append(self, organization, conversation_id, request_id, expected_revision, content, now):
        identity(organization), identity(conversation_id), identity(request_id), revision_number(expected_revision), text(content), finite_time(now)
        with self.database.transaction() as db:
            conversation = scoped_conversation(db, organization, conversation_id)
            old = db.execute("SELECT * FROM conversation_messages WHERE organization=? AND conversation_id=? AND request_id=?", (organization, conversation_id, request_id)).fetchone()
            if old:
                if old["content"] != content or old["revision"] != expected_revision + 1:
                    raise Conflict("Message request already binds different inputs")
                return {"id": request_id, "revision": old["revision"], "replayed": True}
            if conversation["revision"] != expected_revision:
                raise Conflict("Conversation changed; reload before appending this message")
            history = messages(db, organization, conversation_id)
            if len(history) >= 30 or sum(len(m["content"].encode()) for m in history) + len(content.encode()) > 12000:
                raise ValueError("Conversation context limit reached; start a new conversation")
            db.execute("INSERT INTO conversation_messages VALUES(?,?,?,?,?,?)", (organization, conversation_id, request_id, expected_revision + 1, content, now))
            db.execute("UPDATE conversations SET revision=revision+1 WHERE organization=? AND id=?", (organization, conversation_id))
            return {"id": request_id, "revision": expected_revision + 1, "replayed": False}

    def admit(self, organization, conversation_id, request_id, expected_revision, context, now, preflight):
        identity(organization), identity(conversation_id), identity(request_id), revision_number(expected_revision), finite_time(now)
        with self.database.transaction() as db:
            conversation = scoped_conversation(db, organization, conversation_id)
            old = db.execute("SELECT * FROM conversation_plans WHERE organization=? AND conversation_id=? AND request_id=?", (organization, conversation_id, request_id)).fetchone()
            if old:
                if old["revision"] != expected_revision:
                    raise Conflict("Planning request already binds a different revision")
                # Recovery uses admitted knowledge/configuration, never current files.
                return json.loads(old["payload"])
            if conversation["revision"] != expected_revision:
                raise Conflict("Conversation changed before planning admission")
            if expected_revision == 0:
                raise ValueError("Add your campaign objective before requesting a plan")
            admissions = db.execute("SELECT revision FROM conversation_plans WHERE organization=? AND conversation_id=?", (organization, conversation_id)).fetchall()
            if any(row[0] == expected_revision for row in admissions):
                raise Conflict("This revision already has a planning request; inspect or resume its original request")
            if len(admissions) >= 6:
                raise ValueError("Conversation planning budget exhausted")
            frozen = {**context, "conversation_id": conversation_id, "request_id": request_id, "revision": expected_revision,
                      "messages": messages(db, organization, conversation_id),
                      "run_request_id": "conversation-plan:" + digest({"conversation": conversation_id, "request": request_id})}
            # Check the actual encoded provider envelope before recording the
            # one permitted admission for this revision or reserving a call.
            preflight(frozen)
            db.execute("INSERT INTO conversation_plans VALUES(?,?,?,?,?,?)", (organization, conversation_id, request_id, expected_revision, canonical(frozen), now))
            return frozen
