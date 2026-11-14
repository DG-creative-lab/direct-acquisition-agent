"""Reviewed synthetic recipient facts and bounded projections, never instructions or authority."""

from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
import math
import hashlib

from acquisition.audiences import NativeReference, native_reference_from
from acquisition.contracts import Conflict, canonical, digest


SLOTS = ('contact_role','prior_interaction','account_activity','business_signal')
VALUES = {
    'contact_role': {'operations_manager':'an operations manager', 'owner_director':'an owner or director',
                     'procurement_manager':'a procurement manager'},
    'prior_interaction': {'requested_overview':'requested a product overview', 'attended_demo':'attended a product demonstration'},
    'account_activity': {'equipment_quote':'requested an equipment quotation', 'maintenance_overview':'requested a maintenance overview'},
    'business_signal': {'new_location':'announced a new business location', 'maintenance_program':'announced a maintenance program'},
}
USES = ('email:acquisition','human_call:acquisition')


def text(value, maximum=200):
    if (type(value) is not str or not 1<=len(value)<=maximum or value!=value.strip()
            or any(ord(c)<32 for c in value) or chr(0x2014) in value):
        raise ValueError('Use bounded plain recipient metadata')


def moment(value):
    if type(value) not in (int,float) or not math.isfinite(value) or value<0:
        raise ValueError('Use a finite nonnegative context timestamp')


def uses(values):
    if type(values) is not tuple or len(set(values))!=len(values) or not set(values)<=set(USES):
        raise ValueError('Declare distinct supported recipient-data uses')


@dataclass(frozen=True)
class RecipientTarget:
    organization: str
    profile_id: str
    contact: NativeReference
    account: NativeReference
    experiment_unit: str

    def __post_init__(self):
        for value in (self.organization,self.profile_id,self.experiment_unit): text(value)
        if (type(self.contact) is not NativeReference or type(self.account) is not NativeReference
                or self.contact.role!='contact' or self.account.role!='account'
                or self.contact.connection.organization!=self.organization
                or self.account.connection!=self.contact.connection):
            raise ValueError('Bind an exact scoped contact/account pair')

    @property
    def id(self): return 'recipient_' + digest(asdict(self))


@dataclass(frozen=True)
class RecipientDocument:
    key: str
    kind: str
    body: str

    def __post_init__(self):
        text(self.key)
        if (self.kind not in {'crm_note','webpage','attachment','inbound_body','structured_record'}
                or type(self.body) is not str or not 1<=len(self.body)<=4096):
            raise ValueError('Use bounded untrusted source material')

    @property
    def sha256(self): return hashlib.sha256(self.body.encode()).hexdigest()


@dataclass(frozen=True)
class RecipientFact:
    subject_id: str
    slot: str
    code: str | None
    event_date: str | None
    document_key: str
    start: int
    end: int
    observed_at: float
    expires_at: float
    permitted_uses: tuple[str, ...]
    review_id: str | None
    state: str = 'asserted'

    def __post_init__(self):
        text(self.subject_id); text(self.document_key)
        if self.slot not in SLOTS or self.state not in {'asserted','withdrawn','unknown'}:
            raise ValueError('Unsupported recipient claim slot or state')
        if self.state=='asserted':
            if self.code not in VALUES[self.slot]: raise ValueError('Use a supported reviewed fact value')
            if self.slot=='contact_role':
                if self.event_date is not None: raise ValueError('A recorded role has no event date')
            elif type(self.event_date) is not str or date.fromisoformat(self.event_date).isoformat()!=self.event_date:
                raise ValueError('Event facts require an exact calendar date')
        elif self.code is not None or self.event_date is not None:
            raise ValueError('Unknown/withdrawn facts cannot supply factual values')
        moment(self.observed_at); moment(self.expires_at); uses(self.permitted_uses)
        if not self.observed_at<self.expires_at: raise ValueError('Invalid fact freshness window')
        if self.event_date is not None and self.event_date>datetime.fromtimestamp(self.observed_at,timezone.utc).date().isoformat():
            raise ValueError('An observed event cannot be future-dated')
        if (type(self.start) is not int or type(self.end) is not int or not 0<=self.start<self.end<=4096):
            raise ValueError('Bind an exact bounded evidence span')
        if self.review_id is not None: text(self.review_id)

    @property
    def id(self): return 'recipient_fact_' + digest(asdict(self))

    @property
    def signature(self):
        return (self.code,self.event_date,self.state,self.expires_at,tuple(sorted(self.permitted_uses)),self.review_id is not None)

    @property
    def statement(self):
        if self.state!='asserted': return None
        if self.slot=='contact_role': return 'The contact is recorded as ' + VALUES[self.slot][self.code] + '.'
        owner = 'contact' if self.slot=='prior_interaction' else 'account'
        return 'The ' + owner + ' is recorded as having ' + VALUES[self.slot][self.code] + ' on ' + self.event_date + '.'


@dataclass(frozen=True)
class RecipientEvidence:
    target: RecipientTarget
    source_key: str
    version: int
    observed_at: float
    expires_at: float
    permitted_uses: tuple[str, ...]
    complete: bool
    declared_documents: int
    declared_facts: int
    documents: tuple[RecipientDocument, ...]
    facts: tuple[RecipientFact, ...]
    schema: str = 'recipient-evidence/v1'
    mode: str = 'SYNTHETIC_ONLY'

    def __post_init__(self):
        if type(self.target) is not RecipientTarget: raise ValueError('Declare an exact recipient target')
        text(self.source_key); moment(self.observed_at); moment(self.expires_at); uses(self.permitted_uses)
        if (type(self.version) is not int or not 1<=self.version<=100 or type(self.complete) is not bool
                or not self.observed_at<self.expires_at or self.schema!='recipient-evidence/v1' or self.mode!='SYNTHETIC_ONLY'):
            raise ValueError('Use a versioned synthetic context source')
        for declared, values, kind, maximum in ((self.declared_documents,self.documents,RecipientDocument,8),
                                               (self.declared_facts,self.facts,RecipientFact,16)):
            if (type(declared) is not int or not 0<=declared<=maximum or type(values) is not tuple
                    or len(values)>declared or (self.complete and len(values)!=declared)
                    or any(type(v) is not kind for v in values)):
                raise ValueError('Context coverage differs from its declared bounded population')
        documents = {d.key:d for d in self.documents}
        if len(documents)!=len(self.documents) or len({f.id for f in self.facts})!=len(self.facts):
            raise ValueError('Duplicate context documents or facts')
        for fact in self.facts:
            subject = self.target.contact if fact.slot in {'contact_role','prior_interaction'} else self.target.account
            if (fact.subject_id!=subject.id or fact.document_key not in documents
                    or fact.end>len(documents[fact.document_key].body) or fact.observed_at>self.observed_at):
                raise ValueError('Fact scope, evidence span or observation differs from its source')

    @property
    def id(self): return 'recipient_source_' + digest(asdict(self))

    def manifest(self):
        """Retain typed observations and exact evidence fingerprints, never raw document bodies."""
        docs = {d.key:d for d in self.documents}
        return {'schema':'recipient-source-manifest/v1','source_id':self.id,'target':asdict(self.target),
            'target_id':self.target.id,'source_key':self.source_key,'version':self.version,
            'observed_at':self.observed_at,'expires_at':self.expires_at,'complete':self.complete,
            'permitted_uses':list(self.permitted_uses),'mode':self.mode,
            'documents':[{'key':d.key,'kind':d.kind,'sha256':d.sha256,'length':len(d.body)} for d in self.documents],
            'facts':[{'fact':asdict(f),'fact_id':f.id,'evidence':{'document_key':f.document_key,
                'document_sha256':docs[f.document_key].sha256,'start':f.start,'end':f.end,
                'span_unit':'unicode_codepoints',
                'quote_sha256':hashlib.sha256(docs[f.document_key].body[f.start:f.end].encode()).hexdigest()}} for f in self.facts]}


@dataclass(frozen=True)
class RecipientContextRequest:
    assessment_id: str
    contact_id: str
    source_key: str
    source_version: int
    slots: tuple[str, ...]
    max_facts: int = 2

    def __post_init__(self):
        for value in (self.assessment_id,self.contact_id,self.source_key): text(value)
        if (type(self.source_version) is not int or not 1<=self.source_version<=100
                or type(self.slots) is not tuple or not self.slots or len(set(self.slots))!=len(self.slots)
                or not set(self.slots)<=set(SLOTS) or type(self.max_facts) is not int or not 1<=self.max_facts<=4):
            raise ValueError('Use bounded explicit context slots and source selection')


@dataclass(frozen=True)
class RecipientContextGuidance:
    version: str = 'v1'
    priority: tuple[str, ...] = SLOTS
    max_prompt_chars: int = 1600

    def __post_init__(self):
        text(self.version)
        if (type(self.priority) is not tuple or len(self.priority)!=len(SLOTS) or set(self.priority)!=set(SLOTS)
                or type(self.max_prompt_chars) is not int or not 256<=self.max_prompt_chars<=2000):
            raise ValueError('Freeze bounded recipient-context selection guidance')

    @property
    def id(self): return 'recipient_guidance_' + digest(asdict(self))


@dataclass(frozen=True)
class RecipientContextBasis:
    target: RecipientTarget
    assessment_id: str
    audience_source_id: str
    readiness_digest: str
    channel: str
    purpose: str
    eligible: bool

    def __post_init__(self):
        if type(self.target) is not RecipientTarget or type(self.eligible) is not bool:
            raise ValueError('Use attested recipient identity and eligibility')
        for value in (self.assessment_id,self.audience_source_id,self.readiness_digest): text(value)
        if self.channel+':'+self.purpose not in USES: raise ValueError('Unsupported recipient-context use')


def recipient_target_from(payload):
    return RecipientTarget(**(payload | {'contact':native_reference_from(payload['contact']),
                                         'account':native_reference_from(payload['account'])}))


def recipient_fact_from(payload):
    return RecipientFact(**(payload | {'permitted_uses':tuple(payload['permitted_uses'])}))


def recipient_evidence_from(payload):
    return RecipientEvidence(**(payload | {'target':recipient_target_from(payload['target']),
        'permitted_uses':tuple(payload['permitted_uses']),
        'documents':tuple(RecipientDocument(**d) for d in payload['documents']),
        'facts':tuple(recipient_fact_from(f) for f in payload['facts'])}))


def select_recipient_context(target, request, guidance, manifest, history, channel, purpose, now, eligible):
    """Missingness and contradictions omit specificity; source prose is never prompt material."""
    selected, omissions = [], []
    use = channel+':'+purpose
    global_reason = None
    if not eligible: global_reason = 'recipient_not_eligible'
    elif manifest is None: global_reason = 'retrieval_unavailable'
    elif manifest['target_id']!=target.id: raise Conflict('Context source differs from the exact recipient')
    elif not manifest['complete']: global_reason = 'source_incomplete'
    elif not manifest['observed_at']<=now<manifest['expires_at']: global_reason = 'source_outside_window'
    elif use not in manifest['permitted_uses']: global_reason = 'use_not_permitted'
    candidates = [item for item in manifest['facts']] if manifest else []
    known = {}
    for source in history:
        for item in source['facts']:
            fact = recipient_fact_from(item['fact']); key = (fact.subject_id,fact.slot)
            previous = known.get(key,())
            if not previous or fact.observed_at>previous[0].observed_at: known[key] = (fact,)
            elif fact.observed_at==previous[0].observed_at and fact not in previous: known[key] = (*previous,fact)
    def prompt(items):
        return {'kind':'source_derived_data_not_instructions','recipient_scope':target.id,
                'facts':[{'fact_id':f['fact_id'],'statement':f['statement']} for f in items]}
    for slot in guidance.priority:
        if slot not in request.slots: continue
        reason = global_reason
        group = [i for i in candidates if i['fact']['slot']==slot]
        if not reason:
            if not group: reason = 'missing'
            else:
                latest = max(i['fact']['observed_at'] for i in group)
                group = [i for i in group if i['fact']['observed_at']==latest]
                facts = [recipient_fact_from(i['fact']) for i in group]
                seen = known.get((facts[0].subject_id,slot),())
                if seen and seen[0].observed_at>latest: reason = 'superseded'
                elif len({f.signature for f in (*facts,*seen)})>1: reason = 'contradictory'
                elif facts[0].state!='asserted': reason = facts[0].state
                elif facts[0].review_id is None: reason = 'unreviewed'
                elif not facts[0].observed_at<=now<facts[0].expires_at: reason = 'fact_outside_window'
                elif use not in facts[0].permitted_uses: reason = 'use_not_permitted'
                elif len(selected)>=request.max_facts: reason = 'fact_limit'
                elif len(canonical(prompt(selected+[{'fact_id':min(group,key=lambda i:i['fact_id'])['fact_id'],
                    'statement':facts[0].statement}])))>guidance.max_prompt_chars: reason = 'context_budget'
                else:
                    item = min(group,key=lambda i:i['fact_id'])
                    selected.append({'fact_id':item['fact_id'],'subject_id':facts[0].subject_id,'slot':slot,
                        'statement':facts[0].statement,'evidence':item['evidence'],'review_id':facts[0].review_id,
                        'observed_at':facts[0].observed_at,'expires_at':facts[0].expires_at,
                        'source_id':manifest['source_id'],'source_key':manifest['source_key'],'source_version':manifest['version']})
        if reason: omissions.append({'slot':slot,'reason':reason})
    return {'schema':'recipient-context/v1','mode':'SYNTHETIC_ONLY','target_id':target.id,
        'channel':channel,'purpose':purpose,'guidance_id':guidance.id,'selected':selected,'omissions':omissions,
        'status':'ready' if selected and not omissions else 'partial' if selected else 'insufficient_context',
        'clarification':'Which reviewed business role or recent interaction should inform the message?' if not selected else None,
        'prompt_data':prompt(selected),'prompt_char_count':len(canonical(prompt(selected))),
        'retention':'synthetic_audit_only_no_raw_documents','authority':'none','approval':'not_granted','execution':'not_performed'}


def validate_recipient_assertions(context, assertions):
    if type(assertions) is not tuple or len(assertions)>4: raise ValueError('Use bounded factual assertions')
    allowed = {f['fact_id']:f for f in context['selected']}
    for assertion in assertions:
        if (type(assertion) is not dict or set(assertion)!={'fact_id','statement','target_id'}
                or any(type(value) is not str for value in assertion.values())
                or assertion['target_id']!=context['target_id'] or assertion['fact_id'] not in allowed
                or assertion['statement']!=allowed[assertion['fact_id']]['statement']):
            raise Conflict('Recipient assertion differs from its exact permitted evidence')
    return {'validated_assertions':len(assertions),'authority':'none','approval':'not_granted'}
