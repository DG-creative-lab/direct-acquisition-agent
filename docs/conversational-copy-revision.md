# Conversational copy revision

Ask the agent to edit a specific variant of the current grounded model campaign, for example: `Make variant B more direct. Keep variant A and the audience unchanged.` The agent shows the selected variant and exact feedback before requesting separate permission for up to five revision calls. The revision preserves the existing campaign experiment and returns a new, unapproved subject.

## User flow

The router proposes `revise_copy`. Server code resolves explicit variant A/B and inventory/contractor references against the frozen current campaign. If a variant or segment is ambiguous, the agent asks for it. A reply such as `B` or `inventory` retains the earlier edit request. A bare selector without a saved edit request asks for feedback instead of inventing an instruction. That selector remains saved across reload, so `B` followed by `Make it more direct` resolves to variant B.

Only unanswered clarification continues into the next edit. Once a proposal is ready for confirmation, a later edit starts a new feedback chain. For example, `Make variant B more formal` followed by `Make variant A more casual` gives A only the casual instruction. A complete target and wording request also replaces an earlier unresolved request. Ready proposals remain separately inspectable and require their own exact confirmation.

Review the named segment and variant, headline and optional **Current copy**. The original draft and creative identities remain in **Inspect follow-up**. The displayed native feedback preserves the user's wording, normalizing whitespace and joining clarification replies with ` / `. Original messages and response references remain in the saved exchange. The existing native limit is 500 plain-text characters, without em dashes. Overlong feedback asks for a complete restatement and resets the carry context so a shorter request can recover.

Check **Allow up to five model calls for this revision**, then choose **Generate copy revision**. The general campaign-copy checkbox does not grant this revision permission. Routing can consume one separately bounded call, but proposing or reading an edit never starts copy generation or rejects an existing approval.

After confirmation, progress uses the original native revision journal. **Review revised copy** opens the current in-chat review. The new subject needs fresh approval and a separate simulated handoff. Missing configuration, stale work, known failure and uncertain paid outcomes remain distinct. An uncertain request is never automatically repeated.

## Scope and authority

This first slice supports the current conversation's prepared, grounded model campaign. Fixture campaigns cannot be relabeled as generated revisions. Accepted simulated campaigns, stale drafts and exhausted native revision limits block new edits. Arbitrary campaigns, other channels, multi-variant edits and automatic approval are outside this slice. Broad natural-language target interpretation beyond the supported references remains evaluation work.

The conversation module owns the immutable proposal and bounded name resolution. The existing review module owns copy revision admission, budgets, model generation, screening, publication and approval invalidation. Workspace composition supplies current server-owned campaign targets. Runtime remains business-agnostic.

The model chooses an action type, not executable session or creative IDs. The confirmation binds the immutable routing result, current conversation revision, case, subject, creative, feedback and explicit generation permission. The native revision adapter independently compares the displayed preview with the actual base creative. It rechecks operator/reviewer authority, current evidence and suppressions, source provenance and case limits in the existing transaction.

The action confirmation, native revision admission, exact-subject rejection, audit and command receipts commit together in the shared conversation database. No brief message is appended, no campaign planning restarts and no audience selection is replaced. Carried copy exchanges are checked against their original scoped task outputs and durable admission order. The native workflow continues to preserve the sibling creative and the audience, assignments, budget, selected product wording and qualifications.

## Persistence and recovery

New follow-ups use `conversations.route.v2`, `route-followup/v2`, `propose_conversation_action/v2` and dialogue v4. The earlier capability, skill and tool contract remain installed for original frozen requests. Recorded legacy prompts are not rebuilt with current tools. Dialogue v3 retains its original interpretation and recorded request envelope. An unconfirmed older proposal that carries a ready edit for a different variant is rejected at confirmation without rewriting its saved result. Same-target v3 feedback and historical receipt replay retain their original behavior. New routing inference also binds its exact admitted capability, preventing a new request from being dispatched through the older contract.

`POST /api/conversations/{id}/confirm-copy-action` accepts exactly `request_id`, `action_id`, `result_id`, `expected_revision` and `allow_model_copy: true`. Scope and native targets come from the saved proposal, never browser-supplied organization, subject or creative fields. Existing Host, same-origin and token checks apply.

The native revision request identity is deterministic from the conversation action. Exact retry and another observation key return that original effect. Conflicting request reuse is rejected. Historical receipt observation does not require provider credentials or grant fresh authority. New confirmation can persist while the provider key is unavailable; restoring the original configuration resumes the saved native revision.

Existing schema-v8 JSON journals hold these records; this slice adds no migration. The native copy admission and source task retain a narrow conversation-action reference. Original campaign artifacts, prior source selections, legacy cutoff and historical result envelopes remain unchanged.

Use a matching application version for the workspace. Older binaries cannot interpret the new routing contract; mixed-version processes remain unsupported.

The client retains its original command identity after a lost response and reconciles saved state. A delayed confirmation cannot replace another chat opened in the meantime. Sending a reply is disabled until the selected saved conversation has loaded, so a quick reply after reload cannot create a different campaign.

## Verification limits

Real SQLite and fake-provider tests cover proposal/confirmation separation, target clarification, exact feedback and preview, consent, stale subjects, scoped HTTP access, concurrent confirmation, transactional rollback, lost responses, process restart, unavailable keys and uncertain inference. Browser checks exercise desktop and 320px/390px mobile, in-chat review and delayed loading/navigation. These establish control behavior, not live model routing accuracy or marketing performance. No live-provider quality is claimed by this slice.
