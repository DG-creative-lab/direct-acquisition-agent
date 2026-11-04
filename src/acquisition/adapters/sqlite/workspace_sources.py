"""Scoped facts for environment intent. No workspace projection is consulted."""
import json
from acquisition.contracts import Conflict
from .admission_sources import conversation_source, require_owner, row_json


def environment_source(db,session,kind,read_environment):
    org=session['organization'];source={}
    if kind=='conversation':
        source=conversation_source(db,org,session['conversation_plan']['id'])
        require_owner(db,source['owner'])
    if session['parent_id']:
        parent=read_environment(db,org,session['parent_id'])
        if parent is None:raise Conflict('Verified continuation requires its authoritative parent environment')
        cohort=db.execute('SELECT payload,finalization FROM learning_cohorts WHERE organization=? AND id=?',
                          (org,parent['cohort_id'])).fetchone()
        if cohort is None or cohort['finalization'] is None:
            raise Conflict('Only finalized learning can seed another sandbox')
        source|={'parent':parent,'cohort':json.loads(cohort['payload']),'finalization':json.loads(cohort['finalization'])}
    if kind=='followup':
        source['proposal']=row_json(db,'review_commands','receipt',org,session['followup_id'],'request_id')
    return source
