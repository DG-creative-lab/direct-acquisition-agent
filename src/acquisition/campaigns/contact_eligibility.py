"""Hard preparation checks. Evidence readiness grants no review or outbound authority."""

from acquisition.audiences import ContactSnapshot, channel_purpose
from acquisition.contracts import Conflict, digest
from .domain import CampaignProfile


DEFINITIVE_EXCLUSIONS = frozenset({'contact_merged','contact_deleted','contact_retired',
    'account_merged','account_deleted','account_retired','local_business_suppression',
    'current_objection','unsupported_country','unsupported_entity_type','unsupported_segment'})


def contact_eligibility(snapshot: ContactSnapshot, profile: CampaignProfile, channel, purpose, now,
                        objections: set[str], suppressions: set[str], retired: set[str],
                        permission_conflicts: set[str], pressure_conflicts: set[str]):
    channel_purpose(channel, purpose)
    if snapshot.profile_id != profile.id:
        raise Conflict('Contact source differs from the installed company profile')
    accounts = {a.ref.id:a for a in snapshot.accounts}
    permissions = {(p.contact.id,p.channel,p.purpose):p for p in snapshot.permissions}
    pressure = {p.contact.id:p for p in snapshot.pressure}
    global_reasons = []
    if not snapshot.complete or snapshot.cursor is not None:
        global_reasons.append('incomplete_population')
    if not snapshot.observed_at <= now < snapshot.expires_at:
        global_reasons.append('source_outside_window')
    rows = []
    for contact in snapshot.contacts:
        reasons = list(global_reasons)
        account = accounts.get(contact.accounts[0].id) if len(contact.accounts) == 1 else None
        if contact.state != 'active': reasons.append('contact_' + contact.state)
        if contact.state == 'active' and contact.ref.id in retired: reasons.append('contact_retired')
        if account is None: reasons.append('unresolved_account_association')
        else:
            if account.state != 'active': reasons.append('account_' + account.state)
            if account.state == 'active' and account.ref.id in retired: reasons.append('account_retired')
            if account.country != profile.country: reasons.append('unsupported_country')
            if account.entity_type != 'LTD': reasons.append('unsupported_entity_type')
            if account.segment not in {s.key for s in profile.taxonomy.segments}: reasons.append('unsupported_segment')
            if account.business_id in suppressions: reasons.append('local_business_suppression')
        if contact.ref.id in objections: reasons.append('current_objection')
        if not DEFINITIVE_EXCLUSIONS.intersection(reasons):
            if contact.ref.id in permission_conflicts: reasons.append('permission_changed')
            if contact.ref.id in pressure_conflicts: reasons.append('pressure_changed')
            permission = permissions.get((contact.ref.id,channel,purpose))
            if permission is None or permission.status == 'unknown': reasons.append('permission_unknown')
            elif permission.status == 'denied': reasons.append('permission_denied')
            elif not permission.observed_at <= now < permission.expires_at: reasons.append('permission_outside_window')
            if channel == 'email' and contact.email is None: reasons.append('email_missing')
            if channel == 'human_call' and contact.phone is None: reasons.append('phone_missing')
            if channel == 'direct_mail': reasons.append('contact_postal_rendering_not_installed')
            counts = pressure.get(contact.ref.id)
            if (counts is None or not counts.complete or counts.contact_count is None or counts.account_count is None
                    or account is None or counts.experiment_unit != account.experiment_unit
                    or not counts.window_start <= now - 90*86400
                    or not counts.observed_at <= now < counts.expires_at):
                reasons.append('pressure_unknown')
            else:
                same_unit = [p for p in snapshot.pressure if p.experiment_unit == counts.experiment_unit]
                if (len({(p.account_count,p.window_start,p.observed_at) for p in same_unit}) != 1
                        or sum(p.contact_count or 0 for p in same_unit) > counts.account_count):
                    reasons.append('pressure_inconsistent')
                if counts.contact_count >= 2: reasons.append('contact_cap')
                if counts.account_count >= 4: reasons.append('account_cap')
        rows.append({'contact_id': contact.ref.id, 'account_id': account.ref.id if account else None,
            'business_id': account.business_id if account else None,
            'experiment_unit': account.experiment_unit if account else None,
            'eligible_for_preparation': not reasons, 'reasons': sorted(set(reasons))})
    eligible = [r['contact_id'] for r in rows if r['eligible_for_preparation']]
    unresolved = {'unresolved_account_association','permission_unknown','permission_outside_window',
                  'pressure_unknown','pressure_inconsistent','permission_changed','pressure_changed'}
    complete = not global_reasons and not any(unresolved.intersection(r['reasons']) and not DEFINITIVE_EXCLUSIONS.intersection(r['reasons']) for r in rows)
    return {'schema':'contact-readiness/v1', 'mode':'SYNTHETIC_ONLY', 'source_id':snapshot.id,
        'profile_id':profile.id, 'channel':channel, 'purpose':purpose, 'policy':'contact-preparation/v1',
        'input_count':len(rows), 'declared_contacts':snapshot.declared_contacts, 'coverage_complete':complete,
        'ready_for_proposal':complete and bool(eligible), 'eligible':eligible, 'rows':rows,
        'experiment_units':sorted({r['experiment_unit'] for r in rows if r['eligible_for_preparation']}),
        'basis':{'source_id':snapshot.id,'objections':digest(sorted(objections)), 'suppressions':digest(sorted(suppressions)),
                 'retired':digest(sorted(retired))},
        'authority':'none', 'approval':'not_granted', 'execution':'not_performed'}
