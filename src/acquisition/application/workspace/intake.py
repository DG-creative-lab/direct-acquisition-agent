"""Local intake boundary. Scope comes from the operator workspace, never JSON."""

from acquisition.campaigns import CampaignIntake, CampaignBriefDraft, PreparationReview
from acquisition.creative import CompanyDraft, CompanyClaimDraft
from acquisition.conversations import intake_readiness


def fields(value, allowed):
    if type(value) is not dict or set(value) - allowed:
        raise ValueError('Use only the declared intake fields')
    return value


def array(value):
    if type(value) is not list:
        raise ValueError('Use a JSON array for intake collections')
    return tuple(value)


class WorkspaceIntake:
    def __init__(self, intake: CampaignIntake):
        self.intake = intake

    def store_identity(self):
        return self.intake.store_identity()

    def preparation_preview(self, identity, revision):
        return self.intake.preparation.preview('local-conversations', identity, revision)

    def preparation_history(self, identity):
        return {'items':self.intake.preparation.history('local-conversations', identity)}

    def preparation_request(self, request_id):
        return self.intake.preparation.request('local-conversations', request_id)

    def preparation_not_committed(self, request_id):
        return self.intake.preparation.not_committed('local-conversations', request_id)

    def confirm_preparation(self, payload):
        expected = {'request_id','brief_id','brief_revision','preview_id','expected_context_revision',
                    'selected_claim_ids','include_description','include_cta','review_days','review_note','issues','confirmed'}
        if type(payload) is not dict or set(payload) != expected:
            raise ValueError('Use exact preparation review fields')
        value = {k:v for k,v in payload.items() if k != 'request_id'}
        value['selected_claim_ids'] = array(value['selected_claim_ids'])
        value['issues'] = array(value['issues'])
        return self.intake.preparation.confirm('local-conversations','local-operator',payload['request_id'],
                                               PreparationReview(**value))

    def readiness(self, identity, revision):
        brief = self.intake.brief('local-conversations', identity, revision)
        company = self.intake.company('local-conversations', brief['draft']['company_id'], brief['draft']['company_revision'])
        return {'brief_id': identity, 'brief_revision': brief['revision'],
                'company_id': company['id'], 'company_revision': company['revision'],
                **intake_readiness({'company': company, 'brief': brief})}

    def listing(self, kind, after_id='', limit=50):
        listing = {'companies': self.intake.companies, 'briefs': self.intake.briefs}[kind]
        return {'items': listing('local-conversations', after_id=after_id, limit=limit),
                'mode': 'LOCAL_OPERATOR_INTAKE', 'hosted_authentication': False}

    def get(self, kind, identity, revision=None):
        get = {'companies': self.intake.company, 'briefs': self.intake.brief}[kind]
        return get('local-conversations', identity, revision)

    def save(self, kind, payload):
        if (type(payload) is not dict
                or set(payload) != {'request_id', 'id', 'expected_revision', 'draft'}):
            raise ValueError('Use the exact intake save fields')
        value = payload['draft']
        if kind == 'companies':
            fields(value, {'company_name', 'website', 'product_name', 'description', 'claims',
                           'official_cta', 'cta_url', 'source_urls'})
            claims = []
            for claim in array(value.get('claims', [])):
                fields(claim, {'statement', 'qualification', 'source_urls'})
                if 'statement' not in claim:
                    raise ValueError('A claim needs a statement')
                claims.append(CompanyClaimDraft(**(claim | {'source_urls': array(claim.get('source_urls', []))})))
            draft = CompanyDraft(**(value | {'claims': tuple(claims),
                                            'source_urls': array(value.get('source_urls', []))}))
            return self.intake.save_company('local-conversations', 'local-operator', payload['request_id'], draft,
                                            company_id=payload['id'], expected_revision=payload['expected_revision'])
        if kind != 'briefs':
            raise ValueError('Use a supported intake kind')
        fields(value, {'company_id', 'company_revision', 'objective', 'audience', 'country', 'currency',
                       'channels', 'budget_minor', 'max_candidates', 'constraints', 'contact_source'})
        if not {'company_id', 'company_revision'} <= set(value):
            raise ValueError('Select an exact saved company revision')
        if type(value.get('contact_source', 'unspecified')) is not str:
            raise ValueError('Select an intake contact source')
        draft = CampaignBriefDraft(**(value | {'channels': array(value.get('channels', [])),
                                              'constraints': array(value.get('constraints', []))}))
        return self.intake.save_brief('local-conversations', 'local-operator', payload['request_id'], draft,
                                      brief_id=payload['id'], expected_revision=payload['expected_revision'])
