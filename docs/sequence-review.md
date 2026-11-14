# Exact multichannel sequence review

Issue #67 adds a separate review purpose, `simulated_multichannel_sequence/v1`,
for the complete synthetic sequence from #66. An agent can prepare, validate,
open, inspect and advance work. A local accountable reviewer approves one exact
subject for the bounded sequence. No approval dialog is needed for each step.
The installed adapters still perform no live email, call, CRM write or spending.

## Decision and ownership

This is a focused workflow extension from immutable campaign/content inputs to
synthetic effect admission, settlement and operator output. Existing executable
contracts confirm the division: audiences attests source-native identity and
permission; creative owns grounded recipient rendering; campaigns owns the
population, experiment and sequence bounds; reviews owns validation completeness
and human approval; engagements owns reservations, lifecycle and observations.
The generic runtime and frontend are unchanged.

`SequenceReviews` depends on a narrow store port. `EngagementStore` receives an
engagements-owned `SequenceEffectAuthority` port whose SQLite implementation
checks authority in the caller's transaction. Bootstrap wires the adapters.
Engagements does not import reviews or its private implementation. No new module
cycle, event bus, provider registry or shared business model is introduced.

The exact subject embeds the original proposal, including all materialized
personalization, every native target, assignment/control, sender, provider
account, source connection, assignee, cadence, costs, capacities and stop scope.
It also freezes the organization's current immutable source-history identities,
objections, global engagement stops, postal suppression state and existing
review authority epochs. These epochs are deliberately conservative across the
organization: new source evidence can require a fresh review even when it does
not change the selected recipient. Restoring earlier product-pack bytes does
not restore an earlier epoch or approval.

## Required validation

| Required check | Independent authority and observable failure |
| --- | --- |
| `artifact_identity` | Saved proposal and original exact preparation command must agree with the subject. A substituted request or artifact fails. |
| `audience_permissions` | Audience-owned decision reconstruction and current source readiness bind the selected native account population, source purpose and email permissions. Human-call permission and current recipient context are additionally checked for every call payload. |
| `recipient_payloads` | Creative re-renders every payload from its frozen context and recorded proposal, validates the full recipient population and advisory screen, checks completed task/run identity, then rechecks current product/context/contact evidence. A status label or internally rehashed text cannot replace this provenance. |
| `sequence_contract` | Campaign-owned reconstruction checks exact assignments and controls, provider capabilities, all three materialized stages, sender bytes, costs, capacity, validity windows, ordered distinct cadences and stop conditions. Current native engagement objections are checked independently. |
| `current_epochs` | Current scoped durable evidence, objection and suppression history must match the reviewed basis. |

Each check reports `passed`, `failed`, `unknown` or `not_evaluated`. Required
membership belongs to reviews, not to the submitted report. Missing checks are
not evaluated, downgrading a required check is rejected, and checker exceptions
become unknown. Only all required passes establish review readiness. Recorded
semantic screening remains advisory and cannot grant human approval.

`preview` supplies diagnostics before a review is opened. `view` revalidates a
saved subject. On failed or unknown validation, both withhold substantive
sequence content and the operator summary while retaining exact subject and
proposal IDs and check diagnostics. The original immutable artifacts remain
available through their historical inspection APIs.

## Approval and effects

Only a currently enabled local reviewer can decide. These roles reuse the
existing trusted local actor administration, not hosted authentication.
Decisions are immutable and bind purpose, exact subject, reviewer generation,
request key, decision time and expiry. Lifetime is at most fourteen days and is
clipped to the sequence and known evidence validity bounds. Postal approvals
cannot be read as sequence approvals; neither purpose grants live authority.
A later decision, revocation, expiry, reviewer disable/re-enable, changed epoch,
source, recipient material or installed connection blocks the old approval.

New simulation enrollment requires the explicit exact approval ID. Its durable
binding, enrollment population, steps, event and command receipt commit together.
Every effect reservation and completion rechecks the current approval and
required validation inside the writer transaction, including after writes.
Lease and stop checks remain in force. An exception, changed authority or
expired lease rolls back authoritative transitions.

A provider observation may arrive after revocation or lease loss. It is retained
as an immutable observation, not accepted as continuation authority. Unknown or
partial submissions still do not retry. A new request key or cached receipt
cannot expand approval, duplicate enrollment or repeat an effect. An approval
cannot be replaced under an existing simulation; changed work needs a new
proposal and review. An objection stops its native scope and also invalidates
the approval of the whole reviewed population.

The simulation inspector separately labels recorded synthetic approval and its
current applicability. Its counts describe validated submission/observation
facts, never readiness or live authority. A completed historical submission set
with no current approval is `historical_submissions_complete`.

## Operator output

`validate_output` accepts only the bounded structured summary of validated saved
facts for the exact current subject. It rejects invented counts, costs, omitted
population facts, substituted subjects, extra praise or arbitrary prose.
Unconstrained model-written summaries are not supported by this slice. The
summary states synthetic mode and grants no execution authority. It must be
revalidated when used; its saved ID or previous success is not authorization.

## Agent-facing use

Given the proposal and manually configured `operator` and `reviewer` roles:

```python
review = app.reviews.open(org, "review-open-v1", proposal["proposal_id"], "operator")
view = app.reviews.view(org, review["subject_id"])
# Present the exact view for the reviewer's accountable decision.
approval = app.reviews.decide(
    org, "review-approve-v1", review["subject_id"], "reviewer", "approve",
    "Exact synthetic population, payloads and sequence reviewed", 7 * 86400,
)
simulation = app.engagements.start(
    org, "simulation-v1", proposal["proposal_id"], approval["id"],
)
progress = app.engagements.advance(org, simulation["simulation_id"])
```

The standalone `acquisition.sequence_cli` adds `review-preview`, `review-open`,
`review-show`, `review-decide`, `review-revoke` and `validate-output`. `start`
requires `--approval-id`. Use each command's `--help` for exact options. Existing
`acquisition` CLI `review-actor` commands administer local roles. No new UI
forms, network endpoints, model calls or provider credentials are needed.
Conversational orchestration remains #68 work.

## Migration and limits

Schema 21 to 22 adds six immutable tables for subjects, decisions, revocations,
commands, review events and simulation-approval bindings. It does not rewrite
existing rows or backfill approvals. Failed migration rolls back DDL and version
atomically; the schema-v3 admission cutoff remains untouched. New binaries can
inspect schema-21 sequence checkpoints without migrating them. Restored roots
remain inspection-only. Prior binaries reject schema 22, so rollback requires
a pre-upgrade backup.

Historical unapproved simulations remain inspectable, stoppable and able to
record observations for already accepted effects. They cannot reserve new
effects. This deliberate change closes the former unapproved simulation entry
point. It preserves historical facts without upgrading them into authority.

The supported product remains a local modular monolith with per-proposal
synthetic cost/capacity bounds. This work does not prove distributed dispatch,
production quotas, provider-specific regulatory permission, real model quality,
live delivery, retention/deletion compliance or hosted authentication.
