"""Versioned literal budget clarification, separate from model interpretation."""
import re

from .domain import KNOWLEDGE, explicit_budget


BUDGET_POLICY = 'absolute-gbp/v1'


def budget_clarification(frozen):
    policy = frozen.get('budget_policy')
    if 'budget_policy' not in frozen:
        return None  # Preserve admitted historical planning behavior and IDs.
    if policy != BUDGET_POLICY:
        raise ValueError('Unknown frozen budget policy')
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
    if (frozen.get('budget_policy') == BUDGET_POLICY and candidate['outcome'] == 'clarification'
            and candidate['budget_pence'] is None and explicit_budget(frozen['messages']) is None
            and re.search(r'\bbudget\b', candidate['question'], re.I)):
        return {'schema': 'budget-clarification/v1', 'reason': 'missing',
                'message_id': frozen['messages'][-1]['id'], 'question': candidate['question']}
    return None
