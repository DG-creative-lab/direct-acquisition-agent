from typing import Protocol

from .domain import Snapshot, DatasetVersion, AudienceTaxonomy, ProfiledSnapshot


class AudienceStore(Protocol):
    def put(self, snapshot: Snapshot) -> str: ...
    def get(self, organization: str, snapshot_id: str) -> Snapshot: ...


class AudienceSource(Protocol):
    def listing(self, organization: str) -> tuple['DatasetVersion', ...]: ...
    def read(self, organization: str, dataset_id: str, version: str, checksum: str, manifest_id: str) -> tuple['DatasetVersion', Snapshot]: ...


class ProfileFixtureAudience(Protocol):
    def snapshot(self, organization: str, taxonomy: AudienceTaxonomy, size: int, seed: int, as_of: str) -> ProfiledSnapshot: ...
