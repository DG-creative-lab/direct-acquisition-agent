"""Current authority at review/export, using the existing review command journal."""
import json
import hashlib
from acquisition.audiences import contact_snapshot_from
from acquisition.campaigns import campaign_profile_from,evaluate_contact_eligibility,intake_identity
from acquisition.contracts import Conflict,NotFound,canonical,digest
from acquisition.reviews import intake_email_subject,intake_email_decision,intake_email_export,EMAIL_EXPORT_PURPOSE,text
from .actors import require_actor
from .admission_guard import verified_required


class SqliteIntakeEmailReviews:
    def __init__(self,preparations,clock,*,local_roles=None):
        self.preparations,self.database,self.clock=preparations,preparations.database,clock
        self.local_roles=local_roles
    def initialize_local_defaults(self,org):
        if self.local_roles is None:return
        with self.database.connect() as db:
            self.preparations.writable(db)
            if db.execute("SELECT 1 FROM intake_requests WHERE organization=? AND json_extract(inputs,'$.kind')=? LIMIT 1",
                          (org,'intake_email_preparation/v1')).fetchone():return
        for actor,role in (('local-operator','operator'),('local-reviewer','reviewer')):
            self.local_roles.initialize_actor(org,actor,(role,))
    @staticmethod
    def journal_key(org,actor,op,key):
        for v in (org,actor,key):intake_identity(v)
        return 'intake-email-review:'+digest({'organization':org,'actor':actor,'operation':op,'request':key})
    def read_command(self,db,org,actor,op,key):
        row=db.execute('SELECT request_hash,receipt FROM review_commands WHERE organization=? AND request_id=?',
            (org,self.journal_key(org,actor,op,key))).fetchone()
        if row is None:return None
        r=json.loads(row['receipt'])
        if (r['request_id']!=key or r['actor']!=actor or r['kind']!='intake_email_'+op or r['purpose']!=EMAIL_EXPORT_PURPOSE or digest(r['inputs'])!=row['request_hash']
                or r['id']!='intake_email_command_'+digest({k:v for k,v in r.items() if k!='id'})):
            raise Conflict('Email review command integrity failed')
        return r
    def command(self,db,org,actor,op,key,inputs,value):
        old=self.read_command(db,org,actor,op,key)
        if old:
            if canonical(old['inputs'])!=canonical(inputs):raise Conflict('Email review command binds different exact inputs')
            return old
        p={'kind':'intake_email_'+op,'purpose':EMAIL_EXPORT_PURPOSE,'request_id':key,'actor':actor,'inputs':inputs,'value':value}
        r=p|{'id':'intake_email_command_'+digest(p)}
        db.execute('INSERT INTO review_commands VALUES(?,?,?,?)',
            (org,self.journal_key(org,actor,op,key),digest(inputs),canonical(r)))
        return r
    def records(self,db,org,op,batch_id):
        rows=db.execute("SELECT receipt,request_hash,request_id FROM review_commands WHERE organization=? AND json_extract(receipt,'$.kind')=? "
            "AND json_extract(receipt,'$.value.batch_id')=? ORDER BY rowid",(org,'intake_email_'+op,batch_id)).fetchall()
        result=[]
        for row in rows:
            r=json.loads(row[0])
            if (self.journal_key(org,r['actor'],op,r['request_id'])!=row[2] or r['purpose']!=EMAIL_EXPORT_PURPOSE or digest(r['inputs'])!=row[1]
                    or r['id']!='intake_email_command_'+digest({k:v for k,v in r.items() if k!='id'})):
                raise Conflict('Email review history integrity failed')
            result.append(r['value'])
        return result
    def basis(self,db,org):
        result={}
        for table in ('contact_objections','engagement_stops','review_suppressions','review_authorities','review_actors'):
            result[table]=[dict(r) for r in db.execute('SELECT * FROM '+table+' WHERE organization=? ORDER BY rowid',(org,))]
        return result
    def ready(self,db,org,key):
        now=self.clock();view=self.preparations.view(db,org,key,now)
        batch=view['batch'];basis=self.basis(db,org);blockers=list(view['review_required'])
        if self.preparations.read_only or self.database.inspection_only or verified_required(db):
            blockers.append('This email review/export capability is inspection-only or paused.')
        snapshot=contact_snapshot_from(batch['contacts']);profile=campaign_profile_from(batch['profile'])
        objections=set()
        for row in basis['contact_objections']:
            v=json.loads(row['payload'])
            if row['id']!='objection_'+digest(v) or v['organization']!=org:raise Conflict('Objection integrity failed')
            if v['channel'] in {'email','all'} and v['purpose'] in {'acquisition','all'}:objections.add(v['contact_id'])
        suppressed={r['business_id'] for r in basis['review_suppressions']}
        for row in basis['engagement_stops']:
            if row['simulation_id'] is None:
                for a,p in zip(snapshot.accounts,snapshot.contacts,strict=True):
                    if row['subject_id'] in {a.ref.id,a.business_id,a.experiment_unit,p.ref.id}:objections.add(p.ref.id)
        report=evaluate_contact_eligibility(snapshot,profile,'email','acquisition',now,objections,suppressed,set(),set(),set())
        if not report['ready_for_proposal'] or len(report['eligible'])!=len(snapshot.contacts):
            blockers.append('Every intended email recipient must retain current permission, pressure and stop eligibility.')
        for actor in ('local-operator','local-reviewer'):
            # Native callers may use other registered actors. Their generations
            # are still included in the complete scoped basis.
            row=db.execute('SELECT enabled FROM review_actors WHERE organization=? AND id=?',(org,actor)).fetchone()
            if row and not row[0]:blockers.append('A configured local email actor is disabled.')
        subject=intake_email_subject(batch,basis)
        return view,batch,subject,blockers,report
    def authorize(self,db,org,key,subject_id,approval_id):
        view,batch,subject,blockers,report=self.ready(db,org,key)
        if blockers or subject['id']!=subject_id:raise Conflict('Email subject, sources or recipient eligibility changed. Review again.')
        decisions=self.records(db,org,'decision',batch['id'])
        if not decisions or decisions[-1]['id']!=approval_id:raise Conflict('Email approval is missing or superseded')
        approval=decisions[-1]
        if any(v['approval_id']==approval_id for v in self.records(db,org,'revocation',batch['id'])):
            raise Conflict('Email export approval was revoked')
        actor=require_actor(db,org,approval['actor'],'reviewer');now=self.clock()
        if (approval['purpose']!=EMAIL_EXPORT_PURPOSE or approval['subject_id']!=subject_id or approval['decision']!='approve'
                or actor['generation']!=approval['actor_generation'] or not approval['at']<=now<approval['expires_at']):
            raise Conflict('Email approval is expired or no longer authorized')
        if self.basis(db,org)!=subject['basis']:raise Conflict('Email review basis changed before commit')
        return batch,subject,approval
    def view(self,org,key):
        with self.database.connect() as db:
            db.execute('BEGIN')
            view,batch,subject,blockers,report=self.ready(db,org,key)
            decisions=self.records(db,org,'decision',batch['id']);approval=decisions[-1] if decisions else None;valid=False
            if approval:
                try:self.authorize(db,org,key,subject['id'],approval['id']);valid=True
                except (ValueError,NotFound):pass
            return {'request_id':key,'store_id':view['store_id'],'batch':batch,'subject':subject,'approval':approval,
                'approval_valid':valid,'review_ready':not blockers,'review_required':blockers,'recipient_readiness':report,
                'purpose':EMAIL_EXPORT_PURPOSE,'live_send_authority':'none'}
    def decide(self,org,actor,key,request_id,subject_id,decision,reason,ttl_seconds):
        if type(ttl_seconds) is not int or not 1<=ttl_seconds<=86400:raise ValueError('Use at most one day of export approval')
        inputs={'request_id':request_id,'subject_id':subject_id,'decision':decision,'reason':reason,'ttl_seconds':ttl_seconds}
        with self.database.transaction() as db:
            self.preparations.writable(db);reviewer=require_actor(db,org,actor,'reviewer')
            old=self.read_command(db,org,actor,'decision',key)
            if old:
                if old['inputs']!=inputs:raise Conflict('Review request binds different exact inputs')
                return old|{'observation':'historical_receipt'}
            view,batch,subject,blockers,_=self.ready(db,org,request_id)
            if blockers or subject['id']!=subject_id:raise Conflict('Review the exact current email batch before deciding')
            now=self.clock();expires=min(now+ttl_seconds,batch['binding']['expires_at'])
            approval=intake_email_decision(subject,actor,reviewer['generation'],decision,reason,now,expires,key)
            receipt=self.command(db,org,actor,'decision',key,inputs,approval)
            # Recheck native sources, actor and authority after inserting the decision.
            _,_,fresh,blocks,_=self.ready(db,org,request_id)
            current=require_actor(db,org,actor,'reviewer')
            if (blocks or fresh!=subject or current['generation']!=reviewer['generation']
                    or not now<=self.clock()<expires):raise Conflict('Email authority changed before review commit')
            self.preparations.writable(db);return receipt
    def revoke(self,org,actor,key,request_id,approval_id,reason):
        text(reason,1000);inputs={'request_id':request_id,'approval_id':approval_id,'reason':reason}
        with self.database.transaction() as db:
            self.preparations.writable(db);require_actor(db,org,actor,'reviewer')
            batch=self.preparations.original(db,org,request_id)
            if not any(v['id']==approval_id for v in self.records(db,org,'decision',batch['id'])):
                raise NotFound('Email approval does not belong to this batch')
            return self.command(db,org,actor,'revocation',key,inputs,{'batch_id':batch['id'],'approval_id':approval_id,
                'actor':actor,'reason':reason,'at':self.clock(),'purpose':EMAIL_EXPORT_PURPOSE})
    def export(self,org,actor,key,request_id,subject_id,approval_id):
        inputs={'request_id':request_id,'subject_id':subject_id,'approval_id':approval_id}
        with self.database.transaction() as db:
            self.preparations.writable(db);require_actor(db,org,actor,'operator')
            batch,subject,approval=self.authorize(db,org,request_id,subject_id,approval_id)
            content=canonical(intake_email_export(batch,subject,approval))+'\n'
            value={'batch_id':batch['id'],'subject_id':subject_id,'approval_id':approval_id,'content_sha256':hashlib.sha256(content.encode()).hexdigest(),
                   'content':content,'purpose':EMAIL_EXPORT_PURPOSE,'live_send_authority':'none'}
            receipt=self.command(db,org,actor,'export',key,inputs,value)
            self.authorize(db,org,request_id,subject_id,approval_id);require_actor(db,org,actor,'operator')
            return {k:v for k,v in receipt.items() if k!='value'}|{'value':{k:v for k,v in receipt['value'].items() if k!='content'}}
    def not_committed(self,org,actor,op,key):
        if self.preparations.read_only or self.database.inspection_only:return False
        with self.database.connect() as db:return self.read_command(db,org,actor,op,key) is None
    def receipt(self,org,actor,op,key):
        if op not in {'decision','revocation','export'}:raise ValueError('Use an installed email review operation')
        with self.database.connect() as db:
            receipt=self.read_command(db,org,actor,op,key)
            if receipt is None:raise NotFound('Email review command not found')
            return {k:v for k,v in receipt.items() if k!='value'}|{'value':{k:v for k,v in receipt['value'].items() if k!='content'},'observation':'historical_receipt'}
    def download(self,org,actor,key,subject_id):
        with self.database.transaction() as db:
            self.preparations.writable(db);require_actor(db,org,actor,'operator')
            receipt=self.read_command(db,org,actor,'export',key)
            if receipt is None:raise NotFound('Email export receipt unavailable')
            inputs=receipt['inputs']
            if inputs['subject_id']!=subject_id:raise Conflict('Download must bind the exact displayed email subject')
            batch,subject,approval=self.authorize(db,org,inputs['request_id'],subject_id,inputs['approval_id'])
            content=canonical(intake_email_export(batch,subject,approval))+'\n'
            if receipt['value']['content']!=content:raise Conflict('Saved export differs from its exact current batch')
            self.authorize(db,org,inputs['request_id'],subject_id,inputs['approval_id']);return content.encode()
