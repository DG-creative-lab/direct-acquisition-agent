"""Atomic, paused workflow admission. No legacy ownership inference or dispatch.

request_planning is a server-only explicit user command, not a model tool. It
persists verified frozen inputs and the exact generation decision before any
task exists. request_workflow uses installed source loaders and task composers.
admit consumes saved requests, never caller-supplied consent claims.
"""

import json
import time
from uuid import uuid4
from dataclasses import asdict

from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.conversations import (
    CAMPAIGN_ADMISSION_KINDS, CAPABILITY, FIXTURE_CAPABILITY, AdmissionIntent, AdmissionReceipt, identity, revision_number,
    planning_permission, planning_capacity, planning_intent, planning_binding,
)

from acquisition.runtime import TaskSpec

from .conversations import scoped_conversation, messages
from .database import stored_plan_hash
from .execution import account, require_active
from .tasks import finite_time, insert_run, event, scoped_run
from .admission_sources import require_owner, freshness_fence
from .admission_guard import seal_legacy_writes, verified_required


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
    def __init__(self, database, preflight, clock=time.time, *, workflow_source=None, workflow_intent=None):
        self.database,self.preflight,self.clock=database,preflight,clock
        self.workflow_source,self.workflow_intent=workflow_source,workflow_intent

    def required(self):
        with self.database.connect() as db:return verified_required(db)

    def seal_legacy_writes(self):
        """An irreversible format selection, never permission to execute."""
        with self.database.transaction() as db:
            seal_legacy_writes(db, self.clock)

    def request_inputs(self, organization, request_id):
        identity(organization),identity(request_id)
        with self.database.connect() as db:
            row=db.execute('SELECT * FROM admission_requests WHERE organization=? AND request_id=?',
                           (organization,request_id)).fetchone()
            if row is None:return None
            self._request_intent(row)
            return json.loads(row['inputs'])

    def request_for_source(self, organization, kind, source_id, references):
        """Find an original source operation independently of caller key spelling."""
        for value in (organization,kind,source_id):identity(value)
        with self.database.connect() as db:
            row=db.execute("SELECT * FROM admission_requests WHERE organization=? AND json_extract(inputs,'$.operation_key')=?",
                           (organization,kind+':'+source_id)).fetchone()
            if row is None:return None
            intent=self._request_intent(row);command=json.loads(row['inputs'])
            if (command.get('kind')!=kind or intent.source_id!=source_id or
                    canonical(command.get('references'))!=canonical(references)):
                raise Conflict('Saved admission source differs from the requested native operation')
            return row['request_id']

    def request_for_planning(self, organization, conversation_id, native_request_id):
        """Read the original scoped key without rewriting older raw-key requests."""
        for value in (organization,conversation_id,native_request_id):identity(value)
        with self.database.connect() as db:
            rows=db.execute("""SELECT * FROM admission_requests WHERE organization=? AND conversation_id=?
                AND COALESCE(json_extract(inputs,'$.native_request_id'),request_id)=?""",
                (organization,conversation_id,native_request_id)).fetchall()
            if not rows:return None
            if len(rows)!=1:raise Conflict('Multiple admissions claim the same native planning request')
            row=rows[0];intent=self._request_intent(row);command=json.loads(row['inputs'])
            if (command.get('conversation_id')!=conversation_id or intent.source_id!=conversation_id or
                    intent.tasks[0].inputs.get('request_id')!=native_request_id):
                raise Conflict('Saved planning request differs from its native conversation source')
            return row['request_id']

    def request_workflow(self, organization, request_id, kind, references, *, allow_model, model_config=None, entrypoint=None):
        """Server-only explicit command. Only installed source loaders can build tasks."""
        identity(organization),identity(request_id)
        if self.workflow_source is None or self.workflow_intent is None:
            raise ValueError('Workflow admission composition is unavailable')
        values={'kind':kind,'references':references,'allow_model':allow_model,
                'model_config':asdict(model_config) if model_config else None}
        if entrypoint is not None:values['entrypoint']=entrypoint
        command=canonical(values)
        if len(command.encode())>1_048_576:raise ValueError('Workflow request exceeds the admission envelope')
        references=json.loads(command)['references']
        with self.database.transaction() as db:
            old=db.execute('SELECT * FROM admission_requests WHERE organization=? AND request_id=?',
                           (organization,request_id)).fetchone()
            if old:
                inputs=json.loads(old['inputs']);inputs.pop('operation_key',None)
                if canonical(inputs)!=command:raise Conflict('Admission request already binds different inputs or consent')
                return self._request_intent(old)
            now=self.clock();finite_time(now)
            source=self.workflow_source(db,organization,kind,references,now)
            intent,operation=self.workflow_intent(organization,request_id,kind,references,source,allow_model,model_config,now)
            if db.execute("SELECT 1 FROM admission_requests WHERE organization=? AND json_extract(inputs,'$.operation_key')=?",
                          (organization,operation)).fetchone():
                raise Conflict('This source operation already has an admission request; resume its original identity')
            self._campaign_available(db,intent,kind)
            runtime_key=intent.tasks[0].inputs['run_request_id']
            self._runtime_available(db,organization,runtime_key)
            if db.execute("SELECT 1 FROM admission_requests WHERE organization=? AND json_extract(payload,'$.tasks[0].inputs.run_request_id')=?",
                          (organization,runtime_key)).fetchone():
                raise Conflict('Runtime key already belongs to another paused request')
            now=self.clock();finite_time(now)
            require_owner(db,source['owner']);freshness_fence(source,now)
            inputs=canonical(json.loads(command)|{'operation_key':operation})
            db.execute('INSERT INTO admission_requests VALUES(?,?,?,?,?,?,?,?,NULL,NULL)',
                (organization,request_id,inputs,canonical(intent.payload()),intent.fingerprint,canonical(source),
                 canonical(generation_decision(intent)),now))
            return intent

    def request_planning(self, organization, conversation_id, request_id, revision, context, *,
                         fixture, allow_model, model_config=None, native_request_id=None):
        native_request=request_id if native_request_id is None else native_request_id
        identity(native_request)
        for value in (organization,conversation_id,request_id):identity(value)
        revision_number(revision)
        if revision<1 or type(fixture) is not bool or type(allow_model) is not bool:
            raise ValueError('Use a positive revision and explicit generation decisions')
        planning_permission(fixture,allow_model,model_config)
        values={'conversation_id':conversation_id,'revision':revision,'context':context,
                'fixture':fixture,'allow_model':allow_model,
                'model_config':asdict(model_config) if model_config else None}
        if native_request_id is not None:values['native_request_id']=native_request
        inputs=canonical(values)
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
            self._available(db,organization,conversation_id,revision,own_request=native_request,admission_request_id=request_id)
            intent=planning_intent(organization,request_id,source,context,planning_results(db,organization,conversation_id),
                fixture=fixture,allow_model=allow_model,config=model_config,native_request_id=native_request_id)
            self._runtime_available(db,organization,intent.tasks[0].inputs['run_request_id'])
            if db.execute("SELECT 1 FROM admission_requests WHERE organization=? AND json_extract(payload,'$.tasks[0].inputs.run_request_id')=?",
                          (organization,intent.tasks[0].inputs['run_request_id'])).fetchone():
                raise Conflict('Runtime key already belongs to another paused request')
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
    def _available(db, organization, conversation_id, revision, *, own_request=None, admission_request_id=None):
        old=db.execute('SELECT request_id,revision FROM conversation_plans WHERE organization=? AND conversation_id=?',
                       (organization,conversation_id)).fetchall()
        staged=db.execute("SELECT request_id,revision,COALESCE(json_extract(inputs,'$.native_request_id'),request_id) AS native_request_id FROM admission_requests WHERE organization=? AND conversation_id=?",
                          (organization,conversation_id)).fetchall()
        planning_capacity(revision,old,[dict(row) for row in staged],own_request,admission_request_id=admission_request_id)

    @staticmethod
    def _campaign_available(db, intent, kind):
        if kind not in CAMPAIGN_ADMISSION_KINDS:return
        campaign=intent.tasks[0].inputs['brief']['campaign_id']
        # Actual frozen identities cover pre-fix staged rows with kind-prefixed
        # operation keys as well as new shared campaign reservations.
        for row in db.execute('SELECT * FROM admission_requests WHERE organization=? AND request_id!=?',
                              (intent.organization,intent.request_id)):
            command=json.loads(row['inputs'])
            if command.get('kind') in CAMPAIGN_ADMISSION_KINDS:
                saved=SqliteAdmissions._request_intent(row)
                if saved.tasks[0].inputs['brief']['campaign_id']==campaign:
                    raise Conflict('Campaign identity belongs to another admission request')
        if db.execute("""SELECT 1 FROM runs r JOIN tasks t ON t.run_id=r.id
                WHERE r.organization=? AND t.position=0 AND json_extract(t.inputs,'$.brief.campaign_id')=?
                AND json_extract(t.inputs,'$.workflow_version') IN
                ('monthly-mail/v1','monthly-mail/v2','monthly-mail/v3','conversation-mail/v1','conversation-model-mail/v3')""",
                (intent.organization,campaign)).fetchone():
            raise Conflict('Campaign identity already belongs to a runtime plan')

    @staticmethod
    def _legacy_tasks(db, organization, request_id):
        row=db.execute('SELECT * FROM runs WHERE organization=? AND request_id=?',(organization,request_id)).fetchone()
        if row is None:return None
        if db.execute('SELECT 1 FROM execution_admissions WHERE organization=? AND run_id=?',
                      (organization,row['id'])).fetchone():return None
        specs=[TaskSpec(t['capability'],json.loads(t['inputs']),t['max_attempts']) for t in
               db.execute('SELECT * FROM tasks WHERE run_id=? ORDER BY position',(row['id'],))]
        if (not specs or any('execution_admission_id' in spec.inputs for spec in specs) or
                row['request_hash']!=digest([asdict(spec) for spec in specs])):
            raise Conflict('Legacy runtime plan failed integrity checks')
        return row['id'],specs

    def legacy_tasks(self, organization, request_id):
        identity(organization),identity(request_id)
        with self.database.connect() as db:
            db.execute('BEGIN')
            return self._legacy_tasks(db,organization,request_id)

    def replay_legacy(self, organization, request_id, specs):
        with self.database.connect() as db:
            db.execute('BEGIN')
            saved=self._legacy_tasks(db,organization,request_id)
            if saved is None:raise Conflict('Legacy request is no longer observable')
            if canonical([asdict(s) for s in specs])!=canonical([asdict(s) for s in saved[1]]):
                raise Conflict('Legacy replay differs from the original task plan')
            return saved[0]

    def legacy_planning(self, organization, conversation_id, request_id, revision, *, fixture, config, frozen_context=None):
        for value in (organization,conversation_id,request_id):identity(value)
        revision_number(revision)
        with self.database.connect() as db:
            db.execute('BEGIN')
            row=db.execute('SELECT * FROM conversation_plans WHERE organization=? AND conversation_id=? AND request_id=?',
                           (organization,conversation_id,request_id)).fetchone()
            if row is None:return None
            frozen=json.loads(row['payload'])
            saved=self._legacy_tasks(db,organization,frozen['run_request_id'])
            if saved is None:return None
            if (row['revision']!=revision or frozen['revision']!=revision or
                    frozen['conversation_id']!=conversation_id or frozen['request_id']!=request_id or
                    bool(frozen.get('fixture'))!=fixture or frozen['model_config']!=(asdict(config) if config else None)):
                raise Conflict('Legacy planning replay differs from its original command')
            if frozen_context is not None:
                context={k:v for k,v in frozen.items() if k not in
                         {'conversation_id','request_id','revision','run_request_id'}}
                if 'messages' not in frozen_context:context.pop('messages')
                if canonical(frozen_context)!=canonical(context):
                    raise Conflict('Legacy planning continuation differs from its frozen context')
            specs=[TaskSpec(FIXTURE_CAPABILITY if fixture else CAPABILITY,frozen)]
            if canonical([asdict(t) for t in specs])!=canonical([asdict(t) for t in saved[1]]):
                raise Conflict('Legacy planning journal differs from its original task plan')
            return saved[0]

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
            owner=intent.ownership
            specs=intent.tasks
            frozen=specs[0].inputs
            command=json.loads(row['inputs'])
            if 'kind' in command:
                if self.workflow_source is None or self.workflow_intent is None:
                    raise ValueError('Workflow admission composition is unavailable')
                now=self.clock();finite_time(now)
                source=self.workflow_source(db,intent.organization,command['kind'],command['references'],now)
                rebuilt,operation=self.workflow_intent(intent.organization,intent.request_id,command['kind'],
                    command['references'],source,command['allow_model'],expected.model_config,now)
                compatible_operation=(operation==command['operation_key'] or
                    (command['kind'] in CAMPAIGN_ADMISSION_KINDS and command['operation_key']==command['kind']+':'+intent.source_id))
                if rebuilt!=expected or intent!=expected or not compatible_operation:
                    raise Conflict('Workflow source, settings or task plan changed before admission')
                self._campaign_available(db,intent,command['kind'])
            else:
                source=planning_source(db,intent.organization,intent.source_id)
                fixture=planning_binding(intent,expected,source)
                self._current(db,intent.organization,intent.source_id,owner.revision,source)
                self._available(db,intent.organization,intent.source_id,owner.revision,own_request=frozen['request_id'],admission_request_id=intent.request_id)
                self.preflight(intent.tasks[0].inputs,intent.organization,fixture,intent.model_config)
            self._runtime_available(db,intent.organization,frozen['run_request_id'])
            now=self.clock();finite_time(now)  # Include lock wait and validation time.
            if 'kind' in command:
                require_owner(db,source['owner']);freshness_fence(source,now)
            a=account(db,owner.organization,owner.scope_id) if owner.kind=='conversation' else None
            run='run_'+uuid4().hex
            receipt=AdmissionReceipt(intent.organization,intent.id,run,intent.fingerprint,now)
            # A deferred FK permits admission first, while commit still requires
            # the exact runtime row. SQL guards reject old cached writers too.
            def record_admission():
                db.execute("INSERT INTO execution_admissions VALUES(?,?,?,?,?,?,?,'paused')",
                           (intent.organization,intent.id,intent.request_id,run,canonical(intent.payload()),intent.fingerprint,canonical(asdict(receipt))))
            required=verified_required(db)
            if required:record_admission()
            run=insert_run(db,intent.organization,frozen['run_request_id'],specs,now,
                           reservation_owner=(intent.request_id,intent.fingerprint),run_id=run)
            if owner.kind=='conversation':
                db.execute('INSERT INTO execution_runs VALUES(?,?,?,?,?)',
                           (intent.organization,run,owner.organization,owner.scope_id,owner.revision))
            if 'kind' not in command:
                db.execute('INSERT INTO conversation_plans VALUES(?,?,?,?,?,?)',
                           (intent.organization,owner.scope_id,frozen['request_id'],owner.revision,canonical(frozen),now))
            if not required:record_admission()
            event(db,run,None,'execution_admitted',{'admission_id':intent.id,'status':'paused',
                  'policy':a['policy'] if a else 'standalone-per-run'},now)
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
            run['request_id']!=intent.tasks[0].inputs['run_request_id'] or
            (intent.ownership.kind=='conversation' and (owner is None or
             tuple(owner)!=(intent.ownership.organization,intent.ownership.scope_id,intent.ownership.revision))) or
            (intent.ownership.kind=='standalone' and owner is not None)):
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
