"""Immutable intake email receipts in the existing intake-owned command journal."""
from dataclasses import asdict
import json
from acquisition.campaigns import evaluate_preparation_eligibility,grounding_request_from
from acquisition.contracts import Conflict,NotFound,canonical,digest
from .preparation_context import SqlitePreparationContexts
from .intake_preparation import SqliteIntakePreparation
from .admission_guard import verified_required
from .actors import require_actor


def email_key(organization,request):return 'intake-email:'+digest({'organization':organization,'request':request})
def email_slot(fingerprint):return 'intake-email-context:'+fingerprint


class SqliteIntakeEmails:
    def __init__(self,database,build,clock,*,read_only=False):
        self.database,self.build,self.clock,self.read_only=database,build,clock,read_only
    def writable(self,db):
        if self.read_only or self.database.inspection_only or verified_required(db):
            raise Conflict('This email capability is unavailable in an inspection or verified-paused store')
    @staticmethod
    def context(db,organization,key,now,*,historical=False):
        row=SqliteIntakePreparation._row(db,organization,key)
        view=SqlitePreparationContexts._view(db,row,now)
        if historical:
            c=view['context'];view['review_required']=[] if c['reviewed_at']<=now<c['review_expires_at'] else ['Input review expired or future-dated.']
        return view
    @classmethod
    def eligibility(cls,db,organization,key,now,*,historical=False):
        view=cls.context(db,organization,key,now,historical=historical)
        return evaluate_preparation_eligibility(view,now,channel='email')|{'context':view['context']}
    def preview(self,organization,key,now):
        with self.database.connect() as db:
            p=self.eligibility(db,organization,key,now)
            row=db.execute('SELECT receipt FROM intake_requests WHERE organization=? AND request_id=?',
                (organization,email_slot(p['context_fingerprint']))).fetchone()
            if row:p['original_email_request_id']=json.loads(row[0])['request_id']
            if self.read_only or self.database.inspection_only or verified_required(db):
                p['blockers'].append('Email preparation is paused in this inspection or verified-format store.')
            return {k:v for k,v in p.items() if k!='context'}
    def original(self,db,organization,key):
        row=db.execute('SELECT * FROM intake_requests WHERE organization=? AND request_id=?',(organization,email_key(organization,key))).fetchone()
        if row is None:raise NotFound('Email preparation not found in this organization')
        value=json.loads(row['receipt']);inputs=json.loads(row['inputs'])
        request=grounding_request_from(inputs['request'])
        p=self.eligibility(db,organization,request.context_request_id,value['binding']['prepared_at'],historical=True)
        expected=self.build(organization,inputs['actor'],key,request,p,value['binding']['prepared_at'])
        slot=db.execute('SELECT inputs,receipt FROM intake_requests WHERE organization=? AND request_id=?',
            (organization,email_slot(p['context_fingerprint']))).fetchone()
        if (canonical(expected)!=row['receipt'] or value['request_id']!=key or inputs['kind']!='intake_email_preparation/v1'
                or slot is None or tuple(slot)!=(row['inputs'],row['receipt'])):
            raise Conflict('Email preparation differs from its native source, original command or context binding')
        return value
    def view(self,db,organization,key,now,replayed=True):
        batch=self.original(db,organization,key)
        p=self.eligibility(db,organization,batch['binding']['context_request_id'],now)
        blockers=list(p['blockers'])
        if not batch['binding']['prepared_at']<=now<batch['binding']['expires_at']:blockers.append('Source evidence review expired or future-dated.')
        return {'request_id':key,'store_id':batch['binding']['store_id'],'batch':batch,'current':not blockers,
            'review_required':blockers,'replayed':replayed,'authority':'none','approval':'not_granted'}
    def request(self,organization,key,now):
        with self.database.connect() as db:return self.view(db,organization,key,now)
    def not_committed(self,organization,key):
        if self.read_only or self.database.inspection_only:return False
        with self.database.connect() as db:
            return db.execute('SELECT 1 FROM intake_requests WHERE organization=? AND request_id=?',(organization,email_key(organization,key))).fetchone() is None
    def prepare(self,organization,actor,key,request):
        inputs=canonical({'kind':'intake_email_preparation/v1','actor':actor,'request':asdict(request)})
        with self.database.transaction() as db:
            self.writable(db);require_actor(db,organization,actor,'operator')
            row=db.execute('SELECT inputs FROM intake_requests WHERE organization=? AND request_id=?',(organization,email_key(organization,key))).fetchone()
            if row:
                if row[0]!=inputs:raise Conflict('Email request binds different exact inputs')
                return self.view(db,organization,key,self.clock())
            now=self.clock();p=self.eligibility(db,organization,request.context_request_id,now)
            if db.execute('SELECT 1 FROM intake_requests WHERE organization=? AND request_id=?',(organization,email_slot(p['context_fingerprint']))).fetchone():
                raise Conflict('This reviewed context already has an original email preparation. Reconcile it.')
            batch=self.build(organization,actor,key,request,p,now)
            for identity in (email_key(organization,key),email_slot(p['context_fingerprint'])):
                db.execute('INSERT INTO intake_requests VALUES(?,?,?,?)',(organization,identity,inputs,canonical(batch)))
            result=self.view(db,organization,key,self.clock(),False)
            require_actor(db,organization,actor,'operator');self.writable(db)
            if not result['current']:raise Conflict('Email source review expired before commit')
            return result
