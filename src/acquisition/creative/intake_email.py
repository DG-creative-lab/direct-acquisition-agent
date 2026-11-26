"""Offline email material using the installed grounded channel renderer."""
from acquisition.contracts import digest
from .channel_content import FRAMES, synthetic_channel_policy, validate_channel_policy, validate_rendered_channel
from .grounding_policy import validate_fact_pack


def render_intake_email(organization, profile, pack, campaign_profile_id, snapshot, selected, binding_id, today):
    validate_fact_pack(pack, today, profile=profile)
    policy = synthetic_channel_policy(profile.key, profile)
    policy['cta_url'] = selected['cta']['url']
    validate_channel_policy(policy, profile)
    recipients = [{'request_id':p.ref.id, 'context_id':'email_recipient_'+digest({'source':snapshot.id,'contact':p.ref.id}),
        'target_id':p.ref.id, 'profile_id':campaign_profile_id, 'contact_id':p.ref.id, 'channel':'email',
        'segment':'businesses', 'email':p.email, 'phone':None, 'facts':[], 'context_status':'synthetic_no_personalization'}
        for p in snapshot.contacts]
    context = {'schema':'intake-email-context/v1', 'organization':organization, 'binding_id':binding_id,
        'command':{'channel':'email','parent_id':None}, 'product_facts':pack,
        'recipients':recipients, 'channel_policy':policy, 'guidance':{'frames':FRAMES}}
    context_id='intake_email_context_'+digest(context)
    proposals=[{'recipient_context_id':r['context_id'], 'frame_key':'explore',
        'product_fact_id':pack['facts'][i % len(pack['facts'])]['id'], 'recipient_fact_ids':[]}
        for i,r in enumerate(recipients)]
    # Validate and render all intended recipients, never a sample or model HTML.
    from .channel_content import render_channel_rows
    rendered=render_channel_rows(context,context_id,proposals)
    validate_rendered_channel(context,context_id,proposals,rendered)
    return {'context':context, 'context_id':context_id, 'proposals':proposals, 'rows':rendered,
            'semantic_screen':'not_evaluated','model_calls':0,'approval':'not_granted'}
