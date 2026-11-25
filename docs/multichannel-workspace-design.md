# Shared marketing workspace: initial product design

Status: provisional product and architecture design, 24 November 2026. It guides incremental implementation under #60 and the YouTube migration. It does not describe every screen or integration as implemented.

The user should prepare and improve a campaign in one workspace: supply product context, ask the campaign agent for help, review a concrete artifact, then use actual observed results to decide the next change. Shared navigation and knowledge should reduce repeated work across channels. Channel-specific identities, approvals and evidence remain explicit.

This design extends the existing [organization profiles](organization-profiles.md), [Company & brief intake](intake.md), [conversations](conversations.md), [review](reviews.md), [learning](learning.md) and [channel expansion](channel-expansion-plan.md). The [migration plan](youtube-migration-plan.md) maps source capabilities; [hosting preparation](hosted-platform-preparation.md) separates infrastructure already delivered from release gaps.

## User-facing structure

| Surface | User purpose | Functional boundary |
| --- | --- | --- |
| New chat | Ask one campaign agent to advise, prepare or revise | Installed capabilities only; clarify ambiguous channel/brief. Advice alone does not create or approve a campaign |
| Campaigns | Find drafts, revisions, reviewed artifacts and their status | Channel and current scope visible. Exact artifact identity drives review/export |
| Knowledge base | Supply company/product material and inspect what the agent used | Extend saved intake and existing guidance views. Separate assertions, reviewed claims, preferences and proposed updates |
| Learning | Inspect actual campaign evidence and review recommendations | Same saved evidence/finding from chat and dedicated view. No standalone authored learning exercise |
| Recent chats | Return to a saved conversation | Authorized current scope; historical proposals remain historical |
| Account avatar | Manage identity, model connection, model/budget and preferences | Administrative settings outside the composer; only expose roles/tasks that exist |

Use a collapsible sidebar, calm readable surfaces, modest corner radii and light/dark/system themes. Keep agent activity inline and expandable in the conversation. Show concise operational summaries, tool actions, inputs/outputs, blockers and model identity where useful. Do not promise hidden model reasoning or fabricate thinking from fixtures. The auxiliary panel is for artifacts and, only if later implemented, delegated work.

One campaign agent is the initial orchestration model. Capabilities/skills are not personalities users must choose before they can ask a question. Future delegation requires a separate need and lifecycle contract; it does not require a VM per specialist by definition.

Do not expose empty project switchers, disabled future channels or unrelated administration to imply completed capability. For empty Knowledge or Learning, offer the next valid action or state that evidence has not arrived. Show synthetic/rehearsal labels at the point of use.

## Operational objects and authority

The following are semantic roles to map onto existing public APIs, not a mandate for a new universal schema.

| Object | Identity and provenance | Who may change it; what it may authorize |
| --- | --- | --- |
| Organization and current actor | Authoritative hosted identity; server-resolved scope | Current membership/roles govern commands. Browser fields and model text cannot create membership |
| Company/product source draft | Existing intake revision and source assertions | Authorized editor can revise; text alone cannot authorize generation, approved facts or delivery |
| Reviewed profile/fact context | Immutable version/hash, source/evidence IDs, qualifications and freshness | Existing reviewed grounding rules; task consumes a frozen permitted projection |
| Campaign brief and conversation | Scope, channel, revision, messages and frozen planning context | New messages/proposals do not silently mutate a confirmed campaign. Agent may ask, propose or invoke permitted commands |
| Channel artifact | Native subject ID, exact bytes/hash, version and lineage | Revision creates a new subject. No inherited approval or outcome count |
| Approval | Exact native subject, scope, actor and current evidence/authority | Explicit human decision via application boundary, rechecked where required at effect time |
| Provider effect | Original request, prompt/model version, reservation, receipt and known/unknown state | Only admitted bounded execution. Retry/recovery cannot repeat an uncertain paid request |
| Observation/cohort | Channel protocol, assignment, participant/source, time, completeness and correction history | Authoritative event ingestion and channel eligibility rules. Missing evidence stays unknown |
| Finding/recommendation | Evidence references, policy version, context and current status | Advisory. Human can inspect, prepare a draft, keep current guidance or retire it |
| Human preference | Explicit person/scope/version and origin | Shapes permitted future proposals; never edits measured outcomes or grants campaign authority |

Resolve organization scope now. Product/brand subdivisions should reuse existing profile/intake identity until an explicit project-sharing requirement is implemented. Do not assume the source invite model supplies brand ownership or team roles.

The proposed [creative asset storage design](creative-asset-storage-design.md)
adds shared versioned asset references under `creative`, SQL search metadata
and replaceable file adapters. #140 supplies the local foundation and #141 the
private hosted Blob path. This does not require a new empty navigation module
or make public asset publication implicit.

## Knowledge and learning are different user jobs

Knowledge answers: “What should the agent know about this product, and what did it use?” Reuse Company & brief for editable source material, existing product fact packs for reviewed claims, and guidance snapshots for context attribution. A source URL is not automatically retrieved, permitted or current. If a new ingest capability is added, bound acquisition, provenance, permitted use, retention and freshness before passing content to the agent as data.

Learning answers: “What happened, how reliable is the evidence, and should we change something?” Show campaign scope, channel, eligible sample, exclusions, uncertainty, policy version and recommendation. Keep the same finding identity across chat and the Learning view.

The four initial actions are inspect evidence, prepare an unapproved change, keep current guidance and retire a finding. Preparing a change records lineage and requires ordinary review. Retiring stops future recommendation use while retaining history. A human can record a preference even when evidence is weak, but the UI must not present that preference as statistical validation.

YouTube comparison completion and choice evidence use the source viewer protocol. Postal/mail/email outcomes use their own accepted assignments, mature cohorts and commercial definitions. A common Learning screen is possible; a pooled posterior or combined support count is not justified by a common screen. Cross-campaign promotion of guidance requires an explicit scoped review and current eligible evidence.

## Representative flows and failure states

1. **First visit.** An authorized tester opens a scoped workspace, saves company and campaign drafts, and asks for a YouTube proposal. The agent uses the identified source revisions, asks for missing material where necessary, and prepares an unapproved channel artifact. The user can inspect context and review the exact revision. A useful result is an understandable artifact and next action, not a tutorial completion.
2. **Ambiguous intent.** “Contact the best prospects” does not select YouTube or grant email consent. The agent clarifies the intended channel/source when it cannot uniquely resolve a permitted task. Unsupported capabilities produce an explicit blocker rather than defaulting to postal execution.
3. **Actual learning.** Eligible viewer events produce a recommendation with uncertainty. Opening it from chat or Learning shows the same evidence. Applying it prepares one new unapproved draft; replay returns that draft. Rehearsals, duplicate visits, missing outcomes and corrections cannot become independent support.
4. **Existing workflow.** A postal or sequence user continues through its existing exact-subject review and simulated acceptance. Adding YouTube leaves its product grounding, controls, stop rules and evidence meaning intact.
5. **Changed authority or evidence.** A revoked session, edited draft or expired fact context blocks an affected action. A previously valid screen or saved report cannot override the current application check. Show the specific blocker and safe next action.
6. **Interrupted model or write.** The UI displays the durable stage and original request identity. Reload recovers known results. An unknown paid effect stays fenced rather than being retried as a new task; a failed write is not labeled saved.

Evaluate these flows through public commands and browser-visible outcomes. Measure correct channel selection, task completion, groundedness, source attribution, exact review/export, truthful recovery, usability and scoped evidence reuse. Retain separate deterministic conformance, human rubric and live model reports. Better model scores do not prove hosted isolation or correct Bayesian evidence.

## Incremental scope and open choices

First reuse the existing shell, intake and application modules. Implement the YouTube capability and required projections, then refine shared navigation, Knowledge/Learning interactions, rounded surfaces, inline activity and themes against actual capabilities. Avoid a parallel shell redesign in both repositories.

The immediate scope excludes a universal CRM, revenue attribution platform, autonomous cross-channel optimization, outbound YouTube ad buying, real email/call activation, subagent management and automatic global policy updates. Those may be future platform directions, with their own user need and authority/evaluation gates.

Open design choices are the public channel module contract, the first supported export and viewer hosting format, the current-scope vocabulary, funding/session behavior and future history import. Resolve them in implementation issues before binding shared storage or authority to speculative abstractions.

The subsequent [YouTube channel contract v1](youtube-channel-contract.md) resolves the native module, manual JSON export, organization/profile scope, viewer ingress and logical funding/session boundaries. Hosted mechanism choices and history import retain their separate implementation/release gates.
