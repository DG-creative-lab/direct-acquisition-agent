# Go-to-market platform map

Date: 27 November 2026.
Status: accepted product and architecture direction; implementation remains incremental.
Owner: platform architecture under [epic #60](https://github.com/DG-creative-lab/gtm-agent-platform/issues/60).

The repository is now `gtm-agent-platform`, with GTM Agent Platform as the
working product name. The [product overview](product.md) owns current scope and
claims; the [design-partner brief](product-discovery.md) owns positioning
hypotheses. This map owns taxonomy, boundaries and implementation direction.

This is the current product-area taxonomy and responsibility map for the shared
marketing workspace. It extends the [workspace design](multichannel-workspace-design.md)
and [architecture](architecture.md). It does not claim that the proposed areas,
channel subscriptions or commerce integration are installed. Existing native
channel contracts continue to define executable behavior.

## Decision and intended outcome

Build one agent-assisted go-to-market platform with three product areas:
Direct acquisition, Advertising and Agentic commerce. A customer can use a
single channel or an explicitly enabled combination through the same workspace,
company/product knowledge, asset library and review experience.

Retain the Python modular monolith, public module APIs, narrow ports, injected
adapters and one composition root. Product categories are navigation and
packaging concepts. Channel or capability modules own business rules. A family
label is neither a universal campaign schema nor execution authority.

One main agent interprets the goal and proposes or invokes installed,
authorized capabilities. Models may plan across areas; application policy
controls access, approvals, budgets and effects. This decision does not require
specialist agents, separate VMs, microservices or a new harness.

## Product areas and delivery status

| Product area | Channels or capabilities | Business responsibility | Current boundary |
| --- | --- | --- | --- |
| Direct acquisition | Direct mail, email, human-assisted calls | Recipient/account eligibility, permissions, contact pressure, sequences, channel content and response experiments | Existing postal workflow and synthetic email/call preparation and sequence paths; no new outbound authority |
| Advertising | YouTube; future Meta and TikTok | Context/placement suitability, creative allocation, advertising constraints and channel measurement | Native authored YouTube draft/review/manual export plus offline decisioning/evaluation; no live ad buying |
| Agentic commerce | Product discoverability, product representation/content improvement, commerce readiness | Product discovery evidence, variants, protocol readiness and observed commerce outcomes | A separate source application is a future integration candidate; no destination capability installed by this map |

Agentic commerce is a capability area, not necessarily a list of advertising
channels. Future areas may use their own operational objects. Do not force
product variants or readiness assessments into mailing drafts.

The UI can group work by these areas while retaining shared chat, artifacts,
Knowledge and Learning. A single-channel customer should see a useful focused
workspace without empty future sections or an agent selector. Administrative
connections and model settings stay in the account area; activity stays inline.
The grouping is not a UI implementation specification.

## Shared platform and native modules

```text
Shared workspace, chat, artifacts, Knowledge and Learning views
                         |
Server-resolved identity, product access, roles and effect authority
                         |
Application use cases and explicit cross-area workflows
       /                       |                         \
Direct acquisition         Advertising              Agentic commerce
  Direct mail                YouTube                  Discoverability
  Email                      Meta (future)            Product variants
  Human calls                TikTok (future)          Commerce readiness
       \                       |                         /
   Narrow public APIs and ports; injected provider/storage adapters
                         |
 Shared runtime, inference admission, assets and evidence infrastructure
```

The diagram shows collaboration, not a mandatory call stack or a new generic
service. Reuse existing owners before extracting a shared component.

| Concern | Shared responsibility | Native responsibility |
| --- | --- | --- |
| Knowledge and intake | Scoped company/product source revisions, reviewed claims, citations, permitted use and freshness | Select the task's permitted context and required factual qualifications |
| Creative assets | Versioned asset identity, searchable metadata and replaceable file storage | Creative suitability, format constraints, publication purpose and approval subject |
| Agent and runtime | Task lifecycle, reservations, inference receipts, cancellation, recovery and operational activity | Skills, domain tools, valid transitions, proposal construction and effect preconditions |
| Identity and access | Authoritative tenant/actor resolution, purchased/enabled capabilities, roles and scoped connections | Required operation, native target/account and current channel constraints |
| Reviews | Reusable decision/provenance concepts and consistent review presentation | Exact subject construction, invalidation and effect-specific approval semantics |
| Evidence and learning | Provenance, versioning, diagnostics and shared inspection/review surfaces | Outcome definition, eligible population, deduplication, maturity, missingness and statistical update |
| Cross-area workflows | Explicit dependencies, aggregate resource reservations and partial-progress presentation | Independent module results and effects; no implicit cross-channel transaction |

Only explicitly permitted projections of shared knowledge and assets cross an
area boundary. An organization's record does not automatically become available
to every user, external provider or connected account. Provider credentials stay
inside the appropriate connection/adapter boundary.

## Current code ownership and target organisation

Evidence baseline: destination main `415442ebbebd0c17cb281efaf0c45af53bc50b17`
after PR #149. The architecture gate classifies 250 production modules with
zero temporary dependency exceptions.

| Current owner | Assessment | Evolution rule |
| --- | --- | --- |
| `runtime`, `reasoning`, `bootstrap.py` | Existing shared lifecycle, inference contracts and composition | Keep business rules out of runtime and provider mechanics out of application/domain code |
| `youtube` | Native channel domain, ports, commands and offline decision/reward policy | Preserve its public boundary and exact native subjects |
| `campaigns` | Intake/profile concepts alongside postal construction and email intake paths | Separate genuinely shared requirements from channel policy as a use case needs the boundary |
| `reviews`, `learning` | Useful review/statistical primitives alongside postal/sequence-specific contracts | Keep mailing acceptance, 28-day postal cohorts and native reward definitions explicit |
| `creative`, `audiences`, `engagements` | Reusable knowledge/identity concepts alongside contact and sequence rules | Do not assume all content, audiences or customer journeys share recipient/sequence semantics |
| `workflows`, workspace application, HTTP adapters | Explicit composition and transport paths | Coordinate public APIs; do not accumulate channel business rules in routing |

For example, `campaigns/domain.py:CampaignScope` currently selects direct mail,
`reviews/domain.py:validate_population` checks a mailing CSV, and
`learning/outcomes.py:cohort_proposal` requires simulated mailing acceptance.
Those contracts remain valid for their existing workflows. They are not the
shared advertising or commerce contracts.

A possible later directory layout is:

```text
<chosen_platform_package>/
  <existing shared business modules>
  channels/
    direct_acquisition/
      direct_mail/
      email/
      human_call/
    advertising/
      youtube/
  commerce/
    <native capability modules introduced with working slices>
  runtime/
  reasoning/
  workflows/
  adapters/
  bootstrap.py
```

This is a target ownership sketch, not a package migration instruction.
Keep `acquisition` as the current Python namespace until a separate, reviewed
rename. Product-area grouping must not require an immediate import rewrite.
Future boundaries should be registered in the existing architecture policy
with zero exceptions and checks against private and prohibited channel imports.
Dependency checks must cover domain, application and adapter shortcuts, while
allowing declared shared value contracts and explicit workflow composition.

Rename separately from behavior changes. Inventory imports, launch commands,
policy classifications, tests, scripts and deployment entry points. Preserve
historical evidence, database rows, capability IDs, request hashes, pinned
prompts, receipts and saved-run recovery. Moving code must not reauthorize or
repeat an old effect. Use explicit compatibility wrappers only where needed;
do not bulk-rewrite immutable artifacts.

## Channel access and customer packaging

A customer may purchase YouTube alone, one direct-acquisition channel, a selected
combination or a product-area bundle. Commercial SKU names and billing-provider
integration remain open. Define access against stable channel/capability IDs,
not directory paths, display names or the model's intent classification.

A bundle resolves to an explicit versioned set of enabled capabilities. Adding
Meta later must not silently grant it through a broad Advertising flag. Channel
IDs can group for display without making an unrelated channel executable.

For a proposed action, the application must establish all relevant conditions:

1. Current actor membership and organization/object scope.
2. Current product/channel grant and role for that operation.
3. Installed capability and eligible provider connection/account.
4. Native permissions, evidence, exact approval and available resource budget.

A channel grant does not grant approval, contact permission, provider scopes or
funding. Model catalogs, browser menus, saved receipts and cached tools do not
grant channel access. Enforce policy through the same application commands for
HTTP, CLI, agent tools and workers. Revalidate revocable authority at admission
and the appropriate commit/dispatch boundary, including resumed queued work.

On grant expiry, prevent new unauthorized effects. Already dispatched work can
still complete; reconcile its original result without redispatch. Decide the
permitted historical reads/exports and retention on downgrade before release.
A denied action should identify the blocked operation and leave permitted
channels usable. Hosted identity/connection ownership stays under #70; #130
consumes that boundary rather than introducing parallel authorization.

## Integrations and provider replacement

Ports represent supported business capabilities. Adapters implement native CRM,
email, call-task, ad-platform, reporting, storage or commerce protocol mechanics.
An adapter declares the operations and constraints it can actually support;
unsupported targeting, missing reports or uncertain execution remain explicit.

Replacement requires conformance evidence for native identity, account scope,
permissions, idempotency, errors, coverage, timing and effect recovery. Do not
assume two providers' targeting controls or metrics are equivalent. Freeze the
provider/connection and native target with an admitted action; re-resolve a new
connection for a new action. Never retarget a pending retry to a replacement
provider. Old receipts retain their original provider identities.

Customer-owned storage or CRM connections can use the same ports when supported
by scoped adapters. This map provisions no provider accounts or storage. Reuse
the [asset design](creative-asset-storage-design.md) and
[hosted preparation](hosted-platform-preparation.md).

## Recursive improvement without pooled evidence

Use the shared pattern:

```text
Goal -> proposal -> validation/review -> permitted action
     -> observed outcome -> scoped finding -> next unapproved proposal
```

The shared loop does not imply one reward, posterior or universal learner.
Direct mail may measure business responses with a no-mail control; YouTube's
contract targets qualified demo actions; commerce may inspect discoverability
and separately collect observed commercial outcomes. Model judgments,
simulations, preferences and measured outcomes retain different provenance.

Cross-area attribution must identify the same real event before claiming
combined performance. A demo action followed by an order cannot become two
independent successes merely because two connectors reported it. Until an
explicit attribution contract exists, show separate native metrics and avoid
a combined conversion rate, posterior or causal lift claim. Missing observations
stay unknown and channel-specific eligibility rules remain in force.

Guidance may transfer as a scoped hypothesis with evidence references and
ordinary review. It cannot carry approval, measured support or causal authority
into another channel. Source edits and new evidence invalidate affected
proposals under the native currentness contract. Synthetic evidence cannot be
promoted into real-world outcome support.

## Commerce integration boundary

The separate `deep-dive-analysis-agentic-commerce-augmentation` repository is a
candidate source for commerce-specific capabilities, not the platform host
selected by this decision. Its canonical modernisation plan and workflow ADR
describe chat, governed capabilities, durable workflows, approvals, belief and
memory. Its implementation uses separate domain/application/infrastructure
layers and its own runtime and identity concepts.

The 27 November scope check inspected its README, modernisation plan,
architecture documentation, workflow ADR and belief-update service. The local
checkout had uncommitted work on top of `d8298cf59187e25b335c0e5f953f7335eb4e7fc1`.
This is not a pinned implementation audit, parity claim or authorization to
copy the working tree. No commerce tests or hosted integration were run.

Before migration, inventory native capabilities, data/schema history,
identities, approval subjects, learning semantics, protocol adapters and
source permissions. Choose one authoritative workspace identity, connection
store, runtime and inference admission path in the destination. Source-specific
lifecycle behavior needs a compatibility mapping and recovery tests; do not
retain competing owners by default or replace the destination harness merely
because source terminology is similar. Import only selected, reviewed
capabilities after this contract is accepted.

## Representative system outcomes and acceptance

| Scenario | Expected composed behavior and evidence |
| --- | --- |
| YouTube-only customer asks for a draft | Shared permitted context produces a native unapproved YouTube artifact; direct-mail/email/commerce effects remain unavailable |
| User requests an email plus a YouTube draft | Resolve enabled capabilities and explicit intent; clarify material ambiguity; compose separate native commands when supported without granting either approval |
| Approved YouTube work plus proposed commerce change | Track dependencies and separate subjects; failed or unauthorized commerce work does not silently block an independent approved YouTube action or report the entire plan complete |
| Channel disabled after a task is queued | Worker/effect boundary rejects new unauthorized effects with zero dispatch; original in-flight receipts remain reconcilable |
| Identity, storage or provider capability unavailable | Return a specific blocked/unknown state; do not substitute a local operator or a different provider |
| Two channel tasks share a campaign/model allowance | Reserve against the same owned aggregate budget; no parallel overspend or repeated charge after ambiguous receipt recovery |
| Provider changed after interrupted dispatch | Recover the original effect identity; a replacement connection cannot replay it as new work |
| Same conversion appears in two reports | Retain native provenance and deduplicate under an explicit attribution contract; otherwise withhold a combined estimate |
| Old saved run resumes after package cleanup | Same pinned context/request identity and authority checks; no extra provider effect caused by a code move |
| New channel or commerce capability added | Public contract and adapter checks pass, existing channel journeys remain unchanged, and access is not granted by family membership alone |

These are future implementation acceptance requirements, not newly passing
runtime tests. Verify through public commands with authored data, real durable
storage and restarts where relevant. Add browser evidence for exposed journeys
and separately authorized live evidence for provider compatibility. Evaluate
usable results, denied/incorrect effects, outcome validity, recovery, cost and
latency rather than only the model's answer quality.

## Build sequence and coordination

| Order | Work package | Existing coordination | Completion evidence |
| --- | --- | --- | --- |
| 1 | Accept this taxonomy and ownership map | #60 and migration epic #128 | Shared links identify current implementation versus proposed areas |
| 2 | Inventory and extract the next necessary channel policy boundary; add executable isolation checks | A follow-up architecture slice to scope under #60 | Postal/sequence/YouTube behavior preserved; prohibited cross-channel paths fail the gate |
| 3 | Continue trusted YouTube measurement and reviewed reuse | #143/#144 handoff into #133 | Native qualified outcome contract, currentness, missingness and scoped reuse verified without postal assumptions |
| Parallel platform track | Implement authoritative hosted membership, channel grants, connection scope and composed access | #70 / #130; asset foundation #140 / #141 | Authorized single-channel journey, guessed IDs, grant revocation and cold-start recovery verified |
| 4 | Release the bounded hosted YouTube journey | #134 / #74 | Actual hosted parity evidence and explicit cutover decision |
| 5 | Define and validate one commerce capability migration | New work to scope after a source/destination gap review | Native contract, single shared authority/runtime ownership and compatibility evidence |
| Separate optional cleanup | Decide whether to migrate the Python namespace after the repository rename | A separately scoped compatibility change | Entry points and old saved work preserved; historical evidence unchanged |

The minimum boundary work for #133 should follow its actual dependencies; a
wholesale directory migration is not a prerequisite. Hosted access work may
continue in the iwoca thread while this thread owns YouTube contracts.
Shared schema, bootstrap, HTTP and access changes need one integration owner
and an agreed base revision before parallel implementation.

This slice creates no new GitHub issues and does not mark existing issues
complete. The references above are coordination points; issue owners must
scope any additional implementation acceptance before starting that work.

## Open decisions

- Customer-facing brand beyond the working product name and any later Python namespace migration.
- Exact customer bundles, billing integration and historical access after downgrade.
- First commerce capability to migrate and any data-import/rollback requirements.
- A future cross-area attribution contract, if combined performance is needed.
- Whether later use cases justify specialist delegation; the initial model remains one agent.
- Provider-specific compatibility and performance, to be established with scoped evidence.

No code move, UI implementation, commerce import, paid inference, external
campaign effect, cloud provisioning or deployment is authorized by this map.
