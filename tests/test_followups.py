"""Frozen follow-up provenance, independent enrollment and new review authority."""
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
import test_conversation_learning as learning_tests
from acquisition.workspace import Workspace
from acquisition.contracts import Conflict, NotFound, canonical, digest
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
                hypothesis = next(h for h in p['hypotheses'] if h['segment'] == segment)
                self.assertEqual(context['audience_summary']['followup_hypothesis'], hypothesis)
                self.assertIn(hypothesis['evidence_id'], canonical(model.copy.requests))
                source = next(c for c in self.parent['review']['manifest']['creatives']
                              if c['id'] == hypothesis['candidate']['creative_id'])
                self.assertEqual(hypothesis['candidate'].get('hook'), source['opening'])
                self.assertIn(source['opening'], canonical(model.copy.requests))
                goal = next(json.loads(r['messages'][1]['content'])['goal'] for r in model.copy.requests
                            if r['tools'][0]['function']['name'] == 'read_editorial_context'
                            and json.loads(r['messages'][1]['content'])['segment'] == segment)
                self.assertIn('historical framing', goal)
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
        reopened = Workspace(self.root,real_clock=lambda:1792972800.)
        with patch('acquisition.learning.hypotheses.recommend', side_effect=AssertionError('Historical hypothesis recomputed')):
            self.assertEqual(reopened.propose_followup(self.sid,'proposal',self.cohort),p)
        for hypothesis in p['hypotheses']:
            self.assertEqual(hypothesis['evidence']['source_cohort'], self.cohort)
            self.assertEqual(hypothesis['evidence']['source_draft'], self.parent['learning']['cohort']['draft_id'])

    def test_hypotheses_and_model_contexts_must_bind_the_native_source_before_commit(self):
        import copy
        p = self.finalized()
        app = self.w._app(self.w._session(self.sid))
        self.assertEqual(p['hypotheses'][0]['evidence_status'], 'strong')
        with app.tasks.database.connect() as db:
            before = db.execute('SELECT count(*) FROM review_commands').fetchone()[0]
        altered = copy.deepcopy(p)
        altered['hypotheses'][0]['evidence_status'] = 'absent'
        with self.assertRaises(Conflict): app.followups.put(self.scope, 'forged-hypothesis', altered)
        altered = copy.deepcopy(p)
        altered.pop('hypotheses')
        with self.assertRaises(Conflict): app.followups.put(self.scope, 'downgraded-hypothesis', altered)
        altered = copy.deepcopy(p)
        altered['learning']['beliefs'][0]['successes'] += 1
        with self.assertRaises(Conflict): app.followups.put(self.scope, 'forged-evidence', altered)
        altered = copy.deepcopy(p)
        segment = p['brief']['segments'][0]
        context = app.memory.get_context(self.scope, p['contexts'][segment])
        context['audience_summary']['followup_hypothesis']['hypothesis'] = 'A substituted direction.'
        altered['contexts'][segment] = app.memory.put_context(self.scope, context)
        with self.assertRaises(Conflict): app.followups.put(self.scope, 'substituted-context', altered)
        with app.tasks.database.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM review_commands').fetchone()[0], before)
            self.assertEqual(db.execute('SELECT count(*) FROM model_calls').fetchone()[0], 0)
        self.assertEqual(app.followups.get(self.scope, p['id']), p)

    def test_historical_followup_without_structured_hypotheses_replays_and_prepares_original_contexts(self):
        p = self.finalized()
        app = self.w._app(self.w._session(self.sid))
        historical = {k: v for k, v in p.items() if k not in {'id', 'hypotheses'}}
        historical['hypothesis'] = 'Original saved exploratory hypothesis.'
        snapshot = app.audiences.get(self.scope, p['snapshot_id'])
        historical['contexts'] = app.followup_contexts(self.scope, snapshot, tuple(p['brief']['segments']),
                                                       p['memory'], historical['hypothesis'])
        historical['id'] = 'followup_' + digest(historical)
        # Simulate an immutable receipt written by the previous application,
        # rather than admitting a new downgraded proposal through today's port.
        with app.tasks.database.transaction() as db:
            for key in ('followup-request:historical', historical['id']):
                db.execute('INSERT INTO review_commands VALUES(?,?,?,?)',
                           (self.scope, key, digest(historical), canonical(historical)))
        with patch('acquisition.workspace.followup_hypotheses', side_effect=AssertionError('Historical hypothesis replaced')):
            self.assertEqual(self.w.propose_followup(self.sid, 'historical', self.cohort), historical)
            child = self.w.prepare_followup(self.sid, 'historical-prepare', historical['id'], 'fixture', False)
        self.assertTrue(child['review']['candidate_valid'])
        self.assertFalse(child['review']['approval_valid'])
        self.assertEqual(app.followups.get(self.scope, historical['id']), historical)

    def test_finalized_source_outcomes_are_reconciled_before_context_creation_and_again_at_commit(self):
        import copy
        p = self.finalized()
        app = self.w._app(self.w._session(self.sid))
        database = app.tasks.database
        with database.connect() as db:
            rows = [tuple(r) for r in db.execute('SELECT * FROM learning_outcomes WHERE organization=? AND cohort_id=?',
                                                (self.scope, self.cohort))]
            members = [tuple(r) for r in db.execute('SELECT * FROM learning_members WHERE organization=? AND cohort_id=?',
                                                   (self.scope, self.cohort))]
            commands = db.execute('SELECT count(*) FROM review_commands').fetchone()[0]
            contexts = db.execute('SELECT count(*) FROM creative_contexts').fetchone()[0]
        selected = next(row for row in rows if json.loads(row[3])['response'])
        original = json.loads(selected[3])
        variants = {
            'response': original | {'response': False, 'observed_at': p['learning']['cohort']['window_end']},
            'time': original | {'observed_at': p['learning']['cohort']['window_start'] + 1},
            'assignment': original | {'creative_id': 'substituted-assignment'},
        }
        for name in (*variants, 'missing', 'replacement', 'membership'):
            with self.subTest(name=name):
                with database.transaction() as db:
                    if name in variants:
                        db.execute('UPDATE learning_outcomes SET payload=? WHERE organization=? AND cohort_id=? AND business_id=?',
                                   (canonical(variants[name]), self.scope, self.cohort, selected[2]))
                    elif name == 'membership':
                        db.execute('DELETE FROM learning_members WHERE organization=? AND business_id=?', (self.scope, selected[2]))
                    else:
                        db.execute('DELETE FROM learning_outcomes WHERE organization=? AND cohort_id=? AND business_id=?',
                                   (self.scope, self.cohort, selected[2]))
                        if name == 'replacement':
                            db.execute('INSERT INTO learning_outcomes VALUES(?,?,?,?)',
                                       (self.scope, self.cohort, 'outside-cohort', canonical(original | {'business_id': 'outside-cohort'})))
                with self.assertRaises(Conflict):
                    self.w.propose_followup(self.sid, 'corrupt-source-' + name, self.cohort)
                with self.assertRaises(Conflict):
                    app.followups.put(self.scope, 'commit-race-' + name, copy.deepcopy(p))
                with database.connect() as db:
                    self.assertEqual(db.execute('SELECT count(*) FROM review_commands').fetchone()[0], commands)
                    self.assertEqual(db.execute('SELECT count(*) FROM creative_contexts').fetchone()[0], contexts)
                with database.transaction() as db:
                    db.execute('DELETE FROM learning_outcomes WHERE organization=? AND cohort_id=?', (self.scope, self.cohort))
                    db.executemany('INSERT INTO learning_outcomes VALUES(?,?,?,?)', rows)
                    db.execute('DELETE FROM learning_members WHERE organization=? AND cohort_id=?', (self.scope, self.cohort))
                    db.executemany('INSERT INTO learning_members VALUES(?,?,?)', members)
        repaired = self.w.propose_followup(self.sid, 'reconciled-source', self.cohort)
        self.assertEqual(repaired['hypotheses'], p['hypotheses'])
        self.assertEqual(app.followups.get(self.scope, p['id']), p)

    def test_finalized_source_requires_its_exact_accepted_job_and_draft_at_read_and_commit(self):
        import os, subprocess, sys
        from acquisition.campaigns import Draft
        p = self.finalized()
        app = self.w._app(self.w._session(self.sid))
        database = app.tasks.database
        case_id = p['learning']['cohort']['case_id']
        draft_id = p['learning']['cohort']['draft_id']
        with database.connect() as db:
            job = tuple(db.execute('SELECT * FROM simulated_agency_jobs WHERE organization=? AND case_id=?',
                                   (self.scope, case_id)).fetchone())
            draft = db.execute('SELECT manifest,mailing FROM drafts WHERE organization=? AND id=?',
                               (self.scope, draft_id)).fetchone()
            commands = db.execute('SELECT count(*) FROM review_commands').fetchone()[0]
            contexts = db.execute('SELECT count(*) FROM creative_contexts').fetchone()[0]
        receipt = json.loads(job[-1])
        other = Draft(json.loads(draft['manifest']) | {'campaign_id': 'another-campaign'},
                      draft['mailing'], app.drafts.get(self.scope, draft_id).assignments_csv)
        with database.transaction() as db:
            db.execute('INSERT INTO drafts VALUES(?,?,?,?,?)',
                       (self.scope, other.id, canonical(other.manifest), other.mailing_csv, other.assignments_csv))
        variants = {
            'mode': receipt | {'mode': 'NOT_ACCEPTED'},
            'kind': receipt | {'kind': 'proposal_only'},
            'case': receipt | {'case_id': 'another-case'},
            'job': receipt | {'id': 'another-job'},
            'approval': receipt | {'approval_id': 'another-approval'},
            'subject': receipt | {'subject_id': 'another-subject'},
            'time': receipt | {'accepted_at': receipt['accepted_at'] + 1},
            'recipients': receipt | {'recipients': receipt['recipients'] - 1},
            'assignments': receipt | {'assignments_sha256': 'changed'},
            'mailing': receipt | {'mailing_sha256': 'changed'},
            'draft': receipt | {'draft_id': 'unavailable-draft'},
            'substituted-draft': receipt | {'draft_id': other.id},
        }
        for name in ('missing', 'foreign-scope', 'job-index', 'subject-index', 'draft-bytes', *variants):
            with self.subTest(name=name):
                try:
                    with database.connect() as db:
                        # Corruption can predate this process. A foreign-scope
                        # decoy must never substitute for the scoped acceptance.
                        db.execute('PRAGMA foreign_keys=OFF')
                        db.execute('BEGIN IMMEDIATE')
                        if name == 'missing':
                            db.execute('DELETE FROM simulated_agency_jobs WHERE organization=? AND case_id=?', (self.scope, case_id))
                            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
                        elif name == 'foreign-scope':
                            db.execute('UPDATE simulated_agency_jobs SET organization=? WHERE organization=? AND case_id=?',
                                       ('foreign-organization', self.scope, case_id))
                        elif name in {'job-index', 'subject-index'}:
                            column = 'id' if name == 'job-index' else 'subject_id'
                            db.execute('UPDATE simulated_agency_jobs SET ' + column + '=? WHERE organization=? AND case_id=?',
                                       ('substituted-index', self.scope, case_id))
                        elif name == 'draft-bytes':
                            db.execute('UPDATE drafts SET mailing=? WHERE organization=? AND id=?',
                                       (draft['mailing'] + 'changed', self.scope, draft_id))
                        else:
                            db.execute('UPDATE simulated_agency_jobs SET payload=? WHERE organization=? AND case_id=?',
                                       (canonical(variants[name]), self.scope, case_id))
                        db.commit()
                    with self.assertRaises(Conflict):
                        self.w.propose_followup(self.sid, 'unaccepted-source-' + name, self.cohort)
                    with self.assertRaises(Conflict):
                        app.followups.put(self.scope, 'acceptance-commit-race-' + name, p)
                    if name == 'missing':
                        code = """import sys
from acquisition.contracts import Conflict
from acquisition.workspace import Workspace
w=Workspace(sys.argv[1],real_clock=lambda:1792972800.)
try:w.propose_followup(sys.argv[2],'restart-missing-acceptance',sys.argv[3])
except Conflict:print('blocked')
else:raise AssertionError('Missing acceptance supported a new proposal after restart')
"""
                        result = subprocess.run([sys.executable, '-c', code, str(self.root), self.sid, self.cohort],
                            env=dict(os.environ, PYTHONPATH=str(Path('src').resolve())), text=True, capture_output=True, timeout=10)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(result.stdout.strip(), 'blocked')
                    with database.connect() as db:
                        self.assertEqual(db.execute('SELECT count(*) FROM review_commands').fetchone()[0], commands)
                        self.assertEqual(db.execute('SELECT count(*) FROM creative_contexts').fetchone()[0], contexts)
                        self.assertEqual(db.execute('SELECT count(*) FROM model_calls').fetchone()[0], 0)
                    # A saved receipt remains a historical observation, even
                    # when its source can no longer support a new proposal.
                    self.assertEqual(self.w.propose_followup(self.sid, 'proposal', self.cohort), p)
                finally:
                    with database.transaction() as db:
                        db.execute('DELETE FROM simulated_agency_jobs WHERE organization IN (?,?) AND case_id=?',
                                   (self.scope, 'foreign-organization', case_id))
                        db.execute('INSERT INTO simulated_agency_jobs VALUES(?,?,?,?,?,?)', job)
                        db.execute('UPDATE drafts SET manifest=?,mailing=? WHERE organization=? AND id=?',
                                   (draft['manifest'], draft['mailing'], self.scope, draft_id))
        reopened = Workspace(self.root, real_clock=lambda: 1792972800.)
        self.assertEqual(reopened.propose_followup(self.sid, 'reconciled-acceptance', self.cohort)['hypotheses'], p['hypotheses'])
        self.assertEqual(app.followups.get(self.scope, p['id']), p)

    def test_context_snapshot_identity_version_and_population_counts_bind_the_proposal(self):
        import copy
        from dataclasses import replace
        from acquisition.bootstrap import copy_assets
        from acquisition.creative import validate_copy_assets
        p = self.finalized()
        app = self.w._app(self.w._session(self.sid))
        segment = p['brief']['segments'][0]
        snapshot = app.audiences.get(self.scope, p['snapshot_id'])
        another = replace(snapshot, records=snapshot.records[:-1])
        another_id = app.audiences.put(another)
        hypotheses = {h['segment']: h for h in p['hypotheses']}
        context_ids = app.followup_contexts(self.scope, another, tuple(p['brief']['segments']), p['memory'], hypotheses)
        # This is a fully valid context for another real snapshot, not a broken
        # content hash or a substituted hypothesis.
        other_context = app.memory.get_context(self.scope, context_ids[segment])
        validate_copy_assets(other_context, self.scope)
        with self.assertRaises(Conflict):
            app.followups.put(self.scope, 'other-snapshot', p | {'contexts': context_ids})
        original = app.memory.get_context(self.scope, p['contexts'][segment])
        for field, value in (('snapshot_id', another_id), ('model_version', 'other-model'),
                             ('input_records', original['audience_summary']['input_records'] + 1)):
            with self.subTest(field=field):
                context = copy.deepcopy(original)
                context['audience_summary'][field] = value
                context = copy_assets(self.scope, context)
                validate_copy_assets(context, self.scope)
                cid = app.memory.put_context(self.scope, context)
                with self.assertRaises(Conflict):
                    app.followups.put(self.scope, 'wrong-' + field, p | {'contexts': p['contexts'] | {segment: cid}})
        self.assertEqual(self.w.propose_followup(self.sid, 'correct-snapshot', self.cohort)['contexts'], p['contexts'])

    def test_grounded_source_hook_uses_its_original_context_after_product_evidence_changes(self):
        import copy
        from acquisition.creative.grounding import editorial_read_exchange
        from acquisition.creative import fact_pack_id
        from acquisition.reviews import ReviewPolicy
        model = RevisionModel()
        with patch('acquisition.workspace.openrouter_key', return_value='fake'), patch('acquisition.workspace.OpenRouter', return_value=model):
            source = self.w.create('grounded-hook-source', 'model')
        sid = source['session']['id']
        approved = self.w.action(sid, 'approve', {'request_id': 'hook-review', 'subject_id': source['review']['subject']['id'], 'reason': 'Reviewed original source.'})
        self.w.action(sid, 'handoff', {'request_id': 'hook-accept', 'approval_id': approved['review']['approval']['id']})
        opened = self.w.action(sid, 'open-learning', {'request_id': 'hook-open'})
        self.w.action(sid, 'finalize', {'request_id': 'hook-final'})
        session = self.w._session(sid)
        app = self.w._app(session)
        original_pack = app.reviews.store.evidence(session['organization'])['pack']
        updated_pack = copy.deepcopy(original_pack)
        updated_pack['cta'] = 'Explore the currently reviewed product page.'
        app.reviews.store.activate(session['organization'], 'local-operator', 'new-hook-facts', updated_pack, ReviewPolicy())
        p = self.w.propose_followup(sid, 'grounded-hook-proposal', opened['learning']['cohort']['id'])
        strong = [h for h in p['hypotheses'] if h['evidence_status'] == 'strong']
        self.assertTrue(strong)
        for hypothesis in strong:
            creative = next(c for c in source['review']['manifest']['creatives'] if c['id'] == hypothesis['candidate']['creative_id'])
            hook = hypothesis['candidate']['hook']
            self.assertTrue(creative['opening'].startswith(hook))
            self.assertNotIn(original_pack['cta'], hook)
            context = app.memory.get_context(session['organization'], p['contexts'][hypothesis['segment']])
            wire = canonical(editorial_read_exchange(context, fact_pack_id(updated_pack)))
            self.assertIn(hook, wire)
            self.assertIn(updated_pack['cta'], wire)
            self.assertNotIn(original_pack['cta'], wire)
            self.assertEqual(context['audience_summary']['followup_hypothesis']['candidate']['hook'], hook)
        self.assertEqual(len(model.copy.requests), 6)

    def test_complete_zero_response_cohort_remains_weak_in_real_sqlite(self):
        self.accept()
        opened = self.w.action(self.sid, 'open-learning', {'request_id': 'open'})
        session = self.w._session(self.sid)
        scope = session['organization']
        app = self.w._app(session)
        cohort = app.learning.source.accepted(scope, session['case_id'])
        session['clock'] = cohort['window_end']
        self.w._save(session)
        app = self.w._app(session)
        rows = [member | {'response': False, 'observed_at': cohort['window_end']} for member in cohort['members']]
        app.learning.store.ingest(scope, 'local-operator', 'all-zero', cohort['id'],
            {'schema': 'synthetic-outcomes/v1', 'mode': 'SYNTHETIC_ONLY', 'cohort_id': cohort['id'], 'outcomes': rows})
        app.learning.store.finalize(scope, 'local-operator', 'zero-final', cohort['id'], cohort['window_end'])
        p = self.w.propose_followup(self.sid, 'zero-hypothesis', opened['learning']['cohort']['id'])
        for hypothesis in p['hypotheses']:
            self.assertEqual(hypothesis['evidence_status'], 'weak')
            self.assertIsNone(hypothesis['candidate'])
            self.assertTrue(all(g['successes'] == 0 for g in hypothesis['evidence']['groups']))
            from acquisition.creative import GroundedCopyAgent
            context = app.memory.get_context(scope, p['contexts'][hypothesis['segment']])
            _, _, messages, _ = GroundedCopyAgent.request(context)
            self.assertIn('without assuming a preferred source framing', json.loads(messages[1]['content'])['goal'])
        with app.tasks.database.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM model_calls').fetchone()[0], 0)

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
