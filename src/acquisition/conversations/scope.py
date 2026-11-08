"""Versioned literal scope evidence, separate from model interpretation.

This bounded resolver recognizes the installed task vocabulary and explicit
scope labels. Defaults are declared capability defaults, not user quotations.
Extend recognition in a new resolver version; retain v1 for historical replay.
"""
from dataclasses import asdict
import re

from acquisition.campaigns import CampaignScope, requested_scope_values
from acquisition.contracts import digest
from .domain import validate_result as legacy_validate_result
from .budgets import result_budget_clarification, budget_response


ALIASES = {
    'product': {
        'iwoca_flexi_loan': r'iwoca(?:\s+flexi[- ]loan)?|flexi[- ]loan|business loan',
        'personal_mortgage': r'(?:personal\s+|residential\s+)*mortgage',
        'personal_loan': r'personal loan', 'credit_card': r'credit cards?', 'overdraft': r'overdraft',
    },
    'channel': {
        'direct_mail': r'direct[- ]mail|postal(?:\s+(?:direct\s+)?mail)?|postcards?',
        'email': r'e[- ]?mail', 'sms': r'sms|text messages?',
        'social_media': r'social media|facebook|instagram|linkedin|whatsapp|tiktok',
        'telephone': r'telephone|phone calls?|cold call(?:ing)?', 'video': r'video campaign',
    },
    'country': {
        'UK': r'UK|United Kingdom|Great Britain|Britain|Northern Ireland',
        'France': r'France|French', 'Germany': r'Germany|German', 'Spain': r'Spain|Spanish',
        'US': r'USA|United States|(?-i:US)', 'Canada': r'Canada|Canadian',
        'Australia': r'Australia|Australian', 'Ireland': r'(?<!Northern )(?:Republic of )?Ireland|Irish',
        'Singapore': r'Singapore', 'New Zealand': r'New Zealand',
    },
    'objective': {
        'response_experiment': r'response(?:[- ]rate)? (?:experiment|campaign|test)|(?:direct[- ]mail|postal) (?:response )?experiment',
        'credit_decision': r'(?:approv\w*|decid\w*)\s+(?:a\s+|the\s+)?(?:credit|loans?)|guarantee\w*\s+(?:a\s+|the\s+)?loans?',
        'financial_optimization': r'(?:maximi[sz]e|optimi[sz]e|increase|guarantee|measure|predict)\s+(?:(?:incremental|net|actual|total)\s+)?(?:revenue|profits?|roi|roas)',
    },
}


def _negated(content, start):
    prefix = re.split(r'[.!?;\n]', content[:start])[-1].casefold()
    # In "do not replace X with Y", X is retained and Y is excluded.
    if re.search(r"(?:do not|don't|never)\s+replace\b.*\bwith\s+(?:the\s+)?$", prefix):
        return True
    return bool(re.search(r"\b(?:no|not|never|without|avoid|exclude|don't|do not)\s+(?:(?:use|send|target|choose|promote|offer|substitute)\s+)?(?:(?:a|an|the)\s+)?$", prefix))


def requested_scope(organization, conversation_id, revision, messages):
    defaults = asdict(CampaignScope())
    facets = {key: {'value': value, 'basis': 'capability_default', 'evidence': []} for key, value in defaults.items()}
    for message in messages:
        content = message['content']
        for facet, aliases in ALIASES.items():
            affirmative, excluded = {}, {}
            for value, pattern in aliases.items():
                for match in re.finditer(r'\b(?:' + pattern + r')\b', content, re.I):
                    evidence = {'message_id': message['id'], 'revision': message['revision'],
                                'start': match.start(), 'end': match.end(), 'quote': match.group()}
                    (excluded if _negated(content, match.start()) else affirmative)[value] = evidence
            # Explicit labels cover values beyond the recognized vocabulary.
            label = {'objective': 'objective|metric', 'country': 'country|market'}.get(facet, facet)
            for match in re.finditer(r'\b(?:' + label + r')\s*[:=]\s*([^.;\n]{1,80})', content, re.I):
                raw = match.group(1).strip()
                value = next((v for v, pattern in aliases.items() if re.fullmatch(pattern, raw, re.I)), 'unknown:' + raw)
                affirmative[value] = {'message_id': message['id'], 'revision': message['revision'],
                                       'start': match.start(1), 'end': match.end(1), 'quote': match.group(1)}
            if set(affirmative) & set(excluded):
                facets[facet] = {'value': None, 'basis': 'conflicting_request',
                                 'evidence': [e | {'value': v, 'excluded': negative}
                                              for negative, group in ((False, affirmative), (True, excluded)) for v, e in sorted(group.items())]}
            elif affirmative:
                values = sorted(affirmative)
                facets[facet] = {'value': values[0] if len(values) == 1 else None,
                                 'basis': 'explicit_request' if len(values) == 1 else 'conflicting_request',
                                 'evidence': [affirmative[v] | {'value': v} for v in values]}
            elif facets[facet]['value'] in excluded:
                value = defaults[facet] if defaults[facet] not in excluded else None
                facets[facet] = {'value': value, 'basis': 'default_after_exclusion' if value else 'excluded_supported_scope',
                                 'evidence': [e | {'excluded_value': v} for v, e in sorted(excluded.items())]}
    uncertain = [k for k,v in facets.items() if v['value'] is None or v['value'].startswith('unknown:')]
    unsupported = [k for k,v in facets.items() if k not in uncertain and v['value'] != defaults[k]]
    if uncertain:
        status = 'needs_clarification'
        response = 'Which ' + ', '.join(uncertain) + ' should this campaign use? Supported scope: UK postal direct mail for iwoca Flexi-Loan response experiments.'
    elif unsupported:
        status = 'unsupported'
        details = ', '.join(k + ': ' + facets[k]['value'] for k in unsupported)
        response = 'Unsupported requested scope (' + details + '). Only UK postal direct mail for iwoca Flexi-Loan response experiments is supported. Credit decisions and guarantees are unavailable.'
    else:
        status, response = 'supported', ''
    payload = {'schema': 'requested-campaign-scope/v1', 'resolver': 'literal-scope/v1',
               'organization': organization, 'conversation_id': conversation_id, 'revision': revision,
               'messages_hash': digest(messages), 'requirements': facets, 'status': status,
               'response': response, 'authority': 'none'}
    return payload | {'id': 'request_scope_' + digest(payload)}


def bind_requested_scope(frozen, organization):
    scope = frozen.get('requested_scope')
    if scope is not None and scope != requested_scope(organization, frozen.get('conversation_id', scope['conversation_id']),
                                                     frozen.get('revision', scope['revision']), frozen['messages']):
        raise ValueError('Requested scope differs from its frozen user messages')
    return scope


def scope_response(scope):
    if scope is None or scope['status'] == 'supported':
        return None
    clarify = scope['status'] == 'needs_clarification'
    return {'outcome': 'clarification' if clarify else 'unsupported', 'objective': '', 'budget_pence': None,
            'segments': [], 'copy_mode': 'fixture', 'question': scope['response'] if clarify else '',
            'assumptions': [], 'unsupported_reason': '' if clarify else scope['response']}


def scope_projection(scope):
    return {'id': scope['id'], 'values': requested_scope_values(scope), 'status': scope['status'], 'response': scope['response']}


def validate_result(candidate, frozen, organization):
    result = legacy_validate_result(candidate, frozen, organization)
    scope = bind_requested_scope(frozen, organization)
    if scope is None and 'budget_policy' not in frozen:
        return result
    required = scope_response(scope) or budget_response(frozen)
    if required is not None and candidate != required:
        raise ValueError('Planning cannot substitute a different task or budget for the frozen request')
    if candidate['outcome'] == 'brief_proposal':
        described = requested_scope(organization, frozen['conversation_id'], frozen['revision'],
                                    [{'id': 'proposed-objective', 'revision': frozen['revision'], 'content': candidate['objective']}])
        if described['status'] != 'supported':
            raise ValueError('Proposed objective contradicts the supported requested scope')
    payload = {k:v for k,v in result.items() if k != 'id'}
    if scope is not None:
        payload['requested_scope'] = scope
    clarification = result_budget_clarification(candidate, frozen)
    if clarification is not None and scope_response(scope) is None:
        payload['budget_clarification'] = clarification
    return payload | {'id': 'brief_' + digest({'organization': organization, 'request_id': frozen['request_id'], 'result': payload})}
