# Execution authority and rebuildable workspace state

Decision for [issue 33](https://github.com/DG-creative-lab/direct-acquisition-agent/issues/33).
The design covers admission, inference, cancellation and recovery across the
workspace, CLI and direct workers. It preserves the modular monolith and the
existing campaign, review and learning boundaries.

**Implementation status:** the schema-13 entry-point cutover remains selected by
`verified-paused/v1`; new-format tasks cannot run or reserve inference. Schema 14
moves new preparation intent, sandbox environment, time, command identity and
scoped domain mappings into application storage. Unsealed compatibility stores
retain their existing operating paths. Legacy workspace records are not silently
certified. Phase 4b adds explicit offline projection inspection and rebuild for
registered new-format environments. Explicit legacy migration and
inspection-only restore are implemented. Execution activation remains planned.
Approval and acceptance retain their existing controls.

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

The current location column records the pre-consolidation checkpoint, still used by unsealed compatibility stores. For new selected work, the schema-14 storage ownership below supersedes the workspace locations in this inventory. The intended owner column remains normative for the full cutover.

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

`build_admissions(path, clock)` is the composition entry point for the storage
API. It has no provider client and is not registered as a model tool.
Application services now use it through the public admission port when the
store requires verified admission. It uses the existing planner's scoped asset validation,
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

## Sealed entry points and paused execution

`WorkflowAdmissions` owns original-command replay through the public port.
Planning, routing reconciliation, application campaign creation and native
revision reconciliation use it when the store is sealed. Original command
parameters and model permission are saved with the source references. Replay
loads those frozen references before any context-building callback, so a new
memory snapshot or unavailable current catalogue cannot replace admitted input.
Native revision continuation also checks the exact saved source receipt.

The CLI can seal an application database explicitly. The workspace server can
select verified admissions after acquiring its existing exclusive root lock.
Its selection persists in the root application database; future sandbox stores
inherit that selection before creating tasks. It is not stored in workspace
presentation state or accepted from a browser/model argument. Passing the
default option on restart never unseals a store. The singleton policy is
technical store-format metadata applying to every organization in that database;
business records and authority lookups remain organization-scoped.

Sealing and competing creation share the SQLite write lock. Sealing refuses a
running task, reserved inference, or a legacy planning admission without its
runtime row. This avoids trapping an immutable partial plan between formats.
Existing queued legacy work becomes inspectable paused history; it is not
silently certified as new-format work. A failed seal transaction leaves the
previous format intact. Update/delete triggers prevent policy downgrade.

Python claim and reservation independently validate the committed request,
consent fingerprint, task plan and owner binding before reporting a paused
admission. Generic runtime insertion and the old planning writer reject new
unverified work in sealed stores. New-format ancestry comes from the admission
and domain parent records; workspace descendant reconstruction and journal
witness binding are skipped for these stores.

Database guards also cover cached older writers that lack the Python checks.
In a sealed store a run needs its admission before insertion, task rows must
match the saved task plan, task execution status updates are refused and new
inference reservations are refused. Schema 13 makes the admission-to-run foreign
key deferred: the verified adapter writes admission first, then runtime rows,
ownership and audit in one transaction. Commit still requires the runtime row;
an interruption rolls back the whole admission. Schema-12 records and receipts
are copied unchanged. Guards are removed/recreated under the migration lock
when earlier table rebuilds must run, with rollback preserving the original set.

Stopping/cancelling remains available. Restored running leases cannot settle
results through the paused path. Existing provider observations keep their
original reservation/receipt rules; no observation authorizes new execution.
Progress exposes the saved admission as paused, and chat preparation displays
a bounded explanation instead of promising model generation. No provider key
or client is loaded for paused model admission; explicit frozen model settings
and generation permission remain required.

There is no activation command or executable verified mode in this slice.
Positive new-format model dispatch and the full verified campaign journey remain
acceptance work for activation. Existing compatibility journeys are tested
separately and do not prove new-format execution.

## Application-owned workspace state, phase 4a

Schema 14 adds immutable preparation intent in the root application store before
planning admission. Intent includes exact revision, model settings, frozen
planning context and copy permission. A separate bounded progress record may
reference only that intent's verified planner run. Restart resumes the saved
request; projection data cannot replace its consent or context.

`conversations.EnvironmentIntent` and `WorkspaceStateStore` own the environment
contract. `workflows.workspace_state` checks root, conversation and finalized
parent sources through public contracts. SQLite loads actual scoped source facts
under the write lock. `bootstrap.build_workspace_state` wires this policy and
storage. The workspace facade submits commands and renders their results.

Each campaign application database stores its environment's immutable mode,
storage scope, initial server time and original command, followed by monotonic
clock state and verified run/case/cohort links. Children inherit the parent's
actual application store. The root application database holds a technical
location catalogue bound to immutable per-store identities. A location is not
an execution grant; an interrupted location-only creation authorizes no work.
Missing or replaced stores block access. Known-store reads do not migrate or
acquire a nested write lock inside another effect transaction.

Simulation clock advance and exact command admission share one transaction.
Clock targets come from the environment's accepted cohort and require an active
operator. A changed request is rejected before advancing time. Domain effects
still use their existing exact approval, acceptance and learning transactions.
A later domain failure does not undo the earlier admitted clock decision; retry
reuses the original identity and domain receipt. No distributed transaction is
claimed between navigation projection and application storage.

Owned intent, mappings and clocks remain readable with `workspace.sqlite`
missing or altered. This slice does not reconstruct old workspace-only authority.
Selected legacy sessions are inspectable, but new workspace continuation or
decisions require explicit migration; their former projected clock is not a new
time grant. Unsealed compatibility operation remains unchanged. Preserve the
root application store and referenced campaign stores together. A location/store
identity detects replacement, not arbitrary stale backups. The phase 4b command
below reconstructs registered new-format projections only. Legacy migration and
checkpoint restore have separate commands and preserve the execution pause.

## Offline projection rebuild, phase 4b

`conversations.WorkspaceProjectionRebuild` owns the inspection/rebuild use case
through narrow source and projection ports. Bootstrap supplies the existing
environment validation policy, a read-only application-store reader and the
SQLite projection adapter. Runtime, inference, review and learning policies do
not move into the projection layer. No source schema migration is needed.

The command acquires the same per-root `server.lock` as the local server. It
requires an existing schema-14 root already selected as `verified-paused/v1`.
It reads only registered stores, checks their immutable identities and selected
policy, and validates owned environment/run/case/cohort links and preparation
intent. Location-only admissions are reported without inventing environments.
It does not discover arbitrary files, initialize source stores, regenerate
guidance, load a model key, run a coordinator or activate a scheduler.

Rebuild reconstructs owned session rows, exact original conversation/experiment
request indexes and command completion projections in one control-store
transaction. Progress continues to be read from application journals; copying
frozen preparation consent back into a legacy authority table is unnecessary.
Cached diagnostic keys tied to positively owned runs/revisions are discarded;
legacy diagnostic keys remain protected even in the same organization.
Optional `expected_plan` binds the inspected source and projection fingerprints.
The projection is checked again after the write lock, protected records are
compared after reconstruction, and source projection facts are rechecked before
commit. A concurrent change rolls back the projection update. The source
connections use SQLite read-only mode and query-only enforcement.

Rows not referring to positively owned environments, opaque legacy preparation
records, existing journal identity and unrelated tables are preserved. A native
request key belonging to a protected legacy row blocks reconstruction rather
than being rebound. Unsupported layouts/triggers, unreadable projection files,
file aliases and missing/replaced source stores are refused. There is no force,
drop-history, implicit legacy enrollment or independence attestation option.

A crash before projection commit leaves the prior rows, or an empty newly
created projection file, for the same command to rebuild. Lost acknowledgement
after commit can be retried without domain effects. The new index does not
certify a missing legacy journal or prove that an authoritative backup contains
all later effects. Inspection fingerprints are not backup manifests or approval
receipts. Preserve the original legacy journal and authoritative stores.

An interrupted projection transaction can leave a hot SQLite rollback journal.
Under the root lock, query-only inspection opens the existing projection with
recovery permission so SQLite can restore its prior committed rows. This never
creates a missing projection during inspection or grants write access to an
application source store. The forced-cache-spill crash test exercises this path.

Acceptance covers real SQLite, fresh CLI processes, hard process exit before
commit, lost acknowledgement, protected mixed history, concurrent source/control
writes, clock and command preservation, uncertain provider observations, source
integrity and lock release. Verified work remains paused. The full activated
campaign journey and deliberate migration/restore procedure belong to phase 5.

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
| New-format workspace projection is missing while registered application stores remain intact | Offline rebuild restores owned indexes from intent, mappings, time and receipts without provider calls, new consent, new approval or changed accounting; legacy-only authority is not recovered |
| Existing run has positive authoritative parent evidence | Recover that relationship without rewriting historical tasks, artifacts or provider receipts |
| Existing run has missing or conflicting ancestry | Pause effectful work and expose the reason. Absence of a parent is not proof of standalone ownership |
| Workspace backup is stale, partial, recreated or unrelated | It cannot prove complete ancestry or authorize independence |
| Authoritative database is rolled back to an old backup | Historical inspection only until deliberate reconciliation. Calls/effects after that checkpoint may be unknown; never reset allowance and automatically resume |

Explicit projection rebuild is implemented for registered new-format state;
it is not a migration or backup-restore activation procedure.
Legacy migration keeps the conservative recovery and journal checks. A database
or journal ID proves identity only. The explicit ownership migration is
restartable and auditable, with an inventory of unresolved records. It
preserves historical receipts, v1/v2 artifact readers, the schema-v3 legacy
cutoff and approval invalidation rules.

The [local workspace checkpoint](workspace-checkpoints.md) captures a stopped
root and publishes a validated inspection-only restore. A read-only comparison
with a later checkpoint can corroborate selected local observations for the
same organization and store. External effects and completeness remain unknown.

## Implementation sequence and acceptance gates

1. **Ownership contract and baseline, implemented.** Freeze the inventory above,
   expose versioned immutable values and an inactive port, and compare the
   current reservation boundary with an independent transition oracle.
2. **Atomic admission adapter, workflow coverage implemented.** Add module-owned authoritative intent, consent,
   parentage and scoped mappings alongside tasks/calls. Verify source facts and
   capability requirements in one transaction. Keep production callers on the
   old path until complete cutover is possible. Tests must inject failure after
   each insert and before commit, and prove exact replay and competing-key
   uniqueness across real SQLite connections and process restart. Other
   workflow source policies must be installed before those writers can switch.
3. **Entry points and paused effect fences, implemented behind store selection.** Connect chat preparation, planning,
   routing, native revisions, CLI creation, manual children and direct workers.
   An explicit schema/capability gate must prevent old writers creating new work
   without ownership. Test one shared allowance, stop-through revision, foreign
   scope rejection and zero dispatch from bypass paths. Store sealing and SQL
   guards close mixed-writer gaps. Verified execution activation remains deferred.
4. **Rebuildable workspace, phases 4a and 4b implemented.** Schema 14 moves new selected coordinator intent, campaign
   mappings, request fingerprints, storage scope, fixture/model mode and sandbox
   time out of workspace authority. Explicit offline rebuild now restores owned
   indexes. Tests delete the projection, rebuild in a fresh process and compare
   exact domain records, original request lookup and paused progress. Process
   interruption and lost acknowledgement cannot repeat a domain effect. The
   original activated chat journey remains a phase-5 acceptance gate.
5. **Migration and inspection-only restore implemented.** The
   [read-only inventory and versioned plan](legacy-migration.md) report scoped
   evidence, parent dependencies and supported/conflicting/incomplete/uncertain
   classifications. Unknown ownership never becomes standalone by absence.
   Inspection remains read-only. Explicit apply records supported existing
   ownership and a receipt in the same transaction in the sealed conversation
   store. Apply rechecks the plan under source locks and preserves unresolved
   origins. Tests cover mixed history, ambiguous CLI runs, recreated and
   stale journals, conflicting parents, rollback and fresh-process receipt
   recovery with the workspace journal missing.
   Cold capture and read-only validation cover the application stores and original
   workspace journal. Restore publishes the complete checkpoint with workers and
   mutations disabled.

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
Activation, reconciliation with external evidence and the full executable
new-format journey remain later gates.

No generic repository, service locator, event bus, new orchestration framework or
microservice split is introduced. Inventory, migration, projection recovery and checkpoint restore keep verified
execution paused.

### Environment link integrity

An environment's runtime key is necessary but insufficient proof of identity.
Linking and reading its run verify the admission against its immutable original
creation command and environment: mode, generation permission/settings, source,
parent, brief, source references and supported workspace command parameters.
These checks use frozen admission facts, not current guidance or regenerated
model context. Source policy remains in workflows and is wired by bootstrap;
the adapter loads scoped facts and enforces the check within the transaction.

In selected mode, owned environments are loaded independently before projection
rows are considered. A projection for an owned ID is not decoded. Other rows
must have a matching storage identity and a valid session shape; malformed rows
are ignored without updating application state. Valid legacy rows remain
inspectable under the existing migration restrictions.

For generated workspace audiences, link policy obtains the expected full
snapshot identity from the v1 deterministic generator using the environment's
original organization/date and the supported workspace size and seed. It does
not accept the admission's snapshot ID or claimed metadata as proof of those
parameters. Bootstrap injects this adapter capability; the comparison occurs
inside the existing application transaction. Selected datasets and learning
follow-ups continue to use their frozen source provenance. No model work or
historical input refresh is performed by this identity check.
