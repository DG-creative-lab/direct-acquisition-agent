"""Versioned literal budget clarification, separate from model interpretation."""
import re

from .domain import KNOWLEDGE, explicit_budget


BUDGET_POLICY = 'absolute-gbp/v6'
SUPPORTED_BUDGET_POLICIES = frozenset({'absolute-gbp/v1', 'absolute-gbp/v2', 'absolute-gbp/v3', 'absolute-gbp/v4', 'absolute-gbp/v5', BUDGET_POLICY})


_UNITS = r'(?:seconds?|minutes?|hours?|days?|weeks?|fortnights?|months?|quarters?|years?|recipients?|audiences?|variants?|segments?|business(?:es)?|locations?|regions?|countr(?:y|ies)|channels?|customers?|contacts?|leads?|letters?|mailpieces?|mailings?|impressions?|clicks?|conversions?|units?|people|persons?)'
_MONEY = r'(?:£\s*|\bGBP\s+)(?:\d{1,3}(?:,\d{3})+|\d{1,7})(?:\.\d{1,2})?(?!\w|[.,]\d)'
_FREQUENCY = r'(?:daily|weekly|fortnightly|monthly|quarterly|annually|annual|yearly|hourly)'
_V2_RATES = (r'\b(?:per|each|every)[ -]+(?:of\s+)?(?:(?:the|both|two|three|\d+)\s+)*' + _UNITS + r'\b',
          r'\b' + _FREQUENCY + r'\s+(?:(?:campaign|marketing)\s+)?(?:budget|amount|figure|estimate|spend|cap|limit|allocation|allowance|rate)\b',
          r'\b' + _FREQUENCY + r'\s+' + _MONEY,
          _MONEY + r'\s*(?:/\s*' + _UNITS + r'|(?:a|an)\s+' + _UNITS + r'|' + _FREQUENCY + r')\b',
          r'\bunit[- ](?:cost|price|rate|budget)\s*(?:(?:of|is|was)\s*|[:=]\s*)?' + _MONEY,
          r'\b(?:half|part|portion|share)\s+of\s+(?:the\s+)?(?:(?:total|overall|campaign)\s+)?budget\b',
          r'\b(?:is|represents|covers)\s+(?:(?:only|just)\s+)?(?:(?:a|an|the)\s+)?(?:deposit|instalment|installment|down payment|unit[- ]cost|unit[- ]price)\b')
_NON_TOTAL = (r'\bnon[- ]total\b', r"\b(?:not|isn['’]t|wasn['’]t|aren['’]t)\s+(?:(?:a|an|the|my|our|actual|confirmed|absolute|final|yet|as|campaign|whole|full)\s+)*(?:total|overall|budget)\b",
              r"\b(?:do not|don['’]t|never)\s+(?:use|treat|take|consider|interpret|count)\s+(?:the\s+)?" + _MONEY)


# Quantities follow the same comma grouping convention as literal GBP amounts.
_QUANTITY = r'(?:\d{1,3}(?:,\d{3})+|\d+|one|two|three|both)'
_V4_RATES = (r'\b(?:per|each|every)[ -]+(?:of\s+)?(?:the\s+)?(?:' + _QUANTITY + r'\s+)?' + _UNITS + r'\b',
          *_V2_RATES[1:3],
          _MONEY + r'\s*(?:/\s*(?:' + _QUANTITY + r'\s+)?' + _UNITS + r'|(?:a|an)\s+' + _UNITS + r'|' + _FREQUENCY + r')\b',
          *_V2_RATES[4:])
_RECIPIENT_DETERMINER = r'(?:the|my|our|your|his|her|its|their|these|those)'
_RECIPIENT_RATE = (r'\b(?:per|each|every)[ -]+(?:' + _QUANTITY + r'\s+)?(?:of\s+)?(?:all\s+)?'
                   + r'(?:' + _RECIPIENT_DETERMINER + r'\s+)?(?:' + _QUANTITY + r'\s+)?' + _UNITS + r'\b')
_RATES = (_RECIPIENT_RATE, *_V4_RATES[1:])
_FINANCIAL_NOUN = r'(?:budget|amount|figure|spend|(?:budget|spending|campaign)\s+(?:cap|limit|allocation|allowance))'
# Retain the admitted v3 grammar while fresh admissions preserve financial links.
_V3_LINK = r'\s*(?:(?:is|was|would be|represents|covers|as|of)\s+)?(?:(?:only|just|a|an|the|total|whole|full|campaign|budget|amount)\s+)*'

_LINK = r'\s*(?:(?:is|was|would be|represents|covers|as|of)\s+)?(?:(?:only|just|a|an|the|total|whole|full|campaign|budget|amount|cost|price|rate)\s+)*(?:(?:for|of)\s+)?'


def _bound_budget_qualifier(content, match, link):
    """A rate must describe money or a financial subject, not delivery cadence."""
    if re.search(_MONEY, match.group(), re.I):
        return True
    prefix, suffix = content[:match.start()], content[match.end():]
    if re.search(r'(?:' + _MONEY + r'|\b' + _FINANCIAL_NOUN + r')' + link + r'$', prefix, re.I):
        return True
    if re.search(_MONEY + link + r'[.!?;]\s*(?:that|this|it)' + link + r'$', prefix, re.I):
        return True
    if re.match(r'\s*(?:(?:rate|cost|price|budget|amount)\s+)?(?:(?:of|is|was|at)\s+)?' + _MONEY, suffix, re.I):
        return True
    # An isolated qualification can correct a preceding message's amount.
    # Restrict bare pronouns to the whole message so an unrelated object cannot
    # borrow a budget mentioned elsewhere in the same request.
    return bool(re.fullmatch(r'\s*(?:(?:that|this|it)(?:\s+' + _FINANCIAL_NOUN + r')?' + link + r')?'
                             + re.escape(match.group()) + r'(?:\s+' + _FINANCIAL_NOUN + r')?[.!?\s]*', content, re.I))


def _delivery_purpose(content, match):
    """Recognize an explicit campaign total funding recipient letter delivery."""
    if not re.match(r'(?:each|every)\b', match.group(), re.I):
        return False
    if not re.search(r'\b(?:recipients?|business(?:es)?|customers?|contacts?|leads?|people|persons?)$', match.group(), re.I):
        return False
    if not re.match(r'\s+to\s+(?:receive|get|be\s+(?:sent|mailed|posted))\s+'
                    r'(?:(?:a|an|one|two|three|\d+)\s+)?(?:letters?|mailings?|mailpieces?|postcards?)\b',
                    content[match.end():], re.I):
        return False
    total = r'(?:(?:total|overall)(?:\s+(?:campaign|budget|amount|spend))*|(?:whole|full)\s+campaign(?:\s+budget)?)'
    prefix = content[:match.start()]
    after_amount = _MONEY + r'\s+(?:(?:as|in)\s+)?(?:the\s+)?' + total + r'\s+for\s+$'
    before_amount = r'\b' + total + r'\s*(?:(?:of|is)\s+|:\s*)?' + _MONEY + r'\s+for\s+$'
    return bool(re.search(after_amount, prefix, re.I) or re.search(before_amount, prefix, re.I))


def _total_retraction(content, match):
    """Bind a later explicit budget denial to the stated monetary amount."""
    prefix = content[:match.start()]
    return bool(re.search(_MONEY, prefix, re.I) and
                re.search(r'(?:^|[.!?;\n])\s*(?:that|this|it)(?:\s+(?:amount|figure|budget))?'
                          r'\s*(?:(?:is|was)\s+)?$', prefix, re.I))


def non_total_budget_reference(messages):
    """Find a bound non-total amount without overriding a later clean total."""
    return _non_total_budget_reference(messages, _LINK, rates=_RATES, delivery=True, retractions=True)


def _non_total_budget_reference(messages, link, *, rates=_V4_RATES, delivery=False, retractions=False):
    for message in reversed(messages):
        content = message['content']
        for pattern in _NON_TOTAL:
            for match in re.finditer(pattern, content, re.I):
                if _bound_budget_qualifier(content, match, link) or (retractions and _total_retraction(content, match)):
                    return message['id']
        for pattern in rates:
            for match in re.finditer(pattern, content, re.I):
                prefix = content[:match.start()]
                negated = re.search(r"\b(?:not|never|no|rather than|instead of)\s+(?:(?:a|an|the)\s+)?$", prefix, re.I)
                if not negated and _bound_budget_qualifier(content, match, link):
                    if delivery and _delivery_purpose(content, match):
                        continue
                    return message['id']
        if explicit_budget([message]) is not None:
            return None
    return None


def _v2_non_total_budget_reference(messages):
    """Locate an explicit exclusion/rate, without overriding a later clean total.

    This enforces the existing absolute-total contract. Numeric extraction and
    historical result hashes retain their original behavior.
    """
    for message in reversed(messages):
        content = message['content']
        related = (re.search(r'[£$€]|\b(?:GBP|USD|EUR|budget|amount|figure|that|this|it)\b', content, re.I)
                   or re.fullmatch(_V2_RATES[0] + r'[.!?\s]*', content, re.I))
        if related:
            if any(re.search(pattern, content, re.I) for pattern in _NON_TOTAL):
                return message['id']
            for pattern in _V2_RATES:
                for match in re.finditer(pattern, content, re.I):
                    prefix = re.split(r'[.!?;\n]', content[:match.start()])[-1]
                    if not re.search(r"\b(?:not|never|no|rather than|instead of)\s+(?:(?:a|an|the)\s+)?$", prefix, re.I):
                        return message['id']
        if explicit_budget([message]) is not None:
            return None
    return None


def budget_clarification(frozen):
    if 'budget_policy' not in frozen:
        return None
    policy = frozen['budget_policy']
    if policy not in SUPPORTED_BUDGET_POLICIES:
        raise ValueError('Unknown frozen budget policy')
    if policy in {'absolute-gbp/v2', 'absolute-gbp/v3', 'absolute-gbp/v4', 'absolute-gbp/v5', BUDGET_POLICY}:
        resolver = _v2_non_total_budget_reference if policy == 'absolute-gbp/v2' else non_total_budget_reference
        if policy == 'absolute-gbp/v3':
            resolver = lambda messages: _non_total_budget_reference(messages, _V3_LINK)
        elif policy == 'absolute-gbp/v4':
            resolver = lambda messages: _non_total_budget_reference(messages, _LINK)
        elif policy == 'absolute-gbp/v5':
            resolver = lambda messages: _non_total_budget_reference(messages, _LINK, rates=_RATES, delivery=True)
        excluded = resolver(frozen['messages'])
        if excluded is not None:
            return {'schema': 'budget-clarification/v1', 'reason': 'non_total', 'message_id': excluded,
                    'question': 'Which single total campaign budget in GBP should I use? Please state one absolute amount using £ or GBP.'}
    return _v1_budget_clarification(frozen)


def _v1_budget_clarification(frozen):
    """Original resolver retained for exact validation of admitted v1 questions."""
    evidence = explicit_budget(frozen['messages'])
    if evidence is not None:
        if 1 <= evidence['budget_pence'] <= KNOWLEDGE['budget_limit_pence']:
            return None
        reason = 'out_of_range'
        message_id = evidence['message_id']
    else:
        reason, message_id = None, None
        for message in reversed(frozen['messages']):
            content = message['content']
            if re.search(r'[£$€]|\b(?:GBP|USD|EUR|budget|budgets|spend|spending|pounds?|pence|halve|halved|half|double|doubled|increase|decrease|reduce|reduced)\b|\b(?:change|set|make|use|raise|lower|actually|instead)\b[^\n]*\d', content, re.I):
                # Missing input already has the ordinary planner clarification
                # contract. Do not relabel unrelated planner failures as success.
                if not re.search(r'\d|[£$€]|\b(?:halve|halved|half|double|doubled|increase|decrease|reduce|reduced)\b', content, re.I):
                    return None
                reason = 'relative' if re.search(r'\b(?:by|add|subtract|deduct|halve|halved|half|double|doubled|reduce|reduced|extra|more|less|plus|minus|top up)\b', content, re.I) else 'unconfirmed_total'
                message_id = message['id']
                break
        if reason is None:
            return None
    question = ('What is the new total campaign budget in GBP? ' if reason == 'relative' else
                'Which single total campaign budget in GBP should I use? ')
    question += 'Please state one absolute amount using £ or GBP.'
    if reason == 'out_of_range':
        question += ' The supported total is £0.01 to £10,000.'
    return {'schema': 'budget-clarification/v1', 'reason': reason, 'message_id': message_id, 'question': question}


def budget_response(frozen):
    clarification = budget_clarification(frozen)
    if clarification is None:
        return None
    return {'outcome': 'clarification', 'objective': '', 'budget_pence': None, 'segments': [], 'copy_mode': 'fixture',
            'question': clarification['question'], 'assumptions': [], 'unsupported_reason': ''}


def result_budget_clarification(candidate, frozen):
    clarification = budget_clarification(frozen)
    if clarification is not None:
        return clarification
    if (frozen.get('budget_policy') in SUPPORTED_BUDGET_POLICIES and candidate['outcome'] == 'clarification'
            and candidate['budget_pence'] is None and explicit_budget(frozen['messages']) is None
            and re.search(r'\bbudget\b', candidate['question'], re.I)):
        return {'schema': 'budget-clarification/v1', 'reason': 'missing',
                'message_id': frozen['messages'][-1]['id'], 'question': candidate['question']}
    return None
