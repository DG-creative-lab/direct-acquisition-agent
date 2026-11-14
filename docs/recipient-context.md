# Bounded recipient context

Issue #64 adds a creative-owned retrieval API for minimal, reviewed synthetic
recipient facts. It consumes exact contact readiness assessments and prepares
immutable context artifacts. It does not generate messages, admit model work,
create campaigns, approve content or send anything. The existing postal workflow
and its historical formats remain unchanged.

## Ownership and source contract

`creative` owns `RecipientTarget`, `RecipientDocument`, `RecipientFact`,
`RecipientEvidence`, frozen selection guidance and the `RecipientContextSource`
and `RecipientContextStore` ports. `RecipientContexts` uses those ports;
`bootstrap.build_recipient_contexts` wires the installed source and SQLite
adapters. Creative imports audiences' public native-reference domain contracts
to preserve exact identity rather than invent a second contact model. Runtime
remains business-agnostic.

The source port accepts an organization, installed source key/version and exact
contact/account target. There is no raw query, URL, filesystem path or executable
instruction argument. `read` retrieves one bounded package; `manifest` supplies
a frozen local attestation without provider I/O. Only the recorded synthetic
adapter is installed. A future connector must establish source authorization,
reviewed mappings, data handling and effect recovery before being wired.

A package binds the organization, profile, provider-native contact and account,
experiment unit, source/version, observation window, permitted channel/purpose
uses and declared coverage. It contains at most eight text documents of 4,096
characters and sixteen typed observations. Document kinds represent CRM notes,
webpages, decoded attachment text, inbound bodies and structured records. These
are recorded fixtures, not live CRM, web crawling, email ingestion or attachment
parsing integrations.

The initial reviewed vocabulary covers four slots:

| Slot | Subject | Supported synthetic values |
| --- | --- | --- |
| Contact role | Exact contact | Operations manager, owner/director, procurement manager |
| Prior interaction | Exact contact | Product overview requested, demonstration attended |
| Account activity | Exact account | Equipment quotation or maintenance overview requested |
| Business signal | Exact account | New business location or maintenance program announced |

Event observations carry exact calendar dates. Each observation binds its native
subject, typed value/state, document key, Unicode code-point span, observation
time, expiry, permitted uses and reviewed-mapping reference. Citations retain
SHA-256 fingerprints of exact UTF-8 document and excerpt text. Source identity
binds the full original package. A fact ID is interpreted with its context/source
identity, not as a standalone assertion across sources.

The adapter attests the reviewed mapping from source evidence to the typed value.
The application checks identity, provenance, permission, completeness and
freshness; it does not infer factual truth from arbitrary prose or treat a
`review_id` as campaign approval. Fixture tests establish structural behavior,
not live extraction quality or an independently authenticated reviewer service.

## Selection, missingness and injection boundary

The caller requests supported slots and a maximum of one to four facts. Frozen
guidance chooses their priority and bounds the entire serialized prompt-data
object to at most 2,000 characters. Only requested, necessary, usable facts enter
the projection. Factual sentences are rendered from the reviewed typed vocabulary
with a recorded-observation qualification. Raw document text is never used as
instructions, factual wording, a target selector or a tool request.

Missing, unreviewed, unknown, withdrawn, expired, unpermitted and contradictory
observations are omitted with explicit reasons. An incomplete source supplies no
factual specificity. Sparse results can retain independently usable facts with
`status: partial`; no usable facts yields `insufficient_context` and a bounded
clarification. These statuses do not authorize a message or effect.

Known observations are compared by exact native subject and claim slot across
the organization's relevant source history. Newer evidence prevents using an
older observation. Conflicting observations at the same time remain conflicts
across versions and omissions; a genuinely newer reviewed observation can resolve
them. Account observations can constrain another person at that exact account.
Another person's role or another provider account cannot substitute a subject.
Corroborating evidence that leaves the selected facts unchanged remains usable.
Changing a profile or mapping cannot hide a newer withdrawal for the same native
subject. History can constrain a current candidate across those changes; it never
supplies a grant or copies a fact from a different profile into the selected source.

The service has no model gateway, credential-reading capability or effect tool.
Embedded instructions in source material cannot select another organization,
follow a URL, read a local file, expose a provider key or authorize sending.
There is no paid or uncertain-call retry. Retrieval failure records a fixed
`retrieval_unavailable` diagnostic without exception text; exact replay does not
retrieve again. Remote/paid retrieval is not an installed capability.

## Persistence and current applicability

Schema 19 adds creative-owned immutable source manifests, current source pointers,
context artifacts and exact request receipts. Source versions are consecutive;
observation times cannot move backward, including after an intermediate omission.
The migration is atomic and preserves existing artifact rows and the schema-v3
legacy admission cutoff. Older binaries reject schema 19. Checkpoint inspection
supports schemas 14 through 19 and preserves paused behavior.

Preparation reads current audience evidence before retrieval. Publication holds a
SQLite writer transaction, independently reconstructs the exact recipient and
readiness basis, verifies the source attestation and frozen guidance, then commits
the source, pointer, context and receipt together. Rechecks after writes reject
changed evidence, objections, expiry and paused state. No intermediate context
is made usable when publication fails.

The request key binds the exact assessment, contact, source key/version, slots
and fact limit. Guidance is frozen on the original successful preparation.
Replaying the same request under changed guidance returns the original artifact
and source selection. A new request can select under new guidance. Historical
derivation uses frozen manifest references and the original observation time;
it does not rewrite an artifact when source or guidance changes.
The factual wording of v1 is part of its versioned artifact contract; changing
that renderer requires a new version while preserving historical readers.

`inspect` reports the saved artifact and current applicability separately.
`validate` accepts only exact selected factual statements for the exact target
and rechecks current applicability. It validates explicitly supplied assertions,
not arbitrary free-text messages. Neither operation returns approval or outbound
authority. Later copy and execution workflows must validate their complete output
and recheck facts at their own commit/effect boundaries.

## Retention and redaction boundary

| Material | Implemented handling |
| --- | --- |
| Raw notes, pages, attachment text, inbound bodies | Transient source-adapter data; no raw bodies in context tables, receipts, prompt projections or exports |
| Source audit | Exact native scope, typed observations, reviewed-mapping references, source/version, document/span fingerprints and coverage |
| Prompt projection | Only selected typed factual sentences, fact references and a recipient-scope digest; no destination, name, raw note or credential |
| Context artifacts and checkpoint copies | Immutable synthetic audit records; historical inspection is explicit and does not renew freshness or permission |
| Derived email/call copy and provider-side retention | No new copy or provider dispatch in this slice |

This is not a production retention/deletion implementation. Real personal data
requires a reviewed policy for raw evidence, prompts, derived copy, exports,
backups, access revocation and provider-side storage before a connector or pilot
is enabled. Immutable audit identity does not justify retaining personal content
indefinitely. No live/customer data upload is supported here.

## Agent-facing operation

The API needs no forms. The agent can take the assessment and contact from the
existing contact API, then retrieve context directly:

```python
from pathlib import Path
from acquisition.bootstrap import build_contact_directory, build_recipient_contexts

path = Path('.local/contacts.sqlite')
directory = build_contact_directory(path, 'demo', 'fielddesk')
assessment = directory.prepare('demo', 'readiness-1', 'fielddesk-crm-a', 1, 'email')
contact_id = assessment['report']['eligible'][0]
service = build_recipient_contexts(path, 'demo', 'fielddesk')
result = service.prepare('demo', 'context-1', assessment['assessment_id'], contact_id,
    'reviewed-context-a', 1, slots=('contact_role', 'prior_interaction'), max_facts=2)
```

The explicit CLI is `python3 -m acquisition.recipient_cli` with `PYTHONPATH=src`.
It supports `prepare`, `inspect` and exact-assertion `validate`. Organization is
trusted local scope, not hosted authentication. Installed `reviewed-context-a/b`
versions 1 through 4 demonstrate initial evidence, role withdrawal, a newer role
and an incomplete source. Fixtures expire on 24 November 2026 at 00:00 UTC.
Inspecting saved history remains available afterward; new usable context requires
current evidence. Conversational routing and personalized email/call content
remain separately tracked in epic #60.
