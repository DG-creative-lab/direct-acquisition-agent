"""Conversation inputs and non-authoritative campaign brief proposals."""

import re

from acquisition.contracts import digest


CAPABILITY = "conversations.plan.v1"
KNOWLEDGE = {
    "version": "campaign-planning/v1",
    "mode": "LOCAL_SYNTHETIC_PLANNING_ONLY",
    "product": "iwoca_flexi_loan",
    "channel": "direct_mail",
    "country": "UK",
    "segments": {"inventory": "Stock, inventory and supplier payment timing.",
                 "contractors": "Project expenses and client payment timing."},
    "metric": "response_rate_experiment_not_guaranteed_lift",
    "budget_limit_pence": 1000000,
    "procedures": [
        "Interpret the user's objective and cite it as a proposal, not a verified fact.",
        "Select only catalogued segments. No segmentation model or real audience feed is connected.",
        "Require an explicit GBP budget. Ask about missing or ambiguous business preferences.",
        "Use fixture copy by default and disclose that assumption. Model copy is a later explicit generation choice.",
        "A complete brief is a proposal only. Campaign execution and review are separate capabilities.",
        "Product claims must later use the fresh reviewed fact pack and grounded copy workflow.",
    ],
    "execution": "unavailable_in_this_slice",
    "approval": "never_granted_by_planning_or_conversation",
}


def identity(value: str) -> str:
    if type(value) is not str or not re.fullmatch(r"[A-Za-z0-9_:.\-]{1,120}", value):
        raise ValueError("Use a bounded conversation or request identity")
    return value


def text(value: str, maximum: int = 2000, empty: bool = False) -> str:
    if (type(value) is not str or len(value) > maximum or value != value.strip()
            or (not empty and not value) or any(ord(c) < 32 and c not in "\n\t" for c in value)):
        raise ValueError("Use bounded text without hidden control characters")
    return value


def revision_number(value: int) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("Use a nonnegative integer conversation revision")
    return value


def relative_amount(content: str, match: re.Match) -> bool:
    """Identify common amount-as-adjustment phrases, not absolute totals."""
    before, after = content[:match.start()], content[match.end():]
    return bool(
        re.search(r"\bby\s+(?:(?:another|a further|an? (?:extra|additional))\s+)?$", before, re.I)
        or re.search(r"\b(?:add|adding|subtract|subtracting|deduct|deducting|another|extra|additional|plus|minus|top up)\s+$", before, re.I)
        or re.match(r"\s+(?:more|less|extra|additional|higher|lower|increase|decrease)\b", after, re.I)
    )


def explicit_budget(messages: list[dict]) -> dict | None:
    """Resolve an unambiguous literal GBP budget without skipping later corrections."""
    for message in reversed(messages):
        content = message["content"]
        matches = list(re.finditer(r"(?:£\s*|\bGBP\s+)((?:\d{1,3}(?:,\d{3})+|\d{1,7})(?:\.\d{1,2})?)(?!\w|[.,]\d)", content, re.I))
        currency = list(re.finditer(r"£|[$€]|\b(?:GBP|USD|EUR)(?=\b|\d)", content, re.I))
        # An unrecognized or foreign-currency amount is a material reference,
        # even when the valid-GBP parser cannot interpret it.
        if any(not any(marker.start() == match.start() for match in matches) for marker in currency):
            return None
        if any(relative_amount(content, match) for match in matches):
            return None
        if re.search(r"\b(?:not|except|excluding|rather than|instead of|less than|more than|under|over|at least|up to)\s+(?:£|GBP\b)", content, re.I):
            return None
        if matches and (re.search(r"\b(?:or|to|and|mean|actually)\s+\d", content, re.I)
                        or re.search(r"(?<=\d)\s*[-–]\s*(?:£\s*|GBP\s+)?\d", content, re.I)):
            return None
        if not matches:
            if re.search(r"\b(?:budget|budgets|spend|spending|pounds?|pence|halve|halved|half|double|doubled|increase|decrease|reduce|reduced)\b", content, re.I):
                return None
            if re.search(r"\b(?:change|set|make|use|raise|lower|actually|instead)\b[^\n]*\b\d[\d,.]*(?:\s*[km]\b|(?=\s*(?:instead|rather|please)?\s*[.!?]*$))", content, re.I):
                return None
            continue
        amounts = set()
        for match in matches:
            pounds, _, pennies = match.group(1).replace(",", "").partition(".")
            amounts.add(int(pounds) * 100 + int(pennies.ljust(2, "0") or "0"))
        if len(amounts) != 1:
            return None
        return {"budget_pence": amounts.pop(), "message_id": message["id"], "quote": matches[0].group(0)}
    return None


def validate_result(candidate: dict, frozen: dict, organization: str) -> dict:
    fields = {"outcome", "objective", "budget_pence", "segments", "copy_mode", "question", "assumptions", "unsupported_reason"}
    if type(candidate) is not dict or set(candidate) != fields:
        raise ValueError("Submit the exact campaign brief fields")
    if candidate["outcome"] not in {"brief_proposal", "clarification", "unsupported"}:
        raise ValueError("Unknown planning outcome")
    for field in ("objective", "question", "unsupported_reason"):
        text(candidate[field], 600, empty=True)
    segments = candidate["segments"]
    if (type(segments) is not list or len(segments) > 2 or any(type(s) is not str or s not in KNOWLEDGE["segments"] for s in segments)
            or len(set(segments)) != len(segments)):
        raise ValueError("Select distinct supported audience segments")
    if candidate["copy_mode"] not in {"fixture", "model"}:
        raise ValueError("Choose a supported copy mode")
    assumptions = candidate["assumptions"]
    if type(assumptions) is not list or len(assumptions) > 5:
        raise ValueError("Use at most five explicit assumptions")
    for assumption in assumptions:
        text(assumption, 240)
    if any(chr(0x2014) in value for value in [candidate["objective"], candidate["question"], candidate["unsupported_reason"], *assumptions]):
        raise ValueError("Generated content must use full stops, commas or colons instead of em dashes")
    budget, evidence = candidate["budget_pence"], explicit_budget(frozen["messages"])
    if budget is not None:
        if type(budget) is not int or not 1 <= budget <= KNOWLEDGE["budget_limit_pence"]:
            raise ValueError("Use an integer budget from 1 to 1000000 pence")
        if evidence is None or budget != evidence["budget_pence"]:
            raise ValueError("Budget must match an explicit GBP amount in the latest budget message")
    if candidate["outcome"] == "brief_proposal":
        if not candidate["objective"] or budget is None or not segments or candidate["question"] or candidate["unsupported_reason"]:
            raise ValueError("A brief proposal needs an objective, explicit budget and segments, without unanswered questions")
    elif candidate["outcome"] == "clarification":
        if not candidate["question"] or candidate["unsupported_reason"]:
            raise ValueError("Clarification needs one question and no unsupported reason")
    elif not candidate["unsupported_reason"] or candidate["question"]:
        raise ValueError("An unsupported request needs an explanation")
    result = {**candidate, "segments": sorted(segments), "budget_evidence": evidence if budget is not None else None,
              "conversation_id": frozen["conversation_id"], "revision": frozen["revision"],
              "knowledge_id": frozen["knowledge_id"], "mode": "SYNTHETIC_PLANNING_ONLY",
              "approval": "not_granted", "execution": "not_performed"}
    return result | {"id": "brief_" + digest({"organization": organization, "request_id": frozen["request_id"], "result": result})}
