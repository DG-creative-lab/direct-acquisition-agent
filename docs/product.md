# Product overview

Direct Acquisition Agent helps an acquisition operator turn a supplied audience into a reviewable direct-mail experiment, then use observed responses to inform the next proposal. Its central object is the campaign: an exact audience, creative set, assignment plan, evidence pack and cost estimate that a reviewer can inspect together.

The demonstration targets two working-capital situations, stock/inventory and projects/contractors, using synthetic business records and public iwoca Flexi-Loan evidence. These segments illustrate a workflow. They are not validated iwoca customer segments or a live targeting feed.

## Users and decisions

An **operator** prepares campaigns, inspects exclusions and assignments, records suppressions, rebuilds proposals and requests simulated handoff. A **reviewer** approves or rejects an exact proposal and can revoke a decision. The local sandbox configures these identities for demonstration; it does not authenticate distinct people or enforce production separation of duties.

The agent proposes audience-specific headlines and hooks using editorial guidance, reviewer preferences and mature synthetic learning memory. A person remains responsible for evaluating the complete message and experiment. Approval grants authority only for the local handoff simulator.

## The campaign as a controlled experiment

The supplied audience already has segment and propensity metadata. The application does not train a segmentation model. It excludes ineligible, unusable or suppressed records, resolves duplicate business identities conservatively and selects a bounded cohort. Within each segment it randomizes enrolled businesses into A, B and no-mail groups. Controls come from the same selected population as treatments.

The campaign manifest binds source snapshot, creative identities, experiment assignments, counts, money and exported file hashes. Currency calculations use integer pence. Source population counts reconcile with exclusions, controls and mailing recipients. A high-score selected cohort does not represent all businesses, so observed lift cannot be generalized to a wider market without further evidence.

## Copy that can be inspected

Offline mode supplies known fixture messages. Model mode reads frozen segment context and proposes contrasting copy. Code controls allowed product facts, required qualifications, fixed CTA, output contracts and deterministic claim constraints. A separate model request screens framing against the fact pack. A passing screen is advisory and can be wrong.

Reviewer preferences and counted outcome memory are different inputs. A preference describes writing judgment; an outcome contributes statistical support only after a complete cohort matures. Neither changes verified product facts. Rewritten copy receives a new identity and does not inherit approval or response counts. A targeted copy request preserves the existing audience, assignments, budget and product wording while changing the selected hook; the new subject requires review.

## Review and change control

A review subject binds the exact draft to the case revision, audience, current evidence and suppression epochs, policy and simulated-handoff purpose. Approval also binds reviewer generation and expiry. The server rechecks these conditions when accepting a simulated job, rather than trusting the page or a saved approval receipt.

A late suppression invalidates the current subject. Rebuilding produces a new proposal, which needs a fresh decision. Evidence or policy changes, rejection, revocation, reviewer changes and expiry can also prevent acceptance. Accepted history remains immutable; a later event cannot undo an already accepted simulation.

## Learning with explicit denominators

A cohort opens from accepted assignments, including no-mail controls. Missing observations remain unknown. Complete, mature synthetic outcomes update Beta posterior counts once and support a within-cohort comparison between variants and control. Recommendations explain their sample support and uncertainty.

The next experiment is another proposal, not an automatic campaign change. The current independence rule rejects a second learning cohort containing a business already counted in that organization. A descendant campaign can demonstrate reuse of memory, but repeated exposure prevents treating its outcomes as new independent support.

## Implemented scope and limits

| Capability | Current behavior | Further work |
| --- | --- | --- |
| Conversation | Persistent chat, bounded brief planner, continuous background preparation with explicit copy consent, saved progress, in-chat review, targeted copy revision and confirmed simulated handoff with accepted exports and explicit synthetic learning with frozen follow-up proposals and independent-population preparation | Real audience sources and delivery |
| Audience | Seeded synthetic source, supplied segment/score metadata, deterministic exclusions | Verified warehouse/CRM feeds, data rights and completeness contracts |
| Copy | Offline fixtures or bounded OpenRouter generation with source pack and screen | Broader product packs, calibrated evaluation and editorial operations |
| Approval | Exact-subject local decisions, expiry, invalidation and simulator recheck | Hosted identity, tenant membership and enforced separation of duties |
| Delivery | Local agency acceptance simulation and exact exports | Real dispatch, delivery acknowledgements and uncertain-effect reconciliation |
| Outcomes | Explicit synthetic results, 28-day maturity, immutable cohorts | Real attribution feeds, corrections, retractions and repeated-exposure modeling |
| Operations | One local server and one active worker with SQLite persistence | Hosted deployment, measured concurrency, service operations and recovery validation |

Synthetic mailing cost and provider inference cost are separate. Neither demonstrates incremental revenue or profit. The product does not assess lending eligibility, make credit decisions, approve a financial promotion, autonomously modify code or train its model weights.

Start with the [user guide](user-guide.md), then inspect [architecture](architecture.md) and the [scaling path](scalability.md). The [validation guide](validation.md) states what the existing tests establish and what remains unproven.
