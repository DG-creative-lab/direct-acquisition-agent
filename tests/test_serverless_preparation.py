"""Real-store operator preparation, cold invocations and HTTP authority boundaries."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from acquisition.bootstrap import build_database, build_hosted_preparations
from acquisition.adapters.http.serverless_preparation import preparation_handler
from acquisition.contracts import Conflict, NotFound
from acquisition.reasoning import ModelError
from acquisition.runtime import LeaseLost

NOW=1795305600.


class HostedPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'app.sqlite';build_database(self.path)
        self.now=[NOW]
    def service(self,organization='operator',gateway=None):
        return build_hosted_preparations(self.path,organization,lambda:self.now[0],_gateway=gateway)
    def start(self):return self.service().start('start','fielddesk',10000,True)
    def snapshot(self):
        with closing(sqlite3.connect(self.path)) as db:return list(db.iterdump())
    def cold(self, action, **values):
        script="""import json,sys
from acquisition.bootstrap import build_hosted_preparations
s=build_hosted_preparations(sys.argv[1],'operator',lambda:float(sys.argv[2]))
print(json.dumps(getattr(s,sys.argv[3])(**json.loads(sys.argv[4]))))
"""
        result=subprocess.run([sys.executable,'-c',script,str(self.path),str(self.now[0]),action,json.dumps(values)],
                              check=True,capture_output=True,text=True)
        return json.loads(result.stdout)
    def at_generation(self):
        current=self.start();jid=current['receipt']['journey_id']
        for stage in range(3):self.service().advance(jid,stage)
        service=self.service();row=service.journeys.store.get('operator',jid)
        app=service.journeys.host.capabilities(row['inputs'],False)
        # Admit the exact original native task, as if an invocation ended before
        # saving coordinator progress. No replacement command is constructed.
        from acquisition.conversations import journey_commands
        command=journey_commands(jid)['initial'];native=row['inputs']['native_organization']
        run=app.channels.start(native,command,'fielddesk',row['outputs']['email-contexts'],'email')
        return jid,app,native,run

    def test_duplicate_start_changed_inputs_and_cold_resume_to_unapproved_review(self):
        barrier=threading.Barrier(2)
        def start(_):barrier.wait();return self.start()['receipt']
        with ThreadPoolExecutor(max_workers=2) as workers:receipts=list(workers.map(start,range(2)))
        self.assertEqual(receipts[0],receipts[1]);jid=receipts[0]['journey_id']
        with self.assertRaises(Conflict):self.service().start('start','iwoca',10000,True)
        with self.assertRaises(Conflict):self.service().start('start','fielddesk',20000,True)
        before=self.snapshot()
        for _ in range(3):self.cold('status',journey_id=jid)
        self.assertEqual(self.snapshot(),before)
        for stage in range(7):
            state=self.cold('advance',journey_id=jid,expected_stage=stage)
            self.assertEqual(state['progress']['stage'],stage+1)
            before=self.snapshot()
            replay=self.cold('advance',journey_id=jid,expected_stage=stage)
            self.assertEqual(replay['observation'],'already_advanced')
            self.assertEqual(self.snapshot(),before)
        self.assertEqual(state['progress']['status'],'ready')
        self.assertTrue(state['progress']['review']['validation']['review_ready'])
        frozen=self.service().journeys.store.get('operator',jid)['inputs']
        self.assertEqual(frozen['catalogue']['preparation_cadence'],'synthetic-hourly/v1')
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('select count(*) from sequence_journeys').fetchone()[0],1)
            self.assertEqual(db.execute('select count(*) from channel_preparations').fetchone()[0],3)
            self.assertEqual(db.execute('select count(*) from model_calls').fetchone()[0],9)
            self.assertEqual(db.execute('select count(*) from sequence_review_decisions').fetchone()[0],0)
        with self.assertRaises(NotFound):self.service('foreign').status(jid)

    def test_hourly_demonstration_still_blocks_expired_product_evidence_before_inference(self):
        self.now[0]+=3*86400
        current=self.start();jid=current['receipt']['journey_id']
        for _ in range(3):
            current=self.service().advance(jid,current['progress']['stage'])
            if current['progress']['status']=='blocked':break
        self.assertEqual(current['progress']['status'],'blocked')
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM model_calls').fetchone()[0],0)

    def test_two_invocations_claim_one_native_task_and_late_lease_cannot_publish(self):
        jid,app,native,run=self.at_generation()
        barrier=threading.Barrier(2)
        def claim(_):
            service=self.service();row=service.journeys.store.get('operator',jid)
            channels=service.journeys.host.capabilities(row['inputs'],False).channels
            barrier.wait();return channels.tasks.claim(native,self.now[0],10,run_id=run)
        with ThreadPoolExecutor(max_workers=2) as workers:claims=list(workers.map(claim,range(2)))
        owned=next(c for c in claims if c is not None);self.assertEqual(sum(c is not None for c in claims),1)
        outcome=app.channels.worker.capabilities[owned.capability](owned)
        self.now[0]+=11
        with self.assertRaises(LeaseLost):app.channels.tasks.settle(owned,outcome,self.now[0])
        class NeverRepeat:
            def complete(self,request):raise AssertionError('Recorded inference repeated')
        recovered=self.service(gateway=NeverRepeat()).advance(jid,3)
        self.assertEqual(recovered['progress']['stage'],4)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('select count(*) from model_calls').fetchone()[0],3)
            self.assertEqual(db.execute('select count(*) from channel_artifacts').fetchone()[0],1)

    def test_stop_during_generation_fences_reservation_and_publication(self):
        jid,app,native,run=self.at_generation()
        claim=app.channels.tasks.claim(native,self.now[0],180,run_id=run)
        outcome=app.channels.worker.capabilities[claim.capability](claim)
        self.service().stop(jid,'stop')
        with self.assertRaises((Conflict,LeaseLost)):
            app.channels.tasks.settle(claim,outcome,self.now[0])
        before=self.snapshot();self.cold('advance',journey_id=jid,expected_stage=3)
        self.assertEqual(self.snapshot(),before)
        self.assertEqual(self.service().status(jid)['progress']['status'],'cancelled')
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('select count(*) from channel_artifacts').fetchone()[0],0)

    def test_unknown_and_reserved_inference_cannot_repeat_after_restart(self):
        class Unknown:
            def complete(self,request):raise ModelError('provider_request_failed')
        state=self.start();jid=state['receipt']['journey_id']
        for stage in range(3):self.service().advance(jid,stage)
        blocked=self.service(gateway=Unknown()).advance(jid,3)
        self.assertEqual(blocked['progress']['status'],'blocked')
        before=self.snapshot();self.cold('advance',journey_id=jid,expected_stage=3)
        self.assertEqual(self.snapshot(),before)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('select status from model_calls').fetchall(),[('unknown',)])

    def test_real_process_exit_after_claim_resumes_original_run(self):
        jid,app,native,run=self.at_generation()
        script="""import sys,os
from acquisition.bootstrap import build_hosted_preparations
s=build_hosted_preparations(sys.argv[1],'operator',lambda:float(sys.argv[5]))
r=s.journeys.store.get('operator',sys.argv[2])
c=s.journeys.host.capabilities(r['inputs'],False).channels
assert c.tasks.claim(sys.argv[3],float(sys.argv[5]),1,run_id=sys.argv[4]) is not None
os._exit(0)
"""
        subprocess.run([sys.executable,'-c',script,str(self.path),jid,native,run,str(self.now[0])],check=True)
        self.now[0]+=2
        current=self.cold('advance',journey_id=jid,expected_stage=3)
        self.assertEqual(current['progress']['outputs']['initial-run'],run)
        self.assertEqual(current['progress']['stage'],4)

    def test_http_auth_host_origin_methods_and_input_cannot_select_identity(self):
        token='operator-private-token-'*2
        factory_calls=[]
        def factory():factory_calls.append(True);return self.service()
        handler=preparation_handler(factory,token,{'127.0.0.1'}, {'https://operator.example'})
        server=ThreadingHTTPServer(('127.0.0.1',0),handler)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        def request(method,body=None,headers=None,path='/api/preparation'):
            connection=HTTPConnection(*server.server_address,timeout=20)
            try:
                connection.request(method,path,body=json.dumps(body) if body is not None else None,
                    headers={'Host':'127.0.0.1','Authorization':'Bearer '+token,'Content-Type':'application/json',**(headers or {})})
                response=connection.getresponse();return response.status,json.loads(response.read())
            finally:connection.close()
        try:
            for headers in ({'Authorization':'wrong'},{'Host':'attacker'},{'Origin':'https://attacker'}):
                self.assertEqual(request('POST',{},headers)[0],403)
            self.assertFalse(factory_calls)
            start={'action':'start','request_id':'http','profile_key':'fielddesk','budget_pence':10000,'allow_generation':True}
            for extra in ({'organization':'foreign'},{'role':'reviewer'},{'model':'paid'},{'action':'approve'}):
                self.assertEqual(request('POST',start|extra)[0],400)
            self.assertFalse(factory_calls)
            code,started=request('POST',start);self.assertEqual(code,200)
            jid=started['receipt']['journey_id'];before=self.snapshot()
            for _ in range(3):self.assertEqual(request('GET',path='/api/preparation?journey_id='+jid)[0],200)
            self.assertEqual(self.snapshot(),before)
            self.assertEqual(request('POST',{'action':'continue','journey_id':jid,'expected_stage':0})[0],200)
            before=self.snapshot();request('POST',{'action':'continue','journey_id':jid,'expected_stage':0})
            self.assertEqual(self.snapshot(),before)
        finally:server.shutdown();worker.join();server.server_close()

    def test_exit_after_inference_reservation_stays_uncertain_after_lease_expiry(self):
        state=self.start();jid=state['receipt']['journey_id']
        for stage in range(3):self.service().advance(jid,stage)
        script="""import sys,os
from acquisition.bootstrap import build_hosted_preparations
class Exit:
 def complete(self,request):os._exit(0)
s=build_hosted_preparations(sys.argv[1],'operator',lambda:float(sys.argv[3]),_gateway=Exit())
s.advance(sys.argv[2],3)
raise AssertionError('Gateway was not reached')
"""
        subprocess.run([sys.executable,'-c',script,str(self.path),jid,str(self.now[0])],check=True)
        self.now[0]+=181
        result=self.cold('advance',journey_id=jid,expected_stage=3)
        self.assertEqual(result['progress']['status'],'blocked')
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('select status from model_calls').fetchall(),[('reserved',)])
            self.assertEqual(db.execute('select count(*) from channel_artifacts').fetchone()[0],0)

    def test_stop_before_generation_prevents_any_call_reservation(self):
        jid,app,native,run=self.at_generation()
        claim=app.channels.tasks.claim(native,self.now[0],180,run_id=run)
        self.service().stop(jid,'stop')
        with self.assertRaises(Conflict):app.channels.worker.capabilities[claim.capability](claim)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('select count(*) from model_calls').fetchone()[0],0)

    def test_partial_start_resumes_original_command_without_another_conversation(self):
        service=self.service()
        with patch.object(service.journeys,'send',side_effect=RuntimeError('interrupted admission')):
            with self.assertRaises(RuntimeError):service.start('partial','fielddesk',10000,True)
        with self.assertRaises(Conflict):self.service().start('partial','iwoca',10000,True)
        resumed=self.cold('start',request_id='partial',profile_key='fielddesk',budget_pence=10000,allow_generation=True)
        replay=self.service().start('partial','fielddesk',10000,True)
        self.assertEqual(resumed['receipt'],replay['receipt'])
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('select count(*) from conversations').fetchone()[0],1)
            self.assertEqual(db.execute('select count(*) from sequence_journeys').fetchone()[0],1)
            self.assertEqual(db.execute('select count(*) from model_calls').fetchone()[0],0)


    def test_start_race_between_original_lookup_and_source_read_returns_original(self):
        service=self.service();winner=[]
        def source_after_competing_commit(*args):
            winner.append(self.service().start('race','fielddesk',10000,True))
            raise Conflict('Conversation changed during source lookup')
        with patch.object(service.journeys.store,'source',side_effect=source_after_competing_commit):
            observed=service.start('race','fielddesk',10000,True)
        self.assertEqual(observed['receipt'],winner[0]['receipt'])
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('select count(*) from sequence_journeys').fetchone()[0],1)
            self.assertEqual(db.execute('select count(*) from model_calls').fetchone()[0],0)



class HostedWireTests(unittest.TestCase):
    def setUp(self):
        from test_turso_storage import Wire
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'wire.sqlite'
        self.wire=Wire(self.path);self.db=self.wire.database(True);self.now=[NOW]
    def tearDown(self):self.wire.close();self.temp.cleanup()
    def service(self,gateway=None,database=None):
        return build_hosted_preparations(None,'operator',lambda:self.now[0],
            remote_storage={'url':'https://example.turso.io','token':'test-only'},
            _database=database or self.wire.database(),_gateway=gateway)
    def snapshot(self):
        with closing(sqlite3.connect(self.path)) as db:return list(db.iterdump())
    def test_shared_remote_wire_preparation_and_read_only_status(self):
        state=self.service().start('wire','fielddesk',10000,True);jid=state['receipt']['journey_id']
        for stage in range(7):
            state=self.service().advance(jid,stage)
            self.assertEqual(state['progress']['stage'],stage+1)
        self.assertEqual(state['progress']['status'],'ready')
        before=self.snapshot()
        for _ in range(3):self.service().status(jid)
        self.assertEqual(before,self.snapshot())
    def test_expired_io_budget_leaves_reserved_call_fenced_on_fresh_invocation(self):
        state=self.service().start('budget','fielddesk',10000,True);jid=state['receipt']['journey_id']
        for stage in range(3):self.service().advance(jid,stage)
        db=self.wire.database()
        class Expire:
            def complete(inner,request):
                from acquisition.adapters.channel_fixtures import OfflineChannelModel
                response=OfflineChannelModel().complete(request)
                db.send.deadline=time.monotonic()-1
                return response
        from acquisition.adapters.turso import RemoteUnavailable
        with self.assertRaises(RemoteUnavailable):self.service(Expire(),db).advance(jid,3)
        self.now[0]+=181
        class NeverRepeat:
            def complete(self,request):raise AssertionError('Uncertain inference repeated')
        result=self.service(NeverRepeat()).advance(jid,3)
        self.assertEqual(result['progress']['status'],'blocked')
        with closing(sqlite3.connect(self.path)) as raw:
            self.assertEqual(raw.execute('select status from model_calls').fetchall(),[('reserved',)])
            self.assertEqual(raw.execute('select count(*) from channel_artifacts').fetchone()[0],0)
        expired=self.wire.database();expired.send.deadline=time.monotonic()-1
        before=self.snapshot()
        with self.assertRaises(RemoteUnavailable):self.service(database=expired).status(jid)
        self.assertEqual(self.snapshot(),before)


class OperatorPackageTests(unittest.TestCase):
    def test_package_uses_committed_bytes_and_rejects_unsafe_entries(self):
        from scripts import package_serverless_preparation as packaging
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for name in ('src/app.py','config/facts.json','api/preparation.py','public/index.txt',
                         'src/acquisition/entrypoints/serverless_preparation.py','pyproject.toml'):
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('reviewed\n')
            (root/'vercel.json').write_text(json.dumps({'outputDirectory':'public',
                'functions':{'api/preparation.py':{'maxDuration':180}}}))
            subprocess.run(['git','init','-q',str(root)],check=True,capture_output=True)
            subprocess.run(['git','-C',str(root),'add','.'],check=True,capture_output=True)
            def commit():
                subprocess.run(['git','-C',str(root),'-c','user.name=Offline test','-c',
                    'user.email=test@example.invalid','commit','-qm','Reviewed fixture'],check=True,capture_output=True)
            commit()
            (root/'src/app.py').write_text('unreviewed\n')
            (root/'src/.env.private').write_text('do-not-package\n')
            with patch.object(packaging,'ROOT',root):
                manifest=packaging.package(root/'bundle')
                self.assertEqual((root/'bundle/src/app.py').read_text(),'reviewed\n')
                self.assertFalse((root/'bundle/src/.env.private').exists())
                self.assertEqual(len(manifest['source_commit']),40)
                (root/'src/secret.py').symlink_to(root/'src/.env.private')
                subprocess.run(['git','-C',str(root),'add','src/secret.py'],check=True,capture_output=True);commit()
                with self.assertRaises(ValueError):packaging.package(root/'unsafe')
                self.assertFalse((root/'unsafe').exists())


class PersistentTransportTests(unittest.TestCase):
    def setUp(self):
        from acquisition.adapters.turso.transport import Http
        self.requests=[];self.mode='ok'
        owner=self
        class Handler(BaseHTTPRequestHandler):
            protocol_version='HTTP/1.1'
            def log_message(self,*args):pass
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                owner.requests.append((self.client_address,body))
                if owner.mode=='lost':
                    self.connection.shutdown(2);self.connection.close();self.close_connection=True;return
                raw=json.dumps(body).encode()
                self.send_response(307 if owner.mode=='redirect' else 429 if owner.mode=='rate_limit' else 200)
                self.send_header('Location','https://another.turso.io/v3/pipeline')
                self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.http=Http('https://example.turso.io','test-only')
        self.http.url='http://127.0.0.1:'+str(self.server.server_port)+'/v3/pipeline'
        self.addCleanup(self.server.server_close);self.addCleanup(self.thread.join)
        self.addCleanup(self.server.shutdown);self.addCleanup(self.http.close)

    def test_reuses_connection_and_preserves_independent_exact_payloads(self):
        first={'baton':None,'requests':[{'exact':'first'}]};second={'baton':'next','requests':[{'exact':'second'}]}
        self.assertEqual(self.http(first),first);self.assertEqual(self.http(second),second)
        self.assertEqual([r[1] for r in self.requests],[first,second])
        self.assertEqual(self.requests[0][0],self.requests[1][0])

    def test_idle_socket_is_replaced_before_a_single_new_submission(self):
        with patch('acquisition.adapters.turso.transport.time.monotonic',return_value=10):
            self.http({'first':True})
        with patch('acquisition.adapters.turso.transport.time.monotonic',return_value=12):
            self.http({'second':True})
        self.assertEqual([r[1] for r in self.requests],[{'first':True},{'second':True}])
        self.assertNotEqual(self.requests[0][0],self.requests[1][0])

    def test_lost_ack_on_reused_socket_is_not_repeated(self):
        from acquisition.adapters.turso.transport import RemoteUnavailable
        self.http({'first':True});self.mode='lost'
        with self.assertRaises(RemoteUnavailable):self.http({'effect':'uncertain'})
        self.assertEqual([r[1] for r in self.requests],[{'first':True},{'effect':'uncertain'}])
        self.assertIsNone(self.http._connection)

    def test_redirect_and_expired_budget_do_not_send_another_request(self):
        from acquisition.adapters.turso.transport import RemoteUnavailable
        self.mode='redirect'
        with self.assertRaises(RemoteUnavailable):self.http({'first':True})
        self.assertEqual(len(self.requests),1)
        self.mode='rate_limit'
        with self.assertRaises(RemoteUnavailable):self.http({'rate_limited':True})
        self.assertEqual(len(self.requests),2)
        self.http.deadline=time.monotonic()-1
        with self.assertRaises(RemoteUnavailable):self.http({'second':True})
        self.assertEqual(len(self.requests),2)

class TransactionSnapshotTests(unittest.TestCase):
    def setUp(self):
        from test_turso_storage import Wire
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'snapshot.sqlite'
        self.wire=Wire(self.path);self.db=self.wire.database(True);self.db.memoize_transactions=True
        with self.db.transaction() as db:
            db.execute('CREATE TABLE memo_marker(value INTEGER)');db.execute('INSERT INTO memo_marker VALUES(0)')
    def tearDown(self):self.wire.close();self.temp.cleanup()
    def test_writes_invalidate_snapshot_and_new_transactions_observe_current_data(self):
        with self.db.transaction() as db:
            first=db.execute('SELECT value FROM memo_marker');self.assertEqual(first.fetchone()[0],0)
            self.assertEqual(db.execute('SELECT value FROM memo_marker').fetchone()[0],0)
            db.execute('UPDATE memo_marker SET value=1')
            self.assertEqual(db.execute('SELECT value FROM memo_marker').fetchone()[0],1)
        with self.db.connect() as reader:
            self.assertEqual(reader.execute('SELECT value FROM memo_marker').fetchone()[0],1)
            with self.db.transaction() as db:db.execute('UPDATE memo_marker SET value=2')
            self.assertEqual(reader.execute('SELECT value FROM memo_marker').fetchone()[0],2)
        with self.db.transaction() as db:self.assertEqual(db.execute('SELECT value FROM memo_marker').fetchone()[0],2)
    def test_expired_snapshot_cannot_commit_or_dispatch_from_memoized_data(self):
        from acquisition.adapters.turso import CommitUncertain
        dispatched=False
        with self.assertRaises(CommitUncertain):
            with self.db.transaction() as db:
                db.execute('SELECT value FROM memo_marker').fetchone()
                self.wire.sessions[db.baton].execute('ROLLBACK')
                self.assertEqual(db.execute('SELECT value FROM memo_marker').fetchone()[0],0)
            dispatched=True
        self.assertFalse(dispatched)
        with closing(sqlite3.connect(self.path)) as raw:
            self.assertEqual(raw.execute('SELECT value FROM memo_marker').fetchall(),[(0,)])
    def test_functions_are_reexecuted_and_result_cursors_are_independent(self):
        original=self.db.send;queries=[]
        def observed(payload):
            queries.extend(step['stmt']['sql'] for request in payload['requests']
                           for step in request.get('batch',{}).get('steps',[]))
            return original(payload)
        self.db.send=observed
        with self.db.transaction() as db:
            a=db.execute('SELECT value FROM memo_marker');b=db.execute('SELECT value FROM memo_marker')
            self.assertEqual(a.fetchall()[0][0],0);self.assertEqual(b.fetchall()[0][0],0)
            for query,bindings in (("SELECT count(*) FROM memo_marker",()),
                    ("SELECT json_extract(?, '$.value')",('{"value":7}',))):
                self.assertEqual(db.execute(query,bindings).fetchone()[0],db.execute(query,bindings).fetchone()[0])
            for query in ('SELECT random()', 'SELECT random /* volatile */ ()',
                          'SELECT "random"()', 'SELECT CURRENT_TIMESTAMP'):
                db.execute(query).fetchone();db.execute(query).fetchone()
        self.assertEqual(queries.count('SELECT value FROM memo_marker'),1)
        self.assertEqual(queries.count('SELECT random()'),2)
        self.assertEqual(queries.count('SELECT random /* volatile */ ()'),2)
        self.assertEqual(queries.count('SELECT "random"()'),2)
        self.assertEqual(queries.count('SELECT CURRENT_TIMESTAMP'),2)
        self.assertEqual(queries.count('SELECT count(*) FROM memo_marker'),1)
        self.assertEqual(queries.count("SELECT json_extract(?, '$.value')"),1)

    def test_large_bindings_and_rows_are_not_retained_by_the_snapshot_memo(self):
        large='x'*(1024*1024+1)
        original=self.db.send;queries=[]
        def observed(payload):
            queries.extend(step['stmt']['sql'] for request in payload['requests']
                           for step in request.get('batch',{}).get('steps',[]))
            return original(payload)
        self.db.send=observed
        with self.db.transaction() as db:
            db.execute('CREATE TABLE memo_large(payload TEXT)')
            db.execute('INSERT INTO memo_large VALUES(?)',(large,))
            for _ in range(2):self.assertEqual(db.execute('SELECT payload FROM memo_large').fetchone()[0],large)
            for _ in range(2):self.assertEqual(db.execute('SELECT 1 WHERE ? IS NOT NULL',(large,)).fetchone()[0],1)
            self.assertEqual(db.connection._memo_bytes,0)
        self.assertEqual(queries.count('SELECT payload FROM memo_large'),2)
        self.assertEqual(queries.count('SELECT 1 WHERE ? IS NOT NULL'),2)
