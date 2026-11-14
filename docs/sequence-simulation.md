# Multichannel sequence proposals and simulation

Issue #66 adds an agent-callable API/CLI for a complete synthetic email and
human-call strategy. It consumes the frozen audience decision from #63 and the
validated recipient artifacts from #65. It prepares an immutable proposal, then
runs an explicitly requested offline simulation. It does not grant approval or
outbound authority. [Exact sequence review](sequence-review.md), added in #67,
is now required before new simulated effects. Conversational continuation belongs
to #68.

## Ownership and authority

`campaigns` owns `SequenceRequest`, `SequenceConnection`, the frozen population,
strategy arms, controls, schedule, integer-pence limits and proposal identity.
`SequenceCampaigns` depends on `SequenceProposalStore`. The new `engagements`
module owns enrollments, step transitions, submission observations, replies,
native stops and accounting. `EngagementSimulator` depends on `EngagementStore`
and narrow `SimulationTransport` ports. Its pure domain imports only standard
library, serialization helpers and declared public campaign contracts.

`bootstrap.build_sequence_simulation` wires current contact/content/decision
adapters, SQLite stores and synthetic email/task transports. The workflow layer
composes the two public services. The architecture checker declares the acyclic
edge from engagements to campaigns and rejects provider or runtime business
imports. The existing generic runtime is unchanged.

The simulator's bounded `advance` command reserves a domain-specific effect
before calling a transport. This reservation is separate from generic task
retry: an expired uncertain submission becomes unknown, never another attempt.
A later conversational host can compose this public capability without moving
engagement rules into runtime.

## What is frozen

One proposal contains at most six account experiment units. It retains the
exact #63 contact, native account, strategy arm and control assignment. A score
does not grant eligibility and cannot enter content as a recipient fact.

Each treatment has three materialized steps:

1. An initial personalized email.
2. A human call task assigned to a named synthetic representative.
3. A personalized follow-up email.

The initial cadences are explicit: arm A schedules the call after one day and
follow-up after three days; arm B uses two and four days. Request fields can
set different bounded cadences, but the arms must remain distinct. Every step
binds its content/bundle/context identities and bytes, exact contact/account,
source connection, synthetic sender/task capability, assignee, due time,
expiry, unit cost and contact/account stop scope. Controls receive an enrollment
and no steps or charges.

The caller supplies the budget, total call capacity, total step capacity and
schedule bounds. Costs are explicitly synthetic estimates in GBP minor units.
The default email/task unit estimates are 2p/100p and are editable request
inputs. Worst-case treatment cost and capacity must fit before publication.
These are per-proposal allocations, not production-wide quotas or live queue
availability. Known frozen source validity windows must cover scheduled steps;
current evidence is still rechecked later because it can change independently.

Current product packs, recipient contexts, native readiness, audience derivation,
all three content stages and installed connections are reconstructed in the
proposal transaction. A native objection already recorded by engagements blocks
a new proposal containing that treatment unit. No proposed strategy silently
removes a control, substitutes a colleague or changes the frozen selection.

## Submission and observation lifecycle

A simulation enrolls a proposal once, including controls. A new request key for
the same proposal retrieves that simulation instead of creating another
treatment history. Enrollment and step identities are stable across restart.
Reusing a command key with different inputs fails.

Different proposals are distinct explicitly requested simulations. Production
campaign revision, cumulative exposure limits and cross-campaign outcome
deduplication require their own authority and learning contracts.

For each due step, a write transaction checks current content/readiness,
connection, scope, stops and expiry, then reserves an exact effect key and lease.
The installed email/task adapters perform no network I/O. They return accepted,
rejected or partial results, or simulate a timeout. Their configuration identity
is frozen for the simulation; a different configuration cannot continue it.

The provider receipt is a write-once observation. It can survive stop, source
change, process loss or lease expiry without authorizing another step. Step
result and lifecycle event updates occur together under a current lease, with
final source/stop checks. A late acceptance can therefore be visible as a
transport fact while the orchestration step remains stopped, blocked or unknown.

An accepted email is not implicitly delivered or answered. An accepted call task
is not a completed call. The observation API explicitly simulates delivery,
bounce, reply, objection and human task completion, binding each to the exact
accepted provider effect and a valid occurrence time. Replayed observations are
deduplicated across request keys. Contradictory delivery facts require a future
correction contract; the current slice rejects them.

A reply pauses the configured contact or account's pending steps in that
simulation. An objection stops that native scope across simulations in the
organization and blocks fresh proposals that would target it. A user stop
cancels all pending steps in the simulation. In-flight facts remain observable;
stopping cannot undo an already submitted effect. Neither a bounce nor a
rejection grants call permission: the call was already in the proposal and must
pass its own current channel checks. A follow-up waits for explicit completion
of an accepted human task. It never assumes a conversation happened.

Native objections follow attested contact/account merge ancestry, including
transitive merges and connection aliases, during proposal checks, step checks
and pending-step updates. This carries a constraint to surviving identities;
it never rewrites historical targets or supplies permission to contact them.

Unknown or partial submissions block dependent steps and retain their maximum
unresolved cost. An expired reservation without a receipt becomes unknown.
There is no automatic retry, provider switch, live reconciliation or automatic
reply. Read-only inspection explains pending timing and human-completion waits.

Accounting reports confirmed submission cost separately from unresolved maximum
cost, accepted messages/tasks separately from delivery and completed tasks, and
unique responding account units separately from response observations. These
are synthetic operational observations, not conversions, causal lift or counted
learning support. No learning cohort is created.

## Agent API and CLI

Given current decision and content preparation keys:

```python
from acquisition.bootstrap import build_sequence_simulation
from acquisition.campaigns import SequenceRequest

app = build_sequence_simulation("application.sqlite", "example-org", "fielddesk")
request = SequenceRequest(
    profile_key="fielddesk", decision_request="selected-audience",
    initial_content="initial-emails", call_content="call-scripts",
    followup_content="followup-emails", starts_at=start_timestamp,
    expires_at=end_timestamp, budget_pence=10000, call_capacity=6, step_capacity=18,
)
proposal = app.campaigns.prepare("example-org", "sequence-v1", request)
review = app.reviews.open("example-org", "review-v1", proposal["proposal_id"], "operator")
# Present app.reviews.view(...) to the accountable local reviewer.
approval = app.reviews.decide("example-org", "approval-v1", review["subject_id"],
    "reviewer", "approve", "Exact synthetic sequence reviewed", 7 * 86400)
simulation = app.engagements.start("example-org", "simulation-v1", proposal["proposal_id"], approval["id"])
progress = app.engagements.advance("example-org", simulation["simulation_id"])
```

The standalone entry point is `PYTHONPATH=src python3 -m acquisition.sequence_cli`.
It requires `--db`, `--organization` and `--profile`. Commands are `propose`,
`inspect-proposal`, `start`, `advance`, `inspect`, `observe` and `stop`. Run the
command's `--help` for its exact inputs. New `start` calls require `--approval-id`;
see [sequence review](sequence-review.md) for review and output-validation commands. `advance` handles at most eighteen
submissions. `observe` accepts synthetic observations, not public webhooks or
real provider evidence. Organization flags are trusted local scope, not hosted
authentication. No configuration wizard or new frontend route is added.

The installed transports also expose explicit `--email-scenario` and
`--call-scenario` choices: `success`, `rejection`, `partial`, `timeout`. Resume a
simulation with its original choices. No real recipient, sender account,
credential, provider spending, inference call or CRM task write is performed.

## Persistence and compatibility

Schema 20 to 21 adds two campaign proposal/command tables and eight engagement
tables for simulations, enrollments, steps, dispatch reservations, observations,
stops, commands and events. Step inputs and history are immutable; only bounded
lifecycle/lease fields change. Dispatch inputs are immutable and their receipt
can be recorded once. Migration and version advancement share one transaction.

Existing postal, profile, audience, recipient and channel artifacts retain their
serialized bytes. The schema-v3 legacy admission cutoff is preserved. Updated
legacy/checkpoint readers support schema 22, including schema-21 sequence
inspection, and restored roots remain inspection-only. Schema 22 adds exact
sequence review without rewriting schema-21 artifacts. Older binaries reject
schema 22, so rollback to older code
requires a pre-upgrade database backup.

New simulation mutations are refused in verified-paused and restored roots.
The existing postal simulator and its approval purpose remain unchanged. The
supported deployment remains local and single-worker; selected concurrency
tests do not establish distributed dispatch safety. Production authentication,
retention/deletion, provider event verification, live reconciliation, live outbound
approval and commercial learning remain separate work.
