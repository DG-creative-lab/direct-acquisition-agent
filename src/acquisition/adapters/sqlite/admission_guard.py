"""Store-format and immutable admission checks shared by effect boundaries.

This is SQLite enforcement, not runtime policy. No workspace ancestry inference
is consulted for new-format work. Fixture grants are a separate store extension.
"""
import json
import sqlite3
from contextlib import closing
from dataclasses import asdict
from pathlib import Path
from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.creative import CHANNEL_CONTENT_CAPABILITY
from acquisition.conversations import AdmissionIntent, ExecutionOwnership, journey_commands
from acquisition.runtime import TaskSpec
from .database import stored_plan_hash


def read_admission_policy(path):
    """Observe format without migration or a second write lock."""
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=10)) as db:
        return verified_required(db)


def verified_required(db):
    table=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='admission_store_policy'").fetchone()
    if not table:
        if db.execute('PRAGMA user_version').fetchone()[0]>=13:
            raise Conflict('Admission policy metadata is unavailable; restore the authoritative store')
        return False  # Preserved pre-cutover schema fixtures and readers.
    row=db.execute('SELECT policy FROM admission_store_policy WHERE singleton=1').fetchone()
    if row and row[0]!='verified-paused/v1':raise Conflict('Unsupported admission store policy')
    return row is not None


def seal_legacy_writes(db, clock):
    """Select the paused format while holding the caller's SQLite write lock."""
    from .tasks import finite_time
    if verified_required(db):
        return
    if db.execute("SELECT 1 FROM tasks WHERE status='running' LIMIT 1").fetchone() or db.execute(
            "SELECT 1 FROM model_calls WHERE status='reserved' LIMIT 1").fetchone():
        raise Conflict('Quiesce running tasks and reconcile reserved inference before admission cutover')
    if db.execute('''SELECT 1 FROM conversation_plans p LEFT JOIN runs r
            ON r.organization=p.organization AND r.request_id=json_extract(p.payload,'$.run_request_id')
            WHERE r.id IS NULL LIMIT 1''').fetchone():
        raise Conflict('Reconcile the original legacy planning admission before cutover')
    now = clock()
    finite_time(now)
    db.execute("INSERT INTO admission_store_policy VALUES(1,'verified-paused/v1',?)", (now,))


def require_legacy_writer(db):
    if verified_required(db):
        raise Conflict('This store requires verified admission; legacy task creation is closed')


def has_admission_evidence(db, organization, run_id):
    """A reserved runtime key or surviving event also fences a lost binding."""
    return db.execute("""SELECT 1 FROM runs r WHERE r.organization=? AND r.id=? AND (
        EXISTS(SELECT 1 FROM tasks t WHERE t.run_id=r.id
            AND json_type(t.inputs,'$.execution_admission_id') IS NOT NULL)
        OR EXISTS(SELECT 1 FROM admission_requests a WHERE a.organization=r.organization
            AND json_extract(a.payload,'$.tasks[0].inputs.run_request_id')=r.request_id)
        OR EXISTS(SELECT 1 FROM events e WHERE e.run_id=r.id AND e.kind='execution_admitted'))""",
        (organization,run_id)).fetchone() is not None


def binding(db, organization, run_id):
    """Verify stored authority independently at claim and inference reservation."""
    row=db.execute('SELECT * FROM execution_admissions WHERE organization=? AND run_id=?',(organization,run_id)).fetchone()
    if row is None:
        if has_admission_evidence(db,organization,run_id):
            raise Conflict('New-format work is missing its committed admission')
        return None  # A sealed store keeps old runs inspectable but unclaimable.
    intent=AdmissionIntent.from_payload(json.loads(row['payload']))
    request=db.execute('SELECT * FROM admission_requests WHERE organization=? AND request_id=?',
                       (organization,intent.request_id)).fetchone()
    run=db.execute('SELECT request_id,request_hash FROM runs WHERE organization=? AND id=?',(organization,run_id)).fetchone()
    receipt=json.loads(row['receipt'])
    source=json.loads(request['source']) if request is not None else None
    consent={'id':intent.consent_id,'allow_model':intent.model_config is not None,'intent_fingerprint':intent.fingerprint}
    if (intent.organization!=organization or row['id']!=intent.id or row['request_id']!=intent.request_id or
            row['fingerprint']!=intent.fingerprint or request is None or run is None or
            json.loads(request['payload'])!=intent.payload() or request['fingerprint']!=intent.fingerprint or
            digest(source)!=intent.source_fingerprint or json.loads(request['consent'])!=consent or
            receipt.get('organization')!=organization or receipt.get('admission_id')!=intent.id or
            receipt.get('run_id')!=run_id or receipt.get('fingerprint')!=intent.fingerprint or
            run['request_id']!=intent.tasks[0].inputs['run_request_id'] or
            run['request_hash']!=digest(json.loads(intent.task_plan_json)) or stored_plan_hash(db,run_id)!=run['request_hash']):
        raise Conflict('Runtime work differs from its committed admission')
    owner=db.execute('SELECT owner_organization,conversation_id,revision FROM execution_runs WHERE organization=? AND run_id=?',
                     (organization,run_id)).fetchone()
    if ((intent.ownership.kind=='conversation' and (owner is None or tuple(owner)!=
            (intent.ownership.organization,intent.ownership.scope_id,intent.ownership.revision))) or
            (intent.ownership.kind=='standalone' and owner is not None)):
        raise Conflict('Execution ownership differs from its admission')
    if any(spec.capability==CHANNEL_CONTENT_CAPABILITY for spec in intent.tasks):
        _bound_channel_context(db,organization,run_id,intent,source)
    return intent


def _channel_context(db, organization, run_id, context_id=None):
    from .creative import read_context

    preparation = db.execute("""SELECT p.* FROM channel_preparations p
        JOIN runs r ON r.organization=p.organization AND r.id=p.run_id
        WHERE p.organization=? AND p.run_id=? AND r.request_id='channel:'||p.request_id""",
        (organization,run_id)).fetchone()
    if preparation is None or (context_id is not None and preparation['context_id']!=context_id):
        raise Conflict('Channel execution requires its original preparation and run')
    try:
        context = read_context(db,organization,preparation['context_id'])
    except NotFound as error:
        raise Conflict('Restore the original scoped channel context') from error
    if (context.get('organization')!=organization or context.get('schema')!='creative-context/v5'
            or context.get('preparation_request_id')!=preparation['request_id']
            or canonical(context['command'])!=preparation['inputs']):
        raise Conflict('Channel context differs from its original preparation')
    return preparation,context


def _bound_channel_context(db, organization, run_id, intent, source):
    from .sequence_journeys import require_channel_context_origin, require_journey_origin, saved_journey

    preparation,context = _channel_context(db,organization,run_id,intent.source_id)
    specs = intent.tasks
    inputs = specs[0].inputs
    if (intent.workflow_version!='paused-channel-admission/v1' or len(specs)!=1
            or specs[0].capability!=CHANNEL_CONTENT_CAPABILITY
            or inputs.get('context_id')!=preparation['context_id']
            or inputs.get('execution_admission_id')!=intent.id
            or inputs.get('model_config')!=context['model_config']
            or intent.model_config is None or intent.model_config.payload()!=context['model_config']
            or digest(context)!=intent.context_fingerprint
            or inputs.get('journey')!=context.get('journey')):
        raise Conflict('Channel preparation differs from its committed admission')
    lineage = source['recipients']
    if ([(item['request_id'],item['context_id']) for item in lineage]!=
            [(item['request_id'],item['context_id']) for item in context['recipients']]):
        raise Conflict('Channel recipient lineage differs from its committed admission')

    owner = intent.ownership
    origin = context.get('journey')
    if origin is None:
        if owner.kind!='standalone' or owner.organization!=organization:
            raise Conflict('Standalone channel context differs from its committed ownership')
    else:
        if (owner.kind!='conversation' or origin['request_id']!=preparation['request_id']
                or (owner.organization,owner.scope_id,owner.revision)!=
                   (origin['organization'],origin['conversation_id'],origin['revision'])):
            raise Conflict('Channel journey differs from its committed ownership')
        assessment_role = 'email-assessment' if context['command']['channel']=='email' else 'call-assessment'
        assessment_key = journey_commands(origin['journey_id'])[assessment_role]
        if any(assessment_key not in item['assessment_request_ids'] for item in lineage):
            raise Conflict('Channel lineage differs from its original assessment request')
        require_journey_origin(db,organization,origin | {'request_id':assessment_key},current=False)
        frozen = saved_journey(db,origin['organization'],origin['journey_id'])['inputs']
        if frozen['allow_generation'] is not True or frozen['model_config']!=context['model_config']:
            raise Conflict('Channel binding differs from the original journey consent')
    require_channel_context_origin(db,organization,context,current=False,frozen_recipients=lineage,
                                   admitted_standalone=origin is None)


CHANNEL_OWNERSHIP_KEY = 'channel-ownership:'
CHANNEL_OWNERSHIP_EVENT = 'channel_ownership_reconciled'


def channel_reconciliation(db, organization, run_id):
    command = db.execute('SELECT inputs,receipt FROM execution_commands WHERE organization=? AND request_id=?',
                         (organization,CHANNEL_OWNERSHIP_KEY+run_id)).fetchone()
    events = db.execute("""SELECT e.data FROM events e JOIN runs r ON r.id=e.run_id
        WHERE r.organization=? AND r.id=? AND e.kind=?""",
        (organization,run_id,CHANNEL_OWNERSHIP_EVENT)).fetchall()
    if command is None and not events:
        return None
    if command is None or len(events)!=1 or command['receipt']!=events[0]['data']:
        raise Conflict('Restore the original channel ownership reconciliation receipts')
    receipt = json.loads(command['receipt'])
    request = json.loads(command['inputs'])
    if (receipt.get('schema')!='channel-ownership-reconciliation/v1' or receipt.get('organization')!=organization
            or receipt.get('run_id')!=run_id or request!={'fingerprint':receipt.get('fingerprint'),'run_id':run_id}
            or receipt.get('authority')!='none'):
        raise Conflict('Channel reconciliation differs from its original scoped request')
    return receipt


def read_channel_run(db, organization, run_id, context_id=None):
    """Load either a committed binding or the exact original legacy plan."""
    preparation,context = _channel_context(db,organization,run_id,context_id)
    intent = binding(db,organization,run_id)
    if intent is not None and intent.workflow_version!='paused-channel-admission/v1':
        raise Conflict('The channel run uses a different admission workflow')
    if intent is None:
        inputs = {'workflow_version':'channel-content/v1','context_id':preparation['context_id'],
                  'model_config':context['model_config']}
        if 'journey' in context:
            inputs['journey'] = context['journey']
        expected = digest([asdict(TaskSpec(CHANNEL_CONTENT_CAPABILITY,inputs,max_attempts=3))])
        run_hash = db.execute('SELECT request_hash FROM runs WHERE organization=? AND id=?',
                              (organization,run_id)).fetchone()[0]
        if run_hash!=expected or stored_plan_hash(db,run_id)!=expected:
            raise Conflict('Legacy channel work differs from its original preparation and plan')
        origin = context.get('journey')
        link = db.execute('SELECT owner_organization,conversation_id,revision FROM execution_runs '
                          'WHERE organization=? AND run_id=?',(organization,run_id)).fetchone()
        owner = (origin['organization'],origin['conversation_id'],origin['revision']) if origin else None
        if (tuple(link) if link else None)!=owner:
            raise Conflict('Legacy channel accounting link differs from its frozen origin')
        receipt = channel_reconciliation(db,organization,run_id)
        if receipt is not None:
            resolved = ExecutionOwnership(**receipt['ownership'])
            account = (resolved.organization,resolved.scope_id,resolved.revision)
            store = db.execute('SELECT id FROM application_store_identity WHERE singleton=1').fetchone()
            if (store is None or receipt['store_id']!=store[0] or receipt['plan_fingerprint']!=run_hash
                    or receipt['context_id']!=preparation['context_id']
                    or (account!=owner if owner else resolved.kind!='standalone' or resolved.organization!=organization)):
                raise Conflict('Channel reconciliation differs from its original plan, context or owner')
    return preparation,context,intent


def require_channel_run(db, organization, run_id, context_id):
    """Verify a run and apply current origin checks within the caller's effect transaction."""
    from .sequence_journeys import require_channel_context_origin, require_journey_origin

    _,context,intent = read_channel_run(db,organization,run_id,context_id)
    if intent is None:
        require_channel_context_origin(db,organization,context)
    elif context.get('journey') is not None:
        require_journey_origin(db,organization,context['journey'])
    return context
