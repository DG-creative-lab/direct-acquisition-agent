"""Pre-cutover routing/revision replay observes native sources, never new authority."""
import copy
import json
import os
import subprocess
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from acquisition.bootstrap import build
from acquisition.contracts import Conflict, NotFound, canonical
from acquisition.reasoning import ModelConfig
import test_conversation_actions as actions
import test_copy_revisions as revisions


def durable_rows(app):
    with app.tasks.database.connect() as db:
        db.execute('BEGIN')
        tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        return {name:[tuple(r) for r in db.execute('SELECT * FROM "'+name+'"')] for name in tables}


def subprocess_replay(path, organization, key, config, kind):
    script='''import json,sys
from pathlib import Path
from acquisition.bootstrap import build
from acquisition.reasoning import ModelConfig
app=build(Path(sys.argv[1]),model_config=ModelConfig(**json.load(sys.stdin)))
org,key,kind=sys.argv[2:]
source=app.actions.store.get(org,key) if kind=='routing' else app.reviews.store.revision_request(org,key)
run=app.actions.reconcile(org,source) if kind=='routing' else app.revisions.reconcile(org,source)
print(json.dumps({'run_id':run}))
'''
    return subprocess.run([sys.executable,'-c',script,str(path),organization,key,kind],
        input=canonical(config),env=dict(os.environ,PYTHONPATH=str(Path('src').resolve())),
        capture_output=True,text=True,timeout=20)


class LegacyRoutingReplayTests(unittest.TestCase):
    setUp=actions.ConversationActionTests.setUp

    def legacy(self, complete=False):
        app=self.w._conversation_app(with_model=True);org='local-conversations'
        row=app.actions.admit(org,self.c,'legacy-route',1,'What should I change next?',False,self.w.action_context(self.c,1))
        self.assertIsNone(row['alias'])
        run=app.actions.reconcile(org,row)
        if complete:app.worker.drain(org,run_id=run)
        app.admissions.store.seal_legacy_writes()
        return app,org,row,run

    def test_pending_route_replays_in_a_fresh_process_without_admission_or_dispatch(self):
        app,org,row,run=self.legacy();before=durable_rows(app)
        result=subprocess_replay(self.root/'conversations.sqlite',org,row['id'],row['model_config'],'routing')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['run_id'],run)
        self.assertEqual(app.worker.drain(org,run_id=run),0)
        self.assertEqual(self.gateway.routing_requests,[])
        self.assertEqual(durable_rows(app),before)
        self.assertFalse(app.tasks.inspect(org,run)['admission']['binding_valid'])

    def test_completed_route_replays_after_a_later_brief_without_fresh_preflight(self):
        app,org,row,run=self.legacy(complete=True)
        self.assertEqual(app.tasks.inspect(org,run)['run']['status'],'succeeded')
        app.conversations.message(org,self.c,'later',1,'Change the budget to £400.')
        before=durable_rows(app);calls=len(self.gateway.routing_requests)
        reopened=build(self.root/'conversations.sqlite',clock=lambda:self.now,model_config=ModelConfig(**row['model_config']))
        with patch.object(reopened.actions,'preflight',side_effect=AssertionError('Revalidated historical routing')):
            self.assertEqual(reopened.actions.reconcile(org,row),run)
        self.assertEqual(durable_rows(reopened),before)
        self.assertEqual(len(self.gateway.routing_requests),calls)

    def test_route_rejects_changed_native_source_settings_and_internally_valid_task_substitution(self):
        app,org,row,run=self.legacy();before=durable_rows(app)
        for changed in (row|{'context':{}},row|{'inputs':row['inputs']|{'content':'Use another audience'}}):
            with self.assertRaises(Conflict):app.actions.reconcile(org,changed)
        with self.assertRaises(NotFound):app.actions.reconcile('other-org',row)
        wrong=build(self.root/'conversations.sqlite',clock=lambda:self.now,model_config=replace(ModelConfig(**row['model_config']),model='other/model'))
        with self.assertRaises(ValueError):wrong.actions.reconcile(org,row)
        self.assertEqual(durable_rows(app),before)
        # A self-consistent runtime hash alone cannot replace the native source.
        with app.tasks.database.transaction() as db:
            db.execute("UPDATE tasks SET inputs=json_set(inputs,'$.inputs.content','Different instruction') WHERE run_id=?",(run,))
            from acquisition.adapters.sqlite.database import stored_plan_hash
            db.execute('UPDATE runs SET request_hash=? WHERE id=?',(stored_plan_hash(db,run),run))
        before=durable_rows(app)
        with self.assertRaises(Conflict):app.actions.reconcile(org,row)
        self.assertEqual(durable_rows(app),before)


class LegacyRevisionReplayTests(unittest.TestCase):
    setUp=revisions.CopyRevisionTests.setUp

    def legacy(self, complete=False):
        revisions.CopyRevisionTests.admit(self)
        receipt=self.app.reviews.store.revision_request(self.scope,'revision')
        app=self.w._app(self.w._session(self.sid),with_model=True)
        run=app.revisions.reconcile(self.scope,receipt)
        if complete:app.worker.drain(self.scope,run_id=run)
        app.admissions.store.seal_legacy_writes()
        return app,receipt,run

    def test_pending_revision_replays_in_a_fresh_process_without_admission_or_context_writes(self):
        app,receipt,run=self.legacy();before=durable_rows(app)
        result=subprocess_replay(self.root/'conversations.sqlite',self.scope,'revision',receipt['task_inputs']['model_config'],'revision')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['run_id'],run)
        with patch.object(app.memory,'put_context',side_effect=AssertionError('Rewrote historical context')):
            self.assertEqual(app.revisions.reconcile(self.scope,receipt),run)
        self.assertEqual(app.worker.drain(self.scope,run_id=run),0)
        self.assertEqual(self.model.revision_calls,[])
        self.assertEqual(durable_rows(app),before)
        self.assertFalse(app.tasks.inspect(self.scope,run)['admission']['binding_valid'])

    def test_completed_revision_replays_after_publication_and_operator_revocation(self):
        app,receipt,run=self.legacy(complete=True)
        self.assertEqual(app.tasks.inspect(self.scope,run)['run']['status'],'succeeded')
        self.assertIsNotNone(app.reviews.store.revision_publication(self.scope,receipt['id']))
        app.reviews.store.register_actor(self.scope,'local-operator',{'operator'},enabled=False)
        before=durable_rows(app);calls=len(self.model.revision_calls)
        reopened=build(self.root/'conversations.sqlite',clock=lambda:self.now,model_config=ModelConfig(**receipt['task_inputs']['model_config']))
        with patch.object(reopened.memory,'put_context',side_effect=AssertionError('Rewrote historical context')):
            self.assertEqual(reopened.revisions.reconcile(self.scope,receipt),run)
        self.assertEqual(durable_rows(reopened),before)
        self.assertEqual(len(self.model.revision_calls),calls)

    def test_revision_rejects_changed_receipt_settings_and_internally_valid_task_substitution(self):
        app,receipt,run=self.legacy();before=durable_rows(app)
        altered=copy.deepcopy(receipt);altered['inputs']['feedback']='Replace the other letter'
        with self.assertRaises(Conflict):app.revisions.reconcile(self.scope,altered)
        altered=copy.deepcopy(receipt);altered['context']['copy_revision']['feedback']='Invent a claim'
        with self.assertRaises(Conflict):app.revisions.reconcile(self.scope,altered)
        with self.assertRaises((Conflict,NotFound)):app.revisions.reconcile('other-org',receipt)
        wrong=build(self.root/'conversations.sqlite',clock=lambda:self.now,model_config=replace(ModelConfig(**receipt['task_inputs']['model_config']),model='other/model'))
        with self.assertRaises(ValueError):wrong.revisions.reconcile(self.scope,receipt)
        self.assertEqual(durable_rows(app),before)
        with app.tasks.database.transaction() as db:
            db.execute("UPDATE tasks SET inputs=json_set(inputs,'$.target_id','different-target') WHERE run_id=?",(run,))
            from acquisition.adapters.sqlite.database import stored_plan_hash
            db.execute('UPDATE runs SET request_hash=? WHERE id=?',(stored_plan_hash(db,run),run))
        before=durable_rows(app)
        with self.assertRaises(Conflict):app.revisions.reconcile(self.scope,receipt)
        self.assertEqual(durable_rows(app),before)
