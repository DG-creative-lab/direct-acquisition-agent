# Scoped contact evidence and preparation readiness

The additive [audience strategy slice](audience-strategies.md) consumes these exact assessments through audiences-owned inference ports and campaign-owned constraints. It does not turn an assessment into outbound authority.

Issue [#62](https://github.com/DG-creative-lab/direct-acquisition-agent/issues/62), under [epic #60](https://github.com/DG-creative-lab/direct-acquisition-agent/issues/60).

This foundation records scoped account/contact sources, channel permission observations, shared pressure inputs and local objections. It prepares immutable, non-executable contact-readiness assessments for either installed company profile. It creates no campaign, approval, model request, email or call task. The existing postal audience, campaign, review and learning formats retain their original meaning.

## Installed scope

Bootstrap wires a recorded synthetic source and the SQLite store through audiences-owned ports. Both `iwoca` and `fielddesk` have two provider accounts, selected by `<profile>-crm-a` and `<profile>-crm-b`. Each source deliberately uses the same native IDs. Version 1 has two accounts and three people, including two people at one account. Version 2 merges the first person into the second. Version 3 deletes their account. These are authored fixtures, not CRM integration evidence.

The source port separates bounded retrieval from resolving an immutable attested identity. Identity checks under the SQLite write lock use frozen attestations, without provider requests. Future remote adapters must capture their bounded source response before that transaction and supply the same frozen version for validation.

Email addresses end in `.invalid`; telephone destinations carry `DEMO ONLY DO NOT CALL:`. Source and permission windows expire on 24 November 2026 at 00:00 UTC. Tests use controlled clocks. A later source window needs a genuinely reviewed new fixture/version. The installed adapter accepts no arbitrary file, URL, credential, uploaded data or executable tenant configuration.

Contact evidence supports the purposes and channels in `contact-preparation/v1`: acquisition evidence for email, human calls and postal contact. Email and call evidence can be assessed in simulation. Postal rendering for the new contact schema is explicitly unavailable. Existing postal preparation continues through its original contracts. This does not enable email campaigns under the postal-only `CampaignProfile` capability.

## Operating API and CLI

Prepare one assessment from a verified installed source, atomically importing that exact source if necessary:

```sh
PYTHONPATH=src python3 -m acquisition.contact_cli \
  --db .local/contact-demo.sqlite --organization demo --profile fielddesk \
  prepare --request-id first-email --connection fielddesk-crm-a --version 1 \
  --channel email --purpose acquisition
```

The result contains an assessment identity, source/profile bindings, per-person reasons, eligible contact IDs and account experiment units. `ready_for_proposal` describes contact evidence only. `authority: none`, `approval: not_granted` and `execution: not_performed` remain explicit. Eligibility is neither a deliverable validation report nor permission to contact anyone.

Inspect the saved observation and its current applicability:

```sh
PYTHONPATH=src python3 -m acquisition.contact_cli \
  --db .local/contact-demo.sqlite --organization demo --profile fielddesk \
  inspect --assessment-id CONTACT_ASSESSMENT_ID
```

`saved` is immutable. `current` is recomputed from the current source head, permission windows, native lifecycle, objections and existing business suppressions. `currently_applicable` requires the saved report to match that current result. `current_ready_for_proposal` additionally requires complete ready evidence. Inspection performs no writes and works on supported inspection-only checkpoints. It cannot supply cached authorization to a future sender.

Record a local objection with the exact contact ID from the assessment:

```sh
PYTHONPATH=src python3 -m acquisition.contact_cli \
  --db .local/contact-demo.sqlite --organization demo --profile fielddesk \
  object --request-id objection-1 --contact-id NATIVE_CONTACT_ID \
  --channel email --purpose acquisition --reason "The recipient objected to this purpose."
```

`all` is supported for objection channel and purpose. Objections are permanent in this slice; a later source grant cannot erase them. A separate reviewed correction/re-consent lifecycle is required before supporting withdrawal of objections.

Refresh a source without preparing another assessment:

```sh
PYTHONPATH=src python3 -m acquisition.contact_cli \
  --db .local/contact-demo.sqlite --organization demo --profile fielddesk \
  refresh --request-id source-merge --connection fielddesk-crm-a --version 2
```

Versions advance consecutively from 1, without skipping or rewinding. Repeating an exact request returns its historical receipt, never a fresh authorization or a source-head rewind. Changed inputs under the same request key conflict. A different request for identical evidence at the same checked time reuses the immutable assessment while retaining a separate command receipt.

The Python API is `build_contact_directory(...).prepare/refresh/object/inspect`. These bounded operations are available for later agent composition. New chat routing and the full multichannel user journey belong to #68. No configuration wizard or frontend flow is introduced here. Organization arguments provide trusted local scoping, not hosted authentication.

## Identity and evidence contracts

- A connection retains organization, logical connection key, provider, provider account and mapping version. A native reference also retains the exact native object type and ID, with a separate mapped account/contact role. Names and email addresses never resolve identity.
- Native execution identity includes organization, provider, provider account, native type and native ID. Changing a connection alias or mapping version does not rename the person or erase objections. Two different provider accounts using ID `1` remain distinct. A mapping cannot reinterpret a known native person as an account.
- Association evidence is explicit. Zero, multiple, absent or cross-scope account references do not become an eligible resolved person. Unknown association and incomplete source pagination prevent a complete ready population.
- Permission observations bind the exact contact, channel, acquisition purpose, source, observed time and expiry. Missing, unknown, denied and expired states remain distinct. A score or deliverability assertion supplies no permission. These fixture observations establish no legal or provider permission for real outreach.
- Newer or contradictory evidence from another known connection to the same native person invalidates stale permission and pressure readiness. Known shared-account pressure changes also require fresh coherent evidence. Observations are never silently copied into an older source to create a grant or replenish a count.
- A reviewed source maps an account to its organization-scoped business/experiment key. Multiple contacts at that account share one experiment unit. The system does not infer cross-CRM business identity from a matching name or address, or create counted learning outcomes from assessments.
- Pressure observations retain contact/account counts, experiment unit, 90-day window, source, coverage and expiry. Missing, inconsistent or partial counts prevent complete readiness. The transparent synthetic preparation policy excludes contacts at two prior contacts and accounts at four. These are versioned demonstration limits, not commercial recommendations.

Pressure observations describe known past activity. Assessments consume no capacity. Shared reservations, ordered sequence costs and final dispatch-time caps belong to the later engagements/sequence slices. This foundation does not claim concurrent outbound-cap enforcement.

## Lifecycle and transaction boundaries

`audiences` owns source values, identity, permission/pressure observations, merge ancestry and `ContactDirectory`. `campaigns.contact_eligibility` owns deterministic hard preparation checks. SQLite loads current review-owned business suppressions and their audience epoch without changing review authority. `ContactSource` and `ContactDirectoryStore` are narrow ports; bootstrap alone selects their implementations. Runtime, reasoning, creative and learning gain no contact-specific imports or behavior.

Only an installed source attestation can supply source bytes. Consistently rehashing replacement contacts, destinations or source metadata cannot publish them through the store. Every durable contact read/write is organization-scoped. Sources, objections, assessments and command receipts are immutable. The mutable current-source pointer must agree with the latest immutable version.

Import checks the current head, exact source attestation, source/profile binding, native role, experiment identity and complete merge/deletion history. Complete refreshes retain every known identity or an explicit tombstone; source, permission and pressure observation times cannot move backward. Deletion and merging cannot be undone by a later active record, mapping revision, connection alias or omitted intermediate population. Merge ancestry propagates objections across known native aliases. It never retargets saved work or transfers a permission grant. A stale alternate connection cannot restore a known retired native identity. Known exclusions do not require fresh permission or contextual data merely to remain excluded.

Pressure conflict checks retain the latest observation time for each source/contact, including conflicting observations at that same time. A later source version carrying older pressure cannot erase fresher evidence, even in history accepted by a prior writer. Missing observations do not erase earlier ones. Genuinely later evidence can supersede earlier counts, including a lower count for a newer window; the system does not latch the highest historical count. Historical source bytes and saved assessments remain unchanged.

Permission reconciliation follows the same chronology rule for each source/contact/channel/purpose. A later source version cannot erase a denial or different expiry observed at the same time. Equal-time disagreements remain incomplete until genuinely newer coherent evidence arrives. Omitting an observation does not erase it, and permission grants are never copied between contacts, channels or source snapshots.

Preparation commits source/head changes, assessment and exact command receipt in one `BEGIN IMMEDIATE` transaction. After writes it recomputes current eligibility under the same lock, including the clock, source, lifecycle, objections and suppressions. A changed basis or expiry rolls back the whole bundle. Historical read/replay is separate from fresh applicability.

Schema 18 adds five contact-owned tables and append-only guards in the application database. Migration and version update share the existing lock/transaction; the schema-v3 legacy admission cutoff is preserved. Older application binaries reject schema 18. Supported schema-14 through schema-18 checkpoints remain inspection-only, and restoration never enrolls new execution authority. Unsealed local stores support this foundation; verified-paused stores gain no contact mutation capability. Read-only inspection remains available.

## Verification and remaining work

Real SQLite tests cover provider/account/type isolation; exact replay in a fresh interpreter; forged source substitutions; ambiguous, incomplete, missing, expired and denied evidence; pressure consistency and isolated caps; current business suppression; mapping/connection aliases and superseding native evidence; merge/deletion and objection invalidation; role changes; duplicate observations; post-write objections and expiry; concurrent request conflict; immutable history; schema-17 migration rollback and the legacy cutoff. The existing cold-backup round trip now retains nonempty contact history and inspects it through the CLI without changing restored bytes.

See [validation](validation.md) for executed results. Real CRM mapping, legal/provider eligibility policy, global capacity reservations, hosted roles, customer data, real sending/calling, model ranking, personalized copy, sequence approval and counted commercial learning remain separate issues.
