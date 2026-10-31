"""Versioned reasoning assets. Descriptions never grant execution authority."""
import json

from acquisition.contracts import canonical, digest

KINDS = {'authored_guidance', 'product_evidence', 'reviewer_preference', 'synthetic_observation', 'audience_summary'}
USES = {
    'authored_guidance': {'guide_reasoning'},
    'product_evidence': {'ground_product_copy'},
    'reviewer_preference': {'guide_style'},
    'synthetic_observation': {'inform_hypothesis'},
    'audience_summary': {'describe_synthetic_population'},
}


def source_manifest(organization, key, kind, payload, version, provenance, freshness):
    """Bind a manifest to exact scoped bytes, keeping source roles distinct."""
    if kind not in KINDS or not all(type(v) is str and v for v in (organization, key, version, provenance)):
        raise ValueError('Invalid knowledge source identity or kind')
    source = {'key': key, 'kind': kind, 'organization': organization, 'version': version,
              'owner': {'authored_guidance':'project-maintainer', 'product_evidence':'official-source-with-local-review',
                        'reviewer_preference':'local-reviewer', 'synthetic_observation':'local-synthetic-learning',
                        'audience_summary':'local-synthetic-source'}[kind],
              'status': 'advisory' if kind != 'product_evidence' else 'recorded_evidence_not_approval',
              'content_hash': digest(payload), 'provenance': provenance, 'freshness': freshness,
              'permitted_uses': sorted(USES[kind])}
    return source | {'id': 'source_' + digest(source)}


def tool_contract(wire, version, effect, preconditions, outputs):
    if effect not in {'read_context', 'propose', 'screen'}:
        raise ValueError('This catalogue installs no approval or dispatch tools')
    value = {'id': wire['function']['name'] + '/' + version, 'version': version,
             'wire': wire, 'effect': effect, 'scope': 'server_resolved_organization_and_task',
             'preconditions': preconditions, 'outputs': outputs,
             'authority': 'none', 'replay': 'original_scoped_task_and_completed_call',
             'limits': 'existing_frozen_model_config_and_workflow_turn_limits',
             'failure': 'validation_rejection_or_blocked_or_unknown_no_automatic_retry'}
    return value | {'hash': digest(value)}


def freeze_assets(organization, catalogue, tools, skill_ids, sources, *, model_projection=None):
    # Deep-copy at the boundary so callers cannot mutate a saved task by aliasing.
    skills = [s for s in catalogue['skills'] if s['id'] in skill_ids]
    if len(skills) != len(skill_ids) or len(set(skill_ids)) != len(skill_ids):
        raise ValueError('Unknown or duplicate selected skill')
    bundle = {'schema': 'agent-assets/v1', 'catalogue_version': catalogue['version'],
              'organization': organization, 'skills': skills, 'tools': tools, 'sources': sources,
              'authority': 'none'}
    if model_projection is not None:
        bundle["model_projection"] = model_projection
    bundle = json.loads(canonical(bundle))
    bundle['id'] = 'assets_' + digest(bundle)
    validate_assets(bundle)
    return bundle


def validate_assets(bundle, *, organization=None, installed_tools=None, payloads=None):
    if (bundle.get('schema') != 'agent-assets/v1' or bundle.get('authority') != 'none'
            or bundle.get('id') != 'assets_' + digest({k:v for k,v in bundle.items() if k != 'id'})
            or (organization is not None and bundle['organization'] != organization)):
        raise ValueError('Agent asset scope, version or integrity mismatch')
    if set(bundle) - {"model_projection"} != {"schema","catalogue_version","organization","skills","tools","sources","authority","id"}:
        raise ValueError("Unexpected agent asset fields")
    tools = bundle['tools']
    ids = [t['id'] for t in tools]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate installed tool contract')
    for t in tools:
        if (t['authority'] != 'none' or t['effect'] not in {'read_context','propose','screen'}
                or t['hash'] != digest({k:v for k,v in t.items() if k != 'hash'})):
            raise ValueError('Invalid tool contract')
    if installed_tools is not None and canonical(tools) != canonical(installed_tools):
        raise ValueError('Frozen tool contract is not supported by this executor')
    skills = bundle['skills']
    if len({s['id'] for s in skills}) != len(skills) or not skills:
        raise ValueError('Distinct selected skills required')
    for s in skills:
        if set(s) != {'id','version','purpose','applicable_intents','required_source_kinds','guidance','tool_ids','expected_outputs','validation_requirements','stop_conditions','authority'}:
            raise ValueError('Invalid authored skill fields')
        for key in ('applicable_intents','required_source_kinds','guidance','tool_ids','expected_outputs','validation_requirements','stop_conditions'):
            if (type(s[key]) is not list or not s[key]
                    or any(type(v) is not str or not v.strip() or len(v) > 1000 for v in s[key])
                    or len(s[key]) != len(set(s[key]))):
                raise ValueError('Use distinct bounded skill contract values')
        if (s['authority'] != 'none' or not s['id'].endswith('/' + s['version'])
                or not set(s['tool_ids']) <= set(ids) or not s['tool_ids']
                or not all(s[k] for k in ('purpose','applicable_intents','guidance','expected_outputs','validation_requirements','stop_conditions'))):
            raise ValueError('Skill references unavailable tools or lacks its contract')
        if not set(s['required_source_kinds']) <= {m['kind'] for m in bundle['sources']}:
            raise ValueError('Skill lacks required source kinds')
    keys = [m['key'] for m in bundle['sources']]
    if len(set(keys)) != len(keys):
        raise ValueError('Duplicate knowledge source')
    for m in bundle['sources']:
        if (m['organization'] != bundle['organization'] or m['kind'] not in KINDS
                or set(m['permitted_uses']) != USES[m['kind']]
                or m['id'] != 'source_' + digest({k:v for k,v in m.items() if k != 'id'})):
            raise ValueError('Knowledge source role, scope or integrity mismatch')
        if payloads is not None and (m['key'] not in payloads or m['content_hash'] != digest(payloads[m['key']])):
            raise ValueError('Knowledge manifest does not match supplied content')
    if payloads is not None and set(keys) != set(payloads):
        raise ValueError('Knowledge manifest coverage mismatch')
