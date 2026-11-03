"""Resume source-bound admissions saved by the preceding storage-only slice."""
import json
import unittest
from dataclasses import asdict, replace
from unittest.mock import patch

from acquisition.bootstrap import build
from acquisition.campaigns import Brief
from acquisition.adapters.synthetic import generate
from acquisition.contracts import Conflict
from acquisition.reasoning import ModelConfig
import test_conversation_actions as actions
import test_copy_revisions as revisions
from test_legacy_action_replay import durable_rows, subprocess_replay


def request_row(app, organization, request_id):
    with app.tasks.database.connect() as db:
        return tuple(db.execute('SELECT * FROM admission_requests WHERE organization=? AND request_id=?',
                                (organization,request_id)).fetchone())


class PreEntrypointRoutingRecoveryTests(unittest.TestCase):
    setUp=actions.ConversationActionTests.setUp

    def stage(self, key='old-route', *, admitted=False):
        app=self.w._conversation_app(with_model=True);org='local-conversations'
        row=app.actions.admit(org,self.c,'old-route',1,'What should I change next?',False,self.w.action_context(self.c,1))
        refs={'action_id':row['id']}
        intent=app.admissions.store.request_workflow(org,key,'routing',refs,allow_model=True,model_config=app.actions.config)
        self.assertNotIn('entrypoint',app.admissions.store.request_inputs(org,key))
        receipt=app.admissions.store.admit(intent,self.now) if admitted else None
        app.admissions.store.seal_legacy_writes()
        return app,org,row,intent,receipt

    def test_staged_route_resumes_original_identity_in_a_fresh_process_without_rewriting(self):
        app,org,row,intent,_=self.stage();saved=request_row(app,org,intent.request_id)
        before_calls=len(self.gateway.routing_requests)
        result=subprocess_replay(self.root/'conversations.sqlite',org,row['id'],row['model_config'],'routing')
        self.assertEqual(result.returncode,0,result.stderr)
        run=json.loads(result.stdout)['run_id'];receipt=app.admissions.store.find_request(org,intent.request_id)
        self.assertEqual(receipt.run_id,run)
        self.assertEqual(app.admissions.store.get_request(org,intent.request_id),intent)
        self.assertEqual(request_row(app,org,intent.request_id),saved)
        self.assertEqual(app.tasks.inspect(org,run)['admission']['binding_valid'],True)
        self.assertEqual(app.worker.drain(org,run_id=run),0)
        self.assertEqual(len(self.gateway.routing_requests),before_calls)
        before=durable_rows(app)
        self.assertEqual(app.actions.reconcile(org,row),run)
        self.assertEqual(durable_rows(app),before)

    def test_previously_admitted_route_replays_original_receipt_after_a_later_brief(self):
        app,org,row,intent,receipt=self.stage(admitted=True)
        app.conversations.message(org,self.c,'later',1,'Use a £400 budget instead.')
        saved=request_row(app,org,intent.request_id);before=durable_rows(app)
        reopened=build(self.root/'conversations.sqlite',clock=lambda:self.now,model_config=ModelConfig(**row['model_config']))
        self.assertEqual(reopened.actions.reconcile(org,row),receipt.run_id)
        self.assertEqual(app.admissions.store.find_request(org,intent.request_id),receipt)
        self.assertEqual(request_row(app,org,intent.request_id),saved)
        self.assertEqual(durable_rows(reopened),before)

    def test_storage_slice_key_distinct_from_native_key_resumes_without_a_replacement(self):
        app,org,row,intent,_=self.stage(key='preceding-storage-key')
        saved=request_row(app,org,intent.request_id)
        refs={'action_id':row['id']}
        self.assertIsNone(app.admissions.store.request_for_source('other-org','routing',row['id'],refs))
        with self.assertRaises(Conflict):app.admissions.store.request_for_source(org,'routing',row['id'],{'action_id':'other-action'})
        reopened=build(self.root/'conversations.sqlite',clock=lambda:self.now,model_config=ModelConfig(**row['model_config']))
        run=reopened.actions.reconcile(org,row)
        self.assertEqual(app.admissions.store.find_request(org,'preceding-storage-key').run_id,run)
        self.assertEqual(request_row(app,org,intent.request_id),saved)
        self.assertIsNone(app.admissions.store.get_request(org,'old-route'))
        self.assertEqual(app.worker.drain(org,run_id=run),0)

    def test_old_format_does_not_relax_reference_permission_settings_or_command_checks(self):
        app,org,row,intent,_=self.stage();before=durable_rows(app)
        facade=app.admissions;refs={'action_id':row['id']};cfg=app.actions.config
        cases=[('routing',refs,lambda:{'action_id':'other-action'},True,cfg),
               ('routing',{'action_id':'other-action'},lambda:refs,True,cfg),
               ('routing',refs,lambda:refs,False,cfg),
               ('routing',refs,lambda:refs,1,cfg),
               ('routing',refs,lambda:refs,True,replace(cfg,model='other/model')),
               ('routing',refs|{'extra':'value'},lambda:refs,True,cfg),
               ('standalone-campaign',refs,lambda:refs,True,cfg)]
        for kind,entrypoint,factory,permission,config in cases:
            with self.subTest(kind=kind,entrypoint=entrypoint,permission=permission),self.assertRaises((Conflict,ValueError)):
                facade.workflow(org,intent.request_id,kind,entrypoint,factory,allow_model=permission,config=config)
        # A present null field is not the earlier field-absent format.
        original=facade.store.request_inputs(org,intent.request_id)
        with patch.object(facade.store,'request_inputs',return_value=original|{'entrypoint':None}):
            with self.assertRaises(Conflict):facade.workflow(org,intent.request_id,'routing',refs,lambda:refs,allow_model=True,config=cfg)
        self.assertEqual(durable_rows(app),before)

    def test_missing_entrypoint_does_not_infer_an_old_campaign_command(self):
        app=self.w._conversation_app(with_model=True);org='local-conversations'
        refs={'brief':asdict(Brief('old-campaign',60000)),
              'snapshot_id':app.audiences.put(generate(org,100,42,'2026-10-26'))}
        app.admissions.store.request_workflow(org,'old-campaign-request','standalone-campaign',refs,allow_model=False)
        app.admissions.store.seal_legacy_writes();before=durable_rows(app)
        with self.assertRaises(Conflict):
            app.admissions.workflow(org,'old-campaign-request','standalone-campaign',refs,lambda:refs,allow_model=False,config=None)
        self.assertEqual(durable_rows(app),before)

    def test_changed_source_still_blocks_unadmitted_old_request_without_rewriting(self):
        app,org,row,intent,_=self.stage()
        app.conversations.message(org,self.c,'later',1,'Use a £400 budget instead.')
        before=durable_rows(app)
        with self.assertRaises(Conflict):app.actions.reconcile(org,row)
        self.assertIsNone(app.admissions.store.find_request(org,intent.request_id))
        self.assertEqual(durable_rows(app),before)


class PreEntrypointRevisionRecoveryTests(unittest.TestCase):
    setUp=revisions.CopyRevisionTests.setUp

    def test_revision_source_bound_request_also_resumes_its_older_format_and_key(self):
        revisions.CopyRevisionTests.admit(self)
        native=self.app.reviews.store.revision_request(self.scope,'revision')
        app=self.w._app(self.w._session(self.sid),with_model=True)
        intent=app.admissions.store.request_workflow(self.scope,'preceding-revision-key','copy-revision',
            {'revision_request_id':'revision'},allow_model=True,model_config=app.revisions.config)
        saved=request_row(app,self.scope,intent.request_id);app.admissions.store.seal_legacy_writes()
        with patch.object(app.memory,'put_context',side_effect=AssertionError('Recreated frozen context')):
            run=app.revisions.reconcile(self.scope,native)
        self.assertEqual(app.admissions.store.find_request(self.scope,intent.request_id).run_id,run)
        self.assertEqual(request_row(app,self.scope,intent.request_id),saved)
        before=durable_rows(app)
        self.assertEqual(app.revisions.reconcile(self.scope,native),run)
        self.assertEqual(durable_rows(app),before)
        self.assertEqual(app.worker.drain(self.scope,run_id=run),0)
        self.assertEqual(self.model.revision_calls,[])
