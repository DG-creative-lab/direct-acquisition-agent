# Organization and product profile foundation

Issue [#61](https://github.com/DG-creative-lab/direct-acquisition-agent/issues/61), under [epic #60](https://github.com/DG-creative-lab/direct-acquisition-agent/issues/60).

This slice prepares unapproved, source-grounded synthetic postal proposals for two installed company profiles through the same application services. It establishes profile and taxonomy contracts for later expansion. Existing chat, grounded model generation, exact local review, postal simulation and learning retain their original contracts.

The new path is an explicit Python/CLI preparation API. It installs no new chat routing, model execution, review/handoff authority, email sending or calling. Its `approval: not_granted`, `execution: not_performed` and `semantic_screen: not_evaluated` fields are deliberate. Issues #65 through #68 own the later content, sequence and conversational capabilities.

## Installed profiles

| Profile/version | Product evidence | Audience taxonomy | Brand and qualification |
| --- | --- | --- | --- |
| `iwoca/v1` | Existing reviewed public Flexi-Loan pack, preserved exactly | Stock/inventory and projects/contractors | Existing facts, qualifications and official iwoca CTA, with synthetic disclosure |
| `fielddesk/v1` | Fictional visit-planning product specification | Maintenance teams and installation teams | Appointment questions, fictional capability qualifications and a `.invalid` demonstration CTA |

Fielddesk is synthetic. Its authored specification is test evidence, not an externally verified product or a real offering. Both profiles remain UK/GBP postal response experiments. An unsupported market, currency, channel, profile/version or taxonomy is rejected rather than replaced.

Files in `config/profiles/` contain reviewed configuration and fixture content. Bootstrap selects a fixed installed key and binds the source adapter to one trusted local organization. There is no arbitrary profile path, executable configuration or network source retrieval. The CLI organization argument provides local scoping, not hosted authentication.

## Prepare a proposal

From the repository root:

```sh
PYTHONPATH=src python3 -m acquisition.profile_cli \
  --db .local/fielddesk-profile.sqlite \
  --organization fielddesk-demo \
  --profile fielddesk --version v1 --request-id first-profile \
  --objective "Compare responses to visit-planning questions." \
  --budget-pence 60000 --segments maintenance installations \
  --country UK --currency GBP --channel direct_mail
```

For iwoca, use another request/database and `--profile iwoca --version v1 --segments inventory contractors`. The same bootstrap, planning, copy, campaign and persistence implementations handle both. All contact addresses are synthetic and marked not to post. The illustrative 85-pence treatment cost remains the postal demo cost, not a commercial forecast.

The result contains the exact draft/manifest identity, frozen plan, counts and cost. Preparation creates no runtime tasks, model requests, decisions or simulated jobs. Use the returned Python service's `proposals.get(organization, draft_id)` port to inspect saved bytes. The CLI exposes neither approval nor sending.

An identical request observes the original artifact with `observation: historical_proposal`, without recalculating its date or renewing evidence. Changed exact inputs under the same key conflict. A new key requires current evidence. Saved proposals remain historical after expiry.

Publication verifies the whole audience against the installed synthetic recipe using the frozen organization, taxonomy, size, seed and date. Candidate rows, metadata and rehashed identities cannot establish their own provenance. An omitted `as_of` uses the UTC date checked at publication; a change of date between preparation and final publication validation requires fresh preparation. An explicit ISO date remains frozen. Historical replay continues to return the original artifact.

Both checked packs retain their 25 October 2026 checked date and 24 November 2026 review deadline. This implementation does not extend that deadline. New preparation after expiry requires an actually reviewed new installed pack/profile version. Tests use a controlled clock without claiming live evidence verification.

## Contracts and ownership

| Owner | Contract | Responsibility |
| --- | --- | --- |
| `audiences` | `AudienceTaxonomy`, `AudienceSegment`, `audience/v2` | Versioned labels/descriptions and exact record membership; v1 serialization stays unchanged |
| `campaigns` | `CampaignProfile`, `ProfiledBrief`, `profile-draft/v1` | Product/profile references, country/currency/channel/objective, population, assignments and integer money |
| `creative` | `ProductProfile`, `creative-context/v4` | Product/brand/source identity, exact pack hash, voice, framing terms, fixed facts, qualifications, CTA and disclosure |
| `conversations` | `profile-plan/v1` | Freeze explicit typed inputs and profile references as an unapproved, non-executable plan |
| Campaign ports | `CampaignProfileSource`, `ProfileProposalStore` | Resolve installed campaign profiles and atomically publish the preparation bundle |
| Audience/creative ports | `ProfileFixtureAudience`, `ProductEvidenceSource` | Generate synthetic fixtures and derive their expected recipe identity; resolve product evidence without adapter selection in application services |
| `workflows` | `ProfilePreparation` | Compose public APIs without SQL or provider selection |
| Adapters/bootstrap | Local profile source and SQLite publication | Select/wire implementations, persist inputs and enforce transaction/store fences |

`CampaignService.propose` and the existing pure `build_draft` calculation serve legacy and profiled paths. Product, brand and taxonomy come from the profile; campaign selection has no company-specific branch. Deterministic A/B/no-mail assignment, budget accounting and exclusions remain shared.

The new planning contract takes explicit typed inputs. It does not establish general natural-language interpretation for another product. Profile copy uses authored hooks with reviewed factual suffixes and no semantic-screen claim. The current v3 model executor rejects v4 profile contexts before inference. A later model capability needs its own frozen assets, admission and budgets; a legacy workflow cannot stand in for it.

## Atomic publication and authority

One SQLite `BEGIN IMMEDIATE` transaction checks store policy and request identity, then writes the snapshot, scoped contexts, fixture catalogues, proposal and operation mapping. The adapter reconstructs the plan and brief from the exact frozen command and installed configuration, verifies the audience against the source port's expected recipe identity, and validates exact copy and freshness before and after proposal writes. It rolls back the entire bundle on failure. Expected recipe identities are cached only by trusted request parameters and taxonomy, without retaining candidate rows.

Rehashing a candidate cannot choose replacement product/brand authority. Context/catalogue coverage must exactly match selected segments. Organization, source, context, qualification, CTA or catalogue substitution cannot publish.

Preparation is unavailable in sealed verified-admission stores, including fixture-enabled stores. It adds no capability to their allowlist and cannot reinterpret legacy task admissions. Inspection-only roots are fenced before construction/mutation; an existing read handle can inspect saved bytes without activating work. Worker topology and browser transport checks remain unchanged.

Current review/population validation rejects `profile-draft/v1`, as does the legacy draft writer. A preparation-only artifact cannot become a supported review/handoff subject. Profiles confer no approvals or outcomes.

## Compatibility and baseline

Legacy dataclasses gain no serialized profile fields. Original snapshot, brief, creative, manifest, requested-scope and model-tool representations remain intact. Historical v1/v2/v3 interpretation and official-source URL parsing semantics stay unchanged. Profile records have explicit version dispatch and cannot be relabelled as legacy to bypass checks.

No database schema-version change or migration is needed. Existing scoped artifact tables contain explicitly versioned new rows. Older binaries reject unknown artifact/audience formats rather than reinterpret them as v1. Disable the new entry point for rollback; preserve new rows and accepted history.

The baseline is merged main `2e1a11b1c46b145e88474d97cfd54a503c58184b`, containing #25 conversational contracts, #33 execution/recovery and subsequent fixes. Existing #23/#26 work remains separately tracked. Concurrent uncommitted offline-journey evaluation changes are not incorporated or modified here.

| Baseline | Reconciliation in this slice |
| --- | --- |
| Completed #25 | Retain the original installed chat capability catalogue, frozen skills/sources, v3 model executor, exact deliverable gate and unchanged 12-scenario offline corpus. Profile preparation does not silently enroll another product into those capabilities. |
| Completed #33 | Retain authoritative admissions, the schema-v3 legacy cutoff, paused verified execution and inspection-only restore. Profile publication creates no runtime admission and refuses sealed stores; it cannot expand a verified capability allowlist. See [execution authority](execution-authority-decision.md). |
| Open #23 | Preserve the existing offline corpus and lifecycle tests as control evidence. This slice does not incorporate the concurrent complete-journey evaluator or claim a new browser journey. |
| Open #26 | Preserve exact [audience catalogue](audience-catalogue.md) selection, [review/provider](reviews.md) integrity and [recorded reporting/monitoring](learning.md) contracts. New profile audiences are separately versioned synthetic fixtures, not a substitute for a confirmed source. No provider, reporting or counted-learning extension is installed. |

Tests capture original snapshot, draft and CSV hashes independently from unchanged main and require exact equality. Real SQLite and fresh-process CLI checks cover both companies, replay, expiry at commit, concurrent requests, post-write source/catalogue mutation, tenant/product substitution, sealed stores, inspection markers and coordinated legacy downgrade attempts. These are bounded offline control checks, not live model, delivery or commercial evidence.

See [architecture](architecture.md), the [invariant ledger](validation.md) and [channel expansion plan](channel-expansion-plan.md).
