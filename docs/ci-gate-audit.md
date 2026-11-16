# CI gate audit

The original implementation introduced Python 3.11 through 3.14 without a
recorded customer or deployment requirement for that range. This change removes
3.11 and sets the minimum to 3.12. It keeps the remaining matrix while making
its cost and purpose explicit. The full invariant ledger and executable evidence
are in [validation.md](validation.md).

| Check | Protection | Decision |
| --- | --- | --- |
| Backend on 3.12, 3.13, 3.14 | Domain behavior, scoped SQLite transactions, restart/replay, approval and final authority, inference budgets and synthetic learning | Keep the tests. Per-PR coverage of every supported Python version is a policy choice; no deployment requirement for 3.12 or 3.13 was found. |
| Architecture | Module boundaries, private imports and cycles | Keep once, before backend tests. |
| Mutation catalogue | Measures whether selected tests fail for declared harmful changes | Keep, but an assertion failure is evidence of the asserted contract, not proof of complete coverage. |
| Build and type check | Broken frontend types, imports and production assets | Keep for each isolated browser runner. |
| Browser partitions | Displayed subjects, user decisions, reloads and lost responses against the real loopback API | Keep. One worker per isolated root preserves fixture sequencing. |
| Formatting | Source consistency | Optional quality policy; run once. |
| Timing and browser artifacts | Diagnosis and shard estimates | Keep as diagnostics, not correctness checks. |

New CI gates and runtime versions should document the failure they catch, their
value beyond existing checks, cost and cadence. Offline checks do not establish
live model quality, real delivery, public authentication or universal race
coverage. GitHub's effective main-branch rules had no required checks when
inspected on 15 November 2026; repository settings were not changed.

## Cost and shard estimates

In [PR 87's successful run](https://github.com/DG-creative-lab/direct-acquisition-agent/actions/runs/43738876446),
the slowest backend jobs were 17m15s on 3.11, 12m37s on 3.12, 12m25s on 3.13
and 14m55s on 3.14. Removing 3.11 alone would have left a 14m55s bottleneck.
The 3.12 case timings totalled 1,472 seconds; 37 sequence and sequence-review
cases accounted for about 505 seconds. Those cases exercise expiry, stops,
restart and final authority, but repeatedly reconstruct material.

Shard weights use median module case plus class-setup durations across 3.12,
3.13 and 3.14 from that run. The 20 largest measured weights are retained;
other modules use the per-case fallback. Applying the new allocation to the
recorded costs gives estimated maximum shards of 752s, 722s and 707s
respectively. These are projections, not new CI measurements. The full timing
artifacts were uploaded by that run with a 14-day retention; their expiry limits
independent reproduction. Refresh weights from current artifacts when needed.
Discovery and the CI-tool regression ensure both shards cover the discovered
suite, independent of the weights.

## Mutation evidence

The harness rejects loader, fixture, cleanup and unexpected test-body or subtest
errors. A detection requires an assertion failure with no errors or skips. The
first strict run exposed 48 previously credited experiments. The affected tests
now state expected error contracts, required fields, successful recovery or lock
release at the relevant call. A lock fixture was isolated so the mutation reaches
the lock boundary instead of crashing setup. All 48 were individually rerun;
the subsequent full CI run detected all 511 declared variants.

Some assertions check that a specific wrong error is not returned. They establish
an API or recovery contract; they do not establish that an unauthorized effect
occurred. The wrong-proposal approval probe isolates the binding guard and must fail its
assertion when that guard is removed; separate real SQLite checks retain the
full acceptance path. The unknown-permission case reaches the readiness
assertions before the missing-permission case. Recipient-target and review-order
mutations now reach explicit subject and review-provenance assertions. The
control-arm mutation instead
causes a preparation error, so its detection proves that valid controls must
prepare successfully, not that a control was dispatched. A mutation score
cannot substitute for reviewing behavioral oracles and final authority checks.

Further work should reduce repeated material reconstruction and move pure rules
out of full workflow fixtures, preserving fresh evidence and authority checks at
commit. Consider one primary runtime per PR and scheduled compatibility runs if
later detection on older runtimes is acceptable.
