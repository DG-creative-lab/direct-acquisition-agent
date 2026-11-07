# Legacy ownership migration

Phases 5a and 5b of [the execution authority decision](execution-authority-decision.md)
provide an offline inventory and transactional ownership migration. Verified
execution stays paused.

## Inspect an existing root

Stop its server and all CLI writers first. From the repository root, run:

```sh
PYTHONPATH=src python3 -m acquisition.legacy_migration --root .local/workspace inspect
```

The command prints JSON to stdout. It takes the root's `server.lock`, creating
only that coordination file if absent. Source connections use SQLite read-only
mode with `query_only`; neither schemas nor source records are written. SQLite
may use shared-memory files for read locks. A source requiring hot-journal
rollback is reported for separate recovery instead of being opened for writing.
No missing database is initialized.

Discovery includes `conversations.sqlite`, `workspace.sqlite`, and canonical
campaign stores referenced by the root's location catalogue or valid legacy
session routing. It does not scan arbitrary directories for databases. An
unregistered standalone CLI database outside those locations is outside this
report's coverage. Retain it separately for deliberate reconciliation.

Each source is read from a pinned transaction. A second full observation must
match before the report returns. A change invalidates the proposed plan.
This detects observed changes during inspection; it is not a distributed
snapshot or a cold-backup protocol. Keep writers stopped throughout inspection.

## Apply a reviewed plan

Apply targets an existing schema-14 or schema-15 `conversations.sqlite` sealed under
`verified-paused/v1`. Sealing is a separate format decision. On an unsealed
schema-14 store, review the [cutover contract](execution-authority-decision.md)
before running `PYTHONPATH=src python3 -m acquisition --db
.local/workspace/conversations.sqlite admission-cutover`. Inspect again after
the seal. An unsealed inventory ID cannot apply to the changed store.

Explicit cutover refuses a pre-v10 store that contains recorded runs and leaves
its schema and records unchanged. Preserve and inspect that history for separate
ancestry reconciliation. This slice does not provide an automatic safe upgrade
and cutover for that case.

Review the current report. When `apply_available` is true, records marked
`migrate_paused_ownership` are the eligible bindings. Run with the exact
`plan_id` from that report:

```sh
PYTHONPATH=src python3 -m acquisition.legacy_migration --root .local/workspace apply --plan-id "$plan_id"
```

Apply takes the root lock and reserves SQLite write locks on the journal and
the discovered databases. It recalculates the plan from those locked sources.
Missing or unreadable sources, unsupported paths, a rollback journal that
requires separate recovery, or a changed plan ID block the write. Use canonical
local files and keep filesystem writers, file copies and restores stopped
throughout the operation.

Only the conversation store commits changes. A supported legacy run needs
positive conversation provenance, a matching historical task plan, an existing
scoped account and ownership index, and a matching journal association recorded
before the organization's first run. Apply records the existing owner and
revision, evidence fingerprint and parent dependencies with an immutable
receipt. Existing ownership indexes, quarantine markers, allowances and stop
state are preserved. The account's stop fence must agree with its scoped
stop receipts. A missing account with surviving execution history or a
recreated row that contradicts that history requires reconciliation.
A journal identity match cannot prove the absence of later
history. Unattributed or quarantined runs and missing or weak journal
associations stay unresolved, including after reopening a sealed store.

If the process stops before commit, retry the same reviewed plan after
inspection confirms the evidence is unchanged. If commit succeeds and the
response is lost, the same plan ID returns the historical
`legacy-ownership-migration/v1` receipt. To check whether apply committed,
run the receipt-only command:

```sh
PYTHONPATH=src python3 -m acquisition.legacy_migration --root .local/workspace receipt --plan-id "$plan_id"
```

Receipt lookup reads only the existing conversation store and works when the
workspace journal is missing. A missing receipt produces a distinct error.
Re-inspection lists eligible recorded bindings as
`retain_migrated_paused_binding`.

This slice binds legacy run ownership in the canonical conversation store.
Legacy session, clock, preparation and command records still live in their
original journals. Standalone campaign stores remain inspection sources.
The [checkpoint procedure](workspace-checkpoints.md) preserves these journals
and restores them for inspection. Execution activation remains separate work.

## Meaning of the plan

The `legacy-migration-plan/v1` envelope has a content-derived `plan_id` and
`source_fingerprint`, source identities and schema versions, unresolved-source
diagnostics, and record classifications. Evidence references identify their
store, table, scoped key and fingerprint. Parent dependencies refer to other
inventory records. They are observations, never ownership writes.

| Classification | Meaning | Proposed next step |
| --- | --- | --- |
| `supported` | The installed historical reader can match the recorded source and dependency evidence | Review the binding, retain a verified paused record, or rebuild a disposable projection through its separate command |
| `conflicting` | Source integrity, store identity, recorded ownership or parent facts disagree | Preserve the originals and reconcile the specific conflict |
| `incomplete` | Ownership, permission, source mapping or a required dependency is missing or unsupported | Obtain positive evidence; do not infer standalone ownership |
| `uncertain` | Work was in flight or a provider reservation/outcome needs reconciliation | Inspect the original call journal before considering another request |

Conflict takes precedence over uncertainty; an uncertain record retains its
other missing-evidence reasons. A child cannot become supported from an
unresolved parent. Cycles, contradictory owners and overlong ancestry chains
are unresolved rather than guessed. Source failures are reported separately;
zero conflicting records does not mean all sources were readable.

The version-bounded readers compare native planning, routing and copy-revision
admissions with their original runtime task plans. Fixture campaigns retain
their recorded mode. Positive conversation proposals and domain descendant
receipts supply parent dependencies. Routing permission remains routing-only;
it never supplies copy-generation consent. Older model campaign formats without
a supported exact consent proof remain incomplete. Native sources or staged
verified requests interrupted before runtime admission are reported as pending;
inspection does not finish them.

Existing verified admissions are read with the existing binding validator.
Registered application environments and preparation intents remain the source
for their new-format projections. Before marking an environment or its projection
supported, inspection applies the normal authoritative reader's full checks to
the same pinned read-only connection: exact admitted run inputs and original
creation command, review case, learning cohort, parent and clock. A failed check
marks the environment and its projection conflicting while retaining the source
evidence fingerprint. Other valid environments remain inspectable.

Corrupt session payloads for owned IDs cannot override the application record or
redirect source discovery. The shared validator can recompute an expected
synthetic snapshot identifier from the original generation parameters; it does
not persist a replacement audience. Inspection uses no current knowledge
catalogue, model provider or evidence refresh.

Recorded account links and workspace claims can expose contradictions. They
cannot supply missing positive ownership. An old independence receipt, matching
journal identity, root-campaign witness or populated stale backup does not prove
complete ancestry. Missing or different bound journals remain visible conflicts.

## Preserved information and limits

The report retains task-plan, native-admission, consent and context fingerprints;
original parent links; recorded model-call counts and bounded observation states;
original mode and clock where available; and the schema-v3 legacy cutoff evidence.
All other source tables, including artifacts, approvals, acceptance, learning and
opaque legacy bytes, contribute to the full source fingerprint and remain intact.
Prompts, feedback, context bodies, provider responses and credentials are excluded.
Every exported generation choice, including the optional `use_audience_catalogue`,
must be a boolean. Invalid choices classify the preparation as conflicting;
their values stay out of both the report and CLI diagnostics. Valid `true` and
`false` values are preserved exactly.

Legacy session metadata passes a separate closed validation boundary before
export or use as a routing/ownership hint. Mode, optional clock mode, supported
UTC time, storage scope and bounded identifier syntax are checked together.
The clock mode must be compatible with fixture/model mode when present; a
missing historical clock mode is left absent. Optional run, case, cohort and
parent identifiers may be null. Conversation hint identifiers and revision must
also be valid. Malformed sessions remain conflicting, with opaque evidence
fingerprints and no exported payload fields. An invalid journal key is displayed
as a fingerprint locator rather than its raw contents. Its internal inventory
identity still derives from the original key.

The bounded identifier syntax accepts realistic API keys. The final report
projection selects supported fields and checks their types before display.
It renders organization identifiers consistently in records, evidence and
resolved owners. The fixed `local-conversations` label stays readable. All other
organization identifiers, request IDs and standalone campaign scope IDs use
`opaque_` fingerprint references. Generated identifiers use their native formats
where recognized, and null links remain null.

The inventory matches and classifies the original values inside the source
scope. It fingerprints the display values after classification and preserves
the original bytes in storage. Unverified conversation hints remain unresolved.
Migration requires positive domain evidence for each binding.

Call counts are local observations. Remaining allowance is unknown in this report;
it does not recompute or reset an account. Billing and backup completeness are
always unverified. Historical approvals and receipts are never current permission.

Every record has `executable: false`. The plan reports `apply_available` for
an eligible batch. `execution_activation`, `legacy_certification` and
`migration_ready` stay false because ownership binding grants no execution
permission. Provider observations, historical task inputs, the schema-v3
cutoff, approvals, acceptance and learning records stay in their original
tables and retain their existing authority checks.

## Module ownership

`conversations` owns classification, binding eligibility and the exact-plan
command behind `LegacyMigrationSource`. The SQLite adapter discovers sources,
reads scoped facts, and commits the selected bindings and receipt.
`bootstrap.py` connects the port and adapter. The CLI serializes reports and
receipts. The existing sealed-store fences enforce the pause at task claim and
inference reservation.
