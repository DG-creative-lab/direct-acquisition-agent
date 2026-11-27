# Versioned company-context migration

New local work must not inherit a fixed finance product. This is a creation and
routing migration, not a rewrite of saved campaigns or a universal postal model.

## New work

The normal workspace and conversation CLI create `company-context/v2`
conversations. New campaign opens Company & brief. Knowledge has no selected
company evidence. Save and select company/brief revisions through the existing
intake path; interpretation remains unapproved and reviewed preparation/email
export retain their own source, freshness and exact-subject checks.

The chat examples are fictional Fielddesk v2 and authored YouTube placements.
Fielddesk v2 is a distinct authored synthetic specification dated 27 November
2026, reviewed through 27 December 2026. It has new product/profile/fact-pack and
contact mapping identities. It grants no real product verification, customer
permission or provider authority. Original v1 fixtures are unchanged.

A company-context conversation without its authoritative selected intake source
cannot admit the legacy planner, preparation or action router. Both application
preflight and native SQLite admission enforce the boundary before model calls.
An arbitrary company name in a message is not a selected source. A selected intake
plan cannot be converted to a legacy campaign: its managed source and native
preparation contract remain distinct. YouTube and sequence admission retain
separate channel rules; new v2 sequence catalogues contain only Fielddesk v2.

`python -m acquisition demo` prepares an unapproved Fielddesk v2 proposal with no
model, review decision or sending. Its explicit profile form is documented in
[organization profiles](organization-profiles.md). `review-evidence` requires an
explicit `--pack`; it no longer supplies a finance pack.

## Saved work and explicit compatibility

Schema 28 adds `conversations.product_contract`. Existing rows receive
`legacy-fixed-product/v1`. This records their creation policy, not which company
their selected source describes. The upgrade is transactional with the schema journal;
a failed migration rolls back the column, triggers and version together. Update
and replacement guards prevent changing a saved conversation's contract.

The original creation request observes the original conversation and contract.
Saved request payloads, model configuration, prompts, context hashes, task inputs,
review subjects, approvals, delivery/learning records and receipts are not
rewritten. Recovery selects frozen request settings, not the workspace's new
creation default. A known provider receipt can settle its original task without
another provider call. Unknown outcomes remain fenced, and expired evidence or
approval does not become current because the software was upgraded.

Existing postal sessions can still be read, reviewed and resumed through their
original controls. New descendants must bind their actual legacy parent. Fresh
standalone fixed-product creation is unavailable in the normal workspace.
Maintainer tooling can explicitly compose `new_work_contract='legacy-fixed-product/v1'`.
Historical CLI creation/rehearsals require
`--legacy-product-contract legacy-fixed-product/v1`; status, work, calls and review
commands for saved runs keep their identities. The operator-only hosted
preparation API and native profile CLIs still require an explicit profile and
preserve their v1 commands; they never select a finance product implicitly.

Fielddesk workers derive profile versions from the journey's frozen catalogue.
An absent version means original v1. No recovery substitutes v2 content for a v1
journey. A legacy sequence catalogue is rejected when newly admitted against a
company-context/v2 conversation. Inspecting saved content does not refresh it.

## Upgrade and verification

Stop the single local worker, retain a verified checkpoint, and start the current
binary against the same root. Normal initialization migrates local stores. An
operator must migrate remote storage explicitly before using the read-only
serverless composition. Current checkpoint inspection and restore understand
schema 28 and preserve its contract guards. Older binaries reject schema 28;
rollback means restoring the original checkpoint with its matching binary,
not stamping the schema journal backwards.

`tests/test_company_context_migration.py` exercises new-company interpretation,
no-default admission, immutable contracts, physical schema-27 rollback/retry,
provider-receipt recovery, exact legacy approval preservation and a recoverable
Fielddesk v2 sequence. Desktop/mobile browser checks use the actual default
composition. The historical postal corpus opts into v1 explicitly and retains
its substantive assertions. All providers in these checks are authored fakes;
no live targeting, provider calls or deployment is established by these tests.
