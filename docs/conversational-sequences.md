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

Native command keys are reserved before preparation. New channel contexts and task inputs optionally carry a frozen journey origin; existing contexts and tasks retain their old shapes. Bound recipient inputs cannot be moved into an unbound generation request. All three content stages retain one journey and the original sequence request. New keys cannot detach uncertain work or obtain a fresh allowance.

The native adapters recheck revision, stop state and consent inside preparation/publication transactions and inference reservation. Runtime remains business-agnostic. Recorded model calls count against the original conversation even after cancellation or material edits. Immutable journey scope also locates native inference receipts if task origin fields and execution links are lost; an incomplete account cannot reset the allowance. Late inference results remain recordable, but they cannot publish content or start the next call. Unknown/reserved outcomes retain the original run and reservation; the agent never automatically admits replacement work.

Approval confirmation is durable before continuation. Its original reviewer generation, exact subject and original native decision key are rechecked by the native review authority. Existing #67 expiry, full readiness-basis interval and per-acceptance transactional checks remain authoritative. A saved report, conversation status or cached receipt is never current authorization. Synthetic acceptance and observations remain in the existing engagement journals.

The optional verified-admission format remains paused for these capabilities. Admission fails before appending a message, allocating a native run or consuming inference. Restored checkpoints remain inspection-only. This work does not introduce live senders, CRM network access, hosted identity, enterprise tenancy, new learning authority or deployment.

## Validation model

The bounded failure space connects three authority clusters: source revision/consent to generation; exact human confirmation to review and synthetic acceptance; immutable commands to retry/restart recovery. Observable oracles are the actual message revision, model-call journal, immutable artifact rows, native review decisions, dispatches and observations, rather than UI status alone.

`test_sequence_journeys.py` separates pure interpretation tests from shared real-SQLite templates. It covers both companies, focused clarifications and literal scope substitution, one-confirmation completion, read-only inspection, command replay, subprocess restart, message/admission rollback, missing consent, source edits, stop during a reserved call, late usage without publication, detached generation/sequence keys, disabled reviewers, cross-organization lookup, verified-mode rejection, orphaned receipt accounting and a real schema-22 upgrade. Completion recovery also retains the original observation time across a committed clock advance and a stale tab's second request key. Browser tests cover the objective-to-review journey, approval, truthful human-task completion, reload, ambiguity, unsupported scope, late-response navigation and transition from an earlier postal budget question. Existing module suites remain responsible for their full eligibility, grounding, expiry, acceptance, objection and learning contracts.

These tests establish offline control behavior. Live provider semantics, arbitrary language interpretation, distributed workers, autonomous voice, recipient replies and commercial outcomes remain outside the tested space.
