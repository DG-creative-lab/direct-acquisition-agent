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
| Ineligible records never enter mailing | Literal 18-record fixture, ordered exclusions, duplicate/suppressed businesses and disjoint counts | Synthetic source completeness and supplied metadata only |
| Population and integer budget reconcile | Hand-written population plus 3 seeds × 3 sizes × 4 budgets = 36 cases | Bounded examples, not general load/marketing effectiveness |
| Controls share selected enrollment | Scores require assignments from the same top-score cohort; controls absent from mailing | Small groups may lack controls; selected cohort is not the whole market |
| Organization scope persists | Wrong-scope reads/writes, acknowledgement, cancellation, exports, review and learning rejected | Trusted local identity, not hosted authentication |
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
| Workspace commands recover partial success | Domain commit before metadata loss, request identity before clock advance and current-state receipt observation | Separate stores, no distributed transaction |
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

| Continuous preparation reuses exact saved work | Duplicate admission, concurrent identical admission, lost coordinator write, lost draft-status write and real-process queued recovery | One local executor; no multi-node scheduling claim |
| Conversation edits stop continuation | Reads and appends during an in-flight planner, edit before a repair call and edit during copy; no later copy/draft or release | An already dispatched provider request cannot be withdrawn |
| Preparation progress grants no authority | One submitted model brief reaches a valid unapproved candidate; approval invalidates after a later message | Synthetic campaigns and simulated delivery only |
| Interrupted work cannot be presented as ordinary failure | Unknown network outcome and interrupted planner/copy reservation remain uncertain on restart, with no additional provider call | No provider-side reconciliation is implemented |
| Progress is a read-only projection | Guarded 202 admission leaves a queued task without calling the worker; browser reload reaches review with one admission and no plan/draft/approve/handoff POST | Background execution requires the local server; direct legacy endpoints remain synchronous |

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

The mutation command creates temporary source copies and weakens 49 selected enforcement points, including leases, reservations, uncertain-call fencing, retired-workflow admission, timestamp validation, migration locking, review expiry/epochs, cohort maturity/completeness, atomic finalization, snapshot memory, Origin checks, exact-subject binding, planning budget provenance, current-revision projection, conversation scope, targeted execution, stale-budget correction handling and relative-budget recognition. Detection establishes that the targeted test distinguishes that weakened behavior. It is not a general mutation score. Frontend regressions are reported separately from these probes.

The analytic Beta(1,19) quantiles provide an independent check on sampled prior intervals. Count tests verify exact trials/successes and sequential/batch equivalence. This checks calculation behavior; it does not calibrate the prior or turn simulated results into real causal evidence.

## Recorded live model evidence

The [grounding reference](product-grounding.md) records a dated GPT-OSS-120B run and a small eight-variant screening regression. The rubric and regression examples were developed together. Their match rate is not held-out accuracy, and the recorded run is not a fresh claim about current provider pricing, availability or output quality. The exported example remains unreviewed.

## Remaining gaps

There is no asserted line/branch coverage percentage or overall correctness percentage. Selected fault positions and concurrency schedules leave untested interleavings. General semantic claim detection, real data completeness, marketing impact, production authentication, external agency effects, multi-host throughput, disk-full/power-loss behavior, backup restoration, real outcome corrections and repeated-exposure attribution remain outside the demonstrated evidence.

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

Browser journeys cover a lost committed stop response, receipt completion after cancellation, fresh audience confirmation for a new brief, unchanged usage across reload, and 320px/390px overflow assertions. Desktop and mobile screenshots were inspected. Mutation probes weaken shared capacity, original run binding, stop fences, run/task cancellation, stop-receipt persistence, approval preservation and replay at capacity. No paid model calls were made.

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
