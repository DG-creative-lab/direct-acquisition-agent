# Learning and outcome reference

The learning module turns complete, mature synthetic outcome cohorts into persistent Bayesian counts and advisory experiment recommendations. Runtime, campaign selection, editorial preferences and approval remain separate.

## Run the demonstration

```sh
PYTHONPATH=src python3 -m acquisition --db .local/learning-demo.sqlite demo-learning --out .local/learning-demo
```

Open `.local/learning-demo/learning.html`. The command also writes a pending report, outcome JSON, a learning JSON projection and the earlier review demonstration. It uses scripted reviewer decisions, simulated acceptance, synthetic response labels and a simulated 28-day clock. It does not wait 28 real days or claim real customer performance. Its deterministic organization is separate from the operator's organization. No model key or model requests are needed.

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

Use an existing accepted case from the [review flow](reviews.md). The same database and organization must contain the configured operator and that case.

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

## Import recorded provider reports

`learning-import-report` reads a local JSON snapshot for an existing accepted synthetic cohort. Use the organization, cohort ID, job ID, metric and exact window from `learning-show`. The report source uses the same immutable outcome importer as manual batches.

```sh
PYTHONPATH=src python3 -m acquisition --db .local/manual.sqlite --organization demo-org learning-import-report --cohort COHORT_ID --actor operator --request-id report-1 --file provider-report.json
```

The `synthetic-provider-report/v1` envelope has these fields. JSON object keys must be unique at every level.

| Fields | Required value |
| --- | --- |
| `schema`, `mode` | `synthetic-provider-report/v1`, `SYNTHETIC_ONLY` |
| `organization`, `cohort_id`, `job_id`, `metric`, `window_start`, `window_end` | Exact values from the frozen cohort. The accepted job and draft are verified again during import. |
| `report_id` | Stable identity for one immutable snapshot within the cohort. Use a new ID for a cumulative snapshot with new content. |
| `watermark`, `final` | Unix timestamp through which the snapshot reports, and a boolean. A final snapshot must attest the exact cutoff after it has passed. Explicit non-responses require that final attestation. |
| `page_count`, `pages` | Declared count and all pages numbered `1` through `page_count`. Each page contains `report_id`, `number` and an `events` array. |

Each event has `event_id` and `outcome`. The outcome uses the same exact assignment and observation fields as the manual batch above. For this synthetic source, the event ID is `synthetic_event_` followed by the SHA-256 of canonical JSON with `business_id` and `cohort_id` as its only keys. Use the repository's `acquisition.contracts.digest` for canonical encoding. These identities stay stable across snapshots. An exact event repeated across pages or cumulative reports adds no further observation. Changed content for an existing event, another report's page, missing pages or a reused report ID with different content rejects the snapshot atomically. The file limit is 4 MiB, with at most 100 pages and 10,000 events.

The receipt records the report ID, digest, page count, watermark, duplicates and missing assignment count. `coverage_complete` requires a final snapshot with an explicit outcome for every enrolled business, including each no-mail control. A fully paginated report can still leave outcomes unknown. Import saves observations and audit evidence. The `learning-finalize` command separately checks maturity and complete coverage across stored observations before updating beliefs.

The normalized snapshot commits with the import receipt and outcomes. The saved pages retain each event's assignment and observation. Use the report ID from `learning-show` to inspect a single snapshot and check it against its original import digest, even when the source file is gone or the workspace is a read-only restore.

```sh
PYTHONPATH=src python3 -m acquisition --db .local/manual.sqlite --organization demo-org learning-show-report --cohort COHORT_ID --report REPORT_ID
```

An earlier import that saved only its digest has no inspectable snapshot. On the live store, use a fresh request ID to import the exact original report again and attach its pages after checking the saved digest and outcomes. This preserves the original receipt and adds no observations.

## Schedule recorded report checks

In the workspace, open the accepted campaign's outcome window in Learning.
Choose **Recorded synthetic reports**, select the JSON files, set the first
check in UTC and enter the cadence in minutes. Use **Move up** and **Move down**
to order the recordings by watermark. **Review monitoring schedule**
shows the reports, accepted job and cohort before confirmation. Existing schedules
offer **Save cadence**, **Pause monitoring** and **Resume monitoring**. Pausing
and resuming retain the saved cadence. Save a cadence change explicitly to apply
it after the currently scheduled check.

Before sending, the browser saves the original reports, settings and request ID
in IndexedDB. After a lost response or reload, use **Recover saved monitoring
request**. It reuses the original submission. A confirmed response clears the
pending upload. A rejected submission clears only after the server has fenced
that request against a delayed commit. Keep the workspace's browser storage
available while recovering a request.

An operator can register one finite schedule for an open cohort from an accepted
simulated job. Use the `organization` and `cohort_id` in the recording. A chat
campaign uses `<root>/conversations.sqlite`. A standalone workspace campaign
uses `<root>/<organization>/campaign.sqlite`, including its follow-ups. Use the
existing local operator identity, usually `local-operator` in the workspace.

```sh
export PYTHONPATH=src
python3 -m acquisition --db STORE --organization ORG learning-monitor-start \
  --cohort COHORT_ID --actor OPERATOR --request-id schedule-1 \
  --first-check UNIX_SECONDS --interval-seconds 3600 --file early.json --file final.json
python3 -m acquisition --db STORE --organization ORG learning-monitor-show --cohort COHORT_ID
python3 -m acquisition --db STORE --organization ORG learning-monitor-update \
  --cohort COHORT_ID --actor OPERATOR --request-id pause-1 --revision CURRENT_REVISION --status paused
```

Provide 1 to 12 distinct reports in watermark order, up to 16 MiB total.
The schedule freezes their contents and hashes in SQLite. The first check must
fall inside the cohort window. Each report becomes available at its watermark.
After a successful check, the next due time uses the current clock and cadence,
bounded by the cohort cutoff and the next report's availability. A restarted
runner checks at most one report per cohort per pass and processes the remaining
recordings over subsequent passes. Missed intervals do not create check records.

Use the latest schedule revision, a fresh request ID and `--status scheduled`
to resume a paused or blocked check. An optional `--interval-seconds` updates
the cadence after the currently scheduled check. Pausing stops pending imports.
The cohort metric, cutoff and accepted assignments stay fixed.

The workspace server checks due recordings while it runs. Learning shows the
schedule status, last check, watermark and next due time. A fixture operator can
advance the sandbox clock to the exact next displayed check. For an independent
CLI store, run `learning-monitor-tick --cohort COHORT_ID` with the same database
and organization to check one due report. Workspace cohorts use their own
campaign clocks.

Import and schedule progress have separate commits. If the process exits
between them, the next runner reclaims the check after the 30-second lease and
uses the original import receipt. Completing the schedule means all staged
files were checked. Finalization still requires explicit outcomes for the whole
mature cohort, including controls. Checkpoint restores allow schedule inspection.

## Bayesian calculation and recommendation policy

Each segment/creative group starts with the illustrative Beta(1,19) prior, with mean 5% and prior concentration 20. This is a demonstration choice, not a calibrated prior. With n trials and s responses, the posterior is Beta(1+s,19+n-s). Mean and standard deviation are computed from those parameters. Exact counts and parameters are persisted.

A recommendation draws 10,000 samples from each treatment and its segment's no-mail posterior. A fixed seed from the cohort, segment and algorithm version makes repeated reads reproducible on the same Python runtime. Samples estimate central 90% intervals and probabilities for A versus B and the chosen variant versus control. Runtime changes can change Monte Carlo samples; this is an advisory projection, not an exact analytical probability or durable authority. Extreme probabilities are displayed as bounds rather than apparent certainty.

The next-experiment rule requires at least 30 observations per treatment and 10 controls, estimated probability >=90% of beating the other variant and >=95% of beating control. Otherwise it recommends collecting more evidence. Missing treatment/control strata produce no comparison. These thresholds are explicitly illustrative. They do not account for every campaign decision cost, multiple testing, delivery failure, delayed attribution or population drift.

Response lift refers only to the fixed randomized, high-propensity selected cohort. It is not a general population forecast, revenue forecast or profit estimate. The outcome window and prior sensitivity need calibration before real use.

## Memory and copy generation

New model runs read all required organization/segment-scoped synthetic learning memory in one database read transaction, then build their creative contexts from that frozen result alongside the separate editorial examples. A cohort finalizing during context construction cannot appear in only one segment. Memory contains exact creative identities, cohort provenance, support counts and posterior parameters. Existing contexts remain unchanged. No inference is issued by learning itself.

Pooled memory uses finalized disjoint cohorts only and applies the prior once per creative group. These pooled response rates are descriptive. Recommendation comparisons remain within an individual randomized cohort; the system does not compare pooled treatments with pooled controls from different populations. Evidence finalized after the current clock is excluded from new model context.

A copy rewrite gets its own content identity and does not inherit the old creative's support. The model can use historical evidence to propose a new hook; it cannot convert a synthetic result into verified product claims or an approval. Product grounding and exact-subject review still apply to the new draft. No self-modifying code, prompt deployment or autonomous targeting change is introduced.

## Evidence-bound follow-up hypotheses

After complete mature learning, **Propose follow-up experiment** records a
deterministic hypothesis for each selected audience. Each hypothesis binds the
source cohort and accepted draft, exact creative identities, observed successes
and trials, finalization digests, comparison policy and uncertainty. Its evidence
identifier hashes those recorded values. The source counts and posterior
parameters must reconcile with finalization; missing, conflicting, future or
foreign evidence blocks a new proposal.

A **strong** source comparison meets the existing illustrative sample-size and
posterior thresholds. It proposes testing a new expression of that source
variant's framing against a contrasting hook and a no-mail control. A **weak**
comparison has observed A/B/control groups but insufficient comparative support;
it proposes exploration without selecting a preferred framing. **Absent** means
no complete relevant comparison is available. Missing strata remain unknown and
prior parameters add no observations. It does not bypass the finalized-cohort
gate or invent a source advantage.

Comparisons use one randomized source cohort. Pooled history stays separately
frozen as descriptive advisory memory and cannot establish comparative lift.
Source framing notes are historical interpretations, not product facts or an
explanation of why responses occurred. Synthetic observations do not establish
customer performance. New copy retains current product grounding and its own
review; historical outcomes or approval cannot transfer to rewritten copy.

A strong hypothesis includes the original source hook. For grounded copy, the
creative module extracts it using that creative's original frozen context and
removes the exact historical product suffix. The hook remains quoted historical
framing. Old product wording does not become current evidence, even if the active
product pack has changed. Fixture and legacy ungrounded hooks retain their
original text.

The proposal and each model context retain the same audience-specific hypothesis.
Persistence rechecks the native cohort, counted beliefs and context binding under
the SQLite write lock. Request replay and process restart read the original
proposal without recomputing its hypothesis. Historical proposals without these
fields retain their original presentation and contexts. No schema migration or
new inference is needed to propose a hypothesis. Verified paid execution and
restored-workspace execution remain paused.

Hypothesis source reads first reload the organization's accepted simulated job,
check its indexed identities against the acceptance receipt, verify its draft
bytes and identity, and rebuild the exact cohort from that acceptance. They then
reconcile the persisted membership index and complete outcome rows with the
cohort, each assignment and observation window, the outcome digest, derived
posterior groups and finalization receipt. The save transaction repeats these
checks. Missing or mismatched acceptance evidence and changed or substituted rows
block new hypotheses without replacing historical receipts. Each model context must also name the
proposal's exact stored audience snapshot and match its model version and
per-audience input record count.

Offline checks use held-out strong, weak and absent count patterns for both
audiences, plus real SQLite zero-response, forgery, replay and restart checks. A
fresh verified fixture root creates and restores a proposal with zero model calls.
Fake-provider checks verify the frozen hypothesis reaches the copy request; they
do not establish live model quality. The browser exposes source counts and
uncertainty on desktop and mobile while retaining separate preparation consent.

## Architecture and migration

`learning/outcomes.py` owns membership, outcome and counted posterior rules. `learning/reports.py` owns recorded snapshot validation. `learning/recommendations.py` owns reproducible advisory sampling. `LearningService` uses a `CohortSource` port, implemented in workflows through public review and campaign APIs, and a `ReportSource` port implemented by the local file adapter. `SqliteLearning` implements persistence and rechecks the accepted receipt and stored bytes before admitting the cohort or importing a report. A shared SQLite role helper keeps review and learning mutations consistent.

Schema v5 adds cohorts, independent business membership, immutable outcomes, beliefs, commands and events under the existing initialization write lock. It preserves review records and the original schema-v3 legacy admission cutoff. Migration failure rolls back DDL and version changes; retry is tested. Older application versions reject schema v5. Mixed-version rollback is unsupported.

## Verification

See [validation](validation.md) for tests of count semantics, maturity, completeness, assignment identity, immutable observations, concurrent finalization, snapshot memory and historical replay. These tests do not calibrate the prior or establish real customer performance.
