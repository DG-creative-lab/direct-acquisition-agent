"""External learning in disjoint keys of the existing learning command/audit journals."""
import json
from acquisition.contracts import Conflict,NotFound,canonical,digest
from acquisition.learning import (external_registration,external_report,external_historical_report,external_reconciliation,external_summarize,external_final_counts,
    external_comparisons,external_comparison_view,external_text,external_number)
from .actors import require_actor
from .admission_guard import verified_required


def member_key(business):return 'external-member:'+digest(business)
def record_key(kind,*values):return 'external-'+kind+':'+digest(list(values))


class SqliteExternalOutcomes:
    def __init__(self,database,clock,*,read_only=False,local_operator=False):
        self.database,self.clock,self.read_only=database,clock,read_only
        self.local_operator=local_operator
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
        if self.read(db,org,record_key('rejected',actor,op,key),'rejected'):
            raise Conflict('This request was definitively rejected; review again with a new request ID')
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
        self.context(db,org,cohort_id)
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
    def saved_report(self,db,org,cohort,identity):
        record=self.read(db,org,identity,'report')
        if record is None:raise NotFound('External report snapshot unavailable')
        self.audited(db,org,cohort['id'],record);p=record['payload']
        normalized,events,issues=external_historical_report(p['snapshot'],cohort,p['at'])
        if (p['cohort_id']!=cohort['id'] or normalized!=p['snapshot']
                or identity!=record_key('report',cohort['id'],normalized['report_id'])):
            raise Conflict('Report identity differs from its source')
        source=next(s for s in cohort['sources'] if s['id']==normalized['source_id'])
        for event in events:
            native=self.read(db,org,record_key('event',source['system'],source['account_id'],event['event_id']),'event')
            if native is None or native['payload']!={'cohort_id':cohort['id'],'source_id':source['id'],'event':event}:
                raise Conflict('Report event lost its original source binding')
        return p,events,issues,source

    def state(self,db,org,cohort_id):
        c=self.load(db,org,cohort_id);events={};excluded={};snapshots=[];reports=[];total_bytes=0
        rows=db.execute("SELECT request_id FROM learning_commands WHERE organization=? AND json_extract(receipt,'$.schema')='external-learning-record/v1' AND json_extract(receipt,'$.kind')='report' "
            "AND json_extract(receipt,'$.payload.cohort_id')=? ORDER BY rowid",(org,cohort_id)).fetchall()
        for row in rows:
            p,raw,issues,source=self.saved_report(db,org,c,row[0]);normalized=p['snapshot']
            total_bytes+=len(canonical(normalized).encode());reports.append(p)
            rejected={i['event_id']:i for i in issues}
            for e in raw:
                key=record_key('event',source['system'],source['account_id'],e['event_id'])
                if key in events and events[key]!=e:raise Conflict('Duplicate source event changed')
                events[key]=e
                if e['event_id'] in rejected:
                    issue=rejected[e['event_id']]
                    if key in excluded:issue=issue|{'report_ids':sorted(set(issue['report_ids']+excluded[key]['report_ids']))}
                    excluded[key]=issue
            if normalized['final']:
                snapshots.append([e['business_id'] for e in raw if e['kind'] in {'qualified_enquiry','no_qualified_enquiry'}])
        summary,outcomes=external_summarize(c,[e for key,e in events.items() if key not in excluded],snapshots)
        summary['reconciliation']=external_reconciliation(list(excluded.values()))
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

    @staticmethod
    def historical_finalization(cohort,receipt,reconciliation,*,current=True):
        return receipt|{'observation':'HISTORICAL_RECEIPT_NO_CURRENT_AUTHORITY','original_receipt':receipt,
            'comparisons':external_comparison_view(cohort,receipt['comparisons']) if current else [],
            'current':current,'reconciliation':reconciliation}

    @staticmethod
    def historical_import(receipt,reconciliation):
        return receipt|{'observation':'HISTORICAL_RECEIPT_NO_CURRENT_AUTHORITY',
            'original_receipt':receipt,'reconciliation':reconciliation}

    def register(self,org,actor,key,payload,*,selection=None,preview_id=None):
        with self.database.transaction() as db:
            self.writable(db);now=self.now();c=external_registration(payload,org,now)
            context=self.context_selection(db,org,selection) if selection is not None else None
            inputs={'manifest':c}
            if context is not None:inputs.update(company_context=context,preview_id=preview_id)
            old=self.command(db,org,actor,'register',key,inputs)
            if context is not None:
                self.expect_preview(db,org,'register',c,context,preview_id)
            if old is None and self.local_operator and (org,actor)==('local-conversations','local-operator'):
                # Missing authority is not evidence of a fresh setup. Keep prior
                # administration and outcome history authoritative across replay.
                established=(db.execute('SELECT 1 FROM review_actors WHERE organization=? LIMIT 1',(org,)).fetchone()
                    or db.execute('SELECT 1 FROM review_events WHERE organization=? LIMIT 1',(org,)).fetchone()
                    or db.execute('SELECT 1 FROM learning_events WHERE organization=? LIMIT 1',(org,)).fetchone()
                    or db.execute("SELECT 1 FROM learning_commands WHERE organization=? "
                        "AND json_extract(receipt,'$.schema')='external-learning-record/v1' "
                        "AND json_extract(receipt,'$.kind')='registration' LIMIT 1",(org,)).fetchone())
                if not established:
                    db.execute('INSERT INTO review_actors VALUES(?,?,?,?,?)',(org,actor,canonical(['operator']),True,1))
                    db.execute('INSERT INTO review_events(organization,case_id,kind,payload,at) VALUES(?,?,?,?,?)',
                        (org,None,'local_actor_configured',canonical({'actor':actor,'generation':1}),now))
            generation=require_actor(db,org,actor,'operator')['generation']
            if old:self.load(db,org,old['cohort_id']);return old
            existing=self.read(db,org,record_key('campaign',c['campaign_id']),'campaign')
            if existing:
                saved=self.load(db,org,existing['payload']['cohort_id'])
                if saved!=c:raise Conflict('An external campaign cannot change its original assignments or metric')
                if context is not None and self.context(db,org,c['id'])!=context:
                    raise Conflict('An existing cohort cannot acquire or change its original company binding')
                r=self.read(db,org,record_key('cohort',c['id']),'registration')['payload']['receipt']
            else:
                for m in c['assignments']:
                    if self.read(db,org,member_key(m['business_id'])) or db.execute('SELECT 1 FROM learning_members WHERE organization=? AND business_id=?',(org,m['business_id'])).fetchone():
                        raise Conflict('A business cannot count in another learning cohort in this organization')
                for identity,value in self.reservations(c):
                    if self.read(db,org,identity):raise Conflict('An external dispatch or CRM record already belongs to another cohort')
                r={'kind':'external_campaign_registered','cohort_id':c['id'],'campaign_id':c['campaign_id'],'registered_at':now,'actor':actor,'actor_generation':generation,
                   'data_class':c['data_class'],'mode':c['mode'],'authority':'OBSERVATIONS_ONLY_NO_SEND_OR_APPROVAL'}
                registration={'cohort':c,'at':now,'receipt':r}
                if context is not None:registration['company_context_sha256']=digest(context)
                record=self.insert(db,org,record_key('cohort',c['id']),'registration',registration)
                self.audit(db,org,c['id'],record,now)
                if context is not None:
                    binding=self.insert(db,org,record_key('context',c['id']),'company_context',{'cohort_id':c['id'],'context':context})
                    self.audit(db,org,c['id'],binding,now)
                self.insert(db,org,record_key('campaign',c['campaign_id']),'campaign',{'cohort_id':c['id']})
                for m in c['assignments']:self.insert(db,org,member_key(m['business_id']),'member',{'cohort_id':c['id'],'business_id':m['business_id']})
                for identity,value in self.reservations(c):self.insert(db,org,identity,'native-identity',value)
            self.check_writer(db,org,actor,generation)
            external_registration(payload,org,self.now())
            return self.finish(db,org,actor,'register',key,inputs,r,generation,max([now,c['window_start']]+[m['dispatch']['at'] for m in c['assignments'] if m['dispatch']]))
    def ingest(self,org,actor,key,cohort_id,payload,*,preview_id=None):
        with self.database.transaction() as db:
            self.writable(db);generation=require_actor(db,org,actor,'operator')['generation'];now=self.now()
            c,summary,outcomes,reports,events,size,final=self.state(db,org,cohort_id)
            if not self.current(db,org,cohort_id,reports,final,now):raise Conflict('Stored evidence is after the current clock; inspect history instead')
            normalized,raw,issues=external_historical_report(payload,c,now);inputs={'cohort_id':cohort_id,'report':normalized}
            if preview_id is not None:inputs['preview_id']=preview_id
            old=self.command(db,org,actor,'import',key,inputs)
            if old:return self.historical_import(old,summary['reconciliation']) if issues else old
            if preview_id is not None:
                self.require_context(db,org,cohort_id)
                self.expect_preview(db,org,'import',normalized,self.context(db,org,cohort_id),preview_id)
            identity=record_key('report',cohort_id,normalized['report_id']);existing=self.read(db,org,identity,'report')
            if existing:
                if existing['payload']['snapshot']!=normalized:raise Conflict('An immutable report ID cannot change content')
                observed=self.finish(db,org,actor,'import',key,inputs,existing['payload']['receipt'],generation,max(now,normalized['watermark']))
                return self.historical_import(observed,summary['reconciliation']) if issues else observed
            normalized,raw=external_report(payload,c,now)
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
    def finalize(self,org,actor,key,cohort_id,*,preview_id=None):
        with self.database.transaction() as db:
            self.writable(db);generation=require_actor(db,org,actor,'operator')['generation'];now=self.now()
            c,summary,outcomes,reports,events,size,final=self.state(db,org,cohort_id);inputs={'cohort_id':cohort_id}
            if preview_id is not None:inputs['preview_id']=preview_id
            if not self.current(db,org,cohort_id,reports,final,now):raise Conflict('Stored evidence is after the current clock; inspect history instead')
            old=self.command(db,org,actor,'finalize',key,inputs)
            if old:return self.historical_finalization(c,old,summary['reconciliation'])
            if preview_id is not None:
                self.require_context(db,org,cohort_id)
                self.expect_preview(db,org,'finalize',self.final_evidence(c,outcomes,reports,summary),self.context(db,org,cohort_id),preview_id)
            if final:
                observed=self.finish(db,org,actor,'finalize',key,inputs,final['payload'],generation,max(now,c['window_end']))
                return self.historical_finalization(c,observed,summary['reconciliation'])
            if now<c['window_end'] or any(p['at']>now for p in reports) or not summary['coverage_complete']:raise Conflict('Every original assignment, including holdouts, needs an explicit outcome and a complete final snapshot after maturity')
            groups=external_final_counts(c,outcomes)
            value={'kind':'external_cohort_finalized','cohort_id':cohort_id,'finalized_at':now,'actor':actor,'actor_generation':generation,'data_class':c['data_class'],
                'metric':c['metric'],'groups':groups,'comparisons':external_comparisons(c,groups),'reconciliation':summary['reconciliation'],
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
            status='observing'
            if not current:status='historical_evidence_after_current_clock'
            elif s['reconciliation']['excluded_diagnostics']:status='needs_reconciliation'
            elif frozen:status='finalized'
            elif now>=c['window_end']:status='ready_to_finalize' if s['coverage_complete'] else 'awaiting_complete_outcomes'
            return {'cohort':c,'company_context':self.context(db,org,cohort_id),'current':current,'status':status,
                'as_of':now,'enrolled':len(c['assignments']),**s,'reports':[p['receipt'] for p in reports],
                'posterior_groups':final['payload']['groups'] if frozen and current else [],'comparisons':external_comparison_view(c,final['payload']['comparisons']) if frozen and current else [],
                'finalization':self.historical_finalization(c,final['payload'],s['reconciliation'],current=current) if frozen else None,'authority':'OBSERVATIONS_ONLY_NO_SEND_OR_APPROVAL',
                'limitations':['External records are operator-attested, not independently provider-verified.',
                    'Opens, clicks and raw replies are diagnostics, not qualified outcomes.','Missing outcomes remain unknown.',
                    'Repeated business cohorts and finalized corrections are unsupported.','No synthetic memory, live sending or model training is changed.']}
    def snapshot(self,org,cohort_id,report_id):
        with self.database.connect() as db:
            db.execute('BEGIN');cohort=self.load(db,org,cohort_id)
            payload,_,issues,_=self.saved_report(db,org,cohort,record_key('report',cohort_id,report_id))
            return payload|{'observation':'HISTORICAL_RECEIPT_NO_CURRENT_AUTHORITY','reconciliation':external_reconciliation(issues)}
    def receipt(self,org,actor,operation,request_id):
        if operation not in {'register','import','finalize'}:raise ValueError('Use an installed external operation')
        for v in (org,actor,request_id):external_text(v)
        with self.database.connect() as db:
            value=self.read(db,org,record_key('command',actor,operation,request_id),'command')
            if value is None:raise NotFound('External command receipt unavailable')
            return value['payload']['receipt']|{'observation':'HISTORICAL_RECEIPT_NO_CURRENT_AUTHORITY'}

    def identity(self):
        with self.database.connect() as db:return self.store_id(db)

    @staticmethod
    def store_id(db):
        row=db.execute('SELECT id FROM application_store_identity WHERE singleton=1').fetchone()
        if row is None:raise Conflict('Original application store identity is unavailable')
        return row[0]

    def context_selection(self,db,org,selection,*,check_time=True):
        if (type(selection) is not dict or set(selection)!={'brief_id','brief_revision'}
                or type(selection['brief_revision']) is not int or selection['brief_revision']<1):
            raise ValueError('Select one exact saved brief revision')
        external_text(selection['brief_id'])
        def snapshot(kind,identity,revision):
            row=db.execute('SELECT payload FROM intake_'+kind+'_revisions WHERE organization=? AND id=? AND revision=?',
                (org,identity,revision)).fetchone()
            if row is None:raise NotFound('Saved company or brief revision unavailable in this organization')
            value=json.loads(row[0])
            if (value.get('schema')!='intake-'+kind+'-revision/v1' or value.get('organization')!=org
                    or value.get('id')!=identity or value.get('revision')!=revision):
                raise Conflict('Saved intake identity differs from its source')
            receipt=db.execute('SELECT receipt FROM intake_requests WHERE organization=? AND request_id=?',
                (org,value['request_id'])).fetchone()
            if receipt is None or json.loads(receipt[0]).get('snapshot')!=value:
                raise Conflict('Saved intake lacks its original atomic receipt')
            if check_time and value['saved_at']>self.now():raise Conflict('Saved intake is after the current clock')
            return value
        brief=snapshot('brief',selection['brief_id'],selection['brief_revision'])
        company=snapshot('company',brief['draft']['company_id'],brief['draft']['company_revision'])
        return {'schema':'outcome-company-context/v1','company':company,'brief':brief,
            'authority':'USER_SUPPLIED_CONTEXT_NOT_CAMPAIGN_APPROVAL'}

    def context(self,db,org,cohort_id):
        row=self.read(db,org,record_key('context',cohort_id),'company_context')
        registration=self.read(db,org,record_key('cohort',cohort_id),'registration')
        expected=registration['payload'].get('company_context_sha256') if registration else None
        if row is None:
            if expected is not None:raise Conflict('Original company binding is missing')
            return None
        if expected!=digest(row['payload']['context']):raise Conflict('Original company binding differs from registration')
        self.audited(db,org,cohort_id,row)
        context=row['payload']['context'];brief=context['brief']
        expected=self.context_selection(db,org,{'brief_id':brief['id'],'brief_revision':brief['revision']},check_time=False)
        if row['payload']!={'cohort_id':cohort_id,'context':expected}:raise Conflict('Original company binding changed')
        return context

    def require_context(self,db,org,cohort_id):
        if self.context(db,org,cohort_id) is None:
            raise Conflict('Unassociated historical cohorts are inspection only in the browser')

    def preview_identity(self,db,org,operation,payload,context):
        return 'outcomes_preview_'+digest({'schema':'outcomes-preview/v1','store_id':self.store_id(db),
            'organization':org,'operation':operation,'payload':payload,'company_context':context})

    def expect_preview(self,db,org,operation,payload,context,identity):
        if identity!=self.preview_identity(db,org,operation,payload,context):
            raise Conflict('Displayed evidence changed; review a fresh preview before submitting')

    @staticmethod
    def final_evidence(cohort,outcomes,reports,summary):
        return {'policy':'external-outcomes-browser/v1','cohort':cohort,'outcomes':outcomes,'reports':reports,
            'reconciliation':summary['reconciliation']}

    def preview(self,org,operation,payload=None,selection=None,cohort_id=None):
        with self.database.connect() as db:
            db.execute('BEGIN');now=self.now()
            if operation=='register':
                value=external_registration(payload,org,now);context=self.context_selection(db,org,selection)
                return {'preview_id':self.preview_identity(db,org,operation,value,context),
                    'operation':operation,'company_context':context,'manifest':value,'writable':not(self.read_only or self.database.inspection_only or verified_required(db))}
            if operation not in {'import','finalize'}:raise ValueError('Use an installed outcome preview')
            c,s,outcomes,reports,events,size,final=self.state(db,org,cohort_id)
            context=self.context(db,org,cohort_id)
            current=self.current(db,org,cohort_id,reports,final,now)
            if operation=='import':
                value,rows=external_report(payload,c,now)
                details={'report':value,'events':len(rows),'cohort':c}
            else:
                value=self.final_evidence(c,outcomes,reports,s)
                groups=external_final_counts(c,outcomes) if s['coverage_complete'] and current else []
                details={'cohort':c,'summary':s,'posterior_groups':groups,
                    'comparisons':external_comparisons(c,groups) if groups else [],
                    'eligible':now>=c['window_end'] and s['coverage_complete'] and final is None
                        and self.current(db,org,cohort_id,reports,final,now)}
            return {'preview_id':self.preview_identity(db,org,operation,value,context),'operation':operation,
                'company_context':context,'writable':context is not None and current and final is None and not(self.read_only or self.database.inspection_only or verified_required(db)),**details}

    def listing(self,org,company_id='',after_id='',limit=25):
        external_text(org)
        if type(company_id) is not str or type(after_id) is not str or type(limit) is not int or not 1<=limit<=50:
            raise ValueError('Use a bounded company cohort page')
        with self.database.connect() as db:
            db.execute('BEGIN')
            rows=db.execute("SELECT receipt FROM learning_commands WHERE organization=? AND json_extract(receipt,'$.schema')='external-learning-record/v1' "
                "AND json_extract(receipt,'$.kind')='registration' AND json_extract(receipt,'$.payload.cohort.id')>? "
                "AND (?='' OR EXISTS(SELECT 1 FROM learning_commands b WHERE b.organization=? "
                "AND json_extract(b.receipt,'$.kind')='company_context' "
                "AND json_extract(b.receipt,'$.payload.cohort_id')=json_extract(learning_commands.receipt,'$.payload.cohort.id') "
                "AND json_extract(b.receipt,'$.payload.context.company.id')=?)) "
                "ORDER BY json_extract(receipt,'$.payload.cohort.id') LIMIT ?",(org,after_id,company_id,org,company_id,limit+1)).fetchall()
            items=[]
            for row in rows[:limit]:
                value=json.loads(row[0]);c=self.load(db,org,value['payload']['cohort']['id']);context=self.context(db,org,c['id'])
                items.append({'id':c['id'],'campaign_id':c['campaign_id'],'channel':c['channel'],'data_class':c['data_class'],
                    'company_context':context})
            return {'items':items,'next_after':items[-1]['id'] if len(rows)>limit else None}

    def not_committed(self,org,actor,operation,key):
        if operation not in {'register','import','finalize'}:return False
        for value in (org,actor,key):external_text(value)
        with self.database.transaction() as db:
            self.writable(db)
            if self.read(db,org,record_key('command',actor,operation,key),'command'):return False
            identity=record_key('rejected',actor,operation,key)
            if self.read(db,org,identity,'rejected') is None:self.insert(db,org,identity,'rejected',{'operation':operation,'actor':actor,'request_id':key})
            return True
