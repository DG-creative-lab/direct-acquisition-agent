# Confirmed writing preferences

A saved copy comment records feedback on an exact variant. **Remember as a
writing preference** opens a separate confirmation. The operator edits the
preferred wording, optionally records wording to avoid, selects Stock & inventory,
Projects & contractors, or both, and supplies a reason. Explicit confirmation
authorizes saving that guidance. Commenting, praising copy and approving a
campaign do not create preferences.

The preference applies to future conversation campaign contexts in the same local
workspace organization. Its audience scope is explicit and may differ from the
source variant's audience. The original comment, conversation/revision, campaign
scope, draft, subject, creative, segment and experimental arm remain attached.
The interface exposes this source and every decision's operator, time and reason.

**Correct writing preference** creates a new version with independently confirmed
wording and audience scope. **Retire writing preference** records a reason and
excludes that preference from future contexts. Retirement is terminal for that
preference. Both actions require the exact displayed version. Existing versions,
comments, artifacts and frozen contexts are preserved.

New contexts take up to three recent active preferences per audience, with the
existing local CLI/authored examples filling unused places. A correction makes
that preference recent again. Both audience contexts use one SQLite read
snapshot, so a concurrent correction or retirement cannot split their versions.
Each frozen source retains the preference version and original comment provenance.
Already admitted copy and follow-up work uses its original contexts.

The model projection includes the confirmed preferred/avoided wording, confirmed
reason and source identifiers. Original source feedback remains in the immutable
preference journal and full frozen audit context, and is omitted from model
requests. Historical frozen context bytes are never rewritten for this projection.
If an audience has no active preference or existing CLI example, the same read
snapshot selects an authored example from the current frozen guidance. Campaign
and follow-up contexts cannot acquire an empty required memory enum when a
preference is concurrently retired.

## Ownership and effects

`creative` owns preference validation and its narrow persistence port. The SQLite
adapter verifies the original scoped comment receipt, matching audit record,
immutable subject and draft, and conversation ownership. It checks the active
local operator inside the write transaction. The browser supplies no organization
or operator identity. The workspace resolves the source campaign and uses the
fixed `local-conversations` owner for conversation preferences. Standalone CLI
campaigns retain their own organization-scoped examples.

Schema 15 adds `writing_preference_versions`. Each immutable version is the
decision, audit record and command receipt in one insert. The organization and
request ID bind exact inputs. Competing corrections use the expected revision
under the SQLite write lock. An uncertain response keeps the exact browser
decision and request identity through reload; retry retrieves the original
receipt. A post-commit projection failure cannot report a definitive rejection.
Update/delete guards and a before-insert conflict guard protect both the version
key and scoped request ID, including `INSERT OR REPLACE` on normal SQLite
connections. Opening an existing live schema-15 store installs the insert guard
without altering its recorded versions. Checkpoint inspection performs no repair.

The context source is `reviewer_preference`, with style-guidance use only. A
preference supplies no product facts, outcomes, approval, budget or execution
permission. Saving, correcting and retiring make no model calls. Targeted copy
revision retains its existing separate consent and frozen-context behavior.
Paid inference remains paused in verified workspaces.

Migration preserves the existing application identity, admission seal and legacy
cutoff. Failure rolls back the new table, guards and schema version together.
Schema 14 and 15 checkpoints are supported; older schema-14 checkpoints expose no
confirmed preferences and remain untouched. Restored roots stay inspection-only,
including attempts to replay a preference command.

## Verification

Real SQLite and fresh-process checks cover confirmation, cross-conversation and
organization rejection, missing source audit, exact-input replay, stale and
concurrent corrections, atomic failure, retirement, frozen contexts, audience
scope across later campaigns, schema migration and cold restores. The offline
browser journey covers explicit consent, dismissal without an effect, desktop
and mobile, a dropped save response followed by reload and exact retry, correction,
source/history inspection and retirement. These checks make no live quality claim.
