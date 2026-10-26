# Acquisition agent project

Use `feature/...` names for development branches. Write plain, precise copy
without em dashes. Preserve immutable historical artifacts when style changes;
newly generated content must follow the current editorial guidance.

Use the modular monolith decision in `docs/architecture.md` for implementation.
The runnable scope includes deterministic day one and the day-two OpenRouter
copy workflow. Design documents also describe later work and must not be
presented as implemented behavior. See `docs/product-grounding.md` for live model evidence.

## Boundaries

- `runtime`, `audiences`, `campaigns`, `creative`, `reasoning`, and `learning` own their
  domain values, rules and narrow ports. Their `domain.py` files use only the
  standard library, `contracts`, and declared public domain contracts.
- Cross-module use goes through the provider module's `__init__.py` exports.
- Runtime is business-agnostic. It never imports audience, campaign, creative,
  learning, adapter, workflow or CLI code.
- Application services depend on ports, never concrete adapters.
- `workflows` composes module APIs. `bootstrap.py` is the composition root;
  it alone wires workflows, adapters and runtime services together.
- `adapters` implements ports. Modules must not import it. Avoid generic
  repositories, service locators, event buses and unused abstraction layers.
- `contracts.py` contains only stable serialization/hash helpers and common
  errors; do not turn it into a shared business model.

## Invariants

Scope every durable read/write by organization. Check leases at commit, not
only claim. Bind idempotency keys to exact request inputs. Commit task result
and lifecycle/event changes together. Acknowledging the day-one review
checkpoint grants no release or print authority.

Keep source evidence, interpretation, proposals, approval, execution and
observations separate. Synthetic data must remain explicitly labeled. Learning
support counts measure independent outcomes, not model scores or memory use.
Creative rewrites get new identities and cannot inherit approval or outcomes.
Reserve model calls before dispatch; never automatically repeat an uncertain
paid request. Freeze guidance and scoped reviewer memory per run. Keep provider
credentials inside adapters and out of prompts, receipts and exports.
New model workflows use v3 product grounding. Keep selected factual wording,
qualifications, official CTA and evidence IDs bound to the frozen reviewed pack.
Recheck evidence freshness at draft creation. A semantic screening pass is not
approval. Preserve v1/v2 artifact compatibility and keep legacy v2 explicitly
ungrounded; never downgrade a v3 capability's inputs to bypass its checks.

## Verification

Run `make test` and `make arch-check`. Test real SQLite and process restarts,
not only mocked repositories. Maintain the invariant ledger in
`docs/day-one-validation.md`. Add targeted checks for every new effect or
authority boundary. Do not claim live model behavior without executing it.
