# Local workspace checkpoints

Use the checkpoint command to capture a stopped, verified-paused workspace and
inspect its history in a separate local directory. The command is an
administrator operation over the whole root, including every organization in
its application stores. Keep bundles private as you would the original SQLite
files.

## What is captured

| Location | Contents and handling |
| --- | --- |
| `conversations.sqlite` | Root store and scoped sandbox locations, including conversations, exact admissions, generation consent, historical allowance and stop records, and shared campaign data |
| `workspace_<24 lowercase hex digits>/campaign.sqlite` | Registered campaign stores and any other existing stores at canonical legacy campaign paths. Preserve the recorded policy, scope, immutable artifacts, model observations, approvals, simulated jobs and learning records in each store |
| `workspace.sqlite` | Original journal identity and all journal rows. Some rows are rebuildable projections. Legacy rows can be the only record of ancestry, storage routing, frozen preparation and consent, simulation time or request mappings, so the backup keeps the complete journal, including opaque historical data |

Application snapshots contain their persisted audience bytes, evidence packs,
frozen contexts, draft bytes, receipts and schema-v3 cutoff. Configuration and
catalogue files from the checkout, generated exports, logs, environment files
and the server lock are outside the bundle. Historical evidence stays in the
database in which it was recorded.

The supported source has a schema-14 through schema-17 conversation store and journal, with
schema-14 through schema-17 application stores. The conversation store and every registered
campaign store must already select `verified-paused/v1`. Unregistered stores
at canonical legacy paths can retain their unsealed policy. The command
includes them as historical evidence and preserves their state verbatim.
Recover missing or unsupported source files separately. A registered location
must still identify its original store. A missing journal blocks capture
because SQLite alone cannot establish whether legacy-only evidence was lost.

## Create, verify and restore

Stop the workspace server, standalone workers, CLI jobs and any other process
that can write to the source or add stores. Use a trusted local filesystem
with POSIX locks and an existing parent directory for each destination.

```sh
PYTHONPATH=src python3 -m acquisition.workspace_checkpoint create \
  --root .local/workspace --bundle .local/workspace-checkpoint

PYTHONPATH=src python3 -m acquisition.workspace_checkpoint verify \
  --bundle .local/workspace-checkpoint

PYTHONPATH=src python3 -m acquisition.workspace_checkpoint restore \
  --bundle .local/workspace-checkpoint --root .local/workspace-inspection \
  --checkpoint-id CHECKPOINT_ID
```

Record the `checkpoint_id` returned by creation separately and supply it on
restore. Verify checks the versioned manifest, exact file inventory, SHA-256
digests, full SQLite integrity including index contents, foreign keys, recorded
policies, schema versions and known store/journal bindings. It opens
self-contained snapshots read-only.
The checks detect inconsistent or altered files relative to a checkpoint.
They assume a trusted checkpoint ID and local operator.

Creation holds the server's exclusive root lock and SQLite writer locks over
the source journal and application stores, with the journal acquired first.
It refuses running task leases, unresolved `reserved` calls and nonempty
source rollback journals. Settle reservations through the existing recovery
path before taking a checkpoint. Committed `unknown` observations remain
unknown. SQLite's backup API includes committed WAL records. Source database
rows stay untouched. Maintenance can create the permanent root lock file, and
SQLite can perform ordinary WAL housekeeping when source connections close.

Create and restore stage files in a private sibling directory, validate the full
set, flush it and publish by directory rename. A destination must be new or
empty and separate from the input. The format allows up to 64 database files
and 2 GiB of database content. After an interrupted command, verify the
destination if it appeared. A process killed before publication can leave a
private `.acquisition-checkpoint-*` sibling with a partial, fenced copy. After
confirming the command stopped, discard that staging directory and retry
against the original input.

## Inspection after restore

Keep the directory together with its `.acquisition-checkpoint.json` file.
The bundle and restored root use that marker to open application stores
read-only and stop workspace/server startup, migration writes and projection
rebuilds. Use the current checkout for inspection. For example, the run CLI
can read saved task status and model-call receipts. Put any exports in a
separate directory.

A checkpoint may preserve fixture execution policy and grants from its
source. These are historical records in a restored root. Fixture initialization
requires a fresh root.

```sh
PYTHONPATH=src python3 -m acquisition \
  --db .local/workspace-inspection/conversations.sqlite \
  --organization local-conversations status --run RUN_ID

PYTHONPATH=src python3 -m acquisition.legacy_migration \
  --root .local/workspace-inspection inspect
```

Rows and receipts describe the checkpoint's history. The manifest does not
establish whether spending, suppression changes, revocations, approvals,
simulator effects or observations occurred later. The supported commands grant
no execution, acceptance or learning authority. Treat detached database
files, manual edits and older executables as outside this recovery procedure.

## Compare later local evidence

Use `reconcile` with the original bundle or its unchanged inspection root.
Supply the independently recorded checkpoint IDs and select one organization.
Take the later checkpoint from the original workspace that continued after
the baseline, with its writers stopped. Keep both inputs fixed for the
comparison. Divergent copies can share store identities and earlier records,
so the operator must know where each bundle came from.

```sh
PYTHONPATH=src python3 -m acquisition.workspace_checkpoint reconcile \
  --bundle .local/workspace-inspection --checkpoint-id BASELINE_ID \
  --organization local-conversations \
  --later-bundle .local/workspace-later --later-checkpoint-id LATER_ID
```

Omit both later arguments to report missing evidence. Both snapshots undergo
the usual manifest, layout and SQLite checks. The later snapshot must have a
newer capture time and match the root and journal identities. The comparison
checks application store identities and scoped historical records before
reporting additions. An unavailable store or conflicting history blocks
findings for that store. A store present only in the later snapshot has no
baseline for comparison. A different root, a different journal or an
unordered pair blocks the entire comparison.

| Local observation | What corroborates it |
| --- | --- |
| Inference call | Scoped call journal and matching run and task. The recorded account must agree with the committed admission or the original legacy task plans and parent records. A finite nonnegative amount in the stored provider receipt is reported as provider-reported cost. Missing amounts stay null and unknown outcomes stay unknown |
| Execution stop | Scoped stop command, original revision and durable stop fence |
| Review revocation | Scoped revocation, its original decision and subject, and matching audit and command receipts |
| Simulated acceptance | Scoped job bound to its exact approval and subject, with matching audit and command receipts. Provider-backed jobs also require their original provider result and retain full or partial acceptance status. The observation retains the synthetic mode |

The report describes records present in the later snapshot and absent from
the earlier one. Retained review effects must still have matching audit and
command receipts in both snapshots. Sandbox timestamps can be simulated.
The capture timestamps order the checkpoints and do not date individual effects. A compared store
with no additions provides no proof of absence. The report counts all
observations in a compared store and lists up to 100 details per store.

The named organization sees its native records and calls with corroborated
ownership in its conversation accounts. The command compares specific local
journals. External billing, delivery and coverage after the checkpoint remain unknown. Current
approval, other authority changes and learning effects require separate
evidence. A successful report is an inspection result. Every outcome keeps
execution paused and provides no activation permission.
