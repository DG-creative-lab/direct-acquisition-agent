# Conversational execution controls

A conversation has one shared allowance of 48 reserved model calls under `conversation-execution/v1`. Planning, routing, campaign copy, targeted revisions and descendant experiments consume it. Each operation retains its own smaller call limit and explicit generation permission. This allowance is separate from the mailing budget. It is a local prototype policy, not an organization billing service or a dollar spending guarantee.

## User flow

The chat shows calls used and remaining when accounting is complete. Unresolved history changes the summary to known calls and **remaining allowance unknown**; the API returns `remaining: null`. **Inspect model usage** shows completed, rejected, in-progress and uncertain calls, original runs and brief revisions, and provider-reported cost. Every reservation consumes one slot, including rejected or unknown requests. Recorded response replay consumes no additional slot. Changing the brief, restarting or preparing another experiment in that conversation does not reset usage. There is no public allowance-increase command.

An account is initialized only when its scoped execution links, stop journal,
and native runtime and call evidence show no earlier account use. Surviving
planning, routing or task records can identify history after both the account
and run index are lost. Before initializing a new allowance, the adapter
checks that surviving call receipts in the organization have a valid ownership
link, a scoped owner supported by the original runtime plan, or a verifiable
standalone admission. Matching task IDs alone leave the receipt unresolved.
An interrupted admission can still resume by its original request when no
runtime or call evidence shows prior execution. The workspace keeps any known
usage and recorded stops visible with an unknown allowance. The account's stop fence
must match its recorded stop commands before new execution or migration.
An existing account also requires its paid-run links to match the surviving
receipt and ownership history. A missing or conflicting link leaves the
allowance and cost coverage incomplete and blocks new admission and
reservations. Restore the original account, run links and stop records.

**Stop work** applies to the exact displayed brief revision and earlier work in that conversation. It stops pending planning, routing, generation and revisions, and fences later admission and draft publication from those revisions. Send a new brief to start new work through the ordinary planner, audience confirmation and generation controls. The remaining shared allowance is unchanged.

Cancellation does not withdraw an existing approval, erase history, undo simulated acceptance or restore approval rejected when a revision was requested. A campaign already at its review checkpoint remains reviewable subject to current authority. No approval or delivery authority is added.

An already-dispatched request may complete or incur a charge after stopping. Its late receipt is recorded without giving the worker publication authority. A timeout, network failure or interrupted reservation remains uncertain and is never automatically repeated. Polling observes receipts without dispatching inference. Interrupted reserved calls can remain inspectable after restart without claiming provider-side cancellation.

## Ownership and persistence

The conversation module owns policy and the execution service behind a narrow storage port. The SQLite adapter owns scoped accounts, run relationships and stop-command receipts. Runtime retains generic lifecycle and lease contracts. `bootstrap.py` wires the service.

Run admission links each relevant run to its original conversation, revision and organization in the task-creation transaction. Campaign and revision runs use their saved conversation brief. Descendant experiments trace the frozen follow-up proposal to its parent run. The manual next-experiment path first records its server-resolved parent run in the existing execution command journal, then binds the new run during task admission. The same ancestry fences draft storage and revision admission/publication. Existing manual descendants are reconciled from the workspace control journal before usage reads, stopping, execution and exclusive server recovery; original task inputs and provider receipts remain unchanged. An existing link cannot move to another conversation. Standalone campaigns without conversation provenance retain their per-run limits and are outside this policy.

Inference checks the shared allowance inside the write transaction that inserts its original reservation. Competing runs cannot both consume the last slot. Existing request hashes, consent, run limits, evidence, source freshness and leases still apply. Recorded replay precedes the new-reservation budget check, so exhausting the allowance cannot prevent replay of an already recorded response.

A stop request binds its ID to the organization, conversation and revision. The receipt, monotonic stop-through-revision fence, active run/task cancellations and audit events commit together. Lost-response replay observes the original receipt after an intervening edit without stopping the newer revision. Cancellation does not wait for the executor lock held around a model call.

The coordinator journal lives in the separate control database. If its update is interrupted after domain cancellation commits, progress and recovery consult the authoritative fence. A stale coordinator cannot resurrect work. Draft storage, new revision admission and publication check cancellation or the cancelled task lease. A reached review checkpoint is recognized by its final waiting task, completed predecessors and exact committed draft reference, even before a case exists. Stop receipts preserve those checkpoint run identities. The workspace opens their unapproved review cases without running a worker, and exclusive startup recovery completes that step after an interruption. Unrelated waiting tasks are still cancelled. Completed review checkpoints are preserved so stopping alone cannot invalidate approval. Newly admitted stop IDs reserve the internal descendant namespace; existing stop receipts remain observable.

Schema v9 adds accounts, run links and stop receipts under the migration lock. Schema v10 marks ambiguous older campaign runs in conversation-backed organizations as awaiting ancestry recovery. Backfill counts historical journals without rewriting receipts, contexts, artifacts or the schema-v3 legacy cutoff. DDL, backfill and the marker roll back together. Older binaries reject v10; mixed-version access remains unsupported.

## Truthful progress and limits

A reserved call on a cancelled run is uncertain until a receipt arrives. Explicit provider rejections such as a 401 are distinct from network uncertainty; both consume the original slot. Exhaustion is shown separately from missing input, consent, configuration, cancellation and failure.

Cost is the sum of available provider receipt metadata. Missing cost is never presented as a verified zero: coverage is explicit and billing remains unverified. Usage projections exclude credentials, raw prompts, response bodies and lease tokens. Existing per-request price ceilings remain unchanged.

The deployment is still one local server and worker. This slice adds no provider-side cancellation, refunds, top-ups, hosted identity, real dispatch, reporting schedules or organization-wide billing cap. Fake-provider checks establish resource and lifecycle behavior, not live billing or semantic quality.

## Recovery before worker execution

Schema-v10 migration first restores provable run relationships, then records unresolved older campaign origins in the same transaction. Missing old metadata is not evidence of a standalone campaign. A direct worker cannot claim an unresolved run or consume an attempt, and inference reservation independently denies a still-live lease. Known related runs pause while potentially shared old usage remains unattributed. The usage projection labels accounting incomplete instead of presenting its known remaining allowance as available for spending. Unrelated standalone organizations remain runnable.

Workspace recovery resolves the original control-journal parent and links historical reservations without rewriting inputs or provider receipts. CLI runs using `--campaign-id` can also resolve their origin through the original campaign admission in the same organization: both its request identity and frozen brief must identify that campaign. This recovery works during migration and when reopening an already-upgraded database, without a workspace session. A planner request key or a campaign in another organization cannot establish this relationship.

That verified relationship clears the pending-origin marker; the original stop fence and shared allowance then apply. If the original relationship cannot be recovered, work stays blocked rather than choosing an account by inference. Cost coverage remains incomplete while any potentially shared runs are unattributed, including when the known subtotal is zero or all known calls have cost metadata. The subtotal remains visible without treating it as the full cost. The runtime core remains business-agnostic; the SQLite claim and inference adapters enforce the recovery boundary.

### Reconcile a genuinely independent legacy CLI run

Some older CLI runs were independent experiments. They have no workspace parent to recover. An enabled local operator can explicitly attest to that independence after inspecting the stored run and its own provenance. This is trusted local administration, separate from campaign approval. It records the operator's decision rather than inferring independence from absent metadata.

**Inspect model usage** lists the unresolved run IDs and organizations and names the recovery commands. Use the database belonging to the running workspace: conversation campaigns normally use `<workspace-root>/conversations.sqlite`; an isolated sandbox uses `<workspace-root>/<organization>/campaign.sqlite`. The default workspace root is `.local/workspace`. Match the organization shown in the inspection panel, not the account owner `local-conversations` unless that is the run's actual organization.

Inspect quarantined runs without configuring a model or supplying an API key:

```bash
PYTHONPATH=src python3 -m acquisition \
  --db <workspace-root>/conversations.sqlite --organization <organization> \
  execution-unresolved
```

The result includes run and request identities, campaign IDs, status, known call count, matching workspace ancestry and an exact inspection fingerprint. Use the existing `status --run <run-id>` and `calls --run <run-id>` commands with the same database and organization to inspect the original work. Verify its provenance against your CLI experiment records. If it belongs to a conversation, restore that relationship instead. An active run must finish or be stopped with the existing `cancel --run <run-id>` command before classification.

Inspection and classification check the original `workspace.sqlite` journal as well as the domain database. A recorded workspace parent, follow-up or conversation plan prevents an independence decision, even before normal workspace recovery has copied that relationship into the domain journal. The adapter matches the run, request or campaign identity within the organization and verifies its database scope. The original canonical database layout and readable workspace journal are required; an unavailable or inconsistent journal blocks new classification. The command never creates an empty journal to stand in for missing authority.

The workspace journal has a persistent immutable ID. Before an organization's first run, workspace composition records a scoped binding to that ID in the domain execution ledger. Reopening cannot replace the binding. A newly recreated empty journal or an unrelated journal has a different ID and cannot authorize inspection or classification for the original history. The fingerprint includes the verified journal ID. If the journal is lost, stop the server and restore the original journal or its complete backup; creating a blank journal or opening another workspace does not recover this authority.

Independent classification requires a binding established before the organization's first run. A matching legacy root, run ID or admitted task hash proves an association but cannot prove that later descendants are present. Existing history is therefore never enrolled from such a witness. Pre-identity history and earlier `verified_legacy_campaign` bindings cannot authorize an independence claim. Restore available original metadata to recover positively recorded parents; runs whose ownership remains unknown stay paused. An operator attestation cannot turn an unverifiable absence into permission.

Only after verifying independence, submit the exact displayed fingerprint with an explanation:

```bash
PYTHONPATH=src python3 -m acquisition \
  --db <workspace-root>/conversations.sqlite --organization <organization> \
  execution-resolve-independent \
  --run <run-id> --request-id <unique-resolution-id> \
  --fingerprint <inspection-fingerprint> --actor local-operator \
  --reason 'Verified independent CLI experiment from my experiment records.'
```

The operator must already exist and be enabled in that organization. Provisioning or changing local roles uses the existing explicit `review-actor` administration command; reconciliation never enables an actor. A run with a proven conversation origin or recorded workspace ancestry cannot be classified as independent. The fingerprint includes matching workspace records. If those records, task state or provider journal change after inspection, inspect it again and use the new fingerprint. The command obtains the workspace write lock before the domain transaction and retains it through the classification commit, so a concurrent workspace writer cannot invalidate the ancestry check.

Older independence receipts based on a witness-only binding remain historical observations. On reopening, unlinked runs with those receipts are fenced again and usage remains incomplete. A positively recovered parent can restore the correct allowance and stop fence without rewriting the historical receipt.

The immutable decision, command receipt, audit event and quarantine removal commit together. Repeat the original request after a lost response to observe its receipt. Changing its inputs is rejected; a new observation key with identical inputs does not repeat the audit effect. Restarts and migration recovery preserve the decision. A conflicting later parent link is rejected. Original tasks, provider receipts, artifacts, approvals and the legacy cutoff remain unchanged. Any uncertain provider requests retain their original replay restrictions. An independent queued run can resume under its original per-run controls; its calls remain outside conversation accounting because of the explicit operator attestation.

Reload the chat after successful reconciliation. Complete accounting and a numeric remaining allowance return only after every potentially shared run is resolved. This command does not reset an allowance or grant review, mailing or delivery authority.

Checkpoint restoration is isolated per checkpoint. Missing operator authority, unavailable storage, invalid data and other recovery failures produce bounded public guidance without storing raw exceptions. One disabled operator cannot stop server startup or another conversation's recovery. No actor is silently enabled. The local executor retries saved restorations; the UI keeps polling a recoverable checkpoint.

Saving the case ID is not the end of restoration. Recovery also reconciles its preparation journal when the case already exists, validates the original run association, and clears the recovery block only after those steps succeed. Repeated recovery preserves one review case and its existing decisions. A stopped checkpoint remains unapproved until a separate explicit review decision.

## Supported recovery boundary

Normal process restart with the current durable journals is supported. Journal identity verifies lineage, not completeness or backup freshness. [Workspace checkpoints](workspace-checkpoints.md) now provide cold capture, full integrity verification, isolated restoration and read-only reconciliation of later evidence. Restored workspaces remain inspection-only, including restored fixture grants. Fixture activation applies only to a fresh verified workspace; paid inference remains paused. Partial, mismatched or stale rollback restores must not be treated as evidence that missing paid work or ancestry never existed. Inspect such data through the CLI without starting the executor; automatic paid-work resumption from a restore is outside the supported recovery contract.
