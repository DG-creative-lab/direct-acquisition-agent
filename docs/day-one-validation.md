# Day one validation and limits

Historical day-one ledger. The 26 October test review corrected the arithmetic of the bounded budget sample to 36 cases. See [current test review](test-coverage-review.md) for the present scope and results.

Verified 25 October 2026 using Python 3.14.3 and SQLite through the standard library. This is the first implementation in an initially empty code workspace, so there is no Git base/head comparison. Review scope covers the CLI, composition root, module contracts, deterministic domain logic, synthetic source and all SQLite writers/readers.

## Protected outcomes and evidence

| Invariant | Independent rule and tested trigger | Evidence status |
| --- | --- | --- |
| I1 Ineligible records never enter mail | Hand-written 18-record fixture: eight exclusions, one holdout, nine mailed; duplicate suppressed record cannot be selected | Confirmed by executable test |
| I2 Population and budget reconcile | Input equals disjoint terminal groups; exact CSV count and cost bounded over 36 seed/size/budget combinations | Confirmed for this bounded set |
| I3 Control and treatment share enrollment | Hand-written scores require all assignments to come from the top ten enrolled businesses; holdout absent from mailing | Confirmed by executable test |
| I4 Organization scope persists | Wrong-scope run read, cancellation, acknowledgement, claim, audience read, draft read/write and export rejected | Confirmed on public adapter/use-case paths; CLI identity is trusted locally |
| I5 Repeated request binds exact inputs | Same key survives restart; changing population under that key conflicts; simultaneous admission yields one run | Confirmed by executable test |
| I6 Stale workers cannot commit | Expiry at the exact boundary, replacement lease and cancellation all reject old completion | Confirmed by executable tests |
| I7 Receipt, lifecycle and event are atomic | SQLite trigger fails event insertion; task/run state and output roll back together | Confirmed with deterministic fault injection |
| I8 Draft replay does not duplicate domain work | Commit draft, lose task receipt, recover lease; exactly one artifact and operation record remain | Confirmed with deterministic fault injection |
| I9 Waiting grants no release authority | Wrong reference rejected; restart preserves waiting; acknowledgement finishes only the dry run | Confirmed by separate-process and persistence tests |
| I10 Work is bounded | Delayed retry stops at attempt cap; repeated crashes exhaust leases; invalid tick/lease limits rejected | Confirmed for modeled limits |
| I11 Version and content drift fail closed | Unknown workflow/database contract, changed catalogue, altered artifact bytes and mismatched operation content rejected | Confirmed by executable tests |
| I12 Modules remain decoupled | Actual import graph is valid; seven deliberate private/outer-layer/dependency violations detected | Confirmed for static import rules |
| I13 Bayesian math counts outcomes | Exact prior/posterior example, sequential/batch equivalence, zero evidence and invalid counts | Confirmed for the pure value; no persistent learner yet |

The invariant set is 13/13 exercised with executable falsification cases within the stated day-one model. This is not coverage of every future requirement. The budget exploration covers 3 seeds × 3 sizes × 4 budgets = 36 combinations. The architecture probe rejects 7/7 selected import violations; no general mutation score is claimed.

Task states queued, running, waiting, succeeded, failed and cancelled are exercised. Selected recovery positions are: lost process after claim; artifact committed before task receipt; state update before event insertion; restart after committed waiting state. External agency effects and network ambiguity are not implemented or tested.

## Reproducible verification

```sh
make test
make arch-check
make demo
```

The suite passed **27/27 tests**, and `make arch-check` passed. It uses `unittest` and real temporary databases. The CLI test launches separate Python processes. Tests do not call model APIs, inspect credentials, send messages, print or contact an agency.

## Operator-visible demonstration

The default 1,000-record seed reconciles to **245 excluded, 74 no-mail, 681 draft recipients**, costing **57,885 pence (£578.85)** against an £850 demo budget. The operation stops waiting for review. These are synthetic execution counts, not marketing results.

Export contains `manifest.json`, `mailing.csv`, and `assignments.csv`. The manifest records scope, snapshot/model/policy versions, creative content hashes, assignment method, counts, money, file hashes and limitations. The database owns exact bytes; no operator-edited CSV becomes authoritative.

## Residual scope

- Only local trusted operators and synthetic data are supported. No hosted identity or organization-admin boundary exists.
- The full LLM loop, live copy generation, editorial review, monetary inference and persistent Bayesian evidence ingestion are future work.
- The checkpoint is an acknowledgement, not an approval. Approval expiry, revocation, shared spend reservations, printing and agency reconciliation belong to day three.
- Completeness and address attestations come from a synthetic source. They must be independently established by a real adapter.
- One-worker operation is the intended topology. Claims were challenged concurrently, but multi-host scheduling, clocks, recovery, contention and migration have not been validated.
- Appended event rows are not a tamper-proof audit service. Direct database modification by an administrator is outside the local application's authority model.
- Large-scale performance, disk-full/backup recovery, schema upgrades beyond v1 and multi-version rollout are untested.
- The test portfolio deliberately avoids claiming that independent module correctness proves the whole product; composed CLI and fault probes provide additional, bounded evidence.
