# Reviewed preparation inputs

Implemented slice under #131, based on merged main `ff9be5932d0d3e734b08d6a8203e04a68765f1b4`.
The isolated branch is `feature/131-reviewed-preparation-context`. This contract
owns the platform's intake review record. It adds no channel implementation,
hosted identity, provider call, campaign creation or approval.

## Meaning and ownership

The operator selects exact saved description/claim/CTA wording, retains each
claim's qualification and references, records unresolved questions and confirms
the input selection for a finite period of one to thirty days. Campaigns owns
this reviewed preparation context. Creative continues to own company assertions
and reviewed product profiles. Conversations reuses Campaigns' deterministic
requirements-readiness function; its public intake-readiness API and serialized
results remain unchanged. Bootstrap alone wires the narrow context store.

A review records human selection of user-supplied inputs. It is not independent
verification, campaign approval or generation permission. References have stable
IDs, `checked_on: null` and `reference_only_not_fetched` provenance. Intake's
"official" CTA remains a user assertion. No URL is fetched. The new
`reviewed-preparation-context/v1` format cannot be passed as an installed
ProductProfile or a reviewed v3 fact pack. Existing pack validators and execution
pauses remain effective. Future generators must consume the selected inputs
through a separately validated grounding transition and recheck current sources
and freshness when creating a draft. They must not pass the full raw source to a
model as if unselected claims had been permitted.

## Source, review and history

A read-only preview binds the store identity, exact company and brief snapshots,
selected company revision, observed company head, latest review revision and
policy version. Claim IDs bind source identity, revision, position, wording,
qualification and references. No default company/product facts are installed.

Confirmation submits identities and selections, not replacement source prose.
Under the same writer transaction the adapter reloads authoritative intake rows,
checks the exact preview and expected review revision, then appends the context
and complete original command together. Two confirmations of the same original
request converge; competing new keys against the same preview cannot create two
reviews. Exact original retries reconcile before current-source checks and never
renew the original review timestamp or expiry. Changed inputs under that key
conflict. Re-review requires a new explicit confirmation against a fresh preview.

Company edits invalidate an outstanding preview even if the brief pins an old
company version. A fresh preview can explicitly review that pinned version while
showing the newer head. Later company edits, brief edits, a newer review, expiry
or a future-dated review mark a saved context as requiring review. They never
rewrite its bytes. The read-time `current` flag is a projection, not authority.
Unresolved operator questions, missing source references and unsupported or
partial requirements remain visible alongside exact source values. No automatic
semantic contradiction detection is claimed.

Historical reads independently reconstruct the record from its command and
scoped immutable intake revisions. Rehashing a replacement source and every
associated derived field cannot replace the native saved evidence. A review
contains no model settings, provider credentials, runtime run or campaign subject.

## Local workspace and API

The Company & brief workspace adds **Review preparation context**. Save or discard
source edits first, select wording, enter an input review note and confirm the
exact selection. Changing selection, notes or validity resets confirmation. The
UI displays missing evidence, operator questions, expiry and the latest twenty
review records. Earlier records remain addressable by their original request ID.
No model connection is required. Planning and review commands fence each other
while their original result is uncertain.

- `GET /api/intake/contexts/preview?brief_id=...&revision=N` reads an exact preview.
- `GET /api/intake/contexts?brief_id=...` reads the latest twenty reviews.
- `GET /api/intake/contexts/requests/{request_id}` reconciles an original receipt.
- `POST /api/intake/contexts` confirms an exact preview, selected claim IDs,
  description/CTA choices, expected context revision, review days, note, questions
  and `confirmed: true` under an original request ID.

Existing loopback Host, Origin and browser-token checks remain. Identity and
organization are fixed server-side; request JSON cannot select them. The POST
requires the server-derived `X-Intake-Store` identity and accepts no model funding.
The browser persists the entire original command before dispatch, checks the
current store before retrying and attempts read-only receipt reconciliation
before POST. Different-store refusals and inspection-only restores cannot clear
pending recovery as a definite original non-commit. Storage corruption/failure
blocks dispatch. A known no-write rejection on the live original store permits
editing again. Response loss retains the original review and validity window.

Receipt reconciliation preserves newer reviews and their server-reported current
status. History stays ordered by review revision; only a known later revision
can mark an older record historical, and existing reasons are retained. A
confirmed receipt cancels any older in-flight history read so that a late empty
response cannot erase it. Recovery waits for the workspace store identity to load
before dispatch, preserving the displayed receipt across startup initialization.

## Storage and compatibility

Schema 26 adds append-only `preparation_contexts` with scoped foreign keys to
company, observed company-head and brief revisions. The review and command are
one row in one transaction. Canonical records are bounded to 512,000 bytes. Failed migration/write rolls back the version and
entire record. SQLite and the existing Turso adapter use the same port and DDL.
Historical schema-23 probe registration still compares its exact old schema.
Older migration fixtures exclude later DDL rather than manufacturing old versions
by leaving new tables behind. Legacy migration inspection/apply accept schema 26
without changing seals or cutoffs. Checkpoint inspection includes the new table;
restored roots retain read-only records and cannot replay a write.

Upgrade all processes using a store before migrating it. Older schema-25 binaries
cannot open a schema-26 store. This branch allocates schema 26 against merged
#137; parallel YouTube work based on pre-#137 schema 24 must integrate the merged
intake/planning and review migrations rather than independently reuse version 25
or 26. No edits are made to that other worktree. Shared bootstrap, schema and
workspace integration must be reviewed before merging parallel runtime work.

## Acceptance and evidence boundary

- Two different products preserve their own selected wording, qualifications,
  references, CTA and exact requirements, with no iwoca substitution.
- Stale previews, substituted sources/claims and foreign organization reads or
  writes have no review effect. Cached receipts grant no future authority.
- Changed sources and expiry require review while original receipts keep exact
  historical content and deadlines.
- Competing original commands converge and competing new commands against the
  same preview conflict, including fresh processes and remote sessions.
- Process exit before/after commit and lost remote acknowledgement reconcile the
  original command without duplicate records or renewed freshness.
- Reviewed inputs remain unverified and cannot create models, campaigns, approval
  decisions or outbound effects. Read-only restore preserves that boundary.
- Existing architecture, migration, planning and workspace behavior remain intact.

Native SQLite, process, HTTP, browser and managed-remote evidence establish the
finite exercised behaviors. They do not establish factual truth, live-model
quality, hosted authentication or campaign-generation capability. Dated executed
results belong in the validation ledger and a commit-bound evaluation artifact.
