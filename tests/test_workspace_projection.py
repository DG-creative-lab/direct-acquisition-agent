"""Projection recovery must conserve independent application facts and legacy bytes."""
import fcntl
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from acquisition.bootstrap import build_workspace_projection
from acquisition.contracts import Conflict, canonical
from acquisition.workspace import Workspace
from acquisition.conversations import FIXTURE_MESSAGE
from acquisition.reasoning import ModelConfig, ModelError
from acquisition.adapters.sqlite.database import Database
from acquisition.adapters.sqlite.workspace_projection import SqliteWorkspaceProjection
import test_workspace_authority as authority_tests


def records(path):
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)) as db:
        tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        return {table: sorted(db.execute('SELECT * FROM "'+table.replace('"','""')+'"').fetchall(),key=repr) for table in tables}


class WorkspaceProjectionTests(TestCase):
    setUp=authority_tests.WorkspaceAuthorityTests.setUp
    create=authority_tests.WorkspaceAuthorityTests.create
    prepare=authority_tests.WorkspaceAuthorityTests.prepare
    app=authority_tests.WorkspaceAuthorityTests.app
    seed_clock_source=authority_tests.WorkspaceAuthorityTests.seed_clock_source

    def facts(self):
        return {str(p.relative_to(self.root)):records(p) for p in self.root.rglob('*.sqlite') if p.name!='workspace.sqlite'}

    def rebuild(self, **kwargs):return build_workspace_projection(self.root).run(**kwargs)

    def cli(self,*arguments,code=None):
        command=[sys.executable,'-c',code,str(self.root)] if code else [sys.executable,'-m','acquisition.workspace_rebuild','--root',str(self.root),*arguments]
        return subprocess.run(command,capture_output=True,text=True,timeout=25,
                              env=dict(os.environ,PYTHONPATH=str(Path('src').resolve())))

    def remove_projection(self):
        for suffix in ('','-wal','-shm','-journal'):
            (self.root/('workspace.sqlite'+suffix)).unlink(missing_ok=True)

    def legacy(self):
        with self.w.control() as db:
            db.execute('INSERT INTO sessions VALUES(?,?,?)',('legacy-opaque','legacy-hash','{unreadable legacy payload'))
            db.execute('INSERT INTO commands VALUES(?,?,?,?)',('legacy-opaque','command','original',1))
            db.execute('INSERT INTO preparations VALUES(?,?,?,?,?,?,?)',('old-org','legacy-preparation','legacy-request','old-conversation',1,0,'{old frozen consent'))
            db.execute('CREATE TABLE private_legacy(key TEXT PRIMARY KEY,value BLOB)')
            db.execute('INSERT INTO private_legacy VALUES(?,?)',('original',b'\x00\xfforiginal bytes'))
        return records(self.root/'workspace.sqlite')

    def conversation_environment(self):
        root=self.root/'conversation';compat=Workspace(root,real_clock=lambda:self.now)
        c=compat.create_conversation('chat','Original request')['id']
        compat.message_conversation(c,'message',0,FIXTURE_MESSAGE)
        plan=compat.plan_conversation_fixture(c,'plan',1)['current_plan']['result']
        compat._conversation_app().admissions.store.seal_legacy_writes()
        self.root=root;self.w=Workspace(root,real_clock=lambda:self.now)
        result=self.w.draft_conversation(c,'original-draft',1,plan['id'])
        return c,plan['id'],self.w._session(result['session']['id'])

    def test_inspection_is_read_only_and_does_not_load_provider_or_current_guidance(self):
        self.create();self.prepare()
        before=self.facts();control=records(self.root/'workspace.sqlite')
        with patch.object(Database,'transaction',side_effect=AssertionError('Authority write')), \
             patch('acquisition.workspace.OpenRouter',side_effect=AssertionError('Provider loaded')), \
             patch('acquisition.bootstrap.agent_catalogue',side_effect=AssertionError('Current guidance loaded')):
            a=self.rebuild();b=self.rebuild()
        self.assertEqual(a,b);self.assertEqual(a['status'],'inspected');self.assertFalse(a['legacy_migration'])
        self.assertEqual(a['execution_policy'],'verified-paused/v1')
        self.assertEqual(self.facts(),before);self.assertEqual(records(self.root/'workspace.sqlite'),control)

    def test_missing_projection_rebuild_preserves_time_commands_learning_and_paused_runs(self):
        parent=self.create();app,start=self.seed_clock_source(parent)
        self.w.authority.begin(parent['id'],'observe',{'request_id':'observe'})
        self.w.authority.complete(parent['id'],'observe')
        child=self.w._session(self.w.create('child','fixture',parent['id'])['session']['id'])
        cid,preparation=self.prepare()
        self.w.stop_execution(cid,'stop',1)
        expected={s['id']:s for s in self.w.authority.listing()};before=self.facts()
        self.remove_projection()
        inspected=self.cli('inspect');self.assertEqual(inspected.returncode,0,inspected.stderr)
        self.assertFalse((self.root/'workspace.sqlite').exists())
        plan=json.loads(inspected.stdout)['plan_id']
        result=self.cli('--expected-plan',plan,'rebuild')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'],'rebuilt')
        self.assertEqual(self.facts(),before)
        reopened=Workspace(self.root,real_clock=lambda:self.now)
        self.assertEqual({s['id']:s for s in reopened.authority.listing()},expected)
        self.assertEqual(reopened.preparations.store.get('local-conversations',preparation['id'])['inputs'],preparation['inputs'])
        self.assertTrue(reopened.conversation(cid)['execution']['stopped'])
        self.assertEqual(reopened._session(parent['id'])['clock'],start+7*86400)
        self.assertEqual(reopened._session(child['id'])['parent_id'],parent['id'])
        with reopened.control() as db:
            self.assertEqual(db.execute('SELECT done FROM commands WHERE session_id=? AND request_id=?',(parent['id'],'observe')).fetchone()[0],1)
        self.assertEqual(app.worker.drain(parent['organization']),0)
        self.assertEqual(self.facts(),before)

    def test_corrupt_owned_rows_are_rebuilt_without_touching_any_legacy_rows(self):
        session=self.create();legacy=self.legacy();before=self.facts()
        with self.w.control() as db:
            db.execute("UPDATE sessions SET payload='{broken',request_hash='stale' WHERE id=?",(session['id'],))
            rowid=db.execute("SELECT rowid FROM sessions WHERE id='legacy-opaque'").fetchone()[0]
        result=self.rebuild(apply=True)
        self.assertEqual(result['protected_records']['sessions'],1)
        after=records(self.root/'workspace.sqlite')
        for table,rows in legacy.items():
            self.assertEqual([r for r in after[table] if r[0]!=session['id']], [r for r in rows if r[0]!=session['id']])
        with self.w.control() as db:
            self.assertEqual(db.execute('SELECT payload FROM sessions WHERE id=?',(session['id'],)).fetchone()[0],canonical(session))
            self.assertEqual(db.execute("SELECT rowid FROM sessions WHERE id='legacy-opaque'").fetchone()[0],rowid)
        self.assertEqual(self.facts(),before)

    def test_original_conversation_request_lookup_survives_rebuild_and_rejects_changed_inputs(self):
        cid,plan,session=self.conversation_environment();before=self.facts()
        self.remove_projection();self.rebuild(apply=True)
        with self.w.control() as db:
            row=db.execute('SELECT session_id FROM conversation_draft_requests WHERE conversation_id=? AND request_id=?',(cid,'original-draft')).fetchone()
            self.assertEqual(row[0],session['id'])
        replay=self.w.draft_conversation(cid,'original-draft',1,plan)
        self.assertEqual(replay['session']['id'],session['id'])
        with self.assertRaises(Conflict):self.w.draft_conversation(cid,'original-draft',2,plan)
        self.assertEqual(self.facts(),before)

    def test_conflicting_legacy_request_is_reported_and_apply_changes_nothing(self):
        cid,_,session=self.conversation_environment()
        with self.w.control() as db:
            db.execute('INSERT INTO conversation_draft_requests VALUES(?,?,?,?)',(cid,'original-draft','old-hash','legacy-owner'))
        before=records(self.root/'workspace.sqlite');facts=self.facts()
        report=self.rebuild();self.assertEqual(report['status'],'blocked')
        self.assertIn('protected legacy data',report['blocked'][0])
        with self.assertRaises(Conflict):self.rebuild(apply=True)
        self.assertEqual(records(self.root/'workspace.sqlite'),before);self.assertEqual(self.facts(),facts)

    def test_crash_before_commit_rolls_back_and_fresh_process_retries(self):
        session=self.create();self.legacy();before=self.facts()
        with self.w.control() as db:db.execute("UPDATE sessions SET payload='stale' WHERE id=?",(session['id'],))
        control=records(self.root/'workspace.sqlite')
        code='''import os,sys
from unittest.mock import patch
from acquisition.bootstrap import build_workspace_projection
from acquisition.adapters.sqlite.workspace_projection import SqliteWorkspaceProjection
original=SqliteWorkspaceProjection.replace_owned
def crash(db,rows):
    db.execute('PRAGMA cache_size=1')
    original(db,rows)
    os._exit(73)
with patch.object(SqliteWorkspaceProjection,'replace_owned',staticmethod(crash)):
    build_workspace_projection(sys.argv[1]).run(apply=True)
'''
        failed=self.cli(code=code);self.assertEqual(failed.returncode,73,failed.stderr)
        recovered=self.cli('inspect');self.assertEqual(recovered.returncode,0,recovered.stderr)
        self.assertEqual(records(self.root/'workspace.sqlite'),control);self.assertEqual(self.facts(),before)
        retry=self.cli('rebuild');self.assertEqual(retry.returncode,0,retry.stderr)
        self.assertEqual(self.facts(),before);self.assertEqual(self.rebuild()['projection'],'current')

    def test_lost_acknowledgement_after_commit_replays_without_domain_effects(self):
        self.create();self.remove_projection();before=self.facts()
        failed=self.cli(code='''import os,sys
from acquisition.bootstrap import build_workspace_projection
build_workspace_projection(sys.argv[1]).run(apply=True)
os._exit(74)
''')
        self.assertEqual(failed.returncode,74,failed.stderr)
        self.assertEqual(self.rebuild()['projection'],'current')
        self.assertEqual(self.cli('rebuild').returncode,0)
        self.assertEqual(self.facts(),before)

    def test_concurrent_authoritative_change_rolls_back_projection_only(self):
        session=self.create();app=self.app(session)
        control=records(self.root/'workspace.sqlite');original=SqliteWorkspaceProjection.replace_owned
        def changed(db,rows):
            original(db,rows)
            with app.tasks.database.transaction() as source:
                source.execute('UPDATE campaign_environments SET clock=clock+1 WHERE organization=?',(session['organization'],))
        with patch.object(SqliteWorkspaceProjection,'replace_owned',staticmethod(changed)),self.assertRaisesRegex(Conflict,'Authoritative records changed'):
            self.rebuild(apply=True)
        self.assertEqual(records(self.root/'workspace.sqlite'),control)
        self.assertEqual(self.w.authority.get(session['id'])['clock'],session['clock']+1)

    def test_legacy_write_after_inspection_is_not_overwritten(self):
        self.create();service=build_workspace_projection(self.root);original=service.projection.inspect
        def changed(rows):
            result=original(rows)
            with self.w.control() as db:db.execute('INSERT INTO sessions VALUES(?,?,?)',('late-legacy','original','{}'))
            return result
        with patch.object(service.projection,'inspect',side_effect=changed),self.assertRaisesRegex(Conflict,'Projection changed'):
            service.run(apply=True)
        with self.w.control() as db:self.assertEqual(db.execute("SELECT request_hash FROM sessions WHERE id='late-legacy'").fetchone()[0],'original')

    def test_stale_inspection_plan_is_rejected_and_lock_is_released_immediately(self):
        session=self.create();plan=self.rebuild()['plan_id']
        with self.w.control() as db:db.execute("UPDATE sessions SET payload='changed' WHERE id=?",(session['id'],))
        with self.assertRaisesRegex(Conflict,'inspection changed'):self.rebuild(apply=True,expected_plan=plan)
        with (self.root/'server.lock').open('a+') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            fcntl.flock(lock,fcntl.LOCK_UN)

    def test_server_lock_blocks_rebuild_without_any_changes(self):
        self.create();before=self.facts();control=records(self.root/'workspace.sqlite')
        with (self.root/'server.lock').open('a+') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            result=self.cli('rebuild')
        self.assertEqual(result.returncode,2);self.assertIn('Stop the workspace server',result.stderr)
        self.assertEqual(self.facts(),before);self.assertEqual(records(self.root/'workspace.sqlite'),control)

    def test_missing_or_replaced_source_store_is_never_created_or_enrolled(self):
        session=self.create();path=self.app(session).tasks.database.path;backup=path.with_suffix('.saved')
        path.rename(backup);control=records(self.root/'workspace.sqlite')
        with self.assertRaises(ValueError):self.rebuild(apply=True)
        self.assertFalse(path.exists());self.assertEqual(records(self.root/'workspace.sqlite'),control)
        shutil.copyfile(self.root/'conversations.sqlite',path)
        with self.assertRaisesRegex(Conflict,'registered application store'):self.rebuild(apply=True)
        path.unlink();backup.rename(path)

    def test_unreadable_projection_is_preserved_instead_of_replaced(self):
        self.create();self.remove_projection();path=self.root/'workspace.sqlite';path.write_bytes(b'opaque legacy journal')
        before=self.facts()
        with self.assertRaisesRegex(Conflict,'unreadable'):self.rebuild(apply=True)
        self.assertEqual(path.read_bytes(),b'opaque legacy journal');self.assertEqual(self.facts(),before)

    def test_projection_alias_cannot_write_an_authoritative_database(self):
        self.create();self.remove_projection();path=self.root/'workspace.sqlite';source=self.root/'conversations.sqlite'
        before=self.facts()
        for hardlink in (False,True):
            os.link(source,path) if hardlink else path.symlink_to(source)
            with self.assertRaisesRegex(Conflict,'aliases'):self.rebuild(apply=True)
            path.unlink()
        self.assertEqual(self.facts(),before)

    def test_unknown_projection_layout_is_blocked_without_deleting_legacy_rows(self):
        self.create()
        with self.w.control() as db:db.execute('ALTER TABLE commands ADD COLUMN unsupported TEXT')
        control=records(self.root/'workspace.sqlite')
        report=self.rebuild()
        self.assertEqual(report['status'],'blocked');self.assertEqual(report['projection'],'blocked')
        with self.assertRaises(Conflict):self.rebuild(apply=True)
        self.assertEqual(records(self.root/'workspace.sqlite'),control)

    def test_unsealed_store_is_not_implicitly_cut_over(self):
        root=self.root/'legacy';legacy=Workspace(root,real_clock=lambda:self.now)
        legacy.create_conversation('old','Legacy');before=records(root/'conversations.sqlite')
        with self.assertRaisesRegex(Conflict,'already selected'):build_workspace_projection(root).run(apply=True)
        self.assertEqual(records(root/'conversations.sqlite'),before)

    def test_uncertain_legacy_provider_observation_is_preserved_without_activation(self):
        from acquisition.bootstrap import build
        class UnknownProvider:
            def complete(self,request):raise ModelError('provider_request_failed')
        old=build(self.root/'conversations.sqlite',gateway=UnknownProvider(),
                  model_config=ModelConfig('test/model',max_calls=10),clock=lambda:self.now)
        run=old.start_model('legacy-scope','unknown-provider',size=20)
        old.worker.drain('legacy-scope',run_id=run)
        calls=old.calls.inspect('legacy-scope',run)
        self.assertEqual(calls[0]['status'],'unknown')
        self.create();before=self.facts();self.remove_projection()
        report=self.rebuild(apply=True)
        self.assertFalse(report['legacy_migration'])
        self.assertEqual(self.facts(),before)
        self.assertEqual(old.calls.inspect('legacy-scope',run),calls)
        self.assertEqual(old.worker.drain('legacy-scope',run_id=run),0)

    def test_location_only_interruption_is_reported_without_inventing_an_environment(self):
        session=self.create();key='workspace_'+'a'*24
        self.w.authority.store.ensure_location(session|{'id':key,'organization':key,'run_id':None})
        before=self.facts()
        report=self.rebuild(apply=True)
        self.assertEqual(report['pending_locations'],[key])
        self.assertNotIn(key,report['sessions']);self.assertEqual(self.facts(),before)
        with self.w.control() as db:self.assertIsNone(db.execute('SELECT 1 FROM sessions WHERE id=?',(key,)).fetchone())

    def test_invalid_source_releases_root_lock_and_cannot_repair_authority(self):
        session=self.create();app=self.app(session)
        with app.tasks.database.transaction() as db:
            db.execute('DROP TRIGGER environment_intent_no_update')
            db.execute("UPDATE campaign_environments SET fingerprint='bad' WHERE organization=? AND id=?",(session['organization'],session['id']))
        before=self.facts();control=records(self.root/'workspace.sqlite')
        with self.assertRaisesRegex(Conflict,'integrity checks'):self.rebuild(apply=True)
        with (self.root/'server.lock').open('a+') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(lock,fcntl.LOCK_UN)
        self.assertEqual(self.facts(),before);self.assertEqual(records(self.root/'workspace.sqlite'),control)

    def test_missing_root_store_is_not_initialized_by_inspection(self):
        self.assertFalse((self.root/'conversations.sqlite').exists())
        before=sorted(str(p.relative_to(self.root)) for p in self.root.rglob('*'))
        result=self.cli('inspect')
        self.assertEqual(result.returncode,2);self.assertIn('unavailable',result.stderr)
        self.assertEqual(sorted(str(p.relative_to(self.root)) for p in self.root.rglob('*')),before)

    def test_owned_diagnostics_are_discarded_but_legacy_diagnostics_remain(self):
        session=self.create();app,_=self.seed_clock_source(session);org=session['organization']
        # A committed-fact fixture identifies a revision belonging to the owned
        # case. This tests diagnostic ownership, never activation or approval.
        with app.tasks.database.transaction() as db:
            db.execute('INSERT INTO review_commands VALUES(?,?,?,?)',(org,'revision','hash',canonical(
                {'kind':'copy_revision_admission','id':'owned-revision','inputs':{'case_id':'case'}})))
        with self.w.control() as db:
            db.execute('INSERT INTO checkpoint_recovery_blocks VALUES(?,?,?)',(org,session['run_id'],'checkpoint_storage_unavailable'))
            db.execute('INSERT INTO checkpoint_recovery_blocks VALUES(?,?,?)',(org,'legacy-run','checkpoint_authority_unavailable'))
            db.execute('INSERT INTO copy_revision_blocks VALUES(?,?,?)',(org,'owned-revision','configuration_unavailable'))
            db.execute('INSERT INTO copy_revision_blocks VALUES(?,?,?)',(org,'legacy-revision','configuration_unavailable'))
        before=self.facts()
        self.rebuild(apply=True)
        with self.w.control() as db:
            self.assertIsNone(db.execute('SELECT 1 FROM checkpoint_recovery_blocks WHERE organization=? AND run_id=?',(org,session['run_id'])).fetchone())
            self.assertIsNone(db.execute('SELECT 1 FROM copy_revision_blocks WHERE organization=? AND revision_id=?',(org,'owned-revision')).fetchone())
            self.assertIsNotNone(db.execute('SELECT 1 FROM checkpoint_recovery_blocks WHERE organization=? AND run_id=?',(org,'legacy-run')).fetchone())
            self.assertIsNotNone(db.execute('SELECT 1 FROM copy_revision_blocks WHERE organization=? AND revision_id=?',(org,'legacy-revision')).fetchone())
        self.assertEqual(self.facts(),before)
