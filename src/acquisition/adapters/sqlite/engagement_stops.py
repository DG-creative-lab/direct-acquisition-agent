"""Resolve stop constraints through scoped native history, without retargeting saved work."""

from acquisition.audiences import related_identities
from acquisition.contracts import Conflict
from acquisition.engagements import applicable_stop


def native_stop_subjects(db, contacts, organization, scope, subject_id):
    if scope=='simulation':return {subject_id}
    if scope not in {'contact','account'}:raise Conflict('Unsupported native stop scope')
    return related_identities(subject_id,contacts._history(db,organization))


def native_engagement_stop(db, contacts, organization, simulation_id, contact_id, account_id):
    stops=[dict(r) for r in db.execute('SELECT * FROM engagement_stops WHERE organization=? AND (simulation_id IS NULL OR simulation_id=?)',
                                      (organization,simulation_id))]
    history=contacts._history(db,organization)
    return applicable_stop(stops,simulation_id,contact_id,account_id,
        contact_identities=related_identities(contact_id,history),
        account_identities=related_identities(account_id,history))
