"""Versioned grounded channel artifacts. Finite framing is interpretation, never a fact or authority."""

from dataclasses import dataclass
from html import escape
import re
from urllib.parse import urlparse

from acquisition.contracts import Conflict, canonical, digest
from acquisition.reasoning import tool_contract, validate_assets
from .application import tool
from .grounding import validate_fact_pack, fact_pack_id, bounded_text
from .profiles import product_profile_from


CAPABILITY = 'creative.channel_content.v1'
READ = tool('read_channel_context','Read the exact frozen channel context. No effect authority.',{},[])
FRAMES = {
    'explore': {'subject':'A question about your next business plan',
        'opening':'Would you like to explore an option for your next business plan?',
        'discovery':'What would you want to understand before deciding on a next step?'},
    'practical': {'subject':'Considering your next business step',
        'opening':'Is there a business plan you would like to discuss?',
        'discovery':'Which questions would be useful to cover in an initial conversation?'},
}
SUBMIT = {channel:tool(name,'Select framing and supplied facts for every exact recipient. Code renders content.',{
    'context_id':{'type':'string'},'rows':{'type':'array','minItems':1,'maxItems':6,'items':{
        'type':'object','properties':{'recipient_context_id':{'type':'string'},'frame_key':{'type':'string','enum':list(FRAMES)},
            'product_fact_id':{'type':'string'},'recipient_fact_ids':{'type':'array','maxItems':2,'uniqueItems':True,'items':{'type':'string'}}},
        'required':['recipient_context_id','frame_key','product_fact_id','recipient_fact_ids'],'additionalProperties':False}}
    },['context_id','rows']) for channel,name in (('email','submit_contextual_email'),('human_call','submit_call_guidance'))}
CHECK = tool('record_channel_screen','Screen every rendered recipient payload independently. This is not approval.',{
    'candidate_hash':{'type':'string'},'rows':{'type':'array','minItems':1,'maxItems':6,'items':{
        'type':'object','properties':{'recipient_context_id':{'type':'string'},'verdict':{'type':'string','enum':['pass','reject']},
            'reason':{'type':'string','enum':['none','unsupported_fact','misleading_familiarity','missing_qualification','unsafe_rendering','wrong_recipient']}},
        'required':['recipient_context_id','verdict','reason'],'additionalProperties':False}}
    },['candidate_hash','rows'])


def channel_tool_contracts(channel):
    return [tool_contract(wire,'v1',effect,['frozen_channel_context','exact_recipient_population'],[output])
        for wire,effect,output in ((READ,'read_context','channel_context'),(SUBMIT[channel],'propose','unapproved_channel_content'),
                                    (CHECK,'screen','advisory_recipient_verdicts'))]


@dataclass(frozen=True)
class ChannelContentRequest:
    profile_key: str
    recipient_requests: tuple[str, ...]
    channel: str
    style: str = 'explore'
    parent_id: str | None = None

    def __post_init__(self):
        if self.channel not in SUBMIT or self.style not in FRAMES: raise ValueError('Unsupported channel or reviewed framing style')
        if (type(self.recipient_requests) is not tuple or not 1<=len(self.recipient_requests)<=6
                or len(set(self.recipient_requests))!=len(self.recipient_requests)):
            raise ValueError('Declare one to six distinct intended recipient contexts')
        for value in (self.profile_key,*self.recipient_requests): bounded_text(value,200)
        if self.parent_id is not None: bounded_text(self.parent_id,200)


def channel_source_payloads(context):
    return {'guidance':context['guidance'],'product':context['product_facts'],
        'recipients':context['recipients'],'policy':context['channel_policy'],'preferences':context['preferences']}


def synthetic_channel_policy(profile_key, product):
    """Reviewed demo transport material. It is content, never sender authority."""
    domain = profile_key+'.example.invalid'
    return {'schema':'synthetic-channel-policy/v1','mode':'SYNTHETIC_ONLY','sender_name':product.brand_name+' demo',
        'sender':'demo@'+domain,'reply_to':'reply@'+domain,'cta_url':product.official_urls[0],
        'unsubscribe_base':'https://'+domain+'/unsubscribe','unsubscribe_text':'Stop future contact using this demonstration link.',
        'disclosure':product.disclosure+' SYNTHETIC ONLY. DO NOT SEND OR CALL.',
        'call_introduction':'Introduce yourself and the demonstration company. Ask whether this is a suitable time to speak.',
        'objections':['If asked about qualifications, read the exact reviewed qualification.','If not interested, thank the person and end the call.'],
        'do_not_contact':'If the person objects or asks not to be contacted, end the call and record the objection before any further outreach.'}


def validate_channel_policy(policy, product):
    required = {'schema','mode','sender_name','sender','reply_to','cta_url','unsubscribe_base','unsubscribe_text',
                'disclosure','call_introduction','objections','do_not_contact'}
    if (type(policy) is not dict or set(policy)!=required or policy['schema']!='synthetic-channel-policy/v1'
            or policy['mode']!='SYNTHETIC_ONLY' or policy['cta_url'] not in product.official_urls
            or product.disclosure not in policy['disclosure']):
        raise ValueError('Use exact reviewed product and channel policy')
    for key in required-{'objections'}: bounded_text(policy[key],1000)
    for key in ('sender','reply_to'):
        if not re.fullmatch(r'[a-zA-Z0-9_.+\-]+@[a-zA-Z0-9.\-]+\.invalid',policy[key]): raise ValueError('Use synthetic sender endpoints')
    url = urlparse(policy['unsubscribe_base'])
    if (url.scheme!='https' or not url.hostname or not url.hostname.endswith('.invalid') or url.netloc!=url.hostname
            or not url.path or url.query or url.fragment): raise ValueError('Use the exact synthetic opt-out endpoint')
    if type(policy['objections']) is not list or not 1<=len(policy['objections'])<=4: raise ValueError('Provide bounded human objection guidance')
    for wording in policy['objections']: bounded_text(wording,500)


def validate_channel_context(context, organization, today):
    if context.get('schema')!='creative-context/v5' or context.get('organization')!=organization:
        raise Conflict('Use an exact scoped v5 channel context; legacy grounding cannot substitute')
    command = ChannelContentRequest(**(context['command'] | {'recipient_requests':tuple(context['command']['recipient_requests'])}))
    profile = product_profile_from(context['product_profile'])
    validate_fact_pack(context['product_facts'],today,profile=profile)
    validate_channel_policy(context['channel_policy'],profile)
    assets = context['agent_assets']
    skill = 'contextual-email/v1' if command.channel=='email' else 'call-guidance/v1'
    if ([s['id'] for s in assets['skills']]!=[skill] or assets.get('model_projection')!='channel-context/v1'
            or {s['key']:s['kind'] for s in assets['sources']}!={'guidance':'authored_guidance','product':'product_evidence',
                'recipients':'recipient_evidence','policy':'channel_policy','preferences':'reviewer_preference'}):
        raise Conflict('Channel assets differ from the installed capability')
    validate_assets(assets,organization=organization,installed_tools=channel_tool_contracts(command.channel),payloads=channel_source_payloads(context))
    rows = context['recipients']
    if ([r['request_id'] for r in rows]!=list(command.recipient_requests)
            or len({r['context_id'] for r in rows})!=len(rows) or len({r['contact_id'] for r in rows})!=len(rows)):
        raise Conflict('Frozen channel context differs from the exact intended population')
    for row in rows:
        if row['profile_id']!=context['campaign_profile_id'] or row['channel']!=command.channel:
            raise Conflict('Recipient product/channel substitution')
    return command


def channel_recipient_wording(fact):
    roles = {'operations_manager':'operations manager','owner_director':'owner or director','procurement_manager':'procurement manager'}
    if fact.slot=='contact_role': return 'Your recorded role is ' + roles[fact.code] + '.'
    phrases = {'prior_interaction':{'requested_overview':'your request for a product overview','attended_demo':'your attendance at a product demonstration'},
        'account_activity':{'equipment_quote':'an equipment quotation request','maintenance_overview':'a maintenance overview request'},
        'business_signal':{'new_location':'a new business location announcement','maintenance_program':'a maintenance program announcement'}}
    return 'The reviewed record notes ' + phrases[fact.slot][fact.code] + ' on ' + fact.event_date + '.'


def proposal_rows(context, context_id, arguments):
    if type(arguments) is not dict or set(arguments)!={'context_id','rows'} or arguments['context_id']!=context_id:
        raise ValueError('Proposal must bind the exact frozen channel context')
    rows = arguments['rows']; expected = {r['context_id']:r for r in context['recipients']}
    if (type(rows) is not list or len(rows)!=len(expected) or any(type(r) is not dict or set(r)!=
            {'recipient_context_id','frame_key','product_fact_id','recipient_fact_ids'} for r in rows)
            or len({r['recipient_context_id'] for r in rows})!=len(rows) or {r['recipient_context_id'] for r in rows}!=set(expected)):
        raise ValueError('Validate every intended recipient, not a sampled template')
    product_ids = {f['id'] for f in context['product_facts']['facts']}
    for row in rows:
        allowed = {f['fact_id'] for f in expected[row['recipient_context_id']]['facts']}
        ids = row['recipient_fact_ids']
        if (row['frame_key'] not in context['guidance']['frames'] or row['product_fact_id'] not in product_ids or type(ids) is not list
                or len(ids)>2 or any(type(i) is not str for i in ids) or len(set(ids))!=len(ids) or not set(ids)<=allowed):
            raise ValueError('Unsupported framing, product assertion or recipient fact')
    return sorted(rows,key=lambda r:r['recipient_context_id'])


def render_channel_rows(context, context_id, proposals):
    recipients = {r['context_id']:r for r in context['recipients']}; pack = context['product_facts']; policy = context['channel_policy']
    result = []
    for proposed in proposal_rows(context,context_id,{'context_id':context_id,'rows':proposals}):
        recipient = recipients[proposed['recipient_context_id']]; frame = context['guidance']['frames'][proposed['frame_key']]
        fact = next(f for f in pack['facts'] if f['id']==proposed['product_fact_id'])
        personal = [f for f in recipient['facts'] if f['fact_id'] in proposed['recipient_fact_ids']]
        claims = [f['wording'] for f in personal] + [fact['copy'],fact['qualification'],pack['required_qualification']]
        common = {'schema':'channel-recipient/v1','mode':'SYNTHETIC_ONLY','channel':context['command']['channel'],
            'context_id':context_id,'recipient_context_id':recipient['context_id'],'target_id':recipient['target_id'],
            'contact_id':recipient['contact_id'],'product_fact_id':fact['id'],'fact_pack_id':fact_pack_id(pack),
            'recipient_facts':personal,'parent_id':context['command']['parent_id'],'approval':'not_granted',
            'outcome_support':'none','authority':'none','rendering':'grounded-channel/v1'}
        if common['channel']=='email':
            unsubscribe = policy['unsubscribe_base']+'/'+digest({'organization':context['organization'],'contact':recipient['contact_id'],'policy':policy})
            lines = ['Hello,',frame['opening'],*claims,pack['cta'],policy['disclosure'],policy['unsubscribe_text']+' '+unsubscribe]
            html = '<!doctype html><html><body>'+''.join(
                '<p><a href="'+escape(policy['cta_url'],quote=True)+'">'+escape(line)+'</a></p>' if line==pack['cta']
                else '<p>'+escape(line)+'</p>' for line in lines[:-1])
            html += '<p><a href="'+escape(unsubscribe,quote=True)+'">'+escape(policy['unsubscribe_text'])+'</a></p></body></html>'
            payload = common | {'email':{'to':recipient['email'],'from':policy['sender'],'from_name':policy['sender_name'],
                'reply_to':policy['reply_to'],'subject':frame['subject'],'text':'\n\n'.join(lines),'html':html,
                'cta_url':policy['cta_url'],'unsubscribe_url':unsubscribe}}
        else:
            payload = common | {'call':{'contact':recipient['phone'],'introduction':policy['call_introduction'],
                'relevance':claims,'discovery':[frame['discovery']],'approved_claims':[fact['copy'],fact['qualification'],pack['required_qualification']],
                'objections':policy['objections'],'next_steps':[pack['cta']],'do_not_contact':policy['do_not_contact'],
                'disclosure':policy['disclosure'],'human_only':True}}
        result.append(payload | {'id':'channel_recipient_'+digest(payload)})
    return result


def validate_rendered_channel(context, context_id, proposals, rendered):
    expected = render_channel_rows(context,context_id,proposals)
    if canonical(rendered)!=canonical(expected): raise Conflict('Rendered recipient content differs from exact grounded inputs')
    for row in rendered:
        if row['channel']=='email':
            email = row['email']
            for field in ('to','from','reply_to'):
                if not re.fullmatch(r'[a-zA-Z0-9_.+\-]+@[a-zA-Z0-9.\-]+\.invalid',email[field]):
                    raise ValueError('Channel simulation accepts only exact synthetic email endpoints')
            if any(c in email['subject'] for c in '\r\n<>') or '<script' in email['html'].lower():
                raise ValueError('Unsafe email rendering')
        elif not row['call']['contact'].startswith('DEMO ONLY DO NOT CALL:'):
            raise ValueError('Human call simulation accepts only demo contact references')
    return expected


def validate_channel_screen(arguments, rendered):
    fingerprint = digest(rendered)
    if type(arguments) is not dict or set(arguments)!={'candidate_hash','rows'} or arguments['candidate_hash']!=fingerprint:
        raise ValueError('Screen must bind the exact rendered population')
    rows = arguments['rows']; expected = {r['recipient_context_id'] for r in rendered}
    if (type(rows) is not list or len(rows)!=len(expected) or any(type(r) is not dict or set(r)!=
            {'recipient_context_id','verdict','reason'} for r in rows) or len({r['recipient_context_id'] for r in rows})!=len(rows)
            or {r['recipient_context_id'] for r in rows}!=expected):
        raise ValueError('Screen every rendered recipient payload')
    for row in rows:
        if row['verdict']!='pass' or row['reason']!='none': raise ValueError('Advisory semantic screen rejected a recipient')
    return arguments


def validate_channel_bundle(context, context_id, proposals, bundle):
    """Revalidate every byte and recipient, independently of a saved status label."""
    validate_rendered_channel(context,context_id,proposals,bundle['rendered'])
    validate_channel_screen(bundle['screen'],bundle['rendered'])
    expected = {'schema':'channel-bundle/v1','mode':'SYNTHETIC_ONLY','organization':context['organization'],
        'context_id':context_id,'rendered':bundle['rendered'],'screen':bundle['screen'],
        'screen_status':'passed_advisory_not_approval','status':'validated_unapproved','parent_id':context['command']['parent_id'],
        'approval':'not_granted','outcome_support':'none','execution':'not_performed','authority':'none'}
    if bundle != expected: raise Conflict('Channel bundle differs from its grounded content contract')
