"""Immutable reviewed product/brand bindings. These values grant no authority."""

from dataclasses import asdict, dataclass
import re
from urllib.parse import urlparse

from acquisition.contracts import digest


@dataclass(frozen=True)
class ProductProfile:
    key: str
    version: str
    product: str
    brand_key: str
    brand_version: str
    brand_name: str
    voice: str
    disclosure: str
    official_urls: tuple[str, ...]
    fact_pack_hash: str
    taxonomy_id: str
    segment_terms: tuple[tuple[str, tuple[str, ...]], ...]
    prohibited_terms: tuple[str, ...]
    evidence_kind: str
    schema: str = 'product-profile/v1'

    def __post_init__(self):
        if self.schema != 'product-profile/v1' or self.evidence_kind not in {'public_reviewed', 'synthetic_fixture'}:
            raise ValueError('Unsupported product evidence profile')
        for value in (self.key, self.version, self.brand_key, self.brand_version):
            if type(value) is not str or not re.fullmatch(r'[a-zA-Z0-9_.-]{1,100}', value):
                raise ValueError('Use a bounded profile reference')
        for value in (self.product, self.brand_name, self.voice, self.disclosure):
            if (type(value) is not str or not 1 <= len(value.strip()) <= 600
                    or value != value.strip() or any(ord(c) < 32 for c in value) or chr(0x2014) in value):
                raise ValueError('Use bounded plain product/brand text')
        if (not re.fullmatch(r'[a-f0-9]{64}', self.fact_pack_hash)
                or not re.fullmatch(r'taxonomy_[a-f0-9]{64}', self.taxonomy_id)):
            raise ValueError('Bind the exact fact pack and taxonomy')
        if type(self.official_urls) is not tuple or not self.official_urls or len(set(self.official_urls)) != len(self.official_urls):
            raise ValueError('Declare distinct reviewed official URLs')
        for value in self.official_urls:
            url = urlparse(value)
            if (url.scheme != 'https' or not url.hostname or url.netloc != url.hostname
                    or url.query or url.fragment or not url.path
                    or (self.evidence_kind == 'synthetic_fixture' and not url.hostname.endswith('.invalid'))):
                raise ValueError('Use exact reviewed HTTPS sources, with .invalid sources for synthetic products')
        if (type(self.segment_terms) is not tuple or not self.segment_terms
                or len({key for key, _ in self.segment_terms}) != len(self.segment_terms)):
            raise ValueError('Declare distinct framing segments')
        for _, terms in self.segment_terms:
            if type(terms) is not tuple or not terms or any(type(t) is not str or not re.fullmatch(r'[a-z]{2,30}', t) for t in terms):
                raise ValueError('Framing terms are bounded literal words, not executable patterns')
        if (type(self.prohibited_terms) is not tuple or not self.prohibited_terms
                or any(type(t) is not str or not re.fullmatch(r'[a-z]{2,30}', t) for t in self.prohibited_terms)):
            raise ValueError('Declare literal product terms excluded from generated hooks')

    @property
    def id(self):
        return 'product_profile_' + digest(asdict(self))


def product_profile_from(payload):
    return ProductProfile(**(payload | {'official_urls': tuple(payload['official_urls']),
        'prohibited_terms': tuple(payload['prohibited_terms']),
        'segment_terms': tuple((key, tuple(terms)) for key, terms in payload['segment_terms'])}))


def context_product_profile(context):
    if context.get('schema') != 'creative-context/v4':
        if 'product_profile' in context or 'product_profile_id' in context:
            raise ValueError('Profile-bound content cannot use a legacy creative contract')
        return None
    profile = product_profile_from(context['product_profile'])
    if (profile.id != context.get('product_profile_id')
            or digest(context['product_facts']) != profile.fact_pack_hash
            or context['guidance']['locked_block'] != profile.disclosure
            or context.get('segment') not in dict(profile.segment_terms)
            or context.get('copy_mode') not in {'fixture', 'model'}):
        raise ValueError('Creative context differs from its exact reviewed product profile')
    return profile
