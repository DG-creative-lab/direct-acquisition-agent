# Contextual targeting and decisioning feasibility

25 November 2026. Proposed workflow design and implementation gate under #128
and #60. Research is persisted in [contextual targeting options](contextual-targeting-research.md).
This records the revised product direction, not a deployed targeting integration,
verified response model, production allocation policy or permission to spend.

26 November checkpoint: #143 selects **offline-only GO for #144**, with
qualified product-demo actions as the owner-selected objective. The dated
[control/data verification](youtube-targeting-verification.md),
[action and reward contract](youtube-data-reward-contract.md) and
[v1 handoff](../config/youtube-decision-contract-v1.json) resolve the first
offline task. No route is account/write/delivery verified. Manual exact-context
setup remains conditional; #133 follows the accepted #144 handoff and needs
new trusted task receipts, not relabeled recording preferences. The design
below remains the wider implementation plan.

## Decision and purpose

The product should recommend suitable approved creative/context allocations
from the campaign brief and improve recommendations using attributable observed
outcomes. Human preference between recordings is optional research. It cannot
stand in for ad selection, commercial performance or incremental impact.

Start at a controllable **context–creative batch recommendation**. A batch binds
eligible placement/context candidates, exact creative versions, budget proposal,
period and objective. It is not a promise of an external LLM serving each
YouTube impression. Google's auction and delivery policy are external state.

The first implementation mode is recommendation/manual handoff, with no new ad
write authority. Preserve exact review of the resulting package. A later bounded
execution mandate needs its own expiry, budget, permitted changes and rechecks;
the current package approval cannot authorize continuing adaptive changes.

Use a hybrid candidate architecture: LLM-assisted contextual relevance, simple
statistical/Bayesian response estimates when supported by data, and explicit
budget/pacing constraints. Compare baselines before selecting a production
algorithm. Full RL, sequence-model training, causal libraries and purchased
simulation services are not initial dependencies.

## Evidence boundary

- Main inspected for this design is `a5a8630cde102edfa1647ac3238ac200bd3ef85d`,
  containing merged #138 native YouTube preparation and #139 reviewed input
  context. This branch adds no runtime/schema work from the separate #131
  eligibility build at `9507349`.
- The source application has placement classification and a narrow Bayesian
  instruction experiment. These do not establish a learned ad-response model.
- The source-based [YouTube contract](youtube-channel-contract.md) and
  `instruction-beta-v1` remain compatibility boundaries. This proposal adds a
  separate allocation/reward contract; it does not relabel existing completion
  counts, modify priors/utilities or import historical observations.
- Platform and paper findings are dated documentation research in the companion
  note. Google Ads/DV360 account access, exact criterion compatibility,
  inventory, report joins and real campaign performance remain unverified.
- Simile findings are provider methodology/research, not evidence that a generic
  LLM panel predicts our customers. The 2024 paper and November 2026 revision
  are distinguished. Synthetic outcomes remain separately labeled.

## Feasibility outputs and exit decisions

[#143](https://github.com/DG-creative-lab/direct-acquisition-agent/issues/143)
must produce these artifacts before the next #133 implementation slice:

| Artifact | Required contents |
| --- | --- |
| User task and control contract | Objective; actual batch/action unit; recommendation versus execution; platform-supported changes and explicit unsupported states |
| Route capability matrix | API/version/account prerequisites, positive/negative targeting, surface versus exact video/channel control, inherited/expanded targeting, creative writes, reporting grain, budgets/pacing and UI/SDF fallback |
| Data contract | Available fields, provenance/permission, source revision and freshness, scope, denominator/unit, joins, sample size, unknowns, retention and deletion constraints |
| Reward contract | Named primary outcome; unit/denominator; attribution/maturity windows; completeness; duplicates/retractions; objective/proxy labels; utility/cost and minimum worthwhile improvement |
| Decision record | `offline_only`, `manual_handoff`, `shadow_ready` or `blocked_live`; explicit evidence, remaining gaps, owner and revalidation date |

Evidence levels are `documented`, `fixture_contract_verified`,
`account_read_verified`, `validation_or_paused_write_verified` and
`delivery_verified`. Record them per capability; an API type name or read does
not prove targeting writes or serving. A paused test write cannot prove auction
delivery. No new account-specific operation is authorized by this design.

An explicit offline-only or manual-handoff decision can unblock #144 using
permitted authored data. Missing account access does not justify pretending a
route works or delaying all offline work. Hosted/live claims stay blocked until
their actual dependencies and evidence are satisfied.

## Reward and data rules

The goal comes from the reviewed brief; the LLM may interpret it or ask a material
clarification, but cannot silently replace it with an easier metric. Initial
feasibility must select one obtainable objective/reward pair instead of claiming
one universal formula for awareness, conversions and revenue.

For awareness, name the intended reach/frequency or measured brand outcome and
its available evidence. For conversion, name the attributable action/value and
its mature denominator. If only clicks or owned-demo completion are observable,
label them as proxies. A recording preference among post-click visitors cannot
identify response among everyone exposed to an ad.

Audience data is a permitted aggregate segment or authorized first-party source,
not an invented individual profile. Public video metadata does not reveal
private audience demographics, advertising availability or impression-level
viewability. Independently supplied media/transcripts and API metadata have
different processing/retention permissions; preserve those source boundaries.

Pin observations to the actual controllable action/report grain. Track currency,
spend, billed/unknown costs, event/attribution windows, maturity and coverage.
Unresolved conversions and incomplete reports are unknown, not automatic zeros.
No pooling across commercial, preference, instruction, rehearsal or simulated
cohorts. Any partial pooling within a response model needs explicit comparable
groups, assumptions and provenance; it does not manufacture independent support.

## Proposed operational contracts

Names below describe public values to implement, not a new universal schema.

| Value | Frozen identity and semantics |
| --- | --- |
| Context evidence | Organization/profile, source reference/revision, permitted fields, freshness and completeness |
| Candidate action | Context/placement set, native IDs and eligibility evidence, exact creative/asset versions, supported format and destination |
| Decision request | Reviewed brief/context references, objective/reward versions, eligible candidate set, period, money/pacing bounds, policy/model configuration and mode |
| Decision result | Rank/allocation proposal, selection probabilities only where genuinely defined, estimated uncertainty or insufficient evidence, constraints, rationale and source lineage |
| Outcome snapshot | Original decision/action, source/assignment IDs, actual observation unit, denominator, window/cutoff, completeness and measured/proxy/simulated classification |
| Allocation policy | Explicit prior/pooling/exploration/utility versions and bounded resource assumptions, separate from instruction-beta-v1 |

Fit scores are not calibrated action probabilities. A policy selection
probability is not the unknown probability of Google's auction showing an
impression. Do not invent either to make offline evaluation possible.

## Ownership and interaction

| Owner | Responsibility |
| --- | --- |
| `campaigns` / #131 | Reviewed brief/context projection and permitted factual input; intake selection is not independent verification or campaign approval |
| `audiences` public API | Applicable authorized audience/segment evidence; no conversion of CRM people into YouTube placements |
| `creative` / #140 | Exact reusable assets and metadata; #141 later supplies private file transport |
| `youtube` | Native context/creative candidates, objective-bound allocation proposal, channel evidence interpretation and separate policy versions |
| `reasoning` | Existing bounded model gateway, frozen requests, reservations and receipt recovery |
| `workflows` | Compose public brief, evidence, creative and YouTube APIs; keep runtime business-agnostic |
| Ports / adapters | Channel-owned capability, permitted context and reporting contracts; provider-native identity, SQL and SDK mechanics stay in adapters |
| #70 / #130 | Current actor/organization/connection scope and hosted composition; no second identity system |
| #74 / #134 | Shared evaluation machinery, hosted/live evidence and explicit cutover decision |

The ordinary request path is:

reviewed brief -> permitted context/assets -> eligible candidates ->
relevance/response estimation -> constrained recommendation -> exact review ->
manual/provider-supported handoff -> scoped mature observations -> revised
estimates and next recommendation.

Every transform carries scope, source versions, candidate identity, objective,
policy and uncertainty. Provider capabilities are explicit inputs. Bootstrap
alone wires adapters. Model tools and UI use the same application commands.

Persist the original request/result and any observation update atomically at
their SQL commit boundaries. Recheck current revision, scope, authority and
required evidence at publication. Resume the frozen original request; a new
message or expired source fences late publication. Paid inference continues to
use one journal and no automatic retry of an unknown effect. Dependency failure
cannot substitute a provider, asset, objective or account silently.

## Benchmark and promotion

[#144](https://github.com/DG-creative-lab/direct-acquisition-agent/issues/144)
compares rules, LLM/embedding ranking and a sparse Bayesian decision baseline on
the same independently specified tasks. Select a contextual bandit or simple
batch allocator only after defining feedback, overlap and resource limits.
Freeze the corpus splits, primary measures, priors, utility and promotion
thresholds before comparing candidates. Keep the held-out set independent of
prompt/model tuning and record exploratory results separately.

| Layer | Evidence and limit |
| --- | --- |
| Relevance | Human-labeled brief/context/creative tasks with held-out channels, time and creative families; assess wrong fit and needless abstention |
| Prediction | Temporal held-out Brier/log loss, calibration and uncertainty only when real labeled outcomes exist; unavailable labels mean no accuracy claim |
| Simulation | Known response/cost surfaces, sparse/delayed rewards, drift, scarce inventory and outages; measure simulated utility/regret and constraint violations |
| Offline replay | Require compatible logged context/candidates/actions, selection propensities and overlap; otherwise report not identifiable |
| Shadow | Recommendations with no campaign writes/spend; test operational feasibility and observable prediction quality, not reward for unexecuted alternatives |
| Live experiment | Separately authorized provider-supported randomized unit, primary outcome, power/minimum worthwhile effect, cost/stop limits and mature attribution; suitable holdout for incrementality |

A/B testing, Bayesian learning and causal estimation can coexist, but require
compatible assignments and estimands. Adaptive allocation does not automatically
make an ordinary campaign comparison causal. Simulation or a passing agent
capability rubric cannot establish commercial lift. Keep #74's model/tool
correctness checks distinct from this response/policy evaluation.

## Composed scenarios and acceptance

| Scenario | Required outcome |
| --- | --- |
| Supported brief and permitted contextual catalogue | One explainable context–creative batch recommendation with exact lineage; no user need to operate internal tools |
| Missing facts, no observed response data or unknown cost | Honest blocker/weak-prior uncertainty; no fabricated conversion estimate or over-budget allocation |
| Selected route cannot express exact video targeting | Explicit manual/offline alternative or blocked-live result; no silent switch to broad optimized targeting |
| Foreign or revoked scope/connection | No private evidence disclosure, new provider operation or result publication |
| Brief, asset or evidence changes during inference | Original result stays historical; no stale draft or inherited approval |
| Lost inference/result acknowledgement or concurrent requests | Original receipt recovery and one logical recommendation; no repeated uncertain paid call |
| Duplicate/late/partial outcomes | Stable deduplication and maturation; no extra support, false zeros or mixing simulated/participant data |
| Simulated panel prefers one ad but measured evidence disagrees | Real qualified evidence governs applicable updates; simulation remains a hypothesis |
| Model/provider/version added | Same public contract and independent expected outcomes; source policy/hash fixtures remain unchanged |

Acceptance is a recorded feasibility disposition plus reproducible baseline
evidence and a measurement handoff. It is not a claim that the selected model
will improve every campaign. Retain false blocks, failed tasks and untested
paths alongside successful results.

## Revised build sequence and coordination

1. Merge this design/research update to PR #142.
2. Complete #143's control/data/reward feasibility and explicit go/no-go record.
3. Build/evaluate the offline contextual recommendation baseline in #144.
4. Resume #133 with that accepted measurement handoff. Preserve its versioned
   instruction experiment as a distinct feature; implement the selected campaign
   feedback without relabeling preferences as ad conversions.
5. Compose authorized shadow/hosted evidence under #134/#74, consuming #70/#130,
   #131 and applicable #140/#141. Live ad tests and adaptive execution mandates
   require separate explicit scope, evidence and approval.
6. Decide rollout/cutover; retain the source until that decision.

The shared-platform track continues #131 grounding/preparation and #70/#130 platform
work. This YouTube track owns #143/#144 and the revised #133 handoff. Asset work
#140/#141 can proceed against the agreed contract. Record one integration owner
and fresh main baseline before touching shared migrations/bootstrap/workspace
or HTTP composition. No schema number is reserved by a planning document.

Open decisions assigned to #143: exact first campaign objective, obtainable
reward/report grain, platform/account route, lawful permitted feature inputs
and whether execution remains manual. #144 owns model comparison and promotion
thresholds. #70 owns hosted scope and any future connection/mandate mechanism.
These uncertainties are explicit gates, not hidden implementation defaults.
