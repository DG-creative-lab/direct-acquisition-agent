# Conversational synthetic sequences

Issue #68 connects the contact, audience, recipient context, channel content, sequence and exact review capabilities from #62 through #67 to the conversation workspace. The agent owns routine discovery and preparation. A user provides an objective, reviews one proposal, and approves its exact bounded simulation. The existing postal path and immutable campaign artifacts retain their original formats.

## Operating flow

Send, for example:

> Prepare a Fielddesk email and human call sequence for UK contacts with a £100 total budget.

The equivalent Iwoca request is supported. A uniquely resolvable spelling error such as `Fielddsek` resolves to the installed company. Missing or ambiguous company, source or budget produces a focused question. The primary synthetic CRM is the declared default when no source is specified. A source can also be named as primary CRM, secondary CRM, or its installed company connection key.

This slice uses a bounded offline interpreter and offline channel model. Sending an email/call objective permits three content runs, each limited to five calls, at $0. They consume the existing conversation-wide 48-call allowance. These are local deterministic model fixtures, not evidence of live language understanding or commercial copy quality. Browser OpenRouter settings and the postal model-copy checkbox do not select a provider for this capability. Its message endpoint does not request or transmit OpenRouter funding, so an unrelated model connection cannot gate offline clarification, edits or inspection.

The installed sequence includes an initial email, a human call task and a contextual follow-up. It uses the complete eligible installed source, taxonomy-order account selection, one selected contact per account, and A/B/no-contact assignment. It supports UK/GBP synthetic evidence with at most six accounts and eighteen steps. Exact recipient-count requests, additional audience restrictions, other strategies, unsupported companies/countries/providers/channels, autonomous voice and automatic recipient replies produce an explicit unsupported result. They are never silently replaced. A full replacement objective supersedes earlier scope; a short clarification or budget edit retains the earlier requirements.

The worker checks source identity and permissions, prepares the audience and reviewed recipient contexts, creates the three grounded content artifacts, and opens an exact unapproved sequence subject. The proposal exposes:

- Treatment/control counts, planned synthetic email and human-task effects, source coverage and exclusions.
- Estimated maximum cost, explicit user budget and the offline generation limit.
- Day 0 email, arm-specific day 1/2 call tasks and day 3/4 follow-up, bounded to seven days.
- Exact recipients, personalized wording, product claims, qualifications, CTA, evidence IDs and check results through optional inspection.

Select **Review and approve simulation**, inspect the confirmation and choose **Approve and simulate**. The displayed subject, conversation revision and reviewer generation bind the durable confirmation. The worker records the native review decision and continues the synthetic simulator. Inspection and reload never invoke generation or simulation.

Simulation advances an explicitly synthetic, persisted virtual clock to the next due step. It creates human call tasks rather than autonomous calls. An accepted call task needs the user's explicit **Record synthetic task completed** observation before its dependent follow-up can proceed. Independent accounts continue their scheduled work while that call waits. The conversation waits for human completion when all remaining pending steps need that observation. No recipient response or actual call is fabricated. Stop this sequence, or send `stop`, to fence further work. A call already in progress can still record its eventual usage or observation.

For an accepted email, **Record synthetic reply to email** records an explicit
simulation observation. Its account's pending steps pause while independent
accounts continue. The command retains the exact journey, revision and step.
Reload, retry and a second tab preserve the first observation time and one
engagement receipt. A saved reply resumes after process restart.
Reply admission commits a simulation-scoped pause with the command. Native
dispatch reads that pause even when a worker's observation list predates the
reply. Recording the eventual observation preserves the same account scope.
Accepted emails also allow reply observations after submissions complete,
including the final follow-up. Continuation records these observations and
returns to complete using the original submission history.

Task-completion intent freezes its observation time before native continuation. A restart after native observation and a synthetic clock advance reuses that exact time and command. A stale tab using another key for the same task also retains the first explicit observation time.

A status question such as `What is the status?`, `show the proposal` or `inspect` is saved separately from material messages. It does not invalidate the proposal, consume inference or grant approval. Text such as `approve it` points back to the exact approval control and grants no authority. Material changes append a new conversation revision, make the earlier proposal historical and require a fresh review. An explicit, unambiguous postal request returns to the existing postal preparation flow. Historical sequence rows do not capture later postal follow-ups or hide postal resume controls. A saved sequence-routed message that receives a postal message receipt continues with its original funding and consent through postal preparation. A cancelled request is not revived by a new key for the same revision.

## Ownership and ports

| Owner | Contract and authority |
| --- | --- |
| `conversations` | Typed journey inputs, source revision, bounded consent, immutable command identities and continuation state. Narrow intent interpreter, journey store and host ports. No approval or dispatch policy. |
| `workflows` | Composes existing public contact, audience, creative, campaign, review and engagement APIs. The host advances one saved stage and resumes original native commands after interruption. |
| `bootstrap.py` | Wires installed company/profile discovery, offline interpretation/model adapters, shared SQLite persistence and public services. It selects concrete adapters. |
| Existing business modules | Continue to own eligibility, grounding, budgets, exact review, current evidence and synthetic acceptance. Their ports remain usable independently for unbound historical or standalone requests. |
| Workspace application | `application/workspace/service.py` receives a lazy journey factory from bootstrap. It routes messages and exposes saved progress through public conversation contracts. It does not construct concrete adapters. |
| React and HTTP | Present saved progress and exact server-owned subjects. Fixed organization/actor resolution, Host, Origin and token protections remain in the existing loopback transport. |

Company-native scopes are stable hashes of owner organization and profile key. They isolate installed companies while preserving source identity and objection history across journeys for the same company. They do not create hosted tenant administration.

## Durable state and authority

Schema 23 adds `sequence_journeys`, `sequence_journey_bindings`, `sequence_journey_commands` and `sequence_journey_events` in the existing conversation application store. Inputs, bindings, commands and events are immutable. Continuation state is mutable and compare-and-set against the worker's previously observed stage/status/outputs. Message append and journey admission commit together. The schema-22-to-23 migration adds tables and triggers without rewriting historical evidence, artifacts, review decisions, model receipts or the legacy task-admission cutoff.

Native command keys are reserved before preparation. New channel contexts and task inputs optionally carry a frozen journey origin; existing contexts and tasks retain their old shapes. Bound recipient inputs cannot be moved into an unbound generation request. Journey ownership follows the frozen provider-account connection identity, so later reassessments, source versions, mapping revisions and connection aliases cannot turn the source into standalone inputs. A source on a different unowned connection or in an independent organization scope retains the standalone path. A new recipient-context key cannot detach a journey-owned contact assessment: publication requires the original bound context command and its assessment. Channel admission independently follows the saved assessment provenance, including contexts written before this restriction. Loading, inference reservation and artifact publication repeat that derivation for existing channel runs, even when an earlier saved context has no journey field. Rejected continuation preserves the original run and call receipts; uncertain calls remain fenced. A later journey does not retroactively own an independently admitted run. Its immutable requested event records the prior run/context identities inside the admission transaction, so equal clocks do not erase that ordering. Historical events without this ordering evidence remain fenced; a clock value alone does not prove admission order. All three content stages retain one journey and the original sequence request. New keys cannot detach uncertain work or obtain a fresh allowance.

The native adapters recheck revision, stop state and consent inside preparation/publication transactions and inference reservation. Runtime remains business-agnostic. Recorded model calls count against the original conversation even after cancellation or material edits. Immutable journey scope also locates native inference receipts if task origin fields and execution links are lost; an incomplete account cannot reset the allowance. Late inference results remain recordable, but they cannot publish content or start the next call. Unknown/reserved outcomes retain the original run and reservation; the agent never automatically admits replacement work.

Approval confirmation is durable before continuation. Its original reviewer generation, exact subject and original native decision key are rechecked by the native review authority. Existing #67 expiry, full readiness-basis interval and per-acceptance transactional checks remain authoritative. A saved report, conversation status or cached receipt is never current authorization. Synthetic acceptance and observations remain in the existing engagement journals.

The optional verified-admission format remains paused for these capabilities. Admission fails before appending a message, allocating a native run or consuming inference. Restored checkpoints remain inspection-only. This work does not introduce live senders, CRM network access, hosted identity, enterprise tenancy, new learning authority or deployment.

## Validation model

The bounded failure space connects three authority clusters: source revision/consent to generation; exact human confirmation to review and synthetic acceptance; immutable commands to retry/restart recovery. Observable oracles are the actual message revision, model-call journal, immutable artifact rows, native review decisions, dispatches and observations, rather than UI status alone.

`test_sequence_journeys.py` separates pure interpretation tests from shared real-SQLite templates. It covers both companies, focused clarifications and literal scope substitution, one-confirmation completion, read-only inspection, command replay, subprocess restart, message/admission rollback, missing consent, source edits, stop during a reserved call, late usage without publication, detached generation/sequence keys, disabled reviewers, cross-organization lookup, verified-mode rejection, orphaned receipt accounting and a real schema-22 upgrade. Completion recovery also retains the original observation time across a committed clock advance and a stale tab's second request key. Browser tests cover the objective-to-review journey, approval, truthful human-task completion, reload, ambiguity, unsupported scope, late-response navigation and transition from an earlier postal budget question. Existing module suites remain responsible for their full eligibility, grounding, expiry, acceptance, objection and learning contracts.

These tests establish offline control behavior. Live provider semantics, arbitrary language interpretation, distributed workers, autonomous voice, recipient replies and commercial outcomes remain outside the tested space.

## Run ownership design decision

The review series exposed an interaction problem: the native organization and
source identity are shared resources, not the owner of every run using them.
Execution permission and budget accounting must interpret the same immutable
admission evidence. Stopping a journey changes its permission to continue; it
must neither erase its historical usage nor adopt an independent run's usage.

The current fix makes execution accounting consume the same prior-admission
classification used by channel continuation. It checks the exact run/context
pair against each relevant journey's requested-event snapshot and verifies the
saved source provenance. Conflicting native bindings, task-plan corruption,
missing context or incomplete ordering evidence do not gain a standalone
exemption. This is a scoped compatibility decision, not a blanket exemption for
all calls in the native organization.

| Admission evidence | Ownership and accounting | Continuation |
| --- | --- | --- |
| Independent channel run recorded before the journey | Standalone relative to that journey; exclude its calls from that conversation allowance | Original run may continue if its own evidence and call journal permit |
| Original conversation-bound command, context and execution link | Original conversation/revision; retain usage after stop or edit | Recheck current revision, stop and consent at each effect boundary |
| Detached run admitted after its source journey | Unresolved; no standalone exemption from a later journey | Reject further calls and publication; retain existing observations |
| Missing, contradictory or ambiguous historical ownership | Accounting remains incomplete | Explicit recovery must restore evidence; names, timestamps and a new key cannot choose an owner |

The allowance view, reservation checks, task publication and recovery must all
respect these outcomes. An unknown call remains an observation of its original
run, never permission to create replacement work. The regression composes an
independent run, later journey admission, standalone completion or uncertainty,
accounting inspection, restart and preparation to an unapproved sequence. Lost
links and after-journey detached work are separate negative cases.

### Refined implementation plan, 17 November 2026

Tracked follow-up: [epic #107](https://github.com/DG-creative-lab/direct-acquisition-agent/issues/107).
The following work is proposed. The current branch's compatibility fixes remain
subject to review and merge; they do not implement this admission migration.
Completed #33 supplies the existing authority foundation and is not reopened.

#### Provenance before ownership

Admission must independently load the scoped source, assessment, recipient
context and parent/run lineage before deriving permitted ownership. A caller's
standalone label cannot certify independence. Reassessment, source aliases,
new keys, missing links and a later journey cannot detach conversation-owned
inputs. Native APIs and retry paths must pass the same check as workspace paths.

Freeze the exact request and request fingerprint, source identity/version and
fingerprint, context fingerprint, original owner/account/revision, parent,
consent/model references and canonical task plan. Commit their binding to the
exact organization and run, runtime tasks and receipt atomically. A duplicate
exact request returns the original run; a changed declaration conflicts. Provider
I/O remains outside the transaction. Losing acknowledgement cannot repeat work.

#### Reuse the existing authority machinery

| Existing owner or component | Reuse and required extension |
| --- | --- |
| `conversations/admission.py`: `ExecutionOwnership` | Existing standalone/conversation vocabulary and immutable account key; unresolved history is a recovery status, not another executable owner kind |
| `AdmissionIntent` and `AdmissionReceipt` | Existing source/context/task-plan fingerprints, consent/model references, parent binding and exact run receipt; inspect capability gaps before extending/versioning |
| `adapters/sqlite/admissions.py`: request/admit/receipt paths | Saved request and consent, source reconstruction, exact replay, atomic admission/runtime/account writes and receipt validation |
| `admission_sources.py` loaders and workflow composers | Derive authoritative provenance and permitted owner; add missing channel/journey registrations rather than accept caller-supplied ownership |
| `admission_guard.binding` | One verified binding reader checking request, source, context, task plan, run, receipt and ownership; reuse across consumers |
| Existing execution accounting/recovery | Preserve original allowance, stop history, explicit independent resolutions and unresolved-history fences; do not allow auxiliary links to override the admission |

Stage 1 must specify any required schema extension and old/new reader behavior.
Do not introduce a second authoritative ownership ledger that can disagree with
`admission_requests` or `execution_admissions`. Runtime remains business-agnostic;
public business contracts stay out of `contracts.py` and React.

#### Ownership and current authority

Ownership answers whose budget and stop lineage apply. It is immutable after
admission, including across material edits, stop, restart, source refresh and
later journeys. Source revision, generation consent, evidence freshness, leases,
current stop state and exact approval still require independent checks at their
effect and commit boundaries. Late observations may be recorded without gaining
continuation authority. An unknown call cannot be repeated under a replacement
run, owner or allowance.

Persisting or reusing an ownership contract must not activate the paused verified
format. Current unsealed simulation behavior, sealed verified-paused stores,
existing limited fixture grants and inspection-only restores need explicit
compatibility rules. No new fixture grant, format selection, provider activation
or paid/external execution is authorized by this plan.

#### Historical classification and migration

| Evidence class | Required outcome |
| --- | --- |
| Proven standalone | Keep original run/context/request and receipts; a later journey cannot adopt its usage or stop rules |
| Proven conversation-owned | Keep original account, revision, parent, consent, call counts and stop lineage |
| Missing, contradictory or ambiguous evidence | Retain inspection and diagnostics; block execution and new allowance until an explicit evidence-based recovery succeeds |

Start with a scoped read-only classification report, bound to exact store and
source fingerprints. Applying a reconciliation must revalidate the evidence
under its transaction lock and be restartable and idempotent. Preserve legacy
cutoffs, historical bytes, uncertain receipts and restore fences. An absent link
or a clock comparison cannot prove standalone admission. The #68 prior-admission
snapshot is a bounded compatibility bridge; retire it only for record classes
with verified replacement admission, reader and recovery coverage.

#### Ordered implementation issues

| Stage | Concrete deliverable | Dependencies |
| --- | --- | --- |
| [#108](https://github.com/DG-creative-lab/direct-acquisition-agent/issues/108) | Reuse/gap inventory, provenance-first contract, compatibility/transition matrix and focused contract tests | Completed #33; inventory can precede #68 merge |
| [#109](https://github.com/DG-creative-lab/direct-acquisition-agent/issues/109) | Registered channel/journey loaders and atomic ownership/run/task/receipt writers through existing admission machinery | #108 and accepted merged #68 baseline |
| [#110](https://github.com/DG-creative-lab/direct-acquisition-agent/issues/110) | Canonical readers across accounting/generation/publication/recovery, plus scoped legacy classification and reconciliation | #109 |
| [#111](https://github.com/DG-creative-lab/direct-acquisition-agent/issues/111) | Composed conformance, fault/mutation evidence and coverage-backed retirement of redundant compatibility inference | #110; boundary tests accompany every earlier stage |

#68 retains its own product acceptance scope and does not depend on closing
#107. The follow-up gates external writer integration in #71, consumed by
#72/#73, and ownership-related release/portability closure in #74/#77. Read-only
CRM contracts in #69 and access design in #70 can proceed independently.

#### Acceptance across the composed workflow

Extend existing real-SQLite and fresh-process tests to cover both company
fixtures. Cross standalone-before/after journey admission with active/stopped/
historical revisions, equal clocks, new keys, refreshed assessments/aliases,
missing/conflicting links, restart, unknown calls and late observations. Exercise
the material combinations through accounting, reservation, publication and
recovery, not only the admission or continuation reader.

A genuine prior independent run must continue while the later journey reaches a
validated unapproved sequence with only its own calls counted. Journey-derived
work must retain the original stop and allowance regardless of derivation path.
Failures around each atomic admission/reconciliation write must either roll back
or recover one original identity. Conflicting or ambiguous histories must not
become standalone. Exact approval and current evidence remain required for any
subsequent effect.

Run required backend/architecture and applicable interface checks. Record the
bounded coverage, selected harmful mutations, residual risks and measured cost.
Use existing evaluation tooling and CI partitions; a new gate needs distinct
protection, cost and cadence justification. Deterministic synthetic results do
not establish live model quality, provider delivery or hosted authority.
