# Test-suite cost and coverage assessment

## Assessment and evidence

The suite has useful regression coverage and avoidable execution cost. There is
no evidence that deleting a large number of tests is the appropriate first
step. Discovery on `137db62` found 994 distinct backend test IDs, no duplicates
and no loader errors. Distinct IDs do not prove distinct value, and this audit
does not establish that every assertion is indispensable.

This assessment combines the checked-in CI configuration and test code, a local
profile of one sequence-review test, and the successful
[CI run for merged PR #84](https://github.com/DG-creative-lab/direct-acquisition-agent/actions/runs/43639063387).
That run tested 978 backend cases, 484 mutation probes and 108 browser cases.
The unpublished #67 branch has additional review coverage; its complete remote
CI run has not been measured. The previous local 994-case run took 1,481 seconds.
Local macOS timings and hosted Linux timings are different measurements.
The complete follow-up run passed all 994 cases in 1,470 seconds, with temporary
per-case and class-setup timing instrumentation outside the repository. Two
targeted mutation probes ran alongside its early portion, so this is not a
controlled before/after speed comparison.

| Observed job in the PR #84 run | Test execution time |
| --- | ---: |
| Python 3.11, backend shard 1, 492 cases | 369 seconds |
| Python 3.11, backend shard 2, 486 cases | 778 seconds |
| Python 3.14, backend shard 1 | 273 seconds |
| Python 3.14, backend shard 2 | 658 seconds |
| Serial mutation job, 484 probes | About 913 seconds |
| Browser tests, 108 cases, one worker | About 492 seconds |

These are test-step durations, excluding queue delay. The mutation job was the
longest job in this observed run. Updating only backend sharding would leave
that overall completion limit in place.

## Confirmed cost sources

### Backend shard estimates are stale

`scripts/run_backend_shard.py` uses eight module timings from a November 6 run
and estimates every other module at 0.43 seconds per test. It keeps modules
together, which preserves class fixtures and avoids sharing writable stores
between parallel jobs. However, almost equal case counts conceal very unequal
work: the observed Python 3.11 shards differed by a factor of 2.1.

Completion timestamps in that job's log attribute approximately 143 seconds to
the 21 sequence tests, including their fixture time. The planner assigns that
module about 9 seconds. The new 16-test sequence-review module also falls back
to the per-case estimate. Other slow modules have grown beyond the older
weights. Module-level estimates from logs are approximate, rather than exact
per-test profiling, but the job imbalance is directly measured.

The eight slowest modules account for approximately 722 of 1,147 aggregate
Python 3.11 backend seconds, while containing 251 of the 978 cases. They are
sequences, execution controls, conversation actions, copy revisions, follow-ups,
fixture activation, conversational copy revision and conversation audiences.
Optimizing their setup and reconstruction offers more than treating every test
as equally expensive.

The new local timings show even greater concentration in the current branch:
sequence cases used approximately 423 seconds and sequence-review cases 273
seconds, plus about five seconds of shared class setup. Together these 37 of
994 cases account for approximately 48% of the measured full-run time. The
largest individual cases were timeout/partial/rejection simulation at 81
seconds, the five-variant full-basis regression at 73 seconds, and the two-profile
full-strategy simulation at 67 seconds. These cases include their per-case and
manually created variant fixtures. The small shared class-setup time also shows
why fixture caching alone will not solve the cost of repeated deep validation
inside actual operations. Final authority checks need their reconstruction path
profiled as well as the test harness.

### Mutation probes repeat complete targets serially

`scripts/check_failure_mutations.py` copies `src`, `tests`, `config` and `scripts`
to a new directory, starts a new interpreter and runs one target for every
probe. The reviewed baseline has 506 probes; the authority follow-up adds two.
All run serially in one CI job. The sequence and sequence-review targets alone
account for 44 probes in the reviewed baseline.

Each targeted class rebuilds its class fixtures in the new process. Several
targets contain many subcases and continue after the first failed assertion.
That work is valuable in the ordinary regression run; a mutation experiment
only needs one valid behavioral failure to prove that its harmful change is
detected. The runner rejects syntax/import failures and aborts on timeouts, but
its `Ran 1 test` plus nonzero-exit predicate also accepts a test `setUp` error as
a detection. A small local probe confirmed that a broken fixture satisfies
that predicate without reaching its assertion. Classifying fixture/harness
failures separately would make mutation evidence more trustworthy. Speed work
must preserve and improve experiment validity rather than counting crashes.

### Some tests use a more expensive layer than their rule needs

`test_domain_time_boundaries_include_pressure_coverage_and_product_calendar`
uses a complete two-profile fixture, prepares a proposal and approves it before
checking a pure pressure/date rule. A local cProfile run of that one test,
including class setup, recorded about 52.3 million function calls in 13.7
profiled seconds. It performed 891 `decision_evidence` calls, 899 contact report
reconstructions and about 628,000 digest calls. Profiling adds overhead, so its
wall time is not an unprofiled benchmark.

The profile attributes substantial work to recursive dataclass serialization,
canonical JSON, identity hashing and repeated source reconstruction. SQLite
`execute` itself accounted for only 0.23 profiled seconds in this sample. This
sample supports investigating repeated computation before changing durability
settings; it does not establish the bottleneck of every module.

`SequenceTests.setUpClass` already provides reusable real SQLite templates, and
individual cases copy them. The indirect-evidence variants rebuild both profile
templates even when the case uses only fielddesk. Other suites, such as copy
revisions and conversation actions, create and advance a complete preparation
workflow in each case's `setUp`. Pure membership, date and formatting rules can
often be checked separately from this lifecycle setup.

### The execution matrix and browser isolation have deliberate costs

CI runs the backend suite across Python 3.11, 3.12, 3.13 and 3.14, with two shards
per version. That is eight backend jobs, plus mutation and interface jobs. This
checks the supported Python range; it also repeats the entire integration
portfolio four times. Changing that policy could reduce runner consumption,
but would change which versions are checked before merge.

The browser configuration explicitly uses one worker, one fixed loopback port
and one server root. Tests exercise a product whose single-worker and per-root
lock restrictions are intentional. Increasing workers without independent
servers and roots would weaken isolation and invite races.

The workflow has no concurrency cancellation group, so superseded PR revisions
can continue consuming CI capacity. The logs examined here do not measure how
much queue time that has caused. Dependency setup is not the dominant observed
cost: the backend has no third-party runtime dependencies, and the interface
already caches pnpm's store.

## Coverage to retain

The sampled slow cases protect different observable failures: exact subject and
tenant binding, lease/approval expiry at commit, no repeat after uncertain
effects, control populations, native merge objections, migrations and process
restarts. Similar setup or assertions across these cases do not make their
failure mechanisms interchangeable. The new authority regression extends the
existing five evidence variants rather than creating another fixture family.

The repeated expiry findings also expose a coverage-design gap. Report-time
and output-time checks did not prove validity through the later authority
return. A test count or mutation score cannot establish an unmodeled timeline
boundary. Name the report, final epoch/reviewer lookups, final authority return
and effect commit separately when selecting fault points.

Keep real SQLite, restart and transaction fault tests at their actual authority
boundaries. Keep migration cases on the historical schemas they claim to test.
Keep browser checks for displayed-subject binding, reload and lost-response
identity; a domain test does not replace those browser-specific failures.

Candidates for consolidation are duplicated setup, repeated rendering checks
that have an independent cheaper oracle, and pure-rule cases coupled to whole
application preparation. Before retiring a case, map its trigger and observable
failure to a retained test at the same boundary, then verify that the relevant
harmful mutations are still detected. This audit has not performed that
case-by-case replacement proof and recommends no blanket deletions.

## Prioritized work

1. Record per-test and class-fixture timings as CI artifacts. Refresh shard
   weights from recent runs, including sequence and review modules. Report
   actual versus predicted shard times. On the observed Python 3.11 baseline,
   perfect two-way balance has a lower bound around 574 seconds rather than
   778; overhead and indivisible modules limit the achievable improvement.
2. Split the complete mutation catalogue across independent CI jobs using
   target timing estimates. Keep every declared probe, isolated temporary
   copies and invalid-experiment checks. Measure fail-fast execution of each
   target so a detected mutant need not complete every unrelated subcase.
3. Separate pure domain tests from workflow fixture classes. Build reviewed
   synthetic templates once per required source variant and profile, copy them
   per case, and leave migration/initialization tests independent. Verify that
   writes and cleanup remain isolated and mutation detection is retained.
4. Profile repeated production reconstruction in the slow integration paths.
   Consider reuse of immutable parsed values within a single transaction.
   Preserve the final evidence/actor/lease/time checks. A global cache of a
   positive readiness or approval result would recreate the stale-authority
   failures these tests exist to prevent.
5. Cancel superseded PR runs. Consider testing the oldest and newest supported
   Python versions on each PR with the full version matrix on scheduled runs,
   if that compatibility tradeoff is explicitly accepted. This changes cost
   policy and is not required for rebalancing or fixture improvements.
6. Partition browser tests across separate servers, ports and roots before
   increasing parallelism. Retain exact displayed-subject and recovery cases.

No CI scheduling, Python compatibility policy, browser configuration or test
deletions are changed by this assessment. The authority fix remains separate
from these proposed efficiency changes. No speedup is claimed as implemented.
