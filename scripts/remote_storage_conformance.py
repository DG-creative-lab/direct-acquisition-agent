"""Opt-in synthetic conformance on the existing isolated libSQL probe resource."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
from multiprocessing import Manager
import re
import sqlite3
import subprocess
import time
from tempfile import TemporaryDirectory
from uuid import uuid4

from acquisition.adapters.sqlite.database import Database
from acquisition.adapters.turso import TursoDatabase, CommitUncertain
from acquisition.adapters.turso.transport import Connection, Http, RemoteUnavailable, endpoint
from acquisition.bootstrap import build, build_admissions
from acquisition.contracts import Conflict, digest
from acquisition.conversations import AdmissionIntent
from scripts.hosting_probe import load_environment, FIXTURE_MESSAGE, NOW


def storage():return {'url':os.environ['TURSO_DATABASE_URL'],'token':os.environ['TURSO_AUTH_TOKEN']}


def schema_tokens(sql):
    # Ignore formatting, retain literal contents and token boundaries.
    tokens = re.findall(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|\[[^\]]*\]|`[^`]*`|!=|<>|[A-Za-z_]\w*|\d+|[^\s]",sql)
    return ['<>' if token == '!=' else token for token in tokens]


def register_probe():
    """Explicit one-time adoption, only after complete schema-23 comparison.

    Preserve the probe journal, application data, identity and legacy cutoff.
    This is not a general import or restore interface.
    """
    with TemporaryDirectory() as root:
        local = Database(Path(root)/'expected.sqlite')
        with local.transaction() as db:
            # The diagnostic probe predates intake. Compare its exact old shape;
            # production initialization then migrates the registered store to v27.
            for table in ('youtube_revocations','youtube_approvals','youtube_results','youtube_interactions',
                          'youtube_preparations','youtube_requests','youtube_revisions',
                          'preparation_contexts','intake_planning_sources', 'intake_requests', 'intake_brief_revisions', 'intake_company_revisions'):
                db.execute('DROP TABLE ' + table)
            db.execute('PRAGMA user_version=23')
            expected = {r['name']:schema_tokens(r['sql']) for r in db.execute(
                "SELECT name,sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'")}
    connection = Connection(Http(storage()['url'],storage()['token']))
    try:
        connection.execute('BEGIN IMMEDIATE')
        actual = {r['name']:schema_tokens(r['sql']) for r in connection.execute(
            "SELECT name,sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'")}
        if (any(actual.get(k)!=v for k,v in expected.items()) or
            set(actual)-set(expected)-{'hosting_probe_schema_version','hosting_probe_transport','acquisition_schema'}):
            raise ValueError('Probe schema differs from the reviewed current schema')
        if connection.execute('SELECT version FROM hosting_probe_schema_version WHERE singleton=1').fetchone()[0]!=23:
            raise ValueError('Only the current schema-23 probe can be registered')
        connection.execute('CREATE TABLE IF NOT EXISTS acquisition_schema(singleton INTEGER PRIMARY KEY CHECK(singleton=1),version INTEGER NOT NULL)')
        row=connection.execute('SELECT version FROM acquisition_schema WHERE singleton=1').fetchone()
        if row is None:connection.execute('INSERT INTO acquisition_schema VALUES(1,23)')
        elif row[0]!=23:raise ValueError('Existing migration journal differs')
        connection.commit()
        return digest(expected)
    except BaseException:
        try:connection.rollback()
        except Exception:pass
        raise
    finally:connection.close()


def admit(payload, barrier=None):
    db = TursoDatabase(**{'url':storage()['url'],'token':storage()['token']},initialize=False)
    store = build_admissions(None,clock=lambda:NOW,_database=db)
    if barrier is not None:barrier.wait(timeout=30)
    return asdict(store.admit(AdmissionIntent.from_payload(payload),NOW))


def run(key):
    settings = storage()
    app = build(None,clock=lambda:NOW,remote_storage=settings)
    store = app.admissions.store
    org = 'remote_conformance_'+key
    cid = app.conversations.create(org,'chat','Synthetic remote conformance')['id']
    app.conversations.message(org,cid,'message',0,FIXTURE_MESSAGE)
    context = app.conversations.planning_context(org,cid,'prepare',1,True)
    intent = store.request_planning(org,cid,'prepare',1,context,fixture=True,allow_model=False)
    with Manager() as manager, ProcessPoolExecutor(max_workers=2) as workers:
        barrier = manager.Barrier(2)
        receipts = list(workers.map(admit,[intent.payload(),intent.payload()],[barrier,barrier]))
    assert receipts[0]==receipts[1]
    assert admit(intent.payload())==receipts[0]
    assert store.find_request('foreign',intent.request_id) is None
    try:store.admit(replace(intent,source_id='changed'),NOW)
    except Conflict:pass
    else:raise AssertionError('Changed inputs accepted')
    assert app.tasks.claim(org,NOW,60,run_id=receipts[0]['run_id']) is None
    original = store.database.send
    # A separate original request tests the actual commit followed by lost ACK.
    cid2 = app.conversations.create(org,'chat2','Synthetic uncertain acknowledgement')['id']
    app.conversations.message(org,cid2,'message2',0,FIXTURE_MESSAGE)
    context2 = app.conversations.planning_context(org,cid2,'prepare2',1,True)
    intent2 = store.request_planning(org,cid2,'prepare2',1,context2,fixture=True,allow_model=False)
    def lose_ack(payload):
        result = original(payload)
        if any(r.get('stmt',{}).get('sql')=='COMMIT' for request in payload['requests'] for r in request.get('batch',{}).get('steps',[])):
            raise RemoteUnavailable('Injected lost acknowledgement')
        return result
    store.database.send = lose_ack
    try:receipt2 = store.admit(intent2,NOW)
    finally:store.database.send = original
    assert store.find_request(org,intent2.request_id)==receipt2
    marker='remote_rollback_'+key
    try:
        with store.database.transaction() as db:
            db.execute('CREATE TABLE '+marker+'(id INTEGER PRIMARY KEY)')
            db.execute('PRAGMA user_version=22')
            db.execute('INSERT INTO '+marker+' VALUES(1)')
            db.execute('INSERT INTO '+marker+' VALUES(1)')
    except sqlite3.IntegrityError:pass
    else:raise AssertionError('Constraint did not reject transaction')
    with store.database.connect() as db:
        assert db.execute('PRAGMA user_version').fetchone()[0]==27
        assert db.execute("SELECT 1 FROM sqlite_master WHERE name=?",(marker,)).fetchone() is None
        assert db.execute('SELECT count(*) FROM runs WHERE organization=?',(org,)).fetchone()[0]==2
        assert db.execute('SELECT count(*) FROM execution_admissions WHERE organization=?',(org,)).fetchone()[0]==2
        row = db.execute("SELECT :b AS b,:a AS a,:b AS repeated,':literal' AS literal -- :comment\n",{'a':2**60,'b':b'exact'}).fetchone()
        assert tuple(row)==(b'exact',2**60,b'exact',':literal')
    expiry_table = 'remote_expiry_'+key
    expired = False
    try:
        with store.database.transaction() as db:
            db.execute('CREATE TABLE '+expiry_table+'(id INTEGER PRIMARY KEY)')
            db.execute('INSERT INTO '+expiry_table+' VALUES(1)')
            time.sleep(12)
            db.execute('INSERT INTO '+expiry_table+' VALUES(2)')
    except RemoteUnavailable:expired = True
    with store.database.connect() as db:
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE name=?",(expiry_table,)).fetchone()
        if expired:
            assert exists is None, 'Expired transaction leaked DDL or writes'
        else:
            assert db.execute('SELECT count(*) FROM '+expiry_table).fetchone()[0]==2
    if not expired:
        with store.database.transaction() as db:db.execute('DROP TABLE '+expiry_table)
    return {'organization':org,'concurrent_processes':2,'original_receipt':receipts[0],
        'lost_ack_receipt':asdict(receipt2),'durable_runs':2,'changed_inputs_rejected':True,
        'foreign_scope_hidden':True,'paused_execution_preserved':True,
        'atomic_ddl_version_rollback':True,'exact_bindings':True,'model_calls':0,
        'idle_expiry_observed':expired,'idle_partial_writes':False}


def channel_recovery(key):
    from acquisition.bootstrap import build_contact_directory, build_recipient_contexts, build_channel_preparation
    from acquisition.runtime import LeaseLost
    from acquisition.reasoning import ModelError
    settings = storage()
    def seed(suffix):
        org = 'remote_channel_'+key+'_'+suffix
        contacts = build_contact_directory(None,org,'fielddesk',lambda:NOW,remote_storage=settings)
        assessed = contacts.prepare(org,'source','fielddesk-crm-a',1,'email')
        person = assessed['report']['eligible'][0]
        contexts = build_recipient_contexts(None,org,'fielddesk',lambda:NOW,remote_storage=settings)
        contexts.prepare(org,'recipient',assessed['assessment_id'],person,'reviewed-context-a',1)
        return org
    now = [NOW]
    org = seed('lease')
    channel = build_channel_preparation(None,org,'fielddesk',lambda:now[0],remote_storage=settings)
    run_id = channel.start(org,'content','fielddesk',('recipient',),'email')
    claim = channel.tasks.claim(org,NOW,10,run_id=run_id)
    outcome = channel.worker.capabilities[claim.capability](claim)
    now[0] += 11
    try:channel.tasks.settle(claim,outcome,now[0])
    except LeaseLost:pass
    else:raise AssertionError('Expired lease published')
    class NeverRepeat:
        def complete(self, request):raise AssertionError('Recorded generation repeated')
    restarted = build_channel_preparation(None,org,'fielddesk',lambda:now[0],gateway=NeverRepeat(),remote_storage=settings)
    restarted.worker.drain(org,run_id=run_id)
    view = restarted.inspect(org,'content')
    assert view['ready_for_review'] and len(view['model_calls'])==3
    class Unknown:
        def complete(self, request):raise ModelError('provider_request_failed')
    uncertain_org = seed('unknown')
    uncertain = build_channel_preparation(None,uncertain_org,'fielddesk',lambda:NOW,gateway=Unknown(),remote_storage=settings)
    unknown_run = uncertain.start(uncertain_org,'content','fielddesk',('recipient',),'email')
    uncertain.worker.drain(uncertain_org,run_id=unknown_run)
    before = uncertain.inspect(uncertain_org,'content')['model_calls']
    assert len(before)==1 and before[0]['status']=='unknown'
    reopened = build_channel_preparation(None,uncertain_org,'fielddesk',lambda:NOW,gateway=NeverRepeat(),remote_storage=settings)
    reopened.worker.drain(uncertain_org,run_id=unknown_run)
    assert reopened.inspect(uncertain_org,'content')['model_calls']==before
    return {'synthetic':True,'expired_lease_rejected':True,'recorded_fixture_calls':3,
            'recovery_added_calls':0,'unknown_restart_added_calls':0,'live_model_calls':0}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file',type=Path,required=True)
    parser.add_argument('--register-reviewed-probe',action='store_true')
    parser.add_argument('--channel-recovery',action='store_true')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();load_environment(args.env_file)
    url=endpoint(storage()['url'])
    if not url.startswith('https://acquisition-hosting-probe-'):
        raise ValueError('Use the existing dedicated acquisition-hosting-probe resource')
    report={'version':'remote-storage-conformance/v1','synthetic':True,'passed':False}
    report['source_commit']=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    report['source_dirty']=bool(subprocess.check_output(['git','status','--porcelain','--untracked-files=all','--','src','scripts','config','tests'],text=True))
    try:
        if args.register_reviewed_probe:report['registered_schema_sha256']=register_probe()
        key=uuid4().hex
        report['observed']=run(key)
        if args.channel_recovery:report['channel_recovery']=channel_recovery(key)
        report['passed']=True
    except Exception as error:report['error_type']=type(error).__name__
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
