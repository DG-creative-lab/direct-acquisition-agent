"""Human-reviewed intake selections. Review records never verify product claims."""

from dataclasses import asdict, dataclass
import math

from acquisition.contracts import canonical, digest
from acquisition.creative import draft_text
from .intake import intake_identity, intake_revision


PREPARATION_CONTEXT_SCHEMA = 'reviewed-preparation-context/v1'
PREPARATION_POLICY = 'reviewed-intake/v1'


def preparation_readiness(source):
    company, brief = source['company']['draft'], source['brief']['draft']
    missing = []
    for key, label in (('objective', 'campaign objective'), ('audience', 'audience requirements'),
                       ('country', 'country or market'), ('currency', 'currency')):
        if not brief[key]:
            missing.append('Add the ' + label + ' to the saved brief.')
    if not company['company_name'] or not (company['description'] or company['product_name']):
        missing.append('Save a company name and a product name or business description.')
    if brief['budget_minor'] is None or brief['budget_minor'] <= 0:
        missing.append('Save a positive budget in the selected currency minor units.')
    if not brief['channels']:
        missing.append('Select at least one requested channel in the saved brief.')
    unsupported = []
    if brief['country'] and brief['country'].casefold() not in {'uk', 'gb', 'united kingdom'}:
        unsupported.append('The installed campaign capabilities do not support the requested market. The request was preserved.')
    if brief['currency'] and brief['currency'].upper() != 'GBP':
        unsupported.append('The installed campaign capabilities do not support the requested currency. The request was preserved.')
    channels = {'email', 'direct_mail', 'direct mail', 'postal', 'human_call', 'human call', 'call'}
    if any(channel.casefold() not in channels for channel in brief['channels']):
        unsupported.append('An explicitly requested channel is outside the installed capability catalogue. It was not replaced.')
    return {'missing': missing, 'unsupported': unsupported,
            'execution_blockers': ['Company claims are unverified; a reviewed product evidence pack is required before campaign copy generation.',
                                   'This result is planning only. Campaign preparation and approval are separate.']}



@dataclass(frozen=True)
class PreparationReview:
    brief_id: str
    brief_revision: int
    preview_id: str
    expected_context_revision: int
    selected_claim_ids: tuple[str, ...]
    include_description: bool
    include_cta: bool
    review_days: int
    review_note: str
    issues: tuple[str, ...] = ()
    confirmed: bool = False

    def __post_init__(self):
        for value in (self.brief_id, self.preview_id):intake_identity(value)
        intake_revision(self.brief_revision, positive=True)
        intake_revision(self.expected_context_revision)
        if (type(self.selected_claim_ids) is not tuple or len(self.selected_claim_ids) > 20
                or any(type(value) is not str for value in self.selected_claim_ids)
                or len(set(self.selected_claim_ids)) != len(self.selected_claim_ids)):
            raise ValueError('Select distinct claim identities from the exact preview')
        for value in self.selected_claim_ids:intake_identity(value)
        if any(type(value) is not bool for value in (self.include_description, self.include_cta, self.confirmed)):
            raise ValueError('Use explicit preparation selections and confirmation')
        if not self.confirmed:raise ValueError('Confirm the exact displayed preparation inputs')
        if type(self.review_days) is not int or not 1 <= self.review_days <= 30:
            raise ValueError('Review validity must be between one and thirty days')
        draft_text(self.review_note, 1000)
        if not self.review_note:raise ValueError('Record a reason for this input review')
        if type(self.issues) is not tuple or len(self.issues) > 8:
            raise ValueError('Record at most eight unresolved questions')
        for value in self.issues:
            draft_text(value, 1000)
            if not value:raise ValueError('An unresolved question cannot be empty')


def context_time(now):
    if type(now) not in (int, float) or not math.isfinite(now) or not 0 <= now < 253399708800:
        raise ValueError('Use a finite preparation review timestamp')


def preparation_preview(company, brief, store_id, company_head, context_revision):
    """Reconstruct every selectable value from authoritative saved source wording."""
    intake_revision(company_head, positive=True)
    intake_revision(context_revision)
    if (company['organization'] != brief['organization']
            or company_head < company['revision']
            or (company['id'], company['revision']) !=
               (brief['draft']['company_id'], brief['draft']['company_revision'])):
        raise ValueError('Preparation sources must share organization and exact company revision')
    source = {'schema':'preparation-preview/v1', 'policy':PREPARATION_POLICY,
              'organization':brief['organization'], 'store_id':store_id,
              'company':company, 'brief':brief, 'company_head_revision':company_head,
              'context_revision':context_revision,
              'claims':[{'id':'claim_'+digest({'company_id':company['id'], 'revision':company['revision'],
                         'position':index, 'claim':claim}), **claim}
                        for index,claim in enumerate(company['draft']['claims'])],
              'verification':'user_supplied_unverified', 'authority':'none'}
    return source | {'id':'preparation_preview_'+digest(source)}


def reviewed_preparation(preview, review, actor, request_id, now):
    context_time(now)
    if (review.preview_id != preview['id'] or review.brief_id != preview['brief']['id']
            or review.brief_revision != preview['brief']['revision']
            or review.expected_context_revision != preview['context_revision']):
        raise ValueError('Review the current exact preparation preview before confirming')
    claims = {claim['id']:claim for claim in preview['claims']}
    if not set(review.selected_claim_ids) <= set(claims):
        raise ValueError('Selected claims differ from the displayed saved company version')
    company = preview['company']['draft']
    if review.include_description and not company['description']:
        raise ValueError('There is no saved description to select')
    if review.include_cta and not company['official_cta']:
        raise ValueError('There is no saved call to action to select')
    selected = {'company_name':company['company_name'], 'product_name':company['product_name'],
                'description':company['description'] if review.include_description else None,
                'claims':[claims[key] for key in review.selected_claim_ids],
                'cta':{'wording':company['official_cta'], 'url':company['cta_url']}
                      if review.include_cta else None,
                'company_reference_urls':company['source_urls']}
    missing = []
    for key in ('objective','audience','country','currency'):
        if not preview['brief']['draft'][key]:missing.append('Missing campaign ' + key + '.')
    if not company['company_name']:missing.append('Missing company name.')
    if not (selected['description'] or selected['claims']):missing.append('No company description or claims selected.')
    if preview['brief']['draft']['budget_minor'] is None:missing.append('No campaign budget supplied.')
    if not preview['brief']['draft']['channels']:missing.append('No campaign channel supplied.')
    if selected['description'] and not company['source_urls']:
        missing.append('The selected description has no company evidence references.')
    for claim in selected['claims']:
        if not claim['source_urls']:missing.append('Selected claim ' + claim['id'] + ' has no evidence references.')
    if selected['cta'] is None or not selected['cta']['url']:
        missing.append('No selected call to action with a reference URL.')
    readiness = preparation_readiness(preview)
    references = sorted(set(company['source_urls'] + [url for claim in selected['claims'] for url in claim['source_urls']]
                            + ([selected['cta']['url']] if selected['cta'] and selected['cta']['url'] else [])))
    payload = {'schema':PREPARATION_CONTEXT_SCHEMA, 'policy':PREPARATION_POLICY,
               'organization':preview['organization'], 'store_id':preview['store_id'],
               'id':'preparation_context_'+digest({'organization':preview['organization'], 'brief_id':review.brief_id}),
               'revision':review.expected_context_revision + 1, 'request_id':request_id, 'reviewer':actor,
               'reviewed_at':now, 'review_expires_at':now + review.review_days * 86400,
               'source':preview, 'selection':asdict(review), 'selected_inputs':selected,
               'requirements':preview['brief']['draft'],
               'references':[{'id':'reference_'+digest({'preview_id':preview['id'],'url':url}), 'url':url,
                              'verification':'reference_only_not_fetched', 'checked_on':None} for url in references],
               'missing_evidence':missing, 'requirements_readiness':readiness, 'reviewer_questions':list(review.issues),
               'review_status':'recorded_with_questions' if missing or review.issues or readiness['missing'] or readiness['unsupported'] else 'recorded',
               'verification':'user_supplied_unverified', 'approval':'not_granted',
               'generation':'unavailable', 'authority':'none'}
    if len(canonical(payload).encode()) > 512_000:
        raise ValueError('Selected preparation context exceeds the bounded record size')
    return payload | {'fingerprint':digest(payload)}
