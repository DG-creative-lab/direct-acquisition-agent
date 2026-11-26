# Qualified product-demo action contract, v1

26 November 2026. Owner-selected objective for issue #143.
[Feasibility disposition](youtube-targeting-verification.md):
**offline-only GO for #144**, not a deployed conversion tracker.
Machine-readable handoff:
[`youtube-decision-contract-v1.json`](../config/youtube-decision-contract-v1.json).

## Goal, action and identity

The first benchmark objective is **qualified product-demo actions**. For the
voice-demo reference case, success means a user explicitly requests a voice
sample from permitted input text and receives a server-verified playable
generated result. Listening to a prerecorded comparison, choosing a preferred
recording, opening a page, pressing Generate or a client success flag is
insufficient. Existing authored clips remain useful creative/context examples,
but their playback cannot supply this outcome.

The planning action is a context–creative cell in a recommendation batch:
exact context/candidate snapshot, native placement references, creative version,
asset hash, reviewed brief/context revision, policy and reward version, proposed
period and money limits. Decisions are initially proposed every 24 hours, not
at each impression. More frequent execution is not authorized.

All identities carry server-resolved organization/profile. An opaque
campaign-link grant maps to the exact cell and assignment; caller-submitted
UTM strings, video IDs or a model's context label do not establish attribution.
Current channel review and explicit publication semantics remain required.

## Outcome semantics

The proposed v1 assignment unit is `eligible_demo_assignment`, created by
trusted ingress for an attributable arrival, not by claiming a new event ID.
Reopening retains the original assignment/arm. One assignment can earn at most
one positive action. Repeated jobs, receipts, result reads and event retries
cannot add support; the same generation job cannot count for another assignment.
Assignments do not prove unique or independent people.

The positive receipt `server_verified_demo_task_succeeded` must bind:

- Organization/profile, decision, cell, assignment and eligible source grant.
- Exact task/input-definition version, job ID, result receipt and generated
  asset digest; generation must be a user-requested product task.
- Server-validated playable output with expected format and nonzero duration.
- Server occurrence time, event/request identity and current protocol version.

Do not retain private submitted text, audio or credentials in public telemetry.
Permission and retention for the actual task belong to #70/#133 and the
provider integration. Generation, including use of a free allowance, requires
its own admission/budget and uncertainty handling. No provider task is enabled
by this contract.

The observation window is **30 minutes** from assigned arrival, followed by
**5 minutes** ingestion grace. A success must occur within the observation
window under trusted server time. Until maturity, unresolved outcomes remain
unknown. A zero is allowed only when the window plus grace has matured,
coverage is complete and no task effect remains uncertain. A stalled provider,
tracking gap or partial snapshot is unknown, not a failed customer.

Late evidence after a finalized cutoff is retained with its provenance and
requires an explicit correction/new snapshot. It does not silently rewrite a
frozen evaluation. Conflicting retries and missing identity fail rather than
being repaired by an LLM.

Allowed learning source is a verified participant assignment. Staff, rehearsal,
fixture, unknown and LLM-simulation sources remain separate. A browser cannot
choose its own participant label. No live qualified-action receipts currently
exist for this new protocol.

## Metrics and reporting grain

The post-click response uses one frozen, mature assignment cohort. Let `S` be
verified successes, `F` verified non-successes and `U` unknown outcomes, with
the full eligible assignment manifest providing `N = S + F + U`. Time maturity
alone does not establish outcome completeness. An early success in an immature
assignment cannot enter the cohort rate or posterior before its denominator.

A **point estimate `S/N` is available only when `N > 0`, coverage is complete
and `U = 0`**. If any mature outcome remains unknown, report the point estimate
as unavailable. Do not treat the unknown as a failure, divide by `S + F` or
assume that missing outcomes resemble observed outcomes.

When the complete assignment manifest and valid `S/F/U` counts are known, an
incomplete cohort may show bounds **`[S/N, (S+U)/N]`**. These are worst/best-case
missing-outcome bounds, not a confidence or credible interval. If `N = 0`, or
the assignment manifest itself is incomplete, both the point estimate and
bounds are unavailable.

| Mature cohort | Point estimate | Missing-outcome bounds | Cohort posterior update |
| --- | --- | --- | --- |
| One success, one unknown (`N=2`) | Unavailable | 50% to 100% | Blocked |
| One success, one verified non-success (`N=2`, complete coverage) | 50% | 50% to 50% | May consume `S=1, F=1` once |
| One unknown (`N=1`) | Unavailable | 0% to 100% | Blocked |
| No eligible assignments (`N=0`) | Unavailable | Unavailable | Blocked |

No outcome-conditioned posterior or learning update is produced from an
incomplete cohort, including its observed successes. A prior or posterior from
earlier complete cohorts can remain visible with its original support; this
cohort adds none until it is complete and mature, then contributes `S/F` once.
An improvement comparison or promotion requires both comparison cohorts to be
complete at the same frozen cutoff. Unknown cells cannot be removed to obtain
a favorable complete-case comparison. Late resolution uses the explicit
correction/new-snapshot path without counting a cohort twice.

Return `S/F/U/N`, immature count, exclusions, protocol/cutoff, manifest and
coverage status alongside availability and any bounds. Excluded traffic stays
visible separately. Do not call this ad-impression conversion rate,
individual-person conversion, purchase, revenue or causal lift. These are
required #144/#133 semantics; this PR installs no event aggregation or posterior
implementation.

Business cost per qualified action additionally requires known, compatible
spend and attribution to the same frozen cell/time period, plus complete mature
outcomes. Incomplete outcomes also block final cost-per-action and realized
utility point estimates; raw observed counts/cost remain explicitly partial.
With a complete cohort and no actions,
show no qualified actions; with missing cost, show cost unavailable. Never
divide by zero or report unknown spend as zero. Choosing acquisition placements
also needs traffic/exposure/cost evidence: post-click completion alone cannot
rank end-to-end ad efficiency or infer a click-through probability.

The future provider join must retain account/campaign/ad-group/ad/creative
identity, effective targeting snapshot, provider date/time zone, report coverage
and first-party assignment mapping. One cell per verified ad group is a
proposed simplification, not proof of eligible inventory or a usable join.
Cross-surface, multi-creative or expanded delivery cannot be assigned to exact
video cells without supporting evidence. Do not join separate marginal
audience, placement and creative reports into invented observations.

Viewability, paid exposure, click, assigned arrival, successful product task and
sale are different stages. Report each only from its available source. Existing
instruction-beta-v1 completion and optional human choice retain their original
semantics and never feed this qualified-action posterior.

## Data dictionary for #144 / #133

| Field family | Source and unit | Required treatment |
| --- | --- | --- |
| Brief/context | #131 reviewed context + current source revisions | Assertions stay unverified until the existing grounding transition; changed/expired inputs fence publication |
| Candidates | Scoped permitted catalogue + effective platform settings when available | Fictional IDs stay fictional; no inference of inventory or sensitive viewer attributes |
| Creative/assets | Exact permitted version/hash; #140 or bundled adapter | Reference ad candidates do not inherit approval; unavailable bytes block current use |
| Audience features | Authorized aggregate/first-party source or authored simulation | No real response labels available now; postal fixtures are not measured YouTube audiences |
| Decision log | Actual candidate set, context/features, policy/model/prompt, chosen action, probability if defined | Keep our batch selection separate from Google's unknown auction probability |
| Assignment | Trusted scoped campaign-link ingress, protocol and server clock | Stable identity; distinguish participant, rehearsal, fixture, staff and unknown |
| Task outcome | Authorized server job/result receipt | Validate task success and exact output; one positive per assignment |
| Exposure/cost | Compatible provider report and bounded account mapping | No populated destination report or validated join yet; coverage/currency/time zone required |
| Snapshot | Immutable cutoff, `S/F/U/N`, immature/excluded counts and source IDs | Complete-manifest bounds only; complete nonempty cohorts for point estimates/posterior updates; explicit late corrections; no pooling across source types |

## Retention and deletion boundary

The current benchmark retains only authored, permitted fixtures and aggregate
synthetic results in Git. It collects no participant identifiers or real task
inputs. Creator/licensed inputs require a source/use permission, expiry,
revision and revocation path through #140; bundled examples do not confer an
indefinite license on future uploads.

No YouTube API data is imported by this contract. Before any such ingestion,
the adapter must identify the applicable field/use class, API refresh/deletion
requirements and permitted derived processing. Public metadata is not a general
training license. Permission withdrawal or a required refresh that fails must
make the affected candidate unavailable for new work.

Before #133 collects real events, #70/#133 must specify a bounded retention
period, lawful task/input use, participant deletion and the treatment of
referenced observations, aggregates and immutable evaluation snapshots. Until
then participant collection remains blocked. Deletion or loss of a required
source cannot leave a snapshot claiming complete coverage; preserve a redacted
lineage/status where permitted or explicitly invalidate the result. Raw input
text/audio and account data must not enter public fixtures or evaluation JSON.

## Frozen offline tradeoffs

For the first authored simulation only: GBP integer pence, seven planning days,
10,000 pence total budget, 2,000 pence daily cap and 1,000 pence exploration cap.
Both the total and daily limits apply. These are synthetic resource units,
not an approved real account budget or a platform billing guarantee.

The benchmark utility is `500 * qualified_actions - cost_pence`. Its 500-pence
action value is an authored comparison tradeoff, not estimated revenue, customer
value or an approved acquisition price. The minimum worthwhile post-click
activation-rate improvement is two percentage points, a predeclared development
comparison threshold, not a powered live-test design. #144 must retain these
values before comparisons rather than tune the held-out result. The baseline
checker pins every simulation field and its type, including these exact numeric
values, currency, utility formula and interpretation; a different hash alone
does not admit changed assumptions under v1.

Sensitivity cases require a separately identified contract with its own schema
or version, variant ID, parent baseline hash and complete changed assumptions.
Their results must remain labeled as sensitivity, outside the frozen baseline
comparison. This checker rejects sensitivity contracts and additional variant
fields under v1; #144 must explicitly validate any future sensitivity format.

Use independent synthetic assignments with known response/cost surfaces for
initial policy tests, labeling that independence assumption. Real visitors may
repeat or be clustered; no real Bernoulli-independence claim is made. Priors,
pooling and production model selection remain #144 decisions; no old instruction
test priors/utilities are repurposed.

## Promotion boundary

This immutable v1 records the offline decision and currently unavailable real
labels. Future observations belong in separate versioned evidence, not by
editing this historical snapshot to mark it verified. A successor live contract
requires account/read-back, task/attribution implementation, compatible
exposure/cost joins, current hosted scope and separately authorized execution.

#144 can now implement the offline benchmark. #133 remains after its accepted
handoff and must install real task evidence before advertising qualified-action
tracking. A comparison-only viewer may remain as a separate research surface,
not the main optimization loop.
