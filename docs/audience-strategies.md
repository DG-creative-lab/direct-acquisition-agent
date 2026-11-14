# Replaceable audience strategies

Issue #63 adds an offline categorization and decision slice on top of the scoped
[contact evidence foundation](contact-evidence.md). It prepares immutable,
non-executable synthetic selection proposals for iwoca and Fielddesk. Existing
postal campaign construction, model copy, review, simulator acceptance and
learning keep their existing contracts and artifact identities.

## Ownership and authority

Audiences owns `FeatureBatch`, `StrategySpec`, `ScoreSemantics`, typed observations
and results, plus the `AudienceCategorizer`, `AudienceDecisionStrategy` and
`AudienceDecisionStore` ports. `AudienceDecisions` depends on those ports.
Bootstrap selects and wires installed adapters. Neither strategy port uses the
reasoning module's text-completion gateway.

The features are an allowlisted projection of an attested contact source: exact
native contact ID, account experiment unit and declared segment. They contain no
email address, phone number, permission grant, credential or free-text CRM note.
The batch binds organization, profile, immutable readiness assessment, source,
channel, purpose, objective, full taxonomy, feature schema and feature digest.
Unresolved associations produce explicit null values and missingness.

The specification binds kind, key/version, model version, immutable configuration,
taxonomy, objective, feature schema and score semantics. Its content identity
binds configuration changes. Results bind the exact batch and strategy; ranking
also binds the exact categorization result. Each observation records missing
features, abstention and uncertainty. The installed rules declare uncertainty
`not_estimated`; they do not manufacture confidence intervals.

Campaigns owns the independent `contact-selection/v1` policy. It uses current
campaign-owned eligibility, never a strategy's eligibility flag or reclassified
segment. It enforces integer GBP budgets, maximum candidates, observed contact
and account caps, and one selected person per account experiment unit. It budgets
conservatively for every enrolled account, including controls. Unit cost is a
caller-supplied synthetic estimate, not a provider quote or spending authority.

Assignment uses `contact-account-hash/v1`, binding organization, profile, channel,
seed and experiment unit. A hash bucket determines A, B or no-contact, independently
of ranking. Small cohorts need not contain every arm or balanced arm sizes. These
new plans are not accepted learning cohorts and do not change legacy assignment.

## Installed strategies and score meaning

`declared-segment/v1` retains the source's declared taxonomy segment. It abstains
on unavailable features or unsupported labels; it is not a trained classifier.

Two decision adapters use the same port and campaign policy:

| Adapter | Rule | Interpretation |
| --- | --- | --- |
| `taxonomy-order/v1` | Earlier declared taxonomy segments receive higher ordinal fit | Transparent heuristic, 0 to 100 points |
| `reverse-taxonomy-test/v1` | Later segments receive higher ordinal fit | Contrasting deterministic conformance example, not a recommended targeting model |

`ScoreSemantics` distinguishes these contracts:

| Metric | Units | Required context |
| --- | --- | --- |
| Fit | Ordinal points, 0 to 100 | No response horizon |
| Response propensity | Probability parts per million | Explicit horizon in days |
| Expected value | GBP minor units | Explicit horizon in days |
| Uplift | Signed incremental probability parts per million | Horizon and treatment/control contrast |

Only ordinal fit is implemented by installed adapters. A request for another
metric cannot reuse those numbers: it produces an explicit incomplete result
without running inference. Different units, horizons, contrasts and strategy
identities cannot silently become one score. The contracts do not establish
calibration, causal validity or cross-model comparability. There is no supplied-score,
ML or LLM audience adapter in this slice. Legacy postal synthetic propensity
remains in its original explicitly labeled format.

## Preparation, commit and recovery

1. Bind the request key to the exact assessment, strategy specifications, expected
   score contract, budget, unit cost, candidate cap and seed. An exact replay reads
   the original receipt; changed inputs conflict.
2. Read the immutable assessment, current attested source, profile, objections,
   suppression epoch and eligibility in one SQLite snapshot. Stale assessments
   must be prepared again before starting a new decision.
3. Run at most one categorization attempt, then one ranking attempt over the frozen
   batch. Ranking is skipped when categorization is incomplete. Strategies run
   outside the write transaction.
4. Inside the commit transaction, independently reconstruct the batch from current
   source evidence and hard checks. A substituted, truncated or stale batch cannot
   publish. Campaigns validates result bindings, required population, score ranges,
   missingness, taxonomy and uncertainty before allocating.
5. Atomically save features, specifications, observations, diagnostics, constrained
   plan and receipt. Recheck current evidence and freshness after the write. A
   change rolls back the decision journal entry.

Partial results, missing features, unknown taxonomy, malformed result bindings,
explicit abstention or adapter exceptions produce `status: incomplete` with zero
allocations. There is no fallback, invented result or automatic retry. Exceptions
are recorded using fixed failure classifications, without provider exception text.

All data is scoped by organization. The audiences-owned schema-18
`contact_commands` journal stores the new `audience-decision/v1` command and its
complete immutable receipt. Separate command kinds prevent key collisions with
contact preparation, refreshes and objections. No schema migration, historical
row rewrite or new generic repository is needed. Inspection and replay validate
artifact identity and reconstruct the saved plan against its immutable assessment.
Public deserializers allow deterministic reproduction from frozen artifacts.

Replay is historical observation, never renewed authority. Inspection retains the
saved artifact and separately reports current applicability. Verified-paused and
restored inspection-only stores allow historical inspection but refuse mutations.

These are offline, side-effect-free ports. A future remote or paid implementation
needs explicit admission, call reservation, budget and uncertain-effect recovery
before it can be wired. Crash-before-commit repetition is harmless for these pure
offline adapters; that property must not be assumed for remote inference.

## Agent-facing API and CLI

The agent invokes an explicit Python service or CLI; this slice adds no forms or
required UI journey. It does not yet add conversational routing, new skills,
contextual copy, sequences, call tasks, approval subjects or sender integrations.
Those remain separate epic #60 issues.

First prepare an email or human-call readiness assessment using the contact CLI.
Use its exact `assessment_id` below. Fixtures are explicitly synthetic and expire
on 24 November 2026 at 00:00 UTC; new preparation requires applicable evidence.

```sh
PYTHONPATH=src python3 -m acquisition.decision_cli \
  --db .local/contacts.sqlite --organization demo --profile fielddesk \
  --strategy taxonomy-order prepare \
  --request-id decision-1 --assessment-id CONTACT_ASSESSMENT_ID \
  --budget-pence 200 --unit-cost-pence 100 --max-candidates 2 --seed 42

PYTHONPATH=src python3 -m acquisition.decision_cli \
  --db .local/contacts.sqlite --organization demo --profile fielddesk \
  inspect --request-id decision-1
```

`build_audience_decisions(path, organization, profile_key, strategy, clock)` returns
`AudienceDecisions.prepare(...)` and `.inspect(...)`. Organization arguments are
trusted local scope, not hosted authentication. Selection does not reserve shared
outbound capacity or slots; later execution must recheck current evidence and
reserve capacity inside its own effect transaction. No result grants campaign,
copy, model-spend, approval, delivery or learning authority.
