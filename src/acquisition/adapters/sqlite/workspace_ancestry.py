"""Check the authoritative local workspace journal during reconciliation."""

import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

from acquisition.contracts import Conflict

JOURNAL_BINDING_KEY='workspace:journal:v1'


def initialize_workspace_identity(connection):
    """Pin an existing legacy journal or a new empty journal exactly once."""
    connection.execute('BEGIN IMMEDIATE')
    try:
        connection.execute('''CREATE TABLE IF NOT EXISTS workspace_identity (
            singleton INTEGER PRIMARY KEY CHECK(singleton=1), journal_id TEXT NOT NULL UNIQUE,
            origin TEXT NOT NULL CHECK(origin IN ('fresh','legacy')))''')
        origin='legacy' if connection.execute('SELECT 1 FROM sessions LIMIT 1').fetchone() else 'fresh'
        connection.execute('INSERT OR IGNORE INTO workspace_identity VALUES(1,?,?)',('journal_'+uuid.uuid4().hex,origin))
        connection.execute("CREATE TRIGGER IF NOT EXISTS workspace_identity_no_update BEFORE UPDATE ON workspace_identity BEGIN SELECT RAISE(ABORT,'Workspace identity is immutable'); END")
        connection.execute("CREATE TRIGGER IF NOT EXISTS workspace_identity_no_delete BEFORE DELETE ON workspace_identity BEGIN SELECT RAISE(ABORT,'Workspace identity is immutable'); END")
        connection.commit()
    except BaseException:
        connection.rollback()
        raise


def journal_identity(connection):
    rows=connection.execute('SELECT singleton,journal_id,origin FROM workspace_identity').fetchall()
    if (len(rows)!=1 or rows[0]['singleton']!=1 or rows[0]['origin'] not in {'fresh','legacy'}
            or not isinstance(rows[0]['journal_id'],str) or not rows[0]['journal_id'].startswith('journal_')
            or len(rows[0]['journal_id'])!=40):
        raise Conflict('Workspace journal identity is invalid. Restore the original journal')
    return dict(rows[0])


def verify_workspace_binding(db, organization, guard):
    journal=journal_identity(guard[0])
    row=db.execute('SELECT inputs,receipt FROM execution_commands WHERE organization=? AND request_id=?',
                   (organization,JOURNAL_BINDING_KEY)).fetchone()
    if row is None:
        raise Conflict('Workspace journal is not bound to this domain history. Recover positively recorded ancestry; legacy absence cannot authorize independence')
    inputs,receipt=json.loads(row['inputs']),json.loads(row['receipt'])
    if not pre_history_binding(db,organization):
        raise Conflict('Legacy journal completeness is unverified. Recover positively recorded ancestry instead of declaring independence')
    if (inputs!=receipt or inputs.get('kind')!='workspace_journal_binding' or inputs.get('journal_id')!=journal['journal_id']
            or inputs.get('database_kind')!=guard[2].name):
        raise Conflict('Workspace journal differs from the bound original. Restore the original journal before reconciliation')
    return journal['journal_id']


def pre_history_binding(db, organization):
    """An association established after execution is not a completeness proof."""
    row=db.execute('SELECT inputs,receipt FROM execution_commands WHERE organization=? AND request_id=?',
                   (organization,JOURNAL_BINDING_KEY)).fetchone()
    if row is None:
        return False
    try:
        inputs,receipt=json.loads(row['inputs']),json.loads(row['receipt'])
        return (inputs==receipt and inputs.get('kind')=='workspace_journal_binding'
                and inputs.get('basis')=='before_first_run' and inputs.get('witness') is None)
    except (ValueError,TypeError,AttributeError):
        return False


def bind_workspace_journal(database, organization):
    """Workspace composition can enroll history; reconciliation cannot."""
    from acquisition.contracts import canonical
    with database.connect() as db:
        if db.execute('SELECT 1 FROM execution_commands WHERE organization=? AND request_id=?',
                      (organization,JOURNAL_BINDING_KEY)).fetchone():
            return
    with workspace_ancestry_guard(database.path) as guard, database.transaction() as db:
        if db.execute('SELECT 1 FROM execution_commands WHERE organization=? AND request_id=?',
                      (organization,JOURNAL_BINDING_KEY)).fetchone():
            return  # Never replace a previous binding, including after journal loss.
        journal=journal_identity(guard[0])
        history=db.execute('SELECT 1 FROM runs WHERE organization=? LIMIT 1',(organization,)).fetchone()
        if history:
            return  # No subset of a legacy journal proves absence of ancestry.
        value={'kind':'workspace_journal_binding','journal_id':journal['journal_id'],'database_kind':guard[2].name,
               'basis':'before_first_run','witness':None}
        db.execute('INSERT INTO execution_commands VALUES(?,?,?,?)',
                   (organization,JOURNAL_BINDING_KEY,canonical(value),canonical(value)))

@contextmanager
def workspace_ancestry_guard(domain_path):
    domain=Path(domain_path).resolve()
    if domain.name=='conversations.sqlite':
        root=domain.parent
    elif domain.name=='campaign.sqlite':
        root=domain.parent.parent
    else:
        raise Conflict('Reconcile ancestry using the original canonical workspace database path')
    connection=None
    try:
        try:
            # mode=rw must not silently create an empty authority journal. Lock
            # workspace first, then domain, retaining this lock through commit.
            connection=sqlite3.connect((root/'workspace.sqlite').as_uri()+'?mode=rw',uri=True,
                                       timeout=10,isolation_level=None)
            connection.row_factory=sqlite3.Row
            connection.execute('BEGIN IMMEDIATE')
            connection.execute('SELECT id,payload FROM sessions LIMIT 0')
            journal_identity(connection)
        except sqlite3.Error:
            raise Conflict('Workspace ancestry is unavailable. Restore the original workspace journal before reconciliation') from None
        yield connection,root,domain
    finally:
        if connection is not None:
            try:
                connection.rollback()
            finally:
                connection.close()


def workspace_ancestry(guard, organization, run, tasks):
    connection,root,domain=guard
    identities={run['request_id']} | {json.loads(t['inputs']).get('brief',{}).get('campaign_id') for t in tasks}
    records=[]
    try:
        rows=connection.execute("SELECT id,payload FROM sessions WHERE json_extract(payload,'$.organization')=? ORDER BY rowid",
                                (organization,)).fetchall()
        for row in rows:
            session=json.loads(row['payload'])
            if row['id'] not in identities and session.get('run_id')!=run['id']:
                continue
            if session.get('id')!=row['id']:
                raise Conflict('Workspace session identity needs repair before reconciliation')
            shared=(session.get('database_scope')=='conversations' or session.get('conversation_plan')
                    or organization=='local-conversations')
            expected=(root/'conversations.sqlite' if shared else root/organization/'campaign.sqlite').resolve()
            if expected!=domain:
                raise Conflict('Workspace database scope needs repair before reconciliation')
            records.append({k:session.get(k) for k in ('id','organization','database_scope','run_id',
                                                       'parent_id','followup_id','conversation_plan')})
    except (sqlite3.Error,ValueError,TypeError):
        raise Conflict('Workspace ancestry is unreadable. Restore the original workspace journal before reconciliation') from None
    return records
