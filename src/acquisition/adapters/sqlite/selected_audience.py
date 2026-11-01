"""Recheck selected source identity inside inference, draft and review transactions."""
import json
from dataclasses import replace
from datetime import datetime, timezone

from acquisition.audiences import Business, Snapshot, DatasetVersion, validate_dataset
from acquisition.contracts import Conflict, canonical, digest


def require_selected_audience(db, organization, brief, snapshot_id, now):
    if 'conversation_id' not in brief:
        return
    bound=brief.get('audience_source')
    # Later selections cannot retroactively change an admitted campaign's mode.
    # Conversely, stripping provenance cannot turn a sourced admission into an
    # unsourced one. The original run is scoped by its campaign request identity.
    admission=db.execute('''SELECT t.inputs FROM runs r JOIN tasks t ON t.run_id=r.id
        WHERE r.organization=? AND r.request_id=? ORDER BY t.position LIMIT 1''',
        (organization,brief['campaign_id'])).fetchone()
    if admission:
        admitted=json.loads(admission[0]).get('brief', {})
        if canonical(admitted.get('audience_source')) != canonical(bound):
            raise Conflict('Campaign audience mode differs from its original admission')
        if bound is None:
            return
    row=db.execute('SELECT payload FROM conversation_audiences WHERE organization=? AND conversation_id=? AND revision=?',
                   ('local-conversations',brief['conversation_id'],brief['conversation_revision'])).fetchone()
    if row is None and bound is None:
        return  # Original unselected conversation workflows retain their contract.
    selection=json.loads(row[0]) if row else None
    if (not selection or canonical(selection) != canonical(bound)
            or selection['plan_id'] != brief['plan_id']
            or selection['id'] != 'selection_' + digest({k:v for k,v in selection.items() if k != 'id'})):
        raise Conflict('Campaign differs from its confirmed audience provenance')
    def snapshot(scope, identity):
        raw=db.execute('SELECT payload FROM audiences WHERE organization=? AND id=?',(scope,identity)).fetchone()
        if raw is None:
            raise Conflict('Confirmed audience snapshot is unavailable')
        value=json.loads(raw[0]);value['records']=tuple(Business(**r) for r in value['records'])
        result=Snapshot(**value)
        if result.organization != scope or result.id != identity:
            raise Conflict('Confirmed audience snapshot failed integrity checks')
        return result
    original=snapshot('local-conversations',selection['source_snapshot_id'])
    actual=snapshot(organization,snapshot_id)
    source=DatasetVersion(**(selection['source'] | {'segments':tuple(selection['source']['segments'])}))
    if source.id != selection['manifest_id'] or set(source.segments) != set(brief['segments']):
        raise Conflict('Confirmed audience manifest changed')
    validate_dataset(source,original,'local-conversations',datetime.fromtimestamp(now,timezone.utc).date())
    # Review refresh may only add suppression flags. It cannot change population,
    # scores, dates or source metadata, or restore a source-suppressed recipient.
    if len(original.records) != len(actual.records):
        raise Conflict('Campaign population differs from its confirmed source')
    expected=replace(original,organization=organization,records=tuple(
        replace(o,suppressed=a.suppressed) if not o.suppressed else o for o,a in zip(original.records,actual.records)))
    if expected != actual:
        raise Conflict('Campaign population differs from its confirmed source')

    return source
