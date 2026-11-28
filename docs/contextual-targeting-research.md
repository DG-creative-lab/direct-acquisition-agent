# Contextual campaign decisioning: initial options review

25 November 2026. Research and proposed decisions, not implemented capability.
No account inspection, paid calls, ad delivery or deployment was performed.
This note does not amend the existing migration contract or authorize a new
learning metric. Account-specific feature support remains unverified.

## Product correction

The intended product chooses suitable creative/context allocations from a
campaign brief, then improves those choices using observed performance.
Asking visitors which of two recordings they prefer is optional creative
research. It is not a replacement for contextual placement/ad selection,
conversion measurement or incrementality.

Three distinct questions need separate contracts:

1. Relevance: which permitted creative fits this video/channel and brief?
2. Prediction: what outcome is likely for this eligible action and context?
3. Decision: which action/batch allocation should be chosen given uncertainty,
   costs, deadline, pacing, platform control and authority?

The application should not promise an external LLM call at every YouTube ad
impression. Standard campaign-management integrations operate above Google's
auction/serving layer. Define the actual controllable unit before selecting
an algorithm: placement/creative group, ad group or a budgeted campaign batch.

Implementation design: [targeting and decisioning feasibility](targeting-decisioning-feasibility.md). The design governs the revised build sequence; this document retains the source findings and provisional options.

## Repository evidence

The source here is the separate `DG-creative-lab/youtube-ad-agent` repository, inspected at `1c8676e`; the destination is the destination GTM platform repository. The source product brief describes contextual placement/creative pairing.
`campaign_agent/placement_discovery.py` implements scoped permitted catalogues
and classification proposals; its simulated classifier uses authored rules.
`placements.py` has keyword-based context assignment. The bounded live planner
can orchestrate tools; this is not a calibrated audience-response model.
Public YouTube search and independently supplied classifier material already
have different provenance/permission rules in `docs/architecture-plan.md`.

`instruction_policy.py` and `learning.py` implement the narrow
`instruction-beta-v1` experiment. In the destination,
`docs/youtube-channel-contract.md` retains randomized browser-visit instruction
assignment and completed-comparison outcomes. That contract changes wording
while keeping media fixed. It does not establish a contextual ad-allocation
bandit or commercial uplift. Source reporting adapters are bounded and do not
prove production report grain or account access.

The destination's merged #138 provides authored native preparation/review/export,
not a production targeting integration. #133 remains useful measurement/reuse
work, but its preference/instruction loop is only one feedback path.

## Inputs and evidence limits

| Input | Useful fields | Evidence boundary |
| --- | --- | --- |
| Campaign brief | Objective, market/language, approved claims/assets, budget, deadline, pacing, exclusions and desired outcome | User goals are not permission to spend; pin a versioned objective/reward contract |
| Video/channel context | Permitted metadata, themes, language, freshness, creator-supplied/licensed transcript or media analysis | Public listing is not monetized/available inventory or private channel analytics |
| Audience evidence | Permitted aggregate segments, authorized first-party behavior and compatible advertising-platform reports | Do not infer individual viewer identity, sensitive traits or rival-channel demographics from public metadata |
| Creative | Exact approved version, message, tone, length, format, CTA, language and usage rights | Model fit score is neither calibrated response probability nor approval |
| Delivery/outcomes | Spend, eligible impressions/views/clicks, qualified actions, conversion value, time window and completeness | Match action/report grain; deduplicate, preserve lag and missingness; views are not conversions |

YouTube captions download requires permission to edit the video [S5].
YouTube Analytics is authorized channel/content-owner reporting, not a source
of arbitrary competing-channel demographic data [S6].
Derived analysis and retention depend on the accepted API use case and current
policies [S7]. The published policy distinguishes creator planning/suitability
from post-campaign safety verification. Use permitted authored/creator/licensed
data until the intended API processing is confirmed.

## Platform capability matrix

| Route | Documented opportunity | Constraint / next proof |
| --- | --- | --- |
| YouTube Data API | Discover videos/channels and retrieve available metadata | No ad purchase, private viewer dossiers or proof of ad inventory; captions and derived processing have separate conditions |
| Google Ads Video | Existing campaign/criteria reporting, with documented version-specific ad/experiment exceptions [S1] | Not a general create/update path for Video campaigns and placement settings; assess exact campaign type and retain UI/manual setup where needed |
| Google Ads Demand Gen | Campaign creation/management and controls for YouTube surfaces [S2] | Selecting Shorts/in-stream/in-feed is not proof of positive targeting of an arbitrary video; prove inclusion/exclusion, objective and reporting compatibility |
| DV360 traditional YouTube & partners | Retrieve targeting; v5 beta added selected responsive ad creative writes on 12 November [S3] | YouTube line items, ad groups and targeting still require interface/SDF setup under that announcement; creative writes do not imply targeting writes |
| DV360 Demand Gen | Resource management rolled out to partners in June; targeting guide lists YouTube channel/video types [S4] | Strong candidate for a capability probe, not proof that every positive/negative combination works for our chosen objective/account/version |

Google also documents content-targeting restrictions for conversion-focused
Video campaigns [S8]. Do not choose an easier writable campaign type while
silently abandoning exact contextual placement constraints.

Compare exact resource operations, positive versus negative criteria, inherited
targeting, expansion, bidding, pacing, forecasts, reporting joins, experiments,
credential/account availability and costs. A test account or successful paused
write can prove shape/read-back, not real auction eligibility or delivery.

## Model options and proposed first architecture

These are complementary layers rather than interchangeable frameworks:

| Technique | Suitable responsibility | Proposed use |
| --- | --- | --- |
| LLM / pretrained text or multimodal representation | Interpret brief, classify permitted content, describe fit and propose message variants | Start here; preserve evidence references and an explicit unknown/ambiguous outcome |
| Logistic or gradient-boosted response model | Predict a measured outcome from available features | Establish a simple calibrated baseline when labeled observations exist |
| Hierarchical Bayesian model | Estimate sparse context/creative response with partial pooling and uncertainty | Candidate baseline; distinguish cohorts/objectives and validate pooling assumptions |
| Contextual bandit / Thompson sampling | Explore versus exploit eligible actions using context and observed reward | Preferred adaptive policy candidate after defining the controllable unit, feedback and budget bounds [S9] |
| Budget-constrained allocation | Pacing, remaining budget, costs and exploration allowance | Separate explicit constrained optimizer; bandits-with-knapsacks is relevant research, not an automatic solution to auction dynamics [S10] |
| DoWhy / EconML / CausalML | Identification, incremental treatment effects and heterogeneous uplift | Add when experimental/observational data support an identifiable causal question; libraries cannot supply missing assumptions/data [S11] |
| Markov chain / MDP | Stateful journeys and sequential treatment decisions | Only if transitions, action effects and usable sequence data are observed |
| Full RL | Optimize long-term action sequences with delayed effects | Defer until state, dynamics, control and evaluation justify it |
| LSTM / trainable transformer | Learn behavior/content sequence representations | Defer training until data and a held-out gain over simpler baselines justify it; pretrained embeddings can be useful earlier |
| LLM audience simulation | Generate hypotheses, pre-test concepts and stress decision logic | Separate experimental input; validate predictions against held-out people/outcomes before operational use |

Proposed flow:

Permitted brief/context/assets -> relevance features and eligible candidates ->
response estimates with uncertainty -> constrained allocation recommendation ->
exact review or explicit bounded mandate -> platform-supported execution ->
versioned observed outcomes -> posterior/model update -> next recommendation.

Existing exact package approval is not an ongoing mandate for budget or targeting
changes. Start with automated recommendations and reviewable drafts; separately
specify any authority to execute adaptive changes.

For cold start, compare rules, LLM ranking and weak statistical priors.
Do not present invented percentage forecasts as calibrated estimates. Predefine
which evidence can support stronger priors; keep simulated outcomes out of real
participant/commercial counts. A thousand synthetic agents do not supply a
thousand independent real observations.

## LLM simulation findings

The linked 2024 paper can be accessed as arXiv v1 [S12]. Its frequently repeated
85% result normalizes survey prediction against human test-retest agreement;
it is not 85% accuracy at predicting ad conversion. The agents were grounded in
rich interviews, not merely short demographic personas.

The same work has a 16 November 2026 revision with a changed title [S13].
It reports improved survey/personality prediction from richer self-reports,
but not the same improvement for incentivized economic choices, and remaining
statistical distortions. This limits transfer claims to purchase/ad response.

Simile's own methodology describes combining observed behavior with interviews,
surveys and experiments and validating distributions/confidence using real
outcomes [S14]. This is materially different from asking a general LLM to
invent a panel of likely customers.

Potential MVP uses: identify confusing claims/CTAs, compare candidate concepts,
generate plausible failure scenarios, and form testable response hypotheses.
Keep simulation reports labeled with provenance/model/prompt, real grounding,
held-out validation coverage and uncertainty. Do not use simulated people as
measured campaign evidence or claim commercial lift from internal simulation.

The supplied Google Scholar citation page could not be resolved during this
review. Its identity/content are not assumed; the original paper and revision
above were inspected directly.

## Evaluation portfolio

1. **Semantic relevance:** independent human-labeled brief/context/creative
   examples; hold out channels, time and creative families to reduce leakage.
   Compare rules, LLM-only ranking and embedding/statistical baselines.
2. **Prediction:** temporal held-out log loss, Brier score, reliability curves
   and uncertainty, by supported segment/objective. No probability-quality claim
   without real labeled outcomes; a very small sample is diagnostic, not proof.
3. **Controlled simulation:** known response surfaces, drift, sparse rewards,
   delayed outcomes, price shocks and scarce inventory. Measure regret against
   known simulated truth, budget violations and recovery, not real-world lift.
4. **Offline policy evaluation:** replay/IPS/doubly robust methods only with
   suitable logged context, candidate actions, chosen action, selection
   propensity, outcome and overlap [S15]. Ordinary aggregate Google reports do
   not automatically identify counterfactual performance.
5. **Shadow mode:** generate recommendations alongside current operation with
   zero writes/spend; assess feasibility, stability and observed calibration.
   It cannot establish the reward of actions that were never executed.
6. **Bounded randomized live test:** choose a provider-supported randomization
   unit, one primary outcome, exposure/attribution windows, power/minimum
   worthwhile effect, spend/stop limits and delayed-outcome treatment. Use an
   appropriate holdout to assess incrementality. Google auction/optimizer
   selection complicates causal claims from nonrandom campaign comparisons.

Do not optimize preference clicks, comparison completion or viewability while
claiming improved purchases. Awareness needs an explicit reach/frequency/brand
outcome; conversion needs an attributable mature action/value. Human preference
and post-click completion can be separate proxies, not implicit substitutes.

Log our action propensity only when it is defined by our real policy. It is
not the unknown probability that Google's serving system selected an impression.
Unsupported report grains, missing outcomes and unobserved actions remain gaps.

## Next research and implementation gate

Before choosing the next #133 slice as the main product build:

- Specify the first customer job, objective, observable reward and unit of
  automated control; decide whether the MVP recommends batches or executes them.
- Verify one realistic platform route can express the chosen targeting and
  return useful, compatible feedback. Obtain account authorization separately.
- Inventory actually obtainable data, permissions, freshness, sample size,
  report granularity and historical decision/propensity availability.
- Prototype rules/LLM ranking plus a simple Bayesian decision baseline in an
  isolated offline evaluation. Include sparse/unknown cases and a simulation
  baseline; do not silently replace real evidence with synthetic counts.
- Record a decision matrix, adapter capability contract and amended roadmap.
  Preserve #133 measurement as infrastructure, #140/#141 asset storage,
  #70/#130 access/composition and #131 reviewed brief/context preparation.

No model family is finally selected in this note. The strongest provisional
choice is LLM-assisted contextual ranking plus an explicitly budgeted Bayesian
allocation policy, with causal measurement and simulation evaluated separately.

## Sources inspected

- S1: [Google Ads Video API limitations](https://developers.google.com/google-ads/api/docs/video/overview)
- S2: [Demand Gen overview](https://developers.google.com/google-ads/api/docs/demand-gen/overview) and [channel controls](https://developers.google.com/google-ads/api/docs/demand-gen/channel-controls)
- S3: [DV360 responsive YouTube ads update, 12 November 2026](https://developers.google.com/ads/blog/posts/2026/11/manage-responsive-youtube-ads-with-display) and [YouTube targeting](https://developers.google.com/display-video/api/guides/concepts/targeting/youtube)
- S4: [DV360 June rollout](https://developers.google.com/display-video/api/release-notes#june_10_2026) and [Demand Gen targeting](https://developers.google.com/display-video/api/guides/tasks/serve-demand-gen-ad/assign-targeting)
- S5: [Captions download](https://developers.google.com/youtube/data/reference/rest/v3/captions/download)
- S6: [Authorized YouTube Analytics reporting](https://developers.google.com/youtube/analytics/reference/reports/query)
- S7: [Developer policies guide](https://developers.google.com/youtube/terms/developer-policies-guide) and [derived-metrics policy](https://developers.google.com/youtube/terms/derived-metrics-policy)
- S8: [Google Ads targeting restrictions](https://support.google.com/google-ads/answer/1704368?hl=en)
- S9: [Li et al., contextual bandits](https://arxiv.org/abs/1003.0146)
- S10: [Badanidiyuru et al., Bandits with Knapsacks](https://arxiv.org/abs/1305.2545)
- S11: [EconML FAQ](https://www.pywhy.org/EconML/spec/faq.html) and [DoWhy estimation/identification](https://www.pywhy.org/dowhy/v0.11/user_guide/causal_tasks/estimating_causal_effects/effect_estimation_with_estimators.html)
- S12: [Park et al., original 2024 paper](https://arxiv.org/pdf/2411.10109v1)
- S13: [Revised 2026 paper](https://arxiv.org/pdf/2411.10109v4)
- S14: [Simile confidence methodology](https://www.simile.com/blog/confidence?v=2) and [What-If Machine](https://www.simile.com/blog/what-if-machine)
- S15: [Dudik et al., doubly robust policy evaluation](https://arxiv.org/abs/1103.4601) and [Li et al., offline replay](https://arxiv.org/abs/1003.5956)
