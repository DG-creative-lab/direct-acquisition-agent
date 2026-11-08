# Validation and limits

The product is tested at pure-rule, persistence, process, HTTP and browser boundaries. This guide describes the current portfolio rather than the chronology of its construction. The portfolio includes frontend regressions, selected mutation probes and backend tests covering the campaign lifecycle, conversational planning and synthetic preparation. Test counts do not measure overall completeness or production readiness.

## Reproduce the checks

```sh
make test
make arch-check
make mutation-check
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend exec playwright install chromium
make interface-check
```

Python checks require Python 3.11 or later; the interface requires Node 22.12+ and pnpm 10.33+. CI uses Python 3.11 through 3.14 and a Node interface job. Browser and HTTP tests need permission to bind loopback ports. Offline tests do not use provider credit. Live inference evaluations are separate and opt-in.

## Invariant ledger

| Protected outcome | Executable evidence | Boundary of the evidence |
| --- | --- | --- |
| Requested product, channel, country and objective stay attached to the campaign | Versioned literal requirements freeze native messages at admission. Real SQLite rejects a supported replacement, removed scope, foreign rehashed source and mismatched delivery headers. Source changes during publication, approval and acceptance roll back every write; stale requests cannot authorize follow-ups. Browser checks cover visible defaults, mobile reload and four zero-call unsupported outcomes | Finite literal vocabulary and explicit labels, not general semantic understanding. Historical formats and receipts remain immutable. See [scope contract](requested-campaign-scope.md) and the [unchanged issue-25 corpus](evaluations/issue-25-requested-scope.md). The unchanged corpus improves from 6/12 to 10/12, with zero false readiness acceptances; two budget planner failures and typed routing keep issue 25 open |
| Unscoped historical requests cannot authorize fresh follow-ups | Real legacy-format fixtures with no scope fields exercise unsupported frozen/current source text, missing native plans, restart, saved-receipt replay and unchanged artifact bytes. Read-time validation prevents new contexts, snapshots or tasks; source changes during proposal receipt, child publication, approval and acceptance writes roll back. A supported legacy child can learn and propose again, but an amended original conversation blocks the next generation and saved-proposal admission | The native accepted experiment and scoped ancestry, not the presence of a new JSON field, decide which request to validate. Historical learning views and exact receipt replay remain observations. Paid inference stays paused and restores remain inspection-only |
| Ambiguous and relative budgets require a confirmed absolute user total | Real SQLite checks a completed zero-call clarification, exact question/revision bindings, concurrent and conflicting replies, post-write message/question rollback, old-policy replay and fresh-process continuation. Mobile browser tests drop committed reply and preparation responses and retain one revision, one campaign, exact budget evidence and shared usage | Literal GBP evidence remains authoritative. A failed planner does not count as clarification. Missing-budget model questions retain their existing inference path; no live semantic-quality claim. See [budget clarification](budget-clarification.md) |
| Evaluation evidence needs meaningful outcomes and identifiable executed inputs | Real SQLite rejects an unrelated zero-call failure as a passing negative and distinguishes clarification from exhausted validation. Temporary Git repositories change source, fixtures and configuration without moving HEAD, including hidden edits; file hashes record those inputs, and an observed change during execution invalidates an otherwise passing report. Six regressions and two focused harmful variants cover these boundaries | A generic failure never establishes successful scope enforcement or clarification. The v2 report identifies actual input contents and Git differences; before/after checks do not claim immunity to deliberate transient tampering by a local administrator |
| Local checkpoints preserve scoped history and remain inspection-only | SQLite row comparisons across application stores and the legacy journal, committed WAL data, fresh-process status, worker/reservation, approval and learning fences | Trusted local operator and current checkout. Post-checkpoint spend, revocation and simulator effects remain unknown |
| A partial, mixed, corrupt or active checkpoint cannot publish | Recomputed manifests with an unrelated registered store or an inconsistent SQLite index, corrupt source and staged indexes, missing files, digest changes, aliases, sidecars, active root/SQLite locks, running and reserved work, staged-copy damage and killed copy processes | Local POSIX publication and selected failure schedules. No power-loss test or live provider claim |
| Later checkpoint evidence stays scoped and grants no execution authority | Compare real snapshots with later call receipts, a stop, a revocation and simulated acceptance. Reject substituted planner ownership, unavailable, replaced, older or conflicting history, and missing audit or command receipts for retained acceptance. Fresh processes leave both snapshots unchanged and a restored worker remains blocked | Trusted checkpoint IDs and local recorded history. External billing, delivery and completeness remain unknown |
| Fresh verified fixtures execute within their original admission and lease | Complete conversation preparation, exact-subject approval, simulated acceptance and synthetic learning. Kill a process after draft publication, reclaim the same task and verify one draft operation. Exercise grant rollback, stale publication, stop and replay, SQL inference fences and restored-root inspection | Two allowlisted fixture workflows in a fresh local root. Paid inference and restored execution stay paused |
| Fixture publication and settlement retain their authority through commit | SQLite triggers advance the clock during draft, settlement and failure writes and verify rollback. An alternate operation ID and substituted creative catalogue are rejected before publication. An exact-subject operator refresh preserves the copy and rolls back its draft if the review event fails | Local execution clock and scoped SQLite transactions |
| Ineligible records never enter mailing | Literal 18-record fixture, ordered exclusions, duplicate/suppressed businesses and disjoint counts | Synthetic source completeness and supplied metadata only |
| Population and integer budget reconcile | Hand-written population plus 3 seeds × 3 sizes × 4 budgets = 36 cases | Bounded examples, not general load/marketing effectiveness |
| Controls share selected enrollment | Scores require assignments from the same top-score cohort; controls absent from mailing | Small groups may lack controls; selected cohort is not the whole market |
| Organization scope persists | Wrong-scope reads/writes, acknowledgement, cancellation, exports, review and learning rejected | Trusted local identity, not hosted authentication |
| Artifact comments retain their exact copy target | Real SQLite rejects another conversation, creative or superseded subject. Receipt replay and audit rollback preserve one comment. Browser tests retain copy/audience selection and variant through reload, replay a dropped comment response, reopen the same comment after button or Escape dismissal with fresh consent, and separately confirm the exact native revision | Comments record feedback without inference, approval or a brief edit. The mobile toggle changes presentation |
| Writing preferences need separate confirmation and retain their lifecycle | Real SQLite checks scoped comment provenance and audit, explicit consent, exact-input replay, stale/concurrent correction, immutable versions, retirement, frozen context snapshots and future audience scope. Fresh-process, schema-15 migration/rollback and schema-14/15 checkpoint inspection tests retain history. Browser tests confirm dismissal has no effect and replay a dropped save after reload before correction/retirement | Preferences guide writing only. New contexts use up to three recent active preferences per audience; saved contexts and historical copy stay unchanged. Paid inference stays paused and restores remain inspection-only |
| Preference model projection and snapshot selection preserve confirmed intent | A real copy worker with a fake provider receives confirmed wording without original source feedback; full provenance remains frozen. Real SQLite rejects replacement through either version or request keys with recursive triggers disabled, including upgraded schema-15 stores. Retirement interleavings in campaign and follow-up context assembly select usable authored fallback guidance | No live model-quality claim. Authored fallback is guidance, never outcome evidence; historical audit bytes remain immutable |
| Follow-up hypotheses bind source evidence without inheriting authority | Held-out strong, weak and absent comparisons for both audiences include a B-leading case, small extreme samples, large negative lift, zero trials and missing controls. Real SQLite rejects substituted hypotheses/evidence/contexts and preserves zero-response uncertainty. Frozen model inputs, restart replay, desktop/mobile inspection and a fresh verified fixture checkpoint/restore retain the original proposal | Synthetic, within-cohort evidence only. Pooled rates remain descriptive; prior parameters, preferences and model scores add no observations. Paid inference stays paused, restored roots stay inspection-only and new copy still needs review |
| Follow-up framing and outcomes stay tied to original evidence and the proposed audience | Grounded and fixture source hooks reach frozen model inputs; the historical product block is excluded after active facts change. SQLite response, timestamp, assignment, membership, missing-row and same-count replacement corruptions block source reads and commit without creating contexts or receipts. Validly hashed contexts for another snapshot, wrong model version or input population count are rejected | Historical receipts remain immutable observations. Source hooks grant no product-fact authority. Reconciliation is repeated inside the save transaction; new inference stays behind existing consent and pause controls |
| Follow-up cohorts retain their accepted experiment provenance | Real SQLite checks 17 missing, foreign-scope, altered receipt/index and draft cases at source read and save. Deleting the accepted job leaves no foreign-key violations but blocks a new proposal, including in a fresh process. Failed checks create no contexts, commands or model calls; historical proposal replay and a repaired source fixture still work | Rebuilds the cohort from the scoped accepted job and verified draft inside each transaction. Historical acceptance is evidence of simulated enrollment, not current approval or delivery authority |
| Request identities bind exact inputs | Restart replay, concurrent admission, reordered equivalent commands and changed-input conflicts | Local storage contracts; future providers need their own idempotency |
| Stale workers cannot commit | Lease expiry boundary, token replacement, cancellation and attempt caps | Selected local schedules; no multi-node operational claim |
| Domain work survives lost task receipts | Artifact commits before task receipt; restart retrieves the same operation/artifact | Deterministic local operations only |
| Results and events commit atomically | Forced event-write failures roll back result, lifecycle and authority updates | No disk-full, power-loss or backup-restore guarantee |
| Work/configuration remains resumable | Incompatible worker skipped before claim/recovery; correct worker resumes; finite timestamps/deadlines enforced | Configuration must remain pinned; unknown provider outcomes need investigation |
| Version and content drift fail closed | Changed catalogue, bytes, capability/input downgrade, legacy certificate substitution and unknown schema | No protection against an administrator editing trusted database state |
| Initialization is serialized | Lock before version read, whole-chain migration rollback, process/connection races and bounded WAL-busy retry | Local SQLite behavior, no mixed-version rollback support |
| Module ownership remains enforced | Actual import graph plus nine deliberately invalid imports | Static imports, not malicious reflection/in-process code |
| Inference is bounded and replay-safe | Concurrent reservation, input/output limits, lease/cancellation checks, receipt failure and unknown-outcome fencing | Real charging/availability and provider reconciliation are outside offline tests |
| Product copy binds reviewed evidence | Required text, qualifications, provenance, freshness, paired verdict and changed-copy/pack rejection | Lexical checks and a same-model screen do not establish general claim accuracy |
| Approval binds current authority | Exact subject, policy/evidence/suppression epochs, expiry, reviewer generation, revocation and later rejection | Configured local actors, not independently authenticated humans |
| Acceptance is one local effect | Competing acceptors, suppression ordering, tampering and event-write rollback; receipt replay after expiry | Local simulator, not an external delivery contract |
| Outcomes have an exact denominator | Accepted membership, assignment joins, full explicit coverage, complete-but-immature and closed-incomplete cases | Synthetic attestation, not verified real feed completeness |
| Counts use immutable independent observations | Literal posterior examples, deduplication, conflicting imports, disjoint business membership and concurrent finalizers | Repeated exposures and late corrections are unsupported |
| Memory is a consistent snapshot | Finalization forced between segment reads cannot split frozen context evidence | Local transactional snapshot; future adapters must preserve it |
| Historical replay does not repeat effects | New actor/request observing finalized/opened cohorts retains original receipt, event count and time | Existing historical events are not rewritten |
| Workspace commands recover partial success | Domain commit before metadata loss, request identity before clock advance and current-state receipt observation | Compatibility storage still spans databases; no distributed transaction |
| New selected workspace intent is application-owned | Projection poisoning/loss, process restart, frozen preparation, exact creation mapping, verified domain links and store identity checks | `verified-paused/v1` only; no legacy enrollment or activated rebuild journey |
| Owned simulation time binds an exact command | Real-SQLite insert failure rolls back the clock; changed-input replay, disabled operator, missing cohort and non-finite window probes | Seeded domain facts exercise this boundary, not verified execution activation |
| HTTP transport checks precede effects | Host/token/Origin, absolute-form GET/POST, bounded JSON, static traversal and server-root lock probes | Loopback trusted use, not public-service authentication |
| Browser retries preserve identity | Actual lost/5xx approval responses, interposed rejection, authentication error, field ordering, key migration and storage failure | Pending identities live in the browser session; no cross-device recovery UI |
| Presentation preserves access and history | Exact page width at 390/1440px; saved-preview styles and token isolation; named wordmark at 390/820/1440px | Selected Chromium layouts, not exhaustive browser/accessibility certification |
| Conversation intent survives replay and revision | Scoped SQLite messages, concurrent append and plan admission, process restart, stale browser revision and changed request rejection | Local trusted identity; bounded message history |
| Planning guidance is inspectable and immutable per admission | Changed or unavailable playbook source on replay, restart, scoped read, hash tampering and complete saved snapshot inspection after a purpose change | Bounded local playbooks; no claim of semantic retrieval or independent source verification |
| Brief proposals retain provenance without authority | Literal current GBP budget, supported segment catalogue, forbidden tool and no campaign/review/job writes | Model intent interpretation and clarification quality are not proven by structural validation |
| Planning stays bounded across interruptions | Six admissions per conversation, two calls per request, frozen-context admission recovery, unknown-call fencing, recorded-response replay and cancellation | Fake model responses only; no live planner quality or general semantic compliance claim |
| Late planning cannot replace new intent | A correction during inference makes the completed earlier result historical; changing a conversation invalidates review authority for its prior fixture or model campaign | Synthetic audiences and simulated acceptance only |
| Conversational model copy stays bound to the proposal | Selected-segment generation, exact budget, source context, fixture-downgrade rejection, stale evidence, metadata-loss recovery and uncertain-call fencing | Fake-model contract tests; live evidence recorded separately |
| Conversation edits fence further generation spending and draft creation | Edits from a separate workspace during each of the three copy calls; exact call counts and absence of stored drafts | A call reserved before an edit may still return a recorded observation |
| Terminal generation failures remain actionable | Saved 401 run is exposed through the backend and inspected after browser reload without another generate action | Provider codes are allowlisted; recovery requires an explicit new proposal |
| Uncertain generation remains distinct from definitive rejection | Network failure and interrupted reservation survive restart and lease recovery without a second provider call; browser inspects both saved runs after reload | Reserved and unknown receipts require inspection of the original run; no provider reconciliation is claimed |
| Model-copy spending requires explicit permission | Continuous preparation binds per-request copy consent, refuses replay expansion and stops without consent; legacy proposals retain their explicit generation action | Fake-provider browser and real SQLite tests; model interpretation remains separately evaluated |
| Planning replay cannot dispatch unrelated work | Completed-plan replay with a separate queued conversation; targeted recovery with an unrelated expired lease and wrong organization | Targeted local worker path; general worker draining remains organization-wide |
| Budget corrections do not silently reuse stale amounts | Later unsupported currencies, shorthand, relative edits with valid amounts, ranges and mixed valid/invalid amounts require clarification; explicit new totals remain valid | Pattern-based detection cannot identify every natural-language correction |

| Continuous preparation reuses exact saved work | Duplicate admission, concurrent identical admission, lost coordinator write, lost draft-status write and real-process queued recovery. The browser drops a successful admission response before reload and reaches review with one admission | One local executor; no multi-node scheduling claim |
| Conversation edits stop continuation | Reads and appends during an in-flight planner, edit before a repair call and edit during copy; no later copy/draft or release | An already dispatched provider request cannot be withdrawn |
| Preparation progress grants no authority | One submitted model brief reaches a valid unapproved candidate; approval invalidates after a later message | Synthetic campaigns and simulated delivery only |
| Interrupted work cannot be presented as ordinary failure | Unknown network outcome and interrupted planner/copy reservation remain uncertain on restart, with no additional provider call | No provider-side reconciliation is implemented |
| Progress is a read-only projection | Guarded 202 admission leaves a queued task without calling the worker; browser reload reaches review with one admission and no plan/draft/approve/handoff POST | Background execution requires the local server; direct legacy endpoints remain synchronous |
| Checkpoint polling follows recoverable progress | Real SQLite recovery interleaves with old campaign/progress reads. Exact saved stop receipts keep both ready-progress and cancelled-progress reads pollable until the case appears. An ordinary blocked preparation, even alongside another conversation's stopped checkpoint, cannot claim recovery | Local eventual projection reads; polling grants no approval or inference authority |
| Projection reconstruction grants no authority | Independent snapshots of every application table remain unchanged after inspection, rebuild, process exit and retry; paused workers still dispatch nothing | Registered new-format stores only; no legacy migration or restore activation |
| Legacy projection records remain protected | Opaque preparations, BLOBs, journal identity, unrelated session/command rows and legacy diagnostics survive; a conflicting native request key blocks rebuild | Unreadable files and unsupported layouts are refused rather than replaced |
| Projection writes are atomic and bound to observed inputs | Hard exit before commit rolls back, lost acknowledgement replays, changed source/control records reject commit, stale inspection plans fail and locks release immediately | Supported single-server root lock; fingerprints bind projection inputs, not backup completeness |
| Rebuilt progress discards only owned diagnostics | Exact owned run/revision cache keys are removed while diagnostics for legacy keys in the same organization survive | Current progress and permission come from application journals; cache deletion admits no work |

| Message replay cannot transfer consent to a newer brief | Browser loses an acknowledged message response, another writer appends a correction, reload retries the original identity, and no preparation is admitted for the newer revision | Consent remains bound to the original message receipt revision |
| Staleness cannot hide possible provider charges | Planner and copy timeout/crash after an edit retain both historical status and unresolved journal details across restart; browser checks new and older stale records | No automatic provider reconciliation or uncertain retry |
| Planning cannot outlive its coordinator admission | A rejected coordinator write leaves no plan; three interrupted planning admission boundaries resume in a fresh process without a browser and with unavailable current guidance | Separate stores reconcile through original request IDs and frozen inputs |

## Continuous preparation failure model

Confirmed owners are the conversation revision transaction, runtime task lease, inference reservation journal and exact-subject review transaction. Coordinator state describes continuation, not domain authority. The test portfolio challenges six boundary groups: request/consent identity; scope; source revision; provider uncertainty; partial persistence/restart; and review authority. All six have executable cases in `test_preparations.py`, the HTTP suite and the browser journey. This is a bounded inventory, not exhaustive interaction coverage.

Selected schedules reject a coordinator write before any plan is created and interrupt after coordinator persistence before the plan record, after the plan record before task creation, after task creation before run-ID persistence, after campaign commit before coordinator progress, during planner repair and copy inference, and after an inference reservation without a response. Preparation mutations remove copy consent, misclassify uncertain outcomes, omit interrupted-reservation recovery, remove the planner reservation revision check, hide stale uncertainty or terminal journals, and admit a plan before coordinator persistence. Terminal coordination states are not automatically reactivated. Configuration-blocked recovery currently requires inspection and an explicit revised request or trusted local CLI recovery; the UI has no resume command for that state.

## Targeted copy revision boundaries

The new boundary groups are immutable feedback/consent admission, paid-run identity, copy-only scope, current source authority, publication lease, historical receipt replay and exact displayed browser subjects. Tests cover each group with real SQLite or real-backend browser journeys. The nine added mutations challenge source fencing before paid calls, paid-run binding, the final publication lease check, sibling-letter preservation, approval invalidation at admission, review/progress consistency, blocked-state visibility, per-revision failure isolation and blocker removal before dispatch.

- A request records rejection and its immutable context/receipt/audit atomically. Injected audit failure leaves the previous approval valid and creates no revision.
- The actual original and candidate drafts establish the comparison oracle: snapshot, brief, enrolled population, arm assignments, cost, product selections and sibling text/identity remain fixed. The target identity changes; no learning record or approval transfers.
- Separate writers change the brief, policy/evidence epoch, suppressions, operator authority or original run during inference. Later model calls and publication are blocked. A duplicate paid run cannot reuse another revision's admission.
- Expiry before publication and expiry during candidate validation prevent publication. Recorded generation and publication recover after lost task acknowledgements without duplicate calls or subjects. A fresh process resumes an admitted request without browser state.
- Browser tests cover the complete feedback/review journey, stale approval and feedback dialogs, lost decision acknowledgement, uncertain provider outcomes, reload and mobile overflow at 320px/390px. A read/publication interleaving cannot combine completed metadata with the earlier letters. An unrelated rebuild receipt cannot masquerade as copy publication, and a historical approval dialog disables submission while remaining closable.
- A separate workspace admits a revision between the review and progress reads in real SQLite. The returned packet includes the committed rejection and admission together, even though the subject ID is unchanged. The workspace rechecks the complete transactional review projection, excluding only its read timestamp, and retries a changed projection at most three times before returning a conflict. Reads dispatch no model calls.
- Missing-key and frozen-settings failures remain visibly blocked across workspace reconstruction, preserving the exact admission and any queued tasks without consuming attempts. Restoring configuration resumes the original run. An expired-evidence request with no run cannot starve a later healthy campaign. Browser coverage removes the key after actual backend admission, then checks sanitized guidance and blocker persistence after reload. Uncertain-result tests remain independent of recoverable configuration blockers.
- A gated fake provider holds a resumed request in flight after configuration restoration. Real SQLite reads show the same request running with a reserved call and no saved blocker. The browser observes this progress through polling, then reaches review after the gate opens without another generation submission or a stale charge warning. Terminal timeout and interrupted-reservation tests retain their uncertainty warnings.

These are bounded schedules and fake-model responses. They do not establish semantic success on subjective feedback, live model quality, external delivery or multi-worker readiness.

## Test composition

Pure domain tests use literal expected populations, money and posterior values. Persistence tests use real temporary SQLite databases, controlled clocks, concurrent connections and injected failures. CLI tests cross OS process boundaries to exercise restart, review, export, learning and replay. HTTP tests send real requests to the loopback server. Frontend client tests use the real backend, and Chromium tests inspect the rendered interface.

CI runs the complete backend suite in two parallel shards on each Python version from 3.11 through 3.14. Standard unittest discovery supplies both shards. Whole modules stay together, and measured module runtimes balance the two groups. The first shard also runs the architecture check for its Python version. Run the same groups locally with `make test-shard SHARD=1` and `make test-shard SHARD=2`. The mutation suite runs once in a separate, parallel Python 3.12 job. The architecture checker still has a self-test with deliberately forbidden imports.

The mutation command creates temporary source copies and weakens selected enforcement points, including leases, reservations, uncertain-call fencing, retired-workflow admission, timestamp validation, migration locking, review expiry/epochs, cohort maturity/completeness, atomic finalization, snapshot memory, Origin checks, exact-subject binding, planning budget provenance, current-revision projection, conversation scope, targeted execution, stale-budget correction handling and relative-budget recognition. The results apply to the declared probes. They are not a general mutation score. Frontend regressions are reported separately.

The analytic Beta(1,19) quantiles provide an independent check on sampled prior intervals. Count tests verify exact trials/successes and sequential/batch equivalence. This checks calculation behavior; it does not calibrate the prior or turn simulated results into real causal evidence.

## Recorded live model evidence

The [grounding reference](product-grounding.md) records a dated GPT-OSS-120B run and a small eight-variant screening regression. The rubric and regression examples were developed together. Their match rate is not held-out accuracy, and the recorded run is not a fresh claim about current provider pricing, availability or output quality. The exported example remains unreviewed.

## Remaining gaps

There is no asserted line/branch coverage percentage or overall correctness percentage. Selected fault positions and concurrency schedules leave untested interleavings. General semantic claim detection, real data completeness, marketing impact, production authentication, external agency effects, multi-host throughput, disk-full/power-loss behavior, execution from a restored checkpoint, real outcome corrections and repeated-exposure attribution remain outside the demonstrated evidence.

A UI review cannot establish approval correctness, and module unit tests cannot establish restart behavior. Preserve checks at the boundary where each real effect is authorized and persisted as the system evolves.

## Conversational handoff boundary (issue 17)

The approval and simulator transaction remain authoritative. The new chat surface captures the displayed approval and subject, saves the confirmation before command dispatch and uses the existing exact-input API request identity. A simulated acceptance is historical evidence, never authority for another effect. Receipt exports require the exact displayed accepted subject and draft.

- Seven real-backend browser cases cover the offline end-to-end journey, receipt and artifact downloads, historical inspection after a brief edit, mobile overflow at 320px/390px, lost responses before and after commit with reload, and stale confirmations after refresh, revocation, suppression or message append. These cases make no model calls.
- Real SQLite tests cover receipt export before acceptance, wrong subjects, byte-preserved accepted history after a source edit, expiry and disabled reviewer denial. A fresh OS process replays the original handoff after acceptance but before the control acknowledgement is marked complete, producing the same receipt and exactly one acceptance event.
- Existing review tests continue to exercise evidence epochs, candidate integrity, cross-scope approval substitution, acceptance/audit/receipt rollback and transaction ordering. This slice adds no dispatch adapter, learning update, role or approval policy.

The demonstrated topology remains one local server and simulated acceptance. Real delivery, browser storage loss and a production authentication/reconciliation service are outside this evidence.

## Conversational learning boundary (issue 19)

The new surface reuses the Learning view and existing session operations. Chat confirmations bind accepted job/cohort IDs; the facade verifies them against the server-owned session and accepted cohort source before mutation. Legacy workspace payloads remain compatible. Domain cohort membership, maturity, completeness, operator authority, immutable outcomes and atomic finalization remain authoritative.

- Real SQLite tests reject learning before acceptance and reject substituted job/cohort IDs without changing the clock or learning state. Changed request inputs and disabled operators cannot update beliefs.
- Early synthetic responses preserve unknown denominators and leave beliefs/recommendations empty. Complete mature data yields counts summing to the accepted population, including A/B and controls. A later brief edit leaves accepted history usable for learning without authorizing another campaign.
- A fresh OS process replays finalization after the domain commit but before control acknowledgement, preserving the exact projection and one finalization event.
- Four backend browser cases cover the offline lifecycle, posterior/control display, mobile overflow, historical learning after an edit and loss of acknowledged open/observe/finalize responses with reload and exact request replay. No new model request or next experiment is generated.

These are synthetic demonstration results. Real attribution, production calibration, repeated exposure and external feed reconciliation remain outside this slice.

## Follow-up proposal boundary (issue 21)

Ten real-SQLite/fake-provider tests cover finalized-source admission, source and scope substitution, original-mode replay, frozen model context/memory and explicit inference consent, disjoint child enrollment, fresh approval and successful independent cohort opening. Further cases exercise a later allocation/evidence change, a source-stripping publication attempt, exhausted inventory, unknown-call replay and fresh-process preparation. Preparation request IDs bind the parent, proposal, mode and consent in the same control-database transaction as the child session. A restart regression checks replay and rejects reuse for a second valid proposal. The parent cohort and its counts remain unchanged.

Three browser journeys cover proposal-specific generation consent and the finalized offline conversation through proposal inspection and new child approval, exact population disjointness, mobile overflow, reload and a lost acknowledged preparation response. Reading the committed child does not submit another generation. Two added mutation probes weaken population independence and source-brief binding; existing mutation probes continue to cover approval and learning effects.

This establishes the bounded 2,000-record synthetic scenario and selected interleavings. It does not establish real audience inventory, calibrated marketing impact, concurrent hosted operation or remote delivery. Model tests use fake providers and make no live quality claim. The legacy manual follow-up path still has its documented overlap restriction.

## Versioned reasoning assets (issue 25, first slice)

Scoped content bundles bind installed tool schemas, authored skills and exact source hashes/roles in new planning and grounded-copy contexts. Real SQLite and fresh-process tests cover source coverage/content mismatch, foreign scope, tool/schema substitution, invalid skill references, changed current guidance, historical replay without current files, old unannotated tasks and a separately frozen revision skill. Actual base inputs remain exact at revision admission and no asset grants approval. Two declared mutation probes remove installed-schema equality and skill/tool membership checks. These checks establish serialization, provenance and bounded compatibility; they do not establish semantic skill quality or new conversational action execution.

The issue-25 review regressions additionally cover maximum permitted reviewer-memory size at the unchanged 24 KB input budget, complete initial-copy preflight before any paid read, zero-call failure for an oversized submission, original transcript behavior for old unannotated contexts and frozen follow-up preparation with a changed/unavailable current catalogue. Full server metadata is retained while new model-visible copy metadata is compacted through an explicit projection version. Two more mutation probes remove full-envelope preflight and frozen-context reuse.

Legacy copy compatibility also has an exact-input-limit regression with a recorded SQLite read response. The actual legacy request fits while the synthetic exchange is larger; replay must complete with three recorded calls and only one read dispatch. Stable-exchange preflight applies only to the new projection. A declared mutation incorrectly preflights legacy contexts and must be detected.

## Unified readiness report (issue 25, second slice)

Seven required checks compose exact artifact integrity, source-run state, brief provenance, current epochs, evidence freshness, deterministic population/money and copy contracts. The report requires every check to pass; missing/downgraded checks are invalid and unknown results block readiness. Human editorial suitability and real performance remain explicitly unevaluated/unknown. SQLite tests cover stale sources, validator unavailability, exact model/source bindings, read-only restart observations and amendment invalidation. A real-backend browser journey imports a suppression and checks readiness and approval blocking at responsive sizes. Mutation probes remove the required-check gate and coverage check. See [campaign validation](campaign-validation.md) for the observation and authority contract.

## Versioned audience source boundary (issue 26)

Discovery never resolves ambiguity by ordering. Retrieval requires a scoped dataset/version, content checksum and metadata identity. Raw-file integrity is separate from completeness, model provenance, declared population coverage and source freshness. Synthetic source data grants no targeting, approval or delivery authority. Reads make no model calls and create no campaign effects.

Real-file regressions reject changed bytes and metadata, another organization, incomplete or mismatched coverage, expired/future sources, unsafe paths, symlinks, duplicate fields/versions and oversized payloads. Real SQLite checks show that retrieval leaves audiences, runs, decisions and agency jobs unchanged; an explicitly saved immutable snapshot survives a fresh process. Protected loopback API tests verify exact query fields, scope resolution and metadata-only results. Mutation probes remove checksum, manifest matching and source completeness. See [audience catalogue](audience-catalogue.md) for implemented scope and deferred campaign binding.

Verified for the audience-catalogue slice: 298 backend tests, architecture checks, all 59 declared mutation probes and whitespace checks passed. The frontend was unchanged; no live model or external storage call was made.

## Conversation audience selection boundary

The new selection is a revision-bound input decision, not campaign approval. Materialized campaign rows must preserve the independently saved source population and values, allowing only added suppression flags during refresh. The source receipt binds both metadata and decoded snapshot identity; removing or substituting it cannot downgrade a selected campaign to the older generated path.

Real SQLite and process tests cover confirmation before campaign admission, exact-input replay, two valid competing versions, stale revision at commit, transactional rollback of snapshot/selection/receipt, unavailable current files after confirmation, source scope and segment mismatch, combined-segment coverage, targeted copy revision, suppression refresh and separate exact-subject approval. Schema-v7 failure rolls back DDL and the version marker while preserving the original legacy cutoff. Old schema migration tests continue to exercise earlier rollback boundaries.

Freshness tests shorten the audience review window while keeping product evidence valid. One advances twenty seconds across source expiry during a provider call while the lease remains active: no later call or draft is allowed. Separate review tests isolate the audience freshness gate from product expiry. Mutations remove selection-input binding, revision fencing, model-reservation checks, draft binding and review checks and must be detected.

Browser journeys cover source choice on desktop and 320px/390px mobile, original selection after reload, lost confirmation acknowledgement and definitive stale-choice rejection. They inspect actual backend manifests/readiness and confirm that no approval is inherited. No paid inference or remote storage integration is claimed by these fake-provider journeys.

Verified for this slice: 316 backend tests, 55 browser tests, architecture, production build, formatting, whitespace and all 64 declared mutation probes passed. Browser captures cover desktop and 320px/390px mobile. All provider behavior in these checks used fake adapters; no paid model call was made.

## Audience selection review corrections

The original campaign admission binds its sourced or unsourced mode. A later selection for the same conversation revision cannot retroactively invalidate an unsourced campaign or its existing approval. Real SQLite tests approve an unsourced campaign, record a later selection and complete its original handoff. Sourced admissions reject provenance stripping even when the separate selection row is also removed. Legacy preparation progress does not label a later selection as that campaign's confirmed audience.

Selection and inference adapters use composition-root-injected clocks and reread time after acquiring the write lock. Held-lock tests advance twenty seconds across source expiry before allowing each transaction to proceed. Selection leaves no snapshot, selection or command receipt. Inference makes no provider call and creates no reservation. Additional cases cross lease expiry and change the clock to a non-finite value while blocked. The source-expiry case keeps the lease and product evidence valid to isolate the source freshness rule.

Declared mutations remove each locked clock read, the original unsourced-mode preservation and the original sourced-mode binding. Each must be detected by its focused regression. These controlled interleavings do not claim exhaustive scheduling coverage.

Verified after these review corrections: 322 backend tests, architecture and whitespace checks, and all 68 declared mutation probes passed. No frontend files changed in this correction pass; the browser suite was not rerun. No paid model calls were made.

## Final selection and inference commit fences

A clock reading at lock acquisition cannot cover time spent validating or writing. Source confirmation therefore performs a cheap freshness check on its verified manifest at the end of the selection transaction. A newly reserved inference call similarly rechecks finite time, lease expiry and the verified source window after the reservation insert, immediately before transaction commit. No provider call can occur until that transaction returns. Full snapshots are not loaded again by these final deadline checks.

Real SQLite tests advance the clock during selection validation, snapshot serialization and the receipt insert, checking that all snapshot/selection/receipt writes roll back. Separate fake-provider cases advance time during source validation and during the reservation insert, independently crossing the audience deadline or the lease deadline. Product evidence remains valid, and lease-only tests keep the audience window open. All rejected calls leave no journal reservation and dispatch no provider request. A non-finite final clock is rejected; a valid-source/valid-lease control dispatches exactly once. A targeted revision regression checks that its verified source window reaches the shared final reservation fence.

The earlier lock-wait regressions remain. Locked-clock-only mutation probes were replaced with final-clock, final-source, final-lease and revision-deadline propagation probes, since the new final fences also contain the lock-wait failure. This is a bounded set of clock positions and SQL-trigger interleavings, not exhaustive temporal coverage.

Verified after the final-fence corrections: 332 backend tests, architecture and whitespace checks, and all 72 declared mutation probes passed. The correction changes no frontend files; the browser suite was not rerun. All provider tests used fake adapters and made no paid model calls.

## Follow-up action continuity

Inspection is a separate durable operational object, not a brief amendment. Real SQLite tests keep revision, selected source, exact subject and approval unchanged across progress, audience, exclusion and validation questions. A status query completes while a fake copy provider is held in flight, and the original campaign completes without extra copy calls. Answers derive from frozen server observations and retain timestamp and source references across replay and a fresh process.

Amendment confirmation checks the exact action, target, base revision, completed routing result and original task inputs. Its message, revision update, confirmation and command receipt are atomic. Tests reject read-only results, substituted targets, changed frozen text, another scope, stale revisions and conflicting request reuse. Concurrent confirmations advance once; loss after confirmation recovers the original planning identity and copy permission. The model gets no approval or delivery tool.

Routing permits one model call per admitted action and at most twelve model admissions per conversation. Missing configuration preserves the request; an incompatible worker cannot consume it. Inference reservation checks the original action admission and run identity. A stale route cannot dispatch through an internal worker. An interrupted reserved call is cancelled locally on exclusive startup and remains uncertain; a recorded response can replay after a lost task acknowledgement without another provider call. Active reserved calls are presented as in progress rather than falsely terminal or uncertain.

Schema-v8 fault injection rolls back DDL and version changes while preserving selected source and the original legacy cutoff. Browser journeys cover desktop and mobile, inspection without invalidation, explicit amendment, lost action/confirmation responses, stale confirmation and active versus unknown model outcomes. Delayed confirmation responses cannot replace a newly opened chat, including the lost-response reconciliation path. An incompatible routing configuration remains visibly blocked without claiming the task; the original configured worker can resume it. Mutation probes remove replay-input binding, concurrent admission binding, exact confirmation target, action authority, original text binding, routing reservation admission and routing budget. There is no claim of held-out semantic routing accuracy or live-provider quality from these fake-provider checks.

Verified for this slice: 363 backend tests, 66 browser tests, architecture checks, production build, formatting, whitespace and all 79 declared mutation probes passed. Desktop and 320px/390px mobile layouts were checked. Provider tests used fake adapters; no paid model call was made.

## Clarification context in follow-up routing

Routing now freezes the two most recent brief messages and latest completed planner response, including its exact question and result identity. The response records whether it belongs to the current revision. Real SQLite regressions show a budget clarification and short `£600` answer reaching the fake provider together, with no brief change until confirmation. After confirmation, the ordinary planner binds the new budget to the saved answer and waits for audience confirmation. Another case preserves a `yes` answer's original question across request replay, a process restart and an intervening edit; the older question is marked historical and the stale route dispatches no inference.

A boundary case passes two 2,000-character messages and the full planner question through the actual envelope preflight. A golden legacy prompt and recorded receipt survive restart without another call. Mutations remove the question projection and the model-visible dialogue independently. These checks prove context delivery and control continuity with fake providers, not semantic intent accuracy. Handoff browser tests now wait for the visible recorded-approval state before reading its identity, preventing the test from racing the approval command.

Fresh verification after the correction: 367 backend tests, the full 66-test browser run, architecture, production build, formatting, whitespace and all 81 declared mutation probes passed. This includes the handoff test previously reported as flaky. No live model calls were made.

## Router clarification continuity through planning

Dialogue v2 freezes pending clarification and amendment exchanges as well as recent router replies. The exact-subject amendment result carries the source action IDs, user text and recorded agent responses into the displayed confirmation. Real SQLite regressions exercise a mixed £400 change-and-explanation request followed by `Change it`: neither question nor proposal changes approval, then confirmation atomically appends the two displayed user texts and freezes the full exchange for the planner. The new budget cites the carried original request. Both coordinator and direct planner admission preserve the confirmed exchange.

Multiple clarification turns and an unconfirmed proposal retain chronology, so a later explicit £500 correction overrides £400 without concatenating conflicting amounts into one message. Intervening inspection remains observational and cannot supply a £900 budget. The original revision fence and exact-task checks still apply. Confirmation checks carried source admissions and completed outputs in the same transaction; a changed source is rejected. Injecting failure on the final reply rolls back all earlier carried messages, revision changes, confirmation and receipt. Lost continuation after confirmation and process restart preserve one preparation and the final request's copy permission. Confirmation replay observes the original message receipts without appending again.

The model carry limit is four pending change exchanges; exceeding it rejects admission before inference while authored status inspection remains available. Pre-dialogue and dialogue-v1 recorded requests remain replayable without new calls or rewritten artifacts. Browser journeys show the carried original request and clarification before confirmation and preserve exactly one effect after a lost committed response. Mutation probes remove carried context, user-message commitment, source verification, confirmed snapshot propagation, planner visibility, the carry limit and pending-proposal continuity. No live semantic accuracy is claimed from fake-provider tests.

Verified after this correction: 376 backend tests, all 68 browser tests, architecture, production build, formatting, whitespace and all 88 declared mutation probes passed. Carried-request confirmations also stay within 320px and 390px mobile viewports with a long unbroken text input. No paid model calls were made.

## Durable action admission order

Scoped action listing and organization-wide recovery listing use SQLite `rowid` admission order. Wall-clock timestamps remain historical observation data. A controlled-clock SQLite regression admits £400, moves time backwards, admits £500, moves time backwards again and admits the reply. Both listing scopes, frozen router context, the displayed amendment exchange and committed messages preserve admission chronology across restart and replay. The ordinary planner cites £500 as the latest explicit budget. The test failed against timestamp ordering before the correction.

Confirmation rechecks carried source admission order inside its write transaction. A compatibility regression constructs a reversed exchange using the previous timestamp-order producer, then confirms with the corrected consumer. Confirmation rejects it before any brief write and leaves the frozen action, result and message history unchanged. Separate mutations restore timestamp ordering or remove the confirmation sequence fence. No frontend files changed in this correction.

Verified after the ordering correction: 378 backend tests, architecture, whitespace and all 90 declared mutation probes passed. The frontend suite was not rerun for this backend-only correction; its preceding 68-test run remains recorded above. No paid model calls were made.

## Natural-language targeted copy revision

New versioned routing proposes copy-only edits against the current server-owned campaign. It does not change the brief, audience selection, approval or native copy state. Real SQLite tests bind an explicitly named variant, preserve earlier feedback through A/B and segment clarification, reject unsupported fixture targets and recover from the native 500-character feedback limit. A generic campaign-copy checkbox cannot authorize revision: exact confirmation requires the separate boolean five-call permission.

Confirmation, native copy admission, exact-subject rejection, events and command receipts share one transaction. Trigger faults at action confirmation and command receipt insertion roll all of them back, preserving the original approval. The native adapter independently checks the displayed subject, draft, creative and copy preview, and revalidates carried user feedback against its original task. Both facade and direct native admission paths are tested. A wrong result reference, another conversation, changed source feedback, stale subject or reused confirmation key cannot create another effect. Concurrent confirmations and lost-response restart recover one native revision. The native five-call limit, one request per source subject and three-revision case limit remain unchanged.

End-to-end fake-provider revision preserves the sibling's identity and wording, audience, assignments, budget and product wording, then publishes a new unapproved subject. Missing provider configuration remains visibly blocked and restoration resumes the original admission. An uncertain revision stays inspectable without automatic redispatch. Routing reservation now checks its exact admitted capability as well as inputs and run identity. Genuine earlier routing contexts retain their original tool and prompt envelopes for receipt replay.

Browser journeys exercise proposal/consent separation, target clarification, new in-chat review, stale-target rejection, lost committed and uncommitted acknowledgements, unknown outcomes and navigation during a delayed response. A held reload read proves a quick reply cannot create a new chat before the selected conversation loads. Desktop and 320px/390px mobile views were inspected, including document overflow assertions. Mutation probes weaken consent, feedback continuity, result binding, source feedback checks, actual preview attestation, atomic confirmation and routing-capability binding.

Verified for this slice: 399 backend tests, all 76 browser tests, architecture, production build, formatting, whitespace and all 97 declared mutation probes passed. No paid model calls were made. These fake-provider checks establish bounded authority and continuity behavior, not live semantic routing accuracy or marketing performance.

## Copy clarification and independent edit boundaries

New dialogue v4 carries only unanswered copy clarification. Selector-only wording questions survive reload, restart and intervening inspection. A ready proposal closes that feedback chain; a later self-contained target and wording request also starts independently of unresolved feedback. Invalid or overlong feedback resets instead of persisting as a selector. The exact displayed feedback still binds native admission and its separate generation permission.

Five regressions failed against the previous implementation before the correction. Real SQLite tests now exercise `B` followed by `Make it more direct`, a ready formal B edit followed by a casual A edit, a complete replacement of an unresolved request, a new clarification after a ready proposal, and an old cross-target carry rejected at confirmation. Additional cases keep invalid-feedback recovery and a genuine dialogue-v3 recorded request replay intact across task interruption and restart. Frozen legacy results are unchanged; same-target v3 feedback remains confirmable, while an unconfirmed cross-target proposal requires a new edit. Historical confirmation replay grants no new effect.

Browser journeys check both reported sequences through exact feedback display, separate consent and native revision completion. Mutation probes remove selector retention, the ready-proposal boundary, independent restatement and the legacy cross-target fence. Existing approval, source, inference and native revision checks remain in place. No paid model calls were made.

Verification after this correction: the 406-test backend run passed 391 tests and hit sandbox bind restrictions in the 15 HTTP test setups. All 15 HTTP tests then passed with loopback permission. The full 78-test browser suite, architecture check, production build, formatting, whitespace and all 101 declared mutation probes passed. The 27-test targeted copy suite also passed, including the seven new regressions. No live semantic model accuracy is claimed.

## Shared execution allowance and cancellation

The conversation-wide policy counts original inference reservations across planning, routing, campaign copy, targeted revisions and descendant experiments. Real SQLite checks compete for the final allowance slot, replay a recorded response at the exhausted cap, reject another valid conversation substituted into an admitted run, and preserve counts across a fresh process and schema-v9 backfill. Rejected and uncertain calls consume their original slot; late observations do not grant task authority. Cost projections expose metadata coverage and do not claim verified billing.

Cancellation binds an exact revision and idempotency identity. Tests stop held planning and revision providers, verify no additional dispatch or draft publication, retain late or unknown receipts, and recover after admission interruption. Fault injection on the stop receipt rolls back the fence, run/task cancellation and audit. Existing review checkpoints stay intact: stopping alone cannot invalidate approval, and new revision admission after stopping cannot insert a rejection. A new brief clears the current stopped state without resetting the allowance; replay of an earlier stop cannot cancel it. Migration rollback preserves the original legacy cutoff and exact journal bytes.

Browser journeys cover a lost committed stop response, receipt completion after cancellation, fresh audience confirmation for a new brief, unchanged usage across reload, and 320px/390px overflow assertions. The lost-stop-response test holds the fake provider until the browser observes stopped work with a pending response, then releases it and verifies accounting and publication fences. Desktop and mobile screenshots were inspected. Mutation probes weaken shared capacity, original run binding, stop fences, run/task cancellation, stop-receipt persistence, approval preservation and replay at capacity. No paid model calls were made.

Verification: the clean full backend run passed all 422 tests; the full interface check passed all 80 browser tests, production build and formatting. Architecture, whitespace and all 108 declared mutation probes passed. The 15 execution checks also passed after the final ancestry-lookup optimization. Earlier failures came from old-schema fixture setup and a follow-up fixture outside its evidence window; fixtures now preserve the intended historical setup and exercise valid evidence dates without extending production evidence. No live model or billing behavior is claimed.

## Manual descendant ancestry and checkpoint recovery

Manual next experiments now persist the workspace-resolved parent run in the existing execution journal before task admission. Their model calls, native revisions and draft writes resolve the same conversation allowance and stop fence. SQLite regressions observe all six fake-provider calls in shared usage, preserve usage across restart/replay, deny a new child after stopping, cancel a queued legacy child after reconstructing its missing ancestry, and reject further calls at the shared last slot. Recovery attaches existing manual call history without rewriting requests, receipts or draft bytes.

Stop preserves a reached review checkpoint using the final waiting task, successful predecessors and exact stored draft reference, independently of review-case timing. Both fixture and model checkpoints remain waiting and become valid unapproved cases without inference. A fault after the stop receipt commits leaves recoverable checkpoint references; repeated recovery opens one case and grants no approval or handoff. An unrelated waiting task is still cancelled. The chat retains a Stop control for blocked preparation and exposes the recovered review immediately, including after reload.

Targeted mutation probes restore the manual origin omission, skip ancestry admission, require an already-open case at a checkpoint, and omit immediate review recovery. Existing cancellation, allowance, replay and approval-preservation probes remain active. No paid model calls were made.

Verified after these corrections: all 430 backend tests, all 81 browser tests, architecture, production build, formatting, whitespace and all 112 declared mutation probes passed. The strengthened legacy-queued-child regression also passed separately after simulating missing old ancestry before stop. The isolated preview was restarted only after confirming no active runs or running tasks. No live provider behavior was tested.

## Worker migration fencing and isolated checkpoint restoration

Schema-v10 tests migrate an older manual descendant with no stored ancestry and a one-call allowance, then use a direct configured worker before any workspace recovery. It claims no tasks, consumes no attempts and dispatches no model calls. A separately retained live lease is denied at reservation. After the original workspace relationship is recovered, the same work can consume one properly attributed call and cannot exceed its shared allowance. An unrelated standalone organization still completes six fake-provider calls. A fault after the migration's ancestry marking rolls back DDL, version and data while preserving original receipts and the legacy cutoff.

A real loopback server starts with two pending checkpoint restorations while one operator is disabled. The affected checkpoint exposes sanitized blocked guidance, its actor remains disabled, and the other case recovers. Explicit administrative restoration permits recovery without generation or approval. Another test fails the preparation-journal update after the case ID is saved: restart reconciles that existing case to review readiness, records no second review-opened event and leaves approval absent. Repeating completed recovery does not advance the journal epoch.

Browser coverage checks visible recovery guidance and continued polling until authority is restored, without a reload or new inference. Five new mutations remove the unresolved-origin migration mark, worker claim gate, reservation guard, failure isolation and existing-case journal reconciliation. No live provider behavior is claimed.

Verified after the recovery corrections: all 436 backend tests, all 82 browser tests, architecture, production build, formatting, whitespace and all 117 declared mutation probes passed. The focused migration/recovery subset passed all 35 checks. The isolated preview was stopped only after verifying all its domain databases were idle, then reopened with schema v10. Verification used fake providers; no live provider behavior was tested.

## CLI campaign recovery and incomplete cost coverage

Two regressions reproduced a completed CLI campaign remaining quarantined without a descendant session, and six unattributed calls yielding a falsely complete zero-cost projection. Recovery now resolves the CLI's stable campaign reference against the original scoped request and frozen campaign brief. Fresh-process tests cover schema-v9 migration and already-quarantined schema-v10 records, with exact task history, receipts, drafts and legacy cutoff preserved. Repeated workspace recovery needs no descendant session. Recovered queued CLI work obeys the original stop fence and shared allowance before dispatch.

Negative cases preserve quarantine for missing campaign provenance, a request identity belonging to a planner, and a matching campaign in another organization. Unknown histories remain blocked. Cost coverage is incomplete whenever potentially shared runs remain unattributed, even if all known calls report cost. Tests retain a known $0.06 subtotal alongside unresolved calls, and the browser checks the explicit incomplete label using six real fake-provider journal records. Five new mutation probes remove CLI origin resolution, reopening recovery, organization scoping, campaign attestation and incomplete-cost coverage. No paid model calls were made.

Verified after these corrections: all 442 backend tests, all 83 browser tests, architecture, production build, formatting, whitespace and all 122 declared mutation probes passed. The focused execution suite passed all 35 tests; the strengthened stopped-CLI test also passed with an available allowance, independently of budget exhaustion. The idle isolated preview was refreshed and returned HTTP 200. Verification used fake providers; no live model or billing behavior is claimed.

## Explicit reconciliation of independent legacy runs

Unresolved ancestry now exposes a nullable remaining allowance and labels known usage without asserting a spendable remainder. The inspection panel lists recovery commands and scoped run identities. A trusted enabled local operator can inspect a quarantined run and attest that it is independent through the CLI, without a provider key. The command binds the exact run, task and inference-journal fingerprint, actor and explanation. A stale inspection, missing or disabled operator, another organization, active task or proven conversation origin is rejected. This is an explicit administrative classification, not an inference from missing metadata.

Real SQLite tests cover migration of an independent CLI run, preserved task and receipt bytes, existing approval, complete accounting after reconciliation, restart and repeated receipt observation. The immutable classification survives the migration quarantine sweep and rejects a conflicting later parent link. Concurrent classifications produce one decision; changing inputs on a reused identity is rejected. An injected audit failure rolls back both command receipts, the decision and quarantine removal. A queued independent run resumes under its original per-run limit without consuming the stopped conversation's allowance. Fresh-process CLI inspection, resolution and lost-response replay need no model adapter.

The browser checks unknown allowance, incomplete cost and visible operator instructions at desktop and mobile widths, then executes the real operator CLI and reloads to observe the restored numeric allowance. Seven new mutations weaken operator authority, exact inspection binding, proven-origin checks, classification immutability, marker durability, atomic audit and unknown-allowance projection. No paid model calls were made.

Verified after these corrections: all 449 backend tests, all 83 browser tests, architecture, production build, formatting, whitespace and all 129 declared mutation probes passed. The focused execution suite passed all 42 tests. The isolated preview was refreshed only after all domain databases were verified idle and returned HTTP 200. Verification used fake providers; no live semantic or billing behavior is claimed.

## Workspace ancestry at the independence boundary

Reconciliation now checks both authoritative journals before accepting an operator's independence claim. Scoped workspace records matching the run, request or campaign identity are part of the inspection fingerprint. A recorded parent, follow-up or conversation plan rejects classification before domain recovery. An inconsistent database scope or unavailable workspace journal also blocks classification. The command opens the original journal without creating a substitute, obtains its write lock before the domain transaction, and retains that lock through classification commit. Exact historical receipt replay remains observable without current workspace availability.

Real SQLite regressions reject an incorrect operator attestation against a migrated queued workspace child through both the adapter and a fresh CLI process. No decision, audit or quarantine removal commits, normal recovery succeeds, and a subsequent stop prevents dispatch. A completed child with six provider receipts retains those calls in its conversation accounting after recovery. A controlled interleaving commits a workspace parent while reconciliation waits for the write lock; the command reads the newly committed relationship and rejects independence. Another test attempts a competing workspace write at the resolution audit boundary and confirms that the workspace lock is still held. Changed workspace inspection data needs a fresh fingerprint; another organization's record cannot determine this run's origin. Missing-journal checks preserve quarantine while allowing observation of a genuinely completed resolution.

Four new mutations omit workspace-parent authority, weaken the write lock, exclude workspace evidence from the fingerprint, and remove organization scoping. Genuine independent-run authorization, concurrency, replay and atomicity checks remain active. No paid model calls were made.

Verified after this correction: all 456 backend tests, all 83 browser tests in one full run, architecture, production build, formatting, whitespace and all 133 declared mutation probes passed. The focused execution suite passed all 49 tests. No live provider behavior was tested.

## Persistent workspace journal identity

Workspace initialization now assigns an immutable journal ID and records whether identity initialization observed a new empty journal or populated legacy history. Workspace composition binds each organization's domain history to that ID in the existing execution ledger before its first run. Existing bindings are never overwritten. Inspection and new independence decisions verify the scoped binding while holding both journal locks, and include the verified journal ID in the inspection fingerprint. Public stop commands reserve the binding namespace. Historical decision replay remains an observation of the original receipt.

SQLite regressions replace the original journal with a newly created empty workspace and attempt the reported incorrect attestation before recovery. No decision, audit effect or quarantine removal commits, and reopening does not replace the domain binding. Restoring the original journal permits ancestry recovery and preserves the stop fence. A separate genuine independent run rejects a substituted unrelated journal and resolves after its original is restored. A fresh recreated journal cannot adopt old history after matching session rows are added. Journal identity survives restart and rejects updates or deletion through normal SQL operations.

Legacy enrollment requires a populated pre-identity journal with a matching persisted random run ID, request identity, intact task hash and frozen conversation provenance. A regression uses two genuine workspaces with matching campaign names and different run IDs: the unrelated journal cannot enroll the original domain history, while restoring the original permits verified enrollment and independent-run reconciliation. Three new mutations weaken the journal ID comparison, permit fresh journals to enroll existing history, and substitute a matching request name for the exact legacy run witness. No model calls were made during reconciliation; verification providers remain synthetic.

The existing fake-model workspace test wrapper forwards the new composition scope, so its six-call preparation check exercises real journal enrollment rather than bypassing the binding path.

Verified after this correction: all 462 backend tests passed in a clean full rerun, all 83 browser tests passed in one full run, and architecture, production build, formatting, whitespace and all 136 declared mutation probes passed. The focused execution suite passed all 55 tests. No live provider behavior was tested.

## Legacy completeness and deterministic lock release

A matching root cannot prove that a populated legacy backup contains later child sessions. Automatic enrollment of existing history has been removed. Only a binding made before the organization's first run can support independent classification. Witness-based legacy bindings and their independence receipts remain immutable history but do not supply current execution authority. On reopen, unlinked runs with such old decisions regain the pending-origin fence. Positive parent recovery can restore the correct execution account without rewriting the old receipt. Unknown pre-identity ancestry remains paused; full backward or partial-restore recovery is not claimed.

The stale-backup regression snapshots a populated root journal, admits a later child, removes its domain ancestry to represent legacy records, and restores the earlier backup. Neither workspace opening nor an incorrect operator attestation can enroll the history or clear quarantine. Restoring the complete source permits positive parent recovery and preserves stopping. Another test seeds an old witness-based binding and independence decision, verifies historical replay grants no authority, then recovers the positively recorded parent. Existing correctly bound independent runs keep their authorization, replay and atomicity coverage.

The journal guard now establishes cleanup before opening or validating the connection and closes it in a nested finally even if rollback fails. The lock regression retains validation exceptions and tracebacks with garbage collection disabled, supplies multiple invalid identity shapes, and immediately acquires and commits a second writer. This checks release at exception return rather than eventual collection. Mutation probes challenge completeness qualification, historical-decision authority, reinstatement of the weak-decision fence and cleanup on validation failure. No live provider calls were made.

Verified after these corrections: all 465 backend tests, all 83 browser tests in one full run, architecture, production build, formatting, whitespace and all 139 declared mutation probes passed. The focused execution suite passed all 58 tests. No live provider behavior was tested.

## Execution authority contract baseline, issue 33

The [ownership decision](execution-authority-decision.md) identifies current authority in the application and workspace databases, assigns one intended owner per fact and defines the supported recovery states. The first implementation slice exports versioned admission values and an inactive port. It does not implement atomic admission, change existing workers, migrate storage or make the workspace rebuildable.

Eight contract tests cover explicit ownership, a stable account across brief revisions, exact source/context/model/consent/task fingerprints, immutable task inputs, strict wire versions, parent account/revision equality, bounded task envelopes and finite receipt timestamps. A value can bind a supplied consent reference but cannot establish its authority. The future adapter must verify the source, registered effect requirements and consent independently under its transaction.

Four model-based tests compare real SQLite reservation and progress behavior against a separate specification with two accounts, three runs and two slots per account. All 49 pairs of a seven-action alphabet cover reservation, observation, unknown outcome, stopping and restart ordering. Longer traces reach the shared limit, replay a recorded call at that limit, observe a late result after stop and preserve uncertain work across restart. A separate Python process observes the original uncertain receipt and stopped account. Expected ownership is fixed by the scenario, not computed with the production origin resolver. These checks are a reusable baseline for later adapter/caller changes, not proof of those unimplemented changes.

Six new mutation probes weaken account identity, context binding, consent pairing, parent ownership, wire version and the actual SQLite shared-limit check. The last probe tests the independent oracle against a harmful production change. No browser, schema or live model behavior changes in this slice; new admission transaction, full projection rebuild, mixed writers and migration remain explicit acceptance gates for later slices.

Verified for this slice: all 477 backend tests, architecture, whitespace checks and all 145 declared mutation probes passed. The 12 new focused tests passed. The frontend was unchanged, so its prior browser result was not rerun or counted as new verification. No paid model call was made.

## Immutable model IDs at admission

`ModelConfig` now requires a plain string model ID before checking its existing length and whitespace rules. This rejects mutable list/dictionary IDs through both direct construction and admission payload reconstruction. A regression first reproduced acceptance of the reported list before the fix. Two new tests cover rejection of non-string values and verify that mutating valid source/exported configuration dictionaries cannot change an already-created admission's model settings or fingerprint. A targeted mutation removes the new type check and must be detected. No persisted artifact, approval rule or provider call is changed by this correction.

Verified after the correction: all 479 backend tests, architecture and whitespace checks passed. All 10 admission-contract tests and all seven targeted admission/authority mutation probes passed. The complete mutation portfolio and browser suite were not rerun for this correction. No live model call was made.

## Atomic SQLite planning admission, issue 33

Schema 11 adds immutable verified-request and admission journals alongside the existing tasks and inference records. The conversation module owns pure permission, planning-capacity, intent and binding rules. The SQLite adapter loads independently scoped source messages, exchanges, prior results and saved consent under its write transaction. It cannot use a proposed consent ID or fingerprint as a substitute for that saved decision. Request staging creates no task. Admission commits the run, task plan, explicit conversation owner, planning projection, receipt and audit together. Runtime remains business-agnostic.

The installed workflows are model and fixture planning only. They remain paused at claim and reservation, including after restart or loss of the admission row while its explicit task-format marker remains. There is no activation toggle or new model tool/HTTP/CLI route. Current operation paths continue to run, but cannot duplicate a staged planning revision or use the legacy service to evade the six-request limit. Standalone, child, routing, campaign-copy and native revision source policies remain part of the later cutover.

Twenty-one new SQLite tests cover exact-input replay, changed keys/settings/consent, mode downgrade, foreign scope, independent source and consent integrity, current revision/stop checks, frozen context without current catalogue files, full-envelope budget failure and validation-copy mutation. Two concurrent writers produce one request/admission. Seven insert-boundary faults, a saved-request insertion fault and a precommit fault leave no partial executable work. Real subprocess exits before commit leave no run; exits after commit preserve the original receipt for restart/replay. Scoped receipt reads verify the original task hash and ownership from one read snapshot, without granting current approval.

Migration regressions cover schema-11 rollback/retry and concurrent initialization. Older schema-four/five fixtures explicitly exclude later migrations so their failure tests still exercise the intended historical starting version. Existing tests retain positive legacy-cutoff and review-generation preservation. Thirteen new mutation probes challenge consent integrity, exact request binding, source bytes, paused claim/reservation, missing-journal format fencing, request capacity, legacy duplication, mode, early commits, asset scope, scoped reads and validation-copy isolation. The scope probe constructs a valid foreign bundle and updates all dependent hashes, so hash failure cannot hide a missing scope check.

Scoped saved-request lookup and enumeration preserve staging recovery without browser memory or current guidance files. The crash subprocess reads its intent from the database by scoped request identity; it receives no frozen payload from its parent process. These reads are observational and do not activate work.

Full workspace reconstruction, paid execution through new admissions, positive standalone/descendant admission and restore activation are not established by this slice. No live model calls or real campaign sends were made. The React interface is unchanged.

Verified for this slice: the final clean backend run passed all 500 tests, including the 21 new admission regressions. Architecture and whitespace checks passed. The full mutation portfolio detected all 159 declared mutations, and the 13 new probes passed again with the completed staging-recovery API. No frontend files changed, so the browser suite was not rerun or counted as new verification.

## Mixed planning request-key collisions

Staging now rejects a request key already owned by a legacy plan in the same scoped conversation, even on an earlier revision or before the legacy runtime run exists. It also checks the independently derived runtime request key before saving the immutable request and repeats that check at admission. The legacy service rejects keys already staged through the atomic path across revisions, while historical exact replay remains observational.

Three regressions first reproduced the missing protections, then passed with the fix. They cover complete and partial legacy admission, an occupied runtime key without a planning row, organization isolation, and atomic requests both before and after admission. Rejected staging leaves the request journal, planning counts and runtime records unchanged. A replacement key can still stage and admit the current revision; in the reverse direction, a replacement legacy request can finish through the fake planner. Original frozen records remain unchanged. Three targeted mutation probes remove the legacy-key, runtime-key and reverse-key checks.

Verified after this correction: all 503 backend tests, architecture and whitespace checks passed. All 24 focused admission tests and all 16 targeted atomic-admission mutation probes passed. The full mutation portfolio and browser suite were not rerun for this correction. No paid model calls were made.

## Runtime request reservation during staging

The immutable staged request now reserves its explicit runtime key. All application run insertion uses the shared SQLite helper, which checks that reservation inside the writer's transaction. Ordinary campaign, model-campaign and task callers cannot supply the internal owner binding. The verified admission path supplies the exact saved request identity/fingerprint, and insertion checks the original task plan and persisted binding. Missing or mismatched ownership fails before creating a run. No schema or historical artifact changes are needed.

Three regressions first reproduced the unreserved-key gap, then passed with the guard. They cover `Application.start`, model campaign creation, generic creation with copied exact task inputs, another organization using the same key, a fresh-process writer and successful original admission afterward. A controlled interleaving holds the staging write transaction while a campaign writer waits; after staging commits, the competing writer is rejected and the original admission completes. Private insertion tests reject incorrect owner/fingerprint, substituted task plans and a claimed reservation without its saved request. The staging-failure regression also proves rollback releases the key for ordinary creation. These checks assert no extra runtime/task/audit or approval effects; existing campaign preparation may retain unreferenced immutable input artifacts before a later run-creation rejection.

Three new mutation probes remove reservation enforcement, owner matching and exact plan binding. Runtime core contracts remain business-agnostic, and new-format execution stays paused. No paid model calls were made.

Verified after this correction: all 506 backend tests, architecture and whitespace checks passed. The 27 focused admission tests passed, and the full mutation portfolio detected all 165 declared mutations. No frontend files changed; browser checks were not rerun. Verification used fake providers and no paid model calls.

## Paused admission coverage across workflows

Schema 12 extends the existing request/admission journal to routing, conversation
and standalone campaign preparation, manual descendants, finalized learning
follow-ups and native copy revisions. The server-only request API accepts fixed
source references. The SQLite adapter loads actual scoped sources under the
write lock; workflow composition uses public domain contracts and existing task
factories. No caller-supplied task list, ownership declaration or consent ID can
replace that verification. New model copy uses grounded v3 contexts and the
stable transcript projection. The complete read/submit envelope is checked
without a gateway or inference journal, and final source deadlines are checked
after validation before committing staging or admission.

| Invariant | Executable evidence |
| --- | --- |
| A child retains its verified parent's account and original revision | Conversation and explicit standalone parent/child admissions; missing legacy linkage and foreign parents rejected |
| Source facts remain current at admission | Conversation edits and stop after staging; revoked operator; changed follow-up suppression epochs; expiry during preflight |
| Audience provenance cannot be substituted | Completed saved plan and its actual admitted task; selected manifest/version/checksum on every task; different audience bytes rejected; scoped snapshot/segment/context checks |
| Each request binds one exact operation, generation decision and runtime key | Changed inputs/model settings, competing keys, native reconciliation and ordinary task/campaign writers rejected without runtime effects |
| Review and learning authority remain in their existing modules | Native exact-subject revision receipt consumed without another rejection; parent approval/outcomes not inherited; finalized disjoint proposal uses its accepted parent job/case |
| Admission cannot dispatch before cutover | Claims consume no attempt and direct inference reservation is refused; unchanged call, approval, acceptance and belief counts |
| Replay and recovery observe original work | Concurrent duplicate staging, fresh-process receipt replay and retry after injected precommit failure |
| Forward migration preserves history | Concurrent schema-11 upgrade and interrupted schema-12 table rebuild preserve original request JSON, receipts, tasks, events, execution links and schema-3 cutoff; integrity/foreign-key checks and immutable triggers hold |

The focused coverage uses real SQLite, saved planning/routing/revision and cohort
records, and fake providers only to prepare source fixtures. Seven new mutation
probes remove explicit consent, current ownership, final freshness, dataset
provenance, original routing/revision settings and positive parent proof. Each
is detected by its corresponding boundary test.

The new path remains paused and has no transport or model-tool registration.
Live entry-point conversion, missing-workspace rebuild and activation/restore
gates remain later acceptance work for issue 33. No frontend files changed and
no paid model calls were made.

Verification: all 531 backend tests passed with loopback access for HTTP tests;
architecture and whitespace checks passed; all 172 declared mutations were
detected. The 25 focused workflow-coverage tests also passed after tightening
the registered parent-workflow check. The shared copy-request extraction retains
the original correction identifiers and passes the model-copy and grounding
regressions. Browser checks were not rerun because no frontend or transport
behavior changed.

## Frozen follow-up model settings at admission

Model follow-up task construction now requires the exact configuration recorded
in its saved proposal. The same composer runs before request staging and again
inside the admission transaction. A different model, call allowance, input or
output bound, or price ceiling cannot replace the proposal's frozen settings.
Fixture follow-ups still require no model configuration, and new-format tasks
remain paused.

Two real-SQLite regressions reproduced the missing checks before the fix.
The first varies six configuration fields independently, verifies rejection
before model preflight or any journal/runtime effects, then stages and admits
the original configuration successfully. The second reproduces a request saved
by the prior unchecked writer with its original source fingerprint and consent,
reopens the database and verifies that admission rejects it without changing
the immutable request, creating a run or reserving inference. Two targeted
mutation probes independently remove the comparison at these tested boundaries.

Verification after this correction: all 533 backend tests, architecture and
whitespace checks passed. All five focused learning-admission tests and both
targeted mutation probes passed. The full mutation portfolio and browser suite
were not rerun for this correction. No paid model calls were made.

## Entry-point cutover with execution paused

Schema 13 adds explicit `verified-paused/v1` store selection. Planning, chat
coordination, routing reconciliation, CLI/application campaign creation, manual
children, frozen learning follow-ups and native copy revisions use the public
admission port in selected stores. Command replay uses saved references before
context generation. New ownership is established by domain sources before the
first claim; workspace parent reconstruction and journal witness binding do not
supply new-format execution authority. Unselected stores retain their existing
compatibility behavior. No verified execution activation is implemented.

| Invariant | Evidence in `test_admission_entrypoints.py` |
| --- | --- |
| Selecting a format cannot race past live work | Running tasks, reserved provider calls and partial legacy plan admission block selection; original observation/reconciliation permits a later safe selection |
| Selection is atomic and cannot be downgraded | Transaction failure restores the old format; a competing raw writer waits for the write lock and is rejected after commit; immutable policy triggers and missing-metadata checks hold |
| Cached old writers cannot bypass selection | Direct old-protocol SQL cannot insert an unverified run, claim a task or reserve inference; guards need no connection-specific Python function |
| Admission and runtime are committed together | A deferred foreign key permits verified admission before runtime insertion; injected precommit failure leaves the original staged request and no runtime/admission effects; retry succeeds |
| Replay preserves exact commands and context | A fresh builder reuses the original model context without its factory; changed size, model settings and native revision receipt conflict; original requests stay discoverable |
| Descendants retain their original account and stop lineage | A conversation campaign and model child share owner/account; stopping cancels both; a manual workspace child retains its domain parent after presentation parent metadata changes |
| All new-format execution remains paused | Worker ticks and inference reservations are refused; no attempt, model-call or approval count advances; restored active leases cannot settle a task |
| Caller paths share the same contract | Fixture/model roots, successful saved conversation proposals, native revision and finalized follow-up sources produce verified admissions; fresh CLI workers see the persisted format |
| Chat does not mistake pause for missing credentials | Paused planning and routing show bounded progress without loading a provider key; restarting the coordinator preserves the original run |

The original authority and statistical tests remain applicable. SQL guards are
installed under the migration write lock, including when earlier table rebuilds
must run; they preserve saved request/receipt/task bytes and the legacy cutoff.
Existing provider observation rules remain separate from activation. The new
tests use real SQLite, controlled lock interleavings, subprocesses and fake
providers. They prove paused admission and refusal, not positive verified model
dispatch or a complete activated verified campaign. Projection rebuild and
restore/activation remain later gates for issue 33.

Eleven new mutation probes target raw creation, quiescence, partial planning,
context replay, restored leases, exact revision continuation, workspace ancestry
and the SQL run/claim/reservation barriers.

Verification: all 564 backend tests, 83 existing browser tests and 185 declared
mutation probes passed. Architecture, production frontend build/format and
whitespace checks passed. The 31 new entry-point tests include real loopback
requests and the second-server selection boundary. The offline learning demo
completed with the original finalization receipt replayed unchanged. No paid
model calls were made. The verified path remains paused; passing compatibility
journeys does not claim activated verified execution or projection rebuild.


## Cutover identity reservation and historical observation

Campaign identity is one organization-scoped reservation across standalone,
conversation, manual-descendant and learning-follow-up admissions. The adapter
checks actual frozen campaign IDs before staging and again before committing
admission, including older staged requests whose operation key used a workflow
prefix. New requests share a campaign operation namespace. Copy revisions retain
their separate operation identity because they intentionally revise an existing
campaign. Admission of contradictory historical staging blocks safely; replay
of an already committed receipt remains observation, not current permission.

Native routing keys remain conversation-scoped and distinct from planning keys.
The admission wrapper derives its identity from the routing kind and immutable
action ID. Existing raw-key wrappers replay only when their saved kind and source
references match the original action. Native message, action and runtime keys
are preserved.

Sealed stores recognize exact pre-cutover campaign and planning commands through
a read-only path. It compares original task-plan hashes, supported workflow
plans, scoped frozen references, model settings and planning revision/mode.
Historical planning replay does not require the conversation still to have that
revision. Optional frozen continuation context, including messages when supplied,
must match. Replay does not rebuild current guidance, write contexts, reserve
inference, attach ownership or create an admission. It returns the original run,
which remains paused and uncertified. This compatibility guarantee concerns
saved effect-bound inputs; legacy records do not contain every original CLI flag.

The real-SQLite regression portfolio in `test_cutover_review_regressions.py`
covers both cross-kind staging orders, concurrent commands, incompatible pre-fix
staging at admission, unchanged pre-fix operation keys, organization isolation,
a routing/plan key collision, two conversations sharing a routing key, original
raw-wrapper replay, exact fixture/model campaign replay after reopening, and
historical fixture/model planning replay after edits. Full durable-row comparisons
include task/event/admission/accounting, audience and context/memory tables.
Six targeted mutation checks remove the staging/admission campaign fences,
routing scope, exact legacy task-plan comparison, planning revision check and
frozen-context comparison independently.

Verification after these corrections: all 577 backend tests, including the 13
new regression tests, passed. All 191 declared mutation checks, architecture and
whitespace checks passed. The backend suite used loopback access for its HTTP
tests. The browser suite was not rerun because frontend and transport code did
not change in this correction. No live or paid model calls were made.


## Legacy routing and copy-revision observation after cutover

The sealed admission path also recognizes existing native routing and
copy-revision runs before attempting a new verified admission. Routing compares
the supplied action with its scoped saved source, excluding only mutable
confirmation state, then reconstructs the original task. Revision replay checks
the complete native receipt, reads and validates its existing content-addressed
context, and reconstructs both original tasks. The existing legacy reader checks
the runtime hash and compares the full ordered task plan with this independently
reconstructed source plan. Runtime integrity by itself is insufficient.

These observations return the original run without writing context, staging a
request, attaching ownership, recording a new approval/rejection or reserving
inference. They require the original model configuration. Current brief edits,
publication and later operator revocation do not block inspection of the
original run; they still govern any new effect. No new-format admission
is activated, and records already containing verified admission metadata remain
on the verified path.

Six real-SQLite tests in `test_legacy_action_replay.py` cover queued routing and
revision replay in separate processes, completed routing after a later brief,
completed revision after publication and operator revocation, cross-organization
requests, altered native sources and model settings, and substituted task inputs
with a recomputed internally consistent runtime hash. Full database row
comparisons verify observation only. Five new mutation probes target both replay
returns, both native-source checks and the revision task-plan comparison.

Verification: all 583 backend tests and all 196 declared mutation probes passed,
including the six new real-database replay tests and five new mutations.
Architecture and whitespace checks passed. The backend suite used local
loopback access for its HTTP tests. No frontend or transport code changed, so
the browser suite was not rerun for this correction. No live or paid model calls
were made. Verified execution remains paused.


## Recovery of source commands staged before entrypoint metadata

The admission facade recognizes the field-absent storage-slice envelope only for
routing and copy-revision commands. Their single source reference must equal
both the supplied entrypoint and the caller's source references. Workflow kind,
explicit Boolean generation permission and exact frozen model settings remain
bound. A present but null entrypoint is not this older format. Campaign commands
cannot infer missing creation arguments from source references. Other stored
workflow requests retain the original storage-port admission path using their
exact saved intent; this compatibility path does not invent absent CLI inputs.

The original scoped source operation can be found even when the storage-slice
request key differs from the native action or revision key. The adapter checks
the saved intent, source identity and canonical references before returning that
key. Existing native-spelled wrappers retain their keys; new routing and revision
wrappers use the same source-based namespace. Native sources and runtime request
keys are unchanged. Recovery passes the original field-absent envelope back to
the storage port, preserving every saved request byte and its fingerprint.

Unadmitted requests still recheck current source and ownership in the admission
transaction, so a later brief edit blocks stale work. Already-admitted requests
observe their original receipt after later edits. Both paths keep verified
execution paused and reserve no inference.

Seven real-SQLite tests in `test_pre_entrypoint_recovery.py` cover fresh-process
staged recovery, cached receipt replay, a separately keyed storage admission,
source-read organization isolation, changed references/settings/permission,
null metadata, unsupported campaign inference, stale unadmitted source and the
equivalent copy-revision path. Five mutation probes target preservation of the
old envelope, discovery of the original key, source-read scope and both saved
and caller reference comparisons.

Verification: all 590 backend tests, including the seven new recovery tests,
and all 201 declared mutation probes passed. Architecture and whitespace checks
passed. The backend suite used loopback access for its HTTP tests. No frontend
or transport code changed, so the browser suite was not rerun. No live or paid
model calls were made. Verified execution remains paused.


## Conversation-scoped native planning requests

Verified planning now derives an admission key from organization, conversation
and native request ID. Mode and revision remain bound inputs rather than key
components, so changing them cannot allocate another planning request. Native
request IDs remain unchanged in frozen tasks, runtime request hashes and the
conversation planning journal. Admission identity and consent use the separate
scoped key. A new optional native-request field records this relationship in the
staging envelope without a schema migration.

A scoped lookup finds existing staging or admission before freezing context.
Earlier raw-key requests retain their original key, serialized envelope,
fingerprint and task plan. Their cached receipts remain observational. New
requests in another conversation may use the same native key without adopting
that earlier work. Partially staged new requests recover their original context
and identity after reopening or process restart.

Planning capacity checks distinguish native command identity from admission
identity. The existing six-request limit counts revisions once across native
planning and staged records. A native key cannot be reused for another revision
or wrapped in another admission to evade its reservation. The compatibility
writer also checks the native key inside its transaction, including when the
store has not selected cutover yet. Runtime reservation and paused-execution
checks remain unchanged.

Nine real-SQLite tests in `test_planning_request_scope.py` cover shared fixture
and model keys across two conversations, independent consent, native task and
journal IDs, raw staging compatibility, partial admission recovery, concurrent
commands, changed mode/configuration/context, mixed old/new writers, the six
request bound, organization/campaign isolation and fresh-process replay. Eight
new mutation probes target key scope, original staging/envelope recovery, native
task/journal identities, both scoped read predicates and compatibility-writer
native reservation. Existing reverse-key mutation probes follow the updated
SQL predicate.

Verification: all 599 backend tests, including the nine new scope/recovery
regressions, and all 209 declared mutation probes passed. Architecture and
whitespace checks passed. The backend suite used local loopback access for its
HTTP tests. No frontend or transport code changed, so the browser suite was not
rerun for this correction. No live or paid model calls were made. Verified
execution remains paused.


## Application-owned workspace intent, issue 33 phase 4a

Schema 14 separates immutable preparation/environment intent from progress and
navigation projection. New selected work reads mode, routing, initial time,
clock advancement, creation-command mappings and domain links from application
storage. Scope comes from a server-owned catalogue with immutable store identity,
not a session payload. Preparation inputs include the original planning context,
model configuration and copy consent before plan admission. They cannot be
replaced by progress or copied from the old control-store journal.

`test_workspace_authority.py` tests poisoned projection fields, missing
`workspace.sqlite`, a fresh Python process, interruption after environment commit
and after task admission, original preparation recovery without rebuilding
context, and exact conversation draft replay after projection loss. All owned
runs remain paused with zero worker dispatch. Tests reject foreign run links,
changed clock/storage fields, unrelated creation-command aliases, replaced or
missing stores, and symlinks outside the root. A clock read under an existing
write transaction proves that known-store access does not acquire a second
migration lock.

A deliberately seeded set of committed review/job/cohort facts isolates the
simulation clock boundary without enabling paused work. It proves that clock
advance and command admission roll back together, exact retries do not change
state, changed-input retries cannot advance time, disabled operators cannot
advance time, and missing/non-finite cohort windows fail before mutation. A
manual child inherits the owned parent store, organization, clock and admitted
parent run without any workspace session row. These are boundary fixtures, not
an end-to-end verified approval/acceptance journey.

Migration checks inject failure after the v14 DDL but before identity creation:
tables, version and identity roll back together, while the legacy cutoff stays
unchanged. Reopen retains the original store identity. Current-schema missing
identity fails rather than silently assigning a new one. Existing concurrent
initialization and whole-chain rollback tests now include schema 14.

Targeted mutation probes weaken projection precedence, original command input
binding, preparation source selection, store identity/root confinement, clock
command atomicity, operator checks, link integrity, immutable progress fields,
planner-run binding and read-only store opening. The previous workspace ancestry
reconstruction probe is replaced by owned-parent and projection-boundary
coverage: new selected work no longer enters that reconstruction path.

Unsealed compatibility operation remains covered by the existing backend and
browser journeys. Full projection rebuild, legacy migration, stale-backup
consistency and activation of verified execution remain later acceptance gates.
No live model behavior is claimed by this offline pass.


Verification for this slice: `make test` passed 624 backend tests;
`make arch-check` passed; `make mutation-check` detected 223/223 declared
mutations; `make interface-check` passed the production build, formatting and
83 browser tests. The focused workspace authority file passed all 23 tests,
including the final organization-scope assertion. Fifteen new mutation probes
replace one retired reconstruction-path probe, for a net increase of fourteen.
No paid or live provider call was made.

## Exact environment/run binding and projection isolation

The environment/run link now verifies more than a valid admission and matching
runtime key. Inside the same SQLite transaction it reloads the immutable
creation command, original environment, frozen admission command/source and
verified parent environment. Workflow policy checks mode and model permission,
source kind and identity, exact brief, parent run/ownership, source references
and the original workspace command parameters. It does not rebuild model inputs,
refresh historical evidence or enroll legacy work. Reads repeat the integrity
check; an already inconsistent link is blocked, not rewritten.

| Confirmed invariant | Independent falsification | Boundary |
| --- | --- | --- |
| A runtime key alone cannot establish environment intent | Interrupt fixture environment creation, independently admit a valid model run with the same key, reject both direct linking and preparation after reopening | Real SQLite; all new-format runs remain paused |
| Valid commands cannot substitute different intent | Valid same-mode runs change size, seed, budget or date; a model environment receives fixture work; conversation/manual-child environments receive standalone work; a child receives another valid parent | No provider dispatch or alteration of the admitted candidate |
| Exact historical work remains readable | Original model-run recovery, clock advancement, conversation replay, process recovery and frozen fixture/model follow-up contracts continue to pass | Later activation and legacy migration remain deferred |
| Disposable corruption cannot hide owned records | Malformed JSON, wrong identity, incomplete objects, invalid timestamps and malformed nested plans coexist with owned state; listing, conversation and routing context remain readable after reopening | Malformed projection rows are ignored in selected mode; well-formed legacy rows remain visible |

The two causal clusters are admission identity/source/consent at link commit,
and projection corruption/observability during reads. The bounded tests use
valid competing admissions rather than trusting the new matcher to create
expected results. Projection tests assert original owned values and unchanged
application records. New mutations weaken original-command matching, substitute
the candidate's parent for the environment's parent, and remove corruption and
schema isolation. The existing link mutation now removes the complete semantic
check, because the former request-ID check is also covered by that policy.

Verification of these review corrections: `make test` passed 632 backend tests,
`make arch-check` passed, and `make mutation-check` detected 227/227 declared
mutations. The final focused authority file passed 31 tests, including the
additional nested-JSON and legacy-visibility assertions; both projection
mutations were rerun successfully after the parser-error refinement. No frontend
files changed, so the earlier 83-test browser evidence was not rerun for these
corrections. No live provider call was made.

## Audience identity behind a claimed creation command

The reported bypass was reproduced before the fix: eight valid admissions
substituted audience size, seed, date or record content while claiming the
workspace command, in both fixture and model mode. Each could link to the
original environment intent despite the contradictory population.

Generated workspace audiences now bind the content identity independently
derived from the environment's organization, fixed 1,000-record/seed-42 v1
recipe and original UTC simulation date. Bootstrap supplies the deterministic
synthetic adapter's identity function to workflow policy. The link transaction
compares that expected identity with both the frozen source and admitted task.
Claimed command fields and candidate snapshot metadata cannot supply the oracle.
The check covers root/manual-descendant campaigns and unsourced conversation
campaigns. The original synthetic-segmentation/v1 recipe must remain stable
when introducing a new generator version.

This recomputes only the deterministic synthetic identity, with a bounded
128-entry cache of immutable hashes. It does not rebuild model context, invoke
inference, read a live audience feed or change stored snapshots. Selected
datasets retain their independently confirmed version/manifest provenance;
learning follow-ups retain their frozen proposal population. Their audiences
are not replaced with the 1,000-record synthetic recipe.

Tests admit valid competing snapshots with a dishonest but exact entrypoint:
20 records, a different seed, a different date, and altered content with the
expected count and metadata. Link rejection leaves all application rows
unchanged, the environment unlinked and provider calls absent. A separate
unsourced-conversation test covers its implied generation recipe. A confirmed
100-record dataset and existing fixture/model follow-up contracts demonstrate
that legitimate overrides keep their provenance. Three mutations restore
self-certification, omit the conversation check or apply the synthetic recipe
to selected datasets.

Verification of the audience correction: the full `make test` run passed 635
tests. The latest focused authority run passed 35 tests, including the additional
reverse counterexample added while strengthening the command mutation: correct
audience bytes cannot excuse an incorrect saved command. `make arch-check`
passed and the complete mutation run detected 230/230 declared mutations.
No frontend files changed and no live provider call was made.


## Checkpoint recovery polling in CI

PR 38's first CI run passed backend, architecture and mutation checks on all
four Python versions. Its browser job failed waiting for Review campaign after
restoring a disabled checkpoint operator. A conversation read can capture its
campaign mapping before recovery updates the case, then read newer preparation
progress after recovery clears the blocker. The former client saw no active
preparation or blocker and stopped polling, leaving the completed draft hidden.

The client keeps its existing read-only polling active while a campaign has
reached `waiting` or `succeeded`, still has no review-case ID, and its preparation
reports `review_ready` for the same revision and campaign run. Explicit
checkpoint-recovery blockers and a pending-recovery hint backed by the exact
saved stop receipt also keep polling active. A missing case alone does not
imply automatic recovery. Readiness, approval, simulated
acceptance and inference remain controlled by the existing backend. No retry
setting or timeout was increased.

The existing browser test now delivers this single intermediate response from
a real recovery run deterministically. It failed before the client change and
passed ten repetitions afterward. It still asserts unchanged model-call usage,
an unapproved exact draft and no handoff after recovery. The incomplete read is
injected only into the response; the actual server performs checkpoint recovery
and the next poll retrieves the saved case.

A real SQLite probe also pauses the conversation read immediately after its
campaign snapshot, restores the checkpoint, and resumes the read. It produces
`case_id: null`, `generation: waiting`, `preparation: review_ready`, no blocker
and zero pending receipts while the saved case already exists. This confirms
that the browser's injected intermediate packet corresponds to a reachable
backend interleaving.

Local verification: `make interface-check` passed the production build,
formatting and all 83 browser tests. The forced-race checkpoint test passed ten
consecutive repetitions. Architecture and diff checks passed. Backend source
and authority rules are unchanged; CI reruns the full Python matrix on the
published fix. No paid model requests were made.

A follow-up review found that the original missing-case condition also polled
ordinary blocked preparations indefinitely. If case storage fails before a
stop receipt exists, the coordinator saves `blocked` and does not automatically
retry when storage returns. The new browser regression creates that real SQLite
state, restores storage before serving the interface, and observes three polling
intervals without another conversation read. It also checks that progress stays
blocked, no review appears and model usage does not increase. The regression
failed against the broad condition before the matching-ready-progress check was
added. The existing forced-race recovery test covers the transition that must
continue polling.

Follow-up verification: both checkpoint browser cases passed five consecutive
repetitions each. `make interface-check` passed the production build, formatting
and all 84 browser tests. `make test` passed all 636 backend tests;
`make arch-check` and `git diff --check` passed. No live provider calls were made.

The next CI run exposed a second reachable read schedule. A conversation read
captures its campaign mapping and cancelled preparation row, then checkpoint
recovery creates the case, updates the row and clears the blocker before the
read obtains generation state. The response has neither ready progress nor a
blocker, so matching only `review_ready` still stops polling too early. CI did
not retain its trace; a real SQLite probe and a browser test independently
reproduce this schedule and the same five-second missing-review failure.

The backend now projects `checkpoint_recovery_pending` only for a missing case
whose exact organization/run belongs to this conversation's immutable stop
receipt. That receipt is also the executor's recovery input. It remains
discoverable after the blocker clears, and the hint clears when the case mapping
is read. No new recovery task, inference, approval or acceptance is admitted by
this read. An unrelated checkpoint's stop receipt is insufficient.

The browser test holds recovery until an actual progress read has captured the
old row, then restores the real case during that read. Its response is not
rewritten. This complements the earlier injected ready-progress packet and the
ordinary blocked/no-retry case. All three browser cases passed five repetitions
each. Two declared mutations remove the recovery hint or falsely advertise all
missing cases as recoverable. CI now retains failed browser traces, screenshots
and error context for seven days.

Final local verification: all 637 backend tests, all 85 browser tests,
232/232 declared mutations, the production build, formatting, architecture and
diff checks passed. The three targeted browser cases passed 15/15 repetitions.
No live provider calls were made.

## Offline workspace projection rebuild, issue 33 phase 4b

`tests/test_workspace_projection.py` exercises 21 recovery scenarios against
real SQLite. The oracle compares independent snapshots of all application
tables, not the projection adapter's expected rows. A missing projection is
inspected without being created, then rebuilt in a fresh CLI process. Owned
identity, original request lookup, fixture/model mode, simulation clock,
accepted/cohort facts, stopped preparation and unknown provider observations
retain their original meaning. Verified workers remain paused after rebuild.

The mixed-history fixture retains opaque legacy consent, original command rows,
an existing journal identity and unrelated binary data. Conflicting legacy keys,
unreadable files, unsupported layouts and file aliases fail without discarding
history. Missing or replaced application stores are not recreated or enrolled.
An unsealed store is not implicitly selected for verified admission.

Fault tests exit the process after projection writes but before commit, lose the
acknowledgement after commit, change source clock facts before commit and insert
a legacy row after inspection. The crash forces SQLite cache spill so recovery
must handle a real hot rollback journal, not only unflushed process memory.
Query-only projection inspection permits SQLite's own rollback under the root
lock; authoritative source connections remain strictly read-only. These tests
check rollback or exact replay without a new
domain effect. Source-integrity and stale-plan errors release the root lock at
exception return, without garbage collection. A location-only interruption is
reported without inventing a campaign environment.

The diagnostic fixture distinguishes an owned run/revision from legacy keys in
the same organization. Only positively owned cache entries are discarded, so
restored progress is read from application facts rather than stale blocker text.
Nine targeted mutation cases cover SQLite crash recovery, the root lock, source identity, control and
source freshness, atomic commit, legacy preservation and diagnostic ownership.
The existing nested-migration mutation now targets the read-only reader's
equivalent branch; its protected invariant is unchanged.

These tests do not demonstrate executable verified campaigns, legacy
certification, arbitrary partial-backup recovery or absence of post-checkpoint
spend. Source fingerprints are inspection bindings. The migration, supported
restore procedure and activation journey remain phase-5 acceptance work.

Verification: `make test` passed all 658 backend tests, `make interface-check`
passed the production build, formatting and all 85 browser tests, and
`make mutation-check` detected 241/241 declared mutations, including all nine
projection cases. The 21 focused recovery scenarios passed with forced SQLite
cache spill in the pre-commit crash case. Architecture and diff checks passed.
No live provider calls were made.

## Legacy migration inventory, issue 33 phase 5a

The offline `acquisition.legacy_migration inspect` command produces a
`legacy-migration-plan/v1` proposal. All source connections are read-only, including
historical schemas. It never constructs a workspace, selects a store policy,
enrolls a legacy run, changes an allowance, dispatches inference or records approval.
The only writable coordination object is the existing root's `server.lock`.

| Invariant | Independent evidence | Limit |
| --- | --- | --- |
| Inspection conserves history | Full SQL-table and file-byte comparisons before/after repeated inspection and a fresh-process CLI; opaque binary tables, malformed sessions, preparation inputs and original receipts remain unchanged | SQLite may use shared memory for read locks; no cold-backup claim |
| Permission comes from its recorded source | Native planner/routing/revision task matching; an internally consistent replacement plan conflicts with the native admission; routing permission stays routing-only | Unsupported old model-copy consent proofs remain incomplete |
| Ownership needs positive scoped facts | Native conversation proposal and domain descendant fixtures, missing-parent/cycle/conflicting-owner checks, and contradictory account-index tests | No absent-parent inference or independence certification |
| A journal witness is not completeness | Lost, recreated and stale populated journals; matching identity explicitly reports unproven completeness; historical independence receipt remains non-authoritative | Arbitrary partial restore remains unsupported |
| Uncertainty survives inspection | Fake-provider network failure and interrupted reservation retain uncertain status, recorded call count and unknown remaining allowance; a definitive rejection remains a historical observation | No live billing verification, provider retry or account reset |
| Owned projections cannot replace authority | Corrupt owned session ignored in favor of registered environment/preparation evidence; wrong source identity, hardlink alias and escaping paths cannot supply support | No repair is performed |
| Partial admissions stay inspectable | Native admission without a runtime write and a staged verified request appear as pending, without finishing either admission | Inspection performs no migration |
| Recovery does not happen inside inspection | Old/future schemas, missing/unreadable stores and a forced cache-spill hot journal are retained; changed source invalidates the plan; locks release after failure | SQLite recovery must be handled separately |
| Report is metadata, not authority | Fresh-process output excludes prompts, context and response bodies; arbitrary preparation fields are filtered; apply/activate commands are rejected; every executable/migration/activation flag remains false | Historical approvals still require their normal current-authority checks |

`tests/test_legacy_inventory.py` supplies 27 focused scenarios using real SQLite,
fresh processes, source fingerprints and fake providers. Fourteen targeted
mutation cases remove pause/ownership/integrity/uncertainty/redaction and source
checks, accidentally initialize an old schema, or hide a partial admission.
Verification: `make test` passed all 685 backend tests with loopback access,
including all 27 inventory scenarios. `make arch-check` passed, and
`make mutation-check` detected 255/255 declared mutations, including all 14 new
inventory cases. Diff checks passed. No frontend files changed and no live
provider calls were made. Transactional migration, supported restore and verified
execution activation remain later acceptance gates.

### Review: complete environment validation and typed generation choices

The inventory now delegates environment reads to the existing authoritative
workspace reader through a bootstrap-wired callback. It uses the inventory's
pinned read-only transaction and checks the exact admitted run/creation inputs,
review case, learning cohort, original clock and parent before classifying an
environment as supported. Projection records depend on that environment even
when validation fails, so a conflict cannot leave a rebuild recommendation.
The normal reader and effectful workflows are unchanged.

Six additional real-SQLite tests reproduce missing, foreign and wrong-run review
cases; missing and wrong-case cohorts; backward clocks and incompatible clock
modes; valid paused runs with the same runtime key but different mode or audience;
and nonboolean generation choices. Required and optional choices are tested with
strings, objects, lists, integers and null. CLI output cannot contain the injected
credential-shaped marker; valid optional booleans remain exact. Full SQL and file
byte comparisons prove failed inspections leave the source records intact, and
an unrelated valid environment remains supported. The fault-injection cases
failed against the prior implementation and pass with the shared reader and
optional type check.

Three targeted mutation cases cover bypassing that reader, losing projection
conflict propagation and omitting the optional choice type check.

Review verification: `make test` passed all 691 backend tests with loopback
access, including all 33 inventory scenarios. `make arch-check` and
`git diff --check` passed. The targeted mutation run detected all 17/17 inventory
mutations, including the three new cases. No live provider calls were made;
inspection remains read-only and verified execution remains paused.

### Review: validate the complete legacy session metadata projection

Legacy session parsing now validates every exported payload field before
assigning organization, metadata or discovery/ownership hints. It uses the
public bounded identifier and UTC-time contracts, closed mode/clock-mode/storage
enums, nullable link identifiers, and typed conversation-hint identifiers and
revision. Missing historical clock mode is not inferred. Invalid journal keys
use fingerprint locators in both record and evidence references, while internal
record identities still bind the original key. Invalid values never enter the
report or CLI diagnostics, and malformed hints cannot taint a valid original run.

Four real-SQLite regressions cover clock-mode corruption, malformed required and
optional identifiers, invalid nested conversation hints, and valid metadata with
present or absent clock modes. They include credential-shaped strings, long
strings, objects, lists and numeric values, fresh-process CLI output, continued
visibility of an unrelated valid run, and exact SQL/file-byte preservation. The
fault-injection cases reproduced the prior implementation's unsafe reporting.
Five targeted mutations cover enum validation, required/optional identifier
validation, opaque-key rendering and conversation-hint validation.

Review verification: `make test` passed all 695 backend tests with loopback
access, including all 37 inventory scenarios. Architecture and diff checks
passed. The targeted mutation run detected all 22/22 inventory mutations,
including the five new session cases. No live provider calls were made.
Inspection remains read-only and verified execution remains paused.

### Review: native reference formats before public display

The general bounded-identity contract accepts realistic provider keys and is
insufficient for public legacy metadata. The inventory now applies field-specific
native v1 identifier formats to session keys, organizations and optional run,
case, cohort and parent references. Other strings become opaque fingerprint
locators with explicit unverified-reference reasons. Internal lookup and record
identities retain the original scoped inputs; no historical source is rewritten.
Conversation/brief hints outside their native formats cannot affect another
run's ownership classification. Native shape is a display rule, not proof of
ancestry, consent, approval or migration readiness.

Two additional real-SQLite regressions cover a realistic 73-character key-shaped
marker that explicitly passes the general identity validator, and historical
aliases that must stay opaque. They cover every
exported identifier position and both conversation-hint identifiers, fresh-process
CLI output, source preservation, native-format passthrough and opaque historical
aliases. Both tests failed against the prior implementation. Two new targeted
mutations cover bypassing reference redaction and trusting an unverified hint;
the existing opaque-key mutation now targets the shared public-reference rule.

Review verification: `make test` passed all 697 backend tests with loopback
access, including all 39 inventory scenarios. Architecture and diff checks
passed. The targeted mutation run detected all 24/24 inventory mutations,
including both new cases. No live provider calls were made. Inspection remains
read-only, original records are preserved and verified execution remains paused.

### Review of caller-supplied request references

The inventory fingerprints request IDs in both preparation journals, runtime
metadata, pending admission locators and request-keyed evidence. Standalone
ownership scopes use the same rule because campaign IDs can come from the caller.
Run matching by the original request key uses the corresponding fingerprint
within the original store and organization.

Real SQLite tests submit credential-shaped IDs through preparation, planning,
runtime and copy revision APIs. The assertions cover CLI output, partial
admissions, staged requests, standalone scope aliases and source preservation.
The existing journal-parent test exercises request-key matching without a run ID.

The full backend suite passed all 700 tests, including 42 inventory tests.
Architecture and diff checks passed. The targeted mutation run detected all
28 inventory mutations, including the four new request reference cases.

### Review of the inventory report boundary

The normal campaign API accepts a credential-shaped organization identifier.
Previously the inventory forwarded it from the same source dictionary used for
matching. Organization values appeared in records, evidence and resolved owners.
The earlier field-level fixes covered individual paths through that dictionary.

The report now selects fields in one projection after classification. It applies
one organization fingerprint rule to all three positions, retains the fixed
local label and checks the shapes of the metadata it emits. This supersedes the
earlier fingerprint-based matching approach. The classifier uses the original
values and scoped parent links.

The integration regression creates two organizations with credential-shaped
identifiers through the campaign API, reuses a request key across those scopes
and checks a descendant that inherits the first owner's scope. It verifies the
whole CLI output, consistent fingerprints, separate organizations and preserved
source rows. A separate projection test introduces extra source fields and
unsupported metadata strings to exercise the closed display surface.

All 702 backend tests passed, including 44 inventory tests. Architecture and
diff checks passed. The targeted run detected all 30 inventory mutations,
including the two new checks for organization references and report fields.

## Transactional legacy ownership migration, issue 33 phase 5b

Explicit apply records positively evidenced, already-attributed legacy runs
in a sealed schema-14 conversation store with a matching pre-history journal
association. The immutable batch receipt and per-run bindings commit together.
The other inspected databases are locked while SQLite commits the target
transaction.

| Invariant | Executable evidence |
| --- | --- |
| The reviewed plan binds current evidence at the effect boundary | Change the journal after inspection and reject the old ID. Competing writers to the journal and application database cannot obtain write locks during save and can obtain them after completion. |
| Migration adds only proven scope | A mixed store includes a fixture campaign with a native planner, a new paused admission, an unowned CLI run and recorded model usage. A separate case substitutes a different journal parent while retaining the original domain parent. |
| Unknown or missing authority stays visible | Conflicting inputs, uncertain inference, missing accounts and unbound or missing journals stay unresolved. Recreating a journal or restoring a stale copy with the same identity preserves quarantine and unknown allowance through apply and restart. |
| History survives atomic apply and replay | Compare all pre-existing tables, including task inputs, reviews, simulated acceptance, finalized learning and original call records. Interrupt a fresh process after writes and before commit, compare all rows, then retry and replay from fresh processes. |
| Receipt lookup is read-only | Query an uncommitted plan through the receipt command and compare all rows. After a commit, remove the source journal and recover the exact receipt from a fresh process without recreating the journal or acquiring its workspace lock. |
| Migration stays paused and durable | Check zero worker ticks, one retained historical fake-provider call, preserved stop state and rejection of update, delete and replace against committed migration records. |

The test scope uses synthetic data and a fake provider. Historical ownership
bindings are separate from new-format admissions. Supported backup and restore,
explicit activation and the full offline verified journey remain acceptance gates.

Verification passed with 714 backend tests, the architecture check and 69
targeted migration, inventory and recovery mutations.

## Cutover preserves legacy quarantine

Explicit verified selection skips origin recovery and seals the store under
the same SQLite write lock. A rejected cutover rolls back without clearing
quarantine. Existing schema-v10 and later markers remain intact. Cutover of a
pre-v10 store with recorded runs stops before schema changes and requires
separate ancestry reconciliation. Ordinary unsealed opens retain their existing
recovery behavior. A new or existing sandbox store uses the same boundary.
An add-only pass restores missing quarantine for weak historical independence
receipts before selection, and also repairs them on sealed-store startup. It
does not infer ownership, clear markers or rewrite old receipts.

Real SQLite tests cover both CLI forms, the workspace, a direct builder, an
existing standalone sandbox, a competing opener, failed cutovers and rejected
pre-v10 cutovers. They check weak and valid receipts across organizations,
rollback, repeated selection, unknown remaining allowance, preserved quarantine
and legacy cutoff, and paused execution after reopening. Mutation probes remove
the cutover, sandbox and weak-receipt quarantine fences.

## Legacy execution account recovery

A real SQLite regression retains the original run link and stop receipt after
deleting the account row. It exercises workspace reopening, exact stop receipt
replay, inspection and apply. It repeats the check after inserting a
default-valued replacement row. The recorded stop stays visible, remaining
allowance is unknown, and apply records only the separate healthy account's
binding.

Verification passed with 722 backend tests, 85 browser tests, the architecture
check and both targeted account recovery mutations.

The missing-account check also covers loss of the execution index. The
regressions retain an unstopped planning run with one recorded fake-provider
call, an original task with an orphaned call receipt, and a routing run with no
planning history. Reopening keeps the allowance unknown and a later model
request fails before dispatch. A first run can still initialize its account
in the admission transaction. The schema-nine backfill regression covers
stores that predate execution accounting.

Verification passed with 724 backend tests, the architecture check and both
targeted native-history mutations.

A further real-SQLite regression removes the account, run index, run and task
while retaining the planning admission and original call receipt. Reopening,
replaying the original request and submitting a later brief leave the allowance
unknown and the original provider call count intact. A fresh account in the
same organization stays unresolved. A different organization can initialize
its own allowance.

Verification passed with 725 backend tests, the architecture check and three
targeted account-history mutations.

The planning-history regression also retains a task with matching identifiers
after removing its ownership inputs and losing the account, index, run and
planning admission. The receipt keeps the allowance unknown and the provider
call count stays fixed. An intact original runtime plan with valid scoped
ownership still permits account initialization for a separate conversation.

Verification passed with 725 backend tests, the architecture check and three
targeted account-history mutations.

The existing-account regression removes only the execution link for a run
with a recorded call. After reopening, the allowance and cost coverage stay
incomplete. Previously queued work cannot reserve another call and a later
planning request cannot be admitted. Substituting another valid account for
the original owner blocks both accounts. Restoring the exact link restores
the original count. The descendant regression also removes the links from
the campaign organization. The direct reader reports an unknown allowance
until workspace recovery restores the links from the saved ancestry. The
companion mutation removes the existing-account receipt fence.
