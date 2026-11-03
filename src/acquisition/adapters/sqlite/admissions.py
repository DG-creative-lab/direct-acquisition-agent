"""Atomic, paused planning admission. No legacy ownership inference or dispatch.

request_planning is a server-only explicit user command, not a model tool. It
persists verified frozen inputs and the exact generation decision before any
task exists. admit consumes that record, never a caller-supplied consent claim.
"""

import json
import time
from dataclasses import asdict

from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.conversations import (
    AdmissionIntent, AdmissionReceipt, identity, revision_number,
    planning_permission, planning_capacity, planning_intent, planning_binding,
)

from .conversations import scoped_conversation, messages
from .database import stored_plan_hash
from .execution import account, require_active
from .tasks import finite_time, insert_run, event, scoped_run


def planning_source(db, organization, conversation_id):
    row=scoped_conversation(db,organization,conversation_id)
    exchanges=[]
    for action in db.execute('''SELECT id,confirmed FROM conversation_actions
        WHERE organization=? AND conversation_id=? AND confirmed IS NOT NULL ORDER BY rowid''',
        (organization,conversation_id)):
        receipt=json.loads(action['confirmed'])
        if receipt.get('exchange'):
            exchanges.append({'action_id':action['id'],'revision':receipt['message_receipt']['revision'],
                              'exchange':receipt['exchange'],'message_receipts':receipt['message_receipts']})
    return {'organization':organization,'conversation_id':conversation_id,'revision':row['revision'],
            'messages':messages(db,organization,conversation_id),'confirmed_action_exchanges':exchanges}


def planning_results(db, organization, conversation_id):
    rows=db.execute('''SELECT t.output FROM conversation_plans p
        JOIN runs r ON r.organization=p.organization AND r.request_id=json_extract(p.payload,'$.run_request_id')
        JOIN tasks t ON t.run_id=r.id AND t.position=0 AND t.status='succeeded'
        WHERE p.organization=? AND p.conversation_id=? ORDER BY p.revision''',(organization,conversation_id))
    return [json.loads(row[0]) for row in rows]


def generation_decision(intent):
    return {'id':intent.consent_id,'allow_model':intent.model_config is not None,
            'intent_fingerprint':intent.fingerprint}


class SqliteAdmissions:
    def __init__(self, database, preflight, clock=time.time):
        self.database,self.preflight,self.clock=database,preflight,clock

    def request_planning(self, organization, conversation_id, request_id, revision, context, *,
                         fixture, allow_model, model_config=None):
        for value in (organization,conversation_id,request_id):identity(value)
        revision_number(revision)
        if revision<1 or type(fixture) is not bool or type(allow_model) is not bool:
            raise ValueError('Use a positive revision and explicit generation decisions')
        planning_permission(fixture,allow_model,model_config)
        inputs=canonical({'conversation_id':conversation_id,'revision':revision,'context':context,
                          'fixture':fixture,'allow_model':allow_model,
                          'model_config':asdict(model_config) if model_config else None})
        if len(inputs.encode())>1_048_576:raise ValueError('Planning inputs exceed the admission envelope')
        # Copy caller-owned dictionaries before checking or persisting them.
        context=json.loads(inputs)['context']
        with self.database.transaction() as db:
            old=db.execute('SELECT * FROM admission_requests WHERE organization=? AND request_id=?',
                           (organization,request_id)).fetchone()
            if old:
                if old['inputs']!=inputs:raise Conflict('Planning request already binds different inputs or consent')
                return self._request_intent(old)
            source=planning_source(db,organization,conversation_id)
            self._current(db,organization,conversation_id,revision,source)
            self._available(db,organization,conversation_id,revision,own_request=request_id)
            intent=planning_intent(organization,request_id,source,context,planning_results(db,organization,conversation_id),
                fixture=fixture,allow_model=allow_model,config=model_config)
            self._runtime_available(db,organization,intent.tasks[0].inputs['run_request_id'])
            self.preflight(intent.tasks[0].inputs,organization,fixture,model_config)
            now=self.clock();finite_time(now)
            db.execute('INSERT INTO admission_requests VALUES(?,?,?,?,?,?,?,?,?,?)',
                (organization,request_id,inputs,canonical(intent.payload()),intent.fingerprint,canonical(source),
                 canonical(generation_decision(intent)),now,conversation_id,revision))
            return intent

    @staticmethod
    def _current(db, organization, conversation_id, revision, source):
        if source['revision']!=revision:raise Conflict('Conversation changed before admission')
        require_active(db,organization,conversation_id,revision)

    @staticmethod
    def _available(db, organization, conversation_id, revision, *, own_request=None):
        old=db.execute('SELECT request_id,revision FROM conversation_plans WHERE organization=? AND conversation_id=?',
                       (organization,conversation_id)).fetchall()
        staged=db.execute('SELECT request_id,revision FROM admission_requests WHERE organization=? AND conversation_id=?',
                          (organization,conversation_id)).fetchall()
        planning_capacity(revision,old,staged,own_request)

    @staticmethod
    def _runtime_available(db, organization, run_request_id):
        if db.execute('SELECT 1 FROM runs WHERE organization=? AND request_id=?',
                      (organization,run_request_id)).fetchone():
            raise Conflict('An existing run cannot be adopted into a new admission')

    @staticmethod
    def _request_intent(row):
        intent=AdmissionIntent.from_payload(json.loads(row['payload']))
        if (intent.organization!=row['organization'] or intent.request_id!=row['request_id'] or
            intent.fingerprint!=row['fingerprint'] or digest(json.loads(row['source']))!=intent.source_fingerprint or
            json.loads(row['consent'])!=generation_decision(intent)):
            raise Conflict('Saved admission request failed integrity checks')
        return intent

    def admit(self, intent, now):
        if type(intent) is not AdmissionIntent:raise ValueError('Use an immutable admission intent')
        finite_time(now)
        with self.database.transaction() as db:
            previous=db.execute('SELECT * FROM execution_admissions WHERE organization=? AND request_id=?',
                                (intent.organization,intent.request_id)).fetchone()
            if previous:
                if previous['fingerprint']!=intent.fingerprint:raise Conflict('Admission request already binds different inputs')
                return self._receipt(db,previous)[1]
            row=db.execute('SELECT * FROM admission_requests WHERE organization=? AND request_id=?',
                           (intent.organization,intent.request_id)).fetchone()
            if row is None:raise NotFound('Save the exact scoped request and consent before admission')
            expected=self._request_intent(row)
            source=planning_source(db,intent.organization,intent.source_id)
            fixture=planning_binding(intent,expected,source)
            owner=intent.ownership
            self._current(db,intent.organization,intent.source_id,owner.revision,source)
            self._available(db,intent.organization,intent.source_id,owner.revision,own_request=intent.request_id)
            specs=intent.tasks
            frozen=specs[0].inputs
            self.preflight(intent.tasks[0].inputs,intent.organization,fixture,intent.model_config)
            self._runtime_available(db,intent.organization,frozen['run_request_id'])
            now=self.clock();finite_time(now)  # Include lock wait and validation time.
            a=account(db,owner.organization,owner.scope_id)
            run=insert_run(db,intent.organization,frozen['run_request_id'],specs,now,
                           reservation_owner=(intent.request_id,intent.fingerprint))
            db.execute('INSERT INTO execution_runs VALUES(?,?,?,?,?)',
                       (intent.organization,run,owner.organization,owner.scope_id,owner.revision))
            db.execute('INSERT INTO conversation_plans VALUES(?,?,?,?,?,?)',
                       (intent.organization,owner.scope_id,intent.request_id,owner.revision,canonical(frozen),now))
            receipt=AdmissionReceipt(intent.organization,intent.id,run,intent.fingerprint,now)
            db.execute("INSERT INTO execution_admissions VALUES(?,?,?,?,?,?,?,'paused')",
                       (intent.organization,intent.id,intent.request_id,run,canonical(intent.payload()),intent.fingerprint,canonical(asdict(receipt))))
            event(db,run,None,'execution_admitted',{'admission_id':intent.id,'status':'paused','policy':a['policy']},now)
            return receipt

    def _receipt(self, db, row):
        intent=AdmissionIntent.from_payload(json.loads(row['payload']))
        request=db.execute('SELECT * FROM admission_requests WHERE organization=? AND request_id=?',
                           (row['organization'],row['request_id'])).fetchone()
        receipt=AdmissionReceipt(**json.loads(row['receipt']))
        run=scoped_run(db,row['organization'],row['run_id'])
        owner=db.execute('SELECT owner_organization,conversation_id,revision FROM execution_runs WHERE organization=? AND run_id=?',
                         (row['organization'],row['run_id'])).fetchone()
        if (request is None or self._request_intent(request)!=intent or intent.id!=row['id'] or
            intent.fingerprint!=row['fingerprint'] or receipt.organization!=row['organization'] or
            receipt.admission_id!=intent.id or receipt.run_id!=run['id'] or receipt.fingerprint!=intent.fingerprint or
            stored_plan_hash(db,run['id'])!=digest(json.loads(intent.task_plan_json)) or
            run['request_hash']!=stored_plan_hash(db,run['id']) or
            run['request_id']!=intent.tasks[0].inputs['run_request_id'] or owner is None or
            tuple(owner)!=(intent.ownership.organization,intent.ownership.scope_id,intent.ownership.revision)):
            raise Conflict('Saved admission, runtime plan or ownership failed integrity checks')
        return intent,receipt

    def get_request(self, organization, request_id):
        """Observe frozen staging inputs without reconstructing browser state."""
        identity(organization),identity(request_id)
        with self.database.connect() as db:
            row=db.execute('SELECT * FROM admission_requests WHERE organization=? AND request_id=?',
                           (organization,request_id)).fetchone()
            return self._request_intent(row) if row else None

    def pending_requests(self, organization):
        identity(organization)
        with self.database.connect() as db:
            db.execute('BEGIN')
            rows=db.execute('''SELECT r.* FROM admission_requests r LEFT JOIN execution_admissions a
                ON a.organization=r.organization AND a.request_id=r.request_id
                WHERE r.organization=? AND a.id IS NULL ORDER BY r.rowid''',(organization,)).fetchall()
            return [self._request_intent(row) for row in rows]

    def find_request(self, organization, request_id):
        identity(organization),identity(request_id)
        with self.database.connect() as db:
            db.execute('BEGIN')
            row=db.execute('SELECT * FROM execution_admissions WHERE organization=? AND request_id=?',
                           (organization,request_id)).fetchone()
            return self._receipt(db,row)[1] if row else None

    def get(self, organization, admission_id):
        identity(organization),identity(admission_id)
        with self.database.connect() as db:
            db.execute('BEGIN')
            row=db.execute('SELECT * FROM execution_admissions WHERE organization=? AND id=?',(organization,admission_id)).fetchone()
            if row is None:raise NotFound('Admission not found in this organization')
            return self._receipt(db,row)[0]
