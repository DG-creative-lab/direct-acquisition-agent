"""Explicit authored fixture and local operator authority. No provider client."""
import hashlib
from pathlib import Path

from acquisition.youtube import YouTubeError, PROFILE


FIXTURE = {
    'schema': 'youtube-authored-context/v1', 'profile_id': PROFILE,
    'product': 'Voice comparison demonstration',
    'provenance': 'authored_synthetic',
    'disclosure': 'Authored examples and synthetic voices. No real product performance claims.',
    'contexts': {
        'video-editing': {
            'title': 'Video editing', 'terms': ['editing', 'editor', 'tutorial', 'explainer'],
            'creative_version': 'editing-voiceover-v1', 'comparison_version': 'editing-comparison-v1',
            'instruction': 'Watch the same clip twice. Which read fits the moment the light comes on?',
            'passage': 'One small light can change how you see the whole room.',
            'takes': [['a', 'Quick and direct', 'editing-a.mp4'], ['b', 'Measured and deliberate', 'editing-b.mp4']],
            'preview': 'editing-a.mp4',
        },
        'audiobook': {
            'title': 'Audiobook narration', 'terms': ['audiobook', 'narration', 'story', 'reading'],
            'creative_version': 'audiobook-reading-v1', 'comparison_version': 'audiobook-comparison-v1',
            'instruction': 'Listen to both readings. Which delivery fits the moment in the story?',
            'passage': 'Mara stopped at the door. On the other side, someone was humming the song she had forgotten.',
            'takes': [['a', 'Brisk reading', 'audiobook-a.mp3'], ['b', 'Measured reading', 'audiobook-b.mp3']],
            'preview': 'audiobook-preview.mp4',
        },
    },
    'catalogue': [
        {'id': 'SAMPLE00001', 'title': 'Editing a tutorial voiceover', 'creative': 'video-editing', 'source': 'synthetic'},
        {'id': 'SAMPLE00002', 'title': 'Choosing narration for an explainer', 'creative': 'video-editing', 'source': 'synthetic'},
        {'id': 'SAMPLE00003', 'title': 'Pacing an audiobook scene', 'creative': 'audiobook', 'source': 'synthetic'},
        {'id': 'SAMPLE00004', 'title': 'Comparing story readings', 'creative': 'audiobook', 'source': 'synthetic'},
    ],
}


class LocalYouTubeAuthority:
    """Controllable authored-test grant; production reads shared platform actors."""
    def __init__(self, organization, actor='local-operator', profile_id=PROFILE):
        self.organization, self.actor, self.profile_id = organization, actor, profile_id
        self.enabled, self.generation = True, 1

    def require(self, scope, actor, operation):
        if (not self.enabled or scope.organization != self.organization or actor != self.actor
                or scope.profile_id != self.profile_id):
            raise PermissionError('YouTube scope is unavailable to this operator')
        if operation not in {'read', 'draft', 'review', 'approve', 'export', 'revoke'}:
            raise PermissionError('YouTube operation is unavailable')
        return self.generation


class BundledComparisonAssets:
    def __init__(self, directory, origin, fixture=FIXTURE):
        self.directory, self.origin, self.fixture = Path(directory), origin.rstrip('/'), fixture
        from urllib.parse import urlsplit
        url = urlsplit(self.origin)
        if url.scheme != 'http' or url.hostname not in {'127.0.0.1', 'localhost'} or url.path or url.query or url.fragment:
            raise ValueError('This authored preview supports only an explicit local workspace origin')

    def media(self, name):
        allowed = {entry['preview'] for entry in self.fixture['contexts'].values()}
        allowed |= {take[2] for entry in self.fixture['contexts'].values() for take in entry['takes']}
        if name not in allowed:
            raise YouTubeError('media_unavailable', 'This bundled asset is unavailable')
        path = (self.directory / name).resolve()
        if not path.is_relative_to(self.directory.resolve()) or path.stat().st_size > 2_000_000:
            raise YouTubeError('media_unavailable', 'This bundled asset is unavailable')
        return path.read_bytes()

    def manifest(self, contexts):
        comparisons, blockers = {}, []
        for key in contexts:
            entry = self.fixture['contexts'][key]
            hashes = {}
            for name in {entry['preview'], *(take[2] for take in entry['takes'])}:
                try:
                    hashes[name] = hashlib.sha256(self.media(name)).hexdigest()
                except OSError:
                    hashes[name] = None
                    blockers.append('Bundled media is unavailable for ' + entry['title'] + '.')
            content = {
                'title': entry['title'], 'instruction': entry['instruction'], 'passage': entry['passage'],
                'takes': [{'id': take, 'label': label, 'asset': name, 'sha256': hashes[name],
                           'url': self.origin + '/youtube/media/' + name + '?sha256=' + (hashes[name] or '')}
                          for take, label, name in entry['takes']],
                'preview_sha256': hashes[entry['preview']],
                'preview_path': self.origin + '/youtube/media/' + entry['preview'] + '?sha256=' + (hashes[entry['preview']] or ''),
            }
            from acquisition.contracts import digest
            content['viewer_path'] = self.origin + '/youtube/compare/' + key + '?content=' + digest(content)
            comparisons[key] = content
        return {'comparisons': comparisons, 'blockers': blockers,
                'delivery': {'origin': self.origin, 'mode': 'local_bundled_preview',
                             'viewer_capability': 'bundled-comparison-preview/v1',
                             'measurement': 'not_collected', 'public_hosting': False}}
