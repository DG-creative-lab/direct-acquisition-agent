from pathlib import Path
from tempfile import NamedTemporaryFile

from acquisition.campaigns import Draft
from acquisition.contracts import canonical
from acquisition.creative import fact_pack_id


def export_draft(draft: Draft, directory: Path, contexts: tuple[dict, ...] = ()) -> Path:
    # Content-addressed directory prevents different drafts overwriting each other.
    destination = directory / draft.id
    destination.mkdir(parents=True, exist_ok=True)
    contents = [("manifest.json", canonical(draft.manifest) + "\n"),
                ("mailing.csv", draft.mailing_csv), ("assignments.csv", draft.assignments_csv)]
    if any(item.get("status") == "generated_unreviewed" for item in draft.manifest["creatives"]):
        letters = ["SYNTHETIC GENERATED COPY. HUMAN REVIEW REQUIRED. NO RELEASE AUTHORITY.\n"]
        for item in draft.manifest["creatives"]:
            letters.append("\n".join((item["id"], item["headline"], item["opening"], item["locked_block"], "")))
        contents.append(("letters.txt", "\n".join(letters)))
    packs = {fact_pack_id(c["product_facts"]): c["product_facts"] for c in contexts if "product_facts" in c}
    required_packs = {c["fact_pack_id"] for c in draft.manifest["creatives"] if c.get("fact_pack_id")}
    if required_packs != set(packs):
        raise ValueError("Grounded export requires the exact frozen source packs")
    if packs:
        contents.append(("product-evidence.json", canonical({"status": "public_source_evidence_not_lender_approval",
                                                           "packs": packs}) + "\n"))
    for name, content in contents:
        with NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=destination,
                                prefix=name, suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        try:
            temporary.replace(destination / name)
        finally:
            temporary.unlink(missing_ok=True)
    return destination
