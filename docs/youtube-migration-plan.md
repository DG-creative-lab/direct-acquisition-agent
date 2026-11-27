# YouTube migration into the acquisition workspace

Status: proposed implementation plan, 24 November 2026. The owner has selected this repository as the destination for the YouTube product. This document approves no deployment, paid call, data import, outbound campaign or production cutover.

This is the coordination entry point for two workstreams: platform preparation in the iwoca chat, and YouTube compatibility and migration in the YouTube chat. The intended product is one marketing workspace with channel-specific campaign capabilities. Initial delivery remains bounded preparation, human review and manual export.

The 27 November [platform map](gtm-platform-map.md) places YouTube under
Advertising, alongside future Meta/TikTok channels, with Direct acquisition and
Agentic commerce as separate product areas. It records ownership, channel
access and the incremental build sequence. Continue #133 against its native
measurement contract; a full namespace move or commerce migration is not a
prerequisite. Hosted platform work remains coordinated through #70/#130.

Read alongside [shared product design](multichannel-workspace-design.md), [remaining hosted preparation](hosted-platform-preparation.md), and the existing [multichannel expansion plan](channel-expansion-plan.md). Epic [#60](https://github.com/DG-creative-lab/direct-acquisition-agent/issues/60) remains the overarching platform roadmap.

Issue #129 now specifies the [YouTube channel contract v1](youtube-channel-contract.md) and [authored acceptance examples](youtube-channel-contract-examples.json). The contract selects the native module, review/export format, routing and shared inference/funding boundaries. The open choices listed below belong to the earlier planning baseline; use the contract's implementation handoff for their resolution and remaining hosted prerequisites.

The 25 November [targeting and decisioning feasibility design](targeting-decisioning-feasibility.md)
and [research](contextual-targeting-research.md) revise the next-build decision:
#143 defines actual platform control, permitted data and reward; #144 evaluates
contextual recommendations offline; #133 follows that accepted measurement
handoff. The product selects contextual creative allocations and learns from
qualified outcomes. A visitor recording preference is optional research, not
the product objective or evidence of ad conversion.

## Evidence baseline

After merged #147 (`fecb9f0`), the next #144 slice is the
[opt-in model ranking evaluator](youtube-contextual-benchmark.md#opt-in-model-ranking-evaluation).
It freezes the same authored tasks and uses existing inference reservations,
receipts and runtime recovery. Review it with fake gateways, then separately
authorize a small real-model comparison. No real model quality is established
until that comparison is run. #133 then starts trusted assignment and
generated-sample job/result receipts against the accepted measurement handoff;
its first local rehearsal keeps fake results separate from participants.

26 November implementation checkpoint: merged #146 freezes #143's offline
contract. #144 now has a [native recommendation/benchmark slice](youtube-contextual-benchmark.md):
scoped read-only proposals, exact bundled ads, complete cell/day evidence and
576 authored simulation trials. Retain the rules comparison baseline; the
Bayesian candidate is not promoted on these results. Genuine model ranking
quality remains unmeasured. Accept the explicit measurement handoff before
#133; hosted/live readiness and source retirement keep their existing gates.

26 November checkpoint: #143 records
[offline-only feasibility](youtube-targeting-verification.md) and a
[qualified product-demo action contract](youtube-data-reward-contract.md).
The next build after accepting that contract is **#144's offline benchmark**,
then #133's objective-bound measurement/reuse slice. The first qualified task
requires a requested, server-verified generated voice sample. No current live
qualified-action data or exact-context platform write is verified. Merged #142
is the source baseline for this checkpoint; cloud/asset work can continue in
parallel without turning offline evidence into live readiness.

Update, 25 November 2026: PR #138 is merged at
`a1659ce661d5a92ac7d5ae91c7ad779e9bf7e47b`. #132 now supplies native local
draft/review/manual export and refreshed samples. PR #139 is also merged,
adding reviewed input context. #133's measurement/reuse implementation follows
#143 feasibility and #144's offline recommendation/measurement handoff.
The [shared creative asset design](creative-asset-storage-design.md) records
local catalogue/port foundations and the separate hosted Blob workstream.
It preserves #70/#130 identity/composition ownership and #134 cutover gates.
The table below remains the original planning baseline.

| Repository | Inspected baseline | Use |
| --- | --- | --- |
| Direct Acquisition Agent | `796a4cc3f533e0cbae3b7760e89221d9fe1b1b86`, accepted main after PR #127 | Destination contracts and implemented preparation |
| YouTube campaign agent | `8250e1f4f4ce2150d911a8231cc03bd31c2cab8b`, accepted main | Migration behavior oracle |
| YouTube UX proposal | `f92253945fc418adb3399f0d31fdfc16e99f6f72`, [workspace design](https://github.com/DG-creative-lab/youtube-ad-agent/blob/f92253945fc418adb3399f0d31fdfc16e99f6f72/docs/workspace-ux-design.md) | Requirements input, not implemented application behavior |

The older local iwoca checkout at `788c77e` is behind accepted main. Earlier comparisons against that checkout understate the destination's capabilities. Product profiles, contact/context evidence, channel content, sequence simulation/review, native remote storage, request-bound serverless preparation and saved Company & brief intake already exist. Revalidate changed contracts at each implementation start.

The unmerged YouTube guided-learning exercise at `dd1012966f3ae6811340a863415bdf98c284c920` is excluded. Its source issue #124 remains paused. Do not use that exercise as the migrated Learning page.

## Decision and module ownership

Use the destination's modular monolith, public module contracts, React workspace and composition root. Add a channel capability where its semantics differ; keep shared orchestration behind narrow ports. The first contract issue must decide the exact public YouTube module boundary and serialization before source is moved.

Do not make `runtime` import channel business code, put a universal campaign model in `contracts.py`, depend on a sibling checkout via `sys.path`, or copy retained source architecture exceptions into the destination. Architecture policy stays at `exceptions: []`. A Python package extraction is an option only if it preserves these boundaries and demonstrably reduces migration work.

| Source capability | Destination owner or boundary | Migration treatment |
| --- | --- | --- |
| Campaign drafts, revisions, approvals and exports | Channel-native domain/application API composed with `campaigns` and `reviews` | Adapt contracts first. A YouTube approval cannot silently become a postal or sequence approval |
| Placement catalogue, provenance and classification | YouTube channel capability, exposed through public ports | Preserve source identity and evidence; do not recast placements as CRM recipients |
| Conversation planning and agent tools | `conversations`, workspace application ports and workflows | Reuse orchestration with an explicit YouTube capability; unsupported requests must not default to postal preparation |
| OpenRouter catalogue, route checks, bounded inference and pinned prompts | `reasoning` ports, provider adapters and composition | Reconcile lifecycle and funding contracts before reuse. Never create two ledgers for the same provider effect |
| Viewer assets, scoped comparison links and measured events | Channel-native viewer/measurement capability and HTTP adapter | Preserve protocol, permitted media, deduplication and participant eligibility |
| Instruction experiments and Bayesian recommendations | Channel-owned evidence policy with a public advisory projection | Preserve the source experiment protocol and stopping policy; keep commercial learning cohorts separate |
| Save, apply and retire findings | Channel evidence plus application commands; shared Learning read model | Recheck current evidence and authority. Applying creates an unapproved revision with lineage |
| Per-invite compressed SQLite workspace snapshots | Explicit migration adapter, only if later required | Do not install snapshot storage as the destination database model |
| Invite authentication and tab-memory model key | Hosted identity and model-session contract | Source invites are not organization membership. Keys are never migrated |
| Authored scenarios and live capability benchmark | Existing composed evaluation owner #74 plus channel fixtures | Preserve independent expected outcomes and rubric versions; do not rewrite the oracle to make the port pass |

The source preview stores a whole workspace SQLite snapshot behind invite-scoped compare-and-swap. The destination uses native remote SQL through its Hrana adapter. These provide different transaction and recovery boundaries. Existing Turso support is useful infrastructure, not proof that source approvals, receipts or viewer records can be copied directly.

## Build order and gates

1. **Freeze the channel contract.** Inventory public operations, exact identities, approval subjects, permissions, prompt versions, provider receipts, viewer protocol and evidence lineage. Map owners, define unsupported states, and choose the first public channel boundary. Use authored examples and sanitized schemas, never private database exports.
2. **Build one offline preparation slice.** From an explicitly selected YouTube capability and a saved brief, use the same workspace command path to create a channel-native placement/instruction draft, review it and produce its manual export. Demonstrate meaningful revision and reject stale or foreign approval. A missing capability must produce an explicit blocker.
3. **Prove targeting/data/reward feasibility (#143).** Define the unit we can control, exact platform route and positive/negative targeting support, permitted source fields, reporting grain, primary reward and budget/pacing constraints. Record an offline/manual/shadow/blocked-live decision with evidence. Documentation or an API resource name is not account/delivery proof.
4. **Compare offline contextual recommendations (#144).** Evaluate rules, LLM-assisted ranking and a simple Bayesian allocation candidate on independent relevance tasks and known-truth simulations. Keep simulation, prediction and causal claims distinct. Produce the exact measurement handoff before choosing the next #133 slice.
5. **Port the measurement and reviewed learning loop (#133).** Consume the accepted objective/action/reward contract. Deliver usable exact assets, deduplicated scoped outcomes, current evidence and unapproved finding reuse. Preserve the original instruction-beta-v1 comparison experiment separately; never reinterpret its completions or preference as ad conversions.
6. **Prove hosted/shadow and separately authorized live composition.** Combine the preceding slices with hosted identity, native remote storage, frontend and model funding/session contracts. Verify fresh-instance recovery, isolation and budget exhaustion. Shadow recommendations make no writes/spend and cannot prove the value of unexecuted alternatives. Live tests require their own bounded randomized design and authorization.
7. **Decide cutover explicitly.** Compare source and destination behavior, review retained history and rollback options, then separately authorize public routing and any data import. Keep the existing source deployment available until this decision.

The platform work can run alongside these channel gates: hosted tester identity
and APIs, #131 reviewed-input grounding/preparation, #140/#141 shared assets,
frontend delivery and operations. Hosted release waits for the applicable
evidence from both tracks. Offline/manual feasibility can proceed without cloud
provisioning; it does not claim a live route. Do not wait for real CRM, email
delivery or a human-call pilot to evaluate the permitted offline baseline.

## Workstream coordination

| Track | Primary working chat | Owned deliverables |
| --- | --- | --- |
| Shared platform preparation | Existing iwoca chat | Hosted identity/access, workspace API composition, intake grounding, funding/session policy, frontend delivery and remote operations |
| YouTube migration | This YouTube chat | Source contract inventory, channel port, viewer/measurement/finding parity, source-to-target comparison |
| Integration and release | Joint checkpoint in issues | Composition changes, composed evidence, release/cutover decision |

Before implementation, claim an issue and record its baseline, branch and public contract. Shared files such as `bootstrap.py`, workspace ports, HTTP routing, schema migrations, profile selection and model admission need one active integration owner at a time. Agree a contract or merge a prerequisite before another branch changes those surfaces. Use ordinary commits/PRs and issue links; parallel chats are not independent authorities over shared state.

Leave the existing local iwoca working tree and its unmerged evaluation work intact. This design branch starts from accepted main and contains no runtime commits from that branch. Avoid building a second YouTube-only Knowledge, Learning or navigation shell while the shared destination is being prepared; preserve those source issues as requirements and trace them to the destination.

## Compatibility and recovery acceptance

| Scenario | Required observable result |
| --- | --- |
| User requests YouTube advice or preparation | Correct installed channel is selected or ambiguity is clarified; no postal job is created accidentally |
| A draft changes after review | Old approval cannot authorize the new revision; exports identify the exact approved subject |
| Another organization guesses an ID or viewer-management URL | No private draft, evidence, asset-management access or approval is exposed |
| A provider response was paid for before process failure | Recover the original receipt/request under the pinned prompt; no automatic second paid call |
| A write or commit has an uncertain result | Reconcile the durable original request before retrying; show uncertainty rather than fabricated success |
| Two requests apply one finding or submit one revision | Exact replay returns the original result, conflicting input is rejected, no duplicate draft/effect |
| Viewer results are absent, rehearsed, duplicated or corrected | No invented independent evidence; recommendation uses the current eligible cohort |
| A user rejects advice or retires a finding | Preference/review state changes, measured history remains intact |
| Hosted session is revoked, capacity is exhausted or storage fails | Action stops with a truthful blocker; no paid fallback or cross-workspace continuation |

Use the source's versioned canonical cases, policy simulations, reuse cases and capability tasks as behavior evidence, alongside destination boundary tests. Offline conformance, live provider quality, hosted recovery and human usability are separate claims. Record baseline, model, prompt, rubric, actual calls, known/unknown cost and failures with each applicable report.

## History, rollback and unresolved decisions

First delivery uses authored data in a new scoped workspace. It imports no source invites, keys, approvals, historical outcomes or pending provider work. A later history-import proposal must preserve original identifiers/bytes, provenance and scope, reconcile unknown effects, and distinguish historical approvals from current authorization. Data import needs its own acceptance and rollback plan.

Rollback before cutover means retaining the source preview and not routing new work to the failed destination. After any real writes, rollback must account for new destination work; restoring an old database is not a valid way to erase dispatched or unknown effects. Paused and restored work must remain fenced.

Open decisions for the contract stage:

- Exact YouTube module/public API and supported first artifact/export formats.
- Product/brand scope inside current organization authority; do not invent project sharing permissions prematurely.
- Unified funding and credential-session contract: current iwoca server-side explicit generation and source tab-memory BYOK are not interchangeable.
- Public viewer asset hosting, opaque participant access, revocation and retention under the chosen hosted composition.
- Which source histories users actually need before cutover; mass import is deferred.

## Implementation issue map

Migration epic: [#128](https://github.com/DG-creative-lab/direct-acquisition-agent/issues/128), under platform epic #60. All children are provisional planning items, not evidence that deployment or migration has occurred.

| Issue | Deliverable | Dependency and owner |
| --- | --- | --- |
| [#129](https://github.com/DG-creative-lab/direct-acquisition-agent/issues/129) | Freeze channel and compatibility contract | First YouTube task |
| [#130](https://github.com/DG-creative-lab/direct-acquisition-agent/issues/130) | Hosted frontend and preparation APIs | Platform; consumes #70 identity, #129 for YouTube integration |
| [#131](https://github.com/DG-creative-lab/direct-acquisition-agent/issues/131) | Saved intake to live preparation | Platform; reuse merged intake, agree funding/session contract with #129 |
| [#132](https://github.com/DG-creative-lab/direct-acquisition-agent/issues/132) | Native YouTube draft, review and export | YouTube; #129, authored context offline first |
| [#143](https://github.com/DG-creative-lab/direct-acquisition-agent/issues/143) | Targeting controls, permitted data and reward feasibility | YouTube; first next-build gate, record offline/manual/shadow/blocked-live disposition |
| [#144](https://github.com/DG-creative-lab/direct-acquisition-agent/issues/144) | Offline contextual ranking and budgeted Bayesian allocation benchmark | YouTube; #143 contract/disposition, independent baseline and #133 handoff |
| [#133](https://github.com/DG-creative-lab/direct-acquisition-agent/issues/133) | Objective-bound measurement and reviewed learning | YouTube; #143/#144 handoff after #129/#132; retain separate instruction experiment; #130 for hosted delivery |
| [#134](https://github.com/DG-creative-lab/direct-acquisition-agent/issues/134) | Hosted parity and cutover recommendation | Joint under #74; #143/#144/#133 handoff, #130/#131/#132 and applicable #70 |

Platform #70 and #74 retain their wider access and release-evidence ownership. Source [YouTube #136](https://github.com/DG-creative-lab/youtube-ad-agent/issues/136) coordinates the repository transition; source #133 to #135 retain UX/Knowledge/Learning requirements and defer duplicate standalone builds. No source issue is closed as delivered by this plan.
