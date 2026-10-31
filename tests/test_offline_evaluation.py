"""The evaluation report must reflect real assertions and fail closed."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('offline_evaluation', Path(__file__).resolve().parents[1] / 'scripts/evaluate_offline.py')
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)


class OfflineEvaluationTests(unittest.TestCase):
    def test_complete_offline_journey_produces_inspectable_evidence(self):
        with tempfile.TemporaryDirectory() as output:
            self.assertEqual(evaluation.evaluate(Path(output)), 0)
            report_path = next(Path(output).glob('run-*/report.json'))
            report = json.loads(report_path.read_text())
            self.assertTrue(report['passed'])
            self.assertEqual(len(report['checks']), 37)
            self.assertTrue(all(c['passed'] for c in report['checks']))
            self.assertTrue((report_path.parent / 'followup-campaign.json').is_file())
            child = json.loads((report_path.parent / 'followup-campaign.json').read_text())
            self.assertTrue(child['review']['approval_valid'])
            self.assertEqual(child['review']['approval']['subject_id'], child['review']['subject']['id'])

    def test_false_success_is_reported_as_failure(self):
        with tempfile.TemporaryDirectory() as output:
            with patch.object(evaluation, 'validate_result', return_value={'approval':'not_granted'}):
                self.assertEqual(evaluation.evaluate(Path(output)), 1)
            report = json.loads(next(Path(output).glob('run-*/report.json')).read_text())
            self.assertFalse(report['passed'])
            self.assertEqual(report['checks'][-1], {'name':'brief_missing_total','passed':False})

    def test_broken_child_approval_cannot_pass_evaluation(self):
        original = evaluation.Workspace.action
        for failure in ('rejected', 'invalid_authority'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as output:
                def broken(workspace, identity, action, payload):
                    child_approval = action == 'approve' and workspace._session(identity).get('followup_id')
                    if child_approval and failure == 'rejected':
                        raise evaluation.Conflict('Child approval unavailable')
                    result = original(workspace, identity, action, payload)
                    if child_approval:
                        result['review']['approval_valid'] = False
                    return result
                with patch.object(evaluation.Workspace, 'action', broken):
                    self.assertEqual(evaluation.evaluate(Path(output)), 1)
                report = json.loads(next(Path(output).glob('run-*/report.json')).read_text())
                self.assertFalse(report['passed'])
                self.assertIn({'name':'followup_cannot_inherit_approval','passed':True}, report['checks'])
                if failure == 'invalid_authority':
                    self.assertEqual(report['checks'][-1], {'name':'followup_current_approval_authority','passed':False})
