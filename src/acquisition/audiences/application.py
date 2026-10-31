"""Read-only discovery. Selection grants no campaign or contact authority."""
from dataclasses import asdict
from datetime import datetime, timezone

from .domain import catalogue_identity, validate_dataset
from .ports import AudienceSource


class AudienceDiscovery:
    def __init__(self, source: AudienceSource, clock):
        self.source, self.clock = source, clock

    def discover(self, organization, campaign_key=None):
        catalogue_identity(organization)
        if campaign_key is not None:
            catalogue_identity(campaign_key)
        today = datetime.fromtimestamp(self.clock(),timezone.utc).date().isoformat()
        entries = [asdict(m) | {'id':m.id, 'within_review_window':m.generated_on <= today <= m.review_by}
                   for m in self.source.listing(organization) if campaign_key is None or m.campaign_key == campaign_key]
        return {'entries':entries,'resolution':'none' if not entries else 'single' if len(entries)==1 else 'ambiguous',
                'authority':'none','mode':'SYNTHETIC_ONLY','selection':'explicit_dataset_version_and_checksum_required'}

    def read(self, organization, dataset_id, version, checksum, manifest_id):
        for value in (organization,dataset_id,version):
            catalogue_identity(value)
        manifest, snapshot = self.source.read(organization,dataset_id,version,checksum,manifest_id)
        validate_dataset(manifest,snapshot,organization,datetime.fromtimestamp(self.clock(),timezone.utc).date())
        return manifest, snapshot

    def inspect(self, organization, dataset_id, version, checksum, manifest_id):
        manifest, snapshot = self.read(organization,dataset_id,version,checksum,manifest_id)
        return {'source':asdict(manifest) | {'id':manifest.id},'snapshot_id':snapshot.id,
                'record_count':len(snapshot.records),'business_count':len({r.business_id for r in snapshot.records}),
                'authority':'none','status':'retrieved_not_campaign_selected','mode':'SYNTHETIC_ONLY'}
