"""Frozen external assignments and explicitly attested outcome evidence, not send authority."""
from collections import Counter
import math
import random

from acquisition.contracts import Conflict, canonical, digest
from .domain import BetaBelief

MODE = 'EXTERNAL_OPERATOR_ATTESTED'
CLASSES = {'recorded_fixture', 'operator_attested_external'}
KINDS = {'delivered', 'bounced', 'opened', 'clicked', 'reply', 'qualified_enquiry', 'no_qualified_enquiry'}
PRIMARY = {'qualified_enquiry', 'no_qualified_enquiry'}
MAX_MEMBERS = 1000
MAX_REPORTS = 32


def fields(value, names):
    if type(value) is not dict or set(value) != set(names.split()):
        raise ValueError('Use exact external outcome contract fields: '+names)


def text(value, limit=160):
    if (type(value) is not str or not value or value != value.strip() or len(value)>limit
            or any(ord(c)<32 for c in value)):
        raise ValueError('Use bounded nonempty plain source identities or notes')
    return value


def number(value):
    if type(value) not in (int,float) or not 0<=value<1e12 or not math.isfinite(value):
        raise ValueError('Use a finite nonnegative timestamp or parameter')
    return value


def sha(value):
    if type(value) is not str or len(value)!=64 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError('Bind exact content with a lowercase SHA-256 digest')
    return value


def attestation(value):
    fields(value,'confirmed note evidence_ref evidence_sha256')
    if value['confirmed'] is not True:raise ValueError('Explicitly attest the original external records')
    text(value['note'],1000);text(value['evidence_ref'],300);sha(value['evidence_sha256'])


def registration(payload, organization, now):
    fields(payload,'schema mode data_class organization campaign_id channel metric assignment_design qualification_rule window_start window_end prior sources assignments attestation')
    if (payload['schema']!='external-campaign-registration/v1' or payload['mode']!=MODE
            or payload['data_class'] not in CLASSES or payload['organization']!=organization
            or payload['channel'] not in {'postal','email'} or payload['metric']!='qualified_enquiry/v1'):
        raise ValueError('Use a scoped external postal/email qualified-enquiry contract')
    if payload['assignment_design'] not in {'observational','operator_attested_randomized'}:raise ValueError('Declare the original assignment design')
    text(organization);text(payload['campaign_id']);text(payload['qualification_rule'],1000)
    start,end=number(payload['window_start']),number(payload['window_end'])
    if not start<end<=start+90*86400 or start>now:raise ValueError('Freeze a started observation window of at most ninety days')
    fields(payload['prior'],'alpha beta')
    for v in payload['prior'].values():
        number(v)
        if not 0<v<=10000:raise ValueError('Choose explicit positive bounded prior parameters')
    sources=payload['sources']
    if type(sources) is not list or len(sources)!=2:raise ValueError('Register one dispatch source and one outcome source')
    for source in sources:
        fields(source,'id role system account_id')
        for k in ('id','system','account_id'):text(source[k])
    if {s['role'] for s in sources}!={'dispatch','outcomes'} or len({s['id'] for s in sources})!=2:
        raise ValueError('Sources must have unique identities and separate dispatch/outcome roles')
    members=payload['assignments']
    if type(members) is not list or not 3<=len(members)<=MAX_MEMBERS:raise ValueError('Freeze three to one thousand business assignments including A, B and holdout')
    business=set();records=set();dispatches=set();groups={}
    for m in members:
        fields(m,'business_id segment arm creative_sha256 outcome_record_id dispatch')
        for k in ('business_id','segment','outcome_record_id'):text(m[k])
        if m['business_id'] in business or m['outcome_record_id'] in records:raise ValueError('Business and CRM record identities must be unique')
        business.add(m['business_id']);records.add(m['outcome_record_id'])
        if m['arm'] not in {'A','B','holdout'}:raise ValueError('Choose A, B or an untreated holdout')
        if m['arm']=='holdout':
            if m['creative_sha256'] is not None or m['dispatch'] is not None:raise ValueError('A holdout has no message or creative')
        else:
            sha(m['creative_sha256']);d=m['dispatch']
            fields(d,'id status at content_sha256')
            text(d['id']);number(d['at']);sha(d['content_sha256'])
            if (d['status'] not in {'sent','failed','not_sent'} or not start<=d['at']<end or d['at']>now
                    or d['content_sha256']!=m['creative_sha256']):
                raise ValueError('Dispatch evidence must bind the exact assigned creative and original window')
            if d['id'] in dispatches:raise ValueError('Each assignment requires its own external dispatch identity')
            dispatches.add(d['id'])
        key=(m['segment'],m['arm'])
        if key in groups and groups[key]!=m['creative_sha256']:raise ValueError('One exact creative per segment and arm is required')
        groups[key]=m['creative_sha256']
    segments={m['segment'] for m in members}
    if len(segments)>10 or any({m['arm'] for m in members if m['segment']==s}!={'A','B','holdout'} for s in segments):
        raise ValueError('Use at most ten segments with complete A/B/holdout assignments')
    attestation(payload['attestation'])
    value=payload|{'sources':sorted(sources,key=lambda s:s['id']),'assignments':sorted(members,key=lambda m:m['business_id'])}
    return value|{'id':'external_cohort_'+digest(value)}


def report(payload, cohort, now):
    fields(payload,'schema mode data_class organization cohort_id report_id source_id watermark final page_count pages attestation')
    if (payload['schema']!='external-outcome-report/v1' or payload['mode']!=MODE
            or any(payload[k]!=cohort[k] for k in ('organization','data_class')) or payload['cohort_id']!=cohort['id']):
        raise Conflict('Report scope, mode or cohort differs from registration')
    text(payload['report_id']);text(payload['source_id']);watermark=number(payload['watermark'])
    if not cohort['window_start']<=watermark<=min(now,cohort['window_end']) or type(payload['final']) is not bool:
        raise ValueError('Use a known watermark within the elapsed original window')
    sources={s['id']:s for s in cohort['sources']}
    if payload['source_id'] not in sources:raise Conflict('Report source was not registered')
    source=sources[payload['source_id']]
    if payload['final'] and (source['role']!='outcomes' or watermark!=cohort['window_end']):
        raise ValueError('Only the outcome source can attest the complete closed window')
    if type(payload['page_count']) is not int or not 1<=payload['page_count']<=100 or type(payload['pages']) is not list:
        raise ValueError('Use a bounded complete page set')
    if len(payload['pages'])!=payload['page_count']:raise ValueError('Missing report pages remain missing evidence')
    members={m['business_id']:m for m in cohort['assignments']};pages=set();events={};raw_count=0
    for page in payload['pages']:
        fields(page,'number events')
        if type(page['number']) is not int or page['number'] in pages or not 1<=page['number']<=payload['page_count'] or type(page['events']) is not list:
            raise ValueError('Report pages must be unique and complete')
        pages.add(page['number'])
        raw_count+=len(page['events'])
        if raw_count>10000:raise ValueError('Report exceeds ten thousand event rows')
        for e in page['events']:
            fields(e,'event_id business_id arm creative_sha256 record_id kind occurred_at evidence_ref')
            text(e['event_id']);text(e['evidence_ref'],300);number(e['occurred_at'])
            m=members.get(e['business_id'])
            if m is None or any(e[k]!=m[k] for k in ('arm','creative_sha256')):raise Conflict('Event differs from its original assignment')
            kind=e['kind']
            if kind not in KINDS:raise ValueError('Use an observed metric, not a score or inferred success')
            if cohort['channel']=='postal' and kind=='opened':raise ValueError('Postal delivery cannot establish an email open')
            if kind in PRIMARY:
                if source['role']!='outcomes' or e['record_id']!=m['outcome_record_id']:raise Conflict('Qualified outcomes require the registered CRM record/source')
            elif (source['role']!='dispatch' or m['dispatch'] is None or m['dispatch']['status']!='sent'
                    or e['record_id']!=m['dispatch']['id']):raise Conflict('Engagement events require an actually recorded send, not a holdout or planned export')
            if kind=='no_qualified_enquiry':
                if not payload['final'] or e['occurred_at']!=cohort['window_end']:raise ValueError('Non-response requires an explicit closed-window attestation')
            elif not cohort['window_start']<=e['occurred_at']<cohort['window_end'] or e['occurred_at']>watermark:
                raise ValueError('Event falls outside the observed window')
            if e['event_id'] in events and events[e['event_id']]!=e:raise Conflict('An external event ID cannot change its meaning')
            events[e['event_id']]=e
            if len(events)>10000:raise ValueError('Report exceeds ten thousand distinct events')
    attestation(payload['attestation'])
    value=payload|{'pages':sorted(payload['pages'],key=lambda p:p['number'])}
    return value,list(events.values())


def summarize(cohort, events, final_snapshots):
    outcomes={};funnel=Counter();unique={}
    for e in events:
        kind=e['kind'];funnel[kind]+=1;unique.setdefault(kind,set()).add(e['business_id'])
        if kind in PRIMARY:
            success=kind=='qualified_enquiry';old=outcomes.get(e['business_id'])
            if old is not None and old!=success:raise Conflict('Contradictory outcomes require reconciliation, not an overwritten observation')
            outcomes[e['business_id']]=success
    members={m['business_id'] for m in cohort['assignments']}
    complete=any(set(snapshot)==members for snapshot in final_snapshots)
    return {'received':len(outcomes),'missing':len(members-set(outcomes)),'successes':sum(outcomes.values()),
        'coverage_complete':complete and set(outcomes)==members,'event_counts':dict(sorted(funnel.items())),
        'business_counts':{k:len(v) for k,v in sorted(unique.items())}},outcomes


def final_counts(cohort, outcomes):
    groups={}
    for m in cohort['assignments']:
        key=(m['segment'],m['arm'],m['creative_sha256']);g=groups.setdefault(key,[0,0]);g[0]+=1;g[1]+=int(outcomes[m['business_id']])
    result=[]
    for (segment,arm,creative),(n,s) in sorted(groups.items()):
        b=BetaBelief(**cohort['prior']).observe(n,s);a,z=b.alpha,b.beta
        result.append({'segment':segment,'arm':arm,'creative_sha256':creative,'trials':n,'successes':s,
            'alpha':a,'beta':z,'mean':a/(a+z),'standard_deviation':math.sqrt(a*z/((a+z)**2*(a+z+1)))})
    return result


def comparisons(cohort, groups):
    rng=random.Random(digest({'cohort':cohort['id'],'groups':groups,'policy':'external-advisory/v1'}));result=[]
    for segment in sorted({g['segment'] for g in groups}):
        by_arm={g['arm']:g for g in groups if g['segment']==segment}
        draws={a:[rng.betavariate(g['alpha'],g['beta']) for _ in range(10000)] for a,g in by_arm.items()}
        candidate=max(('A','B'),key=lambda a:by_arm[a]['mean']);other='B' if candidate=='A' else 'A'
        enough=min(by_arm[a]['trials'] for a in ('A','B'))>=30 and by_arm['holdout']['trials']>=10
        p_other=sum(x>y for x,y in zip(draws[candidate],draws[other]))/10000
        p_control=sum(x>y for x,y in zip(draws[candidate],draws['holdout']))/10000
        supported=enough and p_other>=.9 and p_control>=.95 and cohort['assignment_design']=='operator_attested_randomized'
        result.append({'segment':segment,'candidate_arm':candidate,'action':'consider_next_experiment' if supported else 'collect_more_evidence',
            'probability_beats_other':p_other,'probability_beats_holdout':p_control,
            'intervals_90':{a:[sorted(v)[500],sorted(v)[9500]] for a,v in draws.items()},
            'authority':'ADVISORY_REQUIRES_NEW_PROPOSAL_AND_APPROVAL','policy':'external-advisory/v1','assignment_design':cohort['assignment_design'],
            'limitation':'Operator-attested assignments and outcomes; sampling and thresholds are illustrative, not calibrated causal proof.'})
    return result
