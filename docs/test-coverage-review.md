# Test coverage review

Reviewed 26 October 2026 using the failure-space and evidence-led review workflows. This is the first repository import. There was no earlier Git commit to compare during the initial review, so the scope was the complete runnable day-one and day-two implementation, not a patch-only review.

## Assessment

The suite provides useful evidence for a local synthetic prototype. It tests real SQLite transactions, restarts across processes, deterministic policy and bounded model integration. It does not establish production readiness or universal claim detection. The day-three addendum below records local approval behavior separately.

The initial 52 tests left several important paths implicit. Nine new tests exercise paid-call races, cancellation during dispatch, lost inference receipts, non-finite clocks and the HTTP transport boundary. The clock probes exposed a defect: a NaN time reading could bypass a lease-expiry comparison in task completion and inference admission. Both paths now reject non-finite time. The HTTP error test also led to closing the error response before returning a sanitized exception.

## Domain and authority map

| Object or boundary | Authority | Evidence status |
| --- | --- | --- |
| Recipient eligibility, holdout and money | Pure campaign rules over the complete synthetic snapshot | Confirmed with literal expected populations and bounded/metamorphic cases |
| Run, task, lease and organization | SQLite task store, scoped queries, atomic lifecycle/event transactions | Confirmed with restarts, concurrency, cancellation and fault injection |
| Exact campaign artifact | Content-addressed manifest and verified stored CSV bytes | Confirmed with tampering and replay probes |
| Inference admission and recovery | Active task lease, atomic reservation, exact request hash and receipt journal | Confirmed for the exercised concurrency/failure schedules |
| Product claims | Manually reviewed official-source pack and exact code-rendered wording | Confirmed for structural/source relations; manual verification remains a trust boundary |
| Semantic screening | Separate model request bound to both variants and the pack | Contract checks confirmed; general semantic accuracy remains unknown |
| Reviewer memory | Organization/segment-scoped preferences frozen per run | Confirmed; no audience conversion is inferred from memory |
| Approval and simulated acceptance | Reviews module and transactional SQLite adapter | Implemented in day three; see the addendum and review ledger |

## Coverage and independent oracles

| Protected behavior | Test evidence and oracle | Limits |
| --- | --- | --- |
| Exclusions and reconciliation | Hand-written 18-record example; 36 budget/size/seed combinations; reversed-input metamorphic check | Not every policy interaction or a live warehouse feed |
| Experiment enrollment | Explicit top-ten cohort membership, holdout outside mailing | Does not prove causal marketing effectiveness |
| Durable task lifecycle | All six states exercised, exact lease expiry, replacement, cancellation, bounded retry | Selected transitions and schedules; no exhaustive state-model exploration |
| Atomic lifecycle and receipts | Event insert failure rolls back task result; receipt write failure preserves uncertain-call fencing | Disk-full, backup restore and power-loss behavior remain untested |
| Paid-call boundaries | One-call budget under two simultaneous reservations; cancellation during gateway completion; oversized input; mismatched receipt token | Local SQLite and trusted caller scope, not multi-node operation |
| Unknown external outcomes | Gateway error and receipt loss each dispatch once; later attempts stop | Reconciliation of an uncertain remote charge remains manual |
| HTTP boundary | HTTP 429, URL failure, timeout, oversized response and redirect rejection | Stubbed transport; TLS/proxy behavior is not tested |
| Grounding | Changed/omitted qualifications, altered copy/pack, missing or swapped paired verdict, evidence expiry before draft | Lexical checks and a same-model critic cannot prove arbitrary prose safe |
| Compatibility | v1-to-v2 database migration, v2 workflow replay, v3 downgrade rejection, historical artifact golden value | No rollback/mixed-version deployment guarantee |
| Architectural boundaries | Actual module graph plus seven deliberately invalid imports | Static imports only |

The budget sample is 3 seeds x 3 sizes x 4 budgets = **36**, correcting the older ledger's arithmetic. The existing semantic critic regression has eight labelled variants, developed alongside the rubric. Its successful recorded result is a regression observation, not held-out accuracy.

## Targeted failure measurements

The nine newly declared failure scenarios have nine executable tests. The non-finite-time scenario checks three clock values across three operations, so **9/9** declared clock/operation combinations reject the action. The transport tests exercise **5/5** selected failure partitions: HTTP rejection, URL failure, timeout, oversized response and redirect.

`make mutation-check` creates temporary source copies and weakens eight controls: task lease expiry, inference clock validation, the reservation budget, uncertain-call retry fencing, worker configuration preflight, retired-workflow admission, durable timestamp validation and the migration write transaction. All **8/8** declared mutants are detected by the targeted tests. The suite separately rejects **7/7** declared architecture violations. These denominators describe selected experiments, not all possible mutations.

Three added call-timeline fault positions are exercised: cancellation during a request, remote response before receipt persistence, and receipt write failure before a repeat attempt. They are **3/3** selected injections, not exhaustive fault-point coverage. Existing tests add other task/artifact recovery positions.

Line coverage was not used as a completeness proxy. No line/branch coverage percentage is claimed. The remaining unmodeled transition, schedule and semantic spaces prevent a meaningful overall completeness percentage.

## Verification and release scope

Run:

```sh
make test
make arch-check
make mutation-check
```

The release includes CI for Python 3.11 through 3.14. Offline tests do not need a model key. The public tree includes portable documentation and a labelled recorded copy example. Credentials, development databases, private research and internal references are excluded.

Before day three, the critical remaining design work is explicit approval authority, an immutable approval subject containing the exact draft and current evidence, rejection of stale or superseded subjects, and tests at the approval/use boundary. Current checkpoint acknowledgement grants no release authority and must not be relabelled approval.

## Follow-up review: three P2 findings

The local review found three real gaps despite the first green suite. Ten additional regression tests brought the suite to **71**. The old test that created a fresh v2 workflow is now an admission-rejection test; compatibility is tested using genuine persisted schema-v2 rows created before the current application opens the database.

| Finding | Enforcement | Regression evidence |
| --- | --- | --- |
| Wrong worker configuration terminally failed a resumable run | Atomic claim-time compatibility check, including expired-lease recovery | Missing model, changed model/limits/tool choice and repeated worker invocations preserve attempts and state; correct worker resumes; compatible offline work is not starved; CLI reproduction covered |
| Legacy registration allowed fresh ungrounded v2 work | New retired-capability admission rejected; schema-v3 migration freezes existing organization/run/plan hashes and checks them before legacy execution | Actual pre-migration records resume, matching replay returns the same run, fresh v2 admission fails, restart does not certify new rows, and coordinated plan/hash changes cannot reuse a certificate |
| Infinite creation/acknowledgement times stranded tasks | Finite timestamp checks before mutation and finite derived lease/retry deadlines | Creation, acknowledgement and cancellation reject non-finite inputs without state/event changes; a finite clock still resumes valid work; overflowing lease expiry is rejected |

The migration's table creation, admission snapshot and version change are transactional. A fault during snapshotting rolls back the cutoff and a subsequent clean migration resumes the original legacy run. Existing terminal or malformed records are not silently rewritten. The certificate is local database state, not a tamper-proof service against an administrator who edits the certificate itself.

No paid live-model regression was rerun for these storage and scheduling changes. Offline tests exercise the actual CLI, worker, SQLite boundaries and model contracts with deterministic doubles. The seven selected mutation probes include the three new enforcement boundaries. General model quality, production topology and approval authority remain outside these checks.

## Concurrent initialization follow-up

The next review reproduced a migration race that the earlier tests missed. Version discovery occurred outside the migration lock, so a second initializer could use a stale version and reapply an older script after the first reached schema v3. The version marker could fall back to 2 while the admission table remained present, preventing subsequent opens.

The constructor now acquires `BEGIN IMMEDIATE` before reading the version. All migration statements, the legacy admission snapshot and version changes share that transaction. Migration scripts no longer contain their own transaction boundaries, and production initialization executes complete statements individually to avoid `executescript` committing the outer transaction. A known stale-marker state is repaired by preserving the original admission table and restoring version 3, never by refreshing the admission cutoff.

Four additional tests initially brought the suite to **75**:

- A controlled two-connection interleaving starts from versions 0 and 1. Both initializers succeed; each version read occurs inside a transaction, and the second observes version 3. The same test against commit `4cf912f` reproduces the reported table-already-exists error for both starting versions.
- Two separate Python processes initialize the same database from versions 0 and 1. Both exit successfully; repeated opens retain version 3 and pass SQLite integrity checks.
- An injected failure at the final migration rolls back all preceding migrations and version changes, preserving the original version 0 or 1. A clean retry succeeds.
- The earlier damaged version-2/schema-3 state is reopened successfully, while later records remain outside the original legacy admission snapshot.

The additional mutation removes the constructor's write transaction and is detected by the whole-chain rollback test. This is **8/8** selected mutations in total. These bounded schedules establish local initialization behavior, not multi-host operational readiness. No paid model calls were made.

The first CI run then caught another contention point on Python 3.13: post-migration WAL activation returned `SQLITE_BUSY`. The schema remained valid, but one initializer failed. WAL activation now retries only busy errors on fresh connections until a ten-second deadline, using a short per-attempt busy timeout. It never repeats schema migrations. Two more tests force a busy result followed by success and verify that deadline exhaustion and unrelated I/O errors are not hidden. The current suite has **77 tests**. This records the CI-discovered failure and its fix rather than treating a rerun as evidence of correctness.

## Day-three addendum

The suite now has **108 offline tests**, including 27 review cases and four CLI/migration cases. The [day-three ledger](day-three.md) records exact-subject approval, stale authority, revocation, suppression, copy replacement, actor generation, expiry, artifact integrity, transaction faults, selected races and process replay. Four additional mutation probes bring the declared set to **12/12 detected**. The review report was inspected at desktop and mobile widths. No paid model regression was run. Earlier counts and schema-v3 references above describe their historical review stages; current initialization reaches schema v4 while preserving the original legacy cutoff. Local configured identities and a simulated agency do not establish hosted authentication or remote delivery guarantees.

## Day-four addendum

The suite now contains **133 offline tests**. Twenty-two learning tests and three CLI/migration tests cover exact counts, analytic prior-quantile references, pending/mature completeness, assignment and scope substitution, deduplication, conflicting observations, concurrent finalization/imports, storage faults and process replay. New copy contexts freeze mature synthetic memory without altering prior contexts or approval records. The [day-four ledger](day-four.md) records the bounded evidence and statistical assumptions. Five new mutation probes bring the selected set to **17**; the first maturity mutant revealed a masked test because completeness also blocked finalization, so a complete-but-immature regression now isolates that boundary. Schema v5 preserves review state and the original legacy cutoff. All outcomes remain synthetic, and no paid model requests were made.

## Day-four local review follow-up

Two P2 findings added two independent regressions, bringing the suite to **135 offline tests**. Model contexts now freeze all segment learning from a single read transaction; a forced finalization after the snapshot read cannot split the evidence. Semantic finalization replay persists only a new command receipt, preserving the original effect actor, timestamp and event count, including after restart. Opening an existing cohort follows the same receipt-only rule. Both regressions fail against `fe28c3d`, and two additional targeted mutation probes bring the selected set to **19**. Historical events are preserved rather than rewritten. No paid model requests were made.

## Day-five interface addendum

The current suite has **149 Python tests**, including 14 workspace tests, plus strict TypeScript/build and formatting checks. The real HTTP tests reject wrong Host/token/Origin, bounded-input violations and static traversal. Facade tests cover stale review, suppression/rebuild, replay after metadata loss, exact displayed-subject downloads and future experiment memory without inherited approval. Three additional targeted mutants bring the selected denominator to **22**. Desktop/mobile browser verification covers the real UI/API/persistence journey. This does not establish hosted authentication, remote deployment or live model quality; gateway doubles were used for inference tests, with no paid calls.

## Interface local review follow-up

The three P2 findings in `5b6031b` added two raw-HTTP tests and eight executable frontend regressions. The suite now has **151 Python tests**, the original **22 targeted mutation checks**, strict TypeScript/build/formatting checks and **8 frontend regressions**. Absolute-form GET/POST requests are rejected before routing. Client tests lose actual committed approval responses, interpose another review command and verify that retry neither appends another approval event nor overrides the later rejection. They also cover reordered fields, pending-key migration and storage failure before dispatch. Chromium asserts document/client width equality at 390px and 1440px. Both raw-HTTP cases and the original frontend's replay/mobile defects are reproducible against `5b6031b`. No paid model requests were made.
