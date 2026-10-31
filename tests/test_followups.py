"""Frozen follow-up provenance, independent enrollment and new review authority."""
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
import test_conversation_learning as learning_tests
from acquisition.workspace import Workspace
from acquisition.contracts import Conflict, NotFound
from test_copy_revisions import RevisionModel


class FollowupTests(unittest.TestCase):
    setUp=learning_tests.ConversationLearningTests.setUp
    approve=learning_tests.ConversationLearningTests.approve
    accept=learning_tests.ConversationLearningTests.accept

    def finalized(self):
        self.accept()
        self.w.action(self.sid,'open-learning',{'request_id':'open'})
        self.parent=self.w.action(self.sid,'finalize',{'request_id':'final'})
        self.scope=self.w._session(self.sid)['organization']
        self.cohort=self.parent['learning']['cohort']['id']
        return self.w.propose_followup(self.sid,'proposal',self.cohort)

    def test_fixture_followup_is_disjoint_has_new_subject_and_can_open_independent_learning(self):
        p=self.finalized()
        self.assertTrue(p['eligible'])
        child=self.w.prepare_followup(self.sid,'prepare',p['id'],'fixture',False)
        self.assertTrue(child['review']['candidate_valid'],child['review']['blocked_reasons'])
        self.assertFalse(child['review']['approval_valid'])
        self.assertNotEqual(child['review']['subject']['id'],self.parent['review']['subject']['id'])
        old={r['id'] for r in self.parent['audience'] if r['arm']!='excluded'}
        new={r['id'] for r in child['audience'] if r['arm']!='excluded'}
        self.assertTrue(new);self.assertFalse(old&new)
        with self.assertRaises((Conflict,NotFound)):
            self.w.action(child['session']['id'],'handoff',{'request_id':'inherited','approval_id':self.parent['review']['handoff']['approval_id']})
        approved=self.w.action(child['session']['id'],'approve',{'request_id':'new-review','subject_id':child['review']['subject']['id'],'reason':'Reviewed the new disjoint proposal.'})
        self.w.action(child['session']['id'],'handoff',{'request_id':'new-handoff','approval_id':approved['review']['approval']['id']})
        opened=self.w.action(child['session']['id'],'open-learning',{'request_id':'new-window'})
        self.assertEqual(opened['learning']['enrolled'],len(new))
        self.assertEqual(self.w.view(self.sid)['learning'],self.parent['learning'])

    def test_replay_freezes_proposal_and_original_mode_and_source_scope(self):
        p=self.finalized()
        self.assertEqual(self.w.propose_followup(self.sid,'proposal',self.cohort),p)
        child=self.w.prepare_followup(self.sid,'prepare',p['id'],'fixture',False)
        reopened=Workspace(self.root,real_clock=lambda:1792972800.)
        replay=reopened.prepare_followup(self.sid,'another-key',p['id'],'fixture',False)
        self.assertEqual(replay['session']['run_id'],child['session']['run_id'])
        self.assertEqual(replay['review']['subject'],child['review']['subject'])
        with self.assertRaises(Conflict): reopened.prepare_followup(self.sid,'changed',p['id'],'model',True)
        with self.assertRaises(Conflict): reopened.propose_followup(self.sid,'proposal','other-cohort')
        with self.assertRaises(NotFound): self.w._app(self.w._session(self.sid)).followups.get('other-org',p['id'])

    def test_changed_population_or_evidence_blocks_before_preparation(self):
        p=self.finalized();app=self.w._app(self.w._session(self.sid))
        app.reviews.store.suppress(self.scope,'local-operator','late',p['population'][0],'Changed after proposal')
        with self.assertRaises(Conflict):self.w.prepare_followup(self.sid,'prep',p['id'],'fixture',False)
        self.assertEqual(self.w.view(self.sid)['learning'],self.parent['learning'])

    def test_preparation_request_binds_inputs_across_valid_proposals_and_restart(self):
        p=self.finalized()
        first=self.w.prepare_followup(self.sid,'same-request',p['id'],'fixture',False)
        app=self.w._app(self.w._session(self.sid))
        app.reviews.store.suppress(self.scope,'local-operator','change-population',p['population'][0],'New suppression')
        second=self.w.propose_followup(self.sid,'new-proposal',self.cohort)
        self.assertTrue(second['eligible'])
        self.assertNotEqual(second['id'],p['id'])
        reopened=Workspace(self.root,real_clock=lambda:1792972800.)
        replay=reopened.prepare_followup(self.sid,'same-request',p['id'],'fixture',False)
        self.assertEqual(replay['session']['id'],first['session']['id'])
        with self.assertRaises(Conflict):
            reopened.prepare_followup(self.sid,'same-request',second['id'],'fixture',False)
        with self.assertRaises(Conflict):
            reopened.prepare_followup(self.sid,'same-request',p['id'],'model',True)
        from acquisition.contracts import digest
        second_id='workspace_'+digest({'followup':second['id']})[:24]
        with self.assertRaises(NotFound): reopened._session(second_id)
        prepared=reopened.prepare_followup(self.sid,'different-request',second['id'],'fixture',False)
        self.assertEqual(prepared['session']['id'],second_id)

    def test_unfinalized_learning_cannot_propose(self):
        self.accept();state=self.w.action(self.sid,'open-learning',{'request_id':'open'})
        with self.assertRaises(Conflict): self.w.propose_followup(self.sid,'p',state['learning']['cohort']['id'])

    def test_model_uses_frozen_context_and_explicit_consent(self):
        p=self.finalized()
        with self.assertRaises(ValueError): self.w.prepare_followup(self.sid,'not-consented',p['id'],'model',False)
        model=RevisionModel()
        with patch('acquisition.workspace.openrouter_key',return_value='fake'),patch('acquisition.workspace.OpenRouter',return_value=model):
            child=self.w.prepare_followup(self.sid,'model',p['id'],'model',True)
            self.assertTrue(child['review']['candidate_valid'],child['review']['blocked_reasons'])
            app=self.w._app(self.w._session(child['session']['id']))
            task=app.tasks.inspect(self.scope,child['session']['run_id'])['tasks'][0]
            self.assertEqual(task['inputs']['context_ids'],p['contexts'])
            for segment,cid in p['contexts'].items():
                context=app.memory.get_context(self.scope,cid)
                self.assertEqual(context['audience_summary']['outcome_evidence'],p['memory'][segment])
            calls=len(model.copy.requests)
            self.w.prepare_followup(self.sid,'retry',p['id'],'model',True)
            self.assertEqual(len(model.copy.requests),calls)

    def test_later_population_allocation_blocks_review_and_cannot_be_removed_from_brief(self):
        from dataclasses import replace
        from acquisition.campaigns import Brief, build_draft
        from acquisition.reviews import creatives_from
        p=self.finalized();child=self.w.prepare_followup(self.sid,'child',p['id'],'fixture',False)
        app=self.w._app(self.w._session(self.sid))
        run=app.start(self.scope,'competing',size=2000,budget_pence=85000,as_of='2026-11-22')
        app.worker.drain(self.scope,run_id=run)
        case=app.reviews.store.open_case(self.scope,run,'local-operator')
        a=app.reviews.store.decide(self.scope,case['case_id'],case['subject_id'],'local-reviewer','approve','competing-review','Reviewed',86400)
        app.reviews.store.handoff(self.scope,case['case_id'],a['id'],'local-operator','competing-handoff')
        blocked=self.w.view(child['session']['id'])
        self.assertFalse(blocked['review']['candidate_valid'])
        with self.assertRaises(Conflict):self.w.action(child['session']['id'],'approve',{'request_id':'blocked','subject_id':blocked['review']['subject']['id'],'reason':'Attempt stale population'})
        original=app.drafts.get(self.scope,child['review']['subject']['draft_id'])
        snapshot=app.audiences.get(self.scope,p['snapshot_id'])
        # Strip the provenance while retaining a structurally valid subset.
        from acquisition.campaigns import FollowupBrief
        stripped=replace(original,manifest=original.manifest|{'brief':original.manifest['brief']|{'followup_id':'followup_forged'}})
        # Direct publication cannot substitute internally consistent source metadata.
        with self.assertRaises(Conflict):app.drafts.put(self.scope,'forged-followup',stripped)
        from acquisition.creative import fixture_catalog
        plain = build_draft(snapshot,Brief(child['session']['id'],60000),fixture_catalog())
        plain_id = app.drafts.put(self.scope,'removed-provenance',plain)
        authority = app.reviews.store.evidence(self.scope)
        with self.assertRaises(Conflict):
            app.reviews.store.propose(self.scope,child['review']['case_id'],child['review']['subject']['id'],plain_id,
                'local-operator','remove-source',authority['audience_epoch'],authority['evidence_epoch'])

    def test_exhausted_inventory_is_visible_and_cannot_prepare(self):
        from dataclasses import replace
        p=self.finalized()
        app=self.w._app(self.w._session(self.sid))
        source=app.followup_population(self.scope,'2026-11-22')
        # A valid complete inventory can contain no independently enrollable rows.
        empty=replace(source,records=())
        with patch('acquisition.bootstrap.Application.followup_population',return_value=empty):
            exhausted=self.w.propose_followup(self.sid,'exhausted',self.cohort)
        self.assertFalse(exhausted['eligible'])
        with self.assertRaises(Conflict):self.w.prepare_followup(self.sid,'prep-empty',exhausted['id'],'fixture',False)


    def test_fresh_process_prepares_original_frozen_proposal(self):
        import subprocess, sys, os
        p=self.finalized()
        code = """import sys,json
from acquisition.workspace import Workspace
w=Workspace(sys.argv[1],real_clock=lambda:1792972800.)
s=w.prepare_followup(sys.argv[2],'restart',sys.argv[3],'fixture',False)
print(json.dumps(s['session']))
"""
        result=subprocess.run([sys.executable,'-c',code,str(self.root),self.sid,p['id']],env=dict(os.environ,PYTHONPATH=str(Path('src').resolve())),text=True,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        child=json.loads(result.stdout)
        replay=self.w.prepare_followup(self.sid,'after-restart',p['id'],'fixture',False)
        self.assertEqual(replay['session']['run_id'],child['run_id'])

    def test_unknown_model_result_is_not_repeated_on_prepare_replay(self):
        from acquisition.reasoning import ModelError
        p=self.finalized();model=RevisionModel()
        with patch('acquisition.workspace.openrouter_key',return_value='fake'),patch('acquisition.workspace.OpenRouter',return_value=model),patch.object(model,'complete',side_effect=ModelError('provider_request_failed')) as dispatch:
            for key in ('initial','retry'):
                with self.assertRaises(Conflict):self.w.prepare_followup(self.sid,key,p['id'],'model',True)
            self.assertEqual(dispatch.call_count,1)
        row=self.w.view(self.sid)['followups'][0]
        self.assertTrue(row['generation']['outcome_uncertain'])

    def test_saved_model_proposal_ignores_changed_or_unavailable_current_assets(self):
        import shutil
        from acquisition.bootstrap import agent_catalogue
        p=self.finalized()
        changed=agent_catalogue()
        changed['skills']=[]
        for unavailable in (False,True):
            with self.subTest(unavailable=unavailable), tempfile.TemporaryDirectory() as folder:
                root=Path(folder)/'saved'
                shutil.copytree(self.root,root)
                w=Workspace(root,real_clock=lambda:1792972800.)
                model=RevisionModel()
                catalogue_patch=(patch('acquisition.bootstrap.agent_catalogue',side_effect=ValueError('Catalogue unavailable'))
                                 if unavailable else patch('acquisition.bootstrap.agent_catalogue',return_value=changed))
                with catalogue_patch as catalogue, patch('acquisition.bootstrap.copy_assets',side_effect=AssertionError('Must use frozen contexts')) as rebuild, patch('acquisition.workspace.openrouter_key',return_value='fake'),patch('acquisition.workspace.OpenRouter',return_value=model):
                    child=w.prepare_followup(self.sid,'frozen-copy',p['id'],'model',True)
                    self.assertTrue(child['review']['candidate_valid'],child['review']['blocked_reasons'])
                    self.assertFalse(child['review']['approval_valid'])
                    catalogue.assert_not_called()
                    rebuild.assert_not_called()
                app=w._app(w._session(child['session']['id']))
                task=app.tasks.inspect(self.scope,child['session']['run_id'])['tasks'][0]
                self.assertEqual(task['inputs']['context_ids'],p['contexts'])
