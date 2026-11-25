"""Native YouTube identities, authored preparation and exact manual review."""
from dataclasses import dataclass
import re

from acquisition.contracts import Conflict, canonical, digest


CONTRACT = 'youtube-channel/v1'
CAPABILITY = 'youtube.prepare.v1'
PROFILE = 'voice-comparison-demo-v1'
PERMISSIONS = ('none', 'placements', 'instruction_test')


class YouTubeError(Conflict):
    def __init__(self, code, message, *, message_not_saved=False):
        super().__init__(message)
        self.code, self.message_not_saved = code, message_not_saved


def identity(value):
    if type(value) is not str or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', value):
        raise ValueError('Use a bounded YouTube identity')
    return value


def revision(value, *, create=False):
    if type(value) is not int or not (0 if create else 1) <= value < 2**63:
        raise ValueError('Use an exact integer revision')
    return value


def text(value, maximum):
    if type(value) is not str or not value.strip() or len(value) > maximum:
        raise ValueError('Use nonempty bounded text')
    return value.strip()


def fields(value, required):
    if type(value) is not dict or set(value) != set(required):
        raise ValueError('Use the exact declared YouTube command fields')


@dataclass(frozen=True)
class YouTubeScope:
    organization: str
    profile_id: str = PROFILE

    def __post_init__(self):
        identity(self.organization), identity(self.profile_id)


def route_youtube(content, *, bound=False):
    """A routing hint never grants write or model authority."""
    content = text(content, 2000)
    youtube = bool(re.search(r'\byou\s*tube\b', content, re.I))
    other = bool(re.search(r'\b(?:e-?mails?|postal|direct[- ]mail|postcards?|human calls?|call scripts?|phone calls?)\b', content, re.I))
    if youtube and other:
        return 'ambiguous'
    if other:
        return 'other'
    return 'youtube' if youtube or bound else 'other'


def select_contexts(content, fixture):
    selected = []
    for key, entry in fixture['contexts'].items():
        if any(term in content.lower() for term in entry['terms']):
            selected.append(key)
    return selected or list(fixture['contexts'])


def authored_draft(frozen, fixture):
    contexts, command = frozen['contexts'], frozen['command']
    return {'title': text(command['content'], 2000)[:120], 'goal': text(command['content'], 2000)[:500],
            'contexts': contexts, 'placements': [dict(row) for row in fixture['catalogue'] if row['creative'] in contexts]}


def draft_rows(rows, contexts, fixture):
    if type(rows) is not list or len(rows) > 2400:
        raise ValueError('Save at most 2400 placements')
    known = {row['id']: row for row in fixture['catalogue']}
    seen, selected = set(), []
    for row in rows:
        fields(row, {'id', 'title', 'creative', 'source'})
        if (any(type(value) is not str for value in row.values()) or row['id'] in seen
                or row['id'] not in known or row != known[row['id']] or row['creative'] not in contexts):
            raise YouTubeError('catalogue_mismatch', 'Select unique placements from this authored catalogue')
        seen.add(row['id'])
        selected.append(dict(row))
    return selected


def package_for(campaign, asset_manifest, fixture):
    draft = campaign['draft']
    groups = []
    for key in draft['contexts']:
        entry = fixture['contexts'][key]
        content = asset_manifest['comparisons'][key]
        groups.append({
            'context': key, 'title': entry['title'], 'creative_version': entry['creative_version'],
            'comparison_version': entry['comparison_version'], 'content': content,
            'preview_asset': entry['preview'], 'preview_path': content['preview_path'],
            'viewer_path': content['viewer_path'],
            'placements': [{'demo_id': row['id'], 'title': row['title'], 'source': row['source'],
                            'label': 'Fictional placement'} for row in draft['placements'] if row['creative'] == key],
        })
    return {'campaign_id': campaign['id'], 'revision': campaign['revision'],
            'title': draft['title'], 'data_label': 'Fictional placements for an offline sample',
            'brief': {'id': campaign['context_id'], 'revision': 1, 'goal': draft['goal']},
            'policy': {'id': 'youtube-authored-policy', 'revision': 1},
            'proposed_setup': {'objective': draft['goal'], 'format': 'YouTube video ad example',
                              'budget': 'Unset for the offline sample', 'schedule': 'Unscheduled'},
            'groups': groups}


def review_for(scope, campaign, manifest, fixture, authority_generation):
    package = package_for(campaign, manifest, fixture)
    blockers = list(manifest['blockers'])
    for group in package['groups']:
        if not group['placements']:
            blockers.append('Add placements for ' + group['title'] + '.')
    payload = {'schema': 'youtube-manual-payload/v1', 'package': package,
               'context': {'id': campaign['context_id'], 'fingerprint': campaign['context_fingerprint'],
                           'profile_id': scope.profile_id, 'provenance': 'authored_synthetic'},
               'delivery': manifest['delivery'],
               'limitations': ['Manual setup only. No ad was purchased or deployed.',
                               'Placements are fictional and are not verified YouTube inventory.',
                               'Bundled synthetic voice previews collect no viewer events in this slice.']}
    subject = {'kind': 'youtube.manual_review/v1', 'campaign_id': campaign['id'],
               'revision': campaign['revision'], 'package_fingerprint': digest(package),
               'payload_sha256': digest(payload), 'delivery_fingerprint': digest(manifest['delivery'])}
    subject['subject_id'] = 'yts_' + digest({'schema': 'youtube-subject/v1', 'organization': scope.organization,
        'profile_id': scope.profile_id, 'context': campaign['context_fingerprint'],
        'authority_generation': authority_generation, 'subject': subject})
    return {'subject': subject, 'payload': payload, 'blockers': blockers}


def exact_subject(actual, expected):
    if actual != expected:
        raise YouTubeError('subject_changed', 'This package changed. Review the current revision before continuing.')


def export_bytes(payload, approval):
    return canonical({'schema': 'youtube-manual-export/v1', 'payload': payload,
                      'review_receipt': approval}).encode('utf-8')
