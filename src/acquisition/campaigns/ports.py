from dataclasses import dataclass
from typing import Protocol

from .domain import Draft


@dataclass(frozen=True)
class DraftLease:
    run_id: str
    task_id: str
    token: str


class DraftStore(Protocol):
    def put(self, organization: str, operation_id: str, draft: Draft, *, lease: DraftLease | None = None) -> str: ...
    def get(self, organization: str, draft_id: str) -> Draft: ...


class FollowupStore(Protocol):
    def get(self, organization: str, identity: str) -> dict: ...
    def put(self, organization: str, request: str, proposal: dict) -> dict: ...
    def excluded(self, organization: str) -> set[str]: ...
    def check(self, organization: str, proposal: dict, campaign_id: str) -> None: ...
    def listing(self, organization: str, parent_id: str) -> list[dict]: ...
