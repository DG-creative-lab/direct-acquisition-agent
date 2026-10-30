# Validation and limits

The product is tested at pure-rule, persistence, process, HTTP and browser boundaries. This guide describes the current portfolio rather than the chronology of its construction. The portfolio includes frontend regressions, 41 selected mutation probes and backend tests covering the campaign lifecycle, conversational planning and synthetic preparation. Test counts do not measure overall completeness or production readiness.

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

The mutation command creates temporary source copies and weakens 47 selected enforcement points, including leases, reservations, uncertain-call fencing, retired-workflow admission, timestamp validation, migration locking, review expiry/epochs, cohort maturity/completeness, atomic finalization, snapshot memory, Origin checks, exact-subject binding, planning budget provenance, current-revision projection, conversation scope, targeted execution, stale-budget correction handling and relative-budget recognition. Detection establishes that the targeted test distinguishes that weakened behavior. It is not a general mutation score. Frontend regressions are reported separately from these probes.

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
