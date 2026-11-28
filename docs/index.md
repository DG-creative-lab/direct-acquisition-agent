# Documentation

Start with the product, then choose the guide for the workflow you need.
The repository is now [GTM Agent Platform](https://github.com/DG-creative-lab/gtm-agent-platform);
Python packages and commands still use `acquisition`.

## Maintained entry points

| Question | Read or update here |
| --- | --- |
| What are we building, for whom, and what can we claim today? | [Product overview](product.md) |
| How do we explain the first use case and test demand? | [Design-partner brief](product-discovery.md) |
| Which product areas, channel boundaries and shared services are intended? | [Platform map](gtm-platform-map.md) |
| What does the code own and how do ports/adapters connect? | [Architecture](architecture.md) |
| How do I start, stop, configure or recover the local app? | [Local operations](workspace.md) |
| What verification exists and what does it establish? | [Validation](validation.md) |

The product overview is the capability/status reference. Topic guides own their
detailed operating contracts. The platform map owns accepted direction.
The discovery brief contains hypotheses and copy to test, not market evidence
or a second feature roadmap.

## Use the current workflows

| Job | Guides |
| --- | --- |
| Explore company-independent examples | [Examples index](../examples/README.md), [fictional Fielddesk proposal](../examples/fielddesk-profile/README.md), [reviewed intake email preparation](intake-email-preparation.md) |
| Inspect the legacy postal simulation | [Compatibility scope](legacy-product-demo.md), [user guide](user-guide.md), [campaign validation](campaign-validation.md), [review contract](reviews.md) |
| Save company/product assertions and brief requirements | [Intake](intake.md), [intake planning](intake-planning.md), [reviewed preparation context](reviewed-preparation-context.md), [preparation eligibility](preparation-eligibility.md) |
| Produce a synthetic email export from reviewed intake | [Intake email preparation](intake-email-preparation.md) |
| Rehearse email and human-call sequences | [Conversational sequences](conversational-sequences.md), [sequence simulation](sequence-simulation.md), [sequence review](sequence-review.md), [channel content](channel-content.md) |
| Prepare, review and manually export a YouTube draft | [YouTube preparation](youtube-preparation.md) |
| Inspect contextual recommendation and model-evaluation tools | [YouTube contextual benchmark](youtube-contextual-benchmark.md) |
| Understand synthetic learning and recorded external results | [Learning](learning.md), [external outcomes registry](external-outcomes.md) |

The YouTube benchmark and external outcomes registry are separate capabilities,
not new steps automatically invoked by the chat demo. External results are
operator-attested. Synthetic sequences and authored placements do not become
live delivery when a model connection is present.

## Knowledge, agent behavior and evidence

| Topic | Guides |
| --- | --- |
| Product grounding and permitted facts | [Grounding](product-grounding.md), [organization profiles](organization-profiles.md) |
| Audience source identity and selection | [Catalogue](audience-catalogue.md), [audience strategies](audience-strategies.md), [contact evidence](contact-evidence.md), [recipient context](recipient-context.md) |
| Saved conversations, amendments and copy feedback | [Conversations](conversations.md), [follow-ups](conversational-actions.md), [targeted copy revision](conversational-copy-revision.md), [writing preferences](writing-preferences.md) |
| Model connections and execution limits | [Model integration](model-integration.md), [agent contracts](agent-contracts.md), [execution controls](execution-controls.md), [budget clarification](budget-clarification.md) |
| Admission, ownership and compatibility | [Run ownership](run-ownership-admission.md), [execution authority](execution-authority-decision.md), [requested scope](requested-campaign-scope.md), [legacy migration](legacy-migration.md), [company-context migration](company-context-migration.md), [checkpoints](workspace-checkpoints.md) |
| Presentation | [Branding](branding.md); the [workspace design](multichannel-workspace-design.md) describes the target experience |

## Direction and remaining delivery

| Topic | Current planning reference |
| --- | --- |
| Shared product and channel ownership | [Platform map](gtm-platform-map.md), [workspace design](multichannel-workspace-design.md) |
| YouTube implementation sequence and cutover | [Migration plan](youtube-migration-plan.md) |
| Trusted targeting data, qualified outcomes and offline decisioning | [Feasibility design](targeting-decisioning-feasibility.md), [reward contract](youtube-data-reward-contract.md), [targeting verification](youtube-targeting-verification.md), [contextual research](contextual-targeting-research.md) |
| Hosted identity, UI/API composition and release gaps | [Hosted preparation](hosted-platform-preparation.md) |
| Implemented storage and bounded serverless preparation | [Remote storage](remote-storage.md), [serverless preparation](serverless-preparation.md) |
| Shared assets and proposed remote file storage | [Creative asset design](creative-asset-storage-design.md) |
| Scaling beyond the current topology | [Scaling](scalability.md) |

The [channel expansion plan](channel-expansion-plan.md) retains the original
Direct acquisition proposal and dated implementation history.
[Hosting feasibility](hosting-feasibility.md) and the
[MVP deployment plan](mvp-demo-deployment.md) retain earlier probes and design
choices. Read them alongside the current hosted preparation and implemented
storage guides; their older gap lists are not a fresh feature-status inventory.
Research, accepted contracts and fake-provider tests do not establish current
live account capability or a deployed end-to-end product.

## Engineering verification and retained history

[Boundary verification](hexagonal-boundaries.md) explains the finite offline
recovery corpus. The [CI gate audit](ci-gate-audit.md),
[CI performance](ci-performance.md) and
[test-suite performance](test-suite-performance.md) describe gate purpose,
cadence and measured execution choices.

Dated reports under [evaluations](evaluations/) and versioned example artifacts
are retained evidence. Their commit, environment, fixtures and limitations are
part of their meaning. Preserve those bytes and historical names; do not update
them to make a repository rename or new pitch appear implemented.

When behavior changes, update the owning topic guide and product status.
When only packaging or positioning changes, keep operational commands, stored
identities and historical evidence intact.
