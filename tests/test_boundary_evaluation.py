"""A green flag cannot substitute for complete, attributable recovery evidence."""
from contextlib import redirect_stdout
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import evaluate_boundary_journey as evaluation


def complete_rows():
    observed = {
        'compatibility-model-journey': {'passed': True, 'outcome_category': 'accepted', 'fake_provider_calls': 7, 'recorded_model_calls': 7,
            'journey': {'replay_added_calls': 0, 'inspection_added_calls': 0, 'confirmed_amendment_budget_pence': 51200}},
        'verified-commit-rebuild-replay': {'population': 77, 'received': 77, 'model_calls': 0,
            'projection_preserved_authority': True, 'authoritative_sha256': 'a'*64,
            'fresh_process_replay': {'pid': 2, 'handoff_replayed': True, 'finalize_replayed': True, 'changed_input_rejected': True}},
        'uncertain-restart': {'passed': True, 'fake_provider_calls': 1, 'replay_added_calls': 0, 'used': 1,
            'authoritative_unchanged': True, 'fresh_process_replay': {'pid': 2, 'used': 1, 'campaigns': 0}},
        'profile-replay': {'profiles': [{'profile': key, 'draft_id': key+'-draft', 'manifest_sha256':'a'*64, 'counts': {'input':100,'excluded':24,'eligible_unselected':0,'holdout':6,'mailed':70},
            'cost_pence':5950,'approval':'not_granted','execution':'not_performed'} for key in ('fielddesk','iwoca')],
            'model_calls':0, 'changed_input_rejected':True},
        'engagement-replay': {'counts':{'engagement_simulations':1,'engagement_enrollments':2,'engagement_steps':6,'engagement_dispatches':2},
            'same_receipt':True,'fresh_process_pid':2},
    }
    return [{'id':key,'exit_code':0,'network_attempts':0,'artifacts':{'proof.json':{'sha256':'a'*64,'bytes':1}},
             'observed': value | {'process_pid':1}} for key,value in observed.items()]


class BoundaryEvidenceTests(unittest.TestCase):
    def test_missing_duplicate_malformed_and_success_only_evidence_cannot_pass(self):
        rows=complete_rows(); self.assertEqual(evaluation.grade(rows), [])
        for changed in ([], rows[:-1], rows+[rows[0]], [rows[0]]*len(rows),
                        [{'id':r['id'],'passed':True} for r in rows], [None]*len(rows)):
            with self.subTest(changed=changed):self.assertTrue(evaluation.grade(changed))
        for field,value in [('exit_code',False),('network_attempts',False),('artifacts',{})]:
            changed=copy.deepcopy(rows);changed[0][field]=value
            self.assertTrue(evaluation.grade(changed),field)
        for value in (None, [], True, 'complete'):
            changed=copy.deepcopy(rows);changed[0]['observed']=value
            self.assertTrue(evaluation.grade(changed))

    def test_counted_effects_original_identity_and_approval_are_independent_oracles(self):
        rows=complete_rows()
        for identity, field, value in (
            ('verified-commit-rebuild-replay','received',76),
            ('verified-commit-rebuild-replay','model_calls',1),
            ('verified-commit-rebuild-replay','projection_preserved_authority',False),
            ('uncertain-restart','fake_provider_calls',2),
            ('uncertain-restart','used',0),
            ('engagement-replay','same_receipt',False),
        ):
            changed=copy.deepcopy(rows);next(r for r in changed if r['id']==identity)['observed'][field]=value
            self.assertTrue(evaluation.grade(changed), (identity,field))
        for field,value in [('engagement_simulations',2),('engagement_dispatches',3),('engagement_steps',5)]:
            changed=copy.deepcopy(rows);changed[-1]['observed']['counts'][field]=value
            self.assertTrue(evaluation.grade(changed),field)
        changed=copy.deepcopy(rows);changed[1]['observed']['fresh_process_replay']['pid']=1
        self.assertTrue(evaluation.grade(changed))
        for field in ('approval','execution','counts'):
            changed=copy.deepcopy(rows);changed[3]['observed']['profiles'][0][field]='forged'
            self.assertTrue(evaluation.grade(changed))

    def test_source_or_historical_drift_invalidates_otherwise_passing_cases(self):
        for source_drift,history_drift in ((False,False),(True,False),(False,True)):
            with self.subTest(source=source_drift,history=history_drift), tempfile.TemporaryDirectory() as folder:
                directory=Path(folder);before={'head_commit':'commit','files_sha256':'original','worktree_dirty':False,'files':{}}
                after=before|({'files_sha256':'changed'} if source_drift else {})
                history={'old.json':{'expected':'original','actual':'original'}}
                changed_history={'old.json':{'expected':'original','actual':'changed'}} if history_drift else history
                observed=iter(row['observed'] for row in complete_rows())
                with patch.object(evaluation,'source_state',side_effect=[before,after]), \
                     patch.object(evaluation,'historical',side_effect=[history,changed_history]), \
                     patch.object(evaluation.subprocess,'run',side_effect=lambda *a,**k: SimpleNamespace(returncode=0,stdout=json.dumps(next(observed)),stderr='')), \
                     patch.object(evaluation,'artifacts',return_value={'proof':{'sha256':'a'*64,'bytes':1}}), redirect_stdout(io.StringIO()):
                    report=evaluation.evaluate(directory)
                self.assertEqual(report['passed'],not(source_drift or history_drift))
                self.assertEqual(report['evaluated_commit'],None if source_drift else 'commit')

    def test_network_attempt_caught_by_a_dependency_remains_counted(self):
        # A second hook prevents real DNS/network activity if the evaluated
        # guard misses an event. Only the evidence guard's RuntimeError is caught.
        operations = (
            ("socket.socket().connect(('127.0.0.1',1))", 'socket.connect'),
            ("socket.getaddrinfo('example.invalid',443)", 'socket.getaddrinfo'),
            ("socket.gethostbyname('example.invalid')", 'socket.gethostbyname'),
            ("socket.gethostbyname_ex('example.invalid')", 'socket.gethostbyname'),
            ("_socket.gethostbyname('example.invalid')", 'socket.gethostbyname'),
            ("_socket.gethostbyname_ex('example.invalid')", 'socket.gethostbyname'),
            ("socket.gethostbyaddr('127.0.0.1')", 'socket.gethostbyaddr'),
            ("socket.getnameinfo(('127.0.0.1',0),0)", 'socket.getnameinfo'),
            ("socket.getfqdn('example.invalid')", 'socket.gethostbyaddr'),
        )
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'sitecustomize.py').write_text(evaluation.NETWORK_GUARD);log=root/'network.jsonl'
            for operation,event in operations:
                for nested in (False,True):
                    with self.subTest(operation=operation,nested=nested):
                        log.unlink(missing_ok=True)
                        payload = ("import socket,_socket,sys\n"
                            "def fallback(event,args):\n"
                            " if event in {'socket.connect','socket.getaddrinfo','socket.gethostbyname','socket.gethostbyaddr','socket.getnameinfo'}:\n"
                            "  raise AssertionError('Operation escaped evidence guard')\n"
                            "sys.addaudithook(fallback)\ntry:\n " + operation + "\nexcept RuntimeError:\n pass")
                        script = ("import subprocess,sys; sys.exit(subprocess.run([sys.executable,'-c',"
                                  + repr(payload) + "],env={'PYTHONPATH':''}).returncode)") if nested else payload
                        run=subprocess.run([sys.executable,'-c',script],
                            env=dict(os.environ,PYTHONPATH=str(root),BOUNDARY_NETWORK_LOG=str(log)),capture_output=True,text=True)
                        self.assertEqual(run.returncode,0,run.stderr)
                        self.assertEqual([json.loads(line) for line in log.read_text().splitlines()],[{'event':event}])
                        rows=complete_rows();rows[0]['network_attempts']=1
                        self.assertTrue(evaluation.grade(rows))

    def test_existing_evidence_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'results.json';path.write_bytes(b'Original evidence')
            with patch.object(sys,'argv',['evaluation','--output-dir',folder]), patch('sys.stderr',io.StringIO()), self.assertRaises(SystemExit) as stopped:
                evaluation.main()
            self.assertEqual(stopped.exception.code,2);self.assertEqual(path.read_bytes(),b'Original evidence')
