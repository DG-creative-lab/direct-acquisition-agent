"""Eligibility is a projection, never permission to spend, approve or send."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from acquisition.contracts import digest
from acquisition.creative import SourceEvidenceReview, selected_grounding_material, grounding_material_issues
from .intake import intake_identity
from .preparation_context import context_time, preparation_readiness


@dataclass(frozen=True)
class GroundedPreparationRequest:
    context_request_id: str
    preview_id: str
    evidence: SourceEvidenceReview
    confirmed_synthetic_preparation: bool

    def __post_init__(self):
        for value in (self.context_request_id, self.preview_id):
            intake_identity(value)
        if type(self.evidence) is not SourceEvidenceReview:
            raise ValueError('Use an explicit source evidence review')
        if self.confirmed_synthetic_preparation is not True:
            raise ValueError('Confirm fixed synthetic framing and synthetic contacts, without model execution')


def grounding_request_from(payload):
    evidence = payload['evidence']
    return GroundedPreparationRequest(**(payload | {'evidence': SourceEvidenceReview(**(
        evidence | {'reference_ids': tuple(evidence['reference_ids'])}))}))


def evaluate_preparation_eligibility(view, now):
    context_time(now)
    context = view['context']
    selected, requirements = context['selected_inputs'], context['requirements']
    facts, references = selected_grounding_material(context)
    readiness = preparation_readiness(context['source'])
    blockers = (list(view['review_required']) + list(context['reviewer_questions']) + readiness['missing']
                + readiness['unsupported'] + grounding_material_issues(context))
    if not selected['company_name'] or not selected['product_name']:
        blockers.append('Save an explicit company and product name, then review those inputs.')
    if not facts:
        blockers.append('Select at least one factual item for preparation.')
    if len(references) > 60:
        blockers.append('This bounded source review supports at most sixty selected references.')
    if any(not f['urls'] for f in facts):
        blockers.append('Every selected description or claim needs a source reference.')
    if not selected['cta'] or not selected['cta']['url']:
        blockers.append('Select the official call to action and its reference URL.')
    if len(requirements['channels']) != 1 or requirements['channels'][0].casefold() not in {'direct_mail', 'direct mail', 'postal'}:
        blockers.append('This preparation capability supports one UK postal channel only. Other requests remain unchanged.')
    if requirements['contact_source'] != 'synthetic':
        blockers.append('Explicitly select synthetic contacts in the saved brief.')
    if requirements['budget_minor'] is not None and requirements['budget_minor'] > 1_000_000:
        blockers.append('The synthetic preparation budget limit is 1000000 GBP minor units.')
    if len(requirements['objective']) > 600 or any(ord(c) < 32 for c in requirements['objective']):
        blockers.append('The profile preparation contract needs a single-line objective of at most 600 characters. Source wording was preserved.')
    today = datetime.fromtimestamp(now, timezone.utc).date()
    payload = {'schema': 'preparation-eligibility/v1', 'context_request_id': view['request_id'],
        'context_fingerprint': context['fingerprint'], 'store_id': context['store_id'],
        'selected_inputs': selected, 'requirements': requirements, 'references': references,
        'required_evidence_review': 'Operator must check official sources and support for every selected factual item, qualification and CTA.',
        'blockers': list(dict.fromkeys(blockers)), 'checked_on': today.isoformat(),
        'settings': {'mode': 'offline_fixture', 'model': None, 'model_calls': 0, 'prompt': None,
            'recipe': 'reviewed-intake-fixture/v1', 'size': min(requirements['max_candidates'] or 100, 100),
            'seed': 42, 'framing': 'fixed_business_questions', 'targeting': 'synthetic_not_matched_to_user_audience'},
        'approval': 'not_granted', 'authority': 'none', 'live_generation': 'unavailable'}
    return payload | {'id': 'eligibility_' + digest(payload)}
