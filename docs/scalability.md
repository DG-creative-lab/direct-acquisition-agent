# Scaling and hosted operation

This document describes a possible evolution of the local product. The steps below are proposals, not implemented capabilities or measured capacity claims. The current supported topology is one loopback server, one active worker and local SQLite databases with synthetic data.

The modular monolith is a useful starting point: campaign, review and learning rules already have explicit owners, deterministic identities and narrow ports. Keeping those modules together also keeps important authority transactions local. Splitting them into services before measuring a constraint would add failure modes without establishing more capacity.

## Capacity questions before infrastructure changes

Measure audience size and selection cost, queue wait and lease recovery, database write contention, report/export size, inference latency and cost, approval turnaround and outcome ingestion/finalization time. Define workload and service objectives before choosing capacity targets. The 1,000-record demonstration and selected concurrent-connection tests are not load tests.

Record stable organization, run, task, draft, subject, inference and cohort IDs in operational traces. Separate an unknown provider outcome from a failed request, and receipt observation from a new effect. Logs must exclude credentials and unnecessary audience data.

## A staged path

| Stage | Concrete changes | Evidence needed before adoption |
| --- | --- | --- |
| Hosted pilot | Authenticated users, tenant membership, server-derived roles, TLS, secret management, a deployment-specific API boundary and limited pilot data | Cross-tenant and role substitution tests, revoked-session behavior, current-authority checks, threat review and end-to-end pilot journey |
| Concurrent operations | Shared transactional storage, tested row-claim/lease protocol, heartbeat/time policy, scheduler admission and worker configuration rules | Competing claims, stale worker completion, cancellation, retries, storage failures and mixed worker configurations |
| Real delivery | Agency adapter, transactional dispatch intent/outbox, provider idempotency, delivery-status journal and reconciliation | Remote success with lost acknowledgement, duplicates, delayed receipts, expiry/revocation around dispatch and recovery after restart |
| Real outcome feeds | Verified assignment joins, source completeness watermarks, attribution policy, corrections/retractions and repeated-exposure model | Late/duplicate/conflicting data, revised denominators, identity drift, cohort overlap and reproducible corrected counts |
| Higher volume | Measured indexes/query plans, bounded ingestion/export work, retention, archival and selective worker scaling | Representative load, latency/cost targets, restored backups and reconciliation under backlog |

These are dependency gates. More workers do not establish correct remote dispatch, and hosted authentication does not establish data quality or calibrated learning.

## Storage and workers

A PostgreSQL adapter could replace SQLite behind the existing ports when concurrent writers or hosted operation require it. SQL transactions, claim semantics, constraints and snapshot reads must be reimplemented and verified; the port definitions do not make database behavior interchangeable. Migrate organizations, immutable artifacts, legacy admission certificates and authoritative receipts without rewriting identities. Reconcile counts and hashes before switching writers.

Keep exact-subject validation and acceptance in one authoritative transaction. Preserve the read snapshot used to freeze all segment learning. Validate time and lease deadlines at durable boundaries. Use a consistent clock policy, heartbeats for longer work and clear fencing semantics for a worker whose lease expires while inference is in flight.

The current facade serializes commands and uses a per-root file lock. A hosted service must replace that process assumption with database-backed admission and conflict handling. Its separate control store and domain store need explicit reconciliation after partial success. Adding an HTTP load balancer alone would not make the application safe for concurrent service instances.

Inference capacity needs independent controls: organization/run spending reservations, provider rate limits, bounded queues and model compatibility checks. Preserve unknown-call fencing; retries after uncertain spend require investigation or a provider-supported reconciliation contract. The current per-run limits are not a shared organization billing service.

## External effects

The simulator's local transaction cannot commit an agency's remote effect. A delivery integration should persist an authorized dispatch intent and stable external key, then deliver through a worker and reconcile receipts. Define when approval must still be valid: at reservation, at dispatch and/or at provider acceptance. A suppression arriving before remote dispatch must have an explicit blocking rule; one arriving after acceptance requires a cancellation/retraction contract with the agency.

Persist every uncertain state rather than silently retrying. An outbox provides durable intent, not exactly-once delivery by itself. Provider idempotency, receipt matching and operator reconciliation are still required. Preserve accepted history even when a later cancellation succeeds.

## Data, evidence and learning

Replace synthetic source attestations with verified inventory, freshness and completeness contracts. Keep audience records outside model prompts unless an explicit use case and data policy permit them; aggregate context is the current default. Add purpose-specific access, retention, deletion and audit policies before using real customer data.

Evidence operations need ownership, source review, activation, expiry and change handling. The current pack is manually maintained. Automated source monitoring could assist reviewers but must not silently extend evidence validity or rewrite historical contexts.

Real learning needs a defined response event, attribution window, delivery status, independent population and business identity policy. The present Beta prior and recommendation thresholds are illustrative. Evaluate prior sensitivity, drift, delayed outcomes and decision costs before relying on comparisons. A correction/retraction design must update derived support reproducibly without erasing historical records. Repeated exposures need a statistical model rather than relaxing the duplicate-business constraint.

## Reliability and security operations

A hosted pilot needs authenticated authority at every mutation and receipt observation, operational dashboards, alerts for stalled/uncertain work, database backup/restore exercises, retention, incident response and versioned migrations. Audit rows are currently local records, not a tamper-proof audit service. The local browser token is not a user identity, and the loopback server should not be exposed as a public service.

Validate restore behavior across the control store, domain databases and derived exports. Test disk exhaustion, provider outage, queue backlog, clock disagreement and interrupted migrations. Define forward rollout and rollback policy before mixed versions run against shared state; older binaries currently reject newer schemas.

## When to extract a service

Consider extraction only when a measured workload, ownership boundary or release requirement warrants independent operation. Inference execution or rebuildable reporting may be candidates because they can consume stable IDs through narrow contracts. Review/acceptance and cohort finalization have strong atomicity needs; separating them requires a deliberate consistency protocol.

Keep the current public module contracts and invariant tests as migration acceptance criteria. A successful extraction must preserve authority, replay and data identity under failure, not merely reproduce a happy-path demo. See [architecture](architecture.md) and [validation](validation.md).
