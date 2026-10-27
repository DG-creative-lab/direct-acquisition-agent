# Validation and limits

The product is tested at pure-rule, persistence, process, HTTP and browser boundaries. This guide describes the current portfolio rather than the chronology of its construction. The portfolio includes nine frontend regressions, 29 selected mutation probes and backend tests covering the campaign lifecycle and persistent conversational planning. Test counts do not measure overall completeness or production readiness.

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
| Brief proposals retain provenance without authority | Literal current GBP budget, supported segment catalogue, forbidden tool and no campaign/review/job writes | Model intent interpretation and clarification quality are not proven by structural validation |
| Planning stays bounded across interruptions | Six admissions per conversation, two calls per request, frozen-context admission recovery, unknown-call fencing, recorded-response replay and cancellation | Fake model responses only; no live planner quality or general semantic compliance claim |
| Late planning cannot replace new intent | A correction during inference makes the completed earlier result historical | Conversation revisions only; no campaign execution from plans yet |
| Planning replay cannot dispatch unrelated work | Completed-plan replay with a separate queued conversation; targeted recovery with an unrelated expired lease and wrong organization | Targeted local worker path; general worker draining remains organization-wide |
| Budget corrections do not silently reuse stale amounts | Later unsupported currencies, shorthand, relative edits with valid amounts, ranges and mixed valid/invalid amounts require clarification; explicit new totals remain valid | Pattern-based detection cannot identify every natural-language correction |

## Test composition

Pure domain tests use literal expected populations, money and posterior values. Persistence tests use real temporary SQLite databases, controlled clocks, concurrent connections and injected failures. CLI tests cross OS process boundaries to exercise restart, review, export, learning and replay. HTTP tests send real requests to the loopback server. Frontend client tests use the real backend, and Chromium tests inspect the rendered interface.

The mutation command creates temporary source copies and weakens 29 selected enforcement points, including leases, reservations, uncertain-call fencing, retired-workflow admission, timestamp validation, migration locking, review expiry/epochs, cohort maturity/completeness, atomic finalization, snapshot memory, Origin checks, exact-subject binding, planning budget provenance, current-revision projection, conversation scope, targeted execution, stale-budget correction handling and relative-budget recognition. Detection establishes that the targeted test distinguishes that weakened behavior. It is not a general mutation score. Frontend regressions are reported separately from these probes.

The analytic Beta(1,19) quantiles provide an independent check on sampled prior intervals. Count tests verify exact trials/successes and sequential/batch equivalence. This checks calculation behavior; it does not calibrate the prior or turn simulated results into real causal evidence.

## Recorded live model evidence

The [grounding reference](product-grounding.md) records a dated GPT-OSS-120B run and a small eight-variant screening regression. The rubric and regression examples were developed together. Their match rate is not held-out accuracy, and the recorded run is not a fresh claim about current provider pricing, availability or output quality. The exported example remains unreviewed.

## Remaining gaps

There is no asserted line/branch coverage percentage or overall correctness percentage. Selected fault positions and concurrency schedules leave untested interleavings. General semantic claim detection, real data completeness, marketing impact, production authentication, external agency effects, multi-host throughput, disk-full/power-loss behavior, backup restoration, real outcome corrections and repeated-exposure attribution remain outside the demonstrated evidence.

A UI review cannot establish approval correctness, and module unit tests cannot establish restart behavior. Preserve checks at the boundary where each real effect is authorized and persisted as the system evolves.
