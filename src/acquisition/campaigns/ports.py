from typing import Protocol

from .domain import Draft


class DraftStore(Protocol):
    def put(self, organization: str, operation_id: str, draft: Draft) -> str: ...
    def get(self, organization: str, draft_id: str) -> Draft: ...
