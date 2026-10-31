# Versioned agent contracts

This first slice of [issue 25](https://github.com/DG-creative-lab/direct-acquisition-agent/issues/25) adds authored skills, installed model-tool descriptions and scoped knowledge manifests to the existing planner and grounded-copy workflows. These are reasoning assets, not a new executor or permission system.

## What is installed

`config/agent-skills-v1.json` defines three skills:

- `prepare-campaign/v1`: brief interpretation, clarification and unsupported requests.
- `grounded-copy/v1`: source-bound A/B drafting and screening.
- `revise-grounded-copy/v1`: targeted revisions preserving the sibling and product wording.

Each skill declares purpose, applicability, required source kinds, guidance, tool references, expected outputs, validation requirements and stop conditions. The fields describe the procedure. Existing Python services continue to enforce the actual checks, budgets and stopping rules. Outcome interpretation and general conversational action selection remain later slices.

The tool contracts are constructed from installed wire schemas, not loaded as callable code from a skill:

| Contract | Existing tool | Effect |
| --- | --- | --- |
| `submit_campaign_brief/v1` | Brief planner submission | Propose a brief, clarification or unsupported result |
| `read_editorial_context/v1` | Read the exact frozen copy context | Read task data |
| `submit_grounded_copy/v3` | Submit a pair and supplied product fact selections | Propose unreviewed framing |
| `record_claim_check/v1` | Record the separate semantic screen | Advisory screening |

Contracts include server-resolved scope, preconditions, outputs, failure/replay semantics and a reference to the existing frozen inference limits. They grant no approval or dispatch authority. Skills cannot add tools, change their schemas or grant new effects. The copy tool's recorded schema is its installed base contract; the actual request further narrows fact/evidence IDs to the current context. The screening request keeps its existing separate context without reviewer preference memory.

## Source manifests

The generic serialization/integrity rules live in the public `reasoning` API. Module-specific source roles and supported skill/tool selection are checked by the planner and creative workflow. `bootstrap.py` loads local authored files and binds those contracts to the existing services.

Planning receives manifests for its procedures and campaign playbooks. It does not receive product facts as planning guidance. Grounded copy and follow-ups receive separate manifests for editorial guidance, the actual product pack, scoped preferences, synthetic outcome memory and the synthetic audience summary.

Each manifest binds organization, exact content hash, source key, version, owner, provenance, freshness basis and permitted use. Sources are not interchangeable:

- Authored procedures guide reasoning.
- Product evidence grounds the code-rendered product wording, subject to existing fact-pack validation.
- Reviewer examples guide style and do not attest performance.
- Synthetic cohort memory informs hypotheses and does not grant approval or add product facts.
- Synthetic audience summaries describe supplied records and do not attest a recipient's financial need.

Freshness metadata records the source basis. It is not a cached declaration that the evidence is currently valid. The existing pack freshness and review/acceptance checks continue to run at their original boundaries.

## Freeze, replay and revision

New service-created planning admissions contain an `agent_assets` bundle inside their frozen knowledge. Creative contexts contain the corresponding bundle inside their existing content-addressed payload. The bundle includes the selected skill payload, installed tool contracts and source manifests, plus an organization-bound content identity. Construction deep-copies the input values before hashing.

Changed current skill text affects new admissions, not saved work. A fresh process can reconcile the original planning request without rereading the current authored catalogue. Execution validates a saved bundle against the tool schemas that executor actually supports; an unsupported schema cannot become callable by describing itself as installed. Supporting a changed tool protocol will require explicit compatibility handling.

A new targeted revision selects the revision skill while preserving every actual base-context value and the exact targeted feedback. The admission transaction permits only this validated asset-metadata replacement; it still rejects changes to audience, product evidence, preferences, learned observations, sibling text or base identities. The previous context remains immutable. Replay of an already admitted revision uses its original saved context.

Existing unannotated planning tasks and v3 creative contexts retain their original interpretation. They are not silently rewritten as skill-annotated artifacts. The additive metadata does not replace grounding or create a new authorization gate. Legacy v1/v2 behavior and the v2 admission cutoff remain unchanged.

## Inspection and remaining work

The guarded, read-only `/api/knowledge` endpoint includes `agent_catalogue`, labelled `installed_contracts_not_dynamic_dispatch`. Planning inspection already returns the full frozen knowledge, including its bundle; creative contexts retain their exact bundle in persistence and existing context exports. The catalogue shows current installed descriptions, not which sources a historical run read or whether a tool invocation succeeded.

This slice has no new user-facing action router, source editor, privileged role, learning tool, delivery connector or dynamic skill execution. It does not make validation requirement names into automatic checks. The unified result-validation report and chat routing from issue 25 remain separate work.

## Verification boundary

Real SQLite tests exercise frozen content, scoped source roles, unavailable tool references, source coverage and content mismatch, unsupported wire schemas, new versus historical guidance, fresh-process replay without current files, legacy unannotated work and a separately annotated revision without inherited approval. Existing revision tests continue to exercise exact-base validation and transactional authority. Declared mutation checks remove installed-schema matching and skill/tool membership and must be detected.

No live model quality claim follows from these fake-provider and offline checks.

Verified for this slice: 275 backend tests, 51 existing browser tests, all 51 declared mutation probes, architecture checks, frontend build/formatting and whitespace checks passed. The final backend run includes the exact-base revision guard and the nine new asset tests. Contract metadata shares the existing model input budget; this slice does not raise model limits. No paid model call was made.

## Copy-envelope and frozen follow-up corrections

New copy bundles declare `model_projection: copy-context/v1`. The model receives selected skill content and source identity/role references, while full tool schemas and manifests remain in the immutable server context. The request already supplies the actual permitted tool schema. Compaction removes duplicate schema metadata without truncating reviewer examples or changing their content.

For new projected contexts, before the first context-read provider call, the copy workflow checks both that request and the complete initial submission request, including the context-read exchange, against the unchanged input budget. New projected contexts use a stable validated read acknowledgement so provider-generated read prose or identifiers cannot change the preflighted submission envelope. Later generated proposals/repair requests retain the existing per-call limits. Historical unprojected contexts preserve their original read transcript and request format for recorded-call replay.

When follow-up preparation supplies frozen context IDs, model startup checks exact selected-segment coverage, scoped context identity and saved product-pack freshness. It does not load current editorial/skill files, read current preference/learning snapshots or write replacement contexts. Existing population, evidence epoch, inference reservation and approval checks remain in force.

Regressions exercise three maximum-size reviewer examples per segment, over-budget submission rejection with zero provider calls/reservations, old copy transcript compatibility, and saved follow-up preparation after the current catalogue is changed or unavailable. Mutation probes remove full-envelope preflight and frozen-context reuse and must be detected.

After these review corrections: 279 backend tests, 51 browser tests, 53/53 declared mutation probes, architecture, build/formatting and whitespace checks passed. No paid model calls were made.

Legacy input-boundary correction: unprojected contexts do not preflight an invented read exchange. They replay the original recorded provider response and size each actual request through the original inference path. A real-SQLite regression sets the limit to the exact original submission size, proves the synthetic exchange is larger, and completes replay with no duplicate read call. New projected contexts retain stable full-submission preflight before dispatch. A mutation that applies synthetic preflight to legacy contexts must fail this regression.

Verified after the legacy boundary correction: all 280 backend tests and 54/54 declared mutation probes passed, alongside architecture and whitespace checks. No paid model calls were made.

## Read-only audience source contracts

The installed catalogue also describes `list_audience_datasets/v1` and `read_audience_dataset/v1`, backed by the scoped audience source service. Their replay and limits describe read-only source access rather than model-call journal replay. They are not offered to the current planner or copy tool loops and do not change historical asset bundles. See [audience catalogue](audience-catalogue.md) for exact selection and the deferred conversational binding.
