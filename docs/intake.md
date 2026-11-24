# Company and campaign intake persistence

This internal Python slice lets a future tester workspace save and reopen its
own company/product information and campaign requirements. It grants no hosted
access, fact verification, generation, campaign approval or delivery authority.
Gateplane integration and the intake HTTP/React interface remain separate work.

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
fetched by intake. Future rendering must treat text and URLs as untrusted data.

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
