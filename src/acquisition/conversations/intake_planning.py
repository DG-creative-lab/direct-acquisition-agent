"""Intake interpretation contracts. A plan cannot authorize campaign preparation."""

from acquisition.contracts import canonical, digest
from acquisition.campaigns import preparation_readiness as intake_readiness
from .domain import text


INTAKE_SOURCE_SCHEMA = 'intake-planning-source/v1'
INTAKE_PLAN_SCHEMA = 'intake-plan/v1'
INTAKE_KNOWLEDGE = {
    'version': 'intake-planning/v1', 'authority': 'none',
    'purpose': 'Interpret the selected user company and campaign requirements as a planning proposal only.',
    'procedures': [
        'Company descriptions, claims, qualifications, references and CTA wording are user-supplied and unverified.',
        'Preserve the exact selected requirements. Do not substitute an installed product or invent missing facts.',
        'Propose an approach, ask material questions or explain unsupported requirements.',
        'No reviewed v3 product pack is established by intake. Grounded generation requires a separate reviewed pack.',
        'A proposal cannot create a campaign, select contacts, approve, export or send anything.',
    ],
}


def validate_intake_result(candidate, source, *, deterministic=False):
    fields = {'outcome', 'summary', 'approach', 'questions', 'limitations'}
    if type(candidate) is not dict or set(candidate) != fields:
        raise ValueError('Use the exact intake planning result fields')
    if candidate['outcome'] not in {'proposal', 'clarification', 'unsupported'}:
        raise ValueError('Use a supported intake planning outcome')
    text(candidate['summary'], 1200)
    for name, limit, length in (('approach', 8, 600), ('questions', 8, 600), ('limitations', 8, 600)):
        values = candidate[name]
        if type(values) is not list or len(values) > limit:
            raise ValueError('Use bounded planning result lists')
        for value in values:
            text(value, length)
    if any(chr(0x2014) in value for value in [candidate['summary'], *candidate['approach'],
                                                           *candidate['questions'], *candidate['limitations']]):
        raise ValueError('Generated interpretation must follow current editorial guidance')
    readiness = intake_readiness(source)
    if candidate['outcome'] == 'proposal' and (readiness['missing'] or readiness['unsupported']):
        raise ValueError('A planning proposal cannot replace missing or unsupported requirements')
    if candidate['outcome'] == 'proposal' and not candidate['approach']:
        raise ValueError('A proposal requires a bounded approach')
    if candidate['outcome'] == 'clarification' and not candidate['questions']:
        raise ValueError('Clarification requires a material question')
    result = candidate | {
        'schema': INTAKE_PLAN_SCHEMA,
        'source': {key: source[key] for key in ('id', 'fingerprint', 'brief_id', 'brief_revision',
                                               'company_id', 'company_revision')},
        'requirements': source['brief']['draft'], 'readiness': readiness,
        'provenance': 'deterministic_readiness' if deterministic else 'model_proposal',
        'authority': 'none', 'execution': 'unavailable', 'product_facts': 'user_supplied_unverified'}
    return result | {'id': 'intake_plan_' + digest(result)}


def intake_readiness_result(source):
    readiness = intake_readiness(source)
    if readiness['unsupported']:
        candidate = {'outcome': 'unsupported', 'summary': 'The saved requirements include unsupported campaign capabilities.',
                     'approach': [], 'questions': readiness['missing'], 'limitations': readiness['unsupported']}
    elif readiness['missing']:
        candidate = {'outcome': 'clarification', 'summary': 'Complete the saved brief before requesting its campaign interpretation.',
                     'approach': [], 'questions': readiness['missing'], 'limitations': []}
    else:
        return None
    return validate_intake_result(candidate, source, deterministic=True)


def intake_source_message(source):
    return canonical({'schema': INTAKE_SOURCE_SCHEMA, 'source_id': source['id'],
                      'fingerprint': source['fingerprint'], 'brief_id': source['brief_id'],
                      'brief_revision': source['brief_revision']})


def bind_intake_source(frozen, organization=None):
    source = frozen.get('intake_source')
    if (type(source) is not dict or source.get('schema') != INTAKE_SOURCE_SCHEMA
            or digest({k:v for k,v in source.items() if k != 'fingerprint'}) != source.get('fingerprint')
            or (organization is not None and source['organization'] != organization)
            or source['model_config'] != frozen.get('model_config')
            or source['conversation_id'] != frozen.get('conversation_id', source['conversation_id'])
            or source['revision'] != frozen.get('revision', source['revision'])):
        raise ValueError('Intake planning requires its exact frozen source, scope and model settings')
    if (source['brief']['organization'] != source['organization'] or source['company']['organization'] != source['organization']
            or (source['brief']['id'], source['brief']['revision']) != (source['brief_id'], source['brief_revision'])
            or (source['company']['id'], source['company']['revision']) != (source['company_id'], source['company_revision'])
            or (source['brief']['draft']['company_id'], source['brief']['draft']['company_revision']) !=
               (source['company_id'], source['company_revision'])):
        raise ValueError('Intake planning source relationships differ')
    selected = [message for message in frozen['messages'] if message['revision'] == source['revision']]
    if len(selected) != 1 or selected[0]['id'] != source['request_id'] or selected[0]['content'] != intake_source_message(source):
        raise ValueError('Intake planning message differs from the selected source')
    return source
