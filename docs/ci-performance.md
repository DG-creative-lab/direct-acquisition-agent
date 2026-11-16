# CI execution cost

Initial measurements below use baseline `0ffba90` (PR #84). The CI branch is
now rebased onto `b88e632` (PR #85), including exact sequence review.

CI retains the full Python 3.11–3.14 matrix. Backend shards keep modules together,
record case and class setup durations and report estimated versus actual time.
Mutation jobs partition the entire catalogue and reject fixture/loader failures.
No test coverage is removed. Reducing Python compatibility checks remains a
policy decision rather than an execution optimization.

## Browser isolation

Two CI jobs use whole-file partitioning with one worker per job and
`fullyParallel: false`. Each job starts its own server: shard 1 uses port 8770
and shard 2 uses 8771. Server roots include the shard and a random UUID. Each
root retains the product's exclusive lock and single-worker constraints.
Tests which create additional fixture servers already use independent temporary
roots and OS-assigned ports. Existing displayed-subject, reload and lost-response
checks remain in the portfolio.

Run a complete local check with `make interface-check`. Run the CI partitions
with `make interface-check BROWSER_SHARD=1 BROWSER_SHARDS=2` and the equivalent
shard 2 command. Build once before running test-only shards concurrently in one
checkout, so two Vite builds cannot write the same `dist` directory concurrently:

```sh
pnpm --dir frontend run build
BROWSER_SHARD=1 BROWSER_SHARDS=2 pnpm --dir frontend test
BROWSER_SHARD=2 BROWSER_SHARDS=2 pnpm --dir frontend test
```

Screenshot paths use Playwright's per-test output directories. Trace/screenshot
outputs and JSON timing reports are scoped by shard and uploaded as separate CI
artifacts. Discovery verification found 108 tests with no missing or overlapping IDs. The initial built-in split had
63/45 cases and concentrated slow files in the first job. Measured file durations
led to grouping chat-review with review-regressions (49 tests), with all remaining
and new files in partition 2 (59 tests). JSON reports support future weight updates. File boundaries
preserve fixture sequencing; unequal counts do not establish unequal wall time.

A pre-existing browser race became visible during concurrent local runs. The
new-brief-after-stop test waited for a three-second fake provider response to
remain in progress. It now uses the existing release-marker fixture to hold the
response until stop, then releases it before checking receipt settlement. The
assertions still exercise actual product state. The lost-audience-confirmation
case also uses the existing ten-second bound for asynchronous preparation
completion after reload, rather than the default five-second visibility bound.

## Production reconstruction

Profiling used this existing real SQLite case, including shared class setup:

```sh
PYTHONPATH=src:tests python3 -m cProfile -o /tmp/sequence.prof -m unittest \
  test_sequences.SequenceTests.test_controls_are_enrolled_but_never_receive_a_step_or_charge
```

The original sample made 593 `decision_evidence` calls, 1,198 current-source
checks and 1,812 `_snapshot` reconstructions. The revised sample retained 593
evidence calls and 1,198 current-source checks while reducing `_snapshot`
reconstructions to 1,219. The comparison measures one case, not the entire suite.
Local concurrent verification contaminated wall-clock comparisons, so no elapsed
speedup is claimed from those profiles.

Reuse lasts only within one `decision_evidence` invocation. A parsed source and
its exact stored row are retained while the report is rebuilt. The final read
queries the current head again and reuses parsing only if every stored field
matches. Changed rows are parsed and validated again. The latest version,
installed attestation and profile are still checked at the original final
boundary. History, exclusions, epochs and time are rebuilt for every evidence
check. No positive readiness or approval result is cached.

The contact regression changes installed attestation after report time and
corrupts stored source bytes within the transaction. Both must reject reuse.
A mutation which skips the final source check must be detected.

## Exact sequence review follow-up

The pure pressure/calendar test now lives in `SequenceReadinessDomainTests`.
It constructs the same recorded synthetic contact values directly and checks
identical pressure thresholds and calendar boundaries. It does not create a
SQLite application, prepare content or grant approval. Its two existing mutation
targets follow the relocated test and must still be detected.

Sequence review templates build only fielddesk. Indirect fixture variants build
one fielddesk template per distinct source variant and keep it for the class.
Population and population-control cases share their identical source template.
Each use copies the template through SQLite backup before any writes. The full
basis regression verifies the cached template has no sequence proposals,
approvals or simulations after exercising a copied store. Migration and
initialization cases retain their own historical database fixtures.

A profile of `test_one_approval_covers_both_arms_and_controls_across_restart`
recorded 3,308 contact-evidence checks and 6,622 current-source checks before and
after the history reuse refinement. Source parsing fell from 6,697 to 3,385 calls.
The history query reuses the already-validated current source only for an exact
stored-row match inside that invocation. All other history rows are parsed and
validated independently. The existing equal-time permission-history regression
also detects a mutation that substitutes the current parsed source for unrelated
history rows. These profiles ran alongside other verification, so their elapsed
times are not a controlled speed comparison.

The new review module has an explicit shard weight rather than the cheap per-case
fallback. Sequence weights initially use the assessment's local module timings;
CI artifacts remain the source for later hosted-run calibration. Wider reuse
across operations or transactions remains deferred until independently profiled
and covered at final authority boundaries.

Rebased verification passed 998 backend tests, all 108 browser tests, architecture,
build, formatting and 79 relevant mutation probes. The complete 510-probe
catalogue was retained but was not rerun in this follow-up. Results and experiment
reruns are recorded in [the validation ledger](validation.md).
