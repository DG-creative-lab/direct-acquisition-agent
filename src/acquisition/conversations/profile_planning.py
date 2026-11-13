"""Explicit profile-bound preparation contract, separate from historical chat plans."""

from dataclasses import asdict
from datetime import date

from acquisition.campaigns import CampaignProfile
from acquisition.contracts import canonical, digest


def profile_plan(organization, request_id, profile: CampaignProfile, *, objective, budget_pence,
                 segments, country, currency, channel, snapshot_id, command):
    if (type(organization) is not str or not organization or type(request_id) is not str
            or not request_id or type(profile) is not CampaignProfile):
        raise ValueError('A scoped request and installed profile are required')
    if (type(objective) is not str or not 1 <= len(objective.strip()) <= 600
            or any(ord(c) < 32 for c in objective) or chr(0x2014) in objective):
        raise ValueError('Use a bounded explicit campaign objective')
    if type(budget_pence) is not int or not 1 <= budget_pence <= 1_000_000:
        raise ValueError('Supply an explicit integer GBP budget')
    if (country, currency, channel) != (profile.country, profile.currency, profile.channel):
        raise ValueError('Requested market, currency or channel is unsupported by this profile')
    if (type(segments) is not tuple or not segments or len(set(segments)) != len(segments)
            or set(segments) - {s.key for s in profile.taxonomy.segments}):
        raise ValueError('Select distinct segments from the installed profile taxonomy')
    if (type(command) is not dict or type(command.get('size')) is not int
            or not 1 <= command['size'] <= 400_000 or type(command.get('seed')) is not int):
        raise ValueError('Freeze bounded synthetic size and integer seed in the request')
    as_of = command.get('as_of')
    if as_of is not None and (type(as_of) is not str or date.fromisoformat(as_of).isoformat() != as_of):
        raise ValueError('Freeze an explicit ISO audience date or use the publication date')
    expected_command = {'schema': 'profile-preparation/v1', 'organization': organization,
        'key': profile.key, 'version': profile.version, 'objective': objective, 'budget_pence': budget_pence,
        'segments': list(segments), 'country': country, 'currency': currency, 'channel': channel,
        'size': command['size'], 'seed': command['seed'], 'as_of': as_of}
    if canonical(command) != canonical(expected_command):
        raise ValueError('Profile plan differs from its exact frozen request')
    import json
    payload = {'schema': 'profile-plan/v1', 'organization': organization, 'request_id': request_id,
        'profile': json.loads(canonical(asdict(profile))), 'profile_id': profile.id, 'objective': objective,
        'objective_kind': profile.objective, 'snapshot_id': snapshot_id,
        'command': command,
        'budget_pence': budget_pence, 'segments': list(segments), 'country': country,
        'currency': currency, 'channel': channel, 'copy_mode': 'fixture',
        'mode': 'SYNTHETIC_PLANNING_ONLY', 'approval': 'not_granted', 'execution': 'not_performed'}
    return payload | {'id': 'profile_plan_' + digest(payload)}
