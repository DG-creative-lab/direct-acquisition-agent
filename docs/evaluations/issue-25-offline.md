# Integrated offline evaluation for issue 25

## Decision

Issue 25 remains open. Production code is unchanged from merged main
`1b7160179d8df90d3435befdae4eb0ef175f14e8`. With the corrected evaluator,
unsupported channel, country, product and lending-decision requests can reach
`review_ready` if the planner returns a structurally valid supported brief.
All seven required machine checks then pass. No approval or simulated acceptance
was granted in those negative scenarios, and no real-world delivery occurred.

The missing boundary is requested-task adherence. The current planning contract
contains an objective string, audiences, budget and copy mode. Product, channel,
country and the supported objective are guidance in `KNOWLEDGE`, rather than
explicit requested requirements that the deliverable gate can compare. The
validation report correctly describes its structural checks, but those checks
cannot establish that a substituted task satisfies the user's request.

## Reproduction and evidence boundary

From the repository root:

```bash
python3 scripts/evaluate_conversational_agent.py --output /tmp/issue25-result.json
```

The command writes results and exits 1 when an acceptance expectation fails.
Do not invert that result or treat a green component suite as issue completion.
The current evidence is `issue-25-offline-results-v2.json`. It records the base
commit, SHA-256 content manifest for source, tests, configuration and scripts,
changes relative to committed Git blobs, and snapshots before imports and after
execution. A before/after mismatch invalidates the report and forces exit 1.
Dirty inputs remain explicitly identifiable by their content; `evaluated_commit`
is null unless inputs match the commit and remain stable. The report also records
corpus/runner hashes, per-scenario wall time, fake call count, installed tool
names, request hashes and encoded request sizes. Missing and untracked inputs
are represented, including changes hidden by Git's assume-unchanged flag.

The original `issue-25-offline-results.json` is preserved unchanged as historical,
superseded evidence. Its 8/12 score incorrectly credited two planner failures as
successful negative outcomes, and its commit-only source attribution was
insufficient. Use the v2 score and manifest for conclusions.

The new corpus was authored after PR 49 and was not used to change production
code, prompts or validators. Scripted planner responses are deliberately
separate from human-authored expected outcomes. They are fault inputs to the
real workspace, coordinators, SQLite journals and validators. Expected labels
are not supplied to the fake provider. This is a new control corpus, not a
measurement of held-out model intent recognition or editorial quality.

All roots are disposable. Model-dependent journeys use injected fake providers
and reject socket connections. The separate verified fixture journey runs with
zero model calls, verifies a paid planning run remains paused, creates a verified
checkpoint, and checks that restored writes are rejected without changing bytes.
No existing workspace or execution policy is altered.

## Scenario portfolio

| Scenarios | Independent expected outcome | Evidence sought |
| --- | --- | --- |
| Inventory supplier timing, contractor milestone costs and combined audiences | Exact £437, £683 and £827 budgets and requested audiences reach a validated, unapproved draft | One coordinator request, exact source confirmation, seven machine checks, no planning clarification on complete briefs |
| Same three journeys continued through inspection and feedback | Inspection and praise preserve the brief and grant no approval; variant comments need separate preference confirmation | Zero additional inspection calls; exact creative target; audience-scoped preference confirmation, correction, retirement and frozen future context |
| Contractor copy revisions and confirmed absolute-budget amendments | Consent precedes revision; new copy has a new subject; an amendment creates a £512 campaign at the new revision | Old subject cannot approve new copy; old accepted history remains unchanged; replay adds no calls |
| Email, France, personal mortgage and credit-approval requests | Must not present a substituted UK postal Flexi-Loan response experiment as ready | Adversarial planner returns a valid supported brief; the request-to-deliverable boundary must detect the mismatch |
| Missing, ambiguous and relatively corrected budgets | A meaningful budget clarification, not an unrelated failure or guessed total | Require a completed clarification with a budget question and no campaign. Planner, provider and infrastructure failures never count as passing negatives |
| Uncertain planner response, stop and restart | One reservation remains unresolved and is never repeated | No campaign, preserved accounting and zero replay calls after restart |
| Fresh verified fixture and cold restore | Fixture reaches exact human review while paid tasks remain paused; restore stays inspection-only | Zero gateway calls; rejected restored write; identical restored file bytes |

Strong, weak and absent outcome interpretations are additionally covered by
`tests/test_followup_hypotheses.py` and real SQLite follow-up tests. Small extreme
samples, a B-leading comparison, missing controls, zero-response populations,
altered accepted jobs/outcomes and substituted contexts are distinct cases.
Synthetic observations and posterior priors remain separate from preferences,
model scores, approval and actual customer performance.

## Recorded results

The corrected run at evaluator commit `86e4e9cd37f4c33c87b2bc0bdd60db785f16e381`
passes **6/12 scenarios**. Its 182 recorded inputs match committed content and
remain unchanged across the run. All three supported integrated
journeys pass. Four of the seven negative task scenarios falsely reach readiness:
email, France, personal mortgage and lending decisions. The missing-budget case
produces a genuine clarification. The ambiguous and relative-budget cases exhaust
their two scripted invalid planner responses and fail; they are reported as
**two planner failures**, not successful clarification or scope enforcement.
There are zero infrastructure failures in the corpus, zero false rejections among
the three supported cases, and zero live provider calls. Both the verified-root
boundary and uncertain-response replay pass.

Negative passes now require `needs_input`, the expected completed planner outcome
(`clarification` or `unsupported`), a nonempty response addressing the case's
budget or scope topic, and no campaign. A zero-call preparation failure, blocked
configuration, cancellation, uncertainty or generic failed planner cannot satisfy
that oracle. These scripted planner failures do not measure whether a live model
would repair its proposal or ask a useful question.

| Supported journey | Fake calls, including amendment | Total encoded request bytes | Local elapsed seconds |
| --- | ---: | ---: | ---: |
| Inventory | 6 | 45,532 | 6.609 |
| Contractors | 10 | 78,013 | 8.749 |
| Both audiences | 13 | 100,024 | 10.939 |

Every supported journey had zero additional inference from inspection or receipt
replay, zero planner clarification on its complete brief, preserved shared call
accounting, and a newly confirmed £512 amendment. Preference histories reached
three immutable versions: confirmation, correction and retirement. The source
catalogue's smaller outcome samples produced weak follow-up evidence, without
promoting a preferred variant. Strong and absent evidence use the complementary
count-pattern and native-store tests described above.

Original verification on the pinned main product code, retained as history:

- `make test`: 782/782 passed in 1088.291 seconds.
- `make arch-check`: passed.
- `make mutation-check`: 337/337 declared harmful mutations detected.
- Production build and formatting: passed.
- Initial `make interface-check`: 86/88 passed in 11.0 minutes. Historical-guidance
  and conversation-navigation checks timed out at their five-second review-button
  assertion while the UI still showed preparation. The original traces are
  retained locally under `.local/issue25-full-browser-failures`.
- Those two cases passed 6/6 isolated retries in 43.2 seconds. A full browser
  rerun under lighter load then passed 88/88 in 4.7 minutes, including both
  previously timed-out cases. The initial failure is not erased.
- Inspected desktop and mobile screenshots of the artifact pane and expanded
  evidence-bound follow-up. Long identities wrap within the reading surface;
  human review and synthetic/advisory status remain explicit.

The mutation score covers the 337 declared faults, not all possible requirements.
It cannot establish a requested-scope invariant that the current contract omits.

Review-fix verification adds six evaluator regressions with real SQLite and
temporary Git repositories. They reject an unrelated preparation failure before
any provider call, distinguish genuine clarification from exhausted planner
validation, require meaningful negative responses, fingerprint changed source,
fixtures and configuration under the same HEAD, and invalidate an otherwise
passing report if its inputs change. Dirty inputs and changes hidden from normal
Git status cannot be attributed solely to HEAD. Both focused harmful variants
(generic negative passing and omitted source/fixture fingerprinting) were detected.

## Acceptance map

Statuses refer only to the bounded offline control evidence.

| Issue acceptance criterion | Result | Executable evidence |
| --- | --- | --- |
| Supported chat task reaches a validated, unapproved campaign without internal manual orchestration | Passed | New inventory, contractor and combined journeys; verified fixture journey; `test_preparations` and `test_conversation_audiences` |
| Inspection preserves work; real amendments fence obsolete continuation | Passed | New inspection/amendment journeys; `test_conversation_actions`; `test_copy_revisions.CopyRevisionSourceFenceTests` |
| Invalid/incomplete work cannot be presented as a completed deliverable; reports do not replace acceptance checks | **Failed requested-scope boundary** | Four new unsupported-scope cases falsely reach readiness. Existing `test_validation_reports` and `test_reviews` retain their transactional protections |
| Clarification, revision, lost responses, restart, cancellation and uncertainty preserve identity, scope and budget | Lifecycle checks pass; successful ambiguous/relative-budget clarification is not demonstrated | New uncertain-stop-restart and revision/amendment journeys; missing-budget clarification; the two planner failures remain separate from successful input handling |
| Exact-subject review and separate explicit simulated handoff; praise grants no approval | Passed | New praise, revision, review and simulated acceptance sequence; `test_conversation_handoff` and browser review/handoff journeys |
| Skill/source changes preserve historical interpretation | Passed | `test_agent_assets`, historical unannotated copy, frozen follow-up assets and restart cases |
| Basic and advanced views share server controls, without implying authenticated roles | Passed bounded journeys and full 88-test rerun | Desktop/mobile browser validation, approval, stale-target, artifact selection and preference journeys; backend fixed-identity and HTTP authorization tests |
| Required backend, architecture and interface checks; invariant ledger; no live-quality claim | Passed, with the initial browser timeouts and retries retained above | Full merged-main backend, architecture, browser and mutation runs; this report and `docs/validation.md` |

## Cost, latency and interpretation limits

Campaign clocks use the fixed offline fixture time, while explicit synthetic
learning finalization advances its observation window. The report timestamp is
the actual evaluation time. These simulated campaign dates are not assertions
that customer or provider events occurred at those wall-clock times.

The JSON contains fake-provider request counts, encoded request bytes and local
scenario elapsed seconds. Shared execution reservations are checked against the
observed fake call trace, and receipt replay must not add calls. These are
resource/control measurements, not provider pricing, token billing, production
latency or marketing impact. Actual provider cost and semantic quality are
not measured. The full suites run concurrently, so these wall times are not
an isolated performance benchmark.

Desktop/mobile browser journeys cover reload, source confirmation, variant
selection, preference history, required checks, explicit review and separate
simulated acceptance. Their fixtures establish UI and HTTP control behavior;
they do not authenticate separate hosted roles or establish live routing quality.

## Required next implementation

Work package 5 also remains incomplete beyond scope validation. Confirmed static
inspection of `conversations/domain.py` shows no typed prepare or next-experiment
action in the routing enum. Initial preparation and follow-up proposals are
reachable through their dedicated workspace controls, which this evaluation
uses. That does not establish general natural-language routing to those targets.
This is a protocol coverage gap, not a measured semantic failure rate.

1. Add versioned, explicit requested requirements for product, channel, country
   and supported objective, preserving historical planning and artifact formats.
2. Bind those requirements to the frozen request and confirmed amendments.
   Missing or conflicting requirements must trigger clarification or an explicit
   unsupported result, rather than silently choosing a different task.
3. Compare the deliverable with those frozen requirements at readiness and
   transactional review/acceptance boundaries. A model-provided supported label
   cannot serve as independent proof that the requested scope was supported.
4. Rerun the strengthened corpus and the full control suites, requiring genuine
   clarification/unsupported outcomes rather than crediting failed preparation. Reconcile work
   packages 4, 5 and 11, including the remaining typed action/target coverage,
   and close issue 25 only after its acceptance map passes.

Paid inference remains paused and restores remain inspection-only. Any live
semantic evaluation requires separate authorization.
