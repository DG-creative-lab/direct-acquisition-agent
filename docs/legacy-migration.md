# Legacy migration inventory

Phase 5a of [issue 33's execution-authority decision](execution-authority-decision.md)
provides an offline inventory and proposed migration plan. It does not migrate,
certify, resume or activate a record. Verified execution stays paused.

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
No missing database is initialized. There is no `apply` or `activate` command.

Discovery includes `conversations.sqlite`, `workspace.sqlite`, and canonical
campaign stores referenced by the root's location catalogue or valid legacy
session routing. It does not scan arbitrary directories for databases. An
unregistered standalone CLI database outside those locations is outside this
report's coverage. Retain it separately for deliberate reconciliation.

Each source is read from a pinned transaction. A second full observation must
match before the report returns. A change invalidates the proposed plan.
This detects observed changes during inspection; it is not a distributed
snapshot or a cold-backup protocol. Keep writers stopped throughout inspection.

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

Every record has `executable: false`. The plan always sets `apply_available`,
`execution_activation`, `legacy_certification` and `migration_ready` to false,
even if all inspected bindings are supported. Later slices must implement and
test transactional migration, interruption/replay, the supported backup/restore
procedure, and explicit activation with a complete offline journey. A saved
inventory report cannot authorize any of those operations.

## Module ownership

`conversations` owns the classification policy, plan version and inspection
service behind `LegacyMigrationSource`. The SQLite adapter discovers bounded
sources and reads scoped historical facts without invoking recovery writers.
`bootstrap.py` connects the port and adapter. The CLI only serializes the report.
The runtime, inference reservation, validation, approval and learning paths are
unchanged.
