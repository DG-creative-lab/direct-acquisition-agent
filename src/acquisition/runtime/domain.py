"""Runtime lifecycle values; no campaign or persistence knowledge."""

from dataclasses import dataclass
from typing import Any


class LeaseLost(RuntimeError):
    """This attempt no longer owns the right to commit."""


class RetryableError(RuntimeError):
    """A registered local operation can safely be retried."""


@dataclass(frozen=True)
class TaskSpec:
    capability: str
    inputs: dict[str, Any]
    max_attempts: int = 3

    def __post_init__(self) -> None:
        if not self.capability or type(self.max_attempts) is not int or not 1 <= self.max_attempts <= 5:
            raise ValueError("Task requires a capability and 1–5 attempts")


@dataclass(frozen=True)
class Claim:
    organization: str
    run_id: str
    task_id: str
    capability: str
    inputs: dict[str, Any]
    token: str
    attempt: int
    resume: dict[str, Any] | None


@dataclass(frozen=True)
class Outcome:
    status: str
    data: dict[str, Any]

    def __post_init__(self) -> None:
        if self.status not in {"succeeded", "waiting"}:
            raise ValueError("Handlers may succeed or wait; they cannot grant lifecycle authority")
        if self.status == "waiting" and not self.data.get("reference"):
            raise ValueError("Waiting needs an exact reference")
