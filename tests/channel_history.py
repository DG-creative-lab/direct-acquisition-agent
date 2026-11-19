"""Write pre-cutover SQLite channel history for compatibility tests."""

from unittest.mock import patch

from acquisition.adapters.sqlite.execution import bind_run
from acquisition.adapters.sqlite.tasks import insert_run
from acquisition.creative import CHANNEL_CONTENT_CAPABILITY
from acquisition.runtime import TaskSpec


def start_legacy_channel(app, organization, request_id, profile, recipients, channel):
    def write(db, organization, request_id, command, context, context_id, lineage, inputs):
        task = {'workflow_version': 'channel-content/v1', 'context_id': context_id,
                'model_config': context['model_config']}
        if 'journey' in context:
            task['journey'] = context['journey']
        run = insert_run(db, organization, 'channel:' + request_id,
                         [TaskSpec(CHANNEL_CONTENT_CAPABILITY, task, max_attempts=3)], app.store._now())
        bind_run(db, organization, run, new_run=True)
        db.execute('INSERT INTO channel_preparations VALUES(?,?,?,?,?)',
                   (organization, request_id, inputs, run, context_id))
        return run

    with patch.object(app.store, '_admit_owned', side_effect=write):
        return app.start(organization, request_id, profile, recipients, channel)
