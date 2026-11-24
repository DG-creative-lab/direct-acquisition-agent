# YouTube channel contract v1

Issue [#129](https://github.com/DG-creative-lab/direct-acquisition-agent/issues/129), 24 November 2026. Status: specified for implementation review. This contract does not install a capability, change a schema, enable inference or approve cutover.

## Decision and scope

Add one business module, `acquisition.youtube`, for YouTube campaign packages, exact native review/manual export, comparison viewers, instruction experiments and evidence-backed findings. Reuse the destination's conversations, runtime, reviewed product context, inference journal and workspace. Workflows compose their public APIs; bootstrap selects adapters.

The first implementation is **authored context → placement draft → exact human review → manual JSON export**, followed by a functional viewer and learning loop. A user can also ask for advice without permitting a draft. No ad buying, Google Ads write, real CRM/email/call effect, source-history import or paused guided-learning exercise is included.

This is a workflow-level contract spanning intent, frozen context, tools, authority, transactions, viewer observations and feedback. Normative authored acceptance examples are in [youtube-channel-contract-examples.json](youtube-channel-contract-examples.json). They are future acceptance inputs, not results from an implemented port.

### Evidence and compatibility baseline

- Destination: `2244e06783bddd02c02a096732eee868ece4bb0a`, merged design PR #135.
- Source: `8250e1f4f4ce2150d911a8231cc03bd31c2cab8b`, accepted YouTube main.
- The [migration plan](youtube-migration-plan.md) and [shared workspace design](multichannel-workspace-design.md) provide product scope. Current [admission](run-ownership-admission.md), [architecture](architecture.md), [intake](intake.md) and [hosted preparation](hosted-platform-preparation.md) remain binding.

The source paths below are relative to the pinned YouTube repository; destination paths are relative to this repository. Source snapshots, key material and private conversations are excluded.

| Source authority | Contract retained | Destination treatment |
| --- | --- | --- |
| `application/campaigns.py`, `application/planner_context.py`, `domain/fingerprints.py` | Scoped revisions, exact package/media fingerprint, current approval, manual export | Native YouTube subject and store; no conversion to postal/sequence approval |
| `agent/draft_permissions.py`, `agent/planning_models.py` | Request permission `none / placements / instruction_test`; typed tool use; prompt pin | Retain permission meaning; workflows freeze it with conversation/task context |
| `foreground_inference.py`, `inference_ledger.py`, `adapters/openrouter_reviews.py` | Reserve before effect, pinned wire request, received-result recovery, charging uncertainty | Extend the single destination reasoning journal through public ports |
| `measurement.py`, `instruction_tests.py` | Assigned browser visits, versioned content, exact event replay, five-minute completion window | Channel-owned viewer/event/experiment state |
| `domain/instruction_policy.py`, `learning.py` | Pinned prior/utility/stopping policy; current evidence and correction; unapproved reuse | Channel-owned recommendation and finding lifecycle |
| Source tests named in the examples | Independent behavior expectations | Port assertions to destination commands, not source SQL shape or exception wording |

No source approval is trusted as current destination authority. Old source stores remain readable in the source app. New destination artifacts use versioned native identities. An eventual importer requires a separate mapping and authority review.

## Module and port ownership

| Planned owner | Responsibility and allowed dependencies |
| --- | --- |
| `youtube/domain.py` and pure supporting files | Immutable values, package validation/fingerprints, viewer protocol and statistical policy. Standard library and technical contracts; no SQL, clock I/O, provider SDK or runtime service |
| `youtube/ports.py` | Narrow `YouTubeStore`, `YouTubeAuthority` and `ComparisonAssets` contracts. Explicit typed values; no connection/callback/native handle in the public API |
| `youtube/application.py` | Commands and current-state validation using those ports and public creative context validation. No dependency on conversations, reviews, learning or concrete adapters |
| `youtube/__init__.py` | Named exports of commands, values and errors. Cross-module callers use this facade |
| `workflows/youtube_preparation.py` | Compose public conversation/admission, reasoning, runtime and YouTube APIs. Register the exact capability/task plan; no direct SQL |
| Workspace application ports/service/views | Route UI and typed tools to the same commands; project native subjects, findings, context and genuine activity |
| SQLite/Turso adapters | Channel records, atomic units and actual asset/authority adapters. Reuse the existing Database/remote transport and migration mechanism |
| HTTP adapters and bootstrap | Resolve actor/scope, translate public requests; bootstrap alone wires implementations. Separate narrow viewer ingress from private workspace API |

Add the new module, public dependency edges and exact production-file classifications to architecture policy during #132. Keep `exceptions: []`. Do not make runtime import YouTube, add YouTube business types to `contracts.py`, import sibling source checkouts or enlarge generic postal/sequence review types.

YouTube owns its native review semantics; shared review screens can project tagged YouTube subjects. The existing `reviews` module continues to own its current subjects. `YouTubeAuthority` consumes the platform's current actor/membership policy, not a second actor registry or role database.

### Persistence and atomicity

One channel store owns package revisions, approvals, export receipts, viewer grants/events, experiments, snapshots and findings in the existing application database. Separate private tables may implement these records; their names and numeric migration version are not public contracts.

The store exposes bounded commands such as `save_revision`, `decide_review`, `publish_export`, `assign_visit`, `record_event`, `save_snapshot`, `save_finding`, `retire_finding` and `apply_finding`. Each accepts frozen values, expected identities and server-resolved authorization, and returns immutable receipts plus a separately current projection.

Adapter transactions must atomically commit:

- Command input fingerprint, domain changes and original result receipt.
- Preparation result, runtime task settlement and conversation artifact/result linkage.
- Approval, exact reviewed snapshot and its result receipt.
- Experiment assignment with first viewer arrival; choice with completion.
- Finding application, the new unapproved revision and its lineage/result linkage.

Use an explicit composition-level transaction adapter to join native runtime settlement and channel publication, like existing channel settlement. No workflow receives a raw connection or invents a second event journal. Provider I/O and asset acquisition happen outside write locks. Immutable asset digests/currentness and authority are rechecked before publication. Failure before commit rolls back all listed writes; a lost acknowledgement recovers the committed receipt.

## Identity, scope and serialization

Channel tag: `youtube`. Contract version: `youtube-channel/v1`. A reference always carries its type/version, not just an ID-shaped string.

| Value | Required fields and meaning |
| --- | --- |
| `YouTubeScope` | Server-resolved `organization` and installed `profile_id`. Campaign ownership binds this pair. Profile selection grants no membership |
| `CampaignRef` | `channel=youtube, campaign_id`; resolved only under YouTubeScope |
| `RevisionRef` | CampaignRef + positive integer `revision` and exact `package_fingerprint` |
| `ContextRef` | Saved company/brief IDs and revisions or authored profile version, reviewed context/evidence IDs and fingerprint. State which source is asserted, reviewed or missing |
| `SubjectRef` | `kind=youtube.manual_review/v1, subject_id, campaign_id, revision, package_fingerprint, payload_sha256, delivery_fingerprint`. Stored ownership and current evidence/authority generation bind it to scope |
| `ApprovalRef` | Native approval ID, exact SubjectRef, human actor and decision time, current validity/revocation state. Not valid for dispatch or any other channel |
| `ExperimentRef` | Test ID, original/revised approved content hashes, correction/review references and protocol/policy versions |
| `SnapshotRef` | Test ID, snapshot ID, cutoff, protocol, arm/content hashes, separate source cohorts and superseded snapshot reference |
| `FindingRef` | Native finding ID, source test/snapshot, context/policy/correction, tested wording/hash and active/retired status |

Organization/profile values supplied by a model or browser are rejected as authorization inputs. Source client/brand/workspace/installation IDs require verified import mappings if migration is later approved. They are never inferred from an invite digest.

Wire objects are strict JSON: reject unknown command fields, duplicate keys, booleans used as revisions, non-finite numbers and out-of-range values. Native IDs are opaque strings matching `[A-Za-z0-9_.:-]{1,160}`; revisions are positive signed 64-bit integers, with zero allowed only for creation's expected revision. Hashes are 64 lowercase hex characters. Event IDs retain the source's 32 lowercase hex format. Timestamps are server UTC integer milliseconds; display formatting carries no authority.

Canonical hashing is UTF-8 of `json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)`, then SHA-256. Preserve list order. Package-compatible source fields, Unicode escaping and hash bytes remain stable; destination metadata belongs in a versioned outer reference. Include a namespaced schema in new reference/command fingerprints. A schema/prompt/protocol change needs an explicit new version, never reinterpretation of old bytes.

Authored hash vectors cover ordering and Unicode. An unsupported contract version is inspectable as historical data where permitted but cannot execute.

## Routing and request envelope

Resolve a uniquely supported explicit YouTube intent against the installed capability catalogue; no model confidence threshold creates authority. If multiple channels or campaigns remain plausible, ask one material clarification. If the channel is known but uninstalled, return `capability_unavailable`. No fallback to the postal constructor.

Route before invoking channel-specific brief validators. YouTube advice/manual preparation with an unset advertising budget must not enter the postal GBP-total clarification loop or require CRM contacts. Campaign advertising budget and USD inference allowance are different values. Existing postal validation remains unchanged for postal requests.

A private command envelope has `contract, operation, request_id, target, expected, inputs`. These are caller data. The host separately supplies resolved scope/actor, current authorization, clock and any admitted task/funding proof. Reads use scoped typed references. Creation uses `target=null` and `expected.revision=0`; updates require the exact current positive revision and relevant fingerprint. No raw provider credential, role, organization override or fabricated receipt is accepted in `inputs`.

Idempotency key: `(organization, actor, operation, request_id)`, with exact original input fingerprint. Also constrain the underlying semantic operation, such as one admission per conversation revision/action and one finding application per target revision. A different request ID cannot bypass an admitted operation or budget.

Exact replay may return the original immutable receipt, labeled historical if current state changed. It must reauthorize inspection first and must not repeat effects. Different inputs under the key give `request_conflict`. A receipt does not make an old approval, evidence snapshot or session current again.

An export receipt replay is not a download grant. Returning file bytes, a signed asset URL or an active viewer grant always rechecks the operation's current export/access guards, even on a cached result. Historical receipt inspection may show identity/status without restoring a stale download.

### Command surface

Names are proposed public operations, not new HTTP endpoints in this PR. Typed model tools and HTTP/CLI translate to these operations.

| Operation | Required inputs beyond envelope | Result; preconditions |
| --- | --- | --- |
| `read_campaign`, `read_catalogue`, `read_measurement_capabilities` | Scoped target/revision or bounded catalogue query | Current draft/context, admitted provenance, or instrument definitions. Definitions make no traffic claim |
| `classify_catalogue` | Exact catalogue/context versions and any admitted analysis request | Advisory context assignments, uncertainty and provenance; read/analysis authority and separate inference consent if a live classifier is used |
| `prepare_placements` | ContextRef, admitted catalogue references, proposed placement rows | New unapproved revision; `placements` request permission and current draft authority |
| `start_brief` | Current RevisionRef, title, goal and installed comparison context | Distinct new brief identity in an unapproved campaign revision; draft authority and `placements` request permission; retain only compatible placement rows |
| `prepare_instruction_test` | Approved baseline/review/correction, selected instruction components | New unapproved revision; `instruction_test` permission; only instruction wording changes |
| `review_package` | RevisionRef and current delivery composition | Exact preview/SubjectRef, blockers and prior history; read only |
| `approve_package`, `revoke_approval` | Exact SubjectRef or ApprovalRef; explicit human decision | Immutable decision receipt; current human review authority; never a model tool |
| `export_manual` | Exact SubjectRef + current ApprovalRef | Frozen manual export and digest; current subject/assets/delivery and export authority |
| `review_performance` | Approved RevisionRef and scoped captured delivery/viewer evidence; correction is optional and resolved by the application | Saved advisory review after transactional currentness checks, applying the latest applicable correction if one exists; no draft or approval |
| `record_correction` | Exact review/package target and an explicit human correction, including keep-takes | Current correction receipt; review authority. It changes interpretation/constraints, never measured observations |
| `start_experiment` | Approved test revision, original approved snapshot, current keep-takes correction, explicit batch allowance | Pinned experiment and narrowly scoped viewer grant; review-write authority |
| `assess_instruction_experiment` | Evidence captured for both bound arms, current correction and allowed assessment reason | Saved verified assessment; review-write authority and current evidence. Insufficient evidence remains an explicit result |
| `snapshot_evidence` | ExperimentRef and original operation ID | Cumulative immutable SnapshotRef with per-source counts, same result on exact replay |
| `read_learning`, `save_finding` | RevisionRef, current snapshot/decision as applicable | Typed evidence/recommendation or active finding; save only for an eligible reuse decision and learning-manage authority |
| `apply_finding` | Current target RevisionRef, finding ID and correction ID | One new unapproved revision; `instruction_test` permission, tested wording/hash, matching policy/context and current evidence |
| `retire_finding` | Current target and finding ID | Retired receipt; learning-manage authority. Observations are retained |

All private reads require current read permission. Writes recheck command-specific permission inside the committing unit. Request permissions are exactly `none`, `placements`, `instruction_test`; they are not cumulative. They can only narrow platform authority. Catalogue import, product-fact approval and global guidance promotion remain separately authorized capabilities.

For `prepare_placements` creation, `target=null/expected.revision=0` admits a new scoped campaign and revision 1 from the specified authored/reviewed ContextRef; it cannot clone approval. Updates preserve the campaign's verified ownership/context or require a separately confirmed brief revision. Placement rows retain source fields `id, title, creative, source`, with `catalog_ref` and optional corroborated `source_reference` for registered entries. Require unique source-valid video IDs, installed creative/context keys and an exact current scoped catalogue match. First-slice offline sources are `synthetic/sample_search`; registered sources are `licensed/creator_supplied`, never arbitrary model assertions.

Retain source limits: at most 2400 placement rows, title at most 3000 characters, brief title 1 to 120 characters, goal 1 to 500, revised instruction 1 to 500 and different from the original after trimming. HTTP byte, catalogue page, conversation and task limits may be stricter and must return an explicit bounded-input reason. Empty placements may be saved as an incomplete draft; required groups/media still block approval. An identical placement save returns its original/current revision rather than appending a new one. Source `start_brief` is retained with narrowed request permission as a new native operation.

Source tool aliases map to these commands: `inspect_catalog → read_catalogue`, `classify_catalog → classify_catalogue`, `save_placement_draft → prepare_placements`, `prepare_next_test → prepare_instruction_test`, and `apply_instruction_finding → apply_finding`. Resolve selected IDs or context filters against the run's actual scoped classification/catalogue receipt; never accept model-invented source titles or provenance. Ambiguous classifications remain review candidates. Source setup validation/activation and platform-report adapters are outside this initial capability and must report unavailable rather than imply a live campaign.

Imported descriptions, user text, learned findings, tool results and model output are data. They cannot select organization, amend request permission, supply approval or execute instructions. Presentation renders them as text, with explicit permitted-link handling.

### First performance review and correction currentness

An approved package can receive its first performance review without any correction. Capture the delivery/viewer evidence, then recheck package approval/content and captured viewer activity inside the saving transaction. Resolve the latest applicable correction for that scoped comparison in the same transaction. If none exists, save an uncorrected review with no correction binding; do not require a prior review or invent a keep-takes decision. If one exists, regenerate the proposal from the validated evidence and apply that current correction, retaining its exact identity/content in the saved review. A caller-supplied or capture-time correction cannot override a later applicable correction.

The ordinary sequence is **uncorrected review → explicit human correction against that review → new performance review incorporating the correction → instruction draft**. The new review uses a new command request ID; replaying the first review returns its historical uncorrected result. Correction recording and later review leave the first review and observed counts unchanged.

Before preparing an instruction test, recheck the approved package, saved review and latest applicable correction in the committing unit. First compare the saved review's correction binding with current state: a difference gives `correction_stale` and requires a new review before preparation. This includes an uncorrected review used after the first correction was recorded, or an older review used after a correction was replaced. If the bindings match but no current keep-takes correction exists, return `correction_required`. A current supported correction and fresh matching review permit the normal unapproved instruction draft.

## Package, review and first export format

Retain the source package vocabulary: `campaign_id, revision, data_label, title, brief, policy, proposed_setup, groups`, and optional `instruction_test/instruction_reuse`. A group retains context, creative/comparison versions, permitted preview/media digests, source-linked placements, content and viewer path. Synthetic IDs remain fictional; licensed/creator-supplied catalogue candidates remain inventory-unverified. Contextual relevance is not targeting inventory verification.

First format: `youtube-manual-export/v1`, downloadable UTF-8 JSON, MIME `application/json`. It is a **manual setup artifact**, not an executable Google Ads request. Keep objective/format and unset or explicitly supplied budget/schedule truthful. No purchased placements or conversion outcomes are implied.

The review preview freezes a payload containing the native package, safe delivery references and manual limitations. SubjectRef binds its canonical payload bytes plus delivery/media manifest. Delivery includes actual supported viewer origin/routes and content hashes. Ephemeral bearer secrets, private media paths and model credentials never enter the exported payload. Public viewer grants are limited to content explicitly approved for that exposure.

`review_package` computes this preview without a write or capability grant. Derive the subject ID from a namespaced digest of scoped campaign/revision, package/payload/delivery hashes, review policy and current evidence/authority generation. `approve_package` rebuilds and compares that exact preview inside the native transaction, then stores the subject, snapshot and decision atomically. A caller-supplied subject ID cannot substitute for recomputation.

Approval records the frozen payload, subject and human decision. The download envelope contains that exact payload and an immutable approval receipt. Its own bytes/digest are frozen on the first export and returned identically on replay. Approval metadata is outside the payload hash to avoid a circular dependency. Show the same payload in review and download.

At export, reject a changed revision, media, instruction text, delivery configuration, revoked approval or unavailable required asset/link with a specific blocker. A new deployment may reuse a stable validated viewer origin; if its delivery manifest changes, prepare a new subject and review. An old snapshot remains historical, not renewed authority. A local-only link must be labeled local; it cannot pass hosted usable-export acceptance.

## Viewer and evidence contract

The private workspace API and public viewer ingress have different principals. A viewer grant is an opaque, purpose-limited server mapping to a test/approved comparison, allowed content, source cohort, expiry/revocation policy and event namespace. It grants no campaign listing, private evidence, review, model or mutation authority. Hosted issuance/access implementation is gated by #70/#130.

Public operations are `open_comparison(grant, browser_ref?)` and `record_event(grant, visit_ref, event_id, example_ref, kind, take)`. The server resolves scope/test/content; the public caller cannot supply organization, arm, cohort or approved content hashes. Browser references are opaque 32-hex pseudonyms and are not proof of a distinct human.

- First open atomically creates a stable original/revised assignment and arrival; reopening preserves the assigned arm and visit. Do not add a second independent arrival.
- Events are `start, finish, choose`; finish requires a start and choose requires both takes finished. Exact event-ID replay returns progress; changed payload under that ID conflicts. Choice and completion commit together.
- Protocol v1 is `assignment_unit=browser_visit`, metric `completed_comparison_per_assigned_visit`, window 300000 ms, eligible source `participant`. Participant, rehearsal, fixture and unknown remain separate.
- Server time and source protocol determine maturity, completion and cutoff inclusion. A still-unresolved visit is not a failure. A visit whose window matured without timely completion can count as a non-completion under this protocol. Missing/corrupt time stays unresolved; source history is not repaired by inference.
- Only assigned visits enter the experiment's counts. Ordinary comparison traffic, fixture actions, rehearsal links and unknown legacy source do not become participant evidence. Fixture ingress is unavailable publicly.
- Same media/comparison, only instruction wording changed; both approved versions and current keep-takes correction are required before a test starts. Missing media blocks the operation without destroying prior assignments/progress.

Snapshot v1 is cumulative and idempotent, retaining exact protocol, cutoff, per-arm content fingerprints and `mature_arrivals/completions/unresolved` per source. Recompute evidence under the current transaction, including same-millisecond cutoff changes, before saving or applying a finding.

The source's saved agent assessment is separate from the Bayesian action. It uses the pinned `evidence-reasons-v2` reason contract and a minimum of 20 eligible arrivals per version; below that it must report insufficient visits. Preserve its current correction and content checks. Do not substitute an assessment reason for a posterior decision or confuse the per-version assessment threshold with the optional-batch policy's total-assignment checkpoint. All evidence capture is read outside a write lock where necessary and revalidated transactionally before saving.

Pin `instruction-beta-v1`: Beta(1,1) prior per arm, minimum worthwhile lift 0.05, reuse utility +1 if worthwhile and -9 otherwise, keep utility 0, batch cost 0.01. Initial optional-batch checkpoint is 40 assigned visits, one additional batch of 10, cap 50; unresolved outcomes and recorded checkpoint govern continuation. No allowance means no automatic batch recommendation. Model calculation limit remains 400 mature visits. Preserve source action/status vocabulary, including `wait_for_evidence, collect, continue_batch, wait_batch, keep, reuse, unavailable` and currentness state `refresh_snapshot`.

These are browser-protocol estimates of completion, not verified people, ad conversions, revenue or proof of commercial uplift. The destination's postal/email cohorts and their maturity/coverage rules remain unchanged. Do not pool their observations or sum their support counts with YouTube.

Finding reuse additionally preserves the source checks: eligible current snapshot, unchanged policy/context/media, matching tested content, current correction, active latest finding, and the source's distinct-brief requirement. Retiring or superseding a finding never revives it on replay. A human preference or rejected recommendation does not rewrite counts or approve future artifacts.

## Inference, funding and recovery

### One journal and one spending principal

Use public `reasoning.Inference/CallJournal` and the existing `model_calls` journal as the single logical call owner. Extend their contract for pinned serialized requests, money reservations/settlement and route evidence where needed. Do not embed the source foreground ledger or chain two journaled inference engines.

New workflow version: `youtube-preparation/v1`; offline mode is explicitly authored and cannot reserve provider calls. Register source verification/task composition through the existing admission machinery. Do not relabel it as `synthetic-channel-admission/v1`, bypass existing paused/verified-store fences or enable a paused historic format.

The registered runtime capability is `youtube.prepare.v1`. Its task inputs bind `workflow_version, operation_id, context_fingerprint` to the admitted operation, frozen context and permission/model selection. The adapter verifies those links against the admission, not caller-declared ownership. Local handlers may replay proven safe computation, but each inference uses the original durable logical call key and each publication uses the original native command. A runtime waiting reference or acknowledgement is continuation state, never artifact approval. Exact internal step decomposition is owned by the workflow implementation and cannot create extra spending authority.

The admitted context pins scope, source revisions, conversation/action revision, owner account, task plan, request permission, prompt/tool/contract versions, model limits and funding selection. Conversation descendants retain the original conversation account; revisions and new command keys do not manufacture allowances. Source legacy prompt IDs v7/v8/v9 retain their renderers/bytes if later supported. New destination requests use a distinct version, such as `youtube-planner/v1`; never label a changed request as source v8.

Existing postal planning limits and owned conversation-account caps are not silently reused as a new tool-loop shape. #131 must register the YouTube request/call allowance and expose its effective limits before live admission; changing the maximum is a versioned policy decision. The source eight-turn request loop and the destination's separate planning limits are an explicit parity question, not proof of an already compatible harness.

Funding selection has exactly one mode: `offline`, `demo_zero_price` or `user_byok`. Benchmarks use separately authorized operator sessions outside normal visitor allowance. There is no fallback between modes or to an operator environment key.

- `offline`: authored adapters, zero provider calls.
- `demo_zero_price`: explicit host allowance, provably zero-priced compatible route, call/time/session caps, no paid fallback.
- `user_byok`: current actor's explicitly connected credential session and approved limits. Server returns a non-secret binding handle; provider keys stay adapter-side. Persist only bound session identity/expiry/revocation and non-secret policy metadata.

The session contract binds actor, organization, profile, browser session, credential generation and funding principal. Disconnect/replacement/revocation blocks new dispatch; it does not erase accounting or repeat in-flight work. A function cold start without an available session can read authorized receipts and pauses new inference with `model_session_unavailable`. It must not switch keys or fall back to another account. #70/#130 choose the secure hosted session mechanism; current process-memory WorkspaceSessions is not proof of cross-function capability.

Model availability depends on actual text/tool/required-tool-choice support, a usable qualified provider route and all applicable known price dimensions. Reserve conservative cost across input, output, cache and other applicable charges within integer money/call limits; unknown pricing, route drift or missing budget enforcement blocks dispatch. List the specific reason, not a blanket two-model allowlist. Existing destination ModelConfig price/call/byte ceilings continue to apply until #131 deliberately extends them. Catalogue discovery alone proves no route or funding authority.

### Exact recovery and lifecycle

Freeze exact wire JSON body bytes/hash before dispatch, not just model name and rebuilt messages. Authorization headers/keys never enter that body or its saved preimage. Journal scope includes organization, original owner/run/task and logical call key; generation/credential binding corroborates the admitted funding principal. Prompt upgrade or model-settings change cannot mutate an unfinished request.

| Situation | Required behavior |
| --- | --- |
| Original call recorded, semantic publication missing | Read authorized original result, revalidate current command authority/evidence, publish once without provider call or fresh route metadata |
| Original call recorded but actor revoked or request superseded/stopped | Retain cost/receipt, deny new domain publication; inspection still requires current read access |
| Reserved/dispatched, no reliable result | Mark/fence unknown; do not automatically repeat even after reconnect/restart |
| Dispatch is proven not sent | Release only the unsent reservation under the same original operation; reconciling this does not grant a new allowance |
| New dispatch | Recheck current identity, lease/stop, funding session, remaining allowance and provider route before the effect |
| Received invalid/truncated output or provider rejection | Record known usage/cost, specific sanitized failure and terminal/blocked activity status; no automatic paid semantic retry |
| Write acknowledgement lost | Re-read original durable command/call receipt; changed input under original key conflicts |

Unresolved billing consumes/fences the original account allowance conservatively. Do not admit further calls against an unknown remaining balance. Unexpected execution errors stop a live batch even when that trial's billing is known; subsequent trials stay not-run until a new explicit reviewed start.

Allow one tool proposal/effect at a time; do not execute parallel provider-returned writes. The model may choose discovery/inspection order and prepare within permission. Application validation owns the result. Actual tool progress and safe failure summaries are visible inline; model-private reasoning and credentials are not persisted as activity.

## Outcomes and error projection

Commands return an immutable receipt and a separate current projection with `status, reason_code, safe_message, references`. Progress distinguishes `ready, running, waiting, blocked, failed, unknown, stopped, completed`; `completed` means the promised durable result exists, not that an ad was deployed.

Stable reason codes include `channel_ambiguous, capability_unavailable, unsupported_contract, scope_unavailable, permission_denied, draft_permission_required, request_conflict, revision_conflict, subject_changed, approval_required, approval_revoked, media_unavailable, delivery_unavailable, correction_required, correction_stale, evidence_stale, finding_ineligible, finding_retired, event_sequence_invalid, payload_too_large, model_session_unavailable, model_route_unavailable, pricing_unsupported, budget_exhausted, provider_rate_limited, provider_output_invalid, inference_unknown, storage_unavailable`. The HTTP adapter maps them to existing conventions; unknown foreign IDs use an indistinguishable unavailable response without leaking ownership.

Never turn storage/provider failure into an empty successful catalogue or zero observed outcomes. Logs carry redacted request/run/task/call references, stage and known/unknown accounting. Raw provider echoes, secrets and private prompts are not routine telemetry. Content retention/eval reuse requires the platform's separate data policy.

## Whole-system acceptance and implementation handoff

| Trace | Authority/effect boundary | Observable success or failure |
| --- | --- | --- |
| Product context → YouTube request → inspection → permitted draft → human review → export | Context grounding, draft permission, exact subject and current export authorization | Correct scoped manual artifact, linked media/delivery, source labels; no accidental postal job |
| Ambiguous channel or missing capability | Installed capability catalogue before dispatch | Clarification or specific blocker, no provider/draft side effect from a default |
| Shared prompt/model upgrade after paid response | Original request/journal receipt and current publication guards | Same result or explicit block; zero additional provider calls |
| First review → human correction → new review → instruction draft | Optional correction at review save; current exact correction binding at draft commit | No initial-review deadlock; old review remains historical, stale correction blocks preparation and a fresh matching review permits an unapproved draft |
| Repeated or concurrent save/apply/approve | Native semantic identity plus request receipt in one transaction | One revision/decision/effect; conflict or original result for the second caller |
| Viewer completion → current snapshot → finding → new brief | Content/assignment protocol, current correction and reuse permission | Eligible tested wording in one unapproved revision; no new commercial count or approval |
| Lost connection, storage failure or actor revocation | Fresh identity/storage checks, original durable operation | Truthful status and safe recovery; no cross-scope exposure or duplicate effect |

The JSON examples freeze positive and negative assertions, source evidence and typed outcomes. #132/#133 must implement them against public commands with real SQLite and applicable Turso/fresh-process tests. #134 adds actual hosted browser and separately authorized live evidence under #74. These examples do not claim the destination currently passes.

| Issue | Required changes or evidence |
| --- | --- |
| #132 | Public module/ports, channel routing, native transactions, authored profile/context, placement draft, exact review/manual JSON export, architecture classifications and command regressions |
| #133 | Functional media/viewer, protocol snapshots, versioned statistical oracle, current finding save/apply/retire and UI projections |
| #130 with #70 | Hosted actor/session resolution, bounded command/delivery composition and scoped participant ingress |
| #131 | Intake-to-reviewed task context, one extended inference journal, qualified model/funding admission and explicit supported limits |
| #134 under #74 | Source parity, tenant/revocation, concurrent rollback and cold-start recovery, prompt-version recovery, real usable export/viewer and live quality report |

The channel API, first export format and ownership decisions above are fixed for these implementation proposals, subject to review. Hosted session storage, detailed authority-provider API and numeric schema allocation remain platform implementation choices. Their absence blocks live activation, not the offline #132 slice. Platform owners must review the funding/session and journal changes in #130/#131 before those live paths merge; this document does not claim cross-chat agreement or deployed compatibility.

## Contract verification boundary

On 24 November 2026, both authored hash vectors and all three frozen Bayesian decision vectors were evaluated against the pinned source's pure functions. All five matched. The 27 scenario records have valid JSON, unique IDs and 26 distinct resolvable source/destination evidence references. Local document links and editorial/whitespace checks were checked separately. YT26 specifies the first-review/correction/re-review/draft sequence; YT27 specifies currentness when a correction changes during capture or after a review.

These checks establish fixture consistency and a source behavior oracle for the port. They do not establish destination command conformance, hosted authority/recovery, statistical validity for real people or live model quality. No live provider request was made. Runtime/schema/HTTP/frontend behavior is unchanged; their implementation gates remain in #132 to #134.
