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
