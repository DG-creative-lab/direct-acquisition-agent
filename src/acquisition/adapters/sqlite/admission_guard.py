"""Store-format and immutable admission checks shared by effect boundaries.

This is SQLite enforcement, not runtime policy. No workspace ancestry inference
is consulted for new-format work. Fixture grants are a separate store extension.
"""
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from acquisition.contracts import Conflict, digest
from acquisition.conversations import AdmissionIntent
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


def binding(db, organization, run_id):
    """Verify stored authority independently at claim and inference reservation."""
    row=db.execute('SELECT * FROM execution_admissions WHERE organization=? AND run_id=?',(organization,run_id)).fetchone()
    marked=db.execute("""SELECT 1 FROM tasks t JOIN runs r ON r.id=t.run_id
        WHERE r.organization=? AND t.run_id=? AND json_type(t.inputs,'$.execution_admission_id') IS NOT NULL""",
        (organization,run_id)).fetchone()
    if row is None:
        if marked:raise Conflict('New-format work is missing its committed admission')
        return None  # A sealed store keeps old runs inspectable but unclaimable.
    intent=AdmissionIntent.from_payload(json.loads(row['payload']))
    request=db.execute('SELECT * FROM admission_requests WHERE organization=? AND request_id=?',
                       (organization,intent.request_id)).fetchone()
    run=db.execute('SELECT request_id,request_hash FROM runs WHERE organization=? AND id=?',(organization,run_id)).fetchone()
    receipt=json.loads(row['receipt'])
    consent={'id':intent.consent_id,'allow_model':intent.model_config is not None,'intent_fingerprint':intent.fingerprint}
    if (intent.organization!=organization or row['id']!=intent.id or row['request_id']!=intent.request_id or
            row['fingerprint']!=intent.fingerprint or request is None or run is None or
            json.loads(request['payload'])!=intent.payload() or request['fingerprint']!=intent.fingerprint or
            digest(json.loads(request['source']))!=intent.source_fingerprint or json.loads(request['consent'])!=consent or
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
    return intent
