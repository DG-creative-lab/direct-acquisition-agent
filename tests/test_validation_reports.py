"""Readiness evidence stays exact and never becomes execution authority."""
import copy
import json
import unittest
from unittest.mock import patch
from acquisition.bootstrap import build
from acquisition.contracts import Conflict, digest
from acquisition.reasoning import ModelConfig
from acquisition.reviews import validation_report
import test_reviews as review_tests
from test_model_copy import FakeModel


class ValidationReportTests(unittest.TestCase):
    setUp = review_tests.ReviewTests.setUp
    approve = review_tests.ReviewTests.approve
    handoff = review_tests.ReviewTests.handoff
    mailed_business = review_tests.ReviewTests.mailed_business
    suppress = review_tests.ReviewTests.suppress

    def report(self):
        return self.store.view('one',self.case)['validation_report']

    def test_fixture_report_is_exact_read_only_and_explicit_about_unmeasured_work(self):
        report=self.report()
        self.assertEqual(report['subject_id'],self.subject)
        self.assertEqual(report['authority'],'none')
        self.assertTrue(report['review_ready'])
        self.assertEqual(report['id'],'validation_'+digest({k:v for k,v in report.items() if k!='id'}))
        checks={c['id']:c for c in report['checks']}
        self.assertEqual(sum(c['required'] for c in checks.values()),7)
        self.assertTrue(all(c['status']=='passed' for c in checks.values() if c['required']))
        self.assertEqual(checks['semantic_screen']['status'],'not_evaluated')
        self.assertEqual(checks['editorial_judgment']['status'],'not_evaluated')
        self.assertEqual(checks['real_performance']['status'],'unknown')
        with self.store.database.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM review_decisions').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM simulated_agency_jobs').fetchone()[0],0)

    def test_passed_snapshot_cannot_authorize_after_suppression_and_history_is_unchanged(self):
        report=copy.deepcopy(self.report()); approval=self.approve()
        self.suppress()
        current=self.report()
        self.assertFalse(current['review_ready'])
        self.assertGreater(current['basis']['audience_epoch'],report['basis']['audience_epoch'])
        checks={c['id']:c for c in current['checks']}
        self.assertEqual(checks['current_epochs']['status'],'failed')
        self.assertEqual(checks['population_budget']['status'],'failed')
        self.assertEqual(report['checks'][0]['status'],'passed')
        with self.assertRaises(Conflict):self.handoff(approval)

    def test_expired_evidence_blocks_readiness_and_new_approval(self):
        self.now=1795564800. # 25 November, outside the recorded review window.
        report=self.report()
        self.assertFalse(report['review_ready'])
        self.assertEqual(next(c['status'] for c in report['checks'] if c['id']=='product_evidence'),'failed')
        with self.assertRaises(ValueError):self.approve()

    def test_unavailable_validator_is_unknown_not_passed_and_recovery_rechecks(self):
        with patch('acquisition.adapters.sqlite.reviews.validate_population',side_effect=RuntimeError('private diagnostic')):
            report=self.report()
        self.assertFalse(report['review_ready'])
        check=next(c for c in report['checks'] if c['id']=='population_budget')
        self.assertEqual(check['status'],'unknown')
        self.assertNotIn('private diagnostic',json.dumps(report))
        self.assertTrue(self.report()['review_ready'])

    def test_gate_rejects_missing_downgraded_unknown_and_not_evaluated_required_checks(self):
        report=self.report(); proposal=self.store.view('one',self.case)['subject']; authority=self.store.evidence('one')
        for status in ('failed','unknown','not_evaluated'):
            checks=copy.deepcopy(report['checks']); checks[0]['status']=status
            self.assertFalse(validation_report(proposal,authority,checks,{},self.now,report['brief'])['review_ready'])
        for mutation in ('missing','optional'):
            checks=copy.deepcopy(report['checks'])
            if mutation=='missing':checks.pop(0)
            else:checks[0]['required']=False
            with self.assertRaises(ValueError):validation_report(proposal,authority,checks,{},self.now,report['brief'])

    def test_grounded_model_report_records_exact_context_and_semantic_screen(self):
        app=build(self.path,clock=lambda:self.now,gateway=FakeModel(),model_config=ModelConfig('test/model',max_calls=10))
        run=app.start_model('one','model-report',size=100)
        app.worker.drain('one',run_id=run)
        case=app.reviews.store.open_case('one',run,'operator')
        report=app.reviews.store.view('one',case['case_id'])['validation_report']
        self.assertTrue(report['review_ready'])
        self.assertEqual(next(c['status'] for c in report['checks'] if c['id']=='semantic_screen'),'passed')
        self.assertEqual(len(report['reasoning_assets']),2)
        self.assertTrue(all(a['asset_id'] and a['source_ids'] and a['skill_ids'] for a in report['reasoning_assets']))

    def test_report_survives_restart_as_a_new_observation_without_any_decision(self):
        first=self.report()
        reopened=build(self.path,clock=lambda:self.now+1)
        second=reopened.reviews.store.view('one',self.case)['validation_report']
        self.assertNotEqual(first['id'],second['id'])
        self.assertEqual(first['subject_id'],second['subject_id'])
        self.assertEqual(first['checks'],second['checks'])
        self.assertEqual(first['basis'],second['basis'])
        self.assertIsNone(reopened.reviews.store.view('one',self.case)['approval'])

    def test_conversation_edit_blocks_current_progress_and_report_without_changing_old_subject(self):
        from acquisition.workspace import Workspace
        from acquisition.conversations import FIXTURE_MESSAGE
        w=Workspace(self.root/'chat',real_clock=lambda:1792972800.)
        c=w.create_conversation('chat','Validation')['id']
        w.message_conversation(c,'m',0,FIXTURE_MESSAGE)
        w.start_preparation(c,'p',1,True,False)
        for _ in range(6):w.advance_preparations()
        view=w.conversation(c);sid=view['campaigns'][0]['session_id']
        old=w.view(sid)['review']['validation_report']
        self.assertEqual(view['preparations'][0]['status'],'review_ready')
        w.message_conversation(c,'edit',1,'Use £300 instead.')
        current=w.view(sid)['review']['validation_report']
        self.assertFalse(current['review_ready'])
        self.assertEqual(current['subject_id'],old['subject_id'])
        self.assertEqual(w.conversation(c)['preparations'][0]['status'],'blocked')
