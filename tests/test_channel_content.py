"""Grounded recipient rendering, exact inference receipts and atomic lifecycle boundaries."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import datetime, timezone
from html.parser import HTMLParser
import copy
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from threading import Barrier
import unittest
from unittest.mock import patch

from acquisition.bootstrap import build_contact_directory, build_recipient_contexts, build_channel_preparation
from acquisition.adapters.channel_fixtures import OfflineChannelModel
from acquisition.adapters.recipient_fixtures import RecordedRecipientContextSource
from acquisition.adapters.sqlite.admission_guard import binding
from acquisition.adapters.sqlite.channel_content import SqliteChannelTasks
from acquisition.adapters.sqlite.database import Database
from acquisition.adapters.sqlite.creative import read_context
from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.creative import (ChannelContentAgent, validate_channel_context, validate_rendered_channel,
                                  render_channel_rows, proposal_rows, RecipientContextRequest)
from acquisition.reasoning import CallScope, ModelError, source_manifest, validate_assets
from acquisition.runtime import Outcome, LeaseLost, TaskSpec


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026,11,14,tzinfo=timezone.utc).timestamp()


class RecordingModel(OfflineChannelModel):
    def __init__(self, transform=None): self.requests, self.transform = [], transform
    def complete(self, request):
        self.requests.append(copy.deepcopy(request))
        response = super().complete(request)
        return self.transform(request,response) if self.transform else response


class ChannelContentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'app.sqlite'; self.now = NOW

    def seed(self, profile='fielddesk', channel='email', count=3):
        contacts = build_contact_directory(self.path,'one',profile,lambda:self.now)
        recipient = build_recipient_contexts(self.path,'one',profile,lambda:self.now)
        ids = []
        for connection in ('a','b'):
            evidence = contacts.prepare('one',profile+channel+connection,profile+'-crm-'+connection,1,channel)
            for index, person in enumerate(evidence['report']['eligible']):
                key = profile+channel+connection+str(index)
                recipient.prepare('one',key,evidence['assessment_id'],person,'reviewed-context-a',1)
                ids.append(key)
                if len(ids)==count: return tuple(ids), contacts

    def app(self, profile='fielddesk', model=None, read_only=False, *, stage_ownership=False):
        return build_channel_preparation(self.path,'one',profile,lambda:self.now,gateway=model,read_only=read_only,
                                         stage_ownership=stage_ownership)

    def result(self, app, recipients, key='content', channel='email', profile='fielddesk', **kwargs):
        return app.prepare('one',key,profile,recipients,channel,**kwargs)

    def counts(self, app):
        with app.store.database.connect() as db:
            return {table:db.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in (
                'channel_artifacts','channel_preparations','creative_contexts','runs','tasks','events','model_calls',
                'review_decisions','simulated_agency_jobs','learning_cohorts')}

    def test_two_profiles_both_channels_validate_every_recipient_at_maximum_batch_size(self):
        for profile in ('fielddesk','iwoca'):
            for channel in ('email','human_call'):
                ids,_ = self.seed(profile,channel,6); model = RecordingModel(); app = self.app(profile,model)
                view = self.result(app,ids,profile+channel,channel,profile)
                self.assertEqual(view['run_status'],'succeeded',app.tasks.inspect('one',view['run_id']))
                self.assertTrue(view['ready_for_review'])
                rows = view['saved']['rendered']; self.assertEqual(len(rows),6)
                self.assertEqual(len({r['id'] for r in rows}),6)
                self.assertEqual(len({r['contact_id'] for r in rows}),6)
                frozen = app.store.load('one',view['context_id']); pack = frozen['product_facts']
                for row in rows:
                    recipient = next(r for r in frozen['recipients'] if r['context_id']==row['recipient_context_id'])
                    self.assertEqual(row['contact_id'],recipient['contact_id'])
                    fact = next(f for f in pack['facts'] if f['id']==row['product_fact_id'])
                    if channel=='email':
                        email = row['email']; self.assertEqual(email['to'],recipient['email'])
                        for required in (fact['copy'],fact['qualification'],pack['required_qualification'],pack['cta']):
                            self.assertIn(required,email['text'])
                        parser = HTMLParser(); parser.feed(email['html']); parser.close()
                        self.assertTrue(email['unsubscribe_url'].startswith('https://'+profile+'.example.invalid/'))
                        self.assertIn(email['unsubscribe_url'],email['text'])
                        self.assertIn('reply@',email['reply_to'])
                    else:
                        self.assertEqual(row['call']['contact'],recipient['phone'])
                        for key in ('introduction','relevance','discovery','approved_claims','objections','next_steps','do_not_contact'):
                            self.assertTrue(row['call'][key])
                        self.assertTrue(row['call']['human_only'])
                    self.assertEqual(row['approval'],'not_granted')
                    self.assertEqual(row['outcome_support'],'none')
                    for personal in row['recipient_facts']:
                        self.assertIn(personal,recipient['facts'])
                self.assertEqual(len(model.requests),3)
                screen = model.requests[-1]; data = json.loads(screen['messages'][-1]['content'])
                self.assertEqual(len(data['rendered']),6)
                self.assertFalse(any(m['role']=='tool' for m in screen['messages']))
                self.assertTrue(all(len(canonical(r).encode())<=32000 for r in model.requests))
        for table in ('review_decisions','simulated_agency_jobs','learning_cohorts'):
            self.assertEqual(self.counts(app)[table],0)

    def test_replay_and_fresh_process_keep_frozen_assets_and_make_no_more_calls(self):
        ids,_ = self.seed(); model = RecordingModel(); app = self.app(model=model)
        first = self.result(app,ids); before = self.counts(app)
        with patch.object(app.inference.gateway,'complete',side_effect=AssertionError('no redispatch')):
            replay = self.result(app,ids)
        self.assertEqual(replay['saved'],first['saved']); self.assertEqual(self.counts(app),before)
        code = '''
import json,sys
from unittest.mock import patch
from acquisition.bootstrap import build_channel_preparation
with patch('acquisition.adapters.channel_fixtures.OfflineChannelModel.complete',side_effect=AssertionError('no call')):
 a=build_channel_preparation(sys.argv[1],'one','fielddesk',lambda:1794614400.)
 print(json.dumps(a.prepare('one','content','fielddesk',sys.argv[2:],'email')))
'''
        process = subprocess.run([sys.executable,'-c',code,str(self.path),*ids],cwd=ROOT,text=True,capture_output=True)
        self.assertEqual(process.returncode,0,process.stderr)
        self.assertEqual(json.loads(process.stdout)['saved'],first['saved'])
        self.assertEqual(self.counts(app),before)
        for changes in ({'style':'practical'},{'recipient_requests':ids[:1]},{'channel':'human_call'}):
            with self.assertRaises(Conflict):
                app.start('one','content','fielddesk',changes.get('recipient_requests',ids),changes.get('channel','email'),
                          style=changes.get('style','explore'))

    def test_paused_channel_admission_rolls_back_at_every_write_and_replays_across_restart(self):
        ids,_ = self.seed(count=1)
        app = self.app(model=RecordingModel(),stage_ownership=True)
        db = app.store.database
        tables = ('creative_contexts','admission_requests','runs','tasks','events','execution_admissions','channel_preparations')

        def snapshot():
            with db.connect() as connection:
                return {table:connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in tables}

        before = snapshot()
        for table in tables:
            for timing in ('BEFORE','AFTER'):
                with self.subTest(table=table,timing=timing):
                    with db.transaction() as connection:
                        connection.execute(f"CREATE TRIGGER interrupt_admission {timing} INSERT ON {table} "
                                           "BEGIN SELECT RAISE(ABORT,'interrupted admission'); END")
                    try:
                        with self.assertRaisesRegex(sqlite3.IntegrityError,'interrupted admission'):
                            app.start('one','paused','fielddesk',ids,'email')
                        self.assertEqual(snapshot(),before)
                    finally:
                        with db.transaction() as connection:
                            connection.execute('DROP TRIGGER interrupt_admission')

        barrier = Barrier(2)
        def start():
            barrier.wait(timeout=10)
            return app.start('one','paused','fielddesk',ids,'email')
        with ThreadPoolExecutor(max_workers=2) as pool:
            first,second = (pool.submit(start) for _ in range(2))
            run = first.result(timeout=30)
            self.assertEqual(second.result(timeout=30),run)
        after = snapshot()
        self.assertEqual(after,{table:count+(2 if table=='events' else 1) for table,count in before.items()})
        with db.connect() as connection:
            intent = binding(connection,'one',run)
            self.assertEqual(intent.ownership.kind,'standalone')
            admitted = connection.execute('SELECT receipt FROM execution_admissions WHERE run_id=?',(run,)).fetchone()[0]
        self.assertEqual(app.tasks.inspect('one',run)['admission']['binding_valid'],True)
        code = '''
import json, sys
from acquisition.bootstrap import build_channel_preparation
app = build_channel_preparation(sys.argv[1],'one','fielddesk',lambda:1794614400.)
view = app.prepare('one','paused','fielddesk',sys.argv[2:],'email')
print(json.dumps(view))
'''
        process = subprocess.run([sys.executable,'-c',code,str(self.path),*ids],cwd=ROOT,text=True,capture_output=True)
        self.assertEqual(process.returncode,0,process.stderr)
        view = json.loads(process.stdout)
        self.assertEqual((view['run_id'],view['run_status'],view['model_calls']),(run,'queued',[]))
        with self.assertRaises(Conflict):
            app.start('one','paused','fielddesk',ids,'email',style='practical')
        with db.connect() as connection:
            self.assertEqual(connection.execute('SELECT receipt FROM execution_admissions WHERE run_id=?',(run,)).fetchone()[0],admitted)
            self.assertIsNone(connection.execute('SELECT 1 FROM admission_store_policy').fetchone())
            self.assertIsNone(connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='fixture_execution_grants'").fetchone())
        self.assertEqual(snapshot(),after)
        self.assertEqual(app.inference.gateway.requests,[])

        # A generic task writer cannot use the paused task's scoped context to
        # reach the provider through a different runtime request or lease.
        copied = {k:v for k,v in intent.tasks[0].inputs.items()
                  if k not in {'execution_admission_id','run_request_id'}}
        spec = TaskSpec(intent.tasks[0].capability,copied,max_attempts=3)
        with self.assertRaises(Conflict):
            app.tasks.create('one','channel:paused',[spec],self.now)
        clone = app.tasks.create('one','new-native-run',[spec],self.now)
        claim = app.tasks.claim('one',self.now,10,run_id=clone)
        with self.assertRaisesRegex(Conflict,'original preparation'):
            app.inference.journal.reserve(CallScope('one',clone,claim.task_id,claim.token),'probe',digest('probe'),1,self.now)
        self.assertEqual(app.inference.gateway.requests,[])
        self.assertEqual(app.inference.journal.inspect('one',clone),[])

    def test_channel_binding_cannot_fall_back_after_coordinated_record_loss(self):
        ids,_ = self.seed(count=1)
        app = self.app(model=RecordingModel(),stage_ownership=True)
        run = app.start('one','missing-binding','fielddesk',ids,'email')
        view = app.inspect('one','missing-binding')
        with app.store.database.transaction() as db:
            intent = binding(db,'one',run)
            old = intent.tasks[0]
            inputs = {k:v for k,v in old.inputs.items() if k not in {'execution_admission_id','run_request_id'}}
            db.execute('DROP TRIGGER execution_admissions_no_delete')
            db.execute('DROP TRIGGER admission_requests_no_delete')
            db.execute('DELETE FROM execution_admissions WHERE organization=? AND run_id=?',('one',run))
            db.execute('DELETE FROM admission_requests WHERE organization=? AND request_id=?',('one',intent.request_id))
            db.execute('UPDATE tasks SET inputs=? WHERE run_id=?',(canonical(inputs),run))
            db.execute('UPDATE runs SET request_hash=? WHERE organization=? AND id=?',
                       (digest([asdict(TaskSpec(old.capability,inputs,max_attempts=old.max_attempts))]),'one',run))
        restarted = self.app(model=RecordingModel())
        self.assertEqual(restarted.ownership('one',run)['status'],'unresolved')
        self.assertFalse(restarted.inspect('one','missing-binding')['currently_applicable'])
        with self.assertRaisesRegex(Conflict,'missing its committed admission'):
            restarted.store.load('one',view['context_id'],run_id=run)
        with self.assertRaisesRegex(Conflict,'missing its committed admission'):
            restarted.start('one','missing-binding','fielddesk',ids,'email')
        self.assertIsNone(restarted.tasks.claim('one',self.now,10,run_id=run))
        self.assertEqual(restarted.inference.gateway.requests,[])

    def test_proven_legacy_reconciliation_is_atomic_and_preserves_unknown_call_after_restart(self):
        ids,_ = self.seed(count=1)
        app = self.app(model=RecordingModel())
        run = app.start('one','legacy','fielddesk',ids,'email')
        queued = app.ownership('one',run)
        with patch.object(app.inference.gateway,'complete',side_effect=ModelError('provider_timeout')):
            app.worker.drain('one',run_id=run)
        before = app.inspect('one','legacy')
        self.assertEqual([call['status'] for call in before['model_calls']],['unknown'])
        report = app.ownership('one',run)
        self.assertEqual(report['status'],'legacy_proven')
        self.assertEqual(report['ownership']['kind'],'standalone')
        self.assertNotEqual(report['fingerprint'],queued['fingerprint'])
        with self.assertRaisesRegex(Conflict,'exact proven legacy'):
            app.reconcile_ownership('one',run,queued['fingerprint'])
        with self.assertRaises(NotFound):
            app.ownership('other',run)
        with app.store.database.transaction() as db:
            db.execute("""CREATE TRIGGER interrupted_ownership BEFORE INSERT ON events
                WHEN NEW.kind='channel_ownership_reconciled'
                BEGIN SELECT RAISE(ABORT,'interrupted ownership'); END""")
        with self.assertRaisesRegex(sqlite3.IntegrityError,'interrupted ownership'):
            app.reconcile_ownership('one',run,report['fingerprint'])
        self.assertEqual(app.ownership('one',run),report)
        with app.store.database.transaction() as db:
            db.execute('DROP TRIGGER interrupted_ownership')
        code = """
import json,sys
from acquisition.bootstrap import build_channel_preparation
app=build_channel_preparation(sys.argv[1],'one','fielddesk',lambda:1794614400.)
print(json.dumps(app.reconcile_ownership('one',sys.argv[2],sys.argv[3])))
"""
        retry = subprocess.run([sys.executable,'-c',code,str(self.path),run,report['fingerprint']],
                               cwd=ROOT,text=True,capture_output=True,timeout=20)
        self.assertEqual(retry.returncode,0,retry.stderr)
        receipt = json.loads(retry.stdout)
        next_app = self.app(model=RecordingModel())
        self.assertEqual(next_app.ownership('one',run),report | {'status':'legacy_reconciled'})
        self.assertEqual(next_app.reconcile_ownership('one',run,report['fingerprint']),receipt)
        self.assertEqual(next_app.prepare('one','legacy','fielddesk',ids,'email'),before)
        self.assertEqual(next_app.inference.gateway.requests,[])
        with next_app.store.database.connect() as db:
            events = db.execute("SELECT data FROM events WHERE run_id=? AND kind='channel_ownership_reconciled'",(run,)).fetchall()
            self.assertEqual([json.loads(row[0]) for row in events],[receipt])

    def test_missing_last_recipient_unsafe_html_familiarity_and_foreign_fact_cannot_be_ready(self):
        ids,_ = self.seed()
        for attack in ('omission','html','familiarity','foreign_fact','foreign_recipient'):
            def mutate(request,response):
                if request['tools'][0]['function']['name']=='submit_contextual_email':
                    args = json.loads(response['message']['tool_calls'][0]['function']['arguments'])
                    if attack=='omission': args['rows'].pop()
                    elif attack in ('html','familiarity'): args['rows'][-1]['frame_key'] = '<img onerror=send()>' if attack=='html' else 'Following our conversation'
                    elif attack=='foreign_fact': args['rows'][-1]['recipient_fact_ids']=['score_or_unknown_fact']
                    else: args['rows'][-1]['recipient_context_id']='other-recipient'
                    response['message']['tool_calls'][0]['function']['arguments']=json.dumps(args)
                return response
            model = RecordingModel(mutate); app = self.app(model=model)
            view = self.result(app,ids,attack)
            self.assertEqual(view['run_status'],'failed',attack)
            self.assertIsNone(view['saved']); self.assertFalse(view['ready_for_review'])
            self.assertEqual(len(model.requests),3)  # Read plus two bounded, known-invalid proposals.

    def test_independent_screen_covers_all_rows_repairs_once_and_never_approves(self):
        ids,_ = self.seed(); rejected = [False]
        def reject(request,response):
            if request['tools'][0]['function']['name']=='record_channel_screen' and not rejected[0]:
                args = json.loads(response['message']['tool_calls'][0]['function']['arguments'])
                args['rows'][-1].update(verdict='reject',reason='misleading_familiarity'); rejected[0]=True
                response['message']['tool_calls'][0]['function']['arguments']=json.dumps(args)
            return response
        model = RecordingModel(reject); app = self.app(model=model); view = self.result(app,ids)
        self.assertEqual(len(model.requests),5); self.assertTrue(view['ready_for_review'])
        self.assertEqual(view['saved']['screen_status'],'passed_advisory_not_approval')
        self.assertEqual(view['saved']['approval'],'not_granted')
        def sampled(request,response):
            if request['tools'][0]['function']['name']=='record_channel_screen':
                args=json.loads(response['message']['tool_calls'][0]['function']['arguments']); args['rows'].pop()
                response['message']['tool_calls'][0]['function']['arguments']=json.dumps(args)
            return response
        model=RecordingModel(sampled); view=self.result(self.app(model=model),ids,'sampled')
        self.assertFalse(view['ready_for_review']); self.assertEqual(view['run_status'],'failed')
        self.assertEqual(len(model.requests),5)

    def test_unknown_inference_is_reserved_and_not_repeated_after_restart_or_work_retry(self):
        ids,_=self.seed(); model=RecordingModel()
        def unknown(request):
            model.requests.append(request); raise RuntimeError('SECRET_KEY_DO_NOT_EXPORT')
        model.complete=unknown; app=self.app(model=model); view=self.result(app,ids)
        self.assertEqual(len(model.requests),1)
        self.assertEqual(view['model_calls'][0]['status'],'unknown')
        self.assertNotIn('SECRET_KEY',canonical(view))
        restarted=self.app(model=RecordingModel()); again=self.result(restarted,ids)
        self.assertEqual(again['run_status'],'failed'); self.assertFalse(again['ready_for_review'])
        self.assertEqual(restarted.inference.gateway.requests,[])

    def test_worker_loss_reuses_recorded_calls_then_commits_one_artifact(self):
        ids,_=self.seed(); model=RecordingModel(); app=self.app(model=model)
        run=app.start('one','content','fielddesk',ids,'email')
        claim=app.tasks.claim('one',self.now,1,run_id=run)
        context=app.store.load('one',claim.inputs['context_id'])
        ChannelContentAgent(app.inference).generate(CallScope('one',run,claim.task_id,claim.token),claim.inputs['context_id'],
            context,datetime.fromtimestamp(self.now,timezone.utc).date())
        self.assertEqual(len(model.requests),3)
        self.now+=2
        restarted=self.app(model=RecordingModel()); restarted.worker.drain('one',run_id=run)
        self.assertEqual(restarted.inference.gateway.requests,[])
        self.assertTrue(restarted.inspect('one','content')['ready_for_review'])
        self.assertEqual(self.counts(restarted)['channel_artifacts'],1)

    def test_rendering_tamper_missing_qualification_recipient_swap_and_html_are_rejected_at_commit(self):
        ids,_=self.seed(); app=self.app()
        run=app.start('one','content','fielddesk',ids,'email'); claim=app.tasks.claim('one',self.now,180,run_id=run)
        context=app.store.load('one',claim.inputs['context_id'])
        result=ChannelContentAgent(app.inference).generate(CallScope('one',run,claim.task_id,claim.token),claim.inputs['context_id'],
            context,datetime.fromtimestamp(self.now,timezone.utc).date())
        for attack in ('qualification','target','html','claims'):
            altered=copy.deepcopy(result)
            row=altered['rendered'][-1]
            if attack=='qualification': row['email']['text']=row['email']['text'].replace(context['product_facts']['required_qualification'],'')
            elif attack=='target': row['email']['to']=altered['rendered'][0]['email']['to']
            elif attack=='html': row['email']['html']='<script>send()</script>'
            else: row['recipient_facts']=[]
            before=self.counts(app)
            try:
                with self.assertRaises(Conflict): app.tasks.settle(claim,Outcome('succeeded',altered),self.now)
            except ValueError as exc:
                self.fail(f'Tampered content must be rejected at the commit boundary: {exc}')
            self.assertEqual(self.counts(app),before)
        app.tasks.settle(claim,Outcome('succeeded',result),self.now)
        self.assertTrue(app.inspect('one','content')['ready_for_review'])
        # Literal authored text is escaped independently of the model's allowlisted frame choice.
        authored=copy.deepcopy(context)
        key=result['proposals'][0]['frame_key']
        authored['guidance']['frames'][key]['opening']='<img src=x onerror="send()"> & literal'
        safe=render_channel_rows(authored,claim.inputs['context_id'],result['proposals'])
        html=next(r['email']['html'] for r in safe if '&lt;img' in r['email']['html'])
        self.assertNotIn('<img',html)
        self.assertIn('&quot;send()&quot;',html)
        self.assertIn('&amp; literal',html)

    def test_rehashed_forged_screen_without_recorded_calls_cannot_publish(self):
        ids,_=self.seed(); app=self.app(); run=app.start('one','content','fielddesk',ids,'email')
        claim=app.tasks.claim('one',self.now,180,run_id=run); context=app.store.load('one',claim.inputs['context_id'])
        proposals=[{'recipient_context_id':r['context_id'],'frame_key':'explore','product_fact_id':context['product_facts']['facts'][0]['id'],
                    'recipient_fact_ids':[]} for r in context['recipients']]
        rendered=render_channel_rows(context,claim.inputs['context_id'],proposals)
        fake={'proposals':proposals,'rendered':rendered,'attempt':0,'screen':{'candidate_hash':digest(rendered),
            'rows':[{'recipient_context_id':r['recipient_context_id'],'verdict':'pass','reason':'none'} for r in rendered]}}
        with self.assertRaisesRegex(Conflict,'receipts'): app.tasks.settle(claim,Outcome('succeeded',fake),self.now)
        self.assertEqual(self.counts(app)['channel_artifacts'],0)

    def test_cancel_or_source_change_during_model_work_prevents_artifact_publication(self):
        ids,contacts=self.seed()
        for effect in ('cancel','objection'):
            holder={}
            def change(request,response):
                if request['tools'][0]['function']['name']=='submit_contextual_email':
                    if effect=='cancel': holder['app'].tasks.cancel('one',holder['run'],self.now)
                    else:
                        person=contacts.source.read('one','fielddesk-crm-a',1).contacts[-1].ref.id
                        contacts.object('one','stop',person,'email','acquisition','stop')
                return response
            model=RecordingModel(change); app=self.app(model=model); run=app.start('one',effect,'fielddesk',ids,'email')
            holder.update(app=app,run=run); app.worker.drain('one',run_id=run)
            self.assertIsNone(app.inspect('one',effect)['saved'])

    def test_postwrite_expiry_rolls_back_artifact_task_result_and_event(self):
        ids,contacts=self.seed(); app=self.app()
        person=contacts.source.read('one','fielddesk-crm-a',1).contacts[-1].ref.id
        original=app.tasks.settle_in_transaction
        for fault in ('lease','objection'):
            run=app.start('one',fault,'fielddesk',ids,'email')
            def inject(db,*args):
                row=original(db,*args)
                if fault=='lease': self.now+=181
                else:
                    value={'organization':'one','channel':'all','purpose':'all','contact_id':person,
                           'recorded_at':self.now,'reason':'stop'}
                    db.execute('INSERT INTO contact_objections VALUES(?,?,?)',('one','objection_'+digest(value),canonical(value)))
                return row
            with patch.object(app.tasks,'settle_in_transaction',side_effect=inject): app.worker.drain('one',run_id=run)
            self.assertEqual(self.counts(app)['channel_artifacts'],0)
            view=app.tasks.inspect('one',run)
            self.assertFalse(any(e['kind']=='task_succeeded' for e in view['events']))
            self.assertNotEqual(view['tasks'][0]['status'],'succeeded')
            with app.store.database.connect() as db:
                self.assertEqual(db.execute('SELECT count(*) FROM contact_objections').fetchone()[0],0)

    def test_rewrite_gets_new_identity_without_approval_outcomes_and_stale_replay_stays_historical(self):
        ids,contacts=self.seed(); app=self.app(); first=self.result(app,ids)
        second=self.result(app,ids,'rewrite',parent_id=first['artifact_id'],style='practical')
        self.assertNotEqual(first['artifact_id'],second['artifact_id'])
        self.assertTrue(set(r['id'] for r in first['saved']['rendered']).isdisjoint(r['id'] for r in second['saved']['rendered']))
        self.assertEqual(second['saved']['parent_id'],first['artifact_id'])
        self.assertEqual(second['saved']['outcome_support'],'none')
        staged = self.app(stage_ownership=True)
        third = staged.start('one','paused-rewrite','fielddesk',ids,'email',style='practical',parent_id=second['artifact_id'])
        with staged.store.database.connect() as db:
            ownership = binding(db,'one',third)
            self.assertEqual(ownership.parent_run_id,second['run_id'])
            self.assertEqual(ownership.ownership.scope_id,
                'channel_operation_'+digest({'organization':'one','request_id':'content'}))
        person=contacts.source.read('one','fielddesk-crm-a',1).contacts[0].ref.id
        contacts.object('one','stop',person,'all','all','stop')
        stale=self.result(app,ids)
        self.assertEqual(stale['saved'],first['saved']); self.assertFalse(stale['ready_for_review'])
        with self.assertRaises(Conflict): app.start('one','new','fielddesk',ids,'email')

    def test_frozen_assets_survive_guidance_changes_and_cannot_install_tools_or_downgrade_grounding(self):
        ids,_=self.seed(); app=self.app()
        snapshot=app.store.memory.examples_snapshot
        with patch.object(app.store.memory,'preferences',side_effect=AssertionError('History is not current style guidance')), \
             patch.object(app.store.memory,'examples_snapshot',wraps=snapshot) as selected:
            run=app.start('one','content','fielddesk',ids,'email')
        selected.assert_called_once_with('one',('installations','maintenance'))
        context_id=app.inspect('one','content')['context_id']
        original=app.store.load('one',context_id)
        app.store.catalogue['skills'][0]['guidance'].append('New current guidance.')
        self.assertEqual(app.store.load('one',context_id),original)
        app.worker.drain('one',run_id=run); self.assertTrue(app.inspect('one','content')['ready_for_review'])
        new=self.result(app,ids,'new-guidance'); self.assertNotEqual(new['context_id'],context_id)
        bad=self.app(); bad.store.catalogue['skills'][0]['tool_ids'].append('send_email/v1')
        before=self.counts(app)
        with self.assertRaises(ValueError): bad.start('one','bad','fielddesk',ids,'email')
        self.assertEqual(self.counts(app),before)
        altered=copy.deepcopy(original); altered['schema']='creative-context/v3'
        with self.assertRaises(Conflict): validate_channel_context(altered,'one',datetime.fromtimestamp(self.now,timezone.utc).date())
        altered=copy.deepcopy(original); assets=altered['agent_assets']
        assets['sources']=[source_manifest('one','recipients','reviewer_preference',altered['recipients'],'v1',
            'Coordinated substitution.','Frozen.') if s['key']=='recipients' else s for s in assets['sources']]
        assets['skills'][0]['required_source_kinds'].remove('recipient_evidence')
        assets['id']='assets_'+digest({k:v for k,v in assets.items() if k!='id'})
        validate_assets(assets)
        with self.assertRaises(Conflict): validate_channel_context(altered,'one',datetime.fromtimestamp(self.now,timezone.utc).date())

    def test_scope_readonly_and_paused_guards_preserve_existing_execution_boundaries(self):
        ids,_=self.seed(); app=self.app(); first=self.result(app,ids); before=self.counts(app)
        with self.assertRaises(NotFound): app.inspect('other','content')
        other=build_channel_preparation(self.path,'other','fielddesk',lambda:self.now)
        with self.assertRaises(NotFound): other.start('other','foreign','fielddesk',ids,'email')
        readonly=self.app(read_only=True)
        self.assertEqual(readonly.inspect('one','content')['saved'],first['saved'])
        with self.assertRaises(Conflict): readonly.start('one','readonly','fielddesk',ids,'email')
        with self.assertRaises(Conflict): readonly.worker.drain('one',run_id=first['run_id'])
        Database(self.path,verified_admissions=True,clock=lambda:self.now)
        with self.assertRaises(Conflict): app.start('one','paused','fielddesk',ids,'email')
        with self.assertRaises(Conflict):
            self.app(stage_ownership=True).start('one','staged','fielddesk',ids,'email')
        self.assertEqual(self.counts(app),before)

    def test_sparse_reviewed_context_stays_honest_without_invented_recipient_claims(self):
        contacts=build_contact_directory(self.path,'one','fielddesk',lambda:self.now)
        evidence=contacts.prepare('one','source','fielddesk-crm-a',1,'email')
        recipient=build_recipient_contexts(self.path,'one','fielddesk',lambda:self.now)
        person=evidence['report']['eligible'][0]
        request=RecipientContextRequest(evidence['assessment_id'],person,'reviewed-context-a',1,('contact_role','prior_interaction'))
        target=recipient.store.capture('one',request).target
        source=recipient.source.read('one','reviewed-context-a',1,target)
        source=replace(source,declared_facts=0,facts=())
        recipient.source=recipient.store.source=RecordedRecipientContextSource('one',(source,))
        receipt=recipient.prepare('one','sparse',evidence['assessment_id'],person,'reviewed-context-a',1)
        self.assertEqual(receipt['context']['status'],'insufficient_context')
        app=self.app(); app.store.recipients=recipient.store
        view=self.result(app,('sparse',))
        self.assertTrue(view['ready_for_review'])
        row=view['saved']['rendered'][0]
        self.assertEqual(row['recipient_facts'],[])
        self.assertIn('Would you like',row['email']['text'])
        self.assertNotIn('Your recorded role',row['email']['text'])
        self.assertNotIn('The reviewed record notes',row['email']['text'])
        self.assertNotIn('score',row['email']['text'].lower())

    def test_expired_frozen_evidence_blocks_work_and_retains_completed_artifact_as_history(self):
        ids,_=self.seed(); app=self.app(model=RecordingModel())
        first=self.result(app,ids)
        run=app.start('one','queued','fielddesk',ids,'email')
        self.now=datetime(2026,11,25,tzinfo=timezone.utc).timestamp()
        app.worker.drain('one',run_id=run)
        self.assertEqual(len(app.inference.gateway.requests),3)
        self.assertIsNone(app.inspect('one','queued')['saved'])
        historical=app.inspect('one','content')
        self.assertEqual(historical['saved'],first['saved'])
        self.assertFalse(historical['ready_for_review'])


class ChannelMigrationTests(unittest.TestCase):
    def test_schema_19_failure_rolls_back_and_upgrade_preserves_context_bytes_and_legacy_cutoff(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'app.sqlite'
            contacts=build_contact_directory(path,'one','fielddesk',lambda:NOW)
            evidence=contacts.prepare('one','source','fielddesk-crm-a',1,'email')
            recipient=build_recipient_contexts(path,'one','fielddesk',lambda:NOW)
            recipient.prepare('one','original',evidence['assessment_id'],evidence['report']['eligible'][0],'reviewed-context-a',1)
            database=contacts.store.database
            with database.transaction() as db:
                db.execute("INSERT INTO runs VALUES('old','one','old','old-hash','succeeded',?)",(NOW,))
                db.execute("INSERT INTO legacy_task_admissions VALUES('one','old','old-hash')")
                saved=db.execute('SELECT payload FROM recipient_contexts').fetchone()[0]
                for table in ('channel_preparations','channel_artifacts'): db.execute('DROP TABLE '+table)
                db.execute('PRAGMA user_version=19')
            original=Database._apply_migration
            def fail(db,script):
                original(db,script)
                if 'CREATE TABLE IF NOT EXISTS channel_preparations' in script: raise OSError('injected migration failure')
            with patch.object(Database,'_apply_migration',side_effect=fail), self.assertRaises(OSError): Database(path)
            with database.connect() as db:
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],19)
                self.assertIsNone(db.execute("SELECT name FROM sqlite_schema WHERE name='channel_artifacts'").fetchone())
                self.assertEqual(db.execute('SELECT payload FROM recipient_contexts').fetchone()[0],saved)
            Database(path)
            with database.connect() as db:
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],23)
                self.assertEqual(db.execute('SELECT payload FROM recipient_contexts').fetchone()[0],saved)
                self.assertEqual(tuple(db.execute('SELECT * FROM legacy_task_admissions').fetchone()),('one','old','old-hash'))


if __name__=='__main__': unittest.main()
