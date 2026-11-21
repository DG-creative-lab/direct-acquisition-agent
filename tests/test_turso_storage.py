"""Real SQLite over the Hrana wire: independent sessions and durable restarts."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from uuid import uuid4

from acquisition.adapters.turso import TursoDatabase, TursoAdmissions, CommitUncertain
from acquisition.adapters.turso.transport import Http, RemoteUnavailable, decode, encode
from acquisition.bootstrap import build, build_admissions
from acquisition.contracts import Conflict
from scripts.hosting_probe import FIXTURE_MESSAGE, NOW


class Wire:
    def __init__(self, path):
        self.path, self.sessions = path, {}
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):pass
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                baton = body.get('baton')
                if baton is None:
                    baton = uuid4().hex
                    db = sqlite3.connect(owner.path, isolation_level=None, check_same_thread=False, timeout=0)
                    db.row_factory = sqlite3.Row
                    owner.sessions[baton] = db
                db = owner.sessions[baton]
                results = []
                def execute(stmt):
                    args = ({v['name']:decode(v['value']) for v in stmt['named_args']}
                            if 'named_args' in stmt else [decode(v) for v in stmt.get('args', [])])
                    try:
                        cursor = db.execute(stmt['sql'], args)
                        return {'type':'ok','response':{'result':{
                            'cols':[{'name':c[0]} for c in cursor.description or []],
                            'rows':[[encode(v) for v in row] for row in cursor.fetchall()],
                            'affected_row_count':cursor.rowcount,'last_insert_rowid':cursor.lastrowid}}}
                    except sqlite3.Error as error:
                        return {'type':'error','error':{'code':error.sqlite_errorname}}
                for request in body['requests']:
                    if request['type'] == 'close':
                        db.close();del owner.sessions[baton];baton = None
                        results.append({'type':'ok','response':{'type':'close'}});continue
                    steps, errors = [], []
                    def condition(c):
                        if c['type']=='is_autocommit':return not db.in_transaction
                        if c['type']=='not':return not condition(c['cond'])
                        if c['type']=='and':return all(condition(v) for v in c['conds'])
                        if c['type']=='ok':return steps[c['step']] is not None
                        raise AssertionError('Unexpected condition')
                    for step in request['batch']['steps']:
                        if step.get('condition') and not condition(step['condition']):
                            steps.append(None);errors.append(None);continue
                        result = execute(step['stmt'])
                        steps.append(result['response']['result'] if result['type']=='ok' else None)
                        errors.append(result['error'] if result['type']=='error' else None)
                    results.append({'type':'ok','response':{'type':'batch',
                        'result':{'step_results':steps,'step_errors':errors}}})
                payload = json.dumps({'baton':baton,'results':results}).encode()
                self.send_response(200);self.send_header('Content-Length',str(len(payload)));self.end_headers()
                self.wfile.write(payload)
        self.server = ThreadingHTTPServer(('127.0.0.1',0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()

    def database(self, initialize=False):
        http = Http('https://example.turso.io', 'test-only')
        http.url = 'http://127.0.0.1:%s/v2/pipeline' % self.server.server_port
        db = TursoDatabase.__new__(TursoDatabase)
        db.send, db.lock_seconds = http, 5
        if initialize:db._initialize(False, lambda:NOW, False)
        return db

    def close(self):
        self.server.shutdown();self.thread.join();self.server.server_close()
        for db in self.sessions.values():db.close()


class RemoteStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'remote.sqlite'
        self.wire = Wire(self.path)
        self.database = self.wire.database(True)
    def tearDown(self):self.wire.close();self.temp.cleanup()

    def intent(self):
        # Composition uses exactly the same domain services and public ports.
        from unittest.mock import patch
        with patch('acquisition.bootstrap.build_database', return_value=self.database):
            app = build(None, clock=lambda:NOW)
        org = 'remote_test'
        cid = app.conversations.create(org,'chat','Remote test')['id']
        app.conversations.message(org,cid,'message',0,FIXTURE_MESSAGE)
        store = build_admissions(None, clock=lambda:NOW, _database=self.database)
        context = app.conversations.planning_context(org,cid,'prepare',1,True)
        return store, store.request_planning(org,cid,'prepare',1,context,fixture=True,allow_model=False)

    def test_concurrent_admission_restart_exact_replay_and_foreign_scope(self):
        store, intent = self.intent()
        barrier = threading.Barrier(2)
        def admit(_):
            independent = build_admissions(None,clock=lambda:NOW,_database=self.wire.database())
            if _ < 2:barrier.wait(timeout=10)
            return independent.admit(intent,NOW)
        with ThreadPoolExecutor(max_workers=2) as pool:receipts = list(pool.map(admit,range(2)))
        self.assertEqual(receipts[0],receipts[1])
        self.assertIsInstance(store,TursoAdmissions)
        self.assertEqual(admit(2),receipts[0])
        self.assertIsNone(store.find_request('foreign',intent.request_id))
        from dataclasses import replace
        with self.assertRaises(Conflict):store.admit(replace(intent,source_id='changed'),NOW)
        with closing(sqlite3.connect(self.path)) as raw:
            self.assertEqual(raw.execute('select count(*) from runs').fetchone()[0],1)
            self.assertEqual(raw.execute('select count(*) from execution_admissions').fetchone()[0],1)
            self.assertEqual(raw.execute('select version from acquisition_schema').fetchone()[0],23)

    def test_lost_commit_ack_reconciles_original_verified_receipt(self):
        store, intent = self.intent()
        original = self.database.send
        def lose_ack(payload):
            result = original(payload)
            if any(r.get('stmt',{}).get('sql')=='COMMIT' for request in payload['requests'] for r in request.get('batch',{}).get('steps',[])):
                raise RemoteUnavailable('lost acknowledgement')
            return result
        self.database.send = lose_ack
        receipt = store.admit(intent,NOW)
        self.database.send = original
        self.assertEqual(receipt,store.find_request(intent.organization,intent.request_id))

    def test_write_failure_rolls_back_all_rows_and_version(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with self.database.transaction() as db:
                db.execute('CREATE TABLE rollback_marker(id INTEGER PRIMARY KEY)')
                db.execute('PRAGMA user_version=22')
                db.execute('INSERT INTO rollback_marker VALUES(1)')
                db.execute('INSERT INTO rollback_marker VALUES(1)')
        with closing(sqlite3.connect(self.path)) as raw:
            self.assertEqual(raw.execute('select version from acquisition_schema').fetchone()[0],23)
            self.assertIsNone(raw.execute("select 1 from sqlite_master where name='rollback_marker'").fetchone())

    def test_unpadded_remote_blobs_preserve_exact_bytes(self):
        self.assertEqual(decode({'type':'blob','base64':'ZXhhY3Q'}),b'exact')

    def test_exact_named_bindings_types_and_row_access(self):
        with self.database.connect() as db:
            row = db.execute("SELECT :b AS b, :a AS a, :b AS again, ':ignored' AS literal -- :comment\n", {'a':2**60,'b':b'bytes'}).fetchone()
            self.assertEqual(tuple(row),(b'bytes',2**60,b'bytes',':ignored'))
            self.assertEqual(dict(row),{'b':b'bytes','a':2**60,'again':b'bytes','literal':':ignored'})

    def test_unknown_transaction_is_not_replayed_or_acknowledged(self):
        original = self.database.send
        def lose_commit(payload):
            if any(r.get('stmt',{}).get('sql')=='COMMIT' for request in payload['requests'] for r in request.get('batch',{}).get('steps',[])):
                raise RemoteUnavailable('unknown')
            return original(payload)
        self.database.send = lose_commit
        with self.assertRaises(CommitUncertain):
            with self.database.transaction() as db:db.execute('CREATE TABLE never_acknowledged(id)')
        self.database.send = original
        with closing(sqlite3.connect(self.path)) as raw:
            self.assertIsNone(raw.execute("select 1 from sqlite_master where name='never_acknowledged'").fetchone())

    def test_unregistered_remote_schema_is_rejected(self):
        with self.database.transaction() as db:db.execute('DROP TABLE acquisition_schema')
        with self.assertRaisesRegex(ValueError,'reviewed import'):self.wire.database(True)

    def test_interrupted_fresh_migration_rolls_back_journal_and_restarts(self):
        other = Wire(Path(self.temp.name)/'migration.sqlite')
        try:
            db = other.database()
            original = db.send
            def interrupt(payload):
                result = original(payload)
                if any('review_cases' in r.get('stmt',{}).get('sql','') and 'CREATE TABLE' in r.get('stmt',{}).get('sql','') for request in payload['requests'] for r in request.get('batch',{}).get('steps',[])):
                    raise RemoteUnavailable('Interrupted migration acknowledgement')
                return result
            db.send = interrupt
            with self.assertRaises(RemoteUnavailable):db._initialize(False,lambda:NOW,False)
            with closing(sqlite3.connect(other.path)) as raw:
                self.assertEqual(raw.execute("select name from sqlite_master where name not like 'sqlite_%'").fetchall(),[])
            other.database(True)
            with closing(sqlite3.connect(other.path)) as raw:
                self.assertEqual(raw.execute('select version from acquisition_schema').fetchone()[0],23)
        finally:other.close()

    def test_concurrent_fresh_initializers_converge_without_partial_schema(self):
        other = Wire(Path(self.temp.name)/'initializers.sqlite')
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(lambda _:other.database(True),range(2)))
            with closing(sqlite3.connect(other.path)) as raw:
                self.assertEqual(raw.execute('select version from acquisition_schema').fetchall(),[(23,)])
                self.assertEqual(raw.execute('select count(*) from application_store_identity').fetchone()[0],1)
                self.assertEqual(raw.execute('pragma foreign_key_check').fetchall(),[])
        finally:other.close()

    def test_expired_server_transaction_cannot_continue_as_autocommit(self):
        original = self.database.send
        def expire_before_write(payload):
            if any('INSERT INTO expiry_marker' in r.get('stmt',{}).get('sql','')
                   for request in payload['requests'] for r in request.get('batch',{}).get('steps',[])):
                self.wire.sessions[payload['baton']].execute('ROLLBACK')
            return original(payload)
        with self.database.transaction() as db:db.execute('CREATE TABLE expiry_marker(id)')
        self.database.send = expire_before_write
        with self.assertRaises(RemoteUnavailable):
            with self.database.transaction() as db:db.execute('INSERT INTO expiry_marker VALUES(1)')
        self.database.send = original
        with closing(sqlite3.connect(self.path)) as raw:
            self.assertEqual(raw.execute('select * from expiry_marker').fetchall(),[])

    def test_probe_registration_rejects_changed_authority_and_preserves_cutoff(self):
        from unittest.mock import patch
        from scripts.remote_storage_conformance import register_probe
        with self.database.transaction() as db:
            original = db.execute("SELECT sql FROM sqlite_master WHERE name='execution_admissions_no_update'").fetchone()[0]
            db.execute('DROP TABLE acquisition_schema')
            db.execute('CREATE TABLE hosting_probe_schema_version(singleton INTEGER PRIMARY KEY,version INTEGER)')
            db.execute('INSERT INTO hosting_probe_schema_version VALUES(1,23)')
            db.execute('DROP TRIGGER execution_admissions_no_update')
        with patch('scripts.remote_storage_conformance.Http',return_value=self.database.send), \
             patch('scripts.remote_storage_conformance.storage',return_value={'url':'https://example.turso.io','token':'test-only'}):
            with self.assertRaisesRegex(ValueError,'reviewed current schema'):register_probe()
            with closing(sqlite3.connect(self.path)) as raw:
                self.assertIsNone(raw.execute("select 1 from sqlite_master where name='acquisition_schema'").fetchone())
                self.assertEqual(raw.execute('select count(*) from legacy_task_admissions').fetchone()[0],0)
            with self.database.transaction() as db:db.execute(original)
            fingerprint=register_probe()
            self.assertEqual(len(fingerprint),64)
            with closing(sqlite3.connect(self.path)) as raw:
                self.assertEqual(raw.execute('select version from acquisition_schema').fetchone()[0],23)
                self.assertEqual(raw.execute('select version from hosting_probe_schema_version').fetchone()[0],23)

    def test_endpoint_and_transport_failures_do_not_disclose_credentials(self):
        from acquisition.adapters.turso.transport import endpoint, Connection
        for url in ('https://attacker.invalid','https://secret@example.turso.io','https://example.turso.io?token=secret'):
            with self.assertRaises(ValueError):endpoint(url)
        requests = []
        def unavailable(payload):
            requests.append(payload)
            raise RuntimeError('private-provider-credential')
        connection=Connection(unavailable)
        with self.assertRaises(RemoteUnavailable) as raised:connection.execute('SELECT 1')
        self.assertNotIn('private-provider-credential',str(raised.exception))
        with self.assertRaises(RemoteUnavailable):connection.execute('SELECT 2')
        self.assertEqual(len(requests),1)
