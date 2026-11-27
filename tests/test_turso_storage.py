"""Real SQLite over the Hrana wire: independent sessions and durable restarts."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
import math
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
        self.round_float_bindings = False
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
                    def binding(value):
                        decoded=decode(value)
                        # Reproduce the measured one-ULP loss in remote JSON
                        # float bindings, independently of the adapter encoder.
                        if owner.round_float_bindings and value['type']=='float':
                            return math.nextafter(decoded,-math.inf)
                        return decoded
                    args = ({(v['name'][1:] if v['name'].startswith((':','@','$','?')) else v['name']):binding(v['value']) for v in stmt['named_args']}
                            if 'named_args' in stmt else [binding(v) for v in stmt.get('args', [])])
                    try:
                        cursor = db.execute(stmt['sql'], args)
                        return {'type':'ok','response':{'result':{
                            'cols':[{'name':c[0]} for c in cursor.description or []],
                            'rows':[[encode(v) for v in row] for row in cursor.fetchall()],
                            'affected_row_count':cursor.rowcount,'last_insert_rowid':str(cursor.lastrowid) if cursor.lastrowid is not None else None}}}
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

    def test_youtube_draft_approval_rollback_and_fresh_session_export(self):
        from unittest.mock import patch
        from acquisition.bootstrap import build_youtube
        with patch('acquisition.bootstrap.build_database', return_value=self.database):
            native = build(None, clock=lambda:NOW)
            app = build_youtube(None, lambda:NOW, organization='youtube')
        authority = app.campaigns.store.authority
        conversation = native.conversations.create('youtube','chat','YouTube')['id']
        app.message({'request_id':'message','conversation_id':conversation,'expected_revision':0,
                     'content':'Prepare YouTube placements for video editing','draft_permission':'placements'})
        campaign = app.campaigns.interactions(conversation)[0]['campaign_id']
        view = app.campaigns.read(campaign)
        command = {'request_id':'approve','campaign_id':campaign,'subject':view['review']['subject']}
        real = authority.require
        attempts = []
        def fail_at_commit(scope, actor, operation):
            if operation == 'approve':
                attempts.append(operation)
                if len(attempts) == 2:raise OSError('rollback approval')
            return real(scope, actor, operation)
        with patch.object(authority,'require',side_effect=fail_at_commit):
            with self.assertRaises(OSError):app.campaigns.command('approve',command)
        self.assertIsNone(app.campaigns.read(campaign)['approval'])
        approved = app.campaigns.command('approve',command)['result']['approval_id']
        export = {'request_id':'export','campaign_id':campaign,'subject':view['review']['subject'],'approval_id':approved}
        payload = app.campaigns.command('export',export)['result']['content']
        with patch('acquisition.bootstrap.build_database', return_value=self.wire.database()):
            reopened = build_youtube(None,lambda:NOW,organization='youtube')
        self.assertEqual(reopened.campaigns.read(campaign)['campaign'],view['campaign'])
        self.assertEqual(reopened.campaigns.command('export',export)['result']['content'],payload)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM youtube_approvals').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM model_calls').fetchone()[0],0)
        # The earlier native preview used version 25 without intake planning.
        with self.database.transaction() as db:
            db.execute('DROP TABLE preparation_contexts')
            db.execute('DROP TABLE intake_planning_sources')
            db.execute('PRAGMA user_version=25')
        with patch('acquisition.bootstrap.build_database', return_value=self.wire.database(True)):
            upgraded = build_youtube(None,lambda:NOW,organization='youtube')
        self.assertEqual(upgraded.campaigns.command('export',export)['result']['content'],payload)
        with upgraded.campaigns.store.database.connect() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],28)

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
            self.assertEqual(raw.execute('select version from acquisition_schema').fetchone()[0],28)

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
            self.assertEqual(raw.execute('select version from acquisition_schema').fetchone()[0],28)
            self.assertIsNone(raw.execute("select 1 from sqlite_master where name='rollback_marker'").fetchone())

    def test_intake_bootstrap_pinning_foreign_scope_and_lost_ack_replay(self):
        from dataclasses import replace
        from unittest.mock import patch
        from acquisition.bootstrap import build_intake
        from acquisition.campaigns import CampaignBriefDraft, CampaignIntake
        from acquisition.creative import CompanyDraft
        from acquisition.contracts import NotFound
        from acquisition.adapters.sqlite.intake import SqliteCampaignIntake
        settings = {'url':'https://example.turso.io', 'token':'test-only'}
        with patch('acquisition.adapters.turso.database.Http', return_value=self.database.send):
            app = build_intake(None, clock=lambda:NOW, remote_storage=settings)
        company = app.save_company('intake','writer','company',CompanyDraft(company_name='Synthetic \u2014 input'))['snapshot']
        objective = 'Preserve exact input \u2014 including punctuation'
        draft = CampaignBriefDraft(company['id'],1,objective=objective,budget_minor=9007199254740991//10000000)
        original = app.store.database.send
        def lose_ack(payload):
            result = original(payload)
            if any(r.get('stmt',{}).get('sql')=='COMMIT' for request in payload['requests'] for r in request.get('batch',{}).get('steps',[])):
                raise RemoteUnavailable('lost intake acknowledgement')
            return result
        app.store.database.send = lose_ack
        with self.assertRaises(CommitUncertain):app.save_brief('intake','writer','brief',draft)
        restarted = CampaignIntake(SqliteCampaignIntake(self.wire.database()), lambda:NOW+1)
        receipt = restarted.save_brief('intake','writer','brief',draft)
        self.assertTrue(receipt['replayed'])
        self.assertEqual(receipt['snapshot']['saved_at'], NOW)
        self.assertEqual(restarted.brief('intake',receipt['snapshot']['id']),receipt['snapshot'])
        restarted.save_company('intake','writer','edit',CompanyDraft(company_name='New'),company_id=company['id'],expected_revision=1)
        self.assertEqual(restarted.company('intake',company['id'],1),company)
        self.assertEqual(restarted.company('intake',company['id'],1)['draft']['company_name'],'Synthetic \u2014 input')
        self.assertEqual(restarted.brief('intake',receipt['snapshot']['id'])['draft']['objective'],objective)
        self.assertEqual(receipt['snapshot']['draft']['company_revision'],1)
        self.assertEqual(restarted.briefs('foreign'),[])
        with self.assertRaises(NotFound):restarted.brief('foreign',receipt['snapshot']['id'])
        with self.assertRaises(NotFound):restarted.save_brief('foreign','writer','forged-reference',draft)
        with self.assertRaises(Conflict):restarted.save_brief('intake','writer','brief',replace(draft,objective='Changed'))
        with self.database.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM intake_brief_revisions WHERE organization=?',('intake',)).fetchone()[0],1)

    def test_remote_intake_competing_writes_and_failed_migration_are_atomic(self):
        from unittest.mock import patch
        from acquisition.campaigns import CampaignIntake
        from acquisition.creative import CompanyDraft
        from acquisition.adapters.sqlite.intake import SqliteCampaignIntake, INTAKE
        app = CampaignIntake(SqliteCampaignIntake(self.database), lambda:NOW)
        first = app.save_company('intake','writer','create',CompanyDraft())['snapshot']
        gate = threading.Barrier(2)
        def save(index):
            independent = CampaignIntake(SqliteCampaignIntake(self.wire.database()),lambda:NOW)
            gate.wait(timeout=5)
            try:
                return independent.save_company('intake','writer','edit-'+str(index),CompanyDraft(company_name=str(index)),
                                                company_id=first['id'],expected_revision=1)
            except Conflict:return 'conflict'
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(save,range(2)))
        self.assertEqual(results.count('conflict'),1)
        self.assertEqual(app.company('intake',first['id'])['revision'],2)
        other = Wire(Path(self.temp.name)/'intake-migration.sqlite')
        try:
            db = other.database(True)
            with db.transaction() as connection:
                for table in ('youtube_revocations','youtube_approvals','youtube_results','youtube_interactions',
                              'youtube_preparations','youtube_requests','youtube_revisions'):
                    connection.execute('DROP TABLE '+table)
                for table in ('preparation_contexts','intake_planning_sources','intake_requests','intake_brief_revisions','intake_company_revisions'):connection.execute('DROP TABLE '+table)
                connection.execute('PRAGMA user_version=23')
            original = TursoDatabase._apply_migration
            def fail(connection, script):
                original(connection,script)
                if script == INTAKE:raise OSError('after intake remote DDL')
            with patch.object(TursoDatabase,'_apply_migration',side_effect=fail):
                with self.assertRaises(OSError):db._initialize(False,lambda:NOW,False)
            with db.connect() as connection:
                self.assertEqual(connection.execute('PRAGMA user_version').fetchone()[0],23)
                self.assertIsNone(connection.execute("SELECT 1 FROM sqlite_master WHERE name='intake_requests'").fetchone())
            db._initialize(False,lambda:NOW,False)
            with db.connect() as connection:self.assertEqual(connection.execute('PRAGMA user_version').fetchone()[0],28)
            from acquisition.adapters.sqlite.intake_planning import INTAKE_PLANNING
            from acquisition.adapters.sqlite.preparation_context import PREPARATION_CONTEXTS
            with db.transaction() as connection:
                for table in ('youtube_revocations','youtube_approvals','youtube_results','youtube_interactions',
                              'youtube_preparations','youtube_requests','youtube_revisions'):
                    connection.execute('DROP TABLE '+table)
                connection.execute('DROP TABLE preparation_contexts')
                connection.execute('DROP TABLE intake_planning_sources')
                connection.execute('PRAGMA user_version=24')
            def fail_planning(connection, script):
                original(connection, script)
                if script == INTAKE_PLANNING:raise OSError('after planning source DDL')
            with patch.object(TursoDatabase,'_apply_migration',side_effect=fail_planning), self.assertRaises(OSError):
                db._initialize(False,lambda:NOW,False)
            with db.connect() as connection:
                self.assertEqual(connection.execute('PRAGMA user_version').fetchone()[0],24)
                self.assertIsNone(connection.execute("SELECT 1 FROM sqlite_schema WHERE name='intake_planning_sources'").fetchone())
            db._initialize(False,lambda:NOW,False)
            with db.connect() as connection:self.assertEqual(connection.execute('PRAGMA user_version').fetchone()[0],28)
            from acquisition.adapters.sqlite.preparation_context import PREPARATION_CONTEXTS
            with db.transaction() as connection:
                connection.execute('DROP TABLE preparation_contexts')
                connection.execute('PRAGMA user_version=26')
            def fail_context(connection, script):
                original(connection,script)
                if script == PREPARATION_CONTEXTS:raise OSError('after reviewed preparation DDL')
            with patch.object(TursoDatabase,'_apply_migration',side_effect=fail_context),self.assertRaises(OSError):
                db._initialize(False,lambda:NOW,False)
            with db.connect() as connection:
                self.assertEqual(connection.execute('PRAGMA user_version').fetchone()[0],26)
                self.assertIsNone(connection.execute("SELECT 1 FROM sqlite_schema WHERE name='preparation_contexts'").fetchone())
            db._initialize(False,lambda:NOW,False)
            with db.connect() as connection:self.assertEqual(connection.execute('PRAGMA user_version').fetchone()[0],28)
        finally:other.close()

    def test_saved_intake_planning_uses_native_harness_over_hrana_wire(self):
        from unittest.mock import patch
        from acquisition.bootstrap import build
        from acquisition.campaigns import CampaignIntake, CampaignBriefDraft
        from acquisition.creative import CompanyDraft
        from acquisition.reasoning import ModelConfig
        from acquisition.adapters.sqlite.intake import SqliteCampaignIntake
        from test_intake_planning import IntakeModel
        intake = CampaignIntake(SqliteCampaignIntake(self.database), lambda:NOW)
        company = intake.save_company('intake','writer','company',CompanyDraft(company_name='Aster',description='Unverified source'))['snapshot']
        brief = intake.save_brief('intake','writer','brief',CampaignBriefDraft(company['id'],1,objective='Explore retail clients',
                    audience='Independent retailers',country='UK',currency='GBP',budget_minor=12345,channels=('email',)))['snapshot']
        model = IntakeModel()
        with patch('acquisition.bootstrap.build_database',return_value=self.database):
            app = build(None,clock=lambda:NOW,gateway=model,model_config=ModelConfig('test/model',max_calls=2,force_tool_choice=True))
        with patch.object(app.tasks,'create',side_effect=OSError('after planning row before runtime commit')):
            with self.assertRaises(OSError):app.intake_planning.request('intake','writer','plan',brief['id'],1)
        later = CampaignBriefDraft(company['id'],1,objective='A later brief',audience='Independent retailers',
                    country='UK',currency='GBP',budget_minor=12345,channels=('email',))
        intake.save_brief('intake','writer','edit',later,brief_id=brief['id'],expected_revision=1)
        with self.assertRaisesRegex(Conflict,'original staged'):
            app.intake_planning.request('intake','writer','later-plan',brief['id'],2)
        self.assertEqual(model.requests,[])
        with self.database.connect() as db:
            self.assertEqual(db.execute('SELECT revision FROM conversations WHERE organization=?',('intake',)).fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM intake_planning_sources').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM runs').fetchone()[0],0)
        run = app.intake_planning.request('intake','writer','plan',brief['id'],1)
        app.worker.drain('intake',run_id=run)
        view = app.intake_planning.view('intake','plan')
        self.assertEqual(view['plan']['status'],'succeeded',view)
        self.assertEqual(view['plan']['result']['requirements'],brief['draft'])
        self.assertEqual(view['source']['company'],company)
        self.assertEqual(app.intake_planning.request('intake','writer','plan',brief['id'],1),run)
        app.worker.drain('intake',run_id=run)
        self.assertEqual(len(model.requests),1)
        from acquisition.campaigns import PreparationReview, ReviewedPreparation
        from acquisition.adapters.sqlite.preparation_context import SqlitePreparationContexts
        contexts=ReviewedPreparation(SqlitePreparationContexts(self.database),lambda:NOW)
        preview=contexts.preview('intake',brief['id'],2)
        review=PreparationReview(brief['id'],2,preview['id'],0,(),True,False,7,
                                 'Reviewed exact source inputs.',confirmed=True)
        original_send=self.database.send
        def lost_context_ack(payload):
            result=original_send(payload)
            if any(step.get('stmt',{}).get('sql')=='COMMIT' for request in payload['requests'] for step in request.get('batch',{}).get('steps',[])):
                raise RemoteUnavailable('lost reviewed-context commit reply')
            return result
        self.database.send=lost_context_ack
        try:
            with self.assertRaises(CommitUncertain):contexts.confirm('intake','writer','context',review)
        finally:self.database.send=original_send
        reopened=ReviewedPreparation(SqlitePreparationContexts(self.wire.database()),lambda:NOW+1)
        receipt=reopened.confirm('intake','writer','context',review)
        self.assertTrue(receipt['replayed']);self.assertEqual(receipt['context']['reviewed_at'],NOW)
        self.assertEqual(receipt['context']['requirements']['objective'],'A later brief')
        self.assertEqual(receipt['context']['generation'],'unavailable')
        preview=reopened.preview('intake',brief['id'],2)
        from dataclasses import replace
        current=replace(review,preview_id=preview['id'],expected_context_revision=1)
        barrier=threading.Barrier(2)
        def compete(index):
            service=ReviewedPreparation(SqlitePreparationContexts(self.wire.database()),lambda:NOW+1)
            barrier.wait(timeout=5)
            try:return service.confirm('intake','writer','context-'+str(index),current)
            except Conflict:return 'conflict'
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(compete,range(2)))
        self.assertEqual(results.count('conflict'),1)
        self.assertEqual(len(model.requests),1)
        with self.database.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM preparation_contexts').fetchone()[0],2)
            self.assertEqual(db.execute('SELECT count(*) FROM intake_planning_sources').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM review_decisions').fetchone()[0],0)
        # This PR's unpublished schema 26 had reviewed inputs but no YouTube tables.
        with self.database.transaction() as db:
            for table in ('youtube_revocations','youtube_approvals','youtube_results','youtube_interactions',
                          'youtube_preparations','youtube_requests','youtube_revisions'):
                db.execute('DROP TABLE '+table)
            original_contexts=[tuple(r) for r in db.execute('SELECT * FROM preparation_contexts ORDER BY revision')]
            db.execute('PRAGMA user_version=26')
        with patch('acquisition.bootstrap.build_database',return_value=self.wire.database(True)):
            upgraded = build(None,clock=lambda:NOW,gateway=model,model_config=ModelConfig('test/model',max_calls=2,force_tool_choice=True))
        self.assertEqual(upgraded.intake_planning.request('intake','writer','plan',brief['id'],1),run)
        self.assertEqual(upgraded.intake_planning.view('intake','plan'),view)
        with upgraded.tasks.database.connect() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],28)
            self.assertEqual([tuple(r) for r in db.execute('SELECT * FROM preparation_contexts ORDER BY revision')],original_contexts)
        migrated=ReviewedPreparation(SqlitePreparationContexts(self.wire.database()),lambda:NOW+2)
        self.assertEqual(migrated.confirm('intake','writer','context',review)['context'],receipt['context'])
        upgraded.worker.drain('intake',run_id=run)
        self.assertEqual(len(model.requests),1)

    def test_unpadded_remote_blobs_preserve_exact_bytes(self):
        self.assertEqual(decode({'type':'blob','base64':'ZXhhY3Q'}),b'exact')

    def test_exact_named_bindings_types_and_row_access(self):
        with self.database.connect() as db:
            row = db.execute("SELECT :b AS b, :a AS a, :b AS again, ':ignored' AS literal -- :comment\n", {'a':2**60,'b':b'bytes'}).fetchone()
            self.assertEqual(tuple(row),(b'bytes',2**60,b'bytes',':ignored'))
            self.assertEqual(dict(row),{'b':b'bytes','a':2**60,'again':b'bytes','literal':':ignored'})
            with closing(sqlite3.connect(':memory:')) as native:
                for sql,args in [('SELECT :x,@x,?1,?2',{'x':b'bytes'}),
                                 ('SELECT ?01,?1',{'01':2**60}),('SELECT ?,?1',{'1':'same'})]:
                    self.assertEqual(tuple(db.execute(sql,args).fetchone()),native.execute(sql,args).fetchone())

    def test_float_bindings_preserve_native_bits_types_and_parameter_slots(self):
        import random,struct
        rng=random.Random(1234)
        values=[1795379458.2227573,0.,-0.,5e-324,-5e-324,1.7976931348623157e308]
        values += [n for _ in range(128) if math.isfinite(n:=struct.unpack('d',rng.randbytes(8))[0])]
        self.wire.round_float_bindings=True
        with self.database.connect() as db,closing(sqlite3.connect(':memory:')) as native:
            for value in values:
                with self.subTest(value=value):
                    sql="SELECT ?2,?1,?2,typeof(?2),'?2 :ignored',1 AS [?:quoted] /* ?99 */ -- ?88\n"
                    args=(7,value)
                    expected=native.execute(sql,args).fetchone();actual=tuple(db.execute(sql,args).fetchone())
                    self.assertEqual(actual[1:],expected[1:])
                    self.assertEqual(struct.pack('d',actual[0]),struct.pack('d',expected[0]))
            sql='SELECT :x,@y,:x,$z::part(suffix),typeof(:x),7 AS "a$b"'
            args={'x':1795379458.2227573,'y':-5e-324,'z::part(suffix)':2.2007250832970862e129}
            self.assertEqual(tuple(db.execute(sql,args).fetchone()),native.execute(sql,args).fetchone())
            sql='SELECT :x\u0301,typeof(:x\u0301),\u0301a$b FROM (SELECT 9 AS \u0301a$b)'
            args={'x\u0301':1795379458.2227573}
            self.assertEqual(tuple(db.execute(sql,args).fetchone()),native.execute(sql,args).fetchone())
            for marker in ('$a::','$a::::b','$a::b::','$a::(x)',':a::','@a::','$::a',':::a',
                           '$a(quoted\'?)','$a()','$a$b'):
                with self.subTest(marker=marker):
                    sql='SELECT '+marker+',typeof('+marker+')';args={marker[1:]:1795379458.2227573}
                    self.assertEqual(tuple(db.execute(sql,args).fetchone()),native.execute(sql,args).fetchone())
            sql="SELECT ?1,?1,?3,?,?1,'literal '' ?9',`a?b` FROM (SELECT 9 AS `a?b`)"
            args=(1795379458.2227573,0,-5e-324,2.5)
            self.assertEqual(tuple(db.execute(sql,args).fetchone()),native.execute(sql,args).fetchone())
            aliases=[('SELECT :x,?1,typeof(?1)',{'x':1.5}),
                ('SELECT :x,?1,:y,?2',{'x':1795379458.2227573,'y':-5e-324}),
                ('SELECT :x,@x,?1,?2',{'x':1.5}),
                ('SELECT ?1,?01,?001',{'1':1.5}),('SELECT ?01,?1',{'01':1.5}),
                ('SELECT ?,?1',{'1':1.5}),('SELECT ?,?01',{'01':-0.0}),
                ('SELECT ?3,:x,?4,?1,?2',{'1':1.0,'2':-0.0,'3':1.5,'x':5e-324}),
                ('SELECT :x,?1',{'x':1.5,'1':99.5})]
            for sql,args in aliases:
                with self.subTest(aliases=sql):
                    expected=native.execute(sql,args).fetchone()
                    actual=tuple(db.execute(sql,args).fetchone())
                    self.assertEqual(actual,expected)
                    for a,e in zip(actual,expected):
                        if isinstance(e,float):self.assertEqual(struct.pack('d',a),struct.pack('d',e))
            for sql,args in [('SELECT ?,?3',{'3':1.5}),('SELECT :x,?1',{'1':1.5})]:
                with self.assertRaises(sqlite3.ProgrammingError):native.execute(sql,args)
                with self.assertRaises(ValueError):db.execute(sql,args)

    def test_float_comparisons_and_updates_preserve_native_affinity(self):
        self.wire.round_float_bindings=True
        with closing(sqlite3.connect(':memory:')) as native,self.database.transaction() as db:
            for affinity in ('TEXT','NUMERIC','REAL','INTEGER','BLOB'):
                table='affinity_'+affinity
                schema='CREATE TABLE '+table+'(id INTEGER PRIMARY KEY,x '+affinity+',marked INTEGER DEFAULT 0)'
                native.execute(schema);db.execute(schema)
                for i,value in enumerate(('1.00','1.0','1','1.5','1.50','0.0',None,b'1')):
                    sql='INSERT INTO '+table+'(id,x) VALUES(?,?)'
                    native.execute(sql,(i,value));db.execute(sql,(i,value))
                for value in (1.0,1.5,-0.0):
                    for predicate in ('x=?','?=x','x<>?','x<?','?<x','x>=?','?>=x',
                                      'x IN (SELECT ?)','? IN (SELECT x FROM '+table+')',
                                      'x BETWEEN ? AND 2','? BETWEEN x AND 2',
                                      'x=CAST(? AS REAL)','CASE x WHEN ? THEN 1 ELSE 0 END=1'):
                        with self.subTest(affinity=affinity,value=value,predicate=predicate):
                            sql='SELECT id FROM '+table+' WHERE '+predicate+' ORDER BY id'
                            expected=native.execute(sql,(value,)).fetchall()
                            self.assertEqual([tuple(r) for r in db.execute(sql,(value,))],expected)
                sql='UPDATE '+table+' SET marked=1 WHERE x=?'
                expected=native.execute(sql,(1.0,)).rowcount
                self.assertEqual(db.execute(sql,(1.0,)).rowcount,expected)
                sql='SELECT id FROM '+table+' WHERE marked=1 ORDER BY id'
                self.assertEqual([tuple(r) for r in db.execute(sql)],native.execute(sql).fetchall())

    def test_unknown_transaction_is_not_replayed_or_acknowledged(self):
        original = self.database.send
        def lose_commit(payload):
            if any(r.get('stmt',{}).get('sql')=='COMMIT' for request in payload['requests'] for r in request.get('batch',{}).get('steps',[])):
                raise RemoteUnavailable('unknown',reason='transport_timeout')
            return original(payload)
        self.database.send = lose_commit
        with self.assertRaises(CommitUncertain) as uncertain:
            with self.database.transaction() as db:db.execute('CREATE TABLE never_acknowledged(id)')
        self.assertEqual(uncertain.exception.reason,'transport_timeout')
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
                self.assertEqual(raw.execute('select version from acquisition_schema').fetchone()[0],28)
        finally:other.close()

    def test_concurrent_fresh_initializers_converge_without_partial_schema(self):
        other = Wire(Path(self.temp.name)/'initializers.sqlite')
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(lambda _:other.database(True),range(2)))
            with closing(sqlite3.connect(other.path)) as raw:
                self.assertEqual(raw.execute('select version from acquisition_schema').fetchall(),[(28,)])
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
            for table in ('youtube_revocations','youtube_approvals','youtube_results','youtube_interactions',
                          'youtube_preparations','youtube_requests','youtube_revisions',
                          'preparation_contexts', 'intake_planning_sources', 'intake_requests', 'intake_brief_revisions', 'intake_company_revisions'):
                db.execute('DROP TABLE '+table)
            db.execute('DROP TRIGGER conversation_company_contract_immutable')
            db.execute('DROP TRIGGER conversation_company_contract_no_replace')
            db.execute('ALTER TABLE conversations DROP COLUMN product_contract')
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


    def test_imported_report_snapshot_survives_string_wire_rowids_and_reopen(self):
        from unittest.mock import patch
        from acquisition.entrypoints.review_demo import run_review_demo
        from acquisition.adapters.sqlite.learning import SqliteLearning
        from acquisition.contracts import digest
        now = [NOW]
        with patch('acquisition.bootstrap.build_database', return_value=self.database):
            app = build(None, clock=lambda:now[0])
        demo = run_review_demo(app, 'wire-learning', 'fixture',
                               Path(self.temp.name)/'review', str(self.path))
        org, actor = demo['organization'], 'demo-operator'
        opened = app.learning.open(org,demo['case_id'],actor,'open')
        cohort = opened['cohort_id']
        accepted = app.learning.source.accepted(org,demo['case_id'])
        now[0] = opened['window_end']
        report = {key:accepted[key] for key in ('organization','job_id','metric','window_start','window_end')}
        report.update(schema='synthetic-provider-report/v1',mode='SYNTHETIC_ONLY',
            cohort_id=cohort,report_id='wire-report',final=False,watermark=now[0],page_count=1,
            pages=[{'report_id':'wire-report','number':1,'events':[{
                'event_id':'synthetic_event_'+digest({'cohort_id':cohort,
                    'business_id':accepted['members'][0]['business_id']}),'outcome':accepted['members'][0] | {
                    'response':True,'observed_at':opened['window_start']+1}}]}])
        receipt = app.learning.store.ingest_report(org,actor,'import',cohort,report)
        self.assertEqual(receipt['added'],1)
        # Read through a fresh connection after the import transaction commits.
        reopened = SqliteLearning(self.wire.database(),lambda:now[0])
        saved = reopened.report_snapshot(org,cohort,'wire-report')
        self.assertEqual(saved['import_receipt']['report_sha256'],digest(saved['snapshot']))
        self.assertEqual(saved['snapshot']['report_id'],'wire-report')
        self.assertEqual(saved['import_receipt'],receipt | {'actor':actor})
        with closing(sqlite3.connect(self.path)) as raw:
            imported = raw.execute("SELECT sequence FROM learning_events WHERE organization=? AND kind='provider_report_imported'",(org,)).fetchone()[0]
            referenced = json.loads(raw.execute("SELECT payload FROM learning_events WHERE organization=? AND kind='provider_report_source_recorded'",(org,)).fetchone()[0])['import_sequence']
            self.assertIs(type(referenced),int)
            self.assertEqual(referenced,imported)


    def test_cursor_preserves_null_and_integer_rowid_precision(self):
        from acquisition.adapters.turso.transport import Cursor
        for wire, expected in ((None,None),('9007199254740993',9007199254740993)):
            with self.subTest(rowid=wire):
                cursor = Cursor({'cols':[],'rows':[],'affected_row_count':0,'last_insert_rowid':wire})
                self.assertEqual(cursor.lastrowid,expected)
                if expected is not None:self.assertIs(type(cursor.lastrowid),int)
