# Fictional Fielddesk preparation example

Fielddesk Demo is an authored visit-planning product with maintenance and
installation audiences. No real company, product service or customer data is
represented. This is the company-independent profile example for the platform.

The files were produced by the existing `build_profile_preparation` API using
a fresh temporary SQLite database, the installed `fielddesk/v1` profile, 100
synthetic input records and seed 42. The explicit simulated date is
**13 November 2026**, inside the unchanged v1 specification's recorded window.
The window expires on 24 November. This is a reproducible rehearsal, not a
new attestation that the old pack is current today.

| File | Meaning |
| --- | --- |
| [proposal.json](proposal.json) | Exact prepared-result identity, frozen plan, counts, illustrative cost and absence of approval/execution |
| [manifest.json](manifest.json) | Exact proposal manifest, product/profile lineage, fixture copy and hashes |

The result has 100 inputs, 24 exclusions, six no-mail controls and 70 fictional
mailing assignments. Its 5,950-pence cost is illustrative. `approval` remains
`not_granted`, `execution` is `not_performed` and `semantic_screen` is
`not_evaluated`. There are no provider calls, generated-model quality claims,
customer outcomes or delivery rights. No source evidence or stored approval is
borrowed from the legacy product.

## Reproduce offline

Run from the repository root. This code uses an isolated temporary store and
explicit fixture time; it does not change installed configuration or persist a
customer workspace:

```sh
PYTHONPATH=src python3 - <<'PY'
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import json
from acquisition.bootstrap import build_profile_preparation

fixture_time = datetime(2026, 11, 13, tzinfo=timezone.utc).timestamp()
with TemporaryDirectory(prefix="fielddesk-example-") as folder:
    app = build_profile_preparation(
        Path(folder) / "example.sqlite", "fielddesk-example", "fielddesk",
        lambda: fixture_time,
    )
    result = app.prepare(
        "fielddesk-example", "fielddesk-reference-v1", "fielddesk", "v1",
        objective="Compare responses to fictional visit-planning questions.",
        budget_pence=60000, segments=("maintenance", "installations"),
        country="UK", currency="GBP", channel="direct_mail", size=100, seed=42,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
PY
```

The printed JSON matches `proposal.json`. A fresh request using the actual
current date after expiry must be rejected. Do not use the fixture clock to
renew evidence for real work. A newly reviewed specification/version is the
proper path to a current example.

The [profile guide](../../docs/organization-profiles.md) describes the API
contract. Profile preparation is not the legacy postal approval path and cannot
be submitted as a legacy review/handoff subject.
