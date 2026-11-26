"""External learning in disjoint keys of the existing learning command/audit journals."""
import json
from acquisition.contracts import Conflict,NotFound,canonical,digest
from acquisition.learning import (external_registration,external_report,external_summarize,external_final_counts,
    external_comparisons,external_text,external_number)
from .actors import require_actor
from .admission_guard import verified_required


def member_key(business):return 'external-member:'+digest(business)
def record_key(kind,*values):return 'external-'+kind+':'+digest(list(values))


class SqliteExternalOutcomes:
    def __init__(self,database,clock,*,read_only=False):self.database,self.clock,self.read_only=database,clock,read_only
    def now(self):return external_number(self.clock())
    def writable(self,db):
        if self.read_only or self.database.inspection_only or verified_required(db):raise Conflict('External outcome writes are paused in an inspection or verified-format store')
    def read(self,db,org,key,kind=None):
        row=db.execute('SELECT request_hash,receipt FROM learning_commands WHERE organization=? AND request_id=?',(org,key)).fetchone()
        if row is None:return None
        try:
            value=json.loads(row[1])
            if (value['schema']!='external-learning-record/v1' or value['organization']!=org or value['key']!=key
                    or value['id']!='external_record_'+digest({k:v for k,v in value.items() if k!='id'})
                    or row[0]!=digest(value) or (kind is not None and value['kind']!=kind)):
                raise Conflict('External learning record integrity failed')
            return value
        except (ValueError,KeyError,TypeError) as e:raise Conflict('External learning journal record is invalid') from e
    def insert(self,db,org,key,kind,payload):
        value={'schema':'external-learning-record/v1','organization':org,'key':key,'kind':kind,'payload':payload}
        value=value|{'id':'external_record_'+digest(value)}
        db.execute('INSERT INTO learning_commands VALUES(?,?,?,?)',(org,key,digest(value),canonical(value)))
        return value
    def audit(self,db,org,cohort,record,now):
        db.execute('INSERT INTO learning_events(organization,cohort_id,kind,payload,at) VALUES(?,?,?,?,?)',
            (org,cohort,'external_'+record['kind'],canonical(record),now))
    def audited(self,db,org,cohort,record):
        rows=db.execute('SELECT payload FROM learning_events WHERE organization=? AND cohort_id=? AND kind=? AND payload=?',
            (org,cohort,'external_'+record['kind'],canonical(record))).fetchall()
        if len(rows)!=1:raise Conflict('External evidence lacks its single atomic audit record')
    def command(self,db,org,actor,op,key,inputs,value=None):
        for v in (org,actor,key):external_text(v)
        identity=record_key('command',actor,op,key);old=self.read(db,org,identity,'command')
        if old:
            if old['payload']['inputs']!=inputs:raise Conflict('External command ID binds different exact inputs')
            return old['payload']['receipt']
        if value is not None:
            self.insert(db,org,identity,'command',{'inputs':inputs,'receipt':value})
            return value
    @staticmethod
    def reservations(c):
        result=[]
        crm=next(s for s in c['sources'] if s['role']=='outcomes')
        sender=next(s for s in c['sources'] if s['role']=='dispatch')
        for m in c['assignments']:
            value={'cohort_id':c['id'],'business_id':m['business_id']}
            result.append((record_key('crm-record',crm['system'],crm['account_id'],m['outcome_record_id']),value))
            if m['dispatch'] is not None:
                result.append((record_key('dispatch',sender['system'],sender['account_id'],m['dispatch']['id']),value))
        return result
    def check_writer(self,db,org,actor,generation):
        self.writable(db)
        if require_actor(db,org,actor,'operator')['generation']!=generation:
            raise Conflict('External operator authority changed before commit')
    def finish(self,db,org,actor,op,key,inputs,value,generation,floor):
        result=self.command(db,org,actor,op,key,inputs,value)
        self.check_writer(db,org,actor,generation)
        if self.now()<floor:raise Conflict('Evidence became future-dated before commit')
        return result
    def load(self,db,org,cohort_id):
        external_text(org);external_text(cohort_id)
        row=self.read(db,org,record_key('cohort',cohort_id),'registration')
        if row is None:raise NotFound('External cohort not found in this organization')
        c=row['payload']['cohort'];self.audited(db,org,cohort_id,row)
        original={k:v for k,v in c.items() if k!='id'}
        if external_registration(original,org,row['payload']['at'])!=c or c['id']!=cohort_id:raise Conflict('External registration differs from its frozen source')
        campaign=self.read(db,org,record_key('campaign',c['campaign_id']),'campaign')
        if campaign is None or campaign['payload']!={'cohort_id':cohort_id}:raise Conflict('External campaign binding is missing')
        for m in c['assignments']:
            slot=self.read(db,org,member_key(m['business_id']),'member')
            if slot is None or slot['payload']!={'cohort_id':cohort_id,'business_id':m['business_id']}:raise Conflict('Original membership reservation is missing or substituted')
            if db.execute('SELECT 1 FROM learning_members WHERE organization=? AND business_id=?',(org,m['business_id'])).fetchone():
                raise Conflict('Business already has a synthetic learning cohort')
        for key,value in self.reservations(c):
            record=self.read(db,org,key,'native-identity')
            if record is None or record['payload']!=value:raise Conflict('Original native dispatch or CRM identity reservation is missing')
        return c
    def state(self,db,org,cohort_id):
        c=self.load(db,org,cohort_id);events={};snapshots=[];reports=[];total_bytes=0
        rows=db.execute("SELECT request_id FROM learning_commands WHERE organization=? AND json_extract(receipt,'$.schema')='external-learning-record/v1' AND json_extract(receipt,'$.kind')='report' "
            "AND json_extract(receipt,'$.payload.cohort_id')=? ORDER BY rowid",(org,cohort_id)).fetchall()
        for row in rows:
            r=self.read(db,org,row[0],'report');self.audited(db,org,cohort_id,r);p=r['payload']
            normalized,raw=external_report(p['snapshot'],c,p['at'])
            if normalized!=p['snapshot'] or row[0]!=record_key('report',cohort_id,normalized['report_id']):raise Conflict('Report identity differs from its source')
            total_bytes+=len(canonical(normalized).encode());reports.append(p)
            source=next(s for s in c['sources'] if s['id']==normalized['source_id'])
            for e in raw:
                key=record_key('event',source['system'],source['account_id'],e['event_id'])
                native=self.read(db,org,key,'event')
                expected={'cohort_id':cohort_id,'source_id':source['id'],'event':e}
                if native is None or native['payload']!=expected:raise Conflict('Report event lost its original source binding')
                if key in events and events[key]!=e:raise Conflict('Duplicate source event changed')
                events[key]=e
            if normalized['final']:
                snapshots.append([e['business_id'] for e in raw if e['kind'] in {'qualified_enquiry','no_qualified_enquiry'}])
        summary,outcomes=external_summarize(c,list(events.values()),snapshots)
        final=self.read(db,org,record_key('final',cohort_id),'finalization')
        if final:
            self.audited(db,org,cohort_id,final)
            value=final['payload']
            if (not summary['coverage_complete'] or value['outcomes_sha256']!=digest(outcomes)
                    or value['reports_sha256']!=digest(reports) or value['groups']!=external_final_counts(c,outcomes)):
                raise Conflict('Finalization differs from the original complete evidence')
        return c,summary,outcomes,reports,events,total_bytes,final
    def current(self,db,org,cohort_id,reports,final,now):
        registered=self.read(db,org,record_key('cohort',cohort_id),'registration')['payload']['at']
        return registered<=now and all(p['at']<=now for p in reports) and (final is None or final['payload']['finalized_at']<=now)

    def register(self,org,actor,key,payload):
        with self.database.transaction() as db:
            self.writable(db);generation=require_actor(db,org,actor,'operator')['generation'];now=self.now();c=external_registration(payload,org,now)
            inputs={'manifest':c};old=self.command(db,org,actor,'register',key,inputs)
            if old:self.load(db,org,old['cohort_id']);return old
            existing=self.read(db,org,record_key('campaign',c['campaign_id']),'campaign')
            if existing:
                saved=self.load(db,org,existing['payload']['cohort_id'])
                if saved!=c:raise Conflict('An external campaign cannot change its original assignments or metric')
                r=self.read(db,org,record_key('cohort',c['id']),'registration')['payload']['receipt']
            else:
                for m in c['assignments']:
                    if self.read(db,org,member_key(m['business_id'])) or db.execute('SELECT 1 FROM learning_members WHERE organization=? AND business_id=?',(org,m['business_id'])).fetchone():
                        raise Conflict('A business cannot count in another learning cohort in this organization')
                for identity,value in self.reservations(c):
                    if self.read(db,org,identity):raise Conflict('An external dispatch or CRM record already belongs to another cohort')
                r={'kind':'external_campaign_registered','cohort_id':c['id'],'campaign_id':c['campaign_id'],'registered_at':now,'actor':actor,'actor_generation':generation,
                   'data_class':c['data_class'],'mode':c['mode'],'authority':'OBSERVATIONS_ONLY_NO_SEND_OR_APPROVAL'}
                record=self.insert(db,org,record_key('cohort',c['id']),'registration',{'cohort':c,'at':now,'receipt':r})
                self.audit(db,org,c['id'],record,now)
                self.insert(db,org,record_key('campaign',c['campaign_id']),'campaign',{'cohort_id':c['id']})
                for m in c['assignments']:self.insert(db,org,member_key(m['business_id']),'member',{'cohort_id':c['id'],'business_id':m['business_id']})
                for identity,value in self.reservations(c):self.insert(db,org,identity,'native-identity',value)
            self.check_writer(db,org,actor,generation)
            external_registration(payload,org,self.now())
            return self.finish(db,org,actor,'register',key,inputs,r,generation,max([now,c['window_start']]+[m['dispatch']['at'] for m in c['assignments'] if m['dispatch']]))
    def ingest(self,org,actor,key,cohort_id,payload):
        with self.database.transaction() as db:
            self.writable(db);generation=require_actor(db,org,actor,'operator')['generation'];now=self.now()
            c,summary,outcomes,reports,events,size,final=self.state(db,org,cohort_id)
            if not self.current(db,org,cohort_id,reports,final,now):raise Conflict('Stored evidence is after the current clock; inspect history instead')
            normalized,raw=external_report(payload,c,now);inputs={'cohort_id':cohort_id,'report':normalized}
            old=self.command(db,org,actor,'import',key,inputs)
            if old:return old
            identity=record_key('report',cohort_id,normalized['report_id']);existing=self.read(db,org,identity,'report')
            if existing:
                if existing['payload']['snapshot']!=normalized:raise Conflict('An immutable report ID cannot change content')
                return self.finish(db,org,actor,'import',key,inputs,existing['payload']['receipt'],generation,max(now,normalized['watermark']))
            if final:raise Conflict('Finalized external outcomes are immutable; reconcile late corrections separately')
            if len(reports)>=32 or size+len(canonical(normalized).encode())>16*1024*1024:raise Conflict('Cohort recorded-report limit reached')
            source=next(s for s in c['sources'] if s['id']==normalized['source_id']);added=0
            for e in raw:
                event_key=record_key('event',source['system'],source['account_id'],e['event_id'])
                previous=self.read(db,org,event_key,'event');value={'cohort_id':cohort_id,'source_id':source['id'],'event':e}
                if previous:
                    if previous['payload']!=value:raise Conflict('External source event ID already binds different observations or a different cohort')
                else:self.insert(db,org,event_key,'event',value);added+=1
            if len(events)+added>20000:raise Conflict('Cohort event limit reached')
            r={'kind':'external_report_imported','cohort_id':cohort_id,'report_id':normalized['report_id'],'imported_at':now,'actor':actor,'actor_generation':generation,
               'added_events':added,'duplicate_events':len(raw)-added,'watermark':normalized['watermark'],'final':normalized['final'],
               'data_class':c['data_class'],'evidence_assurance':'OPERATOR_ATTESTED_NOT_PROVIDER_VERIFIED'}
            record=self.insert(db,org,identity,'report',{'cohort_id':cohort_id,'at':now,'snapshot':normalized,'receipt':r})
            self.audit(db,org,cohort_id,record,now)
            self.state(db,org,cohort_id)  # Contradictory observations roll back the entire report.
            self.check_writer(db,org,actor,generation)
            if self.now()<normalized['watermark']:raise Conflict('Report watermark moved into the future before commit')
            return self.finish(db,org,actor,'import',key,inputs,r,generation,max(now,normalized['watermark']))
    def finalize(self,org,actor,key,cohort_id):
        with self.database.transaction() as db:
            self.writable(db);generation=require_actor(db,org,actor,'operator')['generation'];now=self.now()
            c,summary,outcomes,reports,events,size,final=self.state(db,org,cohort_id);inputs={'cohort_id':cohort_id}
            if not self.current(db,org,cohort_id,reports,final,now):raise Conflict('Stored evidence is after the current clock; inspect history instead')
            old=self.command(db,org,actor,'finalize',key,inputs)
            if old:return old
            if final:return self.finish(db,org,actor,'finalize',key,inputs,final['payload'],generation,max(now,c['window_end']))
            if now<c['window_end'] or any(p['at']>now for p in reports) or not summary['coverage_complete']:raise Conflict('Every original assignment, including holdouts, needs an explicit outcome and a complete final snapshot after maturity')
            groups=external_final_counts(c,outcomes)
            value={'kind':'external_cohort_finalized','cohort_id':cohort_id,'finalized_at':now,'actor':actor,'actor_generation':generation,'data_class':c['data_class'],
                'metric':c['metric'],'groups':groups,'comparisons':external_comparisons(c,groups),
                'outcomes_sha256':digest(outcomes),'reports_sha256':digest(reports),'evidence_assurance':'OPERATOR_ATTESTED_NOT_PROVIDER_VERIFIED',
                'authority':'ADVISORY_REQUIRES_NEW_PROPOSAL_AND_APPROVAL'}
            record=self.insert(db,org,record_key('final',cohort_id),'finalization',value);self.audit(db,org,cohort_id,record,now)
            self.check_writer(db,org,actor,generation)
            if self.now()<c['window_end']:raise Conflict('Observation clock moved before maturity during finalization')
            return self.finish(db,org,actor,'finalize',key,inputs,value,generation,max(now,c['window_end']))
    def view(self,org,cohort_id):
        with self.database.connect() as db:
            db.execute('BEGIN');now=self.now();c,s,outcomes,reports,events,size,final=self.state(db,org,cohort_id)
            frozen=final is not None
            current=self.current(db,org,cohort_id,reports,final,now)
            return {'cohort':c,'current':current,'status':'historical_evidence_after_current_clock' if not current else 'finalized' if frozen else 'awaiting_complete_outcomes' if now>=c['window_end'] else 'observing',
                'as_of':now,'enrolled':len(c['assignments']),**s,'reports':[p['receipt'] for p in reports],
                'posterior_groups':final['payload']['groups'] if frozen and current else [],'comparisons':final['payload']['comparisons'] if frozen and current else [],
                'finalization':final['payload'] if frozen else None,'authority':'OBSERVATIONS_ONLY_NO_SEND_OR_APPROVAL',
                'limitations':['External records are operator-attested, not independently provider-verified.',
                    'Opens, clicks and raw replies are diagnostics, not qualified outcomes.','Missing outcomes remain unknown.',
                    'Repeated business cohorts and finalized corrections are unsupported.','No synthetic memory, live sending or model training is changed.']}
    def snapshot(self,org,cohort_id,report_id):
        with self.database.connect() as db:
            db.execute('BEGIN');self.state(db,org,cohort_id)
            value=self.read(db,org,record_key('report',cohort_id,report_id),'report')
            if value is None:raise NotFound('External report snapshot unavailable')
            return value['payload']
    def receipt(self,org,actor,operation,request_id):
        if operation not in {'register','import','finalize'}:raise ValueError('Use an installed external operation')
        for v in (org,actor,request_id):external_text(v)
        with self.database.connect() as db:
            value=self.read(db,org,record_key('command',actor,operation,request_id),'command')
            if value is None:raise NotFound('External command receipt unavailable')
            return value['payload']['receipt']|{'observation':'HISTORICAL_RECEIPT_NO_CURRENT_AUTHORITY'}
