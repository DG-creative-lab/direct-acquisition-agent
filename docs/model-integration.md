# Model integration

The CLI uses OpenRouter behind a provider-independent inference port. Model commands default to GPT-OSS-120B. The application owns orchestration, task state, tool execution, validation and recovery.

Before a request, the journal checks the active task lease and reserves one call against the run's limit. A completed response is reused only when the request hash matches. If the provider outcome or saved receipt is uncertain, the application stops rather than submitting the call again automatically. A late response may record usage after cancellation but cannot authorize a follow-up call or complete the cancelled task.

Before claiming or recovering a model task, the worker checks its configuration against the task's original model and limits inside the claim transaction. An incompatible worker leaves attempts, lifecycle and events unchanged and can still claim compatible offline work. Resume with the pinned configuration. Historical v2 execution also requires a matching admission record frozen during the schema-v3 migration; new v2 runs are rejected.

The current profile allows ten calls per run, at most 1,600 output tokens per request and a 24,000-byte input envelope. Paid routes have ceilings of $1 per million input tokens and $2 per million output tokens, with no per-request charge. Free model IDs require zero-price routes. Provider fallbacks are disabled. These controls supplement the provider's account or key spending limit.

Only aggregate synthetic segment information is supplied to the model. Reviewer preferences are scoped by organization and segment, then frozen into each run's context. They are writing guidance, not evidence of customer response.

The model writes two audience hooks and selects supplied product fact IDs. Code adds the exact factual statements and qualifications. A separate request screens the proposed framing against the frozen evidence. See [product grounding](product-grounding.md) for its limits, failure history and recorded live results.

Use `make test`, `make arch-check` and `make mutation-check` for offline verification. Live model calls are opt-in and are not part of CI. The small labelled critic regression can be run with `PYTHONPATH=src python3 scripts/evaluate_claim_screen.py` when a key is configured.

New copy uses plain punctuation and rejects em dashes. Historical persisted snapshots and drafts remain immutable. Changing the punctuation of newly seeded addresses changes their snapshot identity; default demo request IDs are versioned to avoid reusing an older request with different bytes.
