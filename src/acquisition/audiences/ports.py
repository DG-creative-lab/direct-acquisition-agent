from typing import Protocol

from .domain import Snapshot


class AudienceStore(Protocol):
    def put(self, snapshot: Snapshot) -> str: ...
    def get(self, organization: str, snapshot_id: str) -> Snapshot: ...
