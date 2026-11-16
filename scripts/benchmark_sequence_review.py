"""Measure unchanged sequence-review cases without overlapping verification work.

Run with PYTHONPATH=src:tests python3 -m scripts.benchmark_sequence_review
--output .local/benchmarks/before.json, then repeat against the candidate source.
"""

import argparse
import hashlib
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time
import unittest

from scripts.run_backend_shard import TimingResult

ROOT = Path(__file__).resolve().parents[1]
TARGETS = (
    'test_sequence_reviews.SequenceReviewTests.test_one_approval_covers_both_arms_and_controls_across_restart',
    'test_sequence_reviews.SequenceReviewTests.test_full_readiness_basis_expiry_withholds_outputs_even_when_selected_payloads_remain_valid',
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repetitions', type=int, default=3, choices=range(1, 11))
    args = parser.parse_args()
    samples = []
    for repeat in range(args.repetitions):
        for target in TARGETS:
            loader = unittest.TestLoader()
            suite = loader.loadTestsFromName(target)
            if loader.errors:
                parser.exit(1, '\n'.join(loader.errors))
            start = time.perf_counter()
            result = unittest.TextTestRunner(verbosity=2, resultclass=TimingResult).run(suite)
            elapsed = time.perf_counter() - start
            if not result.wasSuccessful() or len(result.timings) != 1:
                parser.exit(1, 'Benchmark case failed; no successful comparison is recorded.\n')
            samples.append({'repeat':repeat + 1, 'id':target,
                            'case_seconds':result.timings[0]['seconds'], 'suite_seconds':elapsed})
    summary = []
    for target in TARGETS:
        values = [r['case_seconds'] for r in samples if r['id'] == target]
        summary.append({'id':target, 'median_seconds':statistics.median(values),
                        'min_seconds':min(values), 'max_seconds':max(values)})
    hashes = {}
    for relative in ('src/acquisition/audiences/contacts.py',
                     'src/acquisition/adapters/sqlite/sequence_reviews.py',
                     'src/acquisition/adapters/sqlite/sequence_proposals.py',
                     'src/acquisition/adapters/sqlite/contacts.py', 'tests/test_sequence_reviews.py'):
        hashes[relative] = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
    payload = {'python':sys.version, 'platform':platform.platform(),
               'revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
               'source_sha256':hashes, 'samples':samples, 'summary':summary,
               'measurement':'Unprofiled serial runs. Case includes per-case setup/cleanup; suite includes class setup/cleanup.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
