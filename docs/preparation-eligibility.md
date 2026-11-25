# Preparation eligibility and explicit source grounding

Implemented continuation of #131, based on merged PR #139 (`a5a8630`). This slice
uses the existing offline profile preparation contracts. It adds no live model,
hosted access, campaign approval, release, external fetching or real targeting.
The original checkout and the separate YouTube worktree are not modified.

## User workflow

Save a Company & brief and its preparation input review. Select one UK postal
channel, GBP and synthetic contacts. **Preparation eligibility and source review**
shows the exact selected material, required references and current blockers.
Reading it never writes an attestation or prepares a draft.

The operator must independently inspect the listed official pages, check their
support for the exact selected company/product wording, every factual item,
qualification and CTA, record a note and explicitly request the synthetic draft.
This is a separate act from selecting inputs in PR #139. The application records
an operator attestation, not independent verification. It does not visit a URL,
detect arbitrary semantic contradictions or establish legal correctness. Test
sources under `.invalid` remain synthetic fixtures.

The workspace offers a one-day evidence-review window. The internal application
contract permits one to thirty days, bounded by the original input-review expiry.
A new preparation requires a review dated today. Replays preserve the original
review, timestamp, expiry, settings and draft bytes. A source edit, later input
review, unresolved question or expiry prevents new preparation. Historical
receipts remain inspectable and never renew authority.

The result uses fixed business questions and at most one hundred synthetic rows.
It preserves the user's exact objective, audience, budget, candidate cap,
constraints and source revisions in its plan. The synthetic population is
explicitly **not matched to the user's audience**, and fixed framing is not a
claim of semantic interpretation or live generation quality. The product block
uses only selected, operator-attested material with its exact qualifications and
CTA. Unselected assertions are not included in frozen creative contexts or packs.

The result is an **unapproved grounded synthetic draft**. It has no installed
campaign approval or handoff capability. The existing review population validator
rejects profile proposals. This slice does not make arbitrary intake eligible for
the postal model agent: that agent's profile-model execution pause remains in
place. Actual campaign review/export integration and live generation need their
own explicit capability and verification.

## Contract and ownership

- Creative owns `SourceEvidenceReview`, selected-material projection and its
  transition to a profile-bound evidence pack. All required selected reference
  IDs must be attested, without omissions, additions or substitutions.
- Campaigns owns preparation eligibility and exact request values. The preview
  is a projection with no authority. Missing/unsupported requirements, unresolved
  questions and incompatible grounded-copy wording are explicit blockers.
- Workflows composes public profile planning, `ProfileCopyService`, synthetic
  audience and campaign draft APIs. It freezes the selected context fingerprint,
  source-review command/actor, recipe, no-model settings and exact requirements.
- Bootstrap wires the narrow store and pure builder. The SQLite adapter implements
  it for both local SQLite and Turso, using the same existing native tables.
  There is no new schema version, database adapter, model ledger or task format.

The profile plan includes an `intake-grounding/v1` binding. Copy uses the existing
`creative-context/v4` and `profile-draft/v1` contracts and their evidence/freshness
validators. It cannot downgrade into a legacy ungrounded draft. Required
qualifications, source identities and code-rendered CTA remain bound to the pack.
An included description receives an explicit provenance qualification identifying
it as an operator-reviewed description; saved claim qualifications are unchanged.

Source text is never edited for compatibility. Existing grounded-copy limits
currently reject empty claim qualifications, oversized factual wording, control
characters, em dashes in factual copy and non-exact HTTPS source URLs. Eligibility
explains these limits while preserving the original draft. User objectives are
source requirements, not generated copy; their punctuation remains intact.

## Publication and recovery

Preparation is a bounded synchronous offline computation, with no runtime tasks,
provider reservation or paid effects. The existing task/lease/cancellation and
uncertain-inference controls are unchanged. Verified execution formats stay paused:
this fixture capability cannot write proposals in a verified-admission store.

One writer transaction rechecks native context integrity, latest source/review
revisions, eligibility, the exact preview, evidence freshness and the candidate.
It publishes audience, creative context/catalogue, draft and both original-request
and exact-context operation bindings together. A final validation before commit
rejects expiry or altered state and rolls back all intermediate rows. Two
invocations of the same command converge; another key cannot repeat preparation
for the same input review. A new intentional preparation requires a new input
review. A lost acknowledgement is reconciled by the original scoped request ID.

History is reconstructed from the native immutable intake/context records and
original recipe, not the current input head. Reads also validate exact stored
audience, contexts and catalogues. New eligibility requires current sources;
historical inspection does not. Restores and read-only openings cannot prepare.
Organization and original-store identity scope every lookup and write.

The browser saves the entire original command and store identity before POST.
It reconciles by GET before retrying and retains recovery data after uncertain
failures, corrupt storage, invalid receipts or a store mismatch. Only a matching
receipt or a definite original-store no-write rejection clears pending recovery.
A competing source selection cannot replace the pending command. Stored receipts
are presentation data, never campaign approval or permission for another effect.

## Local workspace API

- `GET /api/intake/eligibility?context_request_id=...`
- `POST /api/intake/preparations`
- `GET /api/intake/preparations/requests/{request_id}`

POST requires the loopback Host/Origin/workspace token and exact `X-Intake-Store`.
Actor and organization remain fixed server-side. Model funding, browser identity
fields, query arguments and duplicate JSON fields are rejected. The payload binds
`request_id`, `context_request_id`, `preview_id`, an exact `evidence` review and
`confirmed_synthetic_preparation: true`. Evidence contains required reference IDs,
`checked_on`, `review_days`, note and both explicit support/official-source flags.

## Acceptance and evidence boundary

The finite regression portfolio covers two authored products, exact selected
wording/qualifications/CTA and budget provenance; omitted/unselected/foreign
material; stale or expired sources; unsupported scope; operator confirmation;
pre/post publication faults; changed-input replay; two concurrent local and remote
sessions; process reopening; lost remote commit acknowledgements; trusted HTTP
scope; browser reload, mobile/desktop forms and original-store recovery. Literal
expected wording and durable row counts serve as independent test oracles.

Native and loopback Hrana evidence establish these contract behaviors. They do
not establish current managed Turso availability, live response quality, factual
truth or hosted access. New managed-provider evidence requires the isolated
operator configuration, which was absent during PR #139 integration. No cloud
resource or credential is created as part of this slice.

The [25 November 2026 verification record](evaluations/issue-131-preparation-eligibility-2026-11-25.json)
binds the executed checks to source `ff1428d`, records the sequential test policy
and preserves the managed-provider and live-model evidence limits.
