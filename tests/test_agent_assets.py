"""Scoped frozen reasoning assets cannot install tools or change review authority."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from acquisition.bootstrap import build, agent_catalogue
from acquisition.contracts import digest, Conflict
from acquisition.conversations import FIXTURE_MESSAGE
from acquisition.reasoning import validate_assets, ModelConfig
from test_conversations import PlannerModel
from test_copy_revisions import RevisionModel
from acquisition.workspace import Workspace


class AgentAssetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'app.sqlite'
        self.app = build(self.path, clock=lambda:1792972800.)
        self.c = self.app.conversations.create('one','chat')['id']
        self.app.conversations.message('one',self.c,'m',0,FIXTURE_MESSAGE)

    def frozen(self):
        self.app.conversations.plan_fixture('one',self.c,'plan',1)
        return self.app.conversations.store.snapshot('one',self.c)['admissions'][0]

    def test_planning_freezes_exact_sources_and_only_installed_proposal_tool(self):
        frozen = self.frozen()
        assets = frozen['knowledge']['agent_assets']
        validate_assets(assets,organization='one')
        self.assertEqual([s['id'] for s in assets['skills']],['prepare-campaign/v1'])
        self.assertEqual([t['wire']['function']['name'] for t in assets['tools']],['submit_campaign_brief'])
        for source in assets['sources']:
            payload = frozen['knowledge']['playbooks'] if source['key'] == 'playbooks' else {k:v for k,v in frozen['knowledge'].items() if k not in {'agent_assets','playbooks'}}
            self.assertEqual(source['content_hash'],digest(payload))
            self.assertEqual(source['permitted_uses'],['guide_reasoning'])
        self.app.worker.drain('one')
        self.assertEqual(self.app.conversations.view('one',self.c)['current_plan']['result']['approval'],'not_granted')
        with self.app.tasks.database.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM review_decisions').fetchone()[0],0)

    def test_historical_plan_resumes_in_fresh_process_without_current_catalogue(self):
        frozen = self.frozen()
        code = """import json,sys
from unittest.mock import patch
from acquisition.bootstrap import build
with patch('acquisition.bootstrap.agent_catalogue',side_effect=ValueError('Current files unavailable')):
 a=build(sys.argv[1],clock=lambda:1792972800.)
 a.conversations.plan_fixture('one',sys.argv[2],'plan',1)
 a.worker.drain('one')
 print(json.dumps(a.conversations.view('one',sys.argv[2])['current_plan']))
"""
        result = subprocess.run([sys.executable,'-c',code,str(self.path),self.c],env=dict(os.environ,PYTHONPATH=str(Path('src').resolve())),capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        view = json.loads(result.stdout)
        self.assertEqual(view['status'],'succeeded')
        self.assertEqual(view['guidance']['content'],frozen['knowledge'])

    def test_new_request_uses_new_skill_content_but_old_snapshot_does_not_change(self):
        before = self.frozen()
        self.app.conversations.message('one',self.c,'m2',1,'Use £300 instead.')
        new = agent_catalogue()
        new['skills'][0]['guidance'].append('New authored wording.')
        with patch('acquisition.bootstrap.agent_catalogue',return_value=new):
            # Use context freeze for a model request; no model dispatch is needed.
            app = build(self.path,clock=lambda:1792972800.,gateway=PlannerModel(),model_config=ModelConfig('test/model'))
            app.conversations.plan('one',self.c,'plan2',2)
        admissions = self.app.conversations.store.snapshot('one',self.c)['admissions']
        self.assertEqual(admissions[0],before)
        self.assertNotEqual(admissions[0]['knowledge']['agent_assets']['id'],admissions[1]['knowledge']['agent_assets']['id'])

    def test_unknown_skill_tool_and_missing_source_fail_before_admission(self):
        for mutate in (lambda c:c['skills'][0]['tool_ids'].append('send_campaign/v1'),
                       lambda c:c['skills'][0].update(id='unknown-skill/v1'),
                       lambda c:c['skills'][0].update(guidance='not-a-list'),
                       lambda c:c['skills'][0].update(authority='approve'),
                       lambda c:c['skills'][0]['required_source_kinds'].append('product_evidence')):
            with self.subTest(mutate=mutate):
                catalogue = agent_catalogue(); mutate(catalogue)
                with patch('acquisition.bootstrap.agent_catalogue',return_value=catalogue):
                    with self.assertRaises(ValueError): self.app.conversations.plan_fixture('one',self.c,'plan',1)
                self.assertEqual(self.app.conversations.store.snapshot('one',self.c)['admissions'],[])

    def test_rehashed_foreign_scope_and_source_roles_are_rejected(self):
        bundle = self.frozen()['knowledge']['agent_assets']
        with self.assertRaises(ValueError): validate_assets(bundle,organization='two')
        changed = copy.deepcopy(bundle)
        changed['sources'][0]['permitted_uses']=['ground_product_copy']
        changed['sources'][0]['id']='source_'+digest({k:v for k,v in changed['sources'][0].items() if k!='id'})
        changed['id']='assets_'+digest({k:v for k,v in changed.items() if k!='id'})
        with self.assertRaises(ValueError): validate_assets(changed)

    def test_changed_wire_schema_and_missing_source_coverage_rejected(self):
        from acquisition.workflows.conversation import validate_planning_assets
        frozen = self.frozen()
        for mutation in ('wire','missing'):
            altered=copy.deepcopy(frozen); bundle=altered['knowledge']['agent_assets']
            if mutation == 'wire':
                t=bundle['tools'][0];t['wire']['function']['parameters']['required']=[]
                t['hash']=digest({k:v for k,v in t.items() if k!='hash'})
            else:
                bundle['sources'].pop()
            bundle['id']='assets_'+digest({k:v for k,v in bundle.items() if k!='id'})
            with self.assertRaises(ValueError): validate_planning_assets(altered,'one')

    def test_bundle_construction_does_not_alias_mutable_source_assets(self):
        from acquisition.reasoning import freeze_assets
        bundle = self.frozen()['knowledge']['agent_assets']
        catalogue = {'version':bundle['catalogue_version'], 'skills':bundle['skills']}
        result = freeze_assets('one',catalogue,bundle['tools'],['prepare-campaign/v1'],bundle['sources'])
        catalogue['skills'][0]['guidance'].append('Changed after freezing.')
        self.assertNotEqual(result['skills'],catalogue['skills'])
        validate_assets(result,organization='one')

    def test_changed_payload_fails_manifest_validation_and_legacy_snapshot_still_runs(self):
        from acquisition.workflows.conversation import validate_planning_assets, ConversationPlanner
        from acquisition.runtime import Claim
        frozen = self.frozen()
        altered = copy.deepcopy(frozen)
        altered['knowledge']['procedures'].append('A new instruction not in the source manifest.')
        with self.assertRaises(ValueError): validate_planning_assets(altered, 'one')
        # An actual old task has no asset metadata. Keep its original hash and
        # original behavior, without rewriting it to the current catalogue.
        legacy = copy.deepcopy(frozen)
        legacy['knowledge'].pop('agent_assets')
        legacy['knowledge_id'] = 'knowledge_' + digest(legacy['knowledge'])
        result = ConversationPlanner(None).fixture_plan(Claim('one','old-run','old-task','fixture',legacy,'lease',1,None))
        self.assertEqual(result.status,'succeeded')
        self.assertEqual(result.data['approval'],'not_granted')

    def test_maximum_reviewer_memory_fits_compact_copy_context(self):
        from test_model_copy import FakeModel
        from acquisition.contracts import canonical
        model=FakeModel()
        app=build(self.path,clock=lambda:1792972800.,gateway=model,model_config=ModelConfig('test/model',max_calls=10))
        for segment in ('inventory','contractors'):
            for index in range(3):
                app.memory.remember('one',segment,'p'*600,'a'*600,str(index)+'r'*599)
        run=app.start_model('one','max-memory',size=100)
        app.worker.drain('one',run_id=run)
        self.assertEqual(app.tasks.inspect('one',run)['run']['status'],'waiting')
        self.assertEqual(len(model.requests),6)
        for request in model.requests:
            self.assertLessEqual(len(canonical(request).encode()),24000)
            if request['tools'][0]['function']['name'] == 'submit_grounded_copy':
                context=json.loads(next(m['content'] for m in request['messages'] if m['role']=='tool'))
                self.assertEqual(len(context['memory']),3)
                self.assertNotIn('tools',context['agent_assets'])
        task=app.tasks.inspect('one',run)['tasks'][0]
        original=app.memory.get_context('one',task['inputs']['context_ids']['inventory'])
        self.assertIn('wire',original['agent_assets']['tools'][0])

    def test_legacy_unannotated_copy_keeps_original_read_transcript(self):
        from acquisition.creative import GroundedCopyAgent
        from acquisition.reasoning import CallScope
        from test_model_copy import FakeModel
        from datetime import date
        model=FakeModel()
        app=build(self.path,clock=lambda:1792972800.,gateway=model,model_config=ModelConfig('test/model',max_calls=10))
        run=app.start_model('one','legacy-transcript',size=100)
        task=app.tasks.inspect('one',run)['tasks'][0]
        context=app.memory.get_context('one',task['inputs']['context_ids']['inventory'])
        context.pop('agent_assets')
        context_id=app.memory.put_context('one',context)
        app.worker.tick('one',run_id=run)
        claim=app.tasks.claim('one',1792972800.,60)
        GroundedCopyAgent(app.inference,app.memory).generate(CallScope('one',run,claim.task_id,claim.token),context_id,date(2026,10,26))
        submitted=model.requests[1]['messages']
        self.assertEqual(submitted[-2]['tool_calls'][0]['id'],'test-call')
        self.assertEqual(submitted[-1]['tool_call_id'],'test-call')
        self.assertNotIn('agent_assets',json.loads(submitted[-1]['content']))

    def test_recorded_legacy_read_replays_at_exact_original_input_limit(self):
        from dataclasses import asdict, replace
        from datetime import date
        from acquisition.contracts import canonical
        from acquisition.creative import GroundedCopyAgent, fact_pack_id
        from acquisition.creative.grounding import editorial_read_exchange
        from acquisition.reasoning import CallScope, Inference
        from acquisition.runtime import TaskSpec
        from test_model_copy import FakeModel, reply

        class ShortReadModel(FakeModel):
            def complete(self, request):
                result=super().complete(request)
                if request['tools'][0]['function']['name'] == 'read_editorial_context':
                    result['message']['tool_calls'][0]['id']='r'
                return result

        config=ModelConfig('test/model',max_calls=10)
        model=ShortReadModel()
        app=build(self.path,clock=lambda:1792972800.,gateway=model,model_config=config)
        source=app.start_model('one','source-context',size=100)
        context_id=app.tasks.inspect('one',source)['tasks'][0]['inputs']['context_ids']['inventory']
        context=app.memory.get_context('one',context_id)
        context.pop('agent_assets')
        context_id=app.memory.put_context('one',context)
        captured={}
        class ProbeStopped(Exception): pass
        def capture(scope, key, messages, tools):
            if tools[0]['function']['name'] == 'read_editorial_context':
                captured['read']=(copy.deepcopy(messages),copy.deepcopy(tools))
                response=reply('read_editorial_context',{})
                response['message']['tool_calls'][0]['id']='r'
                return response
            captured['submit']=(copy.deepcopy(messages),copy.deepcopy(tools))
            raise ProbeStopped()
        with patch.object(app.inference,'call',side_effect=capture):
            with self.assertRaises(ProbeStopped):
                GroundedCopyAgent(app.inference,app.memory).generate(CallScope('one','probe','probe','probe'),context_id,date(2026,10,26))
        messages,tools=captured['submit']
        original=app.inference.prepare_request(messages,tools)
        limit=len(canonical(original).encode())
        synthetic=app.inference.prepare_request(messages[:2]+editorial_read_exchange(context,fact_pack_id(context['product_facts'])),tools)
        self.assertGreater(len(canonical(synthetic).encode()),limit)
        limited=replace(config,max_input_bytes=limit)
        run=app.tasks.create('one','legacy-boundary',[TaskSpec('test.grounded-copy',{'model_config':asdict(limited)})],1792972800.)
        claim=app.tasks.claim('one',1792972800.,60,run_id=run)
        scope=CallScope('one',run,claim.task_id,claim.token)
        inference=Inference(model,app.calls,limited,lambda:1792972800.)
        # Record the historical read, then resume with a fresh inference instance.
        inference.call(scope,context_id+':grounded:read',*captured['read'])
        resumed=Inference(model,app.calls,limited,lambda:1792972800.)
        variants=GroundedCopyAgent(resumed,app.memory).generate(scope,context_id,date(2026,10,26))
        self.assertEqual(len(variants),2)
        self.assertEqual([r['tools'][0]['function']['name'] for r in model.requests],
                         ['read_editorial_context','submit_grounded_copy','record_claim_check'])
        self.assertEqual(canonical(model.requests[1]),canonical(original))
        self.assertEqual(len(app.calls.inspect('one',run)),3)
        self.assertTrue(all(c['status']=='recorded' for c in app.calls.inspect('one',run)))

    def test_over_budget_full_copy_envelope_is_rejected_before_read_or_reservation(self):
        from test_model_copy import FakeModel
        model=FakeModel()
        app=build(self.path,clock=lambda:1792972800.,gateway=model,model_config=ModelConfig('test/model',max_calls=10,max_input_bytes=6000))
        for index in range(3):
            app.memory.remember('one','inventory','p'*600,'a'*600,str(index)+'r'*599)
        run=app.start_model('one','too-large',size=100)
        with patch.object(app.inference,'prepare_request',wraps=app.inference.prepare_request) as preflight:
            app.worker.drain('one',run_id=run)
        self.assertEqual(app.tasks.inspect('one',run)['run']['status'],'failed')
        self.assertEqual(model.requests,[])
        self.assertEqual(app.calls.inspect('one',run),[])
        self.assertEqual([c.args[1][0]['function']['name'] for c in preflight.call_args_list],
                         ['read_editorial_context','submit_grounded_copy'])

    def test_copy_and_revision_freeze_distinct_skills_without_approval(self):
        w=Workspace(Path(self.temp.name)/'workspace',real_clock=lambda:1792972800.)
        c=w.create_conversation('c','Assets')['id']
        model=RevisionModel()
        with patch('acquisition.workspace.openrouter_key',return_value='fake'),patch('acquisition.workspace.OpenRouter',return_value=model):
            w.message_conversation(c,'m',0,'Prepare a £600 contractor campaign with model copy.')
            w.start_preparation(c,'prep',1,False,True)
            for _ in range(6): w.advance_preparations()
            sid=w.conversation(c)['campaigns'][0]['session_id']; state=w.view(sid)
            target=state['review']['manifest']['creatives'][0]
            app=w._app(w._session(sid)); org=w._session(sid)['organization']
            context=app.memory.get_context(org,target['context_id'])
            self.assertEqual(context['agent_assets']['skills'][0]['id'],'grounded-copy/v1')
            self.assertEqual({m['key'] for m in context['agent_assets']['sources']},{'editorial','product_facts','preferences','outcomes','audience'})
            # Recomputing consistent asset metadata cannot substitute base inputs.
            live_app=w._app(w._session(sid),with_model=True)
            from acquisition.bootstrap import copy_assets
            def substituted(organization, value, **kwargs):
                value=copy.deepcopy(value)
                value['audience_summary']['input_records'] += 1
                return copy_assets(organization,value,**kwargs)
            with patch.object(live_app.revisions,'asset_context',side_effect=substituted):
                with self.assertRaises(Conflict):
                    live_app.revisions.admit(org,state['review']['case_id'],'bad-source',state['review']['subject']['id'],target['id'],'Keep it short.',True)
            self.assertEqual(app.reviews.store.revision_requests(org,state['review']['case_id']),[])
            row=w.request_copy_revision(sid,'revise',state['review']['subject']['id'],target['id'],'Use a clearer project question.',True)
            admissions=app.reviews.store.revision_requests(org,state['review']['case_id'])
            revision=admissions[0]['context']
            self.assertEqual(revision['agent_assets']['skills'][0]['id'],'revise-grounded-copy/v1')
            self.assertEqual(revision['product_facts'],context['product_facts'])
            self.assertFalse(w.view(sid)['review']['approval_valid'])
            # Prior context remains immutable.
            self.assertEqual(app.memory.get_context(org,target['context_id']),context)
