"""Shared resources and cancellation tested at actual SQLite effect boundaries."""

import json
import os
import subprocess
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Thread
from unittest.mock import patch

from acquisition.adapters.sqlite.database import Database, EXECUTION, EXECUTION_RECOVERY
from acquisition.contracts import Conflict, NotFound
from acquisition.reasoning import ModelError
from acquisition.workspace import Workspace
import test_conversational_copy_revision as copy_tests
import test_conversation_handoff as handoff_tests


class ExecutionTests(unittest.TestCase):
    setUp = copy_tests.ConversationalCopyRevisionTests.setUp
    route = copy_tests.ConversationalCopyRevisionTests.route
    confirm = copy_tests.ConversationalCopyRevisionTests.confirm

    def usage(self):
        return self.w.conversation(self.c)['execution']

    def lower_limit(self, limit):
        # Test-only resource boundary. No public budget-increase command exists.
        with self.w._conversation_app().calls.database.transaction() as db:
            db.execute('UPDATE conversation_execution SET call_limit=? WHERE organization=? AND conversation_id=?',
                       (limit, 'local-conversations', self.c))

    def test_planning_copy_routing_revision_and_replay_share_one_allowance(self):
        before = self.usage()
        self.assertEqual({r['capability'] for r in before['calls']}, {'conversations.plan.v1','creative.generate_conversation.v3'})
        action = self.route()
        self.assertEqual(self.usage()['used'], before['used']+1)
        self.confirm(action)
        dispatched=[];original=self.model.complete
        def observed(request):
            dispatched.append(request)
            return original(request)
        with patch.object(self.model,'complete',side_effect=observed):
            for _ in range(5):self.w.advance_copy_revisions()
        after = self.usage()
        self.assertEqual(after['used'], before['used']+1+len(dispatched))
        self.assertIn('creative.revise_copy.v3', {r['capability'] for r in after['calls']})
        self.confirm(action,request='observe-confirmation')
        self.w.route_followup(self.c,'edit',1,action['content'],False)
        self.w.advance_actions()
        self.assertEqual(self.usage()['used'],after['used'])
        self.assertEqual(after['limit'],48)
        self.assertEqual(after['remaining'],48-after['used'])

    def test_last_slot_is_atomic_across_two_independent_runs(self):
        before = self.usage()['used'];self.lower_limit(before+1)
        for key in ('first','second'):
            self.w.route_followup(self.c,key,1,'Make variant B more direct. '+key,False)
        app = self.w._conversation_app(with_model=True)
        rows = app.actions.store.listing('local-conversations',self.c)
        runs = [app.tasks.find_run('local-conversations',r['run_request_id']) for r in rows]
        with ThreadPoolExecutor(2) as pool:
            list(pool.map(lambda run:app.worker.tick('local-conversations',run_id=run),runs))
        self.assertEqual(len(self.model.routing_requests),1)
        self.assertEqual(self.usage()['used'],before+1)
        self.assertEqual(self.usage()['remaining'],0)
        self.assertEqual(sorted(app.tasks.inspect('local-conversations',run)['run']['status'] for run in runs),['failed','succeeded'])

    def test_stop_during_paid_revision_records_late_receipt_without_publication(self):
        action=self.route();self.confirm(action)
        entered,release=Event(),Event();original=self.model.complete;dispatched=[]
        def delayed(request):
            dispatched.append(request);entered.set()
            if not release.wait(10):raise TimeoutError('test provider held')
            return original(request)
        with patch.object(self.model,'complete',side_effect=delayed), ThreadPoolExecutor(1) as pool:
            future=pool.submit(self.w.advance_copy_revisions)
            try:
                self.assertTrue(entered.wait(5))
                self.assertEqual(self.usage()['counts']['in_progress'],1)
                stopped=self.w.stop_execution(self.c,'stop',1)
                self.assertTrue(stopped['execution']['stopped'])
                self.assertEqual(stopped['execution']['counts']['uncertain'],1)
                self.assertEqual(len(dispatched),1)
            finally:release.set()
            future.result(10)
        for _ in range(3):self.w.advance_preparations()
        self.assertEqual(len(dispatched),1)
        self.assertEqual(self.w.view(self.sid)['review']['subject']['id'],self.base['review']['subject']['id'])
        self.assertEqual(self.usage()['pending_receipts'],0)
        self.assertEqual(self.usage()['counts']['uncertain'],0)
        self.assertEqual(self.w.conversation(self.c)['actions'][-1]['copy_revision_progress']['status'],'cancelled')

    def test_unknown_paid_call_survives_stop_restart_and_is_never_repeated(self):
        action=self.route();self.confirm(action);before=self.usage()['used']
        with patch.object(self.model,'complete',side_effect=ModelError('provider_request_failed')) as provider:
            self.w.advance_copy_revisions()
            self.w.stop_execution(self.c,'stop',1)
            self.w=Workspace(self.root,real_clock=lambda:self.now)
            self.w.recover_copy_revisions();self.w.recover_actions()
            for _ in range(3):self.w.advance_preparations()
            self.assertEqual(provider.call_count,1)
        self.assertEqual(self.usage()['used'],before+1)
        self.assertEqual(self.usage()['counts']['uncertain'],1)
        self.assertFalse(self.usage()['cost_complete'])
        self.assertNotIn('provider_request_failed',json.dumps(self.usage()))

    def test_stop_is_exact_scoped_atomic_idempotent_and_new_revision_keeps_usage(self):
        subject=self.base['review']['subject']['id']
        self.w.action(self.sid,'approve',{'request_id':'approve','subject_id':subject,'reason':'Reviewed exact campaign.'})
        before=self.usage()['used']
        receipt=self.w.stop_execution(self.c,'stop',1)['execution_receipt']
        self.assertTrue(self.w.view(self.sid)['review']['approval_valid'])
        self.assertEqual(self.w.stop_execution(self.c,'stop',1)['execution_receipt'],receipt)
        with self.assertRaises(Conflict):self.w.stop_execution(self.c,'stop',2)
        app=self.w._conversation_app()
        with self.assertRaises(NotFound):app.execution.stop('another-org',self.c,'stop',1)
        session=self.w._session(self.sid);native=self.w._app(session)
        with self.assertRaises(Conflict):native.drafts.put(session['organization'],'late-write',native.drafts.get(session['organization'],self.base['review']['subject']['draft_id']))
        self.w.message_conversation(self.c,'new-brief',1,'Prepare a £500 contractor experiment with model copy.')
        self.assertFalse(self.usage()['stopped'])
        self.assertEqual(self.usage()['used'],before)
        self.assertEqual(self.w.stop_execution(self.c,'stop',1)['execution_receipt'],receipt)
        self.assertFalse(self.usage()['stopped'])

    def test_fault_on_stop_receipt_rolls_back_fence_and_run_cancellation(self):
        self.w.route_followup(self.c,'queued',1,'Make variant B more direct.',False)
        app=self.w._conversation_app()
        with app.calls.database.transaction() as db:
            db.execute("CREATE TRIGGER reject_stop BEFORE INSERT ON execution_commands BEGIN SELECT RAISE(ABORT,'test fault'); END")
        with self.assertRaises(Exception):self.w.stop_execution(self.c,'stop',1)
        self.assertFalse(self.usage()['stopped'])
        self.assertEqual(self.w.conversation(self.c)['actions'][-1]['status'],'queued')
        self.w.advance_actions()
        self.assertEqual(self.w.conversation(self.c)['actions'][-1]['status'],'succeeded')

    def test_schema_nine_backfill_counts_old_calls_without_rewriting_receipts(self):
        before=self.usage();app=self.w._conversation_app();path=self.root/'conversations.sqlite'
        with app.calls.database.transaction() as db:
            old=[tuple(r) for r in db.execute('SELECT * FROM model_calls ORDER BY rowid')]
            cutoff=[tuple(r) for r in db.execute('SELECT * FROM legacy_task_admissions')]
            for table in ('execution_pending_origins','execution_commands','execution_runs','conversation_execution'):
                db.execute('DROP TABLE '+table)
            db.execute('PRAGMA user_version=8')
        original=Database._apply_migration
        def fail(db,script):
            original(db,script)
            if script==EXECUTION:raise OSError('interrupt schema nine')
        with patch.object(Database,'_apply_migration',side_effect=fail), self.assertRaises(OSError):Database(path)
        import sqlite3
        with sqlite3.connect(path) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],8)
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='execution_runs'").fetchone())
        self.w=Workspace(self.root,real_clock=lambda:self.now)
        self.assertEqual(self.usage()['used'],before['used'])
        with self.w._conversation_app().calls.database.connect() as db:
            self.assertEqual([tuple(r) for r in db.execute('SELECT * FROM model_calls ORDER BY rowid')],old)
            self.assertEqual([tuple(r) for r in db.execute('SELECT * FROM legacy_task_admissions')],cutoff)
        code="from acquisition.workspace import Workspace;import json,sys;print(json.dumps(Workspace(sys.argv[1]).conversation(sys.argv[2])['execution']))"
        result=subprocess.run([sys.executable,'-c',code,str(self.root),self.c],env=dict(os.environ,PYTHONPATH='src'),capture_output=True,text=True,check=True)
        self.assertEqual(json.loads(result.stdout)['used'],before['used'])

    def test_stop_recovers_after_coordinator_admission_without_a_runtime_run(self):
        from acquisition.adapters.sqlite.tasks import SqliteTasks
        c=self.w.create_conversation('partial','Partial admission')['id']
        self.w.message_conversation(c,'m',0,'Prepare a £600 contractor campaign with model copy.')
        with patch.object(SqliteTasks,'create',side_effect=OSError('interrupted task admission')):
            with self.assertRaises(OSError):self.w.start_preparation(c,'prepare-'+c,1,False,True)
        self.assertEqual(self.w.conversation(c)['preparations'][0]['status'],'admitting')
        with patch.object(self.w.preparations.store,'update',side_effect=OSError('control DB interrupted')):
            with self.assertRaises(OSError):self.w.stop_execution(c,'stop-partial',1)
        self.assertEqual(self.w.conversation(c)['preparations'][0]['status'],'cancelled')
        self.w=Workspace(self.root,real_clock=lambda:self.now)
        self.w.preparations.recover('local-conversations')
        with patch.object(self.model,'complete',side_effect=AssertionError('stopped work dispatched')):
            self.w.advance_preparations()
        view=self.w.conversation(c)
        self.assertEqual(view['preparations'][0]['status'],'cancelled')
        self.assertEqual(view['execution']['used'],0)
        self.assertEqual(view['campaigns'],[])

    def test_stop_during_planning_prevents_result_and_later_campaign_calls(self):
        c=self.w.create_conversation('planning','Planning cancellation')['id']
        self.w.message_conversation(c,'m',0,'Prepare a £600 contractor campaign with model copy.')
        self.w.start_preparation(c,'prepare-'+c,1,False,True)
        entered,release=Event(),Event();original=self.model.complete;dispatched=[]
        def delayed(request):
            dispatched.append(request);entered.set()
            if not release.wait(10):raise TimeoutError('provider held')
            return original(request)
        with patch.object(self.model,'complete',side_effect=delayed), ThreadPoolExecutor(1) as pool:
            future=pool.submit(self.w.advance_preparations)
            try:
                self.assertTrue(entered.wait(5))
                self.w.stop_execution(c,'stop-planning',1)
            finally:release.set()
            future.result(10)
        self.w=Workspace(self.root,real_clock=lambda:self.now)
        self.w.preparations.recover('local-conversations');self.w.advance_preparations()
        view=self.w.conversation(c)
        self.assertEqual(view['preparations'][0]['status'],'cancelled')
        self.assertEqual(view['current_plan']['status'],'cancelled')
        self.assertIsNone(view['current_plan']['result'])
        self.assertEqual(view['campaigns'],[])
        self.assertEqual(len(dispatched),1)

    def test_another_conversation_cannot_share_or_stop_this_account(self):
        before=self.usage()['used']
        other=self.w.create_conversation('other-account','Another account')['id']
        self.w.message_conversation(other,'m',0,'Prepare a £500 contractor campaign with model copy.')
        self.w.start_preparation(other,'other-prepare',1,False,True)
        self.w.stop_execution(self.c,'stop-only-this',1)
        self.w.advance_preparations()
        view=self.w.conversation(other)
        self.assertFalse(view['execution']['stopped'])
        self.assertGreater(view['execution']['used'],0)
        self.assertEqual(self.usage()['used'],before)
        with self.assertRaises(Conflict):self.w.stop_execution(other,'stop-only-this',1)

    def test_stop_does_not_reject_an_approval_through_new_revision_admission(self):
        subject=self.base['review']['subject']['id'];scope=self.w._session(self.sid)['organization']
        self.w.action(self.sid,'approve',{'request_id':'approve','subject_id':subject,'reason':'Reviewed exact campaign.'})
        self.w.stop_execution(self.c,'stop',1)
        target=next(c['id'] for c in self.base['review']['manifest']['creatives'] if c['arm']=='B')
        with self.assertRaises(Conflict):
            self.w.request_copy_revision(self.sid,'stopped-revision',subject,target,'More direct.',True)
        state=self.w.view(self.sid)
        self.assertTrue(state['review']['approval_valid'])
        self.assertEqual(state['copy_revisions'],[])
        with self.w._conversation_app().calls.database.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM review_events WHERE organization=? AND kind='review_reject'",(scope,)).fetchone()[0],0)

    def test_known_provider_rejection_consumes_allowance_without_becoming_uncertain(self):
        before=self.usage()['used'];self.lower_limit(before+1)
        with patch.object(self.model,'complete',side_effect=ModelError('provider_http_401')):
            self.route('Make variant B more direct.',request='rejected')
        self.assertEqual(self.usage()['counts']['rejected'],1)
        self.assertEqual(self.usage()['counts']['uncertain'],0)
        self.w.route_followup(self.c,'over-budget',1,'Make variant A more direct.',False)
        with patch.object(self.model,'complete',side_effect=AssertionError('budget overspent')):
            self.w.advance_actions()
        self.assertEqual(self.w.conversation(self.c)['actions'][-1]['status'],'budget_exhausted')
        self.assertEqual(self.usage()['used'],before+1)

    def test_recorded_response_replays_at_exhausted_allowance_without_another_call(self):
        from acquisition.adapters.sqlite.tasks import SqliteTasks
        before=self.usage()['used'];self.lower_limit(before+1)
        self.w.route_followup(self.c,'recorded',1,'Make variant B more direct.',False)
        with patch.object(SqliteTasks,'settle',side_effect=KeyboardInterrupt('after provider record')):
            with self.assertRaises(KeyboardInterrupt):self.w.advance_actions()
        self.assertEqual(self.usage()['remaining'],0)
        self.now+=181
        self.w=Workspace(self.root,real_clock=lambda:self.now)
        self.w.advance_actions()
        self.assertEqual(self.w.conversation(self.c)['actions'][-1]['status'],'succeeded')
        self.assertEqual(len(self.model.routing_requests),1)
        self.assertEqual(self.usage()['used'],before+1)

    def test_run_binding_rejects_another_valid_conversation_even_before_dispatch(self):
        from acquisition.runtime import TaskSpec
        from acquisition.reasoning import CallScope
        from acquisition.contracts import canonical
        app=self.w._conversation_app()
        other=self.w.create_conversation('other-binding','Other binding')['id']
        self.w.message_conversation(other,'m',0,'Prepare a £600 contractor campaign.')
        self.assertEqual(app.execution.view('local-conversations', other)['remaining'], 48)
        inputs={'brief':{'conversation_id':self.c,'conversation_revision':1}}
        run=app.tasks.create('local-conversations','binding-test',[TaskSpec('local.test',inputs)],self.now)
        with app.calls.database.transaction() as db:
            changed={'brief':{'conversation_id':other,'conversation_revision':1}}
            db.execute('UPDATE tasks SET inputs=? WHERE run_id=?',(canonical(changed),run))
        claim=app.tasks.claim('local-conversations',self.now,180,run_id=run)
        scope=CallScope(claim.organization,claim.run_id,claim.task_id,claim.token)
        with self.assertRaises(Conflict):app.calls.reserve(scope,'call','request-hash',1,self.now)
        self.assertEqual(self.w.conversation(other)['execution']['used'],0)

class ExecutionFollowupTests(unittest.TestCase):
    setUp=handoff_tests.ConversationHandoffTests.setUp
    usage=ExecutionTests.usage
    lower_limit=ExecutionTests.lower_limit

    def finalized_parent(self):
        subject=self.state['review']['subject']['id']
        state=self.w.action(self.sid,'approve',{'request_id':'approve','subject_id':subject,'reason':'Reviewed exact campaign.'})
        self.w.action(self.sid,'handoff',{'request_id':'handoff','approval_id':state['review']['approval']['id']})
        self.w.action(self.sid,'open-learning',{'request_id':'open'})
        self.w.action(self.sid,'finalize',{'request_id':'finalize'})

    def manual_child(self, request='manual'):
        from acquisition.contracts import digest
        sid='workspace_'+digest({'request_id':request})[:24]
        with patch.object(self.w,'prepare',return_value=None):
            self.w.create(request,'model',self.sid)
        return sid

    def test_manual_descendant_calls_are_counted_and_replay_after_restart_is_free(self):
        self.finalized_parent();model=copy_tests.CopyRoutingModel();calls=[];original=model.complete
        def observed(request):
            calls.append(request);return original(request)
        with patch('acquisition.workspace.openrouter_key',return_value='fixture'),patch('acquisition.workspace.OpenRouter',return_value=model),patch.object(model,'complete',side_effect=observed):
            child=self.w.create('manual','model',self.sid)
            self.assertEqual(len(calls),6)
            self.assertEqual(self.usage()['used'],6)
            self.assertIn(child['session']['run_id'],{c['run_id'] for c in self.usage()['calls']})
            session = self.w._session(child['session']['id'])
            app = self.w._app(session)
            self.assertNotEqual(session['organization'], 'local-conversations')
            with app.calls.database.transaction() as db:
                db.execute('DELETE FROM execution_runs WHERE organization=?', (session['organization'],))
            usage = app.execution.view('local-conversations', self.c)
            self.assertIsNone(usage['remaining'])
            self.assertFalse(usage['cost_complete'])
            self.w=Workspace(self.root,real_clock=lambda:1792972800.)
            self.w.recover_execution()
            self.w.create('manual','model',self.sid)
            self.assertEqual(len(calls),6)
            self.assertEqual(self.usage()['used'],6)

    def test_admitted_manual_descendant_cannot_dispatch_after_parent_stop(self):
        from acquisition.runtime import Worker
        self.finalized_parent();model=copy_tests.CopyRoutingModel();child=self.manual_child()
        with patch('acquisition.workspace.openrouter_key',return_value='fixture'),patch('acquisition.workspace.OpenRouter',return_value=model):
            with patch.object(Worker,'drain',return_value=0),self.assertRaises(Conflict):self.w.prepare(child)
            session=self.w._session(child);app=self.w._app(session)
            self.assertEqual(app.tasks.inspect(session['organization'],session['run_id'])['run']['status'],'queued')
            with app.calls.database.transaction() as db:
                db.execute('DELETE FROM execution_runs WHERE organization=? AND run_id=?',(session['organization'],session['run_id']))
                db.execute('DELETE FROM execution_commands WHERE organization=? AND request_id=?',(session['organization'],'descendant:'+child))
            self.w=Workspace(self.root,real_clock=lambda:1792972800.)
            self.w.stop_execution(self.c,'stop-manual',1)
            self.assertEqual(app.tasks.inspect(session['organization'],session['run_id'])['run']['status'],'cancelled')
            with patch.object(model,'complete',side_effect=AssertionError('stopped descendant dispatched')) as provider:
                with self.assertRaises(Conflict):self.w.prepare(child)
                self.assertEqual(provider.call_count,0)
        self.assertEqual(self.usage()['used'],0)

    def test_manual_descendant_created_after_stop_cannot_make_a_model_call(self):
        self.finalized_parent();self.w.stop_execution(self.c,'stop-before-child',1)
        with patch('acquisition.workspace.openrouter_key',return_value='fixture'),patch('acquisition.workspace.OpenRouter') as provider:
            with self.assertRaises(ModelError):self.w.create('late-manual','model',self.sid)
            self.assertEqual(provider.return_value.complete.call_count,0)
        self.assertEqual(self.usage()['used'],0)

    def test_manual_descendant_must_reserve_the_shared_last_slot(self):
        self.finalized_parent();self.lower_limit(1);model=copy_tests.CopyRoutingModel()
        with patch('acquisition.workspace.openrouter_key',return_value='fixture'),patch('acquisition.workspace.OpenRouter',return_value=model),patch.object(model,'complete',wraps=model.complete) as provider:
            with self.assertRaises(Conflict):self.w.create('limited-manual','model',self.sid)
            self.assertEqual(provider.call_count,1)
        self.assertEqual(self.usage()['used'],1)
        self.assertEqual(self.usage()['remaining'],0)

    def test_old_manual_descendants_are_backfilled_without_rewriting_receipts(self):
        self.finalized_parent();model=copy_tests.CopyRoutingModel()
        with patch('acquisition.workspace.openrouter_key',return_value='fixture'),patch('acquisition.workspace.OpenRouter',return_value=model):
            child=self.w.create('old-manual','model',self.sid)
        session=self.w._session(child['session']['id']);app=self.w._app(session)
        with app.calls.database.transaction() as db:
            old_calls=[tuple(r) for r in db.execute('SELECT * FROM model_calls ORDER BY rowid')]
            old_drafts=[tuple(r) for r in db.execute('SELECT * FROM drafts ORDER BY rowid')]
            db.execute('DELETE FROM execution_runs WHERE organization=? AND run_id=?',(session['organization'],session['run_id']))
            db.execute('DELETE FROM execution_commands WHERE organization=? AND request_id=?',(session['organization'],'descendant:'+session['id']))
        self.w=Workspace(self.root,real_clock=lambda:1792972800.)
        with patch('acquisition.workspace.OpenRouter',side_effect=AssertionError('recovery requested provider')):
            self.w.recover_execution()
            self.assertEqual(self.usage()['used'],6)
        with app.calls.database.connect() as db:
            self.assertEqual([tuple(r) for r in db.execute('SELECT * FROM model_calls ORDER BY rowid')],old_calls)
            self.assertEqual([tuple(r) for r in db.execute('SELECT * FROM drafts ORDER BY rowid')],old_drafts)

    def test_checkpoint_without_a_case_is_preserved_and_exposed_for_review(self):
        from acquisition.adapters.sqlite.reviews import SqliteReviews
        from acquisition.conversations import FIXTURE_MESSAGE
        model=copy_tests.CopyRoutingModel()
        for fixture in (True,False):
            with self.subTest(fixture=fixture):
                c=self.w.create_conversation('checkpoint-'+str(fixture),'Checkpoint before case')['id']
                content=FIXTURE_MESSAGE if fixture else 'Prepare a £600 contractor campaign with model copy.'
                self.w.message_conversation(c,'m',0,content)
                with patch('acquisition.workspace.openrouter_key',return_value='fixture'),patch('acquisition.workspace.OpenRouter',return_value=model):
                    self.w.start_preparation(c,'checkpoint-prepare-'+str(fixture),1,fixture,not fixture)
                    with patch.object(SqliteReviews,'open_case',side_effect=OSError('case write interrupted')):
                        for _ in range(8):self.w.advance_preparations()
                before=self.w.conversation(c);sid=before['campaigns'][0]['session_id'];session=self.w._session(sid);app=self.w._app(session)
                self.assertIsNone(session['case_id'])
                self.assertEqual(app.tasks.inspect(session['organization'],session['run_id'])['run']['status'],'waiting')
                used=before['execution']['used']
                with patch('acquisition.workspace.OpenRouter',side_effect=AssertionError('stop generated copy')):
                    stopped=self.w.stop_execution(c,'checkpoint-stop-'+str(fixture),1)
                self.assertNotIn(session['run_id'],stopped['execution_receipt']['run_ids'])
                self.assertEqual(app.tasks.inspect(session['organization'],session['run_id'])['run']['status'],'waiting')
                self.assertIsNotNone(stopped['campaigns'][0]['case_id'])
                review=self.w.view(sid)['review']
                self.assertTrue(review['candidate_valid'],review['blocked_reasons'])
                self.assertFalse(review['approval_valid'])
                self.assertEqual(stopped['execution']['used'],used)
                self.assertEqual(stopped['preparations'][0]['status'],'review_ready')

    def test_checkpoint_case_recovery_after_stop_commit_is_restart_safe(self):
        from acquisition.adapters.sqlite.reviews import SqliteReviews
        from acquisition.conversations import FIXTURE_MESSAGE
        c=self.w.create_conversation('recover-checkpoint','Recover checkpoint')['id']
        self.w.message_conversation(c,'m',0,FIXTURE_MESSAGE)
        self.w.start_preparation(c,'recover-prepare',1,True,False)
        with patch.object(SqliteReviews,'open_case',side_effect=OSError('case storage unavailable')):
            for _ in range(6):self.w.advance_preparations()
            stopped=self.w.stop_execution(c,'recover-stop',1)
            self.assertEqual(stopped['preparations'][0]['checkpoint_recovery']['code'],'checkpoint_storage_unavailable')
        sid=self.w.conversation(c)['campaigns'][0]['session_id']
        self.assertIsNone(self.w._session(sid)['case_id'])
        self.w=Workspace(self.root,real_clock=lambda:1792972800.)
        with patch('acquisition.workspace.OpenRouter',side_effect=AssertionError('recovery generated copy')):
            self.w.recover_execution();self.w.preparations.recover('local-conversations')
            self.w.recover_execution()
        view=self.w.view(sid)
        self.assertTrue(view['review']['candidate_valid'])
        self.assertFalse(view['review']['approval_valid'])
        self.assertEqual(sum(e['kind']=='review_opened' for e in view['review']['events']),1)

    def test_non_review_waiting_task_is_still_cancelled(self):
        from acquisition.runtime import TaskSpec,Outcome
        app=self.w._conversation_app()
        run=app.tasks.create('local-conversations','other-wait',[TaskSpec('local.wait',{'brief':{'conversation_id':self.c,'conversation_revision':1}})],1792972800.)
        claim=app.tasks.claim('local-conversations',1792972800.,180,run_id=run)
        app.tasks.settle(claim,Outcome('waiting',{'reference':'not-a-review'}),1792972800.)
        self.w.stop_execution(self.c,'stop-other-wait',1)
        self.assertEqual(app.tasks.inspect('local-conversations',run)['run']['status'],'cancelled')

    def legacy_manual(self, model, *, claim=False):
        from acquisition.runtime import Worker
        self.finalized_parent();self.lower_limit(1)
        child=self.manual_child('pre-recovery')
        with patch.object(Worker,'drain',return_value=0),self.assertRaises(Conflict):self.w.prepare(child)
        session=self.w._session(child);app=self.w._app(session,with_model=True)
        held=None
        if claim:
            app.worker.tick(session['organization'],run_id=session['run_id'])
            held=app.tasks.claim(session['organization'],app.clock(),180,run_id=session['run_id'])
            self.assertTrue(held.capability.startswith('creative.generate'))
        with app.calls.database.transaction() as db:
            db.execute('DELETE FROM execution_runs WHERE organization=? AND run_id=?',(session['organization'],session['run_id']))
            db.execute('DELETE FROM execution_commands WHERE organization=? AND request_id=?',(session['organization'],'descendant:'+child))
            db.execute('DROP TABLE execution_pending_origins')
            db.execute('PRAGMA user_version=9')
        return session,held

    def test_migrated_manual_descendant_cannot_be_claimed_before_workspace_recovery(self):
        model=copy_tests.CopyRoutingModel()
        with patch('acquisition.workspace.openrouter_key',return_value='fixture'),patch('acquisition.workspace.OpenRouter',return_value=model),patch.object(model,'complete',wraps=model.complete) as provider:
            session,_=self.legacy_manual(model)
            direct=self.w._app(session,with_model=True)  # Migration only, no workspace ancestry repair.
            self.assertTrue(direct.execution.pending(session['organization'],session['run_id']))
            before=direct.tasks.inspect(session['organization'],session['run_id'])
            self.assertEqual(direct.worker.drain(session['organization'],run_id=session['run_id']),0)
            self.assertEqual(provider.call_count,0)
            self.assertEqual(direct.tasks.inspect(session['organization'],session['run_id']),before)
            usage=direct.execution.view('local-conversations',self.c)
            self.assertFalse(usage['account_unresolved'])
            self.assertFalse(usage['accounting_complete'])
            self.assertIsNone(usage['remaining'])
            self.assertFalse(usage['cost_complete'])
            self.assertEqual(usage['status'],'blocked')
            self.w.recover_execution()
            self.assertFalse(direct.execution.pending(session['organization'],session['run_id']))
            direct.worker.drain(session['organization'],run_id=session['run_id'])
            self.assertEqual(provider.call_count,1)
            self.assertEqual(self.usage()['used'],1)

    def test_migrated_live_lease_cannot_bypass_ancestry_reservation_guard(self):
        from acquisition.reasoning import CallScope
        model=copy_tests.CopyRoutingModel()
        with patch('acquisition.workspace.openrouter_key',return_value='fixture'),patch('acquisition.workspace.OpenRouter',return_value=model),patch.object(model,'complete',wraps=model.complete) as provider:
            session,claim=self.legacy_manual(model,claim=True)
            direct=self.w._app(session,with_model=True)
            scope=CallScope(claim.organization,claim.run_id,claim.task_id,claim.token)
            with self.assertRaisesRegex(ModelError,'ancestry_recovery_required'):
                direct.inference.call(scope,'unresolved-probe',[{'role':'user','content':'Read the frozen context.'}],
                    [{'type':'function','function':{'name':'read_context','parameters':{'type':'object','properties':{}}}}])
            self.assertEqual(provider.call_count,0)
            self.assertEqual(direct.calls.inspect(session['organization'],session['run_id']),[])

    def test_unrelated_standalone_worker_is_not_blocked_by_legacy_ancestry(self):
        model=copy_tests.CopyRoutingModel()
        with patch('acquisition.workspace.openrouter_key',return_value='fixture'),patch('acquisition.workspace.OpenRouter',return_value=model),patch.object(model,'complete',wraps=model.complete) as provider:
            session,_=self.legacy_manual(model)
            direct=self.w._app(session,with_model=True)
            run=direct.start_model('unrelated-organization','standalone',as_of='2026-10-26')
            direct.worker.drain('unrelated-organization',run_id=run)
            self.assertEqual(provider.call_count,6)
            self.assertEqual(direct.tasks.inspect('unrelated-organization',run)['run']['status'],'waiting')

    def legacy_cli(self, request, campaign_id, *, version=10, organization=None, completed=True, cost=0):
        """Use the public CLI application path with pre-accounting ancestry behavior."""
        session=self.w._session(self.sid)
        model=copy_tests.CopyRoutingModel()
        complete=model.complete
        def priced(request):
            response=complete(request)
            response['usage']['cost']=cost
            return response
        model.complete=priced
        from acquisition.bootstrap import build
        from acquisition.reasoning import ModelConfig
        app=build(self.root/'conversations.sqlite',clock=lambda:1792972800.,gateway=model,
                  model_config=ModelConfig('openai/gpt-oss-120b',max_calls=10,force_tool_choice=True))
        scope=organization or session['organization']
        with patch('acquisition.adapters.sqlite.execution.run_origin',return_value=None):
            run=app.start_model(scope,request,campaign_id=campaign_id,as_of='2026-10-26')
            if completed:
                app.worker.drain(scope,run_id=run)
                self.assertEqual(len(app.calls.inspect(scope,run)),6)
                self.assertEqual(app.tasks.inspect(scope,run)['run']['status'],'waiting')
        with app.calls.database.transaction() as db:
            if version==9:
                db.execute('DROP TABLE execution_pending_origins')
                db.execute('PRAGMA user_version=9')
            else:
                db.execute('INSERT INTO execution_pending_origins VALUES(?,?)',(scope,run))
        return app,scope,run

    def test_completed_cli_campaign_recovers_without_a_descendant_session(self):
        for version in (9,10):
            with self.subTest(version=version):
                app,scope,run=self.legacy_cli('cli-'+str(version),self.sid,version=version)
                history=app.tasks.inspect(scope,run)
                receipts=app.calls.inspect(scope,run)
                with app.calls.database.connect() as db:
                    drafts=[tuple(r) for r in db.execute('SELECT * FROM drafts ORDER BY rowid')]
                    cutoff=[tuple(r) for r in db.execute('SELECT * FROM legacy_task_admissions')]
                # A new direct worker opens the DB before any workspace/session recovery.
                code='''import json,sys
from acquisition.adapters.sqlite.database import Database
from acquisition.adapters.sqlite.execution import SqliteExecution
print(json.dumps(SqliteExecution(Database(sys.argv[1])).view('local-conversations',sys.argv[2])))
'''
                result=subprocess.run([sys.executable,'-c',code,str(app.calls.database.path),self.c],
                    env=dict(os.environ,PYTHONPATH='src'),capture_output=True,text=True,timeout=10)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertTrue(json.loads(result.stdout)['accounting_complete'])
                reopened=Database(app.calls.database.path)
                from acquisition.adapters.sqlite.execution import SqliteExecution
                store=SqliteExecution(reopened)
                usage=store.view('local-conversations',self.c)
                self.assertFalse(store.pending(scope,run))
                self.assertTrue(usage['accounting_complete'])
                self.assertEqual(usage['used'],6*(1+(version==10)))
                self.assertEqual({c['run_id'] for c in usage['calls']} & {run},{run})
                self.assertTrue(usage['cost_complete'])
                self.assertEqual(app.tasks.inspect(scope,run),history)
                self.assertEqual(app.calls.inspect(scope,run),receipts)
                with reopened.connect() as db:
                    self.assertEqual([tuple(r) for r in db.execute('SELECT * FROM drafts ORDER BY rowid')],drafts)
                    self.assertEqual([tuple(r) for r in db.execute('SELECT * FROM legacy_task_admissions')],cutoff)
                self.w=Workspace(self.root,real_clock=lambda:1792972800.)
                self.w.recover_execution()
                self.assertEqual(len(self.w.conversation(self.c)['campaigns']),1)
                self.assertTrue(self.usage()['accounting_complete'])

    def test_recovered_cli_run_obeys_original_stop_and_allowance_before_dispatch(self):
        for stopped in (False,True):
            with self.subTest(stopped=stopped):
                app,scope,run=self.legacy_cli('queued-cli-'+str(stopped),self.sid,completed=False)
                self.lower_limit(48 if stopped else 1)
                if stopped:self.w.stop_execution(self.c,'stop-cli',1)
                Database(app.calls.database.path)
                with patch.object(app.inference.gateway,'complete',wraps=app.inference.gateway.complete) as provider:
                    app.worker.drain(scope,run_id=run)
                    self.assertEqual(provider.call_count,0 if stopped else 1)
                self.assertEqual(self.usage()['used'],1)

    def test_unresolved_calls_make_even_zero_known_cost_incomplete(self):
        app,scope,run=self.legacy_cli('unresolved-cli','unknown-campaign')
        self.w.recover_execution()
        usage=self.usage()
        self.assertEqual(usage['unresolved_runs'],[run])
        self.assertEqual(usage['used'],0)
        self.assertEqual(usage['reported_cost_usd'],'0')
        self.assertEqual(usage['cost_reported_calls'],0)
        self.assertFalse(usage['accounting_complete'])
        self.assertFalse(usage['cost_complete'])
        self.assertIsNone(usage['remaining'])
        self.assertTrue(app.execution.pending(scope,run))

    def resolve_legacy(self, app, scope, run, *, request='resolve', fingerprint=None, actor='local-operator', reason='Verified independent CLI experiment, not conversation work.'):
        inspection=next(r for r in app.execution.unresolved(scope) if r['run_id']==run) if fingerprint is None else None
        return app.execution.resolve_independent(scope,request,run,fingerprint or inspection['fingerprint'],actor,reason)

    def test_independent_legacy_cli_resolution_is_audited_and_survives_restart(self):
        self.w.action(self.sid,'approve',{'request_id':'resolution-approval','subject_id':self.state['review']['subject']['id'],'reason':'Reviewed original campaign.'})
        app,scope,run=self.legacy_cli('independent-cli','independent-cli',version=9)
        Database(app.calls.database.path)
        before=app.tasks.inspect(scope,run);receipts=app.calls.inspect(scope,run)
        self.assertIsNone(self.usage()['remaining'])
        item=app.execution.unresolved(scope)[0]
        self.assertEqual(item['known_calls'],6)
        self.assertEqual(item['campaign_ids'],['independent-cli'])
        decision=self.resolve_legacy(app,scope,run,fingerprint=item['fingerprint'])
        self.assertEqual(decision['known_calls'],6)
        self.assertEqual(decision['actor_generation'],1)
        self.assertFalse(app.execution.pending(scope,run))
        self.assertEqual(app.calls.inspect(scope,run),receipts)
        after=app.tasks.inspect(scope,run)
        self.assertEqual(after['tasks'],before['tasks'])
        self.assertEqual(after['run'],before['run'])
        self.assertEqual(sum(e['kind']=='execution_origin_resolved' for e in after['events']),1)
        self.assertTrue(self.usage()['accounting_complete'])

        self.assertEqual(self.usage()['remaining'],48)
        self.assertEqual(self.usage()['used'],0)
        self.assertTrue(self.w.view(self.sid)['review']['approval_valid'])
        from acquisition.adapters.sqlite.execution import quarantine_old_origins
        with app.calls.database.transaction() as db:quarantine_old_origins(db)
        self.assertFalse(app.execution.pending(scope,run))
        self.w=Workspace(self.root,real_clock=lambda:1792972800.)
        self.w.recover_execution()
        self.assertEqual(app.execution.unresolved(scope),[])
        self.assertTrue(self.usage()['accounting_complete'])
        for key in ('resolve','observe-resolution'):
            self.assertEqual(self.resolve_legacy(app,scope,run,request=key,fingerprint=item['fingerprint']),decision)
        self.assertEqual(sum(e['kind']=='execution_origin_resolved' for e in app.tasks.inspect(scope,run)['events']),1)
        with self.assertRaises(Conflict):self.resolve_legacy(app,scope,run,fingerprint=item['fingerprint'],reason='Changed attestation.')
        # A later guessed parent cannot silently undo the independent decision.
        parent=self.w._session(self.sid)['run_id']
        with self.assertRaises(Conflict):app.execution.descendant(scope,'independent-cli',parent)
        self.assertTrue(self.usage()['accounting_complete'])

    def test_workspace_parent_rejects_incorrect_independence_before_recovery(self):
        model=copy_tests.CopyRoutingModel()
        with patch('acquisition.workspace.openrouter_key',return_value='fixture'),patch('acquisition.workspace.OpenRouter',return_value=model):
            session,_=self.legacy_manual(model)
            app=self.w._app(session,with_model=True)  # Migrate without workspace recovery.
        scope,run=session['organization'],session['run_id']
        item=next(i for i in app.execution.unresolved(scope) if i['run_id']==run)
        self.assertEqual(item['workspace_ancestry'][0]['parent_id'],self.sid)
        before=app.tasks.inspect(scope,run)
        with self.assertRaisesRegex(Conflict,'Workspace ancestry'):
            self.resolve_legacy(app,scope,run,fingerprint=item['fingerprint'],reason='Incorrect operator attestation.')
        self.assertTrue(app.execution.pending(scope,run))
        self.assertEqual(app.tasks.inspect(scope,run),before)
        with app.calls.database.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM execution_commands WHERE request_id LIKE 'independent:%' OR request_id LIKE 'resolution:%'").fetchone()[0],0)
        # A fresh CLI process must enforce the same authority, not just the facade.
        result=subprocess.run([sys.executable,'-m','acquisition','--db',str(app.calls.database.path),'--organization',scope,
            'execution-resolve-independent','--run',run,'--request-id','wrong-cli-attestation','--fingerprint',item['fingerprint'],
            '--actor','local-operator','--reason','Incorrect attestation before recovery.'],
            env=dict(os.environ,PYTHONPATH='src'),capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,2,result.stderr)
        self.assertIn('Workspace ancestry',result.stderr)
        self.w=Workspace(self.root,real_clock=lambda:1792972800.)
        self.w.recover_execution()
        self.assertFalse(app.execution.pending(scope,run))
        self.w.stop_execution(self.c,'stop-after-rejected-attestation',1)
        with patch.object(app.inference.gateway,'complete',side_effect=AssertionError('stopped child dispatched')):
            self.assertEqual(app.worker.drain(scope,run_id=run),0)
        self.assertEqual(app.tasks.inspect(scope,run)['run']['status'],'cancelled')

    def test_completed_workspace_child_cannot_exclude_its_six_calls_by_attestation(self):
        self.finalized_parent();model=copy_tests.CopyRoutingModel()
        with patch('acquisition.workspace.openrouter_key',return_value='fixture'),patch('acquisition.workspace.OpenRouter',return_value=model):
            child=self.w.create('completed-unrecovered','model',self.sid)
        session=self.w._session(child['session']['id']);scope,run=session['organization'],session['run_id'];app=self.w._app(session)
        calls=app.calls.inspect(scope,run)
        self.assertEqual(len(calls),6)
        with app.calls.database.transaction() as db:
            db.execute('DELETE FROM execution_runs WHERE organization=? AND run_id=?',(scope,run))
            db.execute('DELETE FROM execution_commands WHERE organization=? AND request_id=?',(scope,'descendant:'+session['id']))
            db.execute('INSERT INTO execution_pending_origins VALUES(?,?)',(scope,run))
        with self.assertRaisesRegex(Conflict,'Workspace ancestry'):self.resolve_legacy(app,scope,run)
        self.w.recover_execution()
        self.assertEqual(self.usage()['used'],6)
        self.assertEqual(app.calls.inspect(scope,run),calls)

    def test_reconciliation_checks_workspace_after_waiting_for_its_lock(self):
        import acquisition.adapters.sqlite.execution as execution
        from contextlib import contextmanager
        app,scope,run=self.legacy_cli('concurrent-parent','concurrent-parent')
        session={'id':'concurrent-parent','organization':scope,'run_id':run,'database_scope':'conversations','parent_id':None}
        with self.w.control() as db:db.execute('INSERT INTO sessions VALUES(?,?,?)',(session['id'],'test-only',json.dumps(session)))
        item=app.execution.unresolved(scope)[0];entered=Event();original=execution.workspace_ancestry_guard
        @contextmanager
        def observed(path):
            entered.set()
            with original(path) as guard:yield guard
        with self.w.control() as control:
            control.execute('BEGIN IMMEDIATE')
            session['parent_id']=self.sid
            control.execute('UPDATE sessions SET payload=? WHERE id=?',(json.dumps(session),session['id']))
            with patch.object(execution,'workspace_ancestry_guard',new=observed),ThreadPoolExecutor(1) as pool:
                future=pool.submit(self.resolve_legacy,app,scope,run,fingerprint=item['fingerprint'])
                try:self.assertTrue(entered.wait(5))
                finally:control.commit()
                with self.assertRaisesRegex(Conflict,'Workspace ancestry'):future.result(10)
        self.assertTrue(app.execution.pending(scope,run))

    def test_workspace_lock_is_held_until_resolution_commit(self):
        import sqlite3
        import acquisition.adapters.sqlite.tasks as task_adapter
        app,scope,run=self.legacy_cli('locked-independent','locked-independent')
        original=task_adapter.event
        def observed(db,*args):
            other=sqlite3.connect(self.root/'workspace.sqlite',timeout=0,isolation_level=None)
            try:
                with self.assertRaisesRegex(sqlite3.OperationalError,'locked'):
                    other.execute('BEGIN IMMEDIATE')
            finally:other.close()
            return original(db,*args)
        with patch.object(task_adapter,'event',side_effect=observed):self.resolve_legacy(app,scope,run)
        self.assertTrue(self.usage()['accounting_complete'])

    def test_workspace_inspection_changes_require_a_new_fingerprint(self):
        app,scope,run=self.legacy_cli('workspace-inspection','workspace-inspection')
        session={'id':'workspace-inspection','organization':scope,'run_id':None,'database_scope':'conversations','parent_id':None}
        with self.w.control() as db:db.execute('INSERT INTO sessions VALUES(?,?,?)',(session['id'],'test-only',json.dumps(session)))
        item=app.execution.unresolved(scope)[0]
        session['run_id']=run
        with self.w.control() as db:db.execute('UPDATE sessions SET payload=? WHERE id=?',(json.dumps(session),session['id']))
        with self.assertRaisesRegex(Conflict,'changed'):self.resolve_legacy(app,scope,run,fingerprint=item['fingerprint'])
        self.resolve_legacy(app,scope,run)

    def test_another_organization_workspace_parent_cannot_classify_this_run(self):
        app,scope,run=self.legacy_cli('foreign-workspace-parent','foreign-workspace-parent')
        session={'id':'foreign-workspace-parent','organization':'different-organization','run_id':run,
                 'database_scope':'conversations','parent_id':self.sid}
        with self.w.control() as db:db.execute('INSERT INTO sessions VALUES(?,?,?)',(session['id'],'test-only',json.dumps(session)))
        self.assertEqual(app.execution.unresolved(scope)[0]['workspace_ancestry'],[])
        self.resolve_legacy(app,scope,run)

    def test_unavailable_workspace_blocks_new_attestation_but_not_historical_replay(self):
        app,scope,run=self.legacy_cli('journal-independent','journal-independent')
        item=app.execution.unresolved(scope)[0]
        journal=self.root/'workspace.sqlite';saved=self.root/'workspace.saved'
        journal.rename(saved)
        try:
            with self.assertRaisesRegex(Conflict,'Workspace ancestry is unavailable'):
                self.resolve_legacy(app,scope,run,fingerprint=item['fingerprint'])
            self.assertTrue(app.execution.pending(scope,run))
        finally:saved.rename(journal)
        receipt=self.resolve_legacy(app,scope,run,fingerprint=item['fingerprint'])
        journal.rename(saved)
        try:self.assertEqual(self.resolve_legacy(app,scope,run,fingerprint=item['fingerprint']),receipt)
        finally:saved.rename(journal)

    def test_recreated_empty_journal_cannot_release_a_legacy_workspace_child(self):
        model=copy_tests.CopyRoutingModel()
        with patch('acquisition.workspace.openrouter_key',return_value='fixture'),patch('acquisition.workspace.OpenRouter',return_value=model):
            session,_=self.legacy_manual(model)
            app=self.w._app(session,with_model=True)
        scope,run=session['organization'],session['run_id']
        item=app.execution.unresolved(scope)[0]
        with app.calls.database.connect() as db:
            binding=tuple(db.execute("SELECT inputs,receipt FROM execution_commands WHERE organization=? AND request_id='workspace:journal:v1'",(scope,)).fetchone())
        journal=self.root/'workspace.sqlite';saved=self.root/'original-workspace.saved';journal.rename(saved)
        try:
            replacement=Workspace(self.root,real_clock=lambda:1792972800.)
            replacement._app(session)  # Normal reopening must not replace the binding.
            replacement._conversation_app()
            with self.assertRaisesRegex(Conflict,'bound original'):
                self.resolve_legacy(app,scope,run,fingerprint=item['fingerprint'])
            with self.assertRaisesRegex(Conflict,'bound original'):app.execution.unresolved(scope)
            self.assertTrue(app.execution.pending(scope,run))
            with app.calls.database.connect() as db:
                self.assertEqual(tuple(db.execute("SELECT inputs,receipt FROM execution_commands WHERE organization=? AND request_id='workspace:journal:v1'",(scope,)).fetchone()),binding)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM execution_commands WHERE request_id LIKE 'independent:%' OR request_id LIKE 'resolution:%'").fetchone()[0],0)
        finally:
            journal.unlink();saved.rename(journal)
        self.w=Workspace(self.root,real_clock=lambda:1792972800.)
        self.w.recover_execution()
        self.assertFalse(app.execution.pending(scope,run))
        self.w.stop_execution(self.c,'stop-restored',1)
        with patch.object(app.inference.gateway,'complete',side_effect=AssertionError('restoration dispatched')):
            self.assertEqual(app.worker.drain(scope,run_id=run),0)

    def test_unrelated_journal_cannot_authorize_independence_and_original_restore_works(self):
        import sqlite3
        app,scope,run=self.legacy_cli('swapped-journal','swapped-journal')
        item=app.execution.unresolved(scope)[0]
        original_session=self.w._session(self.sid)
        other=Workspace(self.root/'unrelated',real_clock=lambda:1792972800.)
        other.create('different-campaign','fixture')
        journal=self.root/'workspace.sqlite';saved=self.root/'original-workspace.saved';journal.rename(saved)
        try:
            source=sqlite3.connect(other.root/'workspace.sqlite');target=sqlite3.connect(journal)
            try:source.backup(target)
            finally:source.close();target.close()
            Workspace(self.root)._app(original_session)
            with self.assertRaisesRegex(Conflict,'bound original'):
                self.resolve_legacy(app,scope,run,fingerprint=item['fingerprint'])
            self.assertTrue(app.execution.pending(scope,run))
        finally:
            journal.unlink();saved.rename(journal)
        decision=self.resolve_legacy(app,scope,run,fingerprint=item['fingerprint'])
        self.assertEqual(decision['known_calls'],6)
        self.assertTrue(self.usage()['accounting_complete'])

    def test_unbound_legacy_history_cannot_authorize_independence_from_a_root_witness(self):
        from acquisition.adapters.sqlite.workspace_ancestry import JOURNAL_BINDING_KEY
        app,scope,run=self.legacy_cli('pre-identity-cli','pre-identity-cli')
        with app.calls.database.transaction() as db:db.execute('DELETE FROM execution_commands WHERE request_id=?',(JOURNAL_BINDING_KEY,))
        with self.w.control() as db:db.execute('DROP TABLE workspace_identity')
        self.w=Workspace(self.root,real_clock=lambda:1792972800.)
        self.w._app(self.w._session(self.sid))
        with self.assertRaisesRegex(Conflict,'not bound'):app.execution.unresolved(scope)
        with self.assertRaisesRegex(Conflict,'not bound'):
            self.resolve_legacy(app,scope,run,fingerprint='0'*64)
        self.assertTrue(app.execution.pending(scope,run))
        with app.calls.database.connect() as db:
            self.assertIsNone(db.execute('SELECT 1 FROM execution_commands WHERE organization=? AND request_id=?',(scope,JOURNAL_BINDING_KEY)).fetchone())

    def test_fresh_recreated_journal_cannot_adopt_history_even_after_matching_rows_are_added(self):
        from acquisition.adapters.sqlite.workspace_ancestry import JOURNAL_BINDING_KEY
        app,scope,run=self.legacy_cli('unbound-lost-journal','unbound-lost-journal')
        root_session=self.w._session(self.sid)
        with app.calls.database.transaction() as db:db.execute('DELETE FROM execution_commands WHERE request_id=?',(JOURNAL_BINDING_KEY,))
        journal=self.root/'workspace.sqlite';saved=self.root/'original-workspace.saved';journal.rename(saved)
        try:
            replacement=Workspace(self.root,real_clock=lambda:1792972800.)
            with replacement.control() as db:db.execute('INSERT INTO sessions VALUES(?,?,?)',(self.sid,'recreated-record',json.dumps(root_session)))
            replacement._app(root_session)
            with self.assertRaisesRegex(Conflict,'not bound'):app.execution.unresolved(scope)
            with app.calls.database.connect() as db:
                self.assertIsNone(db.execute('SELECT 1 FROM execution_commands WHERE organization=? AND request_id=?',(scope,JOURNAL_BINDING_KEY)).fetchone())
            self.assertTrue(app.execution.pending(scope,run))
        finally:journal.unlink();saved.rename(journal)

    def test_journal_identity_persists_and_cannot_be_reassigned(self):
        import sqlite3
        with self.w.control() as db:identity=tuple(db.execute('SELECT * FROM workspace_identity').fetchone())
        Workspace(self.root,real_clock=lambda:1792972800.)
        with self.w.control() as db:
            self.assertEqual(tuple(db.execute('SELECT * FROM workspace_identity').fetchone()),identity)
            with self.assertRaisesRegex(sqlite3.IntegrityError,'immutable'):db.execute("UPDATE workspace_identity SET journal_id='different'")
            with self.assertRaisesRegex(sqlite3.IntegrityError,'immutable'):db.execute('DELETE FROM workspace_identity')

    def test_unrelated_legacy_journal_with_matching_campaign_names_is_not_a_binding_witness(self):
        import sqlite3
        from acquisition.adapters.sqlite.workspace_ancestry import JOURNAL_BINDING_KEY
        app,scope,run=self.legacy_cli('legacy-lookalike','legacy-lookalike')
        original_session=self.w._session(self.sid)
        other=handoff_tests.ConversationHandoffTests('test_expired_approval_or_changed_reviewer_cannot_accept')
        other.setUp();self.addCleanup(other.doCleanups)
        self.assertEqual(other.sid,self.sid)
        self.assertNotEqual(other.w._session(other.sid)['run_id'],original_session['run_id'])
        for workspace in (self.w,other.w):
            with workspace.control() as db:db.execute('DROP TABLE workspace_identity')
        with app.calls.database.transaction() as db:db.execute('DELETE FROM execution_commands WHERE request_id=?',(JOURNAL_BINDING_KEY,))
        Workspace(other.root)  # Pin this unrelated, populated legacy journal.
        journal=self.root/'workspace.sqlite';saved=self.root/'original-legacy.saved';journal.rename(saved)
        try:
            source=sqlite3.connect(other.root/'workspace.sqlite');target=sqlite3.connect(journal)
            try:source.backup(target)
            finally:source.close();target.close()
            Workspace(self.root)._app(original_session)
            with self.assertRaisesRegex(Conflict,'not bound'):app.execution.unresolved(scope)
            self.assertTrue(app.execution.pending(scope,run))
        finally:journal.unlink();saved.rename(journal)
        self.w=Workspace(self.root,real_clock=lambda:1792972800.)
        self.w._app(original_session)
        with self.assertRaisesRegex(Conflict,'not bound'):app.execution.unresolved(scope)
    def test_resolution_requires_current_scoped_operator_and_exact_inspection(self):
        from acquisition.reviews import ActorUnavailable
        app,scope,run=self.legacy_cli('operator-cli','operator-cli')
        item=app.execution.unresolved(scope)[0]
        for actor in ('missing-operator','local-reviewer'):
            with self.assertRaises(ActorUnavailable):self.resolve_legacy(app,scope,run,fingerprint=item['fingerprint'],actor=actor)
        app.reviews.store.register_actor(scope,'local-operator',('operator',),False)
        with self.assertRaises(ActorUnavailable):self.resolve_legacy(app,scope,run,fingerprint=item['fingerprint'])
        app.reviews.store.register_actor(scope,'local-operator',('operator',),True)
        with self.assertRaises(NotFound):self.resolve_legacy(app,'other-org',run,fingerprint=item['fingerprint'])
        with app.calls.database.transaction() as db:
            row=db.execute('SELECT call_key,response FROM model_calls WHERE organization=? AND run_id=? LIMIT 1',(scope,run)).fetchone()
            response=json.loads(row['response']);response['usage']['cost']=0.5
            db.execute('UPDATE model_calls SET response=? WHERE organization=? AND run_id=? AND call_key=?',(json.dumps(response),scope,run,row['call_key']))
        with self.assertRaisesRegex(Conflict,'changed'):self.resolve_legacy(app,scope,run,fingerprint=item['fingerprint'])
        self.assertTrue(app.execution.pending(scope,run))
        self.resolve_legacy(app,scope,run)

    def test_stale_populated_legacy_backup_cannot_prove_absence_of_later_descendants(self):
        import sqlite3
        from acquisition.adapters.sqlite.workspace_ancestry import JOURNAL_BINDING_KEY
        self.finalized_parent()
        with self.w.control() as db:db.execute('DROP TABLE workspace_identity')
        backup=self.root/'stale-populated.sqlite'
        source=sqlite3.connect(self.root/'workspace.sqlite');target=sqlite3.connect(backup)
        try:source.backup(target)
        finally:source.close();target.close()
        child=self.manual_child('after-backup');model=copy_tests.CopyRoutingModel()
        from acquisition.runtime import Worker
        with patch('acquisition.workspace.openrouter_key',return_value='fixture'),patch('acquisition.workspace.OpenRouter',return_value=model):
            # This fixture represents admission by the pre-identity application.
            from acquisition.adapters.sqlite.workspace_ancestry import initialize_workspace_identity
            with self.w.control() as db:initialize_workspace_identity(db)
            with patch.object(Worker,'drain',return_value=0),self.assertRaises(Conflict):self.w.prepare(child)
        session=self.w._session(child);app=self.w._app(session);scope,run=session['organization'],session['run_id']
        with app.calls.database.transaction() as db:
            db.execute('DELETE FROM execution_runs WHERE organization=? AND run_id=?',(scope,run))
            db.execute('DELETE FROM execution_commands WHERE organization=? AND request_id=?',(scope,'descendant:'+child))
            db.execute('DELETE FROM execution_commands WHERE request_id=?',(JOURNAL_BINDING_KEY,))
            db.execute('INSERT INTO execution_pending_origins VALUES(?,?)',(scope,run))
        journal=self.root/'workspace.sqlite';complete=self.root/'complete-legacy.saved';journal.rename(complete);backup.rename(journal)
        before=app.tasks.inspect(scope,run)
        try:
            restored=Workspace(self.root,real_clock=lambda:1792972800.)
            restored._app(restored._session(self.sid))
            with self.assertRaisesRegex(Conflict,'not bound'):app.execution.unresolved(scope)
            with self.assertRaisesRegex(Conflict,'not bound'):
                self.resolve_legacy(app,scope,run,fingerprint='0'*64,reason='Incorrect independence attestation against a stale backup.')
            self.assertTrue(app.execution.pending(scope,run))
            self.assertEqual(app.tasks.inspect(scope,run),before)
            with app.calls.database.connect() as db:
                self.assertIsNone(db.execute('SELECT 1 FROM execution_commands WHERE organization=? AND request_id=?',(scope,JOURNAL_BINDING_KEY)).fetchone())
                self.assertEqual(db.execute("SELECT COUNT(*) FROM execution_commands WHERE request_id LIKE 'independent:%' OR request_id LIKE 'resolution:%'").fetchone()[0],0)
        finally:journal.unlink();complete.rename(journal)
        self.w=Workspace(self.root,real_clock=lambda:1792972800.)
        self.w.recover_execution()
        self.assertFalse(app.execution.pending(scope,run))
        self.w.stop_execution(self.c,'stop-complete-restoration',1)
        self.assertEqual(app.tasks.inspect(scope,run)['run']['status'],'cancelled')

    def test_old_weak_binding_receipt_is_not_current_independence_authority(self):
        from acquisition.adapters.sqlite.workspace_ancestry import JOURNAL_BINDING_KEY
        model=copy_tests.CopyRoutingModel()
        with patch('acquisition.workspace.openrouter_key',return_value='fixture'),patch('acquisition.workspace.OpenRouter',return_value=model):
            session,_=self.legacy_manual(model)
            app=self.w._app(session)
        scope,run=session['organization'],session['run_id']
        inputs={'run_id':run,'fingerprint':'0'*64,'actor':'local-operator','reason':'Old incorrect attestation.'}
        with app.calls.database.transaction() as db:
            binding=json.loads(db.execute('SELECT receipt FROM execution_commands WHERE organization=? AND request_id=?',(scope,JOURNAL_BINDING_KEY)).fetchone()[0])
            binding.update(basis='verified_legacy_campaign',witness={'run_id':self.w._session(self.sid)['run_id']})
            db.execute('UPDATE execution_commands SET inputs=?,receipt=? WHERE organization=? AND request_id=?',(json.dumps(binding),json.dumps(binding),scope,JOURNAL_BINDING_KEY))
            request_hash=db.execute('SELECT request_hash FROM runs WHERE organization=? AND id=?',(scope,run)).fetchone()[0]
            receipt={'kind':'independent_execution_resolution','inputs':inputs,'request_hash':request_hash,'known_calls':0,'actor_generation':1,'at':1792972800.}
            for key in ('independent:'+run,'resolution:old-resolution'):
                db.execute('INSERT INTO execution_commands VALUES(?,?,?,?)',(scope,key,json.dumps(inputs),json.dumps(receipt)))
            db.execute('DELETE FROM execution_pending_origins WHERE organization=? AND run_id=?',(scope,run))
        Database(app.calls.database.path)
        self.assertTrue(app.execution.pending(scope,run))
        self.assertIsNone(app.execution.view('local-conversations',self.c)['remaining'])
        self.assertEqual(self.resolve_legacy(app,scope,run,request='old-resolution',fingerprint=inputs['fingerprint'],reason=inputs['reason']),receipt)
        self.assertTrue(app.execution.pending(scope,run))
        with self.assertRaisesRegex(Conflict,'completeness'):
            self.resolve_legacy(app,scope,run,request='new-resolution',fingerprint=inputs['fingerprint'])
        self.w.recover_execution()
        self.assertFalse(app.execution.pending(scope,run))
        self.assertTrue(self.usage()['accounting_complete'])
        with app.calls.database.connect() as db:
            self.assertEqual(json.loads(db.execute('SELECT receipt FROM execution_commands WHERE organization=? AND request_id=?',(scope,'resolution:old-resolution')).fetchone()[0]),receipt)

    def test_invalid_journal_identity_releases_writer_lock_without_garbage_collection(self):
        import gc
        import sqlite3
        from acquisition.adapters.sqlite.workspace_ancestry import workspace_ancestry_guard,initialize_workspace_identity
        with self.w.control() as db:original=tuple(db.execute('SELECT * FROM workspace_identity').fetchone())
        errors=[];enabled=gc.isenabled();gc.disable()
        try:
            for rows in ([(1,'bad','fresh')],[],[(1,original[1],'invalid-origin')],[(1,None,'fresh')]):
                with self.subTest(rows=rows):
                    with self.w.control() as db:
                        db.execute('DROP TABLE workspace_identity')
                        db.execute('CREATE TABLE workspace_identity(singleton,journal_id,origin)')
                        db.executemany('INSERT INTO workspace_identity VALUES(?,?,?)',rows)
                    try:
                        with workspace_ancestry_guard(self.root/'conversations.sqlite'):
                            self.fail('Malformed journal identity was accepted')
                    except Conflict as error:errors.append(error)  # Retain its traceback and connection frame.
                    other=sqlite3.connect(self.root/'workspace.sqlite',timeout=0,isolation_level=None)
                    try:
                        other.execute('BEGIN IMMEDIATE')
                        other.execute('UPDATE sessions SET request_hash=request_hash WHERE id=?',(self.sid,))
                        other.commit()
                    finally:other.close()
        finally:
            errors.clear()
            if enabled:gc.enable()
            gc.collect()
            with self.w.control() as db:
                db.execute('DROP TABLE workspace_identity')
                db.execute('CREATE TABLE workspace_identity(singleton,journal_id,origin)')
                db.execute('INSERT INTO workspace_identity VALUES(?,?,?)',original)
                initialize_workspace_identity(db)

    def test_resolution_fault_rolls_back_receipt_event_and_fence_removal(self):
        import sqlite3
        app,scope,run=self.legacy_cli('atomic-cli','atomic-cli')
        item=app.execution.unresolved(scope)[0]
        with app.calls.database.transaction() as db:
            db.execute("CREATE TRIGGER fail_origin_event BEFORE INSERT ON events WHEN NEW.kind='execution_origin_resolved' BEGIN SELECT RAISE(ABORT,'injected audit failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):self.resolve_legacy(app,scope,run,fingerprint=item['fingerprint'])
        self.assertTrue(app.execution.pending(scope,run))
        with app.calls.database.transaction() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM execution_commands WHERE request_id LIKE 'independent:%' OR request_id LIKE 'resolution:%'").fetchone()[0],0)
            db.execute('DROP TRIGGER fail_origin_event')
        self.resolve_legacy(app,scope,run,fingerprint=item['fingerprint'])

    def test_reconciliation_cli_inspects_and_resolves_without_a_provider(self):
        app,scope,run=self.legacy_cli('cli-resolution','cli-resolution')
        prefix=[sys.executable,'-m','acquisition','--db',str(app.calls.database.path),'--organization',scope]
        env=dict(os.environ,PYTHONPATH='src',OPENROUTER_API_KEY='')
        inspected=subprocess.run(prefix+['execution-unresolved'],env=env,text=True,capture_output=True,timeout=10)
        self.assertEqual(inspected.returncode,0,inspected.stderr)
        item=json.loads(inspected.stdout)[0]
        args=['execution-resolve-independent','--run',run,'--request-id','cli-attestation','--fingerprint',item['fingerprint'],
              '--actor','local-operator','--reason','Verified independent legacy CLI run.']
        resolved=subprocess.run(prefix+args,env=env,text=True,capture_output=True,timeout=10)
        self.assertEqual(resolved.returncode,0,resolved.stderr)
        replay=subprocess.run(prefix+args,env=env,text=True,capture_output=True,timeout=10)
        self.assertEqual(replay.returncode,0,replay.stderr)
        self.assertEqual(json.loads(resolved.stdout),json.loads(replay.stdout))
        self.assertTrue(self.usage()['accounting_complete'])

    def test_reconciled_queued_independent_run_resumes_without_consuming_conversation_allowance(self):
        app,scope,run=self.legacy_cli('queued-independent','queued-independent',completed=False)
        self.w.stop_execution(self.c,'stop-conversation',1)
        self.resolve_legacy(app,scope,run)
        with patch.object(app.inference.gateway,'complete',wraps=app.inference.gateway.complete) as provider:
            app.worker.drain(scope,run_id=run)
            self.assertEqual(provider.call_count,6)
        self.assertEqual(app.tasks.inspect(scope,run)['run']['status'],'waiting')
        self.assertEqual(len(app.calls.inspect(scope,run)),6)
        self.assertEqual(self.usage()['used'],0)
        self.assertTrue(self.usage()['stopped'])

    def test_competing_independent_resolutions_record_one_decision_and_reject_changed_identity(self):
        app,scope,run=self.legacy_cli('competing-independent','competing-independent')
        item=app.execution.unresolved(scope)[0]
        def resolve(key):
            try:return self.resolve_legacy(app,scope,run,request=key,fingerprint=item['fingerprint'],reason='Verified by '+key)
            except Conflict:return None
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(resolve,('one','two')))
        self.assertEqual(sum(r is not None for r in results),1)
        self.assertEqual(sum(e['kind']=='execution_origin_resolved' for e in app.tasks.inspect(scope,run)['events']),1)
        _,_,other=self.legacy_cli('another-independent','another-independent')
        winner='one' if results[0] else 'two'
        with self.assertRaises(Conflict):self.resolve_legacy(app,scope,other,request=winner,reason='Verified by '+winner)
        self.assertTrue(app.execution.pending(scope,other))

    def test_active_or_proven_conversation_runs_cannot_be_declared_independent(self):
        app,scope,run=self.legacy_cli('active-cli','active-cli',completed=False)
        claim=app.tasks.claim(scope,app.clock(),180,run_id=run)
        self.assertIsNone(claim)  # Quarantine prevents even the inspect task.
        with app.calls.database.transaction() as db:
            db.execute("UPDATE tasks SET status='running' WHERE run_id=? AND position=0",(run,))
        with self.assertRaisesRegex(Conflict,'active run'):self.resolve_legacy(app,scope,run)
        with app.calls.database.transaction() as db:
            db.execute("UPDATE tasks SET status='queued' WHERE run_id=? AND position=0",(run,))
            parent=self.w._session(self.sid)['run_id']
            inputs={'kind':'descendant_admission','campaign_id':'active-cli','parent_run_id':parent}
            db.execute('INSERT INTO execution_commands VALUES(?,?,?,?)',(scope,'descendant:active-cli',json.dumps(inputs),json.dumps(inputs)))
        with self.assertRaisesRegex(Conflict,'proven conversation'):self.resolve_legacy(app,scope,run)

    def test_campaign_reference_never_crosses_organization_scope(self):
        app,scope,run=self.legacy_cli('foreign-cli',self.sid,organization='another-organization')
        Database(app.calls.database.path)
        with app.calls.database.connect() as db:
            self.assertIsNone(db.execute('SELECT * FROM execution_runs WHERE organization=? AND run_id=?',(scope,run)).fetchone())
        self.assertTrue(app.execution.pending(scope,run))
        self.assertEqual(self.usage()['used'],0)

    def test_planner_request_identity_is_not_campaign_provenance(self):
        with self.w._conversation_app().calls.database.connect() as db:
            request=db.execute('''SELECT r.request_id FROM runs r JOIN tasks t ON t.run_id=r.id
                WHERE r.organization=? AND t.capability='conversations.fixture_plan.v1' ''',('local-conversations',)).fetchone()[0]
        app,scope,run=self.legacy_cli('planner-collision',request,organization='local-conversations')
        Database(app.calls.database.path)
        self.assertTrue(app.execution.pending(scope,run))
        with app.calls.database.connect() as db:
            self.assertIsNone(db.execute('SELECT * FROM execution_runs WHERE organization=? AND run_id=?',(scope,run)).fetchone())

    def test_known_cost_subtotal_is_preserved_while_other_calls_are_unattributed(self):
        # Provider-reported cost is part of the original fake receipt, not a bill.
        app,scope,run=self.legacy_cli('known-cli',self.sid,cost=0.01)
        Database(app.calls.database.path)
        self.legacy_cli('unknown-cli','unknown-campaign')
        usage=self.usage()
        self.assertEqual(usage['used'],6)
        self.assertEqual(usage['cost_reported_calls'],6)
        self.assertEqual(usage['reported_cost_usd'],'0.06')
        self.assertFalse(usage['accounting_complete'])
        self.assertFalse(usage['cost_complete'])

    def test_schema_ten_fence_rolls_back_without_rewriting_history(self):
        import sqlite3
        import acquisition.adapters.sqlite.execution as execution_adapter
        model=copy_tests.CopyRoutingModel()
        with patch('acquisition.workspace.openrouter_key',return_value='fixture'),patch('acquisition.workspace.OpenRouter',return_value=model):
            session,_=self.legacy_manual(model)
        path=self.root/'conversations.sqlite'
        original=execution_adapter.quarantine_old_origins
        def interrupt(db):
            original(db)
            raise OSError('after ancestry fence')
        with sqlite3.connect(path) as db:
            calls=db.execute('SELECT * FROM model_calls ORDER BY rowid').fetchall()
            cutoff=db.execute('SELECT * FROM legacy_task_admissions').fetchall()
        with patch.object(execution_adapter,'quarantine_old_origins',side_effect=interrupt),self.assertRaises(OSError):Database(path)
        with sqlite3.connect(path) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],9)
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='execution_pending_origins'").fetchone())
            self.assertEqual(db.execute('SELECT * FROM model_calls ORDER BY rowid').fetchall(),calls)
            self.assertEqual(db.execute('SELECT * FROM legacy_task_admissions').fetchall(),cutoff)
        app=self.w._app(session)
        self.assertTrue(app.execution.pending(session['organization'],session['run_id']))

    def checkpoint(self, request):
        from acquisition.adapters.sqlite.reviews import SqliteReviews
        from acquisition.conversations import FIXTURE_MESSAGE
        c=self.w.create_conversation(request,'Recovery boundary')['id']
        self.w.message_conversation(c,'m',0,FIXTURE_MESSAGE)
        self.w.start_preparation(c,'prepare-'+request,1,True,False)
        with patch.object(SqliteReviews,'open_case',side_effect=OSError('case storage unavailable')):
            for _ in range(6):self.w.advance_preparations()
        sid=self.w.conversation(c)['campaigns'][0]['session_id']
        return c,sid

    def test_disabled_checkpoint_operator_does_not_block_startup_or_other_recovery(self):
        from acquisition.adapters.sqlite.reviews import SqliteReviews
        from acquisition.workspace_server import WorkspaceServer
        import urllib.request
        bad,bad_sid=self.checkpoint('disabled-checkpoint')
        healthy,healthy_sid=self.checkpoint('healthy-checkpoint')
        with patch.object(SqliteReviews,'open_case',side_effect=OSError('case storage unavailable')):
            self.w.stop_execution(bad,'stop-bad',1)
            self.w.stop_execution(healthy,'stop-healthy',1)
        session=self.w._session(bad_sid);app=self.w._app(session)
        app.reviews.store.register_actor(session['organization'],'local-operator',('operator',),False)
        reopened=Workspace(self.root,real_clock=lambda:1792972800.)
        assets=self.root/'server-assets';assets.mkdir();(assets/'index.html').write_text('<meta name="workspace-token" content="__WORKSPACE_TOKEN__">')
        server=WorkspaceServer(0,reopened,assets)
        thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with urllib.request.urlopen('http://127.0.0.1:'+str(server.server_port),timeout=5) as response:
                self.assertEqual(response.status,200)
            self.assertIsNotNone(reopened._session(healthy_sid)['case_id'])
            self.assertIsNone(reopened._session(bad_sid)['case_id'])
            recovery=reopened.conversation(bad)['preparations'][0]
            self.assertEqual(recovery['status'],'blocked')
            self.assertEqual(recovery['checkpoint_recovery']['code'],'checkpoint_authority_unavailable')
            self.assertIn('permitted local operator',recovery['detail'])
            with app.calls.database.connect() as db:
                self.assertEqual(db.execute('SELECT enabled FROM review_actors WHERE organization=? AND id=?',(session['organization'],'local-operator')).fetchone()[0],0)
            app.reviews.store.register_actor(session['organization'],'local-operator',('operator',),True)
            reopened.recover_execution()
            self.assertEqual(reopened.conversation(bad)['preparations'][0]['status'],'review_ready')
            self.assertFalse(reopened.view(bad_sid)['review']['approval_valid'])
        finally:
            server.shutdown();server.server_close();thread.join(5)

    def test_existing_case_reconciles_cancelled_progress_after_journal_failure(self):
        c,sid=self.checkpoint('journal-gap')
        original=self.w.preparations.store.update
        def interrupt(*args,**kwargs):
            if args[2]=='review_ready':raise OSError('after case metadata')
            return original(*args,**kwargs)
        with patch.object(self.w.preparations.store,'update',side_effect=interrupt):
            stopped=self.w.stop_execution(c,'stop-journal-gap',1)
        case=self.w._session(sid)['case_id'];self.assertIsNotNone(case)
        self.assertEqual(self.w.preparations.store.for_revision('local-conversations',c,1)['status'],'cancelled')
        self.assertEqual(stopped['preparations'][0]['checkpoint_recovery']['code'],'checkpoint_storage_unavailable')
        reopened=Workspace(self.root,real_clock=lambda:1792972800.)
        with patch('acquisition.workspace.OpenRouter',side_effect=AssertionError('recovery dispatched inference')):
            reopened.recover_execution()
            row=reopened.preparations.store.for_revision('local-conversations',c,1)
            self.assertEqual(row['status'],'review_ready')
            self.assertIsNone(reopened.conversation(c)['preparations'][0]['generation']['checkpoint_recovery'])
            reopened.recover_execution()
        self.assertEqual(reopened._session(sid)['case_id'],case)
        self.assertEqual(reopened.preparations.store.for_revision('local-conversations',c,1)['epoch'],row['epoch'])
        review=reopened.view(sid)['review']
        self.assertEqual(sum(e['kind']=='review_opened' for e in review['events']),1)
        self.assertFalse(review['approval_valid'])

    def test_checkpoint_recovery_remains_pollable_after_old_progress_loses_its_blocker(self):
        from acquisition.adapters.sqlite.reviews import SqliteReviews
        c,sid=self.checkpoint('progress-read-race')
        unrelated,_=self.checkpoint('another-progress-read-race')
        self.w.stop_execution(unrelated,'stop-another-progress-read-race',1)
        before=self.w.conversation(c)
        self.assertFalse(before['campaigns'][0]['generation'].get('checkpoint_recovery_pending',False))
        with patch.object(SqliteReviews,'open_case',side_effect=OSError('case storage unavailable')):
            self.w.stop_execution(c,'stop-progress-read-race',1)
        original=self.w.preparation_generation
        interleaved=[]
        def recover_after_progress_snapshot(organization,row):
            if row['inputs']['conversation_id']==c and not interleaved:
                self.assertEqual(row['status'],'cancelled')
                interleaved.append(True)
                self.w.recover_execution()
            return original(organization,row)
        with patch.object(self.w,'preparation_generation',side_effect=recover_after_progress_snapshot), \
                patch('acquisition.workspace.OpenRouter',side_effect=AssertionError('projection recovery dispatched inference')):
            packet=self.w.conversation(c)
        self.assertEqual(interleaved,[True])
        self.assertEqual(packet['preparations'][0]['status'],'cancelled')
        self.assertNotIn('checkpoint_recovery',packet['preparations'][0])
        campaign=packet['campaigns'][0]
        self.assertIsNone(campaign['case_id'])
        self.assertIsNone(campaign['generation']['checkpoint_recovery'])
        self.assertTrue(campaign['generation'].get('checkpoint_recovery_pending',False))
        self.assertEqual(packet['execution']['used'],before['execution']['used'])
        ready=self.w.conversation(c)
        self.assertEqual(ready['preparations'][0]['status'],'review_ready')
        self.assertIsNotNone(ready['campaigns'][0]['case_id'])
        self.assertFalse(ready['campaigns'][0]['generation']['checkpoint_recovery_pending'])
        self.assertFalse(self.w.view(sid)['review']['approval_valid'])

    def test_model_followup_inherits_the_parent_conversation_allowance(self):
        self.model=copy_tests.CopyRoutingModel()
        subject=self.state['review']['subject']['id']
        state=self.w.action(self.sid,'approve',{'request_id':'approve','subject_id':subject,'reason':'Reviewed exact campaign.'})
        self.w.action(self.sid,'handoff',{'request_id':'handoff','approval_id':state['review']['approval']['id']})
        self.w.action(self.sid,'open-learning',{'request_id':'open'})
        self.w.action(self.sid,'finalize',{'request_id':'finalize'})
        parent=self.w._session(self.sid)
        proposal=self.w.propose_followup(self.sid,'next',parent['cohort_id'])
        before=self.usage()['used'];calls=[];original=self.model.complete
        def observed(request):
            calls.append(request)
            return original(request)
        with patch('acquisition.workspace.openrouter_key',return_value='fixture'), patch('acquisition.workspace.OpenRouter',return_value=self.model), patch.object(self.model,'complete',side_effect=observed):
            child=self.w.prepare_followup(self.sid,'prepare-next',proposal['id'],'model',True)
        self.assertTrue(calls)
        self.assertEqual(self.usage()['used'],before+len(calls))
        self.assertIn(child['session']['run_id'],{c['run_id'] for c in self.usage()['calls']})
