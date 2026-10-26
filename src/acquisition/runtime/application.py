from collections.abc import Callable
import math

from .domain import Claim, LeaseLost, Outcome, RetryableError
from .ports import TaskStore


class Worker:
    """One bounded tick; waiting never keeps an invocation open."""

    def __init__(self, store: TaskStore, capabilities: dict[str, Callable[[Claim], Outcome]],
                 clock: Callable[[], float], lease_seconds: float = 60):
        if not math.isfinite(lease_seconds) or lease_seconds <= 0:
            raise ValueError("Lease must be positive")
        self.store, self.capabilities, self.clock = store, dict(capabilities), clock
        self.lease_seconds = lease_seconds

    def tick(self, organization: str) -> bool:
        claim = self.store.claim(organization, self.clock(), self.lease_seconds)
        if claim is None:
            return False
        try:
            handler = self.capabilities.get(claim.capability)
            if handler is None:
                self.store.fail(claim, "unsupported_capability", False, self.clock())
            else:
                result = handler(claim)
                if not isinstance(result, Outcome):
                    raise TypeError("Capability returned an unsupported result")
                self.store.settle(claim, result, self.clock())
        except LeaseLost:
            # Another attempt or cancellation owns the state; never overwrite it.
            pass
        except Exception as error:
            try:
                self.store.fail(claim, type(error).__name__, isinstance(error, RetryableError), self.clock())
            except LeaseLost:
                pass
        return True

    def drain(self, organization: str, max_tasks: int = 20) -> int:
        if type(max_tasks) is not int or not 1 <= max_tasks <= 1000:
            raise ValueError("Use 1–1000 worker ticks")
        count = 0
        while count < max_tasks and self.tick(organization):
            count += 1
        return count
