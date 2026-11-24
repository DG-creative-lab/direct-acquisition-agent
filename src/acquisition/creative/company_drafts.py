"""User-supplied intake, deliberately distinct from reviewed ProductProfile values."""

from dataclasses import dataclass
from urllib.parse import urlsplit


def draft_text(value, maximum=4000):
    if (type(value) is not str or len(value) > maximum or value != value.strip()
            or any(ord(c) < 32 and c != '\n' for c in value) or chr(0x2014) in value):
        raise ValueError('Use bounded plain draft text without surrounding whitespace')


def draft_url(value):
    draft_text(value, 2000)
    if not value:
        return
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise ValueError('Use an absolute HTTP or HTTPS reference') from error
    if (parsed.scheme not in {'http', 'https'} or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or port is not None or any(c.isspace() for c in value)):
        raise ValueError('Use an absolute HTTP or HTTPS reference without credentials or ports')


def draft_sources(values):
    if type(values) is not tuple or len(values) > 20:
        raise ValueError('Use at most 20 distinct reference URLs')
    for value in values:
        draft_url(value)
        if not value:
            raise ValueError('A reference URL cannot be empty')
    if len(set(values)) != len(values):
        raise ValueError('Use distinct reference URLs')


@dataclass(frozen=True)
class CompanyClaimDraft:
    statement: str
    qualification: str = ''
    source_urls: tuple[str, ...] = ()

    def __post_init__(self):
        draft_text(self.statement)
        draft_text(self.qualification)
        draft_sources(self.source_urls)
        if not self.statement:
            raise ValueError('A claim needs a statement')


@dataclass(frozen=True)
class CompanyDraft:
    company_name: str = ''
    website: str = ''
    product_name: str = ''
    description: str = ''
    claims: tuple[CompanyClaimDraft, ...] = ()
    official_cta: str = ''
    cta_url: str = ''
    source_urls: tuple[str, ...] = ()

    def __post_init__(self):
        for value in (self.company_name, self.product_name, self.official_cta):
            draft_text(value, 600)
        draft_text(self.description, 8000)
        draft_url(self.website)
        draft_url(self.cta_url)
        draft_sources(self.source_urls)
        if (type(self.claims) is not tuple or len(self.claims) > 20
                or any(type(value) is not CompanyClaimDraft for value in self.claims)):
            raise ValueError('Use at most 20 user-supplied claims with qualifications and references')
