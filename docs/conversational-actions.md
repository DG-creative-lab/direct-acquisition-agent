# Conversational follow-ups

Direct Acquisition Agent distinguishes a question about an existing campaign from a proposed brief change. Inspection does not advance the brief revision, replace the audience selection, restart preparation or invalidate approval.

## Using the chat

The first campaign request uses the existing brief planner and preparation coordinator. Later messages use the follow-up router.

| Message | Result |
| --- | --- |
| `status?` or `How is the campaign progressing?` | Recorded preparation status, without model inference |
| `Why did you choose this audience?` | Confirmed source version and actual input/assignment counts |
| `Why were these businesses excluded?` | Recorded exclusion counts and reasons |
| `Explain validation` | Exact-draft machine-check results, separate from approval |
| A less familiar inspection question | At most one model call to propose a supported action |
| `Change the budget to £400.` | A proposed amendment, awaiting explicit confirmation |
| `approve it`, `send it` or `looks good` | Guidance to the existing exact-campaign review and handoff controls |

Common phrases are versioned authored aliases, not a claim of general language understanding. Other follow-ups use GPT-OSS-120B through the existing OpenRouter adapter. The model chooses one action type. Explanations are assembled by code from saved server observations, not generated assertions about campaign execution.

New routing requests freeze the two most recent brief messages and the latest completed planner response, including its exact clarification question, result identity and revision. An earlier response is explicitly marked historical. Dialogue v2 also freezes recent router exchanges and pending clarification or amendment requests from this conversation revision. This lets the router interpret a short answer such as `£600` to a budget question or `Change it` after a mixed change-and-explanation request. The answer still requires brief-change confirmation before it enters planning. Each saved message is already bounded to 2,000 characters; the complete provider request, including dialogue, is preflighted against the existing input limit before admission or inference. Model routing stops when more than four pending change exchanges would need to be carried. Start a new conversation and state the complete change; authored inspection shortcuts remain available.

Each answer shows when its observation was recorded. Replaying the same request returns that original observation; a new question can observe newer state. **Inspect follow-up** exposes evidence IDs, the frozen skill/tool/source bundle, routing method and run status. An accepted simulated handoff is described as simulation, never physical delivery.

## Applying an amendment

An amendment proposal shows the exact original user text, base brief revision and copy permission. If it answers a router clarification or pending proposal, the confirmation also shows the earlier user requests and agent responses that supply its context. **Apply brief change** authorizes those displayed user texts to enter the brief, in order, and up to two planning calls. Applying it stops affected older preparation and invalidates review based on that older revision. Model copy remains separately limited by the permission saved with the final follow-up; earlier requests cannot expand it.

The server confirms only a completed `amend_brief` routing result for the exact displayed target. A read-only result, stale revision, substituted target, changed admission text or another conversation cannot be confirmed. Each carried exchange is rechecked against its scoped immutable admission and completed task inside the confirmation transaction. The displayed earlier user requests and final reply are appended as separate messages, each advancing the revision, while their questions remain labeled context. Their message receipts, confirmation and command receipt commit together. Lost responses and repeated confirmations cannot append them twice. Inspection requests and observations never become brief instructions through this carry mechanism.

For example, `Change the budget to £400 and explain the audience`, a router clarification and `Change it` retain the original £400 request. Confirmation carries the two user messages into the brief and freezes the whole exchange for the planner. If a later clarification supplies £500, its later user message wins under the existing literal-budget rule. Assistant questions never supply budget evidence. Replanning starts at the final committed revision, which can advance by more than one, and uses the original saved copy permission.

The new revision goes through the existing planner, source confirmation, generation and validation flow. It inherits neither audience confirmation nor approval. The existing literal-budget rule still applies: relative or ambiguous budget changes need clarification rather than an invented total.

## Durable routing and recovery

`conversation_actions` stores immutable follow-up inputs and frozen context separately from `conversation_messages`, which remains the brief history. Follow-up text is bounded to 2,000 characters, 40 actions and 16 KB in total per conversation. At most 12 actions may require model routing. Each model-routing run permits one inference call, without automatic repair. Existing six-plan and per-campaign copy budgets remain separate.

Admission precedes runtime task creation. A restart reconciles the same task identity and frozen inputs, even if current authored skill files are unavailable. Inference reservation requires the original scoped admission and original run identity. A changed brief fences a queued routing call. A late completed interpretation stays historical and cannot authorize an amendment to the newer brief.

Dialogue is part of the frozen observation and its source manifest. Request replay uses that original exchange rather than rereading the latest question. Confirmed exchanges are durable planning inputs, so continuation after a lost acknowledgement or restart retains the source request and question. Actions admitted before dialogue support, or with dialogue v1, retain their original prompt envelope and confirmation behavior, preserving recorded-response replay without another provider call.

Action history uses SQLite admission order, not wall-clock timestamps. A clock correction cannot make an earlier £400 request override a later £500 correction. Timestamps remain unchanged observations. Confirmation also checks that carried sources precede the current action and follow their durable admission order. If an older request froze a reversed exchange, confirmation rejects it and asks for a new interpretation; the saved artifact is not reordered or rewritten.

Routing admissions can wait without a provider key. Restoring the original configuration resumes the saved request without consuming an attempt while incompatible. An active provider call is shown as in progress. After acquiring the exclusive server lock on startup, an interrupted reserved routing call is cancelled locally for reconciliation and remains visibly uncertain. It is never automatically dispatched again. A recorded provider response with a lost task acknowledgement can replay without another provider call.

A confirmed amendment is durable before preparation continuation. Startup can recover its original planning request and copy consent. A later intervening revision prevents old consent from being applied to the newer brief. Exhausted planning budget and unavailable configuration remain distinguishable from completed preparation.

## Architecture and authority

The conversation module owns actions, confirmation semantics and narrow storage ports. The workflow owns the bounded router tool loop. The workspace supplies scoped observation projections and composes existing campaign services. Runtime remains business-agnostic; adapters own SQLite transactions and provider access.

New schema v8 adds the action and confirmation-command tables under the existing migration lock. Historical messages, plans, selections and artifacts retain their original representation. The original legacy admission cutoff remains unchanged. Older binaries reject the newer schema; mixed-version operation against one workspace is unsupported.

The `route-followup/v1` skill and `propose_conversation_action/v1` tool contract are frozen per request. The `task_observation` source role permits explaining recorded state. It is distinct from official product evidence, authored guidance, preferences and counted learning. It grants no approval, source selection, dispatch or learning authority.

## Scope and evidence

This flow supports inspection and confirmed brief amendments in the current conversation. New routing v2 also connects natural-language targeted copy edits to the existing native revision controls; see [conversational copy revision](conversational-copy-revision.md). Handoff, learning and next-experiment operations retain their existing controls. Shared model-call accounting and exact-revision stopping are described in [execution controls](execution-controls.md). General target selection and external delivery remain further work in issue 25/26.

Real SQLite tests cover request replay, concurrent confirmation and conflicting admission, exact-input binding, rollback, lost continuation, configuration recovery, interrupted/recorded inference and fresh-process observation. An inspection runs while a fake copy provider is held in flight and the original preparation completes once. Browser journeys cover desktop/mobile, explicit confirmation, stale targets, active versus uncertain inference, and lost message/confirmation responses. Mutations weaken selected authority, replay and budget checks. These tests establish bounded control behavior, not live model intent accuracy.
