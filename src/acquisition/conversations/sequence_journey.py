"""Conversation-owned intent and continuation. Interpretation never grants effects."""

import re
from difflib import get_close_matches

from acquisition.contracts import Conflict, digest
from acquisition.campaigns import sequence_time
from .domain import identity, revision_number, text, explicit_budget
from .ports import SequenceJourneyStore, SequenceJourneyHost, SequenceIntentInterpreter


JOURNEY_SCHEMA = 'conversation-sequence/v1'
JOURNEY_ACTIVE = frozenset({'preparing','approving','approved','simulating'})
JOURNEY_STAGES = ('contacts','audience','contexts','initial','call','followup','review')


def mentioned_profiles(content,profiles):
    words=re.findall(r'[a-z]+',content.casefold())
    compact=re.sub(r'[^a-z]','',content.casefold())
    direct=[p for p in profiles if any(re.sub(r'[^a-z]','',a.casefold()) in compact for a in p['aliases'])]
    if direct:return direct
    fuzzy={m for word in words if len(word)>=5 for m in get_close_matches(word,[p['key'] for p in profiles],n=2,cutoff=.82)}
    return [p for p in profiles if p['key'] in fuzzy]


def effective_sequence_messages(messages,catalogue):
    """A complete replacement objective supersedes earlier scope, not short clarifications."""
    for index in range(len(messages)-1,-1,-1):
        content=messages[index]['content']
        if (mentioned_profiles(content,catalogue['profiles']) and explicit_budget([messages[index]])
                and re.search(r'\b(?:prepare|create|build|plan|run|simulate|start)\b',content,re.I)
                and re.search(r'\b(?:email|e-mail|sequence|multichannel)\b',content,re.I)):
            return messages[index:]
    return messages


def sequence_literal_issue(messages,profile=None):
    body=' '.join(m['content'] for m in messages)
    if re.search(r'\b(?:sms|whatsapp|linkedin|facebook|instagram|mortgages?|Germany|France|Spain|USA|Canada|Australia|autonomous voice|live sending|real emails|real calls)\b|\b(?:country|market|currency|provider)\s*[:=]\s*(?!UK\b|GBP\b|synthetic\b)\S+',body,re.I):
        return 'Installed scope is a synthetic UK email, human call-task and follow-up sequence in GBP. This request needs an unavailable capability.'
    if re.search(r'\b(?:without|no)\s+(?:human\s+)?calls?\b|\be-?mail only\b|automatic recipient repl',body,re.I):
        return 'The installed sequence includes explicit human call tasks and no automatic recipient replies.'
    if re.search(r'\b(?:exactly|only|exclude|excluding)\b',body,re.I):
        return 'This installed strategy uses the complete eligible source and account controls. Exact counts or additional audience restrictions need another installed strategy.'
    if profile is None:return None
    for label in ('company','profile','connection','audience','strategy','country','market','currency'):
        for match in re.finditer(r'\b'+label+r'\s*[:=]\s*([^,.;\n]+)',body,re.I):
            allowed={profile['key'],*map(str.casefold,profile['aliases']),'uk','united kingdom','gbp',
                'primary','primary crm','all installed contacts','taxonomy-order',*(c['key'] for c in profile['connections'])}
            if match.group(1).strip().casefold() not in allowed:return 'The explicitly named '+label+' is not installed for this company.'
    return None


def journey_request(organization, conversation_id, revision, request_id, messages, catalogue,
                    proposal, allow_generation, now):
    for value in (organization,conversation_id,request_id): identity(value)
    revision_number(revision)
    sequence_time(now)
    if revision<1 or type(allow_generation) is not bool: raise ValueError('Bind a current message and explicit generation consent')
    if type(proposal) is not dict or set(proposal)!={'outcome','profile_key','connection_key','budget_pence','question','reason'}:
        raise ValueError('Use the installed typed sequence interpretation contract')
    if proposal['outcome'] not in {'sequence','clarification','unsupported'}: raise ValueError('Unknown interpretation outcome')
    for key in ('profile_key','connection_key','question','reason'): text(proposal[key],600,empty=True)
    if proposal['outcome']=='sequence':
        profiles=[p for p in catalogue['profiles'] if p['key']==proposal['profile_key']]
        if len(profiles)!=1: raise Conflict('Interpretation selected an unavailable company profile')
        profile=profiles[0]
        effective=effective_sequence_messages(messages,catalogue)
        named=next((found for m in reversed(effective) if (found:=mentioned_profiles(m['content'],catalogue['profiles']))),[])
        if len(named)!=1 or named[0]['key']!=profile['key']:raise Conflict('Interpretation must retain the uniquely resolved company')
        issue=sequence_literal_issue(effective,profile)
        if issue:raise Conflict(issue)
        for m in reversed(effective):
            body=m['content'].casefold()
            named_connections=[c for c in profile['connections'] if c['key'] in body or any(a in body for a in c['aliases'])]
            if named_connections:break
        else:named_connections=[c for c in profile['connections'] if c['primary']]
        if len(named_connections)!=1 or named_connections[0]['key']!=proposal['connection_key']:
            raise Conflict('Interpretation must retain the uniquely resolved source connection')
        if proposal['connection_key'] not in {c['key'] for c in profile['connections']}:
            raise Conflict('Interpretation selected an unavailable scoped connection')
        budget=explicit_budget(messages)
        if (budget is None or proposal['budget_pence']!=budget['budget_pence']
                or type(proposal['budget_pence']) is not int or not 104<=proposal['budget_pence']<=1_000_000):
            raise Conflict('The sequence must retain the explicit bounded user budget')
    frozen={'schema':JOURNEY_SCHEMA,'organization':organization,'conversation_id':conversation_id,
        'revision':revision,'request_id':request_id,'messages':messages,'catalogue':catalogue,
        'interpretation':proposal,'allow_generation':allow_generation,'created_at':now,
        'mode':'SYNTHETIC_ONLY','model_config':catalogue['model_config'],
        'native_organization':profile['organization'] if proposal['outcome']=='sequence' else None,'authority':'none'}
    return frozen | {'id':'journey_'+digest(frozen)}


def journey_commands(journey_id):
    """Reserve native command identities before any module can perform work."""
    result={key:journey_id+':'+key for key in ('email-assessment','call-assessment','decision',
        'initial','call','followup','sequence','review-open','review-approve')}
    for channel in ('email','human_call'):
        for index in range(6): result[channel+'-context-'+str(index)]=journey_id+':'+channel+'-context-'+str(index)
    return result


class SequenceJourneys:
    def __init__(self, store: SequenceJourneyStore, host: SequenceJourneyHost,
                 interpreter: SequenceIntentInterpreter, clock):
        self.store,self.host,self.interpreter,self.clock=store,host,interpreter,clock

    def send(self,organization,conversation_id,request_id,revision,content,allow_generation=True):
        revision_number(revision)
        text(content)
        key='journey_request_'+digest({'organization':organization,'conversation_id':conversation_id,'request_id':request_id})
        old=self.store.request(organization,conversation_id,key,revision+1,allow_generation)
        if old is not None:
            message=old['inputs']['messages'][-1]
            if message['id']!=request_id or message['content']!=content:
                raise Conflict('The original sequence message already binds different exact inputs')
            return old
        source=self.store.source(organization,conversation_id,revision)
        now=self.clock()
        messages=source['messages']+[{'id':request_id,'revision':revision+1,'role':'user','content':content,'created_at':now}]
        catalogue=self.host.catalogue(organization)
        proposal=self.interpreter.interpret(messages,catalogue)
        frozen=journey_request(organization,conversation_id,revision+1,key,messages,catalogue,proposal,allow_generation,now)
        return self.store.admit_message(organization,frozen,revision,request_id,content)

    def request(self, organization, conversation_id, request_id, revision, allow_generation):
        old=self.store.request(organization,conversation_id,request_id,revision,allow_generation)
        if old is not None:return old
        source=self.store.source(organization,conversation_id,revision)
        catalogue=self.host.catalogue(organization)
        proposal=self.interpreter.interpret(source['messages'],catalogue)
        frozen=journey_request(organization,conversation_id,revision,request_id,source['messages'],
            catalogue,proposal,allow_generation,self.clock())
        return self.store.admit(organization,frozen)

    def advance(self, organization, journey_id):
        row=self.store.current(organization,journey_id)
        if not row['current'] or row['status'] not in JOURNEY_ACTIVE:return row
        try:
            result=self.host.step(organization,row)
            return self.store.progress(organization,row,result)
        except (Conflict,ValueError) as error:
            return self.store.block(organization,journey_id,str(error))

    def view(self, organization, journey_id):
        row=self.store.get(organization,journey_id)
        return self.host.inspect(organization,row)

    def listing(self, organization, conversation_id):
        return [self.host.inspect(organization,row) for row in self.store.listing(organization,conversation_id)]

    def approve(self, organization, journey_id, request_id, revision, subject_id, reason):
        return self.host.approve(organization,journey_id,request_id,revision,subject_id,reason)

    def stop(self, organization, journey_id, request_id, revision):
        return self.store.stop(organization,journey_id,request_id,revision)

    def observe_task(self, organization, journey_id, request_id, revision, step_id):
        return self.host.observe_task(organization,journey_id,request_id,revision,step_id)

    def observe_reply(self, organization, journey_id, request_id, revision, step_id):
        return self.host.observe_reply(organization,journey_id,request_id,revision,step_id)
