# Review and approval reference

Review cases bind durable proposals to local reviewer decisions, invalidation rules and simulated acceptance. The custom runtime and campaign rules retain their own module boundaries. Reviewing, approving, suppressing and simulating acceptance require no model calls.

## Run the scripted demonstration

```sh
PYTHONPATH=src python3 -m acquisition --db .local/review.sqlite demo-review --request-id review-demo --out .local/review-demo
```

Open `.local/review-demo/review.html`. The command also writes `before-approval.html`, `suppression-blocked.html` and exact draft exports under `artifacts/`. These are read-only reports. Their decision examples invoke the CLI, which rechecks authoritative state.

The demonstration uses an isolated synthetic organization and an explicitly scripted reviewer. It creates a draft, records an initial decision, suppresses a selected recipient, confirms that the old approval cannot authorize acceptance, rebuilds, records a fresh decision and accepts one simulated job. Repeating the same command returns the same acceptance receipt. The default 1,000-record fixture produces 681 initial recipients and 680 after suppression. The scripted decision demonstrates the protocol; it is not a human review of marketing copy.

The product pack must still be within its dated review window. Once that window expires, manually verify the official sources and activate an updated pack. Do not backdate the clock or extend review dates without verification.

## A manual review

All commands below use the same database and organization. Replace capitalized identifiers with the exact IDs printed by earlier commands. Run from the repository root.

```sh
PYTHONPATH=src python3 -m acquisition --db .local/manual.sqlite --organization demo-org review-actor --actor operator --role operator
PYTHONPATH=src python3 -m acquisition --db .local/manual.sqlite --organization demo-org review-actor --actor reviewer --role reviewer
PYTHONPATH=src python3 -m acquisition --db .local/manual.sqlite --organization demo-org review-evidence --actor operator --request-id evidence-1
PYTHONPATH=src python3 -m acquisition --db .local/manual.sqlite --organization demo-org demo --request-id campaign-1 --as-of 2026-10-26
PYTHONPATH=src python3 -m acquisition --db .local/manual.sqlite --organization demo-org review-open --run RUN_ID --actor operator
PYTHONPATH=src python3 -m acquisition --db .local/manual.sqlite --organization demo-org review-show --case CASE_ID --html .local/manual/review.html --out .local/manual/artifacts
```

Inspect the population, exclusions, assignments, all four copy variants, source dates and exact manifest. The fixture is explicitly synthetic. For generated copy, use `demo-model` in place of `demo`; its existing OpenRouter controls and evidence checks still apply.

```sh
PYTHONPATH=src python3 -m acquisition --db .local/manual.sqlite --organization demo-org review-decide --case CASE_ID --subject SUBJECT_ID --actor reviewer --request-id decision-1 --decision approve --reason 'Reviewed the exact synthetic draft and evidence.'
PYTHONPATH=src python3 -m acquisition --db .local/manual.sqlite --organization demo-org review-handoff --case CASE_ID --approval DECISION_ID --actor operator --request-id handoff-1
```

Use `--decision reject` to record rejection. Use `review-revoke --case CASE_ID --approval DECISION_ID --actor reviewer --request-id revoke-1 --reason 'Review withdrawn.'` to revoke a decision. A later rejection supersedes an earlier approval of the same subject. Re-run `review-show` to see current validity; a successful decision receipt is historical evidence, not a perpetual permit.

## Changes and fresh approval

A proposal subject hashes the organization, case, revision, draft, audience snapshot, product pack, policy, evidence epoch, suppression epoch and simulated-handoff purpose. The draft identity binds its exact manifest, creative identities, assignments, cost and CSV hashes. Approval binds that subject, reviewer generation, reason, decision time and expiry.

Approval is checked again inside the simulator's acceptance transaction. Any of the following prevents a new acceptance:

- The proposal is superseded, rejected or revoked.
- Suppression state, active product evidence or policy changes.
- Reviewer roles or enabled state change, including disable then re-enable.
- Approval expires, the clock precedes its issue time, or product evidence expires.
- The source run is cancelled, fails or has not reached review.
- Stored input or artifact integrity fails, or current deterministic validation fails.

Epochs are monotonic. Changing evidence and restoring its previous bytes cannot revive an old approval. Conservatively, any new organization-wide suppression invalidates every existing subject in that organization, even when the specific business was not selected.

Record a late suppression before acceptance:

```sh
PYTHONPATH=src python3 -m acquisition --db .local/manual.sqlite --organization demo-org review-suppress --actor operator --request-id suppression-1 --business BUSINESS_ID --reason 'Synthetic late suppression.'
PYTHONPATH=src python3 -m acquisition --db .local/manual.sqlite --organization demo-org review-refresh --case CASE_ID --subject SUBJECT_ID --actor operator --request-id refresh-1
```

Refresh applies the full current suppression set to the immutable original snapshot, recomputes selection and assignments through campaign rules and publishes a new revision. It preserves the existing copy. Preparation may leave an unreferenced immutable draft if a competing revision or evidence update wins. Only the final transactional compare-and-swap publishes authority. Use a new request ID after that conflict.

Copy changes require a new generated run with a new `--request-id` and the original `--campaign-id`. New generation uses the organization's active fact pack. Take its saved draft ID and publish it with `review-replace --case CASE_ID --subject SUBJECT_ID --draft DRAFT_ID --actor operator --request-id replace-1`. Replacement must remain in the same campaign and pass current evidence and suppression validation. Refresh cannot repair outdated grounded copy; regenerate it against the current pack. Both operations require a fresh reviewer decision.

## State and effect ownership

The original runtime checkpoint remains an acknowledgement of dry-run progress. It grants no approval. Review cases, immutable subjects, decisions, revocations, actor generations, evidence epochs, command receipts and audit events have their own SQLite records. The source run and historical drafts are preserved.

Actor configuration is trusted local administration. Operator and reviewer roles constrain normal application operations, but a person with access to the CLI can configure identities. This is not authentication, separation of duties or an externally verified human identity. The model has no approval tool. An approval does not change creative status or become a customer outcome or Bayesian observation.

Current evidence means the explicitly activated organization registry and suppression ledger. The application does not poll websites, detect external policy edits or ingest a live suppression feed. Product source verification remains a manual trust boundary. The policy can allow only the exact known fixture catalogue or require grounded generated copy. Legacy ungrounded generated copy cannot be approved.

The simulator validates approval, inserts its one acceptance per case, writes the audit event and persists the command receipt in one SQLite transaction. Time is read after acquiring the write lock. Suppression and acceptance therefore have a defined order: an earlier suppression blocks acceptance; a later one cannot undo an already accepted historical simulation. Accepted cases cannot acquire new proposals or decisions. Revocation can still record that authority was withdrawn after acceptance, but it does not retract a job.

A retry of an accepted job observes the original receipt, including after approval expiry. It creates no new acceptance. A future real agency integration needs its own authenticated delivery adapter, external idempotency, uncertain-outcome reconciliation and an outbox or equivalent dispatch protocol. The local transaction does not establish those properties for a remote agency.

Schema v4 adds review tables under the existing initialization write lock. It preserves the schema-v3 legacy admission cutoff. A failed migration rolls back both DDL and version markers. Older binaries reject the newer schema; rollback compatibility is not promised.

## Verification

See [validation](validation.md) for the current test portfolio and bounded evidence for review identity, expiry, revocation, concurrency, atomicity and replay.
