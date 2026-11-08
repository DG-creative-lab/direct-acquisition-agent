# Requested campaign scope

This workflow change addresses the four scope substitution failures in the issue-25 offline corpus. It does not complete typed conversational prepare/follow-up routing or establish live model quality. Paid inference remains paused and restored workspaces remain inspection-only.

## Ownership and evidence

`campaigns.CampaignScope` owns the installed delivery capability: `iwoca_flexi_loan`, `direct_mail`, `UK`, `response_experiment`. This agrees with the deterministic UK audience exclusions, fixed postal assignment format and response-experiment forecast basis. The conversation module uses that public pure contract; runtime remains business-agnostic.

`conversations.requested_scope` owns `requested-campaign-scope/v1`, resolved by `literal-scope/v1`. A snapshot records organization, conversation, revision, full native-message hash and four requirements. Each explicit requirement cites the original message ID, revision, character range and quotation. Its content-derived ID binds every field. It is evidence of a bounded literal interpretation, with `authority: none`, never approval or product-fact authority.

| Input condition | Recorded result | Continuation |
| --- | --- | --- |
| Supported explicit value | Value and literal message provenance | Planner may propose a brief |
| Omitted facet | Declared capability default, not an invented user quotation | Default shown in the campaign brief |
| Recognized unsupported value | Requested value retained | Explicit unsupported result, zero planner calls |
| Conflicting affirmative/excluded values, or an unknown explicit label | Unresolved requirement retained | Clarification, zero planner calls |
| A later explicit correction | Replace only that facet for the new revision | Earlier snapshots and campaign artifacts remain immutable |

The resolver recognizes a finite installed vocabulary and explicit `product:`, `channel:`, `country:`/`market:` and `objective:`/`metric:` labels. It distinguishes direct exclusions and the bounded "do not replace X with Y" construction. It does not establish general multilingual, paraphrase, quotation, irony or multi-clause intent recognition. Unknown free-form concepts outside its vocabulary can remain unrecognized. Defaults are a visible product convention, not proof that every omission meant consent to those values. Broader semantic evaluation and additional explicit selections are future work; extending resolver semantics requires a versioned compatibility decision.

## Native bindings and commit points

1. Planning admission derives the snapshot from independently loaded, scoped native messages inside its existing transaction. A caller's proposed context must match. Planning retries retain the original snapshot and settings.
2. The planner receives a compact projection. A recognized negative request is settled as the corresponding clarification or unsupported result without dispatch. Validation rejects a supported replacement, a false rehashed snapshot or an explicitly contradictory proposed objective. Scope is not a model-selected tool argument.
3. Brief construction preserves the snapshot in new campaign inputs. Grounded-copy context includes its ID and values, alongside the original proposed objective. The existing reviewed fact pack still governs claims and freshness.
4. A scoped draft includes the complete brief and actual `campaign_scope`. Storage checks those delivery values against the installed capability and the original successful planning task, plan result, current revision and native message bodies. Removing the scope cannot select a legacy contract when the native planning task was scoped. Copy-only revisions preserve the header and brief.
5. Readiness uses the same source-provenance check as transactional approval and simulated acceptance. Those write transactions repeat the check after their writes, before commit. Draft publication also repeats it after artifact and operation writes. A trigger that changes source evidence rolls back artifacts, decisions, simulator jobs, audit and receipts together.
6. A fresh follow-up must retain its accepted parent's scope. Proposal save, new preparation, publication and review reconcile the original request. An amended source revision cannot grant fresh follow-up authority. A saved proposal or acceptance receipt remains a historical observation on exact replay.

Stopping execution still blocks generation. It does not remove the existing separate ability to review and explicitly simulate acceptance of an already prepared exact subject at the same revision. Scope verification does not convert the stop flag into approval authority.

## Compatibility

No schema migration or historical rewrite is introduced. Older planning results, campaign briefs, copy contexts and manifests omit the new fields and keep their original hashes. Replay returns the original records without attaching current defaults. Fresh review/publication of an old conversation artifact still checks its original and current literal source for unsupported/conflicting scope, without rewriting it. Previously recorded receipts remain observable rather than becoming current authorization.

New scoped subclasses preserve the old serialized dataclass shapes instead of adding null fields to old artifacts. Only newly scoped drafts gain `campaign_scope`. Restore fences, fixture allowlists, inference budgets, uncertainty handling, exact-subject approval and simulation-only delivery remain governed by their existing controls.

## Bounded verification

The independent failure model covers four requested/delivered facets, source removal/substitution, valid rehashing under a different conversation, same-revision source-body changes, a later amendment, three post-write mutation positions (publication, approval, acceptance), follow-up inheritance, defaults versus quotations and old unscoped records. Real SQLite tests assert absent effects and rollback, rather than relying only on the status label. Browser tests exercise the four unsupported requests with a fake gateway, zero usage, no campaign and visible supported defaults on desktop/mobile after reload.

Five declared harmful variants remove planner substitution enforcement, choose scope from the submitted brief instead of the native task, omit the publication/approval commit checks, or skip native message reconciliation. The original unchanged corpus remains the independent oracle for the four previously false readiness cases. See the [follow-up evaluation record](evaluations/issue-25-requested-scope.md) for measured results and remaining issue-25 gaps.
