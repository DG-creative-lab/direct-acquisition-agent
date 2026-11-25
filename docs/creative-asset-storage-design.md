# Shared creative assets and replaceable file storage

Status: proposed implementation design, 25 November 2026. The ownership and
storage direction records the agreed product discussion. Contracts and slices
below require implementation and review; they describe no installed asset
library, Blob integration or hosted release.

## Decision and user outcome

A user can find a permitted creative, use its exact version in a campaign,
review that content, and reopen or play it later. YouTube remains a native
channel module. Shared asset identity, catalogue and lifecycle belong initially
to the existing `creative` module. Filesystem and Vercel Blob implementations
sit behind a narrow file-storage port selected by bootstrap.

Use the existing application database for ownership, revisions, provenance,
search metadata and references. Use object storage for image, audio, video,
document and rendered export bytes. Keep editable copy and scripts as
versioned application records when structured content is the useful source;
rendered files can reference those records. Blob does not replace Turso.

This is a module/workflow design, not a new service, universal campaign engine,
digital asset management suite or separate agent framework. Keep the current
UI and typed-tool application path and the architecture exception list empty.

## Inspected baseline and boundaries

Merged PR #138, commit `a1659ce661d5a92ac7d5ae91c7ad779e9bf7e47b`, supplies
the native draft/review/manual-export flow, schema 26 and refreshed authored
samples. Its candidate `328467b` passed 1,189 backend and 147 browser tests;
these are baseline results, not verification of this proposed design.

- `youtube/ports.py` declares authority, campaign-store and comparison-manifest
  interfaces. It does not yet declare a general asset library/upload contract.
- `adapters/youtube_fixture.py` reads permitted bundled files and hashes bytes.
  It rejects non-loopback origins. Its links and delivery policy are local.
- `bootstrap.build_youtube` injects assets and authority. The SQLite channel
  adapter currently calls both manifest and media operations on that asset
  implementation. Do not grow cloud SDK calls or upload policy inside it.
- `scripts/check_architecture.py` enforces module roles/imports and runtime
  independence. Behavioral adapter conformance must complement that check.
- The source YouTube repository has content-addressed private filesystem
  catalogue behavior. Reuse its identity/recovery lessons and permitted sample
  manifests as evidence; do not import its database, access system or package.

Read with [architecture](architecture.md), [migration](youtube-migration-plan.md),
[channel contract](youtube-channel-contract.md), [hosted preparation](hosted-platform-preparation.md)
and [workspace design](multichannel-workspace-design.md). #70 owns authenticated
scope and connections; #130 hosted composition; #133 viewer evidence; #134 and
#74 composed release evidence.

## Ownership and ports

| Owner | Responsibility | Does not decide |
| --- | --- | --- |
| `creative` public application API | Asset identity/version, permitted catalogue search, upload admission/finalization, references and lifecycle | Hosted membership, campaign approval or publication |
| Catalogue persistence port and SQL adapter | Scoped metadata, exact request receipts, immutable versions and atomic availability transitions | Storage-provider permissions or campaign policy |
| File-storage port | Bounded immutable write, inspect/read exact object, explicit cleanup of unreferenced staged data | Who may use/publish the creative |
| Filesystem / Blob adapter | Provider-native keys, credentials, transport, size/hash verification and normalized failures | Domain identity, approval or tenant policy |
| Channel application / viewer | Bind exact assets to its native campaign, review and purpose-specific public viewer grant | Broad library access from a viewer link |
| Hosted access owner #70 | Current actor, organization, permitted operations and connection scope | Content approval from membership alone |
| Bootstrap and HTTP adapter | Wire implementations; authenticate ingress and deliver authorized responses | Browser/model claims as access authority |

Extend the current comparison manifest to consume a public, versioned creative
projection. Add media reads explicitly to the relevant port instead of relying
on undeclared methods. File-storage ports must not accept arbitrary URLs,
browser-chosen provider paths or credentials. Streaming and bounded byte reads
must be explicit capabilities; do not force production videos into one in-memory
`bytes` operation. SDK objects stay adapter-private.

## Identity, metadata and search

An asset has a server-created logical ID. Each immutable version records its
organization, content digest, byte length, verified content type, provenance,
source content revision where applicable, and a server-resolved storage binding
plus opaque object reference. A provider URL is not the asset identity.

Organization is the current ownership boundary. Product/profile references reuse
existing identities. A profile is not proof of brand membership. Introduce an
authoritative brand subdivision only when #70 supplies that ownership contract;
do not invent a parallel brand registry in the asset adapter.

The catalogue indexes organization, asset kind, product/profile, campaign links,
language, tags, creation date and lifecycle state. Campaign review status is a
derived exact-subject relationship, not a global approved flag on an asset.
Search/filter in SQL and scope the query before returning names or counts.
Begin with structured filters and bounded text search; defer embeddings.

One possible object namespace is
`organisations/{opaque-org-id}/assets/{asset-id}/{version}/{digest}`.
Add an authoritative brand namespace later if required. Paths support cleanup
and prefix listing; they are neither access policy nor the product search index.
Use separate development/preview and production bindings. Do not create a store
per campaign or globally deduplicate private files across organizations.

## Lifecycle and recovery

1. **Admit:** an authorized command freezes owner, expected metadata, operation
   ID, limits and storage binding. A repeated key with changed inputs conflicts.
   The model may propose metadata; it cannot attest ownership or content safety.
2. **Stage:** upload to a scoped immutable location using a bounded operation.
   Unsupported type/size, invalid content, cancellation or changed authority
   prevents finalization. Direct browser uploads require server-issued narrowly
   scoped upload authorization and verified completion.
3. **Verify:** check actual bytes/length/digest and applicable format checks.
   Do not trust a filename, client MIME header, upload acknowledgement or ETag as
   the content hash. A format check does not prove usage rights or factual truth.
4. **Finalize:** recheck current authority and original binding, then atomically
   commit the immutable version, ready state and request receipt in SQL.
   Only a ready version is selectable in a new campaign.
5. **Recover:** object storage and SQL are not one transaction. If an upload
   acknowledgement or SQL commit is lost, inspect the original scoped operation
   and exact object before continuing. Never create a substitute asset/version
   or label a partial result ready. Report unavailable/uncertain state explicitly.
6. **Retain or clean:** bounded reconciliation handles abandoned staged objects
   after a grace period. Recheck references and lifecycle at deletion so cleanup
   cannot race a new reference or remove reviewed/published content. Restrict the
   first cleanup slice to abandoned uploads; deletion/retention of referenced
   history remains an explicit data-operations decision under #70.

Content replacement creates a new version and requires a new campaign review.
Tags can evolve separately; changes that affect permitted use must invalidate
affected authorization rather than rewriting an immutable reviewed subject.
Imported scripts, captions and documents remain untrusted content, including
when retrieved as model context.

## Private delivery, publication and future client storage

Private drafts are the default. Authorize catalogue, upload, preview and download
operations through application code using current server-derived scope.
Credential isolation, revocation and cache policy follow #70. A provider credential
may cover a whole store, so a pathname prefix alone cannot isolate tenants.

Public comparison viewing is a separate purpose-specific grant owned by the
channel. Bind its exact campaign/content, allowed operations, expiry/revocation
and event protocol. A viewer grant cannot search the library or reveal unrelated
drafts. Draft approval does not automatically publish a public asset.
Private delivery starts with an authenticated application route and explicit
cache behavior. If temporary direct links are later selected, specify their
bounded lifetime and residual access after revocation before enabling them.
Publicly downloaded/cached bytes cannot be promised instantaneous revocation.

Vercel Blob is the first proposed remote implementation, not a dependency of
core modules. It provides public/private stores and Python access:
[overview](https://vercel.com/docs/vercel-blob),
[Python SDK](https://vercel.com/docs/vercel-blob/python-sdk-reference).
Verify current upload/streaming, delivery, quotas and pricing at implementation
and activation. A Blob deployment does not transcode or validate campaign videos
for us. No cloud store or live upload is provisioned by this design.

Reserve a storage binding ID in asset metadata now. Future client-owned storage
resolves that ID to an authorized connection with an explicit owner, native
location, credential reference, read/write purposes and lifecycle. Begin such
integrations read-only where feasible; copying/importing and external publication
need separate permission. Never accept a model/browser-supplied location as proof
that it belongs to the client.

Provider migration verifies destination bytes, retains logical asset/version
identity and changes the approved storage mapping explicitly. It needs
reconciliation and rollback evidence. Existing YouTube subjects also bind delivery
origin and manifest: replacing storage or delivery must honor those contracts,
not silently renew local approvals. Temporary URLs do not belong in the durable
identity of the proposed successor contract.

## Composed acceptance scenarios

| Scenario | Required observable result and evidence |
| --- | --- |
| Prepare a YouTube comparison using permitted ready assets | Actual A/B playback, exact bytes/hash in review/export and same version after fresh process; source/provenance labels remain visible |
| Find a reusable creative | Scoped metadata filters return correct candidates; ambiguous names remain candidates, not permission or approval |
| Another organization guesses an asset or object ID | No names, metadata, bytes or new provider operations are disclosed through that request |
| Member/connection revoked during upload or before download | Finalization/new delivery denied; no fallback to an operator credential; retained history does not grant current access |
| Upload succeeds, receipt is lost, then SQL publication fails | Original operation recovers or remains visibly pending; exactly one ready logical version, no false success and no paid regeneration |
| Object bytes disappear or change after selection | Playback/export reports unavailable or integrity failure, not substituted content under an old approval |
| Concurrent replacement, finalization or cleanup | Immutable existing version survives; same request finalizes once; referenced bytes are not collected |
| Public viewer opens a comparison | Only the exact permitted comparison is delivered; no library-management authority, cross-scope evidence or fabricated participant events |
| Local filesystem implementation changes to Blob | Same application contract and expected data; authority, identity, failure and recovery cases run against both; real hosted probe is reported separately |

Measure successful select/play/review/reopen journeys and legitimate false
blocks as well as unauthorized access, duplicate versions and false-ready
states. Operational diagnostics record scoped operation/asset IDs, state and
redacted dependency errors, not credentials, full uploads or generated learning
outcomes. Storage usage is an operational signal, not Bayesian evidence.

## Implementation sequence

| Order / track | Deliverable | Dependency and release boundary |
| --- | --- | --- |
| A: shared platform foundation [#140](https://github.com/DG-creative-lab/direct-acquisition-agent/issues/140) | Minimal `creative` catalogue/version/file ports, local adapter and conformance; adapt YouTube manifests to exact asset references | Existing module/organization contracts; no hosted identity or new sharing assumed |
| B: YouTube #143 -> #144 -> #133 | Targeting/data/reward feasibility, offline contextual allocation benchmark, then its measurement/reuse handoff | See [decisioning design](targeting-decisioning-feasibility.md); consume A or retain bundled exact assets until integration; cloud provisioning does not gate the offline baseline |
| C: hosted asset adapter [#141](https://github.com/DG-creative-lab/direct-acquisition-agent/issues/141) | Private Vercel Blob adapter, scoped delivery/upload recovery and fresh-function verification | A; #70 for hosted identity/connections, #130 composition; evidence under #134/#74 before hosted exposure |
| D: later client storage | One separately scoped client-owned adapter and migration/connection conformance | Concrete client requirement and #70 connection contract; deferred, no speculative adapter now |

The platform chat owns A/C and agrees public contracts with this YouTube track.
The next channel work is #143 and #144 before resuming #133, as detailed in
[targeting feasibility](targeting-decisioning-feasibility.md). Before concurrent
changes to bootstrap, migrations, workspace authority or HTTP composition, record
one integration owner and agreed base. #131 intake/live context remains the other
platform workstream; asset work does not replace it.

For A, limit UI to the existing campaign artifact selection/preview needs; a
standalone asset-library navigation redesign is not a prerequisite. C proves
private delivery, not public campaign activation. Keep the source preview and
source histories until the explicit #134 cutover decision.

## Decisions still needed at implementation

- The exact successor asset/review schema and compatibility treatment of old
  local manifests. Preserve historical identities; do not change golden hashes
  to fit new code.
- File-size/type limits, stream and media-range behavior, format checking and
  supported provider capability matrix. Verify with representative clips before
  claiming production playback.
- The authoritative hosted ownership/connection projection from #70, private
  delivery cache semantics and public viewer revocation behavior.
- Staged-upload expiry, referenced-history retention and reconciliation ownership.
- Actual regional, cost and quota suitability of Blob under the selected account.
  No assumption of unlimited/free production storage or transfer.

These choices do not block recording the ports/identity design or local #133
work. They do block claiming a secure, deployed multi-tenant asset service.
