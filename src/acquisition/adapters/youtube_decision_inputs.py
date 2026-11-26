"""Explicit bundled candidate/price assumptions and scripted ranking responses."""
import hashlib
import json
from pathlib import Path

from acquisition.contracts import digest
from acquisition.youtube import YouTubeError


class BundledDecisionInputs:
    def __init__(self, root):
        self.root = Path(root)

    def load(self, scope):
        directory = self.root / 'examples/youtube-ad-samples'
        checksums = json.loads((directory / 'checksums.json').read_text())
        copy = json.loads((directory / 'copy.json').read_text())
        rows = []
        for ad in copy['ads']:
            if ad['context'] not in {'editing', 'audiobook'}:
                raise YouTubeError('unsupported_creative_context', 'This sample context is not installed.')
            relative = 'examples/youtube-ad-samples/' + ad['id'] + '.mp4'
            path = (self.root / relative).resolve()
            if not path.is_relative_to(directory.resolve()):
                raise YouTubeError('asset_unavailable', 'The sample asset path escaped its catalogue.')
            try:
                if path.stat().st_size > 2_000_000:
                    raise YouTubeError('asset_unavailable', 'The bundled ad exceeds the offline size limit.')
                data = path.read_bytes()
            except OSError:
                raise YouTubeError('asset_unavailable', 'The bundled ad is unavailable.') from None
            expected = checksums[relative]
            if len(data) != expected['bytes'] or hashlib.sha256(data).hexdigest() != expected['sha256']:
                raise YouTubeError('asset_unavailable', 'The bundled ad no longer matches its reviewed source.')
            rows.append({'id': ad['id'], 'version': ad['id'] + '-' + digest(ad)[:16],
                         'context_id': 'video-editing' if ad['context'] == 'editing' else 'audiobook',
                         'asset_path': relative, 'asset_digest': expected['sha256'], 'available': True,
                         'text': ad['headline'] + ' ' + ad['script'],
                         'source': 'authored_synthetic',
                         'cost_per_batch_pence': 50 if ad['id'].endswith('-a') else 100})
        manifest = {'organization': scope.organization, 'profile_id': scope.profile_id,
                    'creatives': rows, 'cost_provenance': 'authored_simulation_not_provider_quote'}
        manifest['id'] = 'candidate_snapshot_' + digest(manifest)
        return {'manifest': manifest, 'contract': json.loads(
            (self.root / 'config/youtube-decision-contract-v1.json').read_text())}


class AuthoredRankingReceipts:
    """Exercises the model-response contract. This is not a measured LLM."""
    def rank(self, frozen):
        return {'schema': 'youtube-contextual-ranking/v1', 'input_id': frozen['id'],
                'ranker': 'authored-ranking-fixture/v1', 'model': 'scripted-no-llm',
                'prompt_version': 'contextual-rank/v1', 'provenance': 'authored_model_fixture',
                'scores': [{'cell_id': cell['id'],
                            'fit': 90 if cell['context_id'] == cell['creative_context'] else 0,
                            'reason': 'Authored context-matching response for interface conformance only.'}
                           for cell in frozen['candidates']]}
