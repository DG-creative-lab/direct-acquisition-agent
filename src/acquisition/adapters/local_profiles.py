"""Reviewed installed profiles, bound to one local organization by bootstrap."""

from dataclasses import asdict
from functools import lru_cache
import json
from pathlib import Path

from acquisition.audiences import taxonomy_from, ProfiledBusiness, ProfiledSnapshot
from acquisition.campaigns import CampaignProfile
from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.creative import product_profile_from

from .synthetic import generate


class LocalProfiles:
    def __init__(self, organization, key, root: Path):
        # Caller configuration selects installed keys, never filesystem paths or code.
        installed = {'iwoca': 'iwoca-v1.json', 'fielddesk': 'fielddesk-v1.json'}
        if key not in installed or not organization:
            raise NotFound('Unknown installed organization profile')
        data = json.loads((root / installed[key]).read_text())
        if data['schema'] != 'installed-profile/v1' or data['key'] != key or data['version'] != 'v1':
            raise ValueError('Unsupported installed profile version')
        taxonomy = taxonomy_from(data['taxonomy'])
        product = product_profile_from(data['product_profile'])
        if (product.taxonomy_id != taxonomy.id or set(dict(product.segment_terms)) != {s.key for s in taxonomy.segments}
                or digest(data['material']['pack']) != product.fact_pack_hash
                or set(data['material']['fixtures']) != {s.key for s in taxonomy.segments}
                or any(set(pair) != {'A', 'B'} for pair in data['material']['fixtures'].values())):
            raise ValueError('Installed profile relationships do not match their reviewed inputs')
        self.organization = organization
        self.profile = CampaignProfile(**data['campaign'], taxonomy=taxonomy, product_profile_id=product.id)
        if self.profile.key != key or self.profile.version != data['version'] or self.profile.product_key != product.key:
            raise ValueError('Installed company/product binding differs')
        self.product, self.material = product, canonical(data['material'])

    def _scope(self, organization):
        if organization != self.organization:
            raise NotFound('Profile is not installed in this organization')

    def campaign_profile(self, organization, key, version):
        self._scope(organization)
        if (key, version) != (self.profile.key, self.profile.version):
            raise NotFound('Unknown installed campaign profile version')
        return self.profile

    def product_profile(self, organization, identity):
        self._scope(organization)
        if identity != self.product.id:
            raise NotFound('Unknown installed product evidence profile')
        return self.product

    def product_material(self, organization, identity):
        self.product_profile(organization, identity)
        return json.loads(self.material)


class SyntheticProfileAudience:
    @lru_cache(maxsize=128)
    def snapshot_identity(self, organization, taxonomy, size, seed, as_of):
        # Only trusted request parameters supply the expected identity, never candidate rows or metadata.
        return self.snapshot(organization, taxonomy, size, seed, as_of).id

    def snapshot(self, organization, taxonomy, size, seed, as_of):
        original = generate(organization, size, seed, as_of)
        segments = [s.key for s in taxonomy.segments]
        records = tuple(ProfiledBusiness(**(asdict(row) | {'segment': segments[i % len(segments)]}))
                        for i, row in enumerate(original.records))
        return ProfiledSnapshot(organization, as_of, records, seed, taxonomy=taxonomy,
                               model_version='synthetic-profile-audience/v1')
