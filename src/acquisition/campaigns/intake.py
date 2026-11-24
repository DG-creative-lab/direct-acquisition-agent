"""Campaign requirements saved as drafts, with no execution capability implied."""

from dataclasses import dataclass
import re

from acquisition.creative import draft_text


def intake_identity(value):
    if type(value) is not str or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', value):
        raise ValueError('Use a bounded intake identity')


def intake_revision(value, *, positive=False):
    if type(value) is not int or not (1 if positive else 0) <= value <= 1_000_000:
        raise ValueError('Use a bounded integer revision')


@dataclass(frozen=True)
class CampaignBriefDraft:
    company_id: str
    company_revision: int
    objective: str = ''
    audience: str = ''
    country: str = ''
    currency: str = ''
    channels: tuple[str, ...] = ()
    budget_minor: int | None = None
    max_candidates: int | None = None
    constraints: tuple[str, ...] = ()
    contact_source: str = 'unspecified'

    def __post_init__(self):
        intake_identity(self.company_id)
        intake_revision(self.company_revision, positive=True)
        for value in (self.objective, self.audience):
            draft_text(value)
        for value in (self.country, self.currency):
            draft_text(value, 80)
        for values, maximum, length in ((self.channels, 10, 80), (self.constraints, 20, 1000)):
            if type(values) is not tuple or len(values) > maximum:
                raise ValueError('Use bounded draft requirements')
            for value in values:
                draft_text(value, length)
                if not value:
                    raise ValueError('Requirements cannot be empty')
            if len(set(values)) != len(values):
                raise ValueError('Use distinct draft requirements')
        if self.budget_minor is not None and (type(self.budget_minor) is not int or not 0 <= self.budget_minor <= 1_000_000_000):
            raise ValueError('Use an explicit integer budget in the requested currency minor units')
        if self.max_candidates is not None and (type(self.max_candidates) is not int or not 1 <= self.max_candidates <= 400_000):
            raise ValueError('Use a bounded candidate count')
        if self.contact_source not in {'unspecified', 'synthetic'}:
            raise ValueError('Live contact integrations are not available through intake')
