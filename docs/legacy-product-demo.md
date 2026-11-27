# Legacy fixed-product demonstration

This is a compatibility reference, not the platform's current product
specification or recommended pitch example. The original direct-mail prototype
used public iwoca Flexi-Loan material. Current documentation leads with
[fictional Fielddesk and contextual YouTube examples](../examples/README.md)
and the user's explicitly reviewed company context.

New local workspace conversations now use `company-context/v2`. New campaign
opens Company & brief, Knowledge has no default company evidence, and the offline
starter uses fictional Fielddesk v2. The fixed-product planner is no longer a
fallback for new company-context requests. See the
[versioned migration contract](company-context-migration.md).

The old postal path remains installed for saved v1 work and explicitly selected
compatibility tooling. Its material may appear when inspecting that saved work.
The operator-only hosted preparation API and low-level profile CLIs require an
explicit installed profile; neither chooses the finance profile by default.

## Retained identities and evidence

| Item | Why it remains |
| --- | --- |
| `config/iwoca-product-facts-v1.json` | Frozen original public-source pack used by saved grounded-copy requests and validation |
| `config/profiles/iwoca-v1.json`, key `iwoca/v1` | Original explicit profile identity retained alongside the fictional profile |
| Product key `iwoca_flexi_loan` | Serialized value used by the legacy campaign/brief scope and its literal interpreter |
| Official source `https://www.iwoca.co.uk/flexi-loan` | Exact original provenance; the old grounding validator checks this source identity |
| `monthly-mail/v2` and `monthly-mail/v3` | Historical ungrounded and grounded task contracts with their existing admission/recovery limits |
| [Recorded grounded run](../examples/grounded-run/README.md) | Original source evidence, generated copy and limited recorded usage, preserved as historical bytes |

The original pack records two bounded product statements, their qualifications,
a general assessment qualification and an official CTA. It is public-source
evidence, not lender approval of the prototype or its copy. It records a
25 October 2026 check and a 24 November review deadline. That deadline is not
renewed by archiving the example, changing documentation or renaming a company.

The application has no connection to the lender's production systems, contains
no lender customer feed, makes no credit decisions and sends no mail.
Do not replace real-source statements with invented fictional lending claims or
present old demonstration costs and audience labels as commercial evidence.

## Operating contracts that still apply

The [legacy grounding guide](product-grounding.md), [postal walkthrough](user-guide.md)
and [requested-scope contract](requested-campaign-scope.md) describe the installed
legacy path. They remain useful to maintainers and for recovery. They do not
define which products, countries, channels or reward models the broader platform
must support.

Saved contexts, evidence hashes, request bytes, capability versions, artifact
identities, review subjects and receipts retain their original meaning.
Old copy does not become company-independent because a name is replaced.
A fictional proposal cannot inherit the old profile's approval or outcome
counts. Dates in an authored rehearsal do not authorize current customer work.

## Compatibility requirements

The versioned migration retires the implicit local default. Maintain these
requirements when extending the current company/channel workflows:

- Inventory the defaults in `bootstrap.py`, `campaigns.CampaignScope`,
  `conversations`, the fixed-source grounding policy, CLI defaults and browser
  labels/selectors.
- Route new work through explicit company/product/context identity, with an
  appropriate versioned channel contract and exact review subject.
- Preserve old-request interpretation and original provider-receipt recovery.
  Prompt edits need supported version dispatch, not a text substitution under
  an existing saved version.
- Keep the old identities available only where compatibility requires them;
  do not globally rewrite manifests, evidence or stored rows.
- Prove new-company success alongside old-run read/recovery, rejected scope
  substitution, stale approval, unknown provider outcome and rollback cases.

The broader [platform map](gtm-platform-map.md) defines module ownership. This
reference introduces no new finance-product requirements and authorizes no live
provider activation.
