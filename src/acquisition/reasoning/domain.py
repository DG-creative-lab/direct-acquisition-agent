"""Provider-independent limits and normalized inference receipts."""

from dataclasses import dataclass


class ModelError(RuntimeError):
    """Inference failed or has an unknown outcome; never retry implicitly."""

    def __init__(self, code: str, receipt: dict | None = None):
        super().__init__(code)
        self.receipt = receipt


@dataclass(frozen=True)
class CallScope:
    organization: str
    run_id: str
    task_id: str
    lease_token: str


@dataclass(frozen=True)
class ModelConfig:
    model: str
    max_calls: int = 6
    max_output_tokens: int = 1600
    max_input_bytes: int = 24000
    max_prompt_usd_per_million: float = 1.0
    max_completion_usd_per_million: float = 2.0
    force_tool_choice: bool = False

    def __post_init__(self) -> None:
        if not self.model or len(self.model) > 160 or any(c.isspace() for c in self.model):
            raise ValueError("Select an explicit model ID")
        if type(self.force_tool_choice) is not bool:
            raise ValueError("Tool-choice configuration must be boolean")
        if type(self.max_calls) is not int or not 1 <= self.max_calls <= 12:
            raise ValueError("Use 1–12 requests per run")
        if type(self.max_output_tokens) is not int or not 128 <= self.max_output_tokens <= 2400:
            raise ValueError("Use 128–2400 output tokens per request")
        if not 1024 <= self.max_input_bytes <= 32000:
            raise ValueError("Input envelope must be bounded")
        # Fixed ceilings protect this inexpensive test profile. Raising them needs code review.
        if not 0 <= self.max_prompt_usd_per_million <= 1 or not 0 <= self.max_completion_usd_per_million <= 2:
            raise ValueError("Test routing ceilings are $1/M input and $2/M output")
