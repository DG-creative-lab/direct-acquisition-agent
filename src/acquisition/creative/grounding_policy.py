"""Pure evidence, wording, provenance and grounded copy validation."""
import json
import re
import unicodedata
from datetime import date
from urllib.parse import urlparse
from acquisition.contracts import Conflict, canonical, digest
from acquisition.reasoning import tool_contract, validate_assets
from .copy_contracts import READ, tool
from .domain import Creative
from .profiles import ProductProfile, context_product_profile

SUBMIT = tool("submit_grounded_copy", "Submit two audience hooks and select one supplied fact for each. Code renders product text.", {
    **{field + "_" + arm: {"type": "string", "maxLength": maximum,
        "description": {"headline": "A short sentence-case question about the segment's possible business situation, with no product claims.",
                        "opening": "One short conditional question about planning stock/project expenses or supplier/client PAYMENT timing. No loan REPAYMENTS, financial product benefits or implied outcomes, even as a question. Avoid improve, control, help, simplify and smooth.",
                        "hypothesis": "A prediction about why this wording might change audience engagement. Do not speculate about product attributes or business outcomes.",
                        "fact_id": "Select exactly one ID from the supplied product facts."}[field]}
       for arm in ("a", "b") for field, maximum in (("headline", 80), ("opening", 240), ("hypothesis", 240), ("fact_id", 100))},
    "guidance_id": {"type": "string"}, "memory_id": {"type": "string"}, "fact_pack_id": {"type": "string"}
}, [field + "_" + arm for arm in ("a", "b") for field in ("headline", "opening", "hypothesis", "fact_id")]
   + ["guidance_id", "memory_id", "fact_pack_id"])


CHECK = tool("record_claim_check", "Record an independent screen of both generated headlines and hooks.", {
    "candidate_hash": {"type": "string"}, "fact_pack_id": {"type": "string"},
    **{arm + "_verdict": {"type": "string", "enum": ["pass", "reject"]} for arm in ("a", "b")},
    **{arm + "_reason": {"type": "string", "maxLength": 400} for arm in ("a", "b")}
}, ["candidate_hash", "fact_pack_id", "a_verdict", "a_reason", "b_verdict", "b_reason"])


def grounded_tool_contracts():
    return [tool_contract(READ, "v1", "read_context", ["frozen_scoped_context"], ["editorial_context"]),
            tool_contract(SUBMIT, "v3", "propose", ["context_read", "fresh_product_evidence"], ["unreviewed_pair"]),
            tool_contract(CHECK, "v1", "screen", ["exact_candidate_hash_and_fact_pack"], ["advisory_pair_verdict"])]


def copy_source_payloads(context):
    return {"editorial": context["guidance"], "product_facts": context["product_facts"],
            "preferences": context["memory"], "outcomes": context["audience_summary"]["outcome_evidence"],
            "audience": {k:v for k,v in context["audience_summary"].items() if k != "outcome_evidence"}}


def validate_copy_assets(context, organization=None):
    profile = context_product_profile(context)
    if "agent_assets" in context:
        if profile is not None:
            raise ValueError('Profile reasoning assets require their explicit successor contract')
        if context["agent_assets"].get("model_projection") not in {None, "copy-context/v1"}:
            raise ValueError("Unsupported copy context projection")
        expected_skill = "revise-grounded-copy/v1" if context.get("copy_revision") else "grounded-copy/v1"
        if [s["id"] for s in context["agent_assets"]["skills"]] != [expected_skill]:
            raise ValueError("Unsupported skill for this copy task")
        expected_kinds = {"editorial":"authored_guidance", "product_facts":"product_evidence",
                          "preferences":"reviewer_preference", "outcomes":"synthetic_observation", "audience":"audience_summary"}
        if {m["key"]:m["kind"] for m in context["agent_assets"]["sources"]} != expected_kinds:
            raise ValueError("Knowledge source classification differs from copy contract")
        validate_assets(context["agent_assets"], organization=organization, installed_tools=grounded_tool_contracts(),
                        payloads=copy_source_payloads(context))


def fact_pack_id(pack: dict) -> str:
    return "facts_" + digest(pack)


def validate_fact_pack(pack: dict, today: date, *, profile: ProductProfile | None = None) -> None:
    try:
        if profile is not None and (type(profile) is not ProductProfile or digest(pack) != profile.fact_pack_hash
                                    or pack['product'] != profile.product):
            raise ValueError('Product pack differs from its reviewed profile')
        checked, review = date.fromisoformat(pack["checked_on"]), date.fromisoformat(pack["review_by"])
        if not checked <= today <= review or not 0 < (review - checked).days <= 30:
            raise ValueError("Product evidence is future-dated or requires re-verification")
        if not pack["version"] or not pack["product"] or not pack["verification"]:
            raise ValueError("Missing product provenance")
        sources = {s["id"]: s for s in pack["sources"]}
        if not sources or len(sources) != len(pack["sources"]):
            raise ValueError("Missing or duplicated product source")
        for source in sources.values():
            url = urlparse(source["url"])
            allowed = (source['url'] in profile.official_urls if profile is not None else
                       url.netloc == 'www.iwoca.co.uk' and url.path == '/flexi-loan')
            if (not allowed or url.scheme != "https"
                    or url.query or url.fragment or source["checked_on"] != pack["checked_on"]):
                raise ValueError("Product source must be the reviewed official product page")
        ids = set()
        for fact in pack["facts"]:
            if not fact["id"] or fact["id"] in ids or fact["source_id"] not in sources:
                raise ValueError("Broken product fact provenance")
            ids.add(fact["id"])
            for field in ("copy", "qualification"):
                bounded_text(fact[field], 300)
        if not ids:
            raise ValueError("At least one sourced product fact is required")
        for field in ("required_qualification", "cta"):
            bounded_text(pack[field], 300)
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError("Incomplete product evidence pack") from error


def bounded_text(text: str, maximum: int) -> None:
    if (type(text) is not str or not 1 <= len(text.strip()) <= maximum or text != text.strip()
            or any(unicodedata.category(c).startswith("C") for c in text)):
        raise ValueError("Invalid text length, whitespace or hidden/control characters")
    if chr(0x2014) in text:
        raise ValueError("Use full stops, commas or colons instead of em dashes")


def validate_framing(headline: str, opening: str, segment: str, *, profile: ProductProfile | None = None) -> None:
    bounded_text(headline, 80)
    bounded_text(opening, 240)
    text = unicodedata.normalize("NFKC", headline + " " + opening).casefold()
    forbidden = re.search(r"\d|[£$€%]|https?[:/]|www\.|\b(?:iwoca|flexi|loan\w*|financ\w*|credit|borrow\w*|interest|"
                 r"rate[sd]?|apr|fees?|repay\w*|approv\w*|eligib\w*|qualif\w*|guarantee\w*|"
                 r"tailored|bespoke|flexible|instant\w*|fast|free|fca|always|never|ensure\w*|boost\w*|"
                 r"unlock|save|saves)\b", text)
    if forbidden:
        raise ValueError("Generated framing contains a prohibited product/price/outcome term: " + forbidden.group(0)
                         + ". Describe supplier/client payments, not loan repayments or product benefits.")
    if re.search(r"we know|you need|you are short|you're short|you have (?:a )?(?:cash|money)|(?:stay|keep jobs) on schedule", text):
        raise ValueError("Generated framing assumes personal need or promises an outcome")
    if re.search(r"\b(?:smooth\w*|simplif\w*|improv\w*|control|benefit\w*|easier|better|help\w*|secur\w*)\b", text):
        raise ValueError("Generated framing implies a business benefit, even if posed as a question. Ask only about stock/project costs and payment dates.")
    vocabulary = {"inventory": r"\b(stock|inventory|supplier|shelves|order|purchase)\w*\b",
                  "contractors": r"\b(project|client|contract|material|labour|job|invoice)\w*\b"}
    if profile is not None:
        vocabulary = {key: r'\b(?:' + '|'.join(re.escape(term) for term in terms) + r')\w*\b'
                      for key, terms in profile.segment_terms}
        if any(re.search(r'\b' + re.escape(term) + r'\w*\b', text) for term in profile.prohibited_terms):
            raise ValueError('Generated framing contains profile product wording')
    if segment not in vocabulary or not re.search(vocabulary[segment], text):
        raise ValueError("Framing must refer to the requested segment's business situation")


def proposal(arguments: dict, context: dict) -> list[dict]:
    profile = context_product_profile(context)
    required = {field + "_" + arm for arm in ("a", "b") for field in ("headline", "opening", "hypothesis", "fact_id")}
    if not isinstance(arguments, dict) or set(arguments) != required | {"guidance_id", "memory_id", "fact_pack_id"}:
        raise ValueError("Submit the exact flat grounded-copy fields")
    pack = context["product_facts"]
    if (arguments["guidance_id"] != context["guidance"]["version"]
            or arguments["memory_id"] not in [m["id"] for m in context["memory"]]
            or arguments["fact_pack_id"] != fact_pack_id(pack)):
        raise ValueError("Cite the exact frozen guidance, memory and product pack")
    facts = {f["id"] for f in pack["facts"]}
    result = []
    for arm in ("a", "b"):
        item = {field: arguments[field + "_" + arm] for field in ("headline", "opening", "hypothesis", "fact_id")}
        if type(item["fact_id"]) is not str or item["fact_id"] not in facts:
            raise ValueError("Choose an available product fact ID")
        validate_framing(item["headline"], item["opening"], context["segment"], profile=profile)
        bounded_text(item["hypothesis"], 240)
        result.append(item | {"arm": arm.upper()})
    if result[0]["opening"].casefold() == result[1]["opening"].casefold():
        raise ValueError("A and B require distinct openings")
    return result


def candidate_hash(items: list[dict], pack_id: str) -> str:
    return digest({"variants": items, "fact_pack_id": pack_id})


def checked_verdict(arguments: dict, expected_hash: str, pack_id: str) -> dict:
    required = {"candidate_hash", "fact_pack_id", "a_verdict", "a_reason", "b_verdict", "b_reason"}
    if not isinstance(arguments, dict) or set(arguments) != required:
        raise ValueError("Claim check must cover exactly both variants")
    if arguments["candidate_hash"] != expected_hash or arguments["fact_pack_id"] != pack_id:
        raise ValueError("Claim check is not bound to this exact copy and evidence")
    for arm in ("a", "b"):
        bounded_text(arguments[arm + "_reason"], 400)
        if arguments[arm + "_verdict"] != "pass":
            raise ValueError("Semantic claim screen rejected variant " + arm.upper() + ": " + arguments[arm + "_reason"])
    return arguments


def product_suffix(pack: dict, fact_id: str) -> str:
    fact = next(f for f in pack["facts"] if f["id"] == fact_id)
    return " " + " ".join((fact["copy"], fact["qualification"], pack["required_qualification"], pack["cta"]))


def historical_hook(creative: dict, context: dict | None = None) -> str:
    """Read original framing without promoting its old product block to evidence."""
    opening = creative['opening']
    if type(opening) is not str or not opening.strip():
        raise Conflict('The source creative has no recorded hook')
    if creative.get('fact_pack_id'):
        if (not context or context.get('segment') != creative['segment']
                or fact_pack_id(context['product_facts']) != creative['fact_pack_id']):
            raise Conflict('The source creative differs from its frozen product context')
        try:
            suffix = product_suffix(context['product_facts'], creative['fact_id'])
        except StopIteration:
            raise Conflict('The source creative fact is absent from its frozen context') from None
        if not opening.endswith(suffix) or not opening[:-len(suffix)].strip():
            raise Conflict('The source creative product suffix differs from its frozen context')
        return opening[:-len(suffix)]
    return opening


def validate_grounded_catalogue(variants: tuple[Creative, ...], context: dict, today: date) -> None:
    validate_copy_assets(context)
    profile = context_product_profile(context)
    fixture = profile is not None and context['copy_mode'] == 'fixture'
    pack = context["product_facts"]
    validate_fact_pack(pack, today, profile=profile)
    pack_id = fact_pack_id(pack)
    if len(variants) != 2 or [v.arm for v in variants] != ["A", "B"]:
        raise ValueError("Grounded catalogue requires complete ordered A/B pair")
    items = []
    for item in variants:
        if item.fact_pack_id != pack_id or item.segment != context["segment"]:
            raise ValueError("Creative has different product evidence or segment")
        if item.fact_id not in {f["id"] for f in pack["facts"]}:
            raise ValueError("Creative selected an unknown fact")
        suffix = product_suffix(pack, item.fact_id)
        if not item.opening.endswith(suffix) or item.locked_block != context["guidance"]["locked_block"]:
            raise ValueError("Product wording, qualification, CTA or demonstration disclosure changed")
        hook = item.opening[:-len(suffix)]
        validate_framing(item.headline, hook, item.segment, profile=profile)
        bounded_text(item.hypothesis, 240)
        if (item.status != ('synthetic_profile_fixture_unapproved' if fixture else 'generated_unreviewed')
                or (item.model != 'offline-fixture/v1' if fixture else not item.model)
                or not {pack_id, item.fact_id, context["guidance"]["version"]} <= set(item.evidence_ids)
                or not set(item.evidence_ids) & {m["id"] for m in context["memory"]}):
            raise ValueError("Grounded copy requires unreviewed status and evidence provenance")
        items.append({"headline": item.headline, "opening": hook, "hypothesis": item.hypothesis,
                      "fact_id": item.fact_id, "arm": item.arm})
    revision_items(context, items)
    if fixture:
        if any(v.claim_check != 'not_evaluated' for v in variants):
            raise ValueError('Offline fixtures cannot claim a semantic screen')
        return
    if variants[0].claim_check != variants[1].claim_check:
        raise ValueError("Copy pair has different claim-check receipts")
    try:
        checked_verdict(json.loads(variants[0].claim_check), candidate_hash(items, pack_id), pack_id)
    except (json.JSONDecodeError, TypeError):
        raise ValueError("Missing or malformed claim-check receipt") from None


def revision_items(context: dict, items: list[dict]) -> None:
    """Copy feedback cannot change a sibling hook or either product selection."""
    request = context.get("copy_revision")
    if request is None:
        return
    original = {c["arm"]: c for c in request["base_variants"]}
    for item in items:
        base = original[item["arm"]]
        suffix = product_suffix(context["product_facts"], base["fact_id"])
        if not base["opening"].endswith(suffix):
            raise ValueError("Original product wording differs from the frozen pack")
        previous = {"headline": base["headline"], "opening": base["opening"][:-len(suffix)],
                    "hypothesis": base["hypothesis"], "fact_id": base["fact_id"], "arm": base["arm"]}
        if item["fact_id"] != previous["fact_id"]:
            raise ValueError("A copy revision must preserve selected product wording")
        if item["arm"] != request["arm"] and item != previous:
            raise ValueError("A copy revision must preserve the other variant")
        if item["arm"] == request["arm"] and (item["headline"], item["opening"]) == (previous["headline"], previous["opening"]):
            raise ValueError("The requested hook was not revised")
