# Reviewed intake email preparation and exact export

This local workspace capability connects saved company facts and an email-only
campaign brief to a bounded, inspectable synthetic email package. It uses the
reviewed preparation context and source grounding introduced in PR #145. It does
not connect a mail provider, admit model work or grant delivery authority.

## Operating flow

1. Save your company assertions, selected factual claims and qualifications,
   official call to action, and an email-only brief. The installed scope is UK,
   GBP and explicitly synthetic contacts. Review the exact saved revisions in
   Company & brief. Selecting another revision makes the old context historical.
2. Inspect email eligibility and the selected source URLs. Record a source-review
   note and explicitly confirm exact wording, qualifications and official
   sources. The application preserves assertions; the operator checks their truth.
3. Prepare one to six fictional emails. The saved candidate limit bounds the
   batch; an omitted limit defaults to three. The complete batch must fit the
   saved budget at two synthetic GBP minor units per recipient. This amount is a
   demonstration cost, not a provider charge. No model call is made.
4. Inspect every recipient, sender, subject, plain text and HTML, including the
   exact product wording, qualification, CTA and opt-out fields. HTML is displayed
   as source text. Fictional contacts have explicit synthetic permission and
   pressure observations. They are not matched to your requested audience.
5. The local reviewer approves or rejects the complete immutable package, with a
   reason. Approval lasts at most one day and cannot outlive source review. The
   local operator can download JSON only while that exact approval remains
   current. Revocation, source edits, expiry, changed actor generations or changed
   recipient eligibility block the download, including an old export URL.

The JSON contains the exact rendered email rows, reviewed source binding,
requirements, product evidence, permission observations, approval and limitations.
It is labeled `SYNTHETIC_ONLY` and `live_send_authority: none`. Sender, recipients
and unsubscribe destinations are fictional. Do not import it into a mail sender.

## Ownership and persistence

Campaigns owns the intake application and preparation port. Creative owns the
existing grounded product builder and email rendering rules. The workflow
composes them with audience permission observations and the public campaign
eligibility policy. Reviews owns the distinct
`synthetic_intake_email_export/v1` subject, decision and export contract.
Bootstrap wires these services through SQLite-compatible adapters; runtime stays
business-agnostic. `EmailCampaignProfile` uses `campaign-profile/v2`; the postal
v1 profile and its exact-type consumers cannot silently accept an email profile.

Preparation writes the original command and exact-context binding atomically in
`intake_requests`, using disjoint `intake-email:` and `intake-email-context:`
keys. The same context cannot be prepared under a second key. Exact replay
returns the original package and original expiry. Reads rebuild the package
from its native reviewed source and validate both bindings. Historical reads
preserve original bytes while reporting current blockers.

Review decisions, revocations and export receipts use the existing
`review_commands` journal, with `intake-email-review:` keys and distinct kinds.
Keys include organization, actor and operation. Each entry hashes its exact
inputs and immutable receipt. A decision identity includes its original request
key so a later decision cannot reuse a revoked identity. No schema migration,
second command registry, task, model reservation or engagement is introduced;
SQLite schema version remains 27.

A review subject binds the complete batch and current scoped authority,
objection, suppression and stop rows. Mutations use the database writer
transaction. Review and export recheck source freshness, recipient eligibility,
actor generation and purpose at commit. Downloads acquire the same writer
transaction and reauthorize before returning the exact bytes. A historical
receipt contains no downloadable body and grants no present authority.
Inspection-only restores, read-only services and verified-paused stores retain
history but cannot prepare, decide, revoke, export or download new output.

The loopback workspace has fixed local operator/reviewer identities. Explicit
first preparation initializes missing defaults through the existing role API;
configured roles are preserved and preparation history prevents later automatic
role recreation. This is not tenant authentication or Gateplane onboarding.

## HTTP and browser recovery

Read endpoints:

- `GET /api/intake/emails/eligibility?context_request_id=...`
- `GET /api/intake/emails/requests/{original_preparation_request}`
- `GET /api/intake/emails/commands/{decision|revocation|export}/{request}`
- `GET /api/intake/emails/exports/{export_request}?subject_id=...`

Commands use `POST /api/intake/emails/{prepare|decision|revoke|export}`.
Preparation uses the exact grounded-preparation fields. Decision, revocation and
export name the original preparation and exact subject/approval as applicable.
Host, Origin, workspace token and `X-Intake-Store` are required for mutations.
Queries, duplicate JSON fields, browser-selected identity and model funding are
rejected. Downloads require the workspace token and current server authorization.

Before dispatch the browser saves the complete command, original store identity
and context fingerprint in versioned session storage. Retry first reads the
original receipt. It repeats the original POST only after a definite absence in
the same store. A store switch, malformed recovery data or uncertain response
retains recovery data and blocks new commands. A successful historical export
reconciliation still needs a freshly authorized download. Changing the selected
context cannot relabel a late command result as the current package.

## Acceptance and evidence limits

The finite portfolio covers two authored companies, exact selected source
wording/qualification/CTA, native permission eligibility, purpose and role
substitution, expiry, revocation, source edits, atomic rollback, lost replies,
restart, original-store recovery and exact downloaded bytes. Native SQLite and
loopback Hrana tests exercise the same application path. Full backend,
architecture, integrated recovery and one-worker browser results are recorded in
`docs/validation.md` and a commit-bound evaluation record.

Loopback Hrana is protocol conformance evidence, not a managed Turso health check.
No live provider, real contact permission, audience match, paid generation,
public hosting, Gateplane session or real sending is established by this slice.
Existing sequence preparation/review/simulation stays separate; this purpose
cannot authorize its execution. Later work can connect live generation and real
contact sources through their existing bounded contracts.
