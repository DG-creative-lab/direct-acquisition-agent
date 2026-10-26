# Day four: persistent synthetic outcome learning

Implemented 26 October 2026 on `feature/bayesian-outcome-learning`. This extends the existing learning module, keeping runtime, campaign selection, reviewer preferences and approval separate.

## Run the demonstration

```sh
PYTHONPATH=src python3 -m acquisition --db .local/day-four.sqlite demo-learning --out .local/day-four
```

Open `.local/day-four/learning.html`. The command also writes a pending report, outcome JSON, a learning JSON projection and the earlier review demonstration. It uses scripted reviewer decisions, simulated acceptance, synthetic response labels and a simulated 28-day clock. It does not wait 28 real days or claim real customer performance. Its deterministic organization is separate from the operator's organization. No model key or model requests are needed.

The default experiment enrolls 754 businesses: 680 simulated mailing recipients and 74 no-mail controls. The seeded labels produce 94 responses. Early positive results leave beliefs unchanged. Once the simulated window closes and all explicit outcomes exist, finalization writes six beliefs, one for each segment/arm pair. Replaying the demonstration returns the same finalization receipt without counting outcomes again. Synthetic labels deliberately favor A to demonstrate the recommendation path; this is not evidence that A is effective.

The simulated clock is confined to this demonstration. Ordinary learning commands use the application's current clock and expose no backdating option. The demo starts inside the checked fixture pack's review window; the later outcome calculation observes historical accepted work without renewing an expired approval.

## Operational contract

| Object | Authority and invariant |
| --- | --- |
| Accepted experiment | Existing simulated acceptance receipt and verified saved draft. A proposed or merely approved campaign cannot open a cohort. |
| Cohort membership | All frozen assignments, including no-mail controls. Rows reconcile with manifest counts, exact creative assignments and CSV hashes. The import does not define its own denominator. |
| Observation window | Fixed interval from simulated acceptance to 28 days later. Positive response timestamps satisfy start <= time < end. |
| Explicit non-response | Boolean false with timestamp exactly at the window end, imported only once that time has arrived. Missing rows stay unknown. |
| Outcome identity | Organization, cohort and business. Assignment metadata must match. Identical observations deduplicate across batches and request IDs; contradictory observations fail. |
| Maturity and completeness | Finalization requires the closed window, an exact complete-through attestation and one explicit result for every assigned business. |
| Statistical support | Integer trials and successes from finalized cohorts. Preferences, scores, critic verdicts, approval and persona judgments add no trials. |
| Atomic update | Belief rows, finalization marker, outcome/count digests, audit event and command receipt commit in one SQLite write transaction. |
| Independence limit | A business may join only one learning cohort per organization, including controls. Repeated exposure is rejected instead of being counted as a new independent trial. |
| Recommendation | Advisory comparison within the same randomized cohort and segment. No automatic copy, targeting, budget or approval mutation. |

The local configured operator role is checked inside each mutation transaction. It remains trusted local administration rather than hosted authentication. The active role check occurs even when returning a cached command receipt. Receipt replay observes historical work; it does not repeat an update or renew authority. A new request ID observing an already finalized or opened cohort persists only its command receipt, without emitting another effect event or changing the original actor/time.

A finalized cohort is immutable. Late corrections, data retraction, recurrent exposures, contamination between experiments, delivery confirmation and real data feeds need further design. The current implementation deliberately rejects conflicting updates. Do not use it as a production outcome warehouse. A real feed needs an independently verified completeness watermark and data-quality policy; a local synthetic attestation cannot establish those facts.

## Manual commands

Use an existing accepted case from day three. The same database and organization must contain the configured operator and that case.

```sh
PYTHONPATH=src python3 -m acquisition --db .local/manual.sqlite --organization demo-org learning-open --case CASE_ID --actor operator --request-id cohort-1
PYTHONPATH=src python3 -m acquisition --db .local/manual.sqlite --organization demo-org learning-show --cohort COHORT_ID --html .local/manual/learning.html
PYTHONPATH=src python3 -m acquisition --db .local/manual.sqlite --organization demo-org learning-import --cohort COHORT_ID --actor operator --request-id batch-1 --file synthetic-outcomes.json
PYTHONPATH=src python3 -m acquisition --db .local/manual.sqlite --organization demo-org learning-finalize --cohort COHORT_ID --actor operator --request-id finalize-1 --complete-through WINDOW_END_TIMESTAMP
```

The open receipt prints the cohort ID and exact window-end Unix timestamp. Split imports into at most 10,000 rows and 4 MiB per CLI file. The whole batch is atomic. Reordering rows with the same request ID is equivalent; changing its inputs conflicts. All batches must use this exact envelope:

```json
{
  "schema": "synthetic-outcomes/v1",
  "mode": "SYNTHETIC_ONLY",
  "cohort_id": "COHORT_ID",
  "outcomes": [
    {
      "business_id": "BUSINESS_ID_FROM_ASSIGNMENTS",
      "segment": "inventory",
      "arm": "A",
      "creative_id": "EXACT_CREATIVE_ID_FROM_ASSIGNMENTS",
      "response": true,
      "observed_at": 1793000000
    }
  ]
}
```

The illustrative timestamp must be replaced with a valid timestamp inside that cohort's window. Control rows have arm `no_mail` and an empty creative ID. Negative rows use `false` and the exact window end. Labels must be booleans rather than scores. The importer refuses other modes, unknown businesses, substituted assignments, duplicate business rows in a batch, future events and out-of-window observations.

The report is a read-only projection with no approval controls. It shows pending counts, mature posterior support, uncertainty, comparison rules and provenance. Saved files can become stale; regenerate them with `learning-show`.

## Bayesian calculation and recommendation policy

Each segment/creative group starts with the illustrative Beta(1,19) prior, with mean 5% and prior concentration 20. This is a demonstration choice, not a calibrated prior. With n trials and s responses, the posterior is Beta(1+s,19+n-s). Mean and standard deviation are computed from those parameters. Exact counts and parameters are persisted.

A recommendation draws 10,000 samples from each treatment and its segment's no-mail posterior. A fixed seed from the cohort, segment and algorithm version makes repeated reads reproducible on the same Python runtime. Samples estimate central 90% intervals and probabilities for A versus B and the chosen variant versus control. Runtime changes can change Monte Carlo samples; this is an advisory projection, not an exact analytical probability or durable authority. Extreme probabilities are displayed as bounds rather than apparent certainty.

The next-experiment rule requires at least 30 observations per treatment and 10 controls, estimated probability >=90% of beating the other variant and >=95% of beating control. Otherwise it recommends collecting more evidence. Missing treatment/control strata produce no comparison. These thresholds are explicitly illustrative. They do not account for every campaign decision cost, multiple testing, delivery failure, delayed attribution or population drift.

Response lift refers only to the fixed randomized, high-propensity selected cohort. It is not a general population forecast, revenue forecast or profit estimate. The outcome window and prior sensitivity need calibration before real use.

## Memory and copy generation

New model runs read all required organization/segment-scoped synthetic learning memory in one database read transaction, then build their creative contexts from that frozen result alongside the separate editorial examples. A cohort finalizing during context construction cannot appear in only one segment. Memory contains exact creative identities, cohort provenance, support counts and posterior parameters. Existing contexts remain unchanged. No inference is issued by learning itself.

Pooled memory uses finalized disjoint cohorts only and applies the prior once per creative group. These pooled response rates are descriptive. Recommendation comparisons remain within an individual randomized cohort; the system does not compare pooled treatments with pooled controls from different populations. Evidence finalized after the current clock is excluded from new model context.

A copy rewrite gets its own content identity and does not inherit the old creative's support. The model can use historical evidence to propose a new hook; it cannot convert a synthetic result into verified product claims or an approval. Product grounding and day-three exact-subject review still apply to the new draft. No self-modifying code, prompt deployment or autonomous targeting change is introduced.

## Architecture and migration

`learning/outcomes.py` owns membership, outcome and counted posterior rules. `learning/recommendations.py` owns reproducible advisory sampling. `LearningService` uses a `CohortSource` port, implemented in workflows through public review and campaign APIs. `SqliteLearning` implements the persistence port. The adapter rechecks the accepted receipt and stored bytes before admitting the cohort. A shared SQLite role helper keeps review and learning mutations consistent.

Schema v5 adds cohorts, independent business membership, immutable outcomes, beliefs, commands and events under the existing initialization write lock. It preserves review records and the original schema-v3 legacy admission cutoff. Migration failure rolls back DDL and version changes; retry is tested. Older application versions reject schema v5. Mixed-version rollback is unsupported.

## Verification ledger

The current suite has 135 offline tests, including 24 new learning tests and three learning CLI/migration tests. Existing foundation tests now expect schema v5; their lifecycle and compatibility assertions are preserved. Architecture checks pass. The 19 declared mutation probes include the original five learning controls: maturity independent of completeness, full assigned population, assignment binding, immutable observations and atomic finalization.

| Failure cluster | Executable evidence and independent oracle |
| --- | --- |
| Count semantics | Literal two-treatment/one-control example yields Beta(2,20) and Beta(1,20); exact counts reconcile with explicit rows. |
| Uncertainty | Beta(1,19) sampled interval compared with analytic CDF quantiles; known strong/negative/small-sample cases exercise recommendation behavior. |
| Lifecycle | Early partial results, complete-but-immature results, closed incomplete cohort, complete finalization and historical replay. |
| Identity and scope | Unknown business, changed segment/arm/creative, wrong organization and wrong local role are rejected. |
| Time | Half-open response window, explicit full-window non-response, non-finite timestamps and complete-through boundaries; future finalized evidence excluded from context. |
| Duplication | Reordered batches, same-key replay, fresh-key duplicate observations and repeated finalization do not increase counts. Contradictions fail. |
| Concurrency | Simultaneous finalizers produce one set of beliefs; conflicting imports produce one immutable winner. |
| Faults | Mid-batch insertion fault rolls back all rows. Finalization-event fault rolls back beliefs and finalization state, then a clean retry succeeds. |
| Compatibility | Schema-v4 upgrade preserves local roles and legacy cutoff; schema-v5 fault rolls back version and partial tables. |
| Whole flow | Separate-process demo/replay retains 754 outcomes and six beliefs. Mature memory changes new contexts, preserves old contexts and issues no model calls. |
| Report | Untrusted text is escaped. Desktop and mobile browser inspection checks layout and explicit synthetic clock labels. |

These are bounded experiments, not exhaustive coverage. No line-coverage percentage, production-readiness claim or live model-quality result is asserted. No paid model calls were made for day-four verification.

## Local review follow-up

Two regression tests reproduce the reported defects against commit `fe28c3d`: finalization between independent segment reads creates mixed context evidence, and a different operator replaying finalization with a fresh key emits a false second effect event. The snapshot regression forces a real SQLite writer commit after the reader has established its snapshot. The audit regression checks exact historical events and receipt equality across actor/time changes and restart. Cohort-opening semantic replay also preserves its single effect event. Two additional mutation probes restore the old behaviors; the selected denominator is now **19**. These fixes do not rewrite existing historical events.
