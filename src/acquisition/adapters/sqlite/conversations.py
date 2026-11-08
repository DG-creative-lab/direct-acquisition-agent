import json

from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.conversations import identity, revision_number, text, requested_scope, BUDGET_POLICY, SUPPORTED_BUDGET_POLICIES, CAPABILITY, validate_result

from .database import Database
from .tasks import finite_time
from .admission_guard import require_legacy_writer
from .execution import require_active


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
            exchanges=[]
            for row in db.execute('SELECT id,confirmed FROM conversation_actions WHERE organization=? AND conversation_id=? AND confirmed IS NOT NULL ORDER BY rowid',
                                  (organization,conversation_id)):
                receipt=json.loads(row['confirmed'])
                if receipt.get('exchange'):
                    exchanges.append({'action_id':row['id'],'revision':receipt['message_receipt']['revision'],
                                      'exchange':receipt['exchange'],'message_receipts':receipt['message_receipts']})
            if exchanges:conversation['confirmed_action_exchanges']=exchanges
            return conversation | {"messages": messages(db, organization, conversation_id),
                                   "admissions": [json.loads(r[0]) for r in db.execute("SELECT payload FROM conversation_plans WHERE organization=? AND conversation_id=? ORDER BY revision", (organization, conversation_id))]}

    def append(self, organization, conversation_id, request_id, expected_revision, content, now):
        identity(organization), identity(conversation_id), identity(request_id), revision_number(expected_revision), text(content), finite_time(now)
        with self.database.transaction() as db:
            return append_message(db, organization, conversation_id, request_id, expected_revision, content, now)

    def reply_budget(self, organization, conversation_id, request_id, expected_revision, plan_id, content, now):
        for value in (organization, conversation_id, request_id, plan_id):
            identity(value)
        revision_number(expected_revision), text(content), finite_time(now)
        inputs = {'kind': 'budget-reply/v1', 'conversation_id': conversation_id, 'revision': expected_revision,
                  'plan_id': plan_id, 'content': content}
        key = 'budget-reply:' + digest({'conversation_id': conversation_id, 'request_id': request_id})
        with self.database.transaction() as db:
            old = db.execute('SELECT inputs,receipt FROM conversation_action_commands WHERE organization=? AND request_id=?',
                             (organization, key)).fetchone()
            if old:
                if json.loads(old['inputs']) != inputs:
                    raise Conflict('Budget reply request already binds different inputs')
                return json.loads(old['receipt']) | {'replayed': True}
            conversation = scoped_conversation(db, organization, conversation_id)
            if conversation['revision'] != expected_revision:
                raise Conflict('The budget question is historical; reload the current conversation')
            require_budget_question(db, organization, conversation_id, expected_revision, plan_id)
            receipt = append_message(db, organization, conversation_id, key, expected_revision, content, now)
            db.execute('INSERT INTO conversation_action_commands VALUES(?,?,?,?)',
                       (organization, key, canonical(inputs), canonical(receipt)))
            # Recheck the original question and exact saved reply after writes.
            require_budget_question(db, organization, conversation_id, expected_revision, plan_id)
            saved = db.execute('SELECT content,revision FROM conversation_messages WHERE organization=? AND conversation_id=? AND request_id=?',
                               (organization, conversation_id, key)).fetchone()
            if (saved is None or tuple(saved) != (content, expected_revision + 1)
                    or scoped_conversation(db, organization, conversation_id)['revision'] != expected_revision + 1):
                raise Conflict('Budget reply changed before commit')
            return receipt

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
            require_legacy_writer(db)
            if db.execute("SELECT 1 FROM admission_requests WHERE organization=? AND conversation_id=? AND (revision=? OR COALESCE(json_extract(inputs,'$.native_request_id'),request_id)=?)",
                          (organization,conversation_id,expected_revision,request_id)).fetchone():
                raise Conflict('This revision or request key has a paused atomic planning request; resume its original admission')
            if conversation["revision"] != expected_revision:
                raise Conflict("Conversation changed before planning admission")
            require_active(db, organization, conversation_id, expected_revision)
            if expected_revision == 0:
                raise ValueError("Add your campaign objective before requesting a plan")
            admissions = db.execute("SELECT revision FROM conversation_plans WHERE organization=? AND conversation_id=?", (organization, conversation_id)).fetchall()
            if any(row[0] == expected_revision for row in admissions):
                raise Conflict("This revision already has a planning request; inspect or resume its original request")
            staged = db.execute('SELECT revision FROM admission_requests WHERE organization=? AND conversation_id=?',
                                (organization,conversation_id)).fetchall()
            if len({row[0] for row in admissions} | {row[0] for row in staged}) >= 6:
                raise ValueError("Conversation planning budget exhausted")
            frozen = {**context, "conversation_id": conversation_id, "request_id": request_id, "revision": expected_revision,
                      "messages": messages(db, organization, conversation_id),
                      "run_request_id": "conversation-plan:" + digest({"conversation": conversation_id, "request": request_id})}
            scope = requested_scope(organization, conversation_id, expected_revision, frozen['messages'])
            if 'requested_scope' in context and context['requested_scope'] != scope:
                raise Conflict('Requested scope changed before planning admission')
            if context.get('budget_policy', BUDGET_POLICY) not in SUPPORTED_BUDGET_POLICIES:
                raise Conflict('Budget policy differs from the installed planning contract')
            frozen['budget_policy'] = BUDGET_POLICY
            frozen['requested_scope'] = scope
            # Check the actual encoded provider envelope before recording the
            # one permitted admission for this revision or reserving a call.
            preflight(frozen)
            db.execute("INSERT INTO conversation_plans VALUES(?,?,?,?,?,?)", (organization, conversation_id, request_id, expected_revision, canonical(frozen), now))
            return frozen


def append_message(db, organization, conversation_id, request_id, expected_revision, content, now):
    identity(organization), identity(conversation_id), identity(request_id), revision_number(expected_revision), text(content), finite_time(now)
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


def require_budget_question(db, organization, conversation_id, revision, plan_id):
    try:
        row = db.execute('SELECT payload FROM conversation_plans WHERE organization=? AND conversation_id=? AND revision=?',
                         (organization, conversation_id, revision)).fetchone()
        frozen = json.loads(row[0]) if row else {}
        if (frozen.get('budget_policy') not in SUPPORTED_BUDGET_POLICIES or frozen.get('conversation_id') != conversation_id
                or frozen.get('revision') != revision
                or frozen.get('knowledge_id') != 'knowledge_' + digest(frozen.get('knowledge'))):
            raise Conflict('This plan has no current budget clarification contract')
        task = db.execute('SELECT t.inputs,t.output FROM tasks t JOIN runs r ON r.id=t.run_id WHERE r.organization=? '
                          "AND r.request_id=? AND r.status='succeeded' AND t.status='succeeded' AND t.position=0 AND t.capability=?",
                          (organization, frozen['run_request_id'], CAPABILITY)).fetchone()
        result = json.loads(task['output']) if task else {}
        fields = ('outcome', 'objective', 'budget_pence', 'segments', 'copy_mode', 'question', 'assumptions', 'unsupported_reason')
        if (not task or json.loads(task['inputs']) != frozen or result.get('id') != plan_id
                or result.get('outcome') != 'clarification' or not result.get('budget_clarification')
                or validate_result({k: result[k] for k in fields}, frozen, organization) != result
                or [m for m in messages(db, organization, conversation_id) if m['revision'] <= revision] != frozen['messages']):
            raise Conflict('Budget reply does not match the completed native clarification')
    except (KeyError, TypeError, ValueError) as error:
        raise Conflict('Budget clarification evidence is invalid') from error
