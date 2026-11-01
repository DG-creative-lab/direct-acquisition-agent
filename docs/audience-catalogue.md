# Versioned audience catalogue

This first source-integration slice of [issue 26](https://github.com/DG-creative-lab/direct-acquisition-agent/issues/26) provides read-only discovery of campaign-linked synthetic datasets. Chat preparation uses this source boundary to propose matching datasets and save an exact confirmed version before preparing a campaign.

## Installed source

`config/audience-catalogue/catalogue.json` declares each organization, dataset ID, exact version, campaign key, segment coverage, model version, source dates, review deadline, population counts and raw-file SHA-256 checksum. Its local filename is private adapter configuration. A content-addressed manifest ID binds all public metadata, including the campaign association, separately from the payload checksum.

Two contractor versions deliberately match `contractor-project-costs`. Discovery returns both as ambiguous and never chooses the first or newest version. `inventory-supplier-timing` has one candidate. Even a single candidate requires an explicit dataset/version/checksum/manifest selection. A list entry is metadata, not proof that the payload passes validation.

A combined working-capital dataset also covers both supported segments. The committed records come from the existing deterministic synthetic generator, filtered by segment while preserving upstream record and business IDs, supplied propensity values and policy fields. They are not an iwoca feed or an ML integration. Fixture review windows expire on 24 November 2026. Tests use controlled clocks; operators must review and publish a new source version when the window expires.

## Ports and checks

`AudienceDiscovery` depends on the `AudienceSource` port. `LocalAudienceSource` reads only installed JSON basenames under the composition-root-selected directory. It rejects caller paths, URLs, symlinks, duplicate JSON fields, duplicate scoped versions and unbounded input. Limits are 100 catalogue entries, 200 KB of catalogue JSON, 4 MB per dataset and 10,000 records.

Exact retrieval checks scope, selected manifest and raw checksum, then checks the snapshot schema, completeness declaration, model provenance, source date, review window, segment coverage and record/business counts. Synthetic address markers remain mandatory. This establishes consistency with the declared source, not independent proof of real-world coverage. It does not infer missing rows or train a segmentation model.

The returned immutable snapshot can be saved through the existing audience store. Retrieval itself saves no audience, campaign, run, approval or outcome and makes no provider call. Preserving business IDs supports existing eligibility and independent-population checks when a future caller binds a source to preparation. Reading a dataset grants no campaign, recipient-contact or dispatch authority.

## Local inspection API

The existing loopback Host and workspace-token guards protect both GET endpoints. Organization is resolved by the server as the local conversation source scope; clients cannot supply it.

```text
GET /api/audience-catalogue?campaign_key=contractor-project-costs
GET /api/audience-dataset?dataset_id=project-contractors&version=v1&checksum=<listed-checksum>&manifest_id=<listed-id>
```

The second endpoint returns verified metadata, the snapshot identity and counts. It does not return contact rows. Unknown or repeated query fields are rejected. Repeating a read creates no effect receipt and advances no workflow. Missing, changed, stale or incomplete sources fail closed.

`/api/knowledge` exposes the installed `list_audience_datasets/v1` and `read_audience_dataset/v1` descriptions. These correspond to the application service's discovery and exact-read operations. The current brief planner still offers only its existing submission tool; the source operations are composed by the host workflow and chat inspection, rather than exposed as a general model tool loop.

## Selection in chat

New chat preparations opt into catalogue selection, including the fixed offline example. The existing model planner interprets the objective into supported segments; candidate discovery requires exact segment coverage. The interface asks for a specific dataset version, even when one candidate remains. It does not silently choose the newest version. Future-dated or expired candidates remain visible but cannot be confirmed.

Confirmation binds organization, conversation, revision, plan, dataset/version, checksum and manifest identity. Its freshness clock is read after acquiring the SQLite write lock and checked again immediately before commit, after validation, serialization and SQL writes. Expiry at either boundary rolls back the entire selection. A single transaction checks the current revision and completed proposal, then saves the verified immutable source snapshot, selection and exact-input request receipt. Another version requires a new message and plan. A duplicate request returns the original receipt, even after the brief changes; observing it grants no authority to continue a historical preparation.

The coordinator pauses in `selecting_audience`, with no campaign or copy inference, until confirmation. The existing model-copy consent check happens before this pause. Confirmation permits preparation of the already authorized request, never approval or delivery. A missing source can be restored and the prompt refreshed. Network uncertainty retains the original client command identity; a server-confirmed pre-commit rejection releases it for recovery.

Preparation materializes the saved rows in the campaign organization without changing business IDs, scores, source dates or policy fields. The source receipt remains in the brief, manifest, exports and exact review subject. Grounded-copy context includes compact source identities alongside the campaign snapshot identity. The original catalogue files are not needed to resume a confirmed selection. Original file checksum, decoded source snapshot identity and campaign snapshot identity remain distinct.

Source provenance is rechecked at model reservation, draft commit and review/acceptance, including targeted copy revisions. Inference reservation reads its clock under the write lock, then rereads it at the final commit boundary after source validation and the reservation insert. The final fence checks both the held lease and the verified source window without loading or serializing snapshots again. Expiry rolls back the uncommitted reservation, preventing dispatch. Targeted revisions carry the same verified source manifest to this final fence. A suppression refresh may add suppression flags but cannot change population, scores or other source data, or undo a source suppression. A new subject still needs fresh approval. Source freshness uses the application's existing live or simulated clock; the local fixture flow is not a production freshness attestation.

Schema v7 adds scoped selections and command receipts under the migration lock, preserving the original legacy admission cutoff. The original run admission owns the campaign source mode. A selection recorded later for the same plan cannot retrofit an unsourced campaign, invalidate its approval or change its handoff. Campaigns admitted with a source still require that exact provenance, including if the selection record is missing. Earlier unsourced artifacts retain their original brief shape. Existing API callers that omit `use_audience_catalogue` keep the generated-fixture path, while new chat requests explicitly set it to true. A direct draft request cannot bypass an admitted catalogue requirement or strip an existing confirmed source.

General action routing, model-driven queries across named campaign catalogues and optional organization-configured audience confirmation are future work. This slice uses a segment-guided lookup and explicit local confirmation.

S3, Google Cloud Storage and other object stores can implement the same narrow port later. This version has no remote credentials, ML job submission, source uploads, real mailing connector or scheduled reporting. Those remain separate work under issue 26.

## Verification

Real-file and real-SQLite regressions cover ambiguity, metadata and payload substitution, scope, freshness, invalid coverage, bounded files, path rejection, duplicate fields, no retrieval effects and persistence across a fresh process. Loopback HTTP coverage checks token/Host guards, exact query selection and summary-only responses. Declared mutation probes remove payload checksum, manifest matching and completeness checks. These tests do not establish cloud integration, live targeting quality or real delivery.
