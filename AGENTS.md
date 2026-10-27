# Acquisition agent project

Use `feature/...` names for development branches. Write plain, precise copy
without em dashes. Preserve immutable historical artifacts when style changes;
newly generated content must follow the current editorial guidance.

Use the modular monolith decision in `docs/architecture.md` for implementation.
The runnable scope includes deterministic day one and the day-two OpenRouter
copy workflow, plus day-three local review and simulated acceptance and day-four synthetic outcome learning. Day five adds a local React interface through a bounded loopback API. Design documents also describe later work and must not be
presented as implemented behavior. See `docs/product-grounding.md` for live model evidence.

## Boundaries

- `runtime`, `audiences`, `campaigns`, `creative`, `reasoning`, `learning`, and `reviews` own their
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

Day-three approval binds an immutable subject, current evidence/suppression epochs, reviewer generation and bounded expiry. Recheck authority and candidate integrity inside the acceptance transaction. Never treat cached receipts or saved reports as current authorization. Keep simulator acceptance, audit and receipt atomic. Preserve the schema-v3 legacy cutoff when migrating to v4. See `docs/day-three.md` for the review authority and test ledger.

Learning cohorts bind accepted simulated assignments, including controls. Missing results are unknown, never implicit non-responses. Finalization requires maturity and full explicit population coverage. Keep outcomes immutable, deduplicate across imports and commit beliefs/finalization/audit/receipt together. Do not count a business in multiple learning cohorts within an organization. Synthetic posterior memory is advisory and separate from preferences, product facts and approval. See `docs/day-four.md` for the ledger and statistical limits.

The React workspace is a presentation/client layer. Keep approval, inference budgets, artifact identity and learning rules in existing Python modules. Bind browser decisions and downloads to exact displayed subjects. Preserve same-origin/token/Host checks and fixed server-side identity resolution. Keep model keys server-side and model inference behind explicit generation. Workspace command replay must not repeat effects or mislabel historical receipts. The per-root server lock and single-worker deployment limit are intentional. Run `make interface-check` for frontend changes. See `docs/day-five.md`.

Presentation follows the publication baseline in `docs/branding.md`. Keep reusable font/palette roles in `frontend/src/brand/tokens.css`; reserve the static Op Art motif for the product signature. Keep semantic status labels and colors distinct, reading surfaces calm, and touch targets at least 44px. Do not restyle historical campaign artifacts as a side effect of UI branding.
