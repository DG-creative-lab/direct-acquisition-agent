"""Selected source identity, effect boundaries and recovery through real SQLite."""
import copy
import json
import os
import subprocess
import shutil
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

from acquisition.adapters.sqlite.database import Database, AUDIENCE_SELECTIONS
from acquisition.bootstrap import build
from acquisition.campaigns import build_draft, brief_from
from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.conversations import AudienceSelectionRejected, FIXTURE_MESSAGE
from acquisition.workspace import Workspace
from test_preparations import CombinedModel


class ConversationAudienceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.now=1793404800.
        self.w=Workspace(self.root, real_clock=lambda:self.now)
        self.c=self.w.create_conversation('c','Audience experiment')['id']
        self.model=CombinedModel()
        for p in (patch('acquisition.workspace.openrouter_key',return_value='fixture'),
                  patch('acquisition.workspace.OpenRouter',return_value=self.model)):
            p.start();self.addCleanup(p.stop)

    def waiting(self, model=False):
        self.w.message_conversation(self.c,'message',0,'Prepare a £600 contractor experiment with model copy.' if model else FIXTURE_MESSAGE)
        self.w.start_preparation(self.c,'prepare',1,not model,model,True)
        for _ in range(4):self.w.advance_preparations()
        view=self.w.conversation(self.c)
        self.assertEqual(view['preparations'][0]['status'],'selecting_audience')
        self.assertEqual(view['campaigns'],[])
        self.assertEqual(self.model.copy.requests,[])
        self.plan=view['current_plan']['result']
        self.entries=view['preparations'][0]['audience_candidates']['entries']
        return view

    def selection(self, entry=None, request_id='selection'):
        e=entry or self.entries[0]
        return dict(request_id=request_id,expected_revision=1,plan_id=self.plan['id'],
                    dataset_id=e['dataset_id'],version=e['version'],checksum=e['checksum'],manifest_id=e['id'])

    def choose(self, entry=None, request_id='selection'):
        return self.w.select_conversation_audience(self.c,**self.selection(entry,request_id))

    def finish(self):
        for _ in range(8):self.w.advance_preparations()
        view=self.w.conversation(self.c)
        self.assertEqual(view['preparations'][0]['status'],'review_ready',view['preparations'][0])
        return self.w.view(view['campaigns'][0]['session_id'])

    def test_chat_selection_uses_exact_source_population_and_requires_fresh_approval(self):
        self.waiting()
        with self.assertRaises(Conflict):
            self.w.draft_conversation(self.c,'bypass',1,self.plan['id'])
        selected=self.choose()['audience_receipt'];view=self.finish()
        manifest=view['review']['manifest']
        self.assertEqual(manifest['counts']['input'],100)
        self.assertEqual(manifest['brief']['audience_source'],selected)
        self.assertTrue(view['review']['validation_report']['review_ready'])
        self.assertFalse(view['review']['approval_valid'])
        session=self.w._session(view['session']['id']);app=self.w._app(session)
        source=app.audiences.get('local-conversations',selected['source_snapshot_id'])
        target=app.audiences.get(session['organization'],manifest['snapshot_id'])
        self.assertEqual(source.records,target.records)
        self.assertNotEqual(source.organization,target.organization)
        self.assertNotEqual(source.id,target.id)
        with self.assertRaises((Conflict,NotFound)):self.w.action(session['id'],'handoff',{'request_id':'no-approval','approval_id':'invented'})
        approved=self.w.action(session['id'],'approve',{'request_id':'approve','subject_id':view['review']['subject']['id'],'reason':'Reviewed exact source, population and copy.'})
        self.assertTrue(approved['review']['approval_valid'])
        self.assertEqual(json.loads(self.w.artifact(session['id'],'manifest',approved['review']['subject']['id'])[0])['brief']['audience_source'],selected)

    def test_model_context_and_review_bind_source_without_inheriting_authority(self):
        self.waiting(model=True);selected=self.choose()['audience_receipt'];view=self.finish()
        self.assertEqual(len(self.model.copy.requests),3)
        session=self.w._session(view['session']['id']);app=self.w._app(session)
        creative=view['review']['manifest']['creatives'][0]
        context=app.memory.get_context(session['organization'],creative['context_id'])
        self.assertEqual(context['audience_summary']['input_records'],100)
        self.assertEqual(context['audience_summary']['dataset_source']['selection_id'],selected['id'])
        self.assertEqual(context['audience_summary']['dataset_source']['checksum'],selected['source']['checksum'])
        self.assertFalse(view['review']['approval_valid'])

    def test_exact_request_replay_survives_unavailable_catalogue_and_process_restart(self):
        self.waiting();receipt=self.choose()['audience_receipt']
        with patch('acquisition.adapters.local_audiences.LocalAudienceSource._bytes',side_effect=OSError('unavailable')):
            replay=self.choose()['audience_receipt'];self.assertEqual(receipt,replay)
            self.w=Workspace(self.root,real_clock=lambda:self.now)
            view=self.finish();self.assertEqual(view['review']['manifest']['counts']['input'],100)
        code='''import json,sys
from acquisition.workspace import Workspace
w=Workspace(sys.argv[1],real_clock=lambda:1793404800.)
v=w.conversation(sys.argv[2]);s=w.view(v['campaigns'][0]['session_id'])
print(json.dumps(s['review']['manifest']['brief']['audience_source']))
'''
        p=subprocess.run([sys.executable,'-c',code,str(self.root),self.c],env=dict(os.environ,PYTHONPATH=str(Path('src').resolve())),capture_output=True,text=True,timeout=10)
        self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(json.loads(p.stdout),receipt)

    def test_selection_identity_rejects_changed_inputs_and_another_valid_version(self):
        self.waiting();receipt=self.choose()['audience_receipt']
        for entry,key in ((self.entries[1],'selection'),(self.entries[1],'new-selection')):
            with self.assertRaises(AudienceSelectionRejected):self.choose(entry,key)
        self.assertEqual(self.choose(request_id='same-version')['audience_receipt'],receipt)
        with self.assertRaises(AudienceSelectionRejected):
            self.w.select_conversation_audience(self.c,**(self.selection()|{'plan_id':'brief_other'}))

    def test_concurrent_different_versions_commit_one_population(self):
        self.waiting()
        def choose(entry):
            try:return self.choose(entry,entry['version'])['audience_receipt']
            except AudienceSelectionRejected:return None
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(choose,self.entries))
        self.assertEqual(sum(r is not None for r in results),1)
        selected=next(r for r in results if r)
        self.assertEqual(self.finish()['review']['manifest']['counts']['input'],selected['source']['record_count'])

    def test_revision_edit_between_source_read_and_commit_leaves_no_selection(self):
        self.waiting();original=self.w._conversation_app().conversation_audiences.store.__class__.select
        def interleave(store,*args):
            self.w.message_conversation(self.c,'edit',1,'Change the budget to £700.')
            return original(store,*args)
        with patch('acquisition.adapters.sqlite.audience_selections.SqliteAudienceSelections.select',new=interleave):
            with self.assertRaises(AudienceSelectionRejected):self.choose()
        self.assertIsNone(self.w._conversation_app().conversation_audiences.store.get('local-conversations',self.c,1))
        self.assertEqual(self.w.listing()['sessions'],[])

    def test_partial_selection_write_rolls_back_snapshot_selection_and_receipt(self):
        self.waiting();app=self.w._conversation_app()
        with app.tasks.database.connect() as db:
            db.execute("CREATE TRIGGER abort_selection BEFORE INSERT ON conversation_audiences BEGIN SELECT RAISE(ABORT,'fault'); END")
        with self.assertRaises(Exception):self.choose()
        with app.tasks.database.connect() as db:
            for table in ('audiences','conversation_audiences','audience_selection_requests'):
                self.assertEqual(db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0],0)
            db.execute('DROP TRIGGER abort_selection')
        self.choose();self.finish()

    def test_new_message_invalidates_selection_and_old_approval(self):
        self.waiting();receipt=self.choose()['audience_receipt'];view=self.finish()
        session=self.w._session(view['session']['id']);subject=view['review']['subject']['id']
        self.w.action(session['id'],'approve',{'request_id':'approve','subject_id':subject,'reason':'Reviewed exact synthetic campaign.'})
        self.w.message_conversation(self.c,'edit',1,'Use £700 instead.')
        self.assertEqual(self.choose()['audience_receipt'],receipt) # Historical observation only.
        current=self.w.view(session['id']);self.assertFalse(current['review']['approval_valid'])
        self.assertFalse(current['review']['validation_report']['review_ready'])
        with self.assertRaises(Conflict):self.w.action(session['id'],'approve',{'request_id':'stale','subject_id':subject,'reason':'Attempted old subject.'})

    def test_source_substitution_and_provenance_stripping_fail_at_draft_commit(self):
        self.waiting();self.choose();view=self.finish();s=self.w._session(view['session']['id']);app=self.w._app(s)
        original=app.drafts.get(s['organization'],view['review']['subject']['draft_id'])
        snapshot=app.audiences.get(s['organization'],original.manifest['snapshot_id'])
        from acquisition.reviews import creatives_from
        for mutate in ('remove','replace','rows'):
            brief=copy.deepcopy(original.manifest['brief']);target=snapshot
            if mutate=='remove':brief.pop('audience_source')
            elif mutate=='replace':
                brief['audience_source']['source']['version']='v2'
                brief['audience_source']['id']='selection_'+digest({k:v for k,v in brief['audience_source'].items() if k!='id'})
            else:target=replace(snapshot,records=snapshot.records[:-1])
            identity=app.audiences.put(target)
            draft=build_draft(target,brief_from(brief),creatives_from(original))
            with self.subTest(mutate=mutate),self.assertRaises(Conflict):app.drafts.put(s['organization'],'substitute-'+mutate,draft)

    def short_source_window(self):
        from acquisition.adapters.local_audiences import LocalAudienceSource
        root=self.root/'short-window';shutil.copytree(Path('config/audience-catalogue'),root)
        c=json.loads((root/'catalogue.json').read_text())
        for entry in c['entries']:entry['review_by']='2026-10-31'
        (root/'catalogue.json').write_text(json.dumps(c))
        patcher=patch('acquisition.bootstrap.LocalAudienceSource',return_value=LocalAudienceSource(root))
        patcher.start();self.addCleanup(patcher.stop)

    def test_expiry_blocks_preparation_and_approval_but_keeps_historical_selection(self):
        self.short_source_window()
        self.waiting();receipt=self.choose()['audience_receipt'];view=self.finish();self.now=1793491200.
        current=self.w.view(view['session']['id'])
        # Fixture clocks do not advance with wall time. Test the domain's actual clock boundary.
        app=build(self.root/'conversations.sqlite',clock=lambda:self.now)
        state=app.reviews.store.view(self.w._session(view['session']['id'])['organization'],view['session']['case_id'])
        self.assertFalse(state['validation_report']['review_ready'])
        self.assertEqual(self.choose()['audience_receipt'],receipt)
        with self.assertRaises(Conflict):
            app.conversation_audiences.materialize('local-conversations',self.c,1,self.plan['id'],'other-campaign')

    def test_schema_seven_migration_failure_rolls_back_and_preserves_legacy_cutoff(self):
        path=self.root/'migration.sqlite';original=Database._apply_migration
        def skip(db,script):
            if script!=AUDIENCE_SELECTIONS:original(db,script)
        with patch.object(Database,'_apply_migration',side_effect=skip):
            # Omit the new schema validation with a seeded schema-six file instead.
            import sqlite3
            from acquisition.adapters.sqlite.database import SCHEMA, DAY_TWO, DAY_THREE, DAY_FOUR, CONVERSATIONS
            with sqlite3.connect(path) as db:
                for script in (SCHEMA,DAY_TWO):db.executescript(script)
                db.execute('CREATE TABLE legacy_task_admissions(organization TEXT,run_id TEXT,request_hash TEXT)')
                for script in (DAY_THREE,DAY_FOUR,CONVERSATIONS):db.executescript(script)
                db.execute("INSERT INTO legacy_task_admissions VALUES('o','historical','original')")
        def fail(db,script):
            if script==AUDIENCE_SELECTIONS:
                db.execute('CREATE TABLE conversation_audiences(broken TEXT)');db.execute('PRAGMA user_version=7');raise OSError('fault')
            original(db,script)
        with patch.object(Database,'_apply_migration',side_effect=fail),self.assertRaises(OSError):Database(path)
        import sqlite3
        with sqlite3.connect(path) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],6)
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='conversation_audiences'").fetchone())
        with Database(path).connect() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],10)
            self.assertEqual(tuple(db.execute('SELECT * FROM legacy_task_admissions').fetchone()),('o','historical','original'))

    def test_expiry_during_inference_prevents_more_calls_and_draft_commit(self):
        self.short_source_window()
        self.now=1793491190. # Ten seconds before the selected source expires.
        self.waiting(model=True);self.choose()
        original=self.model.copy.complete
        def expire(request):
            response=original(request)
            self.now+=20
            return response
        with patch.object(self.model.copy,'complete',side_effect=expire):
            for _ in range(5):self.w.advance_preparations()
        view=self.w.conversation(self.c)
        self.assertEqual(len(self.model.copy.requests),1)
        self.assertIsNone(view['campaigns'][0]['case_id'])
        app=self.w._conversation_app()
        with app.tasks.database.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM drafts').fetchone()[0],0)

    def test_suppression_refresh_preserves_source_and_still_needs_new_approval(self):
        self.waiting();receipt=self.choose()['audience_receipt'];view=self.finish()
        s=self.w._session(view['session']['id']);subject=view['review']['subject']['id']
        approved=self.w.action(s['id'],'approve',{'request_id':'approve','subject_id':subject,'reason':'Reviewed source and campaign.'})
        row=next(r for r in approved['audience'] if r['arm'] in {'A','B'})
        self.w.action(s['id'],'suppress',{'request_id':'suppress','business_id':row['id'],'reason':'Synthetic late suppression.'})
        refreshed=self.w.action(s['id'],'refresh',{'request_id':'refresh','subject_id':subject})
        self.assertFalse(refreshed['review']['approval_valid'])
        self.assertTrue(refreshed['review']['validation_report']['review_ready'])
        self.assertEqual(refreshed['review']['manifest']['brief']['audience_source'],receipt)
        self.assertNotEqual(refreshed['review']['subject']['id'],subject)

    def test_unavailable_catalogue_keeps_selection_prompt_recoverable(self):
        self.waiting()
        with patch('acquisition.adapters.local_audiences.LocalAudienceSource._bytes',side_effect=FileNotFoundError('missing')):
            # Transport exposes a sanitized catalogue error, not paths or raw exceptions.
            view=self.w.conversation(self.c)
            self.assertEqual(view['preparations'][0]['status'],'selecting_audience')
            self.assertIn('audience_error',view['preparations'][0])
        self.choose();self.finish()

    def test_combined_segment_proposal_has_one_exact_complete_dataset(self):
        from test_conversations import proposal
        self.model.planner.results=[proposal(segments=['inventory','contractors'],copy_mode='fixture')]
        self.w.message_conversation(self.c,'message',0,'Prepare a £600 inventory and contractor experiment with offline copy fixtures.')
        self.w.start_preparation(self.c,'prepare',1,False,False,True)
        for _ in range(4):self.w.advance_preparations()
        v=self.w.conversation(self.c);self.plan=v['current_plan']['result']
        found=v['preparations'][0]['audience_candidates'];self.entries=found['entries']
        self.assertEqual(found['resolution'],'single');self.assertEqual(self.entries[0]['dataset_id'],'working-capital')
        self.choose();view=self.finish()
        self.assertEqual(view['review']['manifest']['counts']['input'],200)
        self.assertEqual({c['segment'] for c in view['review']['manifest']['creatives']},{'inventory','contractors'})

    def test_source_scope_and_unrelated_segment_cannot_be_selected(self):
        self.waiting();app=self.w._conversation_app()
        self.assertEqual(app.audience_discovery.discover('other-organization')['entries'],[])
        entry=app.audience_discovery.discover('local-conversations','inventory-supplier-timing')['entries'][0]
        with self.assertRaises(AudienceSelectionRejected):self.choose(entry)
        self.assertIsNone(app.conversation_audiences.store.get('local-conversations',self.c,1))
        self.assertEqual(self.w.listing()['sessions'],[])

    def test_copy_revision_keeps_selected_source_and_requires_new_subject_approval(self):
        from test_copy_revisions import RevisionModel
        model=RevisionModel()
        with patch('acquisition.workspace.OpenRouter',return_value=model):
            self.waiting(model=True);receipt=self.choose()['audience_receipt'];base=self.finish()
            sid=base['session']['id'];subject=base['review']['subject']['id']
            self.w.action(sid,'approve',{'request_id':'approve','subject_id':subject,'reason':'Reviewed source and campaign.'})
            target=next(c['id'] for c in base['review']['manifest']['creatives'] if c['arm']=='B')
            self.w.request_copy_revision(sid,'revision',subject,target,'Make variant B more direct.',True)
            for _ in range(5):self.w.advance_copy_revisions()
            revised=self.w.view(sid)
            self.assertEqual(revised['copy_revisions'][-1]['status'],'complete')
            self.assertNotEqual(revised['review']['subject']['id'],subject)
            self.assertEqual(revised['review']['manifest']['brief']['audience_source'],receipt)
            self.assertEqual(revised['review']['manifest']['snapshot_id'],base['review']['manifest']['snapshot_id'])
            self.assertTrue(revised['review']['validation_report']['review_ready'])
            self.assertFalse(revised['review']['approval_valid'])

    def test_lost_post_commit_continuation_recovers_selection_and_original_consent(self):
        self.waiting()
        with patch.object(self.w.preparations,'step',side_effect=OSError('lost continuation write')):
            with self.assertRaises(OSError):self.choose()
        receipt=self.w._conversation_app().conversation_audiences.store.get('local-conversations',self.c,1)
        self.assertIsNotNone(receipt)
        self.w=Workspace(self.root,real_clock=lambda:self.now)
        self.w.preparations.recover('local-conversations')
        with patch('acquisition.adapters.local_audiences.LocalAudienceSource._bytes',side_effect=OSError('source removed')):
            view=self.finish()
        self.assertEqual(view['review']['manifest']['brief']['audience_source'],receipt)
        self.assertEqual(self.model.copy.requests,[])
        self.assertFalse(view['review']['approval_valid'])

    def test_later_selection_preserves_original_unsourced_campaign_and_approval(self):
        self.w.message_conversation(self.c,'message',0,FIXTURE_MESSAGE)
        self.w.start_preparation(self.c,'legacy-preparation',1,True,False)
        view=self.finish();sid=view['session']['id'];subject=view['review']['subject']['id']
        self.assertNotIn('audience_source',view['review']['manifest']['brief'])
        approved=self.w.action(sid,'approve',{'request_id':'approve','subject_id':subject,'reason':'Reviewed the original unsourced fixture campaign.'})
        self.assertTrue(approved['review']['approval_valid'])
        self.plan=self.w.conversation(self.c)['current_plan']['result']
        self.entries=self.w._conversation_app().conversation_audiences.candidates('local-conversations',self.c,1,self.plan['id'])['entries']
        self.choose()
        current=self.w.view(sid)
        self.assertEqual(current['review']['subject']['id'],subject)
        self.assertTrue(current['review']['approval_valid'])
        self.assertNotIn('audience_source',current['review']['manifest']['brief'])
        self.assertIsNone(self.w.conversation(self.c)['preparations'][0]['audience_selection'])
        accepted=self.w.action(sid,'handoff',{'request_id':'handoff','approval_id':approved['review']['approval']['id']})
        self.assertEqual(accepted['review']['handoff']['subject_id'],subject)

    def test_selection_rechecks_source_expiry_after_waiting_for_write_lock(self):
        from contextlib import contextmanager
        from threading import Event
        self.short_source_window();self.now=1793491190.
        self.waiting()
        app=self.w._conversation_app();service=app.conversation_audiences
        database=service.store.database;original=database.transaction;waiting=Event()
        @contextmanager
        def delayed():
            waiting.set()
            with original() as db:yield db
        # The caller timestamp and source-read check precede this held lock.
        with ThreadPoolExecutor(1) as pool:
            with original(),patch.object(database,'transaction',new=delayed):
                future=pool.submit(service.select,'local-conversations',self.c,**self.selection())
                self.assertTrue(waiting.wait(5))
                self.now+=20
            with self.assertRaises(Conflict):future.result(timeout=10)
        with database.connect() as db:
            for table in ('audiences','conversation_audiences','audience_selection_requests'):
                self.assertEqual(db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0],0)
        self.assertEqual(self.w.conversation(self.c)['preparations'][0]['status'],'selecting_audience')

    def test_reservation_rechecks_source_expiry_after_waiting_for_write_lock(self):
        self._reservation_after_lock_wait(20, 'source')

    def test_reservation_rechecks_lease_expiry_after_waiting_for_write_lock(self):
        self._reservation_after_lock_wait(181, 'lease')

    def _reservation_after_lock_wait(self, elapsed, expected):
        from contextlib import contextmanager
        from threading import Event
        from acquisition.reasoning import CallScope, ModelError
        from acquisition.runtime import LeaseLost
        self.short_source_window();self.now=1793491190.
        self.waiting(model=True);self.choose();self.w.advance_preparations()
        session=self.w._session(self.w.conversation(self.c)['campaigns'][0]['session_id'])
        app=self.w._app(session,with_model=True);scope=session['organization'];run=session['run_id']
        claim=app.tasks.claim(scope,self.now,180,run_id=run)
        self.assertEqual(claim.capability,'creative.generate_conversation.v3')
        call_scope=CallScope(scope,run,claim.task_id,claim.token)
        database=app.calls.database;original=database.transaction;waiting=Event()
        @contextmanager
        def delayed():
            waiting.set()
            with original() as db:yield db
        with ThreadPoolExecutor(1) as pool:
            with original(),patch.object(database,'transaction',new=delayed):
                future=pool.submit(app.inference.call,call_scope,'after-wait',[],[])
                self.assertTrue(waiting.wait(5));self.now+=elapsed
            with self.assertRaises(ModelError if expected=='source' else LeaseLost):future.result(timeout=10)
        self.assertEqual(self.model.copy.requests,[])
        self.assertEqual(app.calls.inspect(scope,run),[])
        state=app.tasks.inspect(scope,run)
        self.assertEqual(state['tasks'][1]['status'],'running')

    def test_sourced_admission_cannot_strip_both_provenance_and_selection_record(self):
        self.waiting();self.choose();view=self.finish()
        session=self.w._session(view['session']['id']);app=self.w._app(session)
        draft=app.drafts.get(session['organization'],view['review']['subject']['draft_id'])
        brief=copy.deepcopy(draft.manifest['brief']);brief.pop('audience_source')
        from acquisition.reviews import creatives_from
        snapshot=app.audiences.get(session['organization'],draft.manifest['snapshot_id'])
        stripped=build_draft(snapshot,brief_from(brief),creatives_from(draft))
        with app.tasks.database.transaction() as db:
            db.execute('DELETE FROM conversation_audiences WHERE organization=? AND conversation_id=? AND revision=?',
                       ('local-conversations',self.c,1))
        with self.assertRaises(Conflict):app.drafts.put(session['organization'],'stripped-admission',stripped)

    def test_reservation_rejects_nonfinite_clock_after_waiting_for_write_lock(self):
        self._reservation_after_lock_wait(float('inf'), 'lease')

    def test_selection_expiry_during_validation_rolls_back_all_writes(self):
        self._selection_expiry_during_work('validation')

    def test_selection_expiry_during_serialization_rolls_back_all_writes(self):
        self._selection_expiry_during_work('serialization')

    def test_selection_expiry_during_receipt_write_rolls_back_all_writes(self):
        self._selection_expiry_during_work('receipt')

    def _selection_expiry_during_work(self, phase):
        from contextlib import ExitStack, contextmanager
        from acquisition.adapters.sqlite import audience_selections
        self.short_source_window();self.now=1793491190.
        self.waiting();app=self.w._conversation_app();service=app.conversation_audiences
        original_validation=audience_selections.validate_dataset
        original_serialization=audience_selections.canonical
        original_transaction=service.store.database.transaction
        crossed=[]
        def expire():
            if not crossed:
                crossed.append(phase);self.now+=20
            return 0
        def validate(*args):
            result=original_validation(*args);expire();return result
        def serialize(value):
            result=original_serialization(value)
            if isinstance(value,dict) and 'records' in value:expire()
            return result
        @contextmanager
        def receipt_write():
            with original_transaction() as db:
                db.create_function('expire_selection_source',0,expire)
                db.execute('''CREATE TEMP TRIGGER expire_receipt AFTER INSERT ON audience_selection_requests
                    BEGIN SELECT expire_selection_source(); END''')
                yield db
        with ExitStack() as stack:
            if phase=='validation':stack.enter_context(patch.object(audience_selections,'validate_dataset',new=validate))
            elif phase=='serialization':stack.enter_context(patch.object(audience_selections,'canonical',new=serialize))
            else:stack.enter_context(patch.object(service.store.database,'transaction',new=receipt_write))
            with self.assertRaises(Conflict):service.select('local-conversations',self.c,**self.selection())
        self.assertEqual(crossed,[phase])
        with service.store.database.connect() as db:
            for table in ('audiences','conversation_audiences','audience_selection_requests'):
                self.assertEqual(db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0],0,table)
        self.assertEqual(self.w.conversation(self.c)['preparations'][0]['status'],'selecting_audience')

    def test_reservation_source_expiry_during_validation_makes_no_call(self):
        self._reservation_during_source_validation(20, 'source')

    def test_reservation_lease_expiry_during_validation_makes_no_call(self):
        self._reservation_during_source_validation(181, 'lease')

    def test_reservation_finite_clock_is_rechecked_after_validation(self):
        self._reservation_during_source_validation(float('inf'), 'lease')

    def test_valid_source_and_lease_still_allow_one_provider_call(self):
        self._reservation_during_source_validation(0, None)

    def _reservation_during_source_validation(self, elapsed, expected, phase="validation"):
        from contextlib import ExitStack, contextmanager
        from acquisition.adapters.sqlite import selected_audience
        from acquisition.reasoning import CallScope, ModelError
        from acquisition.runtime import LeaseLost
        # Keep the product pack fresh in every case. For the lease-only case,
        # keep the audience window open so expiry of the lease is the sole cause.
        if expected=='source':self.short_source_window()
        self.now=1793491190.
        self.waiting(model=True);self.choose();self.w.advance_preparations()
        session=self.w._session(self.w.conversation(self.c)['campaigns'][0]['session_id'])
        app=self.w._app(session,with_model=True);scope=session['organization'];run=session['run_id']
        claim=app.tasks.claim(scope,self.now,180,run_id=run)
        self.assertEqual(claim.capability,'creative.generate_conversation.v3')
        call_scope=CallScope(scope,run,claim.task_id,claim.token)
        original=selected_audience.validate_dataset;validated=[]
        def advance(*args):
            result=original(*args);validated.append(True)
            if phase=="validation":self.now+=elapsed
            return result
        original_transaction=app.calls.database.transaction
        @contextmanager
        def reservation_write():
            with original_transaction() as db:
                def expire():
                    self.now+=elapsed
                    return 0
                db.create_function("expire_reservation",0,expire)
                db.execute("CREATE TEMP TRIGGER expire_model_reservation AFTER INSERT ON model_calls BEGIN SELECT expire_reservation(); END")
                yield db
        def call():
            return app.inference.call(call_scope,'during-validation',[],[{'function':{'name':'read_editorial_context'}}])
        with ExitStack() as stack:
            stack.enter_context(patch.object(selected_audience,'validate_dataset',new=advance))
            if phase=="reservation":stack.enter_context(patch.object(app.calls.database,'transaction',new=reservation_write))
            if expected:
                with self.assertRaises(ModelError if expected=='source' else LeaseLost):call()
            else:
                self.assertEqual(call()['usage']['total_tokens'],300)
        self.assertEqual(validated,[True])
        self.assertEqual(len(self.model.copy.requests),0 if expected else 1)
        self.assertEqual(len(app.calls.inspect(scope,run)),0 if expected else 1)
        self.assertEqual(app.tasks.inspect(scope,run)['tasks'][1]['status'],'running')

    def test_revision_reservation_source_expiry_during_validation_makes_no_call(self):
        from acquisition.adapters.sqlite import selected_audience
        from acquisition.reasoning import CallScope, Inference, ModelError
        self.short_source_window();self.now=1793491190.
        self.waiting(model=True);self.choose();base=self.finish()
        sid=base['session']['id'];subject=base['review']['subject']['id']
        target=next(c['id'] for c in base['review']['manifest']['creatives'] if c['arm']=='B')
        self.w.request_copy_revision(sid,'revision-deadline',subject,target,'Make variant B more direct.',True)
        session=self.w._session(sid);app=self.w._app(session,with_model=True);scope=session['organization']
        receipt=app.reviews.store.revision_request(scope,'revision-deadline')
        run=app.revisions.reconcile(scope,receipt)
        claim=app.tasks.claim(scope,self.now,180,run_id=run)
        self.assertEqual(claim.capability,'creative.revise_copy.v3')
        inference=Inference(self.model,app.calls,app.revisions.config,app.clock)
        original=selected_audience.validate_dataset;validated=[]
        before=len(self.model.copy.requests)
        def advance(*args):
            result=original(*args);validated.append(True);self.now+=20;return result
        with patch.object(selected_audience,'validate_dataset',new=advance):
            with self.assertRaises(ModelError):
                inference.call(CallScope(scope,run,claim.task_id,claim.token),'revision-after-validation',[],[{'function':{'name':'read_editorial_context'}}])
        self.assertEqual(validated,[True])
        self.assertEqual(len(self.model.copy.requests),before)
        self.assertEqual(app.calls.inspect(scope,run),[])

    def test_reservation_source_expiry_during_insert_rolls_back_before_dispatch(self):
        self._reservation_during_source_validation(20, 'source', phase='reservation')

    def test_reservation_lease_expiry_during_insert_rolls_back_before_dispatch(self):
        self._reservation_during_source_validation(181, 'lease', phase='reservation')
