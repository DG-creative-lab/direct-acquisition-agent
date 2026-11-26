"""Explicit operator source review, separate from selecting unverified intake."""

from dataclasses import dataclass
from datetime import date, timedelta
from urllib.parse import urlparse

from acquisition.contracts import digest
from .company_drafts import draft_text
from .grounding_policy import bounded_text, validate_fact_pack
from .profiles import ProductProfile


@dataclass(frozen=True)
class SourceEvidenceReview:
    reference_ids: tuple[str, ...]
    checked_on: str
    review_days: int
    note: str
    confirmed_official_sources: bool
    confirmed_exact_wording: bool

    def __post_init__(self):
        if (type(self.reference_ids) is not tuple or not self.reference_ids
                or any(type(v) is not str for v in self.reference_ids)
                or len(self.reference_ids) > 60 or len(set(self.reference_ids)) != len(self.reference_ids)):
            raise ValueError('Review each distinct required reference')
        if type(self.checked_on) is not str or date.fromisoformat(self.checked_on).isoformat() != self.checked_on:
            raise ValueError('Record the source review date as YYYY-MM-DD')
        if type(self.review_days) is not int or not 1 <= self.review_days <= 30:
            raise ValueError('Source review validity is one to thirty days')
        draft_text(self.note, 1000)
        if not self.note:
            raise ValueError('Record how the sources support the exact selected wording and qualifications')
        if self.confirmed_official_sources is not True or self.confirmed_exact_wording is not True:
            raise ValueError('Explicitly attest source ownership and support for the exact selected wording')


def selected_grounding_material(context):
    """Only selected prose crosses this boundary. Raw company claims never do."""
    selected = context['selected_inputs']
    facts = []
    if selected['description']:
        facts.append({'id': 'description_' + digest(selected['description']), 'copy': selected['description'],
                      'qualification': 'Operator-reviewed company description.',
                      'urls': list(selected['company_reference_urls'])})
    facts.extend({'id': c['id'], 'copy': c['statement'], 'qualification': c['qualification'],
                  'urls': list(c['source_urls'])} for c in selected['claims'])
    urls = {url for f in facts for url in f['urls']}
    cta = selected['cta']
    if cta and cta['url']:
        urls.add(cta['url'])
    references = [r for r in context['references'] if r['url'] in urls]
    return facts, references


def grounding_material_issues(context):
    """Report compatibility blockers without editing saved assertion wording."""
    facts, references = selected_grounding_material(context)
    issues = []
    for f in facts:
        for field in ('copy', 'qualification'):
            try:
                bounded_text(f[field], 300)
            except ValueError:
                issues.append('Selected factual item ' + f['id'] + ' needs bounded wording and an explicit qualification compatible with the grounded copy contract. Source wording was preserved.')
    selected = context['selected_inputs']
    for label, value, maximum in (('company name', selected['company_name'], 600),
            ('product name', selected['product_name'], 600), ('CTA', (selected['cta'] or {}).get('wording', ''), 300)):
        try:
            bounded_text(value, maximum)
        except ValueError:
            issues.append('The selected ' + label + ' is incompatible with the grounded copy contract. Source wording was preserved.')
    for ref in references:
        url = urlparse(ref['url'])
        if (url.scheme != 'https' or not url.hostname or url.netloc != url.hostname
                or url.query or url.fragment or not url.path):
            issues.append('Source ' + ref['id'] + ' needs an exact HTTPS page URL without query or fragment.')
    return list(dict.fromkeys(issues))


def grounded_intake_product(context, review: SourceEvidenceReview, taxonomy, today):
    """An operator attests support; this function performs no fetch or truth check."""
    facts, references = selected_grounding_material(context)
    issues = grounding_material_issues(context)
    if issues:
        raise ValueError('; '.join(issues))
    if set(review.reference_ids) != {r['id'] for r in references}:
        raise ValueError('Source review must cover exactly the required selected references')
    checked = date.fromisoformat(review.checked_on)
    if checked != today:
        raise ValueError('New preparation requires a source review dated today')
    if not facts or any(not f['urls'] for f in facts):
        raise ValueError('Every selected factual item needs a reviewed source')
    selected = context['selected_inputs']
    if not selected['cta'] or not selected['cta']['url']:
        raise ValueError('Select a sourced official call to action')
    sources = [{'id': r['id'], 'url': r['url'], 'checked_on': review.checked_on} for r in references]
    by_url = {r['url']: r['id'] for r in references}
    pack = {'version': 'intake-grounding/v1', 'product': selected['product_name'],
            'verification': 'operator_attested_sources_not_independently_verified',
            'checked_on': review.checked_on, 'review_by': (checked + timedelta(days=review.review_days)).isoformat(),
            'sources': sources,
            'facts': [{'id': f['id'], 'copy': f['copy'], 'qualification': f['qualification'],
                       'source_id': by_url[f['urls'][0]], 'source_ids': [by_url[u] for u in f['urls']]}
                      for f in facts],
            'required_qualification': 'Synthetic demonstration. Not approved for use.',
            'cta': selected['cta']['wording']}
    key = 'intake-' + context['fingerprint'][:32]
    profile = ProductProfile(key, 'v1', selected['product_name'], key, 'v1', selected['company_name'],
        'Fixed synthetic framing for inspection.', 'Synthetic demonstration. No authority to print or send.',
        tuple(r['url'] for r in references), digest(pack), taxonomy.id,
        (('businesses', ('business', 'project', 'supplier')),), ('product',),
        'synthetic_fixture' if all(urlparse(r['url']).hostname.endswith('.invalid') for r in references) else 'public_reviewed')
    validate_fact_pack(pack, today, profile=profile)
    for f in facts:
        bounded_text(f['copy'], 300)
    return profile, pack
