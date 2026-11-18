# Run ownership admission contract

Stage 1 of [epic #107](https://github.com/DG-creative-lab/direct-acquisition-agent/issues/107)
defines the contract for [#108](https://github.com/DG-creative-lab/direct-acquisition-agent/issues/108).
The executable source-ownership comparison lives on `AdmissionIntent`.
The current #109 branch contains preparatory work for the atomic writer.
Universal channel admission is an open acceptance criterion for #109.
Issue #110 owns reader adoption and historical reconciliation.

The inventory uses main at `ff2e1ff9238de0520464a5265cfb8ed2f9e486e9`.
[PR #95](https://github.com/DG-creative-lab/direct-acquisition-agent/pull/95)
was inspected at `85c2b1a28e2dbfd470da97596f22f18268bb90b1`. The newer #68
integration is a local candidate at `512e82d43462652fa590c4b31dcd9034b784164d`
with uncommitted review fixes. The SHA-256 of its reviewed `git diff --binary
HEAD -- src scripts tests` is
`1c451724abb2712a06aaac95ea7ae39cf2cacf310b01ac1ce6a214faa69a60cc`.
References to the #68 compatibility bridge below describe that local candidate.
Pin the reconciled candidate and the #108 revision for any stacked development
before refreshing and reviewing PR #95. Verify the exact integrated tree before
changing production writers.

## Reuse and gaps

| Boundary | Existing authority and enforcement | Channel and journey work |
| --- | --- | --- |
| Intent and consent | `conversations/admission.py` defines `ExecutionOwnership`, `AdmissionIntent` and `AdmissionReceipt`. `SqliteAdmissions.request_workflow` loads source and composes an intent from server-owned references. It stages exact command, source, model settings and consent in `admission_requests`. Planning has its own verified-source path. | Register the channel source loader and task composer. Journey stage and standalone command references select a scoped operation. They do not supply a trusted owner, task plan or consent. |
| Source, parent and freshness | `admission_sources.load_source` and `parent_source` verify installed workflows and exact parent plans. `require_owner` checks current conversation revision and stop. `freshness_fence` checks source-specific validity at commit. | Verify the complete assessment, recipient context, selected source version and original provider-account identity. For rewrites, verify the admitted parent and inherit its full owner. For a journey, verify the original stage key, revision, frozen configuration and consent against the durable journey. |
| Native writer and replay | `SqliteChannelContent.admit` is the shared writer behind native channel preparation and the proposed journey workflow. It compares replay inputs, reconstructs recipients, freezes context, inserts tasks and saves `channel_preparations` in one transaction. `SqliteAdmissions.admit` independently rebuilds the staged intent under the lock and binds the receipt, runtime run/tasks and conversation link. `insert_run` enforces runtime key reservations. | Route the native writer through the reusable admission transaction. A new key cannot repeat an already admitted journey stage. Bind channel preparation lookup to the committed admission, retaining its existing identity and exact replay behavior. |
| Claim and generation load | `SqliteTasks.claim` enforces store policy and lease acquisition. `SqliteChannelContent.load` checks current recipient and product evidence. The local #68 candidate also reconstructs journey origin before generation, including for contexts missing that field. | Resolve the committed admission by scoped run and exact context. Validate the binding and current execution policy before claim or generation. The compatibility path remains defined for old data. |
| Inference and allowance | `SqliteCalls.reserve` checks lease, ancestry, idempotency and run limit before writing the reservation. `execution.reserve_execution` charges the linked conversation account. `unreconciled_call_exists` checks receipt completeness. The local #68 candidate also rechecks derived origin and recognizes proven prior standalone runs. | Read one verified owner before charging its allowance. Corroborate auxiliary links against the admission. Recheck stop, consent, evidence and lease at reservation. `SqliteCalls.record` may record an existing in-flight result without creating any new authority. |
| Publication and downstream approval | `SqliteChannelTasks.settle` checks the exact task lease and atomically calls `SqliteChannelContent.publish`, which validates frozen inputs and recorded model observations. Reviews and engagements own exact approval and acceptance checks. | Verify the same committed owner and current eligibility at publication and before commit. A sequence assembled from channel artifacts must retain their bound lineage. Approval and execution checks still belong to the modules that own those effects. |
| Inspection and recovery | `admission_guard.binding` validates stored intent, request, source, consent, receipt, runtime plan and accounting link. `SqliteAdmissions._receipt` validates replay. `execution.run_origin` reconstructs older links, and `independent_resolution` verifies traditional standalone recovery evidence. Legacy migration and checkpoint adapters enforce their own evidence and restore fences. | Share the verified binding reader for adopted capabilities. Make recovery a read-only classification plus explicit evidence-checked reconciliation. Missing history stays inspectable and fenced. |

## Preparatory paused channel writer in #109

The stacked #109 implementation uses local integration snapshot `17bd908`,
which includes the #68 review fixes and the #108 merge `e66245e`. Treat this
snapshot as a development baseline until the #68 integration is accepted.

The internal `stage_ownership` composition option selects the
`paused-channel-admission/v1` task composer for native preparation and
conversation journey stages. The SQLite writer verifies scoped recipient
receipts, current source and provider-account identities, and the original
journey command when present. A rewrite proves its exact completed parent and
preserves its owner. The same transaction commits the frozen context, native
preparation, admission request and receipt, runtime plan, and conversation
account link. An exact retry reads the original binding after a restart or stop.

The staged task uses the existing paused execution fence. An ordinary native
replay of a staged run returns the same run, and a copied task cannot reserve
calls against that preparation. New requests through the default native
and workspace entry points still use the existing synthetic writer. That
writer can complete a run without an ownership binding.

The staged writer gives #110 a concrete binding to adopt. The default
writer switch requires an accepted #68 integration baseline, a reviewed
execution policy for supported synthetic work in unsealed stores, and the
claim, reservation and publication readers for that policy.

- [ ] Verify universal admission through the default native and workspace
  entry points. Every new standalone channel run and conversation journey
  stage must commit exactly one provenance-validated binding with its runtime
  work. Verify allowed synthetic continuation in unsealed stores, the
  verified-paused and inspection-only fences, and exact replay after restart.

## Ownership readers and legacy reconciliation in #110

The binding reader checks the exact channel preparation, context, task plan,
consent and accounting link for a committed channel admission. It checks
frozen recipient contexts and assessment references for both ownership kinds.
Conversation-owned work must retain its original journey bindings. A committed
standalone admission proves independent ownership and must have no conflicting
channel or recipient binding. For legacy work without a committed admission,
a journey's snapshot establishes prior admission when it names the exact run
and context.
Generation, inference reservation, publication and accounting use that binding. A
surviving runtime marker, reserved request key or admission event keeps work
fenced if its binding disappears. Current stop, evidence and lease checks
still govern the corresponding effects.

The read-only channel inspection classifies a scoped run as `bound`,
`legacy_proven`, `legacy_reconciled` or `unresolved`. A legacy proof checks
the original task plan, native recipient and assessment receipts, frozen
source, parent lineage and account where applicable. A later journey can
establish ordering through its captured prior-admission receipt. Missing
or conflicting evidence leaves the run unresolved.

Use the local channel CLI to inspect a saved run and explicitly record its
proven legacy ownership. Supply the profile, native organization and run ID
from the original work.

```sh
PYTHONPATH=src python3 -m acquisition.channel_cli --db "$store" \
  --organization "$native_organization" --profile "$profile" ownership --run "$run_id"

PYTHONPATH=src python3 -m acquisition.channel_cli --db "$store" \
  --organization "$native_organization" --profile "$profile" reconcile-ownership \
  --run "$run_id" --fingerprint "$inspection_fingerprint"
```

Reconciliation rechecks the report under the write lock and atomically
records an ownership receipt and audit event. Exact replay returns the
original receipt. A changed report requires fresh inspection. An active
lease or reserved inference must be resolved before applying the report.
Reconciliation preserves the run, context, task and call identities and
receipts. Inspection is available on restored checkpoints, where writes
remain blocked. The default admission cutover stays open in #109.

## Provenance and transition rules

1. Resolve the run organization from the server-scoped operation. Load every
   required lineage under that scope. The loader checks stored identity,
   request, source version, assessment and context hashes and durable bindings.
   Source aliases and refreshed versions retain provider-account lineage.
2. Derive the candidate owner from those verified facts. A conversation proves
   its exact owner organization, account, original revision and stage. A
   standalone request needs a positively verified independent operation root.
   Multiple independent inputs to a new standalone root must each be verified
   before the loader attests that root. Missing ancestry, missing consent or
   absence of a conversation link supplies no proof of independence.
3. Use `AdmissionIntent.validate_source_ownership` to require every required
   lineage to agree with the proposed owner. Retain `validate_parent` for the
   exact parent run and run organization. The comparator cannot tell whether a
   caller omitted a required lineage, so coverage and verification belong to
   the registered loader. Preserve the separate owner and run organizations.
4. Under the admission write lock, rebuild the intent and verify current policy.
   Atomically commit the exact request, source/context and plan fingerprints,
   owner, tasks, runtime run, receipt and any account link. A changed request
   conflicts. An identical replay observes the original receipt, including
   after stop, without starting work again.
5. Read back the same binding throughout the run. Ownership fixes the account
   and original revision. Current consent, evidence, stop, lease and approval
   govern their own effect boundaries. Provider I/O remains outside transactions.

| Situation | Ownership result | Observable consequence |
| --- | --- | --- |
| Proven independent admission, then a later journey on the same source | Original standalone root, even with equal clocks | Original run can continue when its current guards pass. Its calls stay outside the later journey account. |
| Bound journey lineage and exact current command | Original conversation/account/revision | New calls are charged to that account. A stop or edit blocks new work while preserving usage and receipts. |
| Refreshed or aliased source, new key, substituted context or removed link | Retain the original proven owner or report unresolved | A standalone declaration cannot override known conversation provenance. Unresolved work cannot reserve, publish or get a new account. |
| Mixed owners, foreign scope, different revision or conflicting parent | Reject admission | No run, reservation or publication follows the proposed owner. |
| Restart or lost acknowledgement after admission, with an unknown call | Original run and owner | Existing receipts replay. An uncertain call is never automatically dispatched again. |
| Legacy evidence absent or ambiguous | Inspectable and unresolved | Recovery must prove the original binding. Ordering or independence cannot be guessed from a timestamp or an empty link. |

## Format and rollout

- Keep the strict `execution-admission/v1` envelope and existing
  `admission_requests` and `execution_admissions` identities. Give the channel
  source payload and composer their own registered version and fingerprint.
  Bind the existing channel command/context through the canonical intent and
  task plan. Add a versioned extension only if a necessary invariant cannot
  fit the envelope.
- Existing `execution_admissions` rows have `status='paused'`. Even in an
  unsealed store, `admission_paused` treats their presence as a barrier to
  ordinary claims and reservation. Merely redirecting the legacy writer to
  `SqliteAdmissions.admit` would therefore break synthetic execution. Stage
  the new atomic writer and binding reader with paused validation first.
- Before switching the existing synthetic writer, review a versioned,
  capability-specific policy for continuing already supported synthetic work in
  unsealed stores. Keep it separate from ownership. The activation change must
  ship with the claim, reservation and publication readers and must exclude
  sealed stores, unknown capabilities and restored roots. Keep the current
  `verified-paused/v1` policy and existing limited fixture grants unchanged.
  A reader that does not understand the extension must refuse activation.
- For history, first classify scoped records without writes. Then reconcile
  only proven bindings with exact store/source verification under the write
  lock. Preserve original IDs, receipts, call journals and schema-v3 cutoffs.
  Repeated or interrupted recovery converges on the same binding. The #68
  prior-admission snapshot can be evidence for old runs. A later snapshot
  cannot clear an earlier owner, and missing snapshots are insufficient.
- Test old/new readers, interrupted rollout and rollback before enabling any
  new writer. A rollback must preserve inspectability and prevent replacement
  work for paused, uncertain or unresolved runs. Checkpoint restores remain
  inspection-only. Runtime remains business-agnostic.

[#109](https://github.com/DG-creative-lab/direct-acquisition-agent/issues/109)
owns writer integration, [#110](https://github.com/DG-creative-lab/direct-acquisition-agent/issues/110)
owns reader adoption and historical reconciliation, and
[#111](https://github.com/DG-creative-lab/direct-acquisition-agent/issues/111)
owns composed conformance and evidence for retiring compatibility inference.
Use both companies and real SQLite to exercise the matrix through accounting,
reservation, publication and fresh-process recovery. The stage 1 comparator
tests cover the admitted owner decision. The follow-up tests must also prove
loader completeness and effect-boundary behavior.
