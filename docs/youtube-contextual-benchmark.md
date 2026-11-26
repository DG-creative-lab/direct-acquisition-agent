# Offline contextual recommendation benchmark

26 November 2026. Issue #144, starting from merged #146 at
`208826199f2390e90491dbf72466915d29ecdf22`.
The [reward/data contract](youtube-data-reward-contract.md) remains pinned to
`c7f4129dd6d50e5de4a2c41db4ab0cddf34f31bb6e1829711019ad462df59949`.

## Usable slice

An existing native YouTube campaign can produce a read-only JSON recommendation
through `YouTubeRecommendations.prepare` or
`YouTubeTools.recommend_contextual_batch`. Both use the same command. The
artifact contains its native campaign/revision, authored context, candidate
snapshot, exact ad versions/hashes, ranking, policy/reward, proposed allocation,
choice probability, evidence support, uncertainty and stopping reason.

This capability is installed explicitly with
`build_youtube_recommendations(campaigns)`. The existing chat/HTTP routes and
manual package approval are unchanged. The artifact is inspectable, not a new
approved/exportable campaign subject. No recommendation journal, schema change,
participant tracker, provider writer or UI is added. A previous package approval
does not approve this recommendation.

History arguments are explicitly authored simulation inputs. This command does
not reserve money or persist an authoritative allocation ledger, and its IDs
cannot be dispatched. A production consumer must resolve allocation history
from trusted storage and reserve budget under current authority before effects;
accepting a model's or browser's proposed history would not satisfy that boundary.

The native campaign still supplies an authored context, not #131's grounded
Company & brief binding. Existing reference ads invite prerecorded comparisons;
their destinations do not implement the new generated-sample task. Both gaps
are explicit live blockers, alongside account targeting/reporting and hosted
authority. No new asset-serving route is created for these ads.

## Ownership and data flow

| Owner | Responsibility |
| --- | --- |
| `youtube/decisioning.py` | Frozen input identity, ranking validation, complete response cohorts, budgeted proposals and blockers |
| `youtube/recommendations.py` | Native scoped read, exact revision, injected input/recorded-ranking ports, final authority/source recheck |
| `adapters/youtube_decision_inputs.py` | Bundled ad bytes, checksums/text, declared synthetic prices, authored ranking responses |
| `bootstrap.py` | Explicit composition of that offline service |
| `scripts/evaluate_youtube_contextual.py` | Withheld labels/truth, independent grading/oracle, network denial and source attribution |

The input adapter reads four permitted ad examples and four fictional placements
from the native draft catalogue. With both context groups selected,
this produces 16 context/creative cells. Costs are authored 50/100 pence for
100 simulated impressions, not a provider quote. Assets must match actual
checksums and bounded paths. Missing price blocks allocation. Scope, revision,
candidate/asset changes, malformed rankings or incompatible old evidence fail
with specific reasons.

Recorded ranking receipts are data, not a serving API. The current implementation
accepts deterministic rules and an explicitly authored model-response fixture.
It cannot certify a real model or accept its claims of identity, price or
authority. Future genuine model serving must use existing `reasoning.Inference`
admission/journaling; no separate live ledger or model client is introduced.

## Frozen method

The [benchmark corpus](../config/youtube-contextual-benchmark-v1.json) is pinned
by its canonical hash in the runner. Changing it requires a separately
identified benchmark contract. There are three development and three held-out
language tasks across only two authored context domains. They are not six
independent audience markets. Development uses seed 100; held-out simulation
uses the 32 predeclared seeds 200 through 231.

Compare:

- Rules: exact context match plus lexical overlap, without a response claim.
- Bayesian mean: independent Beta(1,1) qualified-response priors per frozen cell,
  no hierarchical pooling. Complete response evidence gives Beta(1+S,1+F).
  Descriptive arrival/impression reporting supplies the separate traffic stage.
  Greedy expected utility per penny uses both stages and the frozen 500-pence
  action tradeoff. A fit score never becomes a conversion probability.
- Authored ranking fixture: exercises response validation and allocation
  integration. Its results do not measure an LLM or justify selecting a model.

Exploitation requires supported response and exposure data. Unknown cells use
bounded exploration; its spending counts against the 1,000-pence cap. When
there is a supported greedy action, alternatives have 0.1 total exploration
probability, uniformly divided over affordable alternatives. The greedy action
and alternatives are disjoint, so each recorded cell probability is exact.
The current full-day cold start consumes the whole exploration cap. Later
exploration is therefore unavailable in this baseline, a measured design
limitation rather than a setting tuned after inspecting held-out results.

Spending comes from issued simulated allocations, never from outcome counts.
Missing reports cannot refund budget. The 10,000 total, 2,000 daily, seven-day
and 1,000 exploration limits remain the accepted v1 values. Fresh uncertainty
or a changed creative/version cannot reset the allocation ledger silently.

## Evidence and completeness

An allocation records input/cell, policy/ranking hash, decision seed, reward,
day, cost, 100 impressions, exploration status and local choice probability.
Duplicate identical receipts count once; conflicting identity or changed
scope/version/reward is rejected. Only authored synthetic outcomes are accepted
by this offline capability. Real participant support is always zero.

Qualified-response cohorts are frozen by cell/day over **all issued allocations
in that group**, before feedback. Missing one report or unknown result blocks
the group's response-posterior update, including observed successes. A complete
nonempty closed group contributes once in the stateless reconstruction. An
earlier complete day's support remains separate from an incomplete new day.

Per-arrival maturity is 30 minutes plus 5 minutes grace in synthetic elapsed
seconds. Zero-arrival reports still count descriptive exposures; they never
invent qualified-response support. Exposure counts are not a second response
posterior. The aggregate point estimate requires the complete mature population;
otherwise only permitted bounds are available. Missing allocation reports make
the population denominator unavailable, with observed partial counts labeled.
Instruction-beta-v1 and real/simulated cohorts never mix.

## Evaluation and decision

Run without credentials:

```sh
PYTHONPATH=src python3 scripts/evaluate_youtube_contextual.py
```

Output defaults to ignored `.local/evaluations/youtube-contextual-v1.json`.
Native cases use temporary SQLite stores and preserve their campaigns/approvals.
The runner denies network attempts, checks source before import and after
execution, and stops the remaining batch on unexpected execution errors.

Six scenarios cover stationary response, sparse/delayed reports, drift,
tracking gaps, missing prices and negative utility. Three policies and 32 seeds
produce 576 trials. Expected utility and regret use withheld authored arrival
and response surfaces. Regret is against an exact finite-horizon, budget/daily
constrained oracle with known truth and an option to spend nothing; it is not a
comparison of random realized utility against an expected oracle.

Relevance uses independent positive context/creative labels, precision@1 and
NDCG@3. Constraint grading is separate from the allocator. Actual latency,
simulated costs, stops, trace hashes and one complete sample trace per policy
are retained. Real model cost/latency/quality and real response calibration are
unavailable. Replay/IPS/doubly robust estimates remain unavailable: our local
batch-choice probabilities do not establish Google's auction propensities.

The [dated evidence](evaluations/issue-144-offline-benchmark-2026-11-26.json)
records results and a falsifiable baseline decision. Promotion requires complete
stationary comparisons, at least 200 basis points activation improvement,
better expected utility/regret and zero constraint violations. Its scope is
only the next offline iteration. Production promotion remains blocked.

Keep the original development/prototype result separately in ignored local
output. Corrections to completeness/identity enforcement are attributable code
changes; no prior, budget, epsilon or scenario is tuned to make Bayesian results
win. Further pooling, paced exploration or genuine model comparisons need a
separately identified experiment.

## #133 measurement handoff

Implement the requested generated-sample task and server-bound assignment/job/
result receipts before claiming the primary reward online. Freeze cell/day
membership, exact native brief/creative/reward/policy, cutoff and report coverage.
Deduplicate assignment and generation identities; keep unknown population and
outcomes explicit. Consume complete groups once, with explicit late corrections.
Persist issued allocations separately from observations.

Keep response, exposure, spend and permission sources distinct. Exposure/cost
must join the exact frozen action under a verified platform route; first-party
activation alone cannot measure acquisition efficiency. Reuse #70/#130 identity,
#131 reviewed grounding and #140/#141 assets. Retain instruction-beta-v1 as its
own compatibility feature. Real LLM ranking quality remains an explicit #144
follow-up; this fixture benchmark cannot close that evidence gap.

## Method references and limits

The Beta/Bernoulli treatment and exploration question are standard bandit
building blocks, discussed in [Russo et al.'s tutorial](https://arxiv.org/abs/1707.02038).
This implementation uses posterior means plus bounded epsilon exploration,
not Thompson sampling. That literature does not prove our chosen prior,
utility, corpus or policy effective for YouTube.

[Li et al.'s offline replay study](https://arxiv.org/abs/1003.5956) and
[Dudik et al.'s doubly robust evaluation](https://arxiv.org/abs/1103.4601)
motivate the separation between simulation and evaluation from compatible
logged actions. We implement neither replay nor doubly robust evaluation here.
No human-response, causal-lift, inventory, viewability or commercial-efficiency
claim follows from this synthetic benchmark.
