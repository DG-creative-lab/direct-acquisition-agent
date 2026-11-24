# Company and campaign intake persistence

The Python intake API and local workspace let an operator save and reopen
company/product information and campaign requirements. The local **Company &
brief** area supplies forms over the guarded loopback API. Gateplane-backed
tester access and connecting these drafts to interpretation/generation remain
separate work. Saving supplies no fact verification, campaign approval or delivery
authority.

## Ownership and composition

`creative.CompanyDraft` owns user-supplied company/product names, a website,
description, claims with qualifications and reference URLs, and requested
official CTA wording and URL. These are source assertions, including the word
"official", rather than independently verified product facts. They cannot be
installed as a `ProductProfile` or substituted for a reviewed v3 fact pack.

`campaigns.CampaignBriefDraft` owns the pinned company identity/revision,
objective, audience requirements, requested country/currency/channels, integer
budget in that currency's minor units, candidate count, constraints and explicit
synthetic or unspecified contact source. Missing values are allowed for drafts.
Unsupported market/channel requests remain exact user requirements. Intake does
not substitute defaults, assess campaign capability or imply execution support.
Source punctuation, including em dashes, is retained exactly. Editorial rules
for newly generated copy do not restrict user assertions or campaign requirements.

`campaigns.CampaignIntake` coordinates these drafts through a narrow
`CampaignIntakeStore`. Bootstrap alone selects `SqliteCampaignIntake` and the
local SQLite or remote Turso application database. Runtime, planning, inference,
installed profiles and existing campaign workflows do not consume intake yet.

```python
from acquisition.bootstrap import build_intake
from acquisition.creative import CompanyDraft, CompanyClaimDraft
from acquisition.campaigns import CampaignBriefDraft

intake = build_intake('/tmp/tester-intake.sqlite')
company = intake.save_company(
    'organization-1', 'local-writer', 'company-request-1',
    CompanyDraft(company_name='Example', product_name='Example product',
                 claims=(CompanyClaimDraft('A user assertion', 'Its qualification'),)))
source = company['snapshot']
brief = intake.save_brief(
    'organization-1', 'local-writer', 'brief-request-1',
    CampaignBriefDraft(source['id'], source['revision'],
                       objective='Find potential customers', currency='GBP',
                       budget_minor=10000, contact_source='synthetic'))
saved = intake.brief('organization-1', brief['snapshot']['id'])
```

The organization and actor arguments must be supplied by trusted composition.
There is no browser-controlled identity resolver, new tester account system or
local fallback for a future hosted access decision. This API is not a public
access boundary. Gateplane must authenticate/authorize hosted requests before
the corresponding transport can call it. A local caller has the same trust as
the current operator application. User URLs are stored as references and never
fetched by intake. The workspace renders source text as data, including text that
looks like markup, and never inserts it as HTML.

## Local workspace forms and API

Start the supported local workspace, then open **Company & brief** in its
navigation. Enter company/product details, optionally add claims with their
qualifications and references, and choose **Save company draft**. Partial drafts
are supported. Next choose that saved company and an exact version in the
campaign brief, record the requirements, and choose **Save campaign brief**.
The company-version preview displays the pinned description. Editing the company
later leaves the earlier brief unchanged.

Saved company and brief selectors reopen records for editing. Version numbers
identify the source of an edit. A conflicting save retains the operator's text;
**Replace edits with latest company/brief** explicitly reloads the current saved
version. Save or discard edits before switching to another record. Lists load
50 records at a time with **Load more** controls.

Unsaved form fields remain in memory while switching workspace areas. Save before
reloading or closing the page. A native warning is attached only while there are
unsaved changes; it is an aid, not a durability guarantee. In particular,
[browser beforeunload events are not reliable on mobile](https://developer.mozilla.org/en-US/docs/Web/API/Window/beforeunload_event).

Before a save is dispatched, tab session storage retains its original request ID,
complete body and the edit's base snapshot. While its outcome is uncertain, both
forms are fenced and **Retry original save** repeats that exact command. Reloading
restores the pending edit target and base revision. Known rejection allows editing
again; network errors, server failures and unreadable replies retain the original
command. Storage failure blocks dispatch. The client checks the domain's total ASCII-JSON
size before retaining a command, including Unicode escape expansion. Oversized
drafts remain editable and are never dispatched. An original receipt is labelled as an
original save confirmation and shows its exact historical version. Tab recovery
data is removed only after a confirmed response or explicit server rejection.
Closing the tab can discard tab recovery data, so use the saved records and retain
an uncertain tab until its original save is confirmed.

| Route | Behavior |
| --- | --- |
| `GET /api/intake/companies` or `/briefs` | Latest snapshots with optional `after_id` and integer `limit` from 1 to 100 |
| `GET /api/intake/companies/{id}` or `/briefs/{id}` | Latest snapshot, or an exact optional positive `revision` |
| `POST /api/intake/companies` or `/briefs` | Exact JSON keys `request_id`, `id`, `expected_revision`, `draft`; use null identity and revision zero to create |

The application maps these routes to `local-conversations` and `local-operator`
in the root's `conversations.sqlite`. Organization, actor, schema, approval and
other extra fields are rejected as input. Partial draft objects use the declared
domain defaults; collection fields are JSON arrays and claims have explicit
statement, qualification and reference fields. The supported local server retains
its root lock, token/Host/Origin checks and content-security policy. It is not a
hosted identity or membership boundary and must not be exposed publicly.

Intake saves have a 70 KiB HTTP body limit; the domain still caps a serialized
draft at 64,000 bytes. Other workspace body limits are unchanged. Invalid input
returns 400, missing scoped records return 404 and changed inputs/stale revisions
return 409. These definite rejections carry `intake_not_saved: true`. An uncertain
failure never carries that marker. Model funding headers are rejected on intake
saves. No request fetches source URLs, invokes inference or starts a campaign.
Bootstrap preserves the workspace's selected verified-admission policy when
opening intake. Existing store and historical inspection rules retain their
authority.

## Revision and recovery contract

- Create with an original organization-scoped request key at expected revision
  zero. The service assigns an organization-bound identity. Edit with that
  identity and an exact positive expected revision.
- Every successful save appends a revision and its request receipt in one
  `BEGIN IMMEDIATE` transaction. Writer locking and the revision comparison
  select one winner for competing edits, including separate remote sessions.
- Idempotency binds kind, actor, target, expected revision and complete draft
  payload. JSON object order is immaterial; text and array ordering stay exact.
  A changed command on the same key conflicts, including a different operation.
- An exact retry returns the original saved snapshot with `replayed: true`,
  even after later edits. It is a historical result, not current access or
  approval. Original timestamp and actor attribution are retained.
- Every brief revision has a same-organization foreign key to an existing exact
  company revision. Later company edits never silently rebind saved briefs.
  A new brief revision can explicitly select another existing company revision.
- All reads, latest-revision comparisons, pages, commands and references are
  organization-scoped. Lists are identity-ordered latest snapshots, paged using
  `after_id` and a limit of 1 to 100. A list is not a cross-request snapshot.
- Company revisions, brief revisions and receipts reject SQL update, deletion
  and replacement. There is no delete/retention interface in this slice.
- A failure before commit rolls back both writes. After a remote uncertain
  commit, surface uncertainty and retry the exact original request through a
  fresh invocation. Intake does not automatically repeat the transaction body
  or create a replacement key. Local process loss follows the same replay rule.

Each snapshot is marked `user_supplied_unverified`, `authority: none` and
`execution_readiness: not_assessed`. No inference reservation, URL fetch, campaign
run, approval or outbound effect occurs on save or read.

## Migration and compatibility

Schema 24 adds three intake tables, scoped reference constraints and immutable
history triggers under the existing atomic migration lock. Turso journals the
same migration in `acquisition_schema`. Existing rows, store identity, historical
evidence and legacy cutoffs are not backfilled or rewritten. Read-only Turso
opening requires a migrated schema-24 store. Earlier binaries are not schema-24
readers; roll forward rather than reverting application binaries on that store.

Checkpoint capture/restore and legacy inventory recognize the additive schema.
Restored intake is historical inspection; even original request replay cannot
write through a restored root. `build_intake(..., read_only=True)` additionally
fences all saves. Historical schema-23 probe registration remains explicitly
pinned to its original full schema and then uses the normal reviewed migration.

## Bounded verification

Focused tests exercise exact replay, changed-kind/actor/payload rejection,
cross-organization reads/edits/references, both draft types' competing edits,
append/receipt rollback, process exit before and after commit, immutable SQL
history, partial input and bounds, pinned old company wording, pagination and
zero campaign/inference/approval rows. Real SQLite over the Hrana wire also
checks independent sessions, remote migration rollback and a lost COMMIT reply.
The existing checkpoint round trip now includes intake data.

The opt-in `scripts.intake_conformance` command uses only the existing dedicated
`acquisition-hosting-probe` resource. It retains a unique synthetic organization,
tests competing fresh processes and an intentionally lost commit reply, and
writes source-attributed evidence without disclosing credentials. It does not
activate models, hosted tester access or a deployment. The dated evaluation and
`docs/validation.md` record actual executed results and remaining limits.
