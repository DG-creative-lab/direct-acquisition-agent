# Product overview

GTM Agent Platform is being built to help a team turn product knowledge into
reviewable go-to-market actions and use observed results to decide what to try
next. It brings campaign preparation, human review and the next experiment
into one workspace.

The [platform map](gtm-platform-map.md) owns product-area and module boundaries.
This page owns the current product definition and capability limits.
For a short pitch and demand-testing plan, use the
[design-partner brief](product-discovery.md).

## Problem and intended value

Product knowledge, campaign preparation, approval and performance evidence
often have to be carried between tools. The problem we are testing is whether
a team loses useful context and spends avoidable effort making those handoffs.

The intended value is continuity: know which product evidence shaped a proposal,
what was approved, what happened afterwards and why the next change is proposed.
Time savings, better conversion and willingness to pay remain outcomes to test,
not established results.

## Initial customer and use case

The first discovery hypothesis is an AI or developer-tool product team with a
demonstrable product action and a named person responsible for acquisition.
An example is a voice-product team that wants to reach video editors or
narrators through contextual YouTube campaigns and measure qualified demo use.

That focus follows the current YouTube build and earlier pitch direction. It
does not establish a validated market segment or a relationship with a named
company. Agencies and other B2B teams remain possible later audiences.

The initial use case is a reviewable contextual YouTube campaign: identify
suitable contexts, pair creative with them, inspect the proposal, and establish
the evidence needed to evaluate a qualified product-demo action. The intended
agent chooses context/creative recommendations within objectives, budget and
pacing, then updates recommendations from eligible outcomes. Current local
preparation uses authored examples. Actual inventory, live targeting, generated
demo receipts and measured outcomes require further implementation and
separately scoped verification.

## Product areas

| Area | User job | Native rules that stay distinct |
| --- | --- | --- |
| Direct acquisition | Prepare relevant direct mail, email and human-assisted calls | Recipient/account identity, permissions, pressure, sequences, exclusions and response experiments |
| Advertising | Match objectives, contexts and creative, then evaluate campaign results | Placement suitability, provider targeting/reporting capabilities, creative allocation, pacing and reward definitions |
| Agentic commerce | Improve how products are represented, discovered and evaluated by agents | Product variants, discovery evidence, commerce/protocol readiness and native outcome definitions |

Knowledge, assets, chat, review presentation and operational infrastructure can
be shared. Product areas are not universal campaign schemas. A customer should
eventually be able to use one channel or a selected combination, with server-side
access enforcement. Billing and channel subscriptions are not implemented.

## The intended user journey

1. **Set the objective.** Describe the product, desired audience/context, outcome,
   budget and time span. The agent uses available permitted context and asks
   about material gaps.
2. **Prepare a proposal.** Receive concrete channel artifacts with source
   references, assumptions and blockers. Advice and drafts do not authorize effects.
3. **Review the exact result.** Inspect content, scope and proposed costs.
   Approve or request a change against the displayed version.
4. **Use the permitted output.** Start with manual export; provider execution
   can follow only when its own connection, permission and recovery contracts exist.
5. **Inspect evidence.** See native outcomes, eligible populations, missingness
   and uncertainty. Distinguish simulated, operator-attested and verified signals.
6. **Choose the next experiment.** Review an evidence-backed recommendation.
   Applying it creates a new proposal, not inherited approval.

A main campaign agent coordinates the experience. Skills and tools supply
capabilities; the user need not select agent personalities. The target UI
uses shared Knowledge and Learning views, inline expandable activity and an
artifact panel. The [workspace design](multichannel-workspace-design.md)
describes these interaction goals; it is not a claim of finished UI parity.

## What is implemented today

The primary usable composition is the local React workspace over a bounded
Python loopback API. The capabilities below are not all available through the
same screen or the same model route.

| Capability | Available surface and behavior | Important limit |
| --- | --- | --- |
| Company and campaign intake | Local Company & brief drafts, immutable revisions, explicit model-assisted interpretation and reviewed preparation context | Source assertions require review; interpretation is not factual verification or campaign approval |
| Postal campaign | Chat/local campaign form; synthetic audience, exclusions, A/B/no-mail assignment, inspectable copy, exact review and simulated handoff | No real printing/sending or live audience feed |
| Grounded planning and copy | Bounded, explicitly permitted OpenRouter calls; frozen context, product fact/qualification checks, advisory model screen and original-receipt recovery | A screen is not factual certification; model quality needs separate evaluation |
| Email and human-call journey | Conversational preparation, exact review and bounded simulation for installed company fixtures | Interpreter/content use offline fixtures; no real mail or calling |
| Reviewed company email package | Local reviewed intake to one to six fictional messages, exact approval and JSON export | Synthetic UK/GBP contacts are not matched to a real requested audience; no model generation or send authority |
| YouTube campaign | Local chat, authored placement draft/edit, exact review/approval and manual JSON export with bundled media | Fictional catalogue and prerecorded comparisons; no viewer measurement, live inference or ad buying in this path |
| Contextual recommendations | Separate explicitly composed Python/tool service and offline benchmark; optional local provider-ranking evaluator | Authored history is not an allocation ledger; no promotion of Bayesian allocation or live-model quality is established by the installed evaluator |
| Synthetic learning | Mature complete postal cohorts and advisory memory for a separately reviewed follow-up | Repeated businesses cannot create new independent support; synthetic outcomes stay synthetic |
| External outcomes registry | Python API/CLI registers original postal/email assignments and imports operator-attested local reports; complete mature cohorts yield separate advisory Bayesian results | No authenticated provider feed, browser screen or automatic model-memory integration |
| Storage and hosted preparation | Local SQLite default; native remote libSQL adapter and bounded operator-only synthetic preparation entry point | This is not the complete hosted visitor workspace or multi-worker release |
| Agentic commerce | Accepted platform direction and a separate source application to assess | No migrated commerce capability in this repository |

The operating contracts and examples live in the [documentation index](index.md).
The [validation guide](validation.md) records attributable test evidence and
remaining limitations. Installed behavior does not imply every epic is complete.

## What learning means here

The shared improvement pattern is:

```text
Product context -> proposal -> human review -> permitted action
                -> observed outcome -> finding -> next proposal
```

Bayesian updates express how counted evidence changes a belief under a declared
model. They do not train the LLM's weights or guarantee better acquisition.
In the postal simulation, complete mature A/B/control counts update Beta
posteriors once. The external registry calculates separate advisory results
from operator-attested evidence. YouTube's qualified-demo reward and future
commerce metrics have their own eligibility and missing-data contracts.

Missing results remain unknown. Model confidence, writing preferences and
synthetic judges do not become customer outcomes. The same underlying event
cannot count twice as independent support because two integrations report it.
Causal lift requires an appropriate experimental design and evidence; a
completion rate or posterior alone does not establish it.

Learned guidance remains scoped and advisory. A rewrite gets a new identity,
requires ordinary review and cannot inherit approval or outcome counts.
See [learning](learning.md), [external outcomes](external-outcomes.md) and the
[YouTube reward contract](youtube-data-reward-contract.md).

## Review, authority and trust

An operator prepares work; a reviewer decides on an exact subject. Local roles
are demonstration identities, not authenticated distinct people or proof of
production separation of duties. Depending on the native workflow, that subject
binds content, audience, source evidence, policy, reviewer generation and expiry.
Current checks at export or simulated acceptance can reject stale approval.

A new draft, changed evidence, suppression, revocation or expired authority can
block an affected action. Historical acceptance remains history. Inference
reservations and saved request identity support recovery without automatically
repeating an uncertain paid call. Keys stay outside prompts, receipts and exports.

Ports and adapters separate business rules from provider mechanics. A compatible
adapter can be selected without rewriting campaign rules, but each new provider
needs capability, identity, error, completeness and recovery conformance.
This is an extensibility design, not a claim of universal CRM or ad-platform support.

## Scope for an initial design partner

The immediate goal is to validate whether a useful contextual campaign proposal
and clear review/evidence workflow solve a recurring problem. A local walkthrough
can support that discussion now. A usable online pilot still needs authoritative
hosted identity, channel access, private asset delivery, trusted task receipts,
compatible provider data and composed release evidence.

The implementation order is maintained in the
[platform map](gtm-platform-map.md#build-sequence-and-coordination) and
[YouTube migration plan](youtube-migration-plan.md). Current priorities include
#133's measurement/reuse boundary and #70/#130 hosted access/composition.
Design-partner feedback can refine the next narrow use case without silently
expanding permissions or changing frozen evaluation contracts.

The current examples use fictional businesses and public iwoca product evidence.
They are not validated iwoca segments or a production connection. The platform
makes no lending decisions, approves no financial promotion, and has no
demonstrated acquisition-efficiency or revenue uplift. Autonomous ad buying,
real outreach, full commerce migration and cross-channel attribution remain
future work. See the [design-partner brief](product-discovery.md) for wording
that can be used without presenting the roadmap as shipped functionality.
