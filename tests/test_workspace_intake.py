"""Real HTTP intake: trusted identity, exact retries, conflicts and durable revisions."""

import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from acquisition.bootstrap import build_intake
from acquisition.creative import CompanyDraft
import test_workspace as workspace_tests


class WorkspaceIntakeHttpTests(unittest.TestCase):
    setUp = workspace_tests.WorkspaceHttpTests.setUp
    stop = workspace_tests.WorkspaceHttpTests.stop
    def request(self, path, payload=None, headers=None):
        headers = dict(headers or {})
        if payload is not None and path.split('?')[0] in {'/api/intake/companies', '/api/intake/briefs'}:
            _, body, _ = workspace_tests.WorkspaceHttpTests.request(self, '/api/intake/store')
            headers.setdefault('X-Intake-Store', json.loads(body).get('store_id', 'missing'))
        return workspace_tests.WorkspaceHttpTests.request(self, path, payload, headers)

    def save(self, kind, request_id, draft, identity=None, revision=0):
        return self.request('/api/intake/'+kind, {'request_id':request_id, 'id':identity,
                                                'expected_revision':revision, 'draft':draft})

    def test_round_trip_exact_scope_revisions_replay_and_process_restart(self):
        text = 'Source wording \u2014 preserved exactly'
        status, body, _ = self.save('companies', 'company', {'company_name':'Example', 'description':text,
            'claims':[{'statement':text,'qualification':'UK only','source_urls':['https://example.invalid/source']}]})
        self.assertEqual(status,200,body)
        company = json.loads(body)['snapshot']
        self.assertEqual((company['organization'],company['actor']),('local-conversations','local-operator'))
        brief = {'company_id':company['id'], 'company_revision':1, 'objective':text,
                 'country':'France','channels':['video'],'currency':'EUR','budget_minor':12345}
        status, body, _ = self.save('briefs','brief',brief)
        self.assertEqual(status,200,body)
        saved = json.loads(body)['snapshot']
        self.assertEqual(self.save('companies','edit',{'company_name':'Edited'},company['id'],1)[0],200)
        status, body, _ = self.save('briefs','brief',brief)
        self.assertEqual(status,200,body)
        self.assertTrue(json.loads(body)['replayed'])
        self.assertEqual(json.loads(body)['snapshot'],saved)
        for kind, snapshot in [('companies',company),('briefs',saved)]:
            status, body, _ = self.request('/api/intake/'+kind+'/'+snapshot['id']+'?revision=1')
            self.assertEqual(status,200,body)
            self.assertEqual(json.loads(body),snapshot)
        program = '''
import json,sys
from acquisition.bootstrap import build_intake
app=build_intake(sys.argv[1],read_only=True)
print(json.dumps([app.company('local-conversations',sys.argv[2],1),app.brief('local-conversations',sys.argv[3])]))
'''
        child = subprocess.run([sys.executable,'-c',program,str(self.root/'data'/'conversations.sqlite'),company['id'],saved['id']],
                               env=dict(os.environ,PYTHONPATH='src'),capture_output=True,text=True,timeout=20)
        self.assertEqual(child.returncode,0,child.stderr)
        self.assertEqual(json.loads(child.stdout),[company,saved])
        intake = build_intake(self.root/'data'/'conversations.sqlite')
        with intake.store.database.connect() as db:
            for table in ('runs','tasks','model_calls','drafts','review_decisions'):
                self.assertEqual(db.execute('SELECT count(*) FROM '+table).fetchone()[0],0,table)

    def test_authority_substitution_and_foreign_references_have_no_effect(self):
        company_payload = {'request_id':'company','id':None,'expected_revision':0,'draft':{'company_name':'Example'}}
        for bad in ({'Host':'attacker.invalid'}, {'X-Workspace-Token':''}, {'Origin':'https://attacker.invalid'}):
            self.assertEqual(self.request('/api/intake/companies',company_payload,bad)[0],403)
        for field in ('organization','actor'):
            self.assertEqual(self.request('/api/intake/companies',company_payload | {field:'forged'})[0],400)
            nested = company_payload | {'draft':{'company_name':'Example',field:'forged'}}
            self.assertEqual(self.request('/api/intake/companies',nested)[0],400)
            self.assertEqual(self.request('/api/intake/companies?'+field+'=foreign')[0],400)
        app = build_intake(self.root/'data'/'conversations.sqlite')
        foreign = app.save_company('foreign','writer','company',CompanyDraft(company_name='Private'))['snapshot']
        self.assertEqual(self.request('/api/intake/companies/'+foreign['id'])[0],404)
        self.assertEqual(self.save('companies','foreign-edit',{},foreign['id'],1)[0],404)
        self.assertEqual(self.save('briefs','foreign-reference',{'company_id':foreign['id'],'company_revision':1})[0],404)
        self.assertEqual(json.loads(self.request('/api/intake/companies')[1])['items'],[])

    def test_stale_edits_and_bad_shapes_are_definitive_rejections(self):
        status, body, _ = self.request('/api/intake/companies', [])
        self.assertEqual(status,400)
        self.assertTrue(json.loads(body)['intake_not_saved'])
        status, body, _ = self.save('companies','company',{})
        company = json.loads(body)['snapshot']
        self.assertEqual(status,200)
        self.assertEqual(self.save('companies','edit',{'company_name':'Winner'},company['id'],1)[0],200)
        for kind, draft, identity, revision in (
                ('companies',{'company_name':'Stale'},company['id'],1),
                ('companies',{'claims':'not-an-array'},None,0),
                ('companies',{'claims':[{'statement':'Claim','authority':'verified'}]},None,0),
                ('companies',{'claims':[{}]},None,0),
                ('briefs',{'company_id':company['id'],'company_revision':1,'contact_source':[]},None,0),
                ('briefs',{'company_id':company['id'],'company_revision':1,'budget_minor':1.5},None,0)):
            status, body, _ = self.save(kind,'rejected',draft,identity,revision)
            self.assertIn(status,(400,409),body)
            self.assertTrue(json.loads(body)['intake_not_saved'])
        self.assertEqual(self.request('/api/intake/companies?limit=101')[0],400)
        self.assertEqual(self.request('/api/intake/companies?limit=2&limit=1')[0],400)
        self.assertEqual(self.request('/api/intake/companies/'+company['id']+'?revision=0')[0],400)
        for headers in ({'Authorization':'Bearer test-only'}, {'X-OpenRouter-Handle':'test-only'}):
            status, body, _ = self.request('/api/intake/companies', {'request_id':'funding', 'id':None,
                'expected_revision':0, 'draft':{}}, headers)
            self.assertEqual(status,400)
            self.assertTrue(json.loads(body)['intake_not_saved'])
        page = json.loads(self.request('/api/intake/companies?limit=1')[1])['items']
        self.assertEqual(len(page),1)
        self.assertEqual(page[0]['draft']['company_name'],'Winner')
        self.assertEqual(json.loads(self.request('/api/intake/companies?after_id='+page[0]['id'])[1])['items'],[])

    def test_intake_body_limit_is_local_and_domain_payload_remains_bounded(self):
        # Selecting intake on a verified workspace keeps its existing admission policy.
        self.server.workspace._requested_verified = True
        large = {'description':'x'*8000, 'claims':[{'statement':'x'*3000} for _ in range(6)]}
        status, body, _ = self.save('companies','large',large)
        self.assertEqual(status,200,body)  # Bigger than the ordinary 16 KiB command limit.
        from acquisition.bootstrap import verified_admission_mode
        self.assertTrue(verified_admission_mode(self.root/'data'/'conversations.sqlite'))
        too_large = {'description':'x'*8000, 'claims':[{'statement':'x'*3000} for _ in range(19)]}
        self.assertEqual(self.save('companies','too-large',too_large)[0],400)
        status, body, _ = self.save('companies','transport-limit',{'description':'x'*72000})
        self.assertEqual(status,400)
        self.assertTrue(json.loads(body)['intake_not_saved'])

    def test_original_store_binding_blocks_other_root_and_preserves_replay(self):
        from acquisition.bootstrap import build_workspace
        status, body, headers = self.request('/api/intake/store')
        self.assertEqual(status, 200, body)
        self.assertEqual(headers['Cache-Control'], 'no-store')
        original_id = json.loads(body)['store_id']
        payload = {'request_id':'original', 'id':None, 'expected_revision':0,
                   'draft':{'company_name':'Original store only'}}
        status, body, _ = self.request('/api/intake/companies', payload)
        self.assertEqual(status, 200, body)
        original_receipt = json.loads(body)
        original_workspace = self.server.workspace
        other_root = self.root / 'other'
        self.server.workspace = self.server._http.workspace = build_workspace(other_root)
        other_id = json.loads(self.request('/api/intake/store')[1])['store_id']
        self.assertNotEqual(other_id, original_id)
        for binding in (original_id, ''):
            status, body, _ = self.request('/api/intake/companies', payload, {'X-Intake-Store':binding})
            self.assertEqual(status, 409, body)
            self.assertNotIn('intake_not_saved', json.loads(body))
        self.assertEqual(json.loads(self.request('/api/intake/companies')[1])['items'], [])
        other = build_intake(other_root / 'conversations.sqlite')
        with other.store.database.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM intake_requests').fetchone()[0], 0)
        # Even a same-key receipt in B cannot reconcile A's command.
        self.assertEqual(self.request('/api/intake/companies', payload)[0], 200)
        status, body, _ = self.request('/api/intake/companies', payload, {'X-Intake-Store':original_id})
        self.assertEqual(status, 409, body)
        self.assertNotIn('intake_not_saved', json.loads(body))
        self.server.workspace = self.server._http.workspace = original_workspace
        self.assertEqual(json.loads(self.request('/api/intake/store')[1])['store_id'], original_id)
        status, body, _ = self.request('/api/intake/companies', payload, {'X-Intake-Store':original_id})
        self.assertEqual(status, 200, body)
        self.assertTrue(json.loads(body)['replayed'])
        self.assertEqual(json.loads(body)['snapshot'], original_receipt['snapshot'])
        self.assertEqual(len(json.loads(self.request('/api/intake/companies')[1])['items']), 1)

    def planning_workspace(self):
        from acquisition.bootstrap import build_workspace
        from test_intake_planning import IntakeModel
        model = IntakeModel()
        workspace = build_workspace(self.root/'data', gateway_factory=lambda:model)
        self.server.workspace = self.server._http.workspace = workspace
        return model

    def planning_brief(self):
        status, body, _ = self.save('companies','company',{'company_name':'Aster','description':'Unverified consultancy claims'})
        self.assertEqual(status,200,body)
        company = json.loads(body)['snapshot']
        status, body, _ = self.save('briefs','brief',{'company_id':company['id'],'company_revision':1,
                'objective':'Explore retail consulting','audience':'UK retail businesses','country':'UK','currency':'GBP',
                'budget_minor':12345,'channels':['email']})
        self.assertEqual(status,200,body)
        return company,json.loads(body)['snapshot']

    def test_planning_http_preserves_source_scope_replay_and_read_only_progress(self):
        model = self.planning_workspace()
        company, brief = self.planning_brief()
        store = json.loads(self.request('/api/intake/store')[1])['store_id']
        command = {'request_id':'interpret','brief_id':brief['id'],'brief_revision':1,'allow_model':True}
        status, body, _ = self.request('/api/intake/plans',command,{'X-Intake-Store':store})
        self.assertEqual(status,200,body)
        original = json.loads(body)
        self.assertEqual(original['plan']['status'],'succeeded',original)
        self.assertEqual(original['source']['company'],company)
        self.assertEqual(original['source']['brief'],brief)
        self.assertEqual(len(model.requests),1)
        for path in ('/api/intake/plans/interpret','/api/intake/plans?brief_id='+brief['id'],
                     '/api/intake/briefs/'+brief['id']+'/readiness?revision=1'):
            self.assertEqual(self.request(path)[0],200)
        self.assertEqual(len(model.requests),1)
        status, body, _ = self.request('/api/intake/plans',command,{'X-Intake-Store':store})
        self.assertEqual(status,200,body)
        self.assertEqual(json.loads(body)['plan']['result'],original['plan']['result'])
        self.assertEqual(len(model.requests),1)
        with build_intake(self.root/'data'/'conversations.sqlite').store.database.connect() as db:
            for table in ('drafts','review_decisions','simulated_agency_jobs'):
                self.assertEqual(db.execute('SELECT count(*) FROM '+table).fetchone()[0],0)

    def test_planning_guards_and_unsupported_intake_create_no_model_effect(self):
        model = self.planning_workspace()
        _, brief = self.planning_brief()
        store = json.loads(self.request('/api/intake/store')[1])['store_id']
        command = {'request_id':'interpret','brief_id':brief['id'],'brief_revision':1,'allow_model':True}
        for bad in ({'Host':'attacker.invalid'},{'X-Workspace-Token':''},{'Origin':'https://attacker.invalid'}):
            self.assertEqual(self.request('/api/intake/plans',command,{'X-Intake-Store':store,**bad})[0],403)
        self.assertEqual(self.request('/api/intake/plans',command,{'X-Intake-Store':'other'})[0],409)
        self.assertEqual(self.request('/api/intake/plans',command|{'organization':'foreign'},{'X-Intake-Store':store})[0],400)
        self.assertEqual(self.request('/api/intake/plans',command|{'allow_model':False},{'X-Intake-Store':store})[0],400)
        self.assertEqual(model.requests,[])
        self.assertEqual(json.loads(self.request('/api/intake/plans?brief_id='+brief['id'])[1])['items'],[])
        unsupported = brief['draft'] | {'country':'France','currency':'EUR','channels':['video']}
        self.assertEqual(self.save('briefs','changed',unsupported,brief['id'],1)[0],200)
        status, body, _ = self.request('/api/intake/plans',command,{'X-Intake-Store':store})
        self.assertEqual(status,409,body)
        self.assertTrue(json.loads(body)['intake_plan_not_admitted'])
        status, body, _ = self.request('/api/intake/plans',command|{'request_id':'unsupported','brief_revision':2},{'X-Intake-Store':store})
        self.assertEqual(status,200,body)
        self.assertEqual(json.loads(body)['plan']['result']['outcome'],'unsupported')
        self.assertEqual(json.loads(body)['plan']['result']['requirements']['channels'],['video'])
        self.assertEqual(model.requests,[])

    def context_inputs(self):
        _, brief = self.planning_brief()
        status,body,_=self.request('/api/intake/contexts/preview?brief_id='+brief['id']+'&revision=1')
        self.assertEqual(status,200,body);preview=json.loads(body)
        return {'request_id':'input-review','brief_id':brief['id'],'brief_revision':1,'preview_id':preview['id'],
                'expected_context_revision':0,'selected_claim_ids':[],'include_description':True,'include_cta':False,
                'review_days':7,'review_note':'Reviewed original user assertions.','issues':['Evidence remains unverified.'],'confirmed':True},preview

    def test_preparation_context_http_replays_exact_review_and_guards_authority(self):
        payload,preview=self.context_inputs()
        store=json.loads(self.request('/api/intake/store')[1])['store_id']
        for bad in ({'Host':'attacker.invalid'},{'X-Workspace-Token':''},{'Origin':'https://attacker.invalid'}):
            self.assertEqual(self.request('/api/intake/contexts',payload,{'X-Intake-Store':store,**bad})[0],403)
        status,body,_=self.request('/api/intake/contexts',payload,{'X-Intake-Store':'other'})
        self.assertEqual(status,409);self.assertNotIn('context_not_saved',json.loads(body))
        for bad in ({'organization':'foreign'},{'actor':'another'},{'generation':'allowed'},{'confirmed':False}):
            status,body,_=self.request('/api/intake/contexts',payload|bad,{'X-Intake-Store':store})
            self.assertEqual(status,409,body);self.assertTrue(json.loads(body)['context_not_saved'])
        status,body,_=self.request('/api/intake/contexts',payload,{'X-Intake-Store':store})
        self.assertEqual(status,200,body);first=json.loads(body)
        self.assertEqual(first['context']['source']['company'],preview['company'])
        self.assertEqual(first['context']['source']['brief'],preview['brief'])
        self.assertEqual(first['context']['reviewer'],'local-operator')
        self.assertEqual(first['context']['generation'],'unavailable')
        for path in ('/api/intake/contexts/requests/input-review','/api/intake/contexts?brief_id='+payload['brief_id']):
            self.assertEqual(self.request(path)[0],200)
        self.assertEqual(self.save('companies','edit-company',{'company_name':'New version'},preview['company']['id'],1)[0],200)
        status,body,_=self.request('/api/intake/contexts',payload,{'X-Intake-Store':store})
        replay=json.loads(body);self.assertEqual(status,200,body);self.assertTrue(replay['replayed'])
        self.assertFalse(replay['current']);self.assertEqual(replay['context'],first['context'])
        status,body,_=self.request('/api/intake/contexts',payload|{'review_note':'Changed request'}, {'X-Intake-Store':store})
        self.assertEqual(status,409);self.assertFalse(json.loads(body)['context_not_saved'])
        with build_intake(self.root/'data'/'conversations.sqlite').store.database.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM preparation_contexts').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM model_calls').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM review_decisions').fetchone()[0],0)

    def test_preparation_context_stale_preview_rejects_without_effect_and_fresh_review_succeeds(self):
        payload,preview=self.context_inputs()
        store=json.loads(self.request('/api/intake/store')[1])['store_id']
        draft=preview['brief']['draft']|{'country':'France','currency':'EUR','channels':['video']}
        self.assertEqual(self.save('briefs','changed',draft,payload['brief_id'],1)[0],200)
        status,body,_=self.request('/api/intake/contexts',payload,{'X-Intake-Store':store})
        self.assertEqual(status,409,body);self.assertTrue(json.loads(body)['context_not_saved'])
        status,body,_=self.request('/api/intake/contexts/preview?brief_id='+payload['brief_id']+'&revision=2')
        self.assertEqual(status,200,body);fresh=json.loads(body)
        status,body,_=self.request('/api/intake/contexts',payload|{'brief_revision':2,'preview_id':fresh['id']},{'X-Intake-Store':store})
        self.assertEqual(status,200,body);saved=json.loads(body)['context']
        self.assertEqual(saved['requirements']['country'],'France')
        self.assertTrue(saved['requirements_readiness']['unsupported'])
        self.assertEqual(saved['reviewer_questions'],['Evidence remains unverified.'])
