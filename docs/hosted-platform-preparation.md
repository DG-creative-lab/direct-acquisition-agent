# Remaining preparation for a hosted multichannel workspace

Status: migration planning, 24 November 2026. This is a gap map against accepted main `796a4cc3f533e0cbae3b7760e89221d9fe1b1b86`. It adds no cloud resources, credentials, paid calls or deployment.

The target is a bounded online product a permitted tester can actually use: save company and campaign context, talk to the agent, review an exact result, export it and return to saved work. YouTube adds a usable viewer and channel-specific evidence loop. See the [migration sequence](youtube-migration-plan.md) and [shared workspace design](multichannel-workspace-design.md).

## Reuse the completed preparation

| Existing capability | Evidence in this repository | Remaining distinction |
| --- | --- | --- |
| Reviewed organization/product profiles and synthetic multichannel preparation | [Profiles](organization-profiles.md), [channel expansion](channel-expansion-plan.md); #61 to #68 closed | Not general live user-intake interpretation or real outreach |
| Native remote libSQL storage with transactions, migrations and uncertain-result recovery | [Remote storage](remote-storage.md) | Each new channel's state and cross-function recovery still need conformance evidence |
| Request-bound serverless preparation with explicit stage continuation | [Serverless preparation](serverless-preparation.md), `api/preparation.py` | Operator-only synthetic workflow, not a hosted visitor workspace |
| Saved Company & brief drafts with scoped revisions and replay | [Intake](intake.md), accepted PR #127 | Drafts are source assertions; planning does not yet consume them as reviewed grounding |
| React workspace and bounded local workspace API | [Workspace](workspace.md), [architecture](architecture.md) | Local loopback identity/root lock is not hosted authorization or a distributed lock |
| Vercel/Turso feasibility and deployment plan | [Feasibility](hosting-feasibility.md), [MVP deployment](mvp-demo-deployment.md) | Historical probes and plans are not proof of a newly deployed complete application |

Do not recreate a database adapter, stage runner or intake editor. Older introductions in feasibility documents describe gaps that later merged work addresses. Use current code and dated evidence to distinguish remaining work.

The current preparation deployment serves `public` and an operator endpoint. Its configured region and invocation deadline describe that composition, not an entitlement to every platform limit. Current pricing, free-tier eligibility, account quotas and model allowance must be verified at activation. This plan makes no promise of unlimited or permanently free hosting.

## Remaining work and ownership

### Hosted tester identity and workspace commands

Extend the existing authenticated-pilot boundary in [#70](https://github.com/DG-creative-lab/direct-acquisition-agent/issues/70). Resolve identity and organization using Gateplane's authoritative hosted contract. A fixed operator bearer token, local browser token, submitted organization field or old YouTube invite is insufficient evidence of visitor membership.

Decide the bounded tester role set and permitted operations. Enforce current membership, revocation and object scope in application commands and commit-time checks, including downloads, evidence and model operations. Browser projections and model-selected tools cannot enlarge access. Scope caches and idempotency receipts to the same resolved identity contract.

Acceptance must include two distinct authorized organizations, guessed IDs, revoked sessions, concurrent changes, reload, cold start and an unavailable identity dependency. Reject unauthorized effects with no fallback to the operator identity. A narrow preparation/export release may use synthetic contacts; full CRM-connected pilot acceptance remains under #69 to #75.

### Saved intake to live agent context

Reuse `creative.CompanyDraft`, `campaigns.CampaignBriefDraft` and `CampaignIntake`. Add an explicit transition from saved source assertions to the permitted context used for interpretation and artifact generation. Record source and intake revisions, product/profile version, qualifications, evidence IDs, missing fields and freshness.

A website string is a reference, not fetched or verified evidence. Do not upgrade a user claim into an installed reviewed fact pack, silently fall back to iwoca facts, or bypass v3 grounding with legacy inputs. Decide whether a task requires reviewed factual material or can produce clearly labeled advice pending review. Inspecting draft context must not dispatch generation.

New claims, unsupported channels and contradictions should produce an editable draft or clarification with clear blockers. Changes invalidate affected downstream proposals. Retrying after partial admission must recover the original frozen context and request.

### Funding, model selection and session lifetime

Choose one explicit contract before enabling migrated live tools. The source YouTube app permits tab-memory BYOK and selectable bounded paid routes; current destination generation uses server-side credentials and explicit admission. The hosted free-demo proposal has stricter zero-price/no-paid-fallback goals.

Separate hosted demo allowance, user-funded requests and any operator-funded benchmark. Specify permitted models/routes, spending principal, local reservation ceilings, batch/session limits, expiry, revocation and cost uncertainty. A local ceiling is not an external billing guarantee. A model listing is not route qualification. Unknown billing or uncertain provider execution must block further unsafe calls.

Keys never enter Git, prompts, browser history, receipts or exports. Never transfer an old tab key, read it out of the browser, or turn a deployment change into authorization for a new paid test. Paid verification remains a separate owner-authorized action.

### Deployable frontend and request lifecycle

Compose the React bundle, authenticated workspace API and installed channel capabilities in a supported hosted entrypoint. Reuse stage continuation and original-receipt recovery. Local scheduler threads or root filesystem locks cannot coordinate independent functions.

Define which requests complete within a bounded invocation and which require durable continuation. User-visible status must describe the durable stage, including failed, blocked, unknown and completed states. A disconnect must not imply success, cancellation or safe repeat. Health/readiness must use a fresh bounded storage probe and distinguish process liveness from ability to perform authorized work.

Exports and viewer assets need exact content identity, appropriate visibility, content types, usable links and revocation behavior. A download must correspond to the displayed authorized subject. Avoid persisting private assets under public static paths.

### Remote operations and release evidence

Reuse native remote storage. Verify schema opening, concurrent requests, failed writes, uncertain commits, optimistic conflicts, cold-start reads and recovery for the new workflow. Local ancestry/checkpoint/restore semantics must not be assumed to transfer to remote storage.

Define minimal session/run diagnostics with request ID, stage, model/prompt version, tool status, receipt linkage, known/unknown billing and redacted errors. Set retention and deletion controls before collecting content for later evaluation. Diagnostics cannot serve as authorization or as independent learning outcomes.

Under [#74](https://github.com/DG-creative-lab/direct-acquisition-agent/issues/74), record composed release evidence for:

- Independent visitors seeing only their own saved work after a fresh deployment/function.
- Save, exact review/export and channel event persistence through simulated write failure and retry.
- Correct stop/recovery behavior after a provider reservation or ambiguous response.
- Current model-route qualification, funding exhaustion and no automatic paid fallback.
- A truthful degraded-state UX when identity, storage or provider access fails.
- Existing postal/sequence behavior preserved alongside the installed YouTube capability.

Real CRM reads, Resend delivery, human-call dispatch and a commercial pilot keep their existing #69 to #78 gates. The YouTube preparation MVP must not silently activate those effects.

## Release decision

The next deployable milestone is achieved only when a permitted tester completes the intended workflow on the actual hosted composition. Passing a storage probe or generating a model answer alone does not establish that claim.

Require an attributable report naming commit, schema, environment, identity mode, fixtures versus live components, model/prompt and authorized cost scope. Note failures and untested paths. Keep the existing YouTube preview until the migration's hosted parity and explicit cutover decision are complete.
