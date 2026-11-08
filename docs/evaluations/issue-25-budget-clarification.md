# Budget clarification evaluation for issue 25

The unchanged offline acceptance corpus passes **12/12**, up from the preserved scope run's **10/12**. The ambiguous and relative-budget cases now finish with genuine budget clarifications, null totals, no campaign and zero provider calls. All three supported journeys and the four scope rejections still pass. There are zero false acceptances, false rejections, planner failures, infrastructure failures or live provider calls in this bounded corpus.

Issue 25 remains open. Typed conversational prepare/next-experiment actions and target coverage still need implementation, followed by a final acceptance reconciliation on merged main. Passing these 12 scripted scenarios does not establish general semantic model quality or complete every issue-25 acceptance condition.

## Attribution and reproduction

```sh
python3 scripts/evaluate_conversational_agent.py --output /tmp/issue-25-budget-results.json
```

This run exits 0. Neither the checked-in corpus nor the evaluator/grading oracle changed. Its existing oracle still requires the expected completed clarification/unsupported outcome, a topical response and no campaign. The evaluator regression now separately injects invalid planner responses on a missing-budget request and requires a real planner failure, preserving the distinction from successful clarification.

The [raw v2 report](issue-25-budget-clarification-results.json) evaluates committed source `055b22c15cdb377326aea33ae210ba426dc107a3` at `2026-11-08T10:04:59.531283+00:00`. All 187 source, test, script and configuration inputs match committed blobs and remain stable across the run. Source-content SHA-256: `9958a8d4e57d2ed1c2de87a94d0e9a914db9e998fb7c12b852afd9102c4adc35`. The raw report retains per-file hashes and Git status. A later report-only commit does not alter those evaluated inputs.

Corpus SHA-256: `630348cba3fd2a2d6738cb5601dc0ecd42bd3c0cf26e9a8279f1365328b3bc64`. Runner SHA-256: `1d66cc892850c0b9a244eaccfc1be9e85502f37cf3f05817444e18cd8385ac5f`. [Earlier scope results](issue-25-requested-scope.md) and earlier integrated reports remain unchanged historical evidence of their recorded commits.

## Recorded outcomes

| Scenario | Result | Completed outcome or boundary category | Fake calls |
| --- | --- | --- | ---: |
| inventory-supplier-timing | Pass | brief_proposal | 6 |
| contractors-milestone-costs | Pass | brief_proposal | 10 |
| combined-separate-framing | Pass | brief_proposal | 13 |
| unsupported-email | Pass | unsupported | 0 |
| unsupported-france | Pass | unsupported | 0 |
| unsupported-personal-mortgage | Pass | unsupported | 0 |
| unsupported-lending-decision | Pass | unsupported | 0 |
| missing-budget | Pass | clarification | 1 |
| ambiguous-budget | Pass | clarification | 0 |
| relative-budget-correction | Pass | clarification | 0 |
| verified-fixture-and-restore | Pass | boundary_pass | 0 |
| uncertain-stop-restart | Pass | boundary_pass | 1 |

Supported inventory, contractor and combined-audience journeys retain all seven required machine checks, exact unapproved subjects, separately confirmed writing preferences, copy revision consent and identity, praise without approval, explicit review and separate simulation-only acceptance, mature synthetic learning, advisory follow-up evidence, a confirmed £512 amendment and restart replay. Inspection and receipt replay add no calls. Their fake call counts remain 6, 10 and 13, with 47,731, 80,325 and 102,709 encoded request bytes. Local elapsed seconds were 6.745, 10.123 and 13.656 under concurrent control-suite load. These are local harness measurements, not provider latency, billing or customer performance.

The missing-budget scenario retains its ordinary one-call model clarification. Recognized ambiguous/relative amounts are diagnosed by the new frozen literal policy before dispatch. Generic failures, malformed planner output and uncertain provider outcomes are not converted to passing clarification results. The verified fixture/restore case leaves restored bytes unchanged; uncertain-call replay adds no calls.

## Reply and recovery checks

The corpus above measures the original held-out tasks. Separate real SQLite tests exercise the reply journey: a typed budget question, one user-confirmed absolute GBP total, exact native question and source bindings, shared allowance, one new revision and one unapproved campaign. A bare number asks again without inference. A fresh process resumes the original admitted reply preparation, while exact replay preserves the historical question and does not repeat calls. Foreign/changed targets, conflicting keys and concurrent replies are rejected; source/question/reply changes after transaction writes roll back.

Mobile browser tests reload before answering and drop either a committed reply response or a preparation response. They retain the original request keys and require one new revision, one campaign at £400, zero routing calls for the reply and truthful usage after reload. Planning, copy consent, review and simulated acceptance remain separate authorities. See [budget clarification](../budget-clarification.md) for the precise partial-admission and compatibility boundaries.

## Control verification

Architecture checks, 63 focused backend tests, the six evaluation regressions and all eight new harmful mutation probes pass. Local `make interface-check` passes build/formatting and all 92 browser tests. An initial targeted browser assertion matched both the chat brief and artifact review's budget; the final test scopes that assertion to the brief and the complete suite passes.

The first broad backend run had loaded the old evaluation expectation that ambiguous budgets fail. It was interrupted after updating that regression and proving that injected invalid planner output still fails. The complete final backend run and PR CI are the remaining in-progress gates at report publication; their final results are recorded in the PR. Paid inference remains paused and restored workspaces remain inspection-only throughout.
