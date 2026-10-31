# Versioned audience catalogue

This first source-integration slice of [issue 26](https://github.com/DG-creative-lab/direct-acquisition-agent/issues/26) provides read-only discovery of campaign-linked synthetic datasets. It prepares the source boundary for conversational campaign selection. It does not yet change how a chat prepares its campaign.

## Installed source

`config/audience-catalogue/catalogue.json` declares each organization, dataset ID, exact version, campaign key, segment coverage, model version, source dates, review deadline, population counts and raw-file SHA-256 checksum. Its local filename is private adapter configuration. A content-addressed manifest ID binds all public metadata, including the campaign association, separately from the payload checksum.

Two contractor versions deliberately match `contractor-project-costs`. Discovery returns both as ambiguous and never chooses the first or newest version. `inventory-supplier-timing` has one candidate. Even a single candidate requires an explicit dataset/version/checksum/manifest selection. A list entry is metadata, not proof that the payload passes validation.

The committed records come from the existing deterministic synthetic generator, filtered by segment while preserving upstream record and business IDs, supplied propensity values and policy fields. They are not an iwoca feed or an ML integration. Fixture review windows expire on 24 November 2026. Tests use controlled clocks; operators must review and publish a new source version when the window expires.

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

`/api/knowledge` exposes the installed `list_audience_datasets/v1` and `read_audience_dataset/v1` descriptions. These correspond to the application service's discovery and exact-read operations. The current brief planner still offers only its existing submission tool; these new source contracts are not yet a model tool loop or a chat selection interface.

## Next integration boundary

Conversational routing must persist the user's exact source selection and carry its manifest and snapshot provenance into frozen preparation. It must handle multiple candidates, require any configured human confirmation and retain eligibility, budget, population allocation, validation and approval checks. Reading a source cannot substitute for those checks.

S3, Google Cloud Storage and other object stores can implement the same narrow port later. This version has no remote credentials, ML job submission, source uploads, real mailing connector or scheduled reporting. Those remain separate work under issue 26.

## Verification

Real-file and real-SQLite regressions cover ambiguity, metadata and payload substitution, scope, freshness, invalid coverage, bounded files, path rejection, duplicate fields, no retrieval effects and persistence across a fresh process. Loopback HTTP coverage checks token/Host guards, exact query selection and summary-only responses. Declared mutation probes remove payload checksum, manifest matching and completeness checks. These tests do not establish cloud integration, live targeting quality or real delivery.
