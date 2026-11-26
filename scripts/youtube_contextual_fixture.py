"""Native authored campaign producer shared by offline evaluation and tests."""
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from acquisition.bootstrap import build, build_youtube, build_youtube_recommendations
from acquisition.adapters.youtube_fixture import LocalYouTubeAuthority


@contextmanager
def native_campaign(content, organization='benchmark'):
    with TemporaryDirectory() as directory:
        path = Path(directory) / 'application.sqlite'
        native = build(path, clock=lambda: 1795687200.)
        conversation = native.conversations.create(organization, 'contextual-chat', 'Contextual benchmark')['id']
        authority = LocalYouTubeAuthority(organization)
        app = build_youtube(path, clock=lambda: 1795687200., organization=organization, authority=authority)
        app.message({'request_id': 'contextual-brief', 'conversation_id': conversation,
                     'expected_revision': 0, 'content': content, 'draft_permission': 'placements'})
        campaign = app.campaigns.interactions(conversation)[-1]['campaign_id']
        yield app, campaign, authority, build_youtube_recommendations(app.campaigns)
