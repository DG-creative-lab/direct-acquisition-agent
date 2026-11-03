# Execution authority and rebuildable workspace state

Decision for [issue 33](https://github.com/DG-creative-lab/direct-acquisition-agent/issues/33).
The design covers admission, inference, cancellation and recovery across the
workspace, CLI and direct workers. It preserves the modular monolith and the
existing campaign, review and learning boundaries.

**Implementation status:** versioned values and paused SQLite admissions
are implemented. Schema 12 extends model and fixture planning with verified
routing, campaign preparation, manual descendants, learning follow-ups and copy revisions. No
workspace, HTTP or CLI caller uses this adapter, and new-format tasks cannot be
claimed or reserve inference. Atomic admission is separate from activation.
The entry-point cutover and projection rebuild remain planned work. Approval and
campaign acceptance still use the existing controls.

## Evidence and decision

Current import isolation is intact. The structural problem is that an execution
decision can need facts from both the application database and
`workspace.sqlite`. In particular, manual parentage, continuation consent and
sandbox time can survive only in workspace records. Inference accounting and
stop fences live in the application database. A workspace restart can reconcile
many interrupted writes, but a missing relationship cannot safely be inferred
from an empty or restored journal.

These are confirmed properties of `workspace.py`, the SQLite preparation adapter,
the execution adapter and the reservation transaction. The inference that this
split contributes to repeated recovery findings motivates consolidation; it does
not establish that every workflow needs rewriting.

Record each new operation's explicit ownership, verified source, frozen context,
generation consent and task admission in one authoritative application database.
The same database already holds the tasks, leases and inference journal used at
the effect boundary. A workspace record may locate or display that operation;
its absence must not change permission to run it.

This is one transaction boundary across module-owned records, not one shared
business model. Runtime remains unaware of conversations, campaigns and approval.
SQLite adapters implement the atomic mechanism; application services use narrow
ports and public module contracts. Network calls remain outside transactions.

## Ownership inventory

The current location column describes the implementation at the checkpoint.
The intended owner column is normative for the cutover.

| Fact | Current durable location | Intended owner and responsibility |
| --- | --- | --- |
| Messages, brief revision, planning results and clarification exchanges | Application conversation/action records | `conversations`: immutable intent and exact revision |
| Parent campaign and inherited execution account | Application provenance plus workspace session `parent_id`, `conversation_plan` and recovery links | `conversations`: verified original parent and account, committed before child tasks |
| Preparation mode, frozen planning inputs and copy consent | Workspace `preparations` and admitted domain inputs | `conversations`: durable continuation intent, explicit consent and original request mapping |
| Copy-revision request, target and consent | Application review commands and revision records | `reviews`: exact target and revision admission; execution ownership is linked in the same transaction |
| Selected audience version, bytes and provenance | Application snapshots and audience-selection records | `audiences` owns source validity; `conversations` owns the revision-bound choice |
| Run/task inputs, lifecycle, attempts and leases | Application runtime tables | `runtime`: business-agnostic lifecycle; no consent or allowance policy |
| Allowance, origin, stop fence and their receipts | Application execution tables and execution commands | `conversations`: shared account and stop policy; all writers must supply verified ownership |
| Reservations, observations and provider-reported cost | Application `model_calls` | `reasoning`: per-run bounds and observation semantics; adapter checks shared policy before reservation |
| Frozen creative guidance and outcome memory | Application creative contexts | `creative`: exact scoped inputs, refreshed only through explicit new operations |
| Approval and simulator acceptance | Application review decisions, subjects and accepted jobs | `reviews`: exact-subject authorization and acceptance transaction |
| Cohorts, immutable outcomes and posterior support | Application learning records | `learning`: population, maturity and counted observations |
| Sandbox `clock`, `clock_mode` and execution mode | Workspace session payload | `conversations` owns durable sandbox intent/environment; `learning` still decides maturity. Rebuild cannot advance time or change fixture/model mode |
| Organization, database scope and campaign-to-run/case mapping | Workspace session payload and some domain references | Authoritative scoped operation metadata in the application store; the workspace index is derived |
| Idempotency fingerprints and command-to-session mappings | Workspace `commands`, `conversation_draft_requests`, `followup_prepare_requests`, plus domain receipts | Provider module owns the exact command and effect receipt; workspace completion markers are projections |
| Titles, navigation, progress and blocker text | Workspace sessions, preparation status and blocker tables | Workspace projections, regenerated from authoritative facts; never authorization |

`workflows` composes module APIs. `bootstrap.py` selects adapters and resolves
server-owned storage. The HTTP server and React client submit scoped commands
and render observations. None may manufacture ownership, consent, evidence or a
reviewer's identity from model output or missing metadata.

One conversation and its descendant runs must remain in the same application
database. This decision does not merge every standalone sandbox into one global
database. The future rebuild must discover known server-owned stores and verify
their scope; it cannot accept a browser-supplied path or silently route a child
to a different store.

## First contract

The public `conversations` API now exports `ExecutionOwnership`, `AdmissionIntent`,
`AdmissionReceipt`, `ADMISSION_SCHEMA` and the `AdmissionStore` port.

`ExecutionOwnership` explicitly declares either a conversation account and its
original revision, or a standalone root lineage. Missing ownership is invalid.
The account key excludes the revision: editing a brief cannot reset its shared
allowance. A child preserves the parent's full ownership, including the source
revision, and stays in the parent's run organization. Owner organization and
run organization are separate scopes and must be verified, not assumed equal.
Standalone ownership does not introduce a new conversation quota; existing
per-run limits and explicit generation permission still apply.

`execution-admission/v1` binds the scoped request identity to a workflow version,
source identity and fingerprint, frozen context fingerprint, canonical task plan,
declared ownership and optional parent run. Model settings and a consent reference
must be supplied together. The request's admission ID is stable; changing any
bound input changes its fingerprint and must conflict on replay. Task inputs are
serialized at construction and decoded into fresh copies so later mutation cannot
change the admitted proposal. The envelope allows 1 to 20 tasks and at most 1 MiB
of canonical task JSON; each model request retains its smaller existing budget.

These values validate shape and binding, not truth. A supplied hash does not
prove that its source exists, is current or authorizes an effect. A supplied
consent ID does not prove user consent. The adapter must load and verify the
scoped authoritative source, installed workflow/effect requirements, parent,
context and exact consent inside the admission transaction. Omitting model
settings from a proposal must never downgrade a registered paid capability to a
deterministic one. The contract tests explicitly demonstrate this evidence limit.

`AdmissionStore.admit` is responsible for operation uniqueness as well as request
replay: a new request key cannot repeat planning for one revision or duplicate an
already admitted generation. It must commit verified intent, owner, runtime tasks
and receipt together. `find_request` observes the original scoped request;
`get` returns its immutable intent. A receipt observes admission, not current
execution permission. Workers still recheck current conditions at each effect.

## Paused SQLite adapter

`build_admissions(path, clock)` is the explicit composition entry point for the
new storage API. It has no provider client and is not registered as a model tool
or exposed by a transport. It uses the existing planner's scoped asset validation,
fixture checks and complete request-envelope preflight.
The conversation module owns the pure permission, capacity, intent-construction
and binding rules. SQLite loads their facts and persists their result under its
transaction; neither the runtime core nor the transport owns those policies.

`request_planning` records an explicit server-resolved user command. It requires
a real current conversation/revision, its stored messages and clarification
exchanges, the actual previous planning results, frozen versioned guidance and
an explicit fixture/model choice. Model planning requires consent and matching
bounded settings; declaring a model mode without consent is invalid. The saved
request binds the original command inputs, source bytes, canonical task plan and
generation decision. It is non-executable and contains no runtime task. Saving
the same exact request observes its original frozen intent; changed inputs
conflict. A new request key cannot repeat the same revision.
Scoped `get_request` and `pending_requests` reads recover these frozen inputs
without the original browser, current catalogue or caller-held context. They
observe saved intent and never admit or activate work on their own.

The immutable request also reserves its explicit runtime request key in that
same transaction. Shared SQLite run insertion looks up this reservation and
requires the exact saved owner binding and task plan from the admission path.
Campaign, model-campaign and generic task creation cannot occupy that key while
the request is staged. A failed staging transaction leaves no reservation.
Admission retains the reservation as immutable history; matching receipt replay
observes the original run. All workflow families use the same request journal.

`admit` loads that saved request and its consent under the write lock. Supplied
fingerprints or consent IDs cannot replace it. It rechecks current revision,
the stop fence, exact source bytes, registered planning capability/mode and
frozen scoped assets before writing. One transaction creates the run, task,
explicit execution-account link, planning record, immutable admission receipt
and audit. Both admission journals reject updates and deletion. A failure before
commit leaves only the earlier non-executable request, which is discoverable by
its original identity and can be admitted again safely. After commit, request
lookup observes the original receipt even after stopping, without new work.

The planning workflows are `conversation-planning/v1` and
`conversation-fixture-planning/v1`. They have one registered planning task and
an explicit conversation owner. `request_workflow` extends the same store with
the following server-only commands. Callers supply fixed source references,
never task lists or ownership claims.

| Kind | Verified source | Task and ownership rules |
| --- | --- | --- |
| `routing` | Native saved action, original question/dialogue, scoped assets and model settings | One original v1/v2 routing capability; aliases have no task. Routing permission does not grant downstream copy consent |
| `conversation-campaign` | Successful saved plan and its admitted task, current conversation revision, complete scoped snapshot and any confirmed dataset selection | Derive the exact brief and campaign scope from the saved proposal; fixture or grounded v3 copy must match its mode. Bind model contexts to the objective, segment and dataset |
| `standalone-campaign` | Explicit new root command, complete scoped snapshot and optional frozen model contexts | Explicit standalone lineage with existing per-run limits. Known campaign identities cannot erase their ancestry by declaring a new root |
| `manual-descendant` | Positive parent campaign/run in the same application database and new campaign inputs | Inherit the full verified parent owner and original revision. Missing legacy ownership blocks admission. A positively admitted standalone root may have standalone descendants |
| `learning-followup` | Saved eligible proposal, exact cohort finalization, accepted parent job/case and current independent population/epochs | Derive the brief, snapshot and contexts from that proposal. Model copy requires its exact frozen model settings at staging and admission. Inherit the actual parent account, without inheriting approval or outcomes |
| `copy-revision` | Existing native exact-subject revision receipt, current operator/reviewer authority, evidence/suppression epochs and unaccepted case | Preserve its exact target, feedback, five-call permission and frozen context. Inherit the original campaign owner; do not repeat the native rejection effect |

The native routing and copy-revision services still own their source admission
rules. Their paused wrappers consume an already saved source before its runtime
run exists. They do not retroactively adopt a live or completed legacy run.
An existing runtime key blocks staging; a staged key blocks ordinary runtime
writers, including their original native reconciliation path. Exact request
replay observes its frozen intent; a second key cannot repeat the source
operation. Admission rechecks the source under the write lock, then commits the
run, ownership where applicable, immutable receipt and audit together. Only
planning also writes a planning projection.

Conversation permission and ownership values remain in `conversations`.
`workflows/admission_coverage.py` composes public domain contracts and the
existing task-plan factories. The SQLite source loader supplies scoped facts,
checks current authority in the transaction and has no workspace dependency.
`bootstrap.py` wires these components; no application service imports an adapter.
Model preflight has no gateway or inference journal. New copy admissions require
the stable versioned context projection and fresh evidence. A final clock check
after validation prevents a source expiring during preflight from committing.

Schema 12 rebuilds the two admission tables under the existing migration write
lock. Non-planning sources may omit the planning-only conversation/revision
columns; their explicit owner stays bound in the immutable intent. Unique
operation and runtime-key indexes prevent competing staged admissions. Existing
schema-11 JSON, receipts, task bytes and the schema-3 legacy cutoff are copied
unchanged. Transaction failure restores the prior tables and version. This
migration does not activate tasks, infer unknown legacy parentage or make a
workspace projection authoritative.

Both staged and existing planning records count toward the conversation's six
planning requests. The legacy planning service refuses a revision already saved
through the new API and includes staged revisions in its limit. These guards
avoid duplicating an operation through the two service paths. They do not claim
that every old raw-task writer has been converted; that is the next slice.

Every new task carries an explicit admission-format marker. Claim and reservation
both reject these paused tasks, including after process restart or if the
admission row is missing. There is no activation toggle in this implementation.
Admission receipt reads verify the stored request, task plan, run and ownership
from one read snapshot; they never perform current approval or dispatch decisions.

## Transitions and commit boundaries

| Transition | Authoritative decision | Required atomic result |
| --- | --- | --- |
| Proposal to admission | Exact source/revision, workflow, consent, parent, account and operation uniqueness | Intent, ownership, task plan and receipt, or none |
| Admission to running task | Eligible capability, original scope, stop fence and generic lease policy | Current task claim/token and lifecycle event |
| Task to model dispatch | Active lease, source freshness/revision, consent scope, per-run limit and shared allowance | One reserved call before network dispatch |
| Provider result to observation | Original reservation identity | Exact response or uncertain outcome; late observation after stop grants no publication authority |
| Running task to artifact/checkpoint | Current source, lease and deterministic validators | Original artifact identity and runtime lifecycle/event commits under their existing idempotent contracts |
| Active revision to stopped | Exact revision and command identity | Monotonic stop fence, task cancellation and receipt; preserve a reached review checkpoint |
| Draft to acceptance | Exact subject, current evidence/suppression, reviewer generation and expiry | Existing review acceptance/audit/receipt transaction |
| Observation to learning | Accepted cohort, maturity and explicit complete results | Existing immutable outcome and posterior-finalization transaction |
| Domain commit to workspace projection | Read authoritative records by stable identity | Rebuildable presentation update; interruption cannot repeat an effect |

The model may propose plans, targets and wording. Deterministic validation checks
the proposal and current authoritative facts. The user grants bounded generation
consent and exact approval separately. No plan, skill, progress state, account
balance or cached receipt grants campaign release authority.

The new admission transaction does not combine every later artifact and task
acknowledgement into one transaction. Existing idempotent artifact operations
retain their recovery contract. There is no claim of exactly-once remote delivery
or automatic retry of uncertain provider requests.

## Recovery contract

| Condition | Supported behavior |
| --- | --- |
| Process dies before the new admission commits | No runnable partial admission; retry original identity |
| Process dies after admission but before acknowledgement | Read the original receipt and resume its tasks without recreating consent |
| Process dies after call reservation | Keep outcome uncertain until a recorded observation resolves it; do not dispatch again automatically |
| Workspace projection is deleted after the complete cutover | Rebuild from domain intent, mappings, time and receipts without provider calls, new consent, new approval or changed accounting |
| Existing run has positive authoritative parent evidence | Recover that relationship without rewriting historical tasks, artifacts or provider receipts |
| Existing run has missing or conflicting ancestry | Pause effectful work and expose the reason. Absence of a parent is not proof of standalone ownership |
| Workspace backup is stale, partial, recreated or unrelated | It cannot prove complete ancestry or authorize independence |
| Authoritative database is rolled back to an old backup | Historical inspection only until deliberate reconciliation. Calls/effects after that checkpoint may be unknown; never reset allowance and automatically resume |

Projection rebuild is a target acceptance gate and is not implemented yet.
Until the migration is implemented, keep the current conservative recovery and
journal checks. A database or journal ID proves identity, not completeness.
Migration must be explicit, restartable and auditable, with an inventory of
unresolved records. It must preserve historical receipts, v1/v2 artifact readers,
the schema-v3 legacy cutoff, and approval invalidation rules.

Backup work must distinguish inspection from execution activation. A restore
does not itself activate schedulers or paid work. A consistent local snapshot
still cannot attest provider effects that happened after its checkpoint. No
transparent recovery from arbitrary partial backups is promised.

## Implementation sequence and acceptance gates

1. **Ownership contract and baseline, implemented.** Freeze the inventory above,
   expose versioned immutable values and an inactive port, and compare the
   current reservation boundary with an independent transition oracle.
2. **Atomic admission adapter, paused planning implemented.** Add module-owned authoritative intent, consent,
   parentage and scoped mappings alongside tasks/calls. Verify source facts and
   capability requirements in one transaction. Keep production callers on the
   old path until complete cutover is possible. Tests must inject failure after
   each insert and before commit, and prove exact replay and competing-key
   uniqueness across real SQLite connections and process restart. Other
   workflow source policies must be installed before those writers can switch.
3. **All entry points and effect fences.** Switch chat preparation, planning,
   routing, native revisions, CLI creation, manual children and direct workers.
   An explicit schema/capability gate must prevent old writers creating new work
   without ownership. Test one shared allowance, stop-through revision, foreign
   scope rejection and zero dispatch from every bypass path. No permissive
   interval with mixed writer assumptions is acceptable.
4. **Rebuildable workspace.** Move authoritative coordinator intent, campaign
   mappings, request fingerprints, storage scope, fixture/model mode and sandbox
   time before removing their workspace authority. Delete only the projection
   database in tests, restart, compare exact domain records, and complete the
   original chat journey with zero reconstruction inference. Kill the process
   after domain commit and before projection update. Review/learning history,
   stopped revisions and uncertain calls must retain their meaning.
5. **Migration and restore activation.** Test mixed legacy/new histories,
   ambiguous CLI runs, missing or stale journals, conflicting parents, atomic
   migration rollback and interrupted migration resume. Positive evidence can
   recover known ownership; unknown records remain inspectable and paused.
   Exercise the full offline journey and document the supported backup procedure
   before enabling execution for migrated stores.

Each slice keeps `make test` and `make arch-check` green. UI changes additionally
require `make interface-check`. Mutation probes must show that tests detect
removed ownership, changed-input replay, lost consent, skipped stop/allowance
fences and accidental projection authority. No paid model behavior is claimed
without a separate explicitly bounded live run.

The first slice's reference oracle fixes two accounts, three active runs and two
slots per account independently of production origin resolution. It explores all
49 pairs of a seven-action alphabet, longer traces for last-slot exhaustion,
recorded replay and late/unknown observations, and a fresh Python process. This
is a bounded reservation baseline. Separate admission tests now cover paused
planning's atomic writes, scoped consent, concurrent admission and real crashes.
Full workspace rebuild, legacy activation and alternate-writer cutover remain
unproven until their later slices.

No generic repository, service locator, event bus, new orchestration framework or
microservice split is introduced. The next reviewable change is the entry-point
cutover with its remaining workflow source policies, not new marketing features.
