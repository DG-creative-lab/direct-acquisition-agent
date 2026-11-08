# Requested scope evaluation for issue 25

The unchanged acceptance corpus passes **10/12**, compared with the preserved corrected baseline of **6/12**. All four previously false readiness cases now produce completed unsupported results with no campaign and zero provider calls. All three supported journeys still pass. Issue 25 remains open: the ambiguous and relative-budget cases still exhaust their scripted invalid planner responses instead of producing the required clarification. Remaining typed conversational prepare/follow-up routing is also deferred.

Paid inference remains paused. All gateways in this evaluation are fake, outbound socket connections are disabled, and restored workspaces remain inspection-only.

## Reproduction and attribution

```sh
python3 scripts/evaluate_conversational_agent.py --output /tmp/issue-25-scope-results.json
```

The command exits 1 while any acceptance expectation fails. It did so for the two budget cases; a failed planner is not a passing negative case. The runner, corpus and grading oracle are unchanged from merged PR 50.

The [raw v2 report](issue-25-requested-scope-results.json) evaluates committed source `fe6d94e3c22a1e9699fa4322ad607b344aceb34a` at `2026-11-08T07:55:56.126481+00:00`. All 184 source, test, script and configuration inputs match committed blobs and remain stable across the run. The content-set SHA-256 is `613fc1f123a3428ec677150a91b3c62e86c0c7b1a649099917bf08df7773684a`. The report's per-file fingerprints cover actual imported source and fixtures. Later commits adding this report do not change those evaluated inputs.

Corpus SHA-256: `630348cba3fd2a2d6738cb5601dc0ecd42bd3c0cf26e9a8279f1365328b3bc64`. Runner SHA-256: `1d66cc892850c0b9a244eaccfc1be9e85502f37cf3f05817444e18cd8385ac5f`. The [original integrated report](issue-25-offline.md) and both earlier raw reports remain immutable historical evidence.

## Observed outcomes

| Scenario | Result | Completed outcome or failure category | Fake calls |
| --- | --- | --- | ---: |
| inventory-supplier-timing | Pass | brief_proposal | 6 |
| contractors-milestone-costs | Pass | brief_proposal | 10 |
| combined-separate-framing | Pass | brief_proposal | 13 |
| unsupported-email | Pass | unsupported | 0 |
| unsupported-france | Pass | unsupported | 0 |
| unsupported-personal-mortgage | Pass | unsupported | 0 |
| unsupported-lending-decision | Pass | unsupported | 0 |
| missing-budget | Pass | clarification | 1 |
| ambiguous-budget | Fail | planner_failure | 2 |
| relative-budget-correction | Fail | planner_failure | 2 |
| verified-fixture-and-restore | Pass | boundary_pass | 0 |
| uncertain-stop-restart | Pass | boundary_pass | 1 |

There are **zero false acceptances, zero false rejections and zero infrastructure failures** in this bounded corpus. The two planner failures remain failures. Missing-budget clarification, verified fixture/restore behavior and uncertain-call stop/restart replay pass. No retry adds a call to an uncertain outcome.

The supported journeys retain all seven required machine checks, distinct inventory/contractor copy, exact unapproved subjects, source selection, separately confirmed preferences and history, copy-revision consent, praise without approval, explicit review and simulation-only acceptance, complete synthetic learning, frozen advisory follow-up evidence, restart replay and a confirmed £512 amendment. Inspection and receipt replay add zero calls. Their fake-call counts are unchanged at 6, 10 and 13; encoded requests total 47,731, 80,325 and 102,709 bytes. Local wall times were 18.438, 34.871 and 37.127 seconds under concurrent suite load. These are local control observations, not a production latency benchmark or provider pricing measurement.

## Interpretation and next acceptance work

The new [scope contract](../requested-campaign-scope.md) freezes literal requirements with source evidence before planning. Readiness, publication, review and simulator acceptance reconcile those requirements with native sources and actual delivery scope. Tests additionally challenge scope removal, changed headers, rehashed foreign provenance, legacy records, source mutation during writes and follow-up inheritance.

Recognition is a bounded vocabulary and explicit-label resolver. These results establish enforcement for the authored literal scenarios, not general natural-language understanding, semantic model quality or editorial effectiveness. Unknown paraphrases outside the vocabulary remain an evidence gap. Declared capability defaults are displayed and distinct from explicit user intent.

The next issue-25 slice should produce meaningful clarification for ambiguous and relative budgets, then complete typed prepare/next-experiment action and target coverage. Rerun the unchanged acceptance corpus before considering closure. No live semantic evaluation is authorized by this result.

## Control checks

All 10 jobs in [Actions run 42460782347](https://github.com/DG-creative-lab/direct-acquisition-agent/actions/runs/42460782347) pass on the evaluated implementation commit: 799 backend tests in each full Python 3.11 through 3.14 matrix, split into 399/400-test groups, architecture checks, 89 browser tests with build/formatting, and all 342 declared harmful mutation probes. All five new scope variants are detected.

The final local focused suite passes 11 real-SQLite/domain regressions and architecture checks pass. The browser scope scenario passes on desktop and mobile with reload, declared defaults and zero-call unsupported outcomes. The initial local `make interface-check` run passed build/formatting and 88/89 browser tests; `knowledge sources and frozen planning guidance are inspectable` exceeded its five-second wait while the review checkpoint was still queued. An isolated rerun passed, and CI's complete 89-test run passed. The initial failure is not presented as a clean local suite pass.

The full local backend and mutation runs were also invoked; CI above is the completed full-suite evidence for the exact committed implementation. Control-suite success does not turn the two remaining acceptance-corpus failures into passes.
