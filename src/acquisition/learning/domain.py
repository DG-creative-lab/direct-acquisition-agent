"""Statistical value only; production outcome ingestion arrives on day four."""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class BetaBelief:
    alpha: float
    beta: float

    def __post_init__(self) -> None:
        if not all(math.isfinite(value) and value > 0 for value in (self.alpha, self.beta)):
            raise ValueError("Prior parameters must be finite and positive")

    def observe(self, trials: int, successes: int) -> "BetaBelief":
        if type(trials) is not int or type(successes) is not int or not 0 <= successes <= trials:
            raise ValueError("Require integer 0 <= successes <= trials")
        return BetaBelief(self.alpha + successes, self.beta + trials - successes)
