"""Held-out count patterns, independent of the scripted demonstration labels."""
import copy
import unittest

from acquisition.contracts import Conflict, digest
from acquisition.learning import followup_hypotheses, posterior


SEGMENTS = ('inventory', 'contractors')
CREATIVES = [{'segment': segment, 'arm': arm, 'id': segment + '-' + arm,
              'headline': 'Source ' + segment + ' ' + arm, 'hypothesis': 'Historical framing note.',
              'hook': 'The original ' + segment + ' hook for ' + arm + '.'}
             for segment in SEGMENTS for arm in ('A', 'B')]


def groups_for(segment, a, b, control, trials=200):
    return [posterior(segment, arm, '' if arm == 'no_mail' else segment + '-' + arm, trials, successes)
            for arm, successes in (('A', a), ('B', b), ('no_mail', control))]


def source_for(groups, cohort_id='source-cohort'):
    groups = sorted(groups, key=lambda g: (g['segment'], g['arm']))
    n, s = sum(g['trials'] for g in groups), sum(g['successes'] for g in groups)
    return {'cohort': {'id': cohort_id, 'organization': 'one', 'draft_id': 'source-draft',
                       'schema': 'synthetic-response-cohort/v1', 'metric': 'synthetic_response_within_28_days',
                       'case_id': 'source-case', 'mode': 'SYNTHETIC_ONLY', 'window_end': 100},
            'finalization': {'cohort_id': cohort_id, 'mode': 'SYNTHETIC_ONLY', 'complete_through': 100,
                             'finalized_at': 100, 'observations': n, 'successes': s,
                             'beliefs_digest': digest(groups), 'outcome_digest': 'recorded-outcomes'},
            'as_of': 100, 'status': 'finalized', 'missing': 0, 'received': n, 'enrolled': n, 'beliefs': groups}


class FollowupHypothesisTests(unittest.TestCase):
    def test_strong_evidence_tracks_the_actual_leading_arm_per_audience_and_preserves_uncertainty(self):
        source = source_for(groups_for('inventory', 65, 4, 3) + groups_for('contractors', 4, 65, 3))
        result = followup_hypotheses('one', source, CREATIVES, SEGMENTS)
        self.assertEqual(result, followup_hypotheses('one', source, CREATIVES, SEGMENTS))
        self.assertEqual([h['evidence_status'] for h in result], ['strong', 'strong'])
        self.assertEqual([h['candidate']['arm'] for h in result], ['A', 'B'])
        for hypothesis in result:
            self.assertEqual(hypothesis['candidate']['creative_id'], hypothesis['segment'] + '-' + hypothesis['candidate']['arm'])
            self.assertEqual(hypothesis['candidate']['hook'], next(c['hook'] for c in CREATIVES
                             if c['id'] == hypothesis['candidate']['creative_id']))
            self.assertEqual(sum(g['trials'] for g in hypothesis['evidence']['groups']), 600)
            self.assertEqual(hypothesis['evidence']['source_cohort'], 'source-cohort')
            self.assertGreater(hypothesis['evidence']['comparison']['lift_interval_90'][0], 0)
            self.assertIn('Earlier lift may not repeat', hypothesis['hypothesis'])
            self.assertIn('zero observed outcomes', hypothesis['limitations'])
            self.assertEqual(hypothesis['authority'], 'ADVISORY_ONLY_NO_COPY_OR_APPROVAL_INHERITANCE')

    def test_weak_evidence_cannot_promote_a_variant_despite_small_extreme_or_large_negative_results(self):
        for segment in SEGMENTS:
            for groups in (groups_for(segment, 9, 0, 0, trials=9),
                           groups_for(segment, 50, 1, 100), groups_for(segment, 10, 10, 10)):
                with self.subTest(segment=segment, groups=groups):
                    source = source_for(groups)
                    # Neither a forged recommendation nor arbitrary pooled
                    # metadata can turn within-cohort uncertainty into support.
                    source['recommendations'] = [{'action': 'propose_next_experiment', 'candidate_arm': 'A'}]
                    source['pooled_memory'] = {'trials': 10_000_000, 'successes': 10_000_000}
                    h, = followup_hypotheses('one', source, CREATIVES, (segment,))
                    self.assertEqual(h['evidence_status'], 'weak')
                    self.assertIsNone(h['candidate'])
                    self.assertIn('does not support', h['hypothesis'])
                    self.assertIsNotNone(h['evidence']['comparison'])

    def test_absent_comparison_preserves_unknown_strata_and_never_counts_priors_as_observations(self):
        for segment in SEGMENTS:
            other = next(s for s in SEGMENTS if s != segment)
            for relevant in ([], groups_for(segment, 3, 2, 0)[:2], groups_for(segment, 0, 0, 0, trials=0)):
                with self.subTest(segment=segment, relevant=relevant):
                    source = source_for(groups_for(other, 65, 4, 3) + relevant)
                    h, = followup_hypotheses('one', source, CREATIVES, (segment,))
                    self.assertEqual(h['evidence_status'], 'absent')
                    self.assertIsNone(h['candidate'])
                    self.assertIsNone(h['evidence']['comparison'])
                    self.assertNotIn('no_mail', [g['arm'] for g in h['evidence']['groups']])
                    self.assertIn('no source advantage is assumed', h['hypothesis'])

    def test_conflicting_missing_future_or_foreign_source_evidence_blocks_interpretation(self):
        source = source_for(groups_for('inventory', 65, 4, 3))
        mutations = [
            lambda s: s.update(status='observing'),
            lambda s: s.update(missing=1),
            lambda s: s.update(as_of=99),
            lambda s: s['cohort'].update(organization='other'),
            lambda s: s['cohort'].update(metric='profit'),
            lambda s: s['cohort'].update(schema='synthetic-response-cohort/v2'),
            lambda s: s['finalization'].update(cohort_id='other-cohort'),
            lambda s: s['finalization'].update(observations=601),
            lambda s: s['beliefs'][0].update(successes=99),
        ]
        for change in mutations:
            altered = copy.deepcopy(source)
            change(altered)
            with self.subTest(altered=altered), self.assertRaises(Conflict):
                followup_hypotheses('one', altered, CREATIVES, ('inventory',))
        wrong = copy.deepcopy(CREATIVES)
        wrong[0]['id'] = 'substituted-creative'
        with self.assertRaises(Conflict): followup_hypotheses('one', source, wrong, ('inventory',))

    def test_probabilities_cannot_be_substituted_for_counted_posterior_parameters(self):
        source = source_for(groups_for('inventory', 10, 10, 10))
        source['beliefs'][0]['mean'] = .99
        source['finalization']['beliefs_digest'] = digest(source['beliefs'])
        with self.assertRaises(Conflict): followup_hypotheses('one', source, CREATIVES, ('inventory',))
