"""Evidence-bound next-experiment interpretations, with no execution authority."""
from acquisition.contracts import Conflict, digest
from .outcomes import posterior
from .recommendations import recommend, COMPARISON_POLICY


AUTHORITY = 'ADVISORY_ONLY_NO_COPY_OR_APPROVAL_INHERITANCE'
POLICY = {**COMPARISON_POLICY, 'version': 'followup-hypotheses/v1', 'comparison': COMPARISON_POLICY['version']}
LIMITS = ('Synthetic observations are not customer evidence. The prior and comparison thresholds are illustrative. '
          'A new creative starts with zero observed outcomes and requires its own review and approval.')


def followup_hypotheses(organization, source, creatives, segments):
    """Interpret one complete mature source cohort, never pooled outcome rates."""
    cohort, finalization, groups = source['cohort'], source['finalization'], source['beliefs']
    if (source['status'] != 'finalized' or cohort['organization'] != organization
            or cohort['schema'] != 'synthetic-response-cohort/v1'
            or cohort['metric'] != 'synthetic_response_within_28_days'
            or cohort['mode'] != 'SYNTHETIC_ONLY' or not finalization
            or finalization['mode'] != 'SYNTHETIC_ONLY' or finalization['cohort_id'] != cohort['id']
            or finalization['complete_through'] != cohort['window_end']
            or not cohort['window_end'] <= finalization['finalized_at'] <= source['as_of']
            or source['missing'] != 0 or source['received'] != source['enrolled']
            or source['received'] != finalization['observations']
            or digest(groups) != finalization['beliefs_digest']):
        raise Conflict('A follow-up hypothesis requires complete mature scoped source evidence')
    if (type(segments) is not tuple or not segments or len(set(segments)) != len(segments)
            or set(segments) - {'inventory', 'contractors'}):
        raise ValueError('Select unique supported audiences for the hypothesis')
    references = {(c['segment'], c['arm']): c for c in creatives}
    seen = set()
    for group in groups:
        key = group['segment'], group['arm']
        if key in seen or group['segment'] not in {'inventory', 'contractors'} or group['arm'] not in {'A', 'B', 'no_mail'}:
            raise Conflict('Source learning has conflicting comparison groups')
        seen.add(key)
        if (group != posterior(group['segment'], group['arm'], group['creative_id'], group['trials'], group['successes'])
                or (group['arm'] == 'no_mail' and group['creative_id'] != '')
                or (group['arm'] != 'no_mail' and (key not in references or references[key]['id'] != group['creative_id']))):
            raise Conflict('Source learning differs from its counted outcomes or original creatives')
    if (sum(g['trials'] for g in groups) != finalization['observations']
            or sum(g['successes'] for g in groups) != finalization['successes']):
        raise Conflict('Source learning counts do not reconcile with finalization')
    comparisons = {r['segment']: r for r in recommend(cohort['id'], groups)}
    result = []
    for segment in segments:
        observed = [g for g in groups if g['segment'] == segment and g['trials'] > 0]
        comparison = comparisons[segment]
        complete = {g['arm'] for g in observed} == {'A', 'B', 'no_mail'}
        status = 'absent' if not complete else 'strong' if comparison['action'] == 'propose_next_experiment' else 'weak'
        candidate = None
        if status == 'strong':
            arm = comparison['candidate_arm']
            creative = references[(segment, arm)]
            if type(creative.get('hook')) is not str or not creative['hook'].strip():
                raise Conflict('A strong framing hypothesis requires the original source hook')
            candidate = {'arm': arm, 'creative_id': creative['id'], 'headline': creative.get('headline', ''),
                         'hook': creative['hook'], 'framing_note': creative.get('hypothesis', ''),
                         'role': 'historical_framing_not_product_evidence'}
            hypothesis = (f'Test whether new hooks informed by source variant {arm} can reproduce its '
                          'source-cohort response advantage on an independent synthetic population, '
                          'against a contrasting new hook and a no-mail control. Earlier lift may not repeat.')
        elif status == 'weak':
            hypothesis = ('Compare two contrasting new hooks and a no-mail control on an independent synthetic population. '
                          'The source comparison does not support carrying forward a preferred framing.')
        else:
            hypothesis = ('Explore two contrasting new hooks and a no-mail control on an independent synthetic population. '
                          'No complete relevant A/B/control comparison is available, so no source advantage is assumed.')
        evidence = {'source_cohort': cohort['id'], 'source_draft': cohort['draft_id'], 'metric': cohort['metric'],
                    'finalization': {k: finalization[k] for k in ('outcome_digest', 'beliefs_digest', 'finalized_at')},
                    'groups': observed, 'comparison': comparison if complete else None}
        result.append({'schema': 'followup-hypothesis/v1', 'segment': segment, 'evidence_status': status,
                       'hypothesis': hypothesis, 'candidate': candidate, 'evidence': evidence,
                       'evidence_id': 'hypothesis_evidence_' + digest(evidence), 'policy': dict(POLICY),
                       'limitations': LIMITS, 'mode': 'SYNTHETIC_ONLY', 'authority': AUTHORITY})
    return result
