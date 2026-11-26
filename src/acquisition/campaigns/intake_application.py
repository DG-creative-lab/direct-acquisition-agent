"""Save and inspect user intake without admitting campaign or inference work."""

from dataclasses import asdict
import math

from acquisition.contracts import canonical
from acquisition.creative import CompanyDraft
from .intake import CampaignBriefDraft, intake_identity, intake_revision
from .ports import CampaignIntakeStore


class CampaignIntake:
    def __init__(self, store: CampaignIntakeStore, clock, preparation=None, grounded=None, emails=None, email_reviews=None, initialize_email_defaults=None):
        self.store, self.clock, self.preparation = store, clock, preparation
        self.grounded = grounded
        self.emails,self.email_reviews,self.initialize_email_defaults=emails,email_reviews,initialize_email_defaults

    def store_identity(self):
        """Persistent database identity for binding local recovery to its owner."""
        return self.store.identity()

    def save_company(self, organization, actor, request_id, draft: CompanyDraft, *, company_id=None, expected_revision=0):
        if type(draft) is not CompanyDraft:
            raise ValueError('Supply a user-supplied company draft')
        return self._save('company', organization, actor, request_id, draft, company_id, expected_revision)

    def save_brief(self, organization, actor, request_id, draft: CampaignBriefDraft, *, brief_id=None, expected_revision=0):
        if type(draft) is not CampaignBriefDraft:
            raise ValueError('Supply a campaign brief draft')
        return self._save('brief', organization, actor, request_id, draft, brief_id, expected_revision)

    def _save(self, kind, organization, actor, request_id, draft, identity, revision):
        for value in (organization, actor, request_id):
            intake_identity(value)
        intake_revision(revision)
        if identity is not None:
            intake_identity(identity)
        if (identity is None) != (revision == 0):
            raise ValueError('Create at revision zero or edit an existing exact revision')
        payload = asdict(draft)
        if len(canonical(payload).encode()) > 64_000:
            raise ValueError('Intake draft exceeds 64000 serialized bytes')
        now = self.clock()
        if type(now) not in (int, float) or not math.isfinite(now) or not 0 <= now < 253402300800:
            raise ValueError('Use a finite intake timestamp')
        inputs = {'kind': kind, 'actor': actor, 'id': identity, 'expected_revision': revision, 'draft': payload}
        return self.store.save(organization, request_id, inputs, now)

    def company(self, organization, company_id, revision=None):
        return self._get('company', organization, company_id, revision)

    def brief(self, organization, brief_id, revision=None):
        return self._get('brief', organization, brief_id, revision)

    def _get(self, kind, organization, identity, revision):
        intake_identity(organization)
        intake_identity(identity)
        if revision is not None:
            intake_revision(revision, positive=True)
        return self.store.get(organization, kind, identity, revision)

    def companies(self, organization, *, after_id='', limit=50):
        return self._listing('company', organization, after_id, limit)

    def briefs(self, organization, *, after_id='', limit=50):
        return self._listing('brief', organization, after_id, limit)

    def _listing(self, kind, organization, after_id, limit):
        intake_identity(organization)
        if after_id:
            intake_identity(after_id)
        if type(after_id) is not str or type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('Use a bounded intake page')
        return self.store.listing(organization, kind, after_id, limit)
