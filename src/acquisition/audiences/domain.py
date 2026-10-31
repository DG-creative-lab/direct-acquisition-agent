from dataclasses import asdict, dataclass
from datetime import date

from acquisition.contracts import digest


@dataclass(frozen=True)
class Business:
    record_id: str
    business_id: str
    segment: str
    country: str
    entity_type: str
    address: str
    deliverable: bool
    suppressed: bool
    contacts_last_90_days: int
    last_contact: str | None
    propensity_ppm: int | None

    def __post_init__(self) -> None:
        if not self.record_id or not self.business_id:
            raise ValueError("Record and business identity are required")
        if self.segment not in {"inventory", "contractors"}:
            raise ValueError("Unknown segment")
        if type(self.deliverable) is not bool or type(self.suppressed) is not bool:
            raise ValueError("Policy attestations must be booleans")
        if type(self.contacts_last_90_days) is not int or self.contacts_last_90_days < 0:
            raise ValueError("Invalid contact count")
        if self.propensity_ppm is not None and (
            type(self.propensity_ppm) is not int or not 0 <= self.propensity_ppm <= 1_000_000
        ):
            raise ValueError("Invalid probability")
        if self.last_contact is not None:
            date.fromisoformat(self.last_contact)


@dataclass(frozen=True)
class Snapshot:
    organization: str
    as_of: str
    records: tuple[Business, ...]
    seed: int
    complete: bool = True
    schema_version: str = "audience/v1"
    model_version: str = "synthetic-segmentation/v1"
    score_semantics: str = "synthetic_response_propensity_not_uplift"

    def __post_init__(self) -> None:
        date.fromisoformat(self.as_of)
        if not self.organization or self.schema_version != "audience/v1":
            raise ValueError("Unsupported snapshot contract")
        if type(self.complete) is not bool or type(self.seed) is not int:
            raise ValueError("Invalid snapshot metadata")
        if len({record.record_id for record in self.records}) != len(self.records):
            raise ValueError("Record identities must be unique")

    @property
    def id(self) -> str:
        return "aud_" + digest(asdict(self))


def catalogue_identity(value: str) -> str:
    import re
    if type(value) is not str or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", value) or value in {'.','..'}:
        raise ValueError('Use a bounded catalogue identity')
    return value


@dataclass(frozen=True)
class DatasetVersion:
    organization: str
    dataset_id: str
    version: str
    campaign_key: str
    title: str
    description: str
    segments: tuple[str, ...]
    record_count: int
    business_count: int
    checksum: str
    as_of: str
    generated_on: str
    review_by: str
    model_version: str
    schema_version: str = 'audience/v1'
    channel: str = 'postal_direct_mail'
    mode: str = 'SYNTHETIC_ONLY'

    def __post_init__(self):
        import re
        for value in (self.organization,self.dataset_id,self.version,self.campaign_key):
            catalogue_identity(value)
        if any(type(v) is not str or not 1 <= len(v.strip()) <= 600 or any(ord(c)<32 for c in v)
               for v in (self.title,self.description,self.model_version)):
            raise ValueError('Invalid dataset description or model version')
        if (type(self.segments) is not tuple or not self.segments or len(set(self.segments)) != len(self.segments)
                or not set(self.segments) <= {'inventory','contractors'}):
            raise ValueError('Declare distinct supported dataset segments')
        if (type(self.record_count) is not int or not 1 <= self.record_count <= 10000
                or type(self.business_count) is not int or not 1 <= self.business_count <= self.record_count):
            raise ValueError('Invalid bounded dataset population')
        if not re.fullmatch(r'[a-f0-9]{64}',self.checksum):
            raise ValueError('Dataset requires a SHA-256 content checksum')
        for value in (self.as_of,self.generated_on,self.review_by):
            if date.fromisoformat(value).isoformat() != value:
                raise ValueError('Dataset dates must use YYYY-MM-DD')
        if not date.fromisoformat(self.as_of) <= date.fromisoformat(self.generated_on) <= date.fromisoformat(self.review_by):
            raise ValueError('Invalid dataset source dates')
        if self.schema_version != 'audience/v1' or self.channel != 'postal_direct_mail' or self.mode != 'SYNTHETIC_ONLY':
            raise ValueError('Unsupported dataset schema, channel or source mode')

    @property
    def id(self):
        return 'dataset_' + digest(asdict(self))


def validate_dataset(manifest: DatasetVersion, snapshot: Snapshot, organization: str, today: date):
    from acquisition.contracts import Conflict
    if manifest.organization != organization or snapshot.organization != organization:
        raise Conflict('Dataset is not available in this organization')
    if not date.fromisoformat(manifest.generated_on) <= today <= date.fromisoformat(manifest.review_by):
        raise Conflict('Dataset is outside its declared review window')
    if (not snapshot.complete or snapshot.schema_version != manifest.schema_version
            or snapshot.model_version != manifest.model_version or snapshot.as_of != manifest.as_of
            or snapshot.score_semantics != 'synthetic_response_propensity_not_uplift'):
        raise Conflict('Dataset metadata or completeness differs from its manifest')
    if (len(snapshot.records) != manifest.record_count
            or len({r.business_id for r in snapshot.records}) != manifest.business_count
            or {r.segment for r in snapshot.records} != set(manifest.segments)):
        raise Conflict('Dataset population differs from its declared coverage')
    for record in snapshot.records:
        for value, maximum in ((record.record_id,200),(record.business_id,200),(record.country,2),(record.entity_type,50),(record.address,300)):
            if type(value) is not str or not 1 <= len(value) <= maximum or any(ord(c)<32 for c in value):
                raise ValueError('Invalid bounded audience record text')
        if not record.address.startswith('DEMO ONLY DO NOT POST:'):
            raise ValueError('This audience source accepts only synthetic contact addresses')
