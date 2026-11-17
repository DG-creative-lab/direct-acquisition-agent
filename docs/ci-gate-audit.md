# CI gate audit

The original implementation introduced Python 3.11 through 3.14 without a
recorded customer or deployment requirement for that range. CI now uses only
Python 3.14, and the minimum required version is 3.14. Compatibility with other
versions is not currently checked. The full invariant ledger and executable evidence
are in [validation.md](validation.md).

| Check | Protection | Decision |
| --- | --- | --- |
| Backend on 3.14 | Domain behavior, scoped SQLite transactions, restart/replay, approval and final authority, inference budgets and synthetic learning | Keep the full suite in four module partitions on the selected runtime. Other Python versions are not checked. |
| Architecture | Module boundaries, private imports and cycles | Keep once, before backend tests. |
| Mutation catalogue | Audits whether existing regression tests detect deliberately damaged implementations | Manual full audit for the MVP. Run on approval/isolation/lease/replay changes or before release. It is not a routine PR gate. |
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
commit. Add compatibility coverage only when a product or deployment need is
identified.


## MVP gate cadence and Aion comparison, 17 November 2026

The full mutation catalogue duplicated selected backend executions 512 times
per routine CI run, each in a fresh interpreter and temporary source copy.
This assesses test strength; it does not add 512 distinct application scenarios.
The ordinary backend suite already runs the target regression tests. Full
mutation checking now runs only on explicit `workflow_dispatch`; that invocation
runs the four mutation partitions without also repeating backend/browser jobs.
Normal pull requests and main pushes run the four backend and two browser jobs.
Application authority checks, all regression cases and the full catalogue remain.

Run a full audit explicitly for changes to approval, scope isolation, leases or
replay behavior, or before a release. For a pull request, dispatch the audit on
its head branch, not the base branch. Replace the placeholders with the PR number
and its head branch:

```sh
gh pr view <PR_NUMBER> --repo DG-creative-lab/direct-acquisition-agent --json headRefName,headRefOid
gh workflow run ci.yml --repo DG-creative-lab/direct-acquisition-agent --ref <PR_HEAD_BRANCH>
```

After the run completes, compare its `headSha` with the PR's current `headRefOid`:

```sh
gh run view <AUDIT_RUN_ID> --repo DG-creative-lab/direct-acquisition-agent --json headSha,status,conclusion,url
gh pr view <PR_NUMBER> --repo DG-creative-lab/direct-acquisition-agent --json headRefOid
```

The audit is current only when the run succeeded and those commit IDs match.
If the branch changes during or after the audit, run it again on the new head.
For an audit of the already merged release, use `--ref main` and verify the run
against the intended main commit instead.

The successful main run [44033513092](https://github.com/DG-creative-lab/direct-acquisition-agent/actions/runs/44033513092)
used 50m04s of summed runner job time: backend 19m50s, mutation 19m40s and
browser 10m34s. The job window was 6m34s. Moving the mutation audit changes
routine compute cadence, not the runtime authority contract. It removes that
19m40s component from routine runs; the remaining backend/browser work still
needs execution improvements. Summed job time is a compute proxy, not measured
CPU use or a billed charge; GitHub's usage endpoint reported zero billable time.

Aion's inspected workflow runs Python/API tests, lint/architecture checks,
Docker validation and vulnerability scanning; its inspected runs also include
access-contract/composition checks. It does not run this mutation catalogue or
Playwright browser suites. The latest inspected [Aion run](https://github.com/DG-creative-lab/agentic-auth/actions/runs/44036682897)
passed 1,504 tests, versus 1,033 backend tests here. Its summed job time was
11m42s and its test job took 8m41s; the preceding test job took 8m01s.
Those latest wall times are not faster than this app, but Aion uses substantially
less aggregate runner time. Its test portfolio includes many in-memory use-case
tests and session-scoped database fixtures; this app puts many permutations
through complete real-SQLite workflows, including process restart and final
commit checks. Test counts alone therefore do not describe the workload.

The additional browser workload here is 108 cases (49 and 59), exercising real
loopback API workflows. Keep exact displayed-subject, consent, lost-response,
reload and HTTP-boundary regressions. Further browser reductions need a mapping
from each candidate case to retained protection; no browser cases are removed
in this change. Build/type checks and the cheap architecture scan remain useful
PR checks. Formatting is optional policy and is not the main source of delay.
