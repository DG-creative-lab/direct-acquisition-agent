# Direct Acquisition Agent

A Python acquisition operations demo with custom orchestration, persistent tasks, audience-specific copy and human review checkpoints. All audience data is synthetic. This is an independent demonstration with no connection to a lender's production systems.

The first workflow prepares a direct-mail campaign: inspect an audience, draft contrasting messages for two segments, apply deterministic exclusions and a budget, assign A/B/no-mail groups, then stop for review. It does not send letters or make lending decisions.

## Run locally

Requires Python 3.11 or later. No third-party packages are currently required.

```sh
make demo
PYTHONPATH=src python3 -m acquisition --db .local/review.sqlite demo-review --out .local/day-three
PYTHONPATH=src python3 -m acquisition --db .local/learning.sqlite demo-learning --out .local/day-four
make test
make arch-check
make mutation-check
```

The deterministic demo needs no model account. It creates a local SQLite database and exports a manifest, mailing CSV and assignment CSV. Repeated requests reuse their persisted identity and artifact.

For generated copy, configure an OpenRouter key in ignored `.env.local` as `OPENROUTER_API_KEY`. GPT-OSS-120B is the default. You can also list current inexpensive tool-capable models:

```sh
PYTHONPATH=src python3 -m acquisition models
PYTHONPATH=src python3 -m acquisition --db .local/copy.sqlite demo-model --request-id copy-demo
```

Free endpoints may be unavailable or fail the output contract. No paid fallback is automatic. Model responses are validated before a draft is saved. All generated copy remains unreviewed, and checkpoint acknowledgement grants no sending authority.

Model commands default to GPT-OSS-120B. The current direct-mail configuration uses a dated, public-source iwoca fact pack. Generated framing is checked separately; code inserts selected factual wording, qualifications and the official CTA. The source pack and paired screening result travel with the exported draft. The semantic screen can make mistakes and does not replace human review. New generation stops when the evidence review window expires.

## Architecture

One deployable modular monolith contains runtime, audiences, campaigns, creative, reasoning, learning and reviews modules. Domain rules are pure; application services depend on narrow ports; SQLite, filesystem and OpenRouter implementations are adapters. An explicit composition root wires the application together. Static checks enforce module imports and reject cycles.

The model can read editorial context and submit bounded copy drafts. Code controls the population, experiment assignments, exact money calculations, task lifecycle and artifact integrity. Inference requests are reserved and journaled before dispatch so task recovery can reuse completed responses without issuing another request.

## Memory and learning

Editorial memory contains reviewer preferences and examples scoped to the organization and segment. Each run freezes the guidance and examples it uses. This is separate from evidence of audience response.

The learning module ingests explicit synthetic outcomes for accepted simulated campaigns, waits for a complete 28-day cohort and persists Beta posterior counts. It compares A/B variants with the no-mail control and recommends a further experiment when illustrative evidence thresholds are met. New copy runs freeze mature learning memory alongside separate editorial preferences.

Run `demo-learning` to create `.local/day-four/learning.html`, with a clearly labelled simulated clock and outcomes. Repeated imports and finalization do not double-count evidence. The prototype rejects repeated business exposure across cohorts. Recommendations remain advisory and require a new proposal and approval. See the [day-four guide](docs/day-four.md) for the statistical assumptions, import contract and limits. No synthetic judgment is presented as real customer response.

## Current boundaries

This is a local prototype for trusted operators, with a single active worker. The organization flag selects a scope; it is not hosted authentication. Review decisions bind the exact draft, audience and active evidence. Changes, expiry or revoked reviewer authority block a new simulated handoff. A read-only HTML report supports inspection; decisions use the transactional CLI. See the [day-three guide](docs/day-three.md) for manual commands, invalidation rules and recovery semantics.

The scripted review demo writes `.local/day-three/review.html` and demonstrates a late suppression followed by fresh approval. Its reviewer decisions are scripted, and agency acceptance is a local simulation. Hosted authentication, real agency delivery and production data connectors require further implementation and verification.

Tests cover domain rules, real SQLite persistence, separate-process restart, task leases, idempotency, scoped memory, model-call replay and deterministic output validation. Live model quality is evaluated separately from offline contract tests.

## Review evidence

The current suite has 133 offline tests, a static architecture check and 17 targeted mutation checks. See the [test coverage review](docs/test-coverage-review.md), [architecture](docs/architecture.md) and [product-grounding notes](docs/product-grounding.md). A [recorded copy example](examples/grounded-run/letters.txt) shows the unreviewed output of a live run.

Development branches use the `feature/...` naming convention. Real outcome feeds, correction/retraction, repeated-exposure models and external delivery are later work. No license terms have been selected yet.
