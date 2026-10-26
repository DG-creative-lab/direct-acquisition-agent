import random
from datetime import date, timedelta

from acquisition.audiences import Business, Snapshot


def generate(organization: str, size: int = 1000, seed: int = 42, as_of: str = "2026-10-25") -> Snapshot:
    if type(size) is not int or not 1 <= size <= 400_000 or type(seed) is not int:
        raise ValueError("Use 1–400,000 synthetic records and an integer seed")
    today, rng = date.fromisoformat(as_of), random.Random(seed)
    rows = []
    for index in range(size):
        business_number = index - 1 if index > 0 and index % 97 == 0 else index
        rows.append(Business(
            record_id=f"record-{index:06}", business_id=f"synthetic-{business_number:06}",
            segment="inventory" if index % 2 == 0 else "contractors",
            country="DE" if index % 31 == 0 else "UK",
            entity_type="SOLE_TRADER" if index % 37 == 0 else "LTD",
            address=f"DEMO ONLY DO NOT POST: synthetic contact {index:06}",
            deliverable=index % 29 != 0, suppressed=index % 13 == 0,
            contacts_last_90_days=2 if index % 41 == 0 else 0,
            last_contact=(today - timedelta(days=7)).isoformat() if index % 43 == 0 else None,
            propensity_ppm=None if index % 47 == 0 else rng.randint(1000, 50000),
        ))
    return Snapshot(organization, as_of, tuple(rows), seed)
