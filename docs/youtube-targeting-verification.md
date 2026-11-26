# YouTube targeting feasibility decision, issue 143

26 November 2026. Baseline: `74a53bbd7bb0e3d5c1b67ae12d12db6bbcaedda9`
(merged PR #142). Scope is source inspection, public documentation and an offline
contract check. No customer account, credentials, campaign write, live inference,
ad delivery or deployment was accessed. Account-specific source probes/results
remain outside Git and are not imported as destination verification.

## Decision

**GO for #144's offline contextual recommendation benchmark. NOT live-ready.**

The owner selected **qualified product-demo actions** on 26 November. The
[data/reward contract](youtube-data-reward-contract.md) and
[machine-readable v1 handoff](../config/youtube-decision-contract-v1.json)
freeze the first task, evidence unit, maturity, attribution, cost assumptions
and exclusions. Context/creative recommendations remain unapproved proposals.

The selected route is `offline_only`, using permitted authored examples.
A future manual export is conditional on a buyer verifying actual placement
setup, inventory and exact creative/account configuration. No current Google
route is certified for automated exact placement writes. A broad-audience or
surface-only campaign is not substituted for the contextual product.

This issue can finish with that explicit fallback under its acceptance terms.
#144 does not wait for cloud provisioning, but cannot claim learned conversion
accuracy, real campaign utility, counterfactual lift or shadow readiness.

## Evidence grades

- **Documented:** primary sources describe an operation or restriction.
- **Conflicted / needs account proof:** primary pages differ, a feature is
  version/configuration dependent, or a criterion exists without operation proof.
- **Offline contract verified:** this repository's fixture/schema checks ran.
- **Account / write / delivery verified:** none performed for this issue.

A query accepted against an empty test account would prove query acceptance
only. An API resource name or successful ad creative write does not prove
targeting mutations, populated reports, inventory or delivery.

## Control matrix, checked 26 November

| Route / version boundary | Inclusion, exclusion and expansion | Creative/setup, money and reporting | Disposition |
| --- | --- | --- | --- |
| Google Ads Video, current guide and v26 field reference | General Video campaign/criteria mutations are restricted. Product UI placement support is not API mutation support. Conversion-focused Video content targeting has separate restrictions [G1,G3] | Existing Video reporting is documented; guide lists version-specific responsive-ad and experiment exceptions. Not a general campaign/budget/pacing writer [G1] | Read/report integration candidate plus conditional UI/manual setup; account and effective settings unverified |
| Google Ads Demand Gen | Channel controls can select YouTube surfaces [G2]. Current contextual help distinguishes placement inclusion from keyword/topic hints and unrestricted other inventories [G4]. Audience help mentions YouTube contextual targeting while the overview retains placement-exclusion limitations [G5,G6] | Campaign/creative management and network/surface reporting documented [G2,G7]. Positive video/channel criterion mutations, exclusion precedence, expansion-off behavior and exact report joins are not account-verified | Plausible future route; exact-context capability is unresolved, not declared unavailable in all accounts or fully supported |
| DV360 YouTube & partners, v4 targeting / v5 public beta creative update | Targeting guide is read-only [D1]. The 12 November update still requires line item, ad group and targeting through UI/SDF [D2] | Selected responsive ad creatives can be managed in v5; subtype exclusions remain. Ad creative writes do not establish budget/targeting writes or raw impression access [D2] | Conditional UI/SDF setup; no claim of end-to-end API targeting |
| DV360 Demand Gen, v4 / v5 beta distinctions | Guide lists channel/video targeting and demonstrates **negative** channel assignment. The native details include a negative flag, but that alone does not prove positive inclusion semantics for every account/configuration [D3,D4] | Resource management rollout is documented. Inherited partner/advertiser/line-item/ad-group settings must be read together. Reporting, money/pacing and our qualified-action join require separate proof [D3,D5] | Candidate capability probe once account/scope exists; not selected as a verified live route |

### Required exact-context proof before activation

The following are documented resource/operation boundaries, **not executed
requests**. No API client/version is installed by this design.

| Route | Named operation or field to verify in an authorized account |
| --- | --- |
| Google Ads Video | `GoogleAdsService.SearchStream`: campaign/ad-group reads and `managed_placement_view` criteria metrics [G1]; generic `VIDEO` campaign/criterion mutation is not the selected path |
| Google Ads Demand Gen | Ad-group `demand_gen_ad_group_settings.channel_controls.selected_channels` and its GAQL read-back [G2]; this selects surfaces. Exact positive video/channel mutations remain unproved |
| DV360 YouTube | Assigned-targeting reads in the targeting guide; UI/SDF setup remains separate from v5 responsive-ad create/update [D1,D2] |
| DV360 Demand Gen | `advertisers.listAssignedTargetingOptions`, line-item/ad-group `bulkListAssignedTargetingOptions` for inherited scope; ad-group `bulkEditAssignedTargetingOptions` demonstrates negative YouTube-channel assignment [D3]. Positive exact-cell execution needs a separate supported payload/read-back |

Revalidate Demand Gen in the week of **1 December 2026**: Google's announced
Display-control migration moves exclusion to ad-group channel controls and
rejects setting the campaign network flag to false [G10]. Explicitly read all
enabled surfaces; neither an omitted flag nor an old campaign flag proves
YouTube-only inventory. This is a scheduled provider change, not an application
migration implemented here.

Pin platform/API version, supported campaign/line-item subtype and advertiser
scope. Verify the requested positive video/channel set, exclusions, inherited
settings, other inventory disabled, optimization/expansion behavior, exact
creative and destination after read-back. Do not confuse YouTube Shorts as a
surface with a particular creator's channel. Recheck effective configuration
before each bounded execution, not merely when the plan was proposed.

Read back currency, time zone, schedule, total/daily constraints, bid mode,
provider delivery/pacing semantics and any provider overdelivery behavior.
Our proposed batch ceilings are not platform billing guarantees. Changes need
their own exact approval or separately specified bounded mandate.

## Reporting and data feasibility

The existing source Google Ads reporting adapter reads ad-group and
ad-group/video impressions, clicks and cost in its fixed test-account scope.
It has no qualified-demo action feed. That code is source-only and not a
destination account-access or report-coverage claim.

The current Google field reference lists placement-view metrics [G8], and
Demand Gen documents network/surface breakdown [G7]. This does **not** establish
that creative, exact placement, audience segment, date, exposure, conversion and
cost can all be joined at our desired grain. Do not manufacture that joint
table from separate marginals.

For future manual/probed setup, begin with one frozen context–creative cell per
distinct ad group and an exact campaign-link mapping. Verify effective settings
and report granularity; ambiguous multi-creative groups, expanded traffic,
suppressed/missing placement rows or unknown attribution make exact-cell value
unavailable. The assignment-level demo outcome is separate from aggregate ad
exposure/cost. Provider conversion upload is an external write, not a local
tracking requirement or an automatically enabled feature [G9].

Viewability is a provider metric with its own measurable-impression denominator.
Playback completion, public video popularity and LLM relevance cannot establish
impression viewability. Conversion windows and incomplete reports retain unknown
states; no current join, randomized action log or valid propensity data exists
for offline counterfactual evaluation.

## Available data, not inferred access

| Source | What is present / obtainable in principle | Current permitted use and gap |
| --- | --- | --- |
| Destination authored catalogue | Two contexts, four deliberately fictional placements | Offline relevance tasks only; no inventory, audience, demand or response labels |
| Bundled comparison media | Five files: three MP4 and two MP3 | Exact permitted comparison playback; prerecorded use is not a qualified demo task |
| Reference ad candidates | Four MP4, four captions and two scene images with scripts/provenance | Authored benchmark candidates, not installed selectable/approved live ads |
| Reviewed company/brief | Merged #139 freezes selected input context | Assertions are not verified product facts; #131 eligibility/grounding remains the producer boundary |
| YouTube Data API | Available public video/channel metadata with provenance/freshness | No destination request made; creator/licensed inputs remain the ranker baseline. Metadata availability is not permission for all derived processing [Y1] |
| Transcripts / richer video semantics | Creator-supplied or licensed material, or an authorized caption path | Caption download requires edit permission; no arbitrary-video transcript corpus is established [Y2] |
| Audience / sequence behavior | Authorized first-party or platform aggregate data may later exist | Zero real YouTube response labels supplied; do not recast postal CRM fixtures as a measured YouTube audience |
| Own-channel analytics | Authorized channel/content-owner reports | Not competitor private demographics or person-level ad exposure [Y3] |
| Qualified demo outcomes | New v1 protocol specified, zero live events | #133 must implement trusted task/assignment receipts; existing choice/completion events cannot be relabeled |

None of the counts above is a market sample size. Multiple clips, LLM panel
votes and simulated people do not increase real observed support. Source
identifiers in hypothetical catalogues remain visibly fictional.

## #144 handoff and remaining ownership

#144 can compare independent rules/LLM contextual relevance and known-truth
simulated allocation using the frozen contract. Its simulation has its own
authored action-value/cost choices, not estimated customer lifetime value or
paid allowance. Freeze splits, utility and promotion rules before evaluation.

The subsequent #133 slice must implement the selected task/outcome receipt,
assignment/attribution, deduplication, maturation and read model, while preserving
instruction-beta-v1 separately. This does not require a second public learning
exercise or a preference picker as the main goal.

Live blockers: authorized account/effective targeting read-back, verified
inventory/creative configuration, trusted product-demo task completion, compatible
report joins and coverage, hosted membership/publication and separately approved
spend/execution. #70/#130 own identity/composition; #140/#141 assets;
#74/#134 actual shadow/live evaluation and cutover. Retest capabilities on API,
campaign type, permission, reporting, objective or provider-setting changes.
The next dated public-documentation review is 1 December 2026; account proof
remains required immediately before any future activation.

## Verification and limits

`python3 scripts/check_youtube_decision_contract.py` checks the frozen offline
handoff and emits its content hash. It is not an account capability probe,
runtime event validator or production authorization policy. Focused tests reject
proxy rewards, altered units/maturity, weakened exclusions, missing identity,
false live claims, invented propensities and inconsistent simulation money.
No statistical calibration or performance result is claimed by these checks.

## Primary source register

- G1: [Google Ads Video limitations](https://developers.google.com/google-ads/api/docs/video/overview)
- G2: [Demand Gen channel controls](https://developers.google.com/google-ads/api/docs/demand-gen/channel-controls)
- G3: [Content targeting and conversion campaigns](https://support.google.com/google-ads/answer/1704368?hl=en)
- G4: [Contextual targeting: placements versus hints](https://support.google.com/google-ads/answer/2404186)
- G5: [Demand Gen audiences](https://support.google.com/google-ads/answer/15594567?hl=en)
- G6: [Demand Gen overview / exclusions](https://support.google.com/google-ads/answer/13695777?hl=en)
- G7: [Demand Gen reporting](https://developers.google.com/google-ads/api/docs/demand-gen/reporting)
- G8: [v26 placement-view field reference](https://developers.google.com/google-ads/api/fields/v26/detail_placement_view)
- G9: [Offline conversion upload](https://developers.google.com/google-ads/api/docs/conversions/upload-offline)
- G10: [Demand Gen Display control change, week of 1 December](https://developers.google.com/ads/blog/posts/2026/11/display-targeting-changes-in-demand-gen)
- D1: [DV360 YouTube targeting](https://developers.google.com/display-video/api/guides/concepts/targeting/youtube)
- D2: [12 November responsive YouTube ad update](https://developers.google.com/ads/blog/posts/2026/11/manage-responsive-youtube-ads-with-display)
- D3: [DV360 Demand Gen targeting](https://developers.google.com/display-video/api/guides/tasks/serve-demand-gen-ad/assign-targeting)
- D4: [DV360 v5 native assigned targeting details](https://developers.google.com/display-video/api/reference/rest/v5/advertisers.adGroups.targetingTypes.assignedTargetingOptions)
- D5: [DV360 Demand Gen rollout](https://developers.google.com/display-video/api/release-notes#june_10_2026)
- Y1: [YouTube developer-policy guidance](https://developers.google.com/youtube/terms/developer-policies-guide)
- Y2: [Caption download permission](https://developers.google.com/youtube/data/reference/rest/v3/captions/download)
- Y3: [Authorized YouTube Analytics](https://developers.google.com/youtube/analytics/reference/reports/query)
