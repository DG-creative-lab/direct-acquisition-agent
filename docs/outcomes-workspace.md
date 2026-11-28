# Recorded outcomes in the local Learning workspace

Learning offers **Recorded campaigns** alongside the existing **Synthetic campaign**
view. Recorded campaigns work without first creating a synthetic campaign. They
use the [external outcomes registry](external-outcomes.md), not a second learner.
Separately developed YouTube measurement retains its own journal, assignment
identities and reward definitions.

## Operator workflow

1. Save a company and campaign brief in **Company & brief**. In Learning, select
   that company, brief and exact brief revision. A brief retains the company
   revision it originally referenced, even if the company has since changed.
2. Upload or paste an original registration JSON manifest. Review the frozen
   company/brief, campaign, channel, assignments, qualification rule, source
   accounts, observation window and prior before **Confirm registration**.
3. Select the saved cohort and upload source reports. **Preview report** parses
   the original text strictly, including duplicate-field rejection. Confirm the
   report only after inspecting its source and event population.
4. Inspect explicit outcomes, unknown outcomes, diagnostic events and independent
   businesses. Missing observations never become negative outcomes. Recorded
   fixtures remain labeled; operator-attested results are not provider-verified.
5. Once the original window is mature and a complete final source snapshot covers
   every assignment, **Review finalization** displays the counts, posterior and
   comparison. Confirmation rechecks that evidence inside the write transaction.
   A report arriving after preview invalidates the old preview. Refresh and review
   the new evidence rather than silently finalizing a different population.
6. Inspect historical source reports and download the exact displayed snapshot.
   Current eligibility-filtered comparisons are separate from historical receipts.
   Neither the receipt nor an advisory comparison grants campaign or send authority.

Browser uploads use UTF-8 JSON in the existing registry schemas, bounded to four
MiB each. Invalid encoding is rejected instead of silently replacing source characters.
The local workspace resolves organization `local-conversations` and operator
`local-operator` on the server. Evidence must name that organization; JSON cannot
select a different actor, organization, role or model connection. The examples in
`examples/external-outcomes` describe the source format, not automatically verified
or dispatched platform campaigns.

## Persistence and recovery

The selected workspace root stores all new records in `conversations.sqlite`,
using schema 28 and the existing learning command/event journals. No new database
or schema migration is introduced. Registration, the full frozen company/brief
association, source reservations, audit and receipt commit in one transaction.
The association has its own immutable journal identity and does not alter the
original registration manifest or cohort ID. Older unassociated cohorts remain
inspectable; the browser cannot attach a new company to them after the fact.
Original API/CLI inputs and replay identities remain compatible.

The first explicit valid local registration can initialize the local operator if
absent, atomically with registration. It never enables a disabled actor or grants a
reviewer role. Preview and listing do not create operator authority. Inspection
roots and the existing paused verified-admission format remain unwritable.

Before an effectful request is sent, IndexedDB retains its original JSON text,
preview, company, store identity and request ID. This supports uploads larger than
session storage. Reloading offers **Recover original request**. Recovery resends
that exact request. A lost reply after commit converges on the original receipt.
The client checks store identity before dispatch; the server checks it again.
Starting another root at the same origin cannot redirect a pending request there.
**Inspect saved request receipt** reads an available original receipt without
clearing pending recovery or requiring write authority. It checks the original
store again. Do not clear browser storage while a request is uncertain.

A validation error clears recovery only after a durable rejection fence confirms
that no command committed. All writes check that fence inside their transaction,
so a delayed original request cannot commit after the browser was told it was
safe to start again. An already committed command cannot be fenced away. Network
errors, malformed replies and paused-format failures retain the original request.
Provider credentials and workspace tokens are not saved with browser recovery.

## Local HTTP boundary

All routes retain the existing loopback Host, same-origin mutation and workspace
session-token checks. Mutations and upload previews require exactly one
`X-Outcomes-Store` header. Model-funding headers and extra query fields are rejected.

- `GET /api/outcomes/store`
- `GET /api/outcomes/cohorts?company_id=...&after_id=...` (25 per page)
- `GET /api/outcomes/cohorts/{cohort}`
- `GET /api/outcomes/commands/{register|import|finalize}/{request}`
- `GET /api/outcomes/cohorts/{cohort}/reports/{report}`
- The same report route with `snapshot_id` downloads exactly the inspected bytes.
- `POST /api/outcomes/{register|import|finalize}-preview`
- `POST /api/outcomes/{register|import|finalize}`

This is a local single-worker workspace. Hosted tester authentication, authenticated
provider webhooks, live delivery, automatic suggestion-memory integration and a
shared cross-channel posterior are separate work.
