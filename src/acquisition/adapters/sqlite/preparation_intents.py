"""Preparation intent and progress in the authoritative application database."""
import json
import sqlite3
from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.conversations import preparation_record, planning_intent
from acquisition.reasoning import ModelConfig
from .admissions import planning_source, planning_results
from .admission_guard import verified_required, binding
from .conversations import scoped_conversation
from .execution import require_active


class SqlitePreparationIntents:
    def __init__(self,database):self.database=database

    @staticmethod
    def decode(row,db):
        value=json.loads(row['intent'])
        if (digest(value)!=row['fingerprint'] or value['id']!=row['id'] or value['request_id']!=row['request_id'] or
                value['inputs']['conversation_id']!=row['conversation_id'] or value['inputs']['revision']!=row['revision']):
            raise Conflict('Preparation intent failed integrity checks')
        progress=json.loads(row['progress'])
        if set(progress)!={'status','detail','run_id'}:raise Conflict('Preparation progress cannot replace intent fields')
        if progress['run_id'] is not None:
            owner=binding(db,row['organization'],progress['run_id'])
            if owner is None or owner.tasks[0].inputs.get('request_id')!=value['plan_request_id'] or owner.source_id!=value['inputs']['conversation_id']:
                raise Conflict('Preparation progress refers to another planning run')
        return value|progress|{'epoch':row['epoch']}

    def request(self,organization,request_id):
        with self.database.connect() as db:
            row=db.execute('SELECT * FROM workflow_preparations WHERE organization=? AND request_id=?',(organization,request_id)).fetchone()
            return self.decode(row,db) if row else None

    def for_revision(self,organization,conversation_id,revision):
        with self.database.connect() as db:
            row=db.execute('SELECT * FROM workflow_preparations WHERE organization=? AND conversation_id=? AND revision=?',
                           (organization,conversation_id,revision)).fetchone()
            return self.decode(row,db) if row else None

    def create(self,organization,request_id,value):
        value=preparation_record(organization,request_id,value);inputs=value['inputs'];context=value['planning_context']
        with self.database.transaction() as db:
            if not verified_required(db):raise Conflict('Authoritative preparation requires verified format selection')
            old=db.execute('SELECT * FROM workflow_preparations WHERE organization=? AND request_id=?',(organization,request_id)).fetchone()
            if old:
                if old['intent']!=canonical(value):raise Conflict('Preparation already binds different frozen inputs')
                return self.decode(old,db)
            source=planning_source(db,organization,inputs['conversation_id'])
            if source['revision']!=inputs['revision']:raise Conflict('The brief changed before preparation intent committed')
            require_active(db,organization,inputs['conversation_id'],inputs['revision'])
            config=ModelConfig(**context['model_config']) if context.get('model_config') else None
            planning_intent(organization,value['plan_request_id'],source,context,planning_results(db,organization,inputs['conversation_id']),
                            fixture=inputs['fixture'],allow_model=not inputs['fixture'],config=config)
            native=db.execute('SELECT request_id FROM conversation_plans WHERE organization=? AND conversation_id=? AND revision=?',
                              (organization,inputs['conversation_id'],inputs['revision'])).fetchone()
            staged=db.execute('SELECT payload FROM admission_requests WHERE organization=? AND conversation_id=? AND revision=?',
                              (organization,inputs['conversation_id'],inputs['revision'])).fetchone()
            if ((native and native[0]!=value['plan_request_id']) or
                (staged and json.loads(staged[0])['tasks'][0]['inputs']['request_id']!=value['plan_request_id'])):
                raise Conflict('This brief already has another planning request')
            try:
                db.execute('INSERT INTO workflow_preparations VALUES(?,?,?,?,?,?,?,0,?)',
                    (organization,value['id'],request_id,inputs['conversation_id'],inputs['revision'],canonical(value),digest(value),
                     canonical({k:value[k] for k in ('status','detail','run_id')})))
            except sqlite3.IntegrityError:raise Conflict('This revision already has a preparation request') from None
            return value

    def get(self,organization,preparation_id):
        with self.database.connect() as db:
            row=db.execute('SELECT * FROM workflow_preparations WHERE organization=? AND id=?',(organization,preparation_id)).fetchone()
            if row is None:raise NotFound('Preparation not found in this organization')
            return self.decode(row,db)

    def listing(self,organization,conversation_id=None):
        with self.database.connect() as db:
            rows=db.execute('SELECT * FROM workflow_preparations WHERE organization=?'+(' AND conversation_id=?' if conversation_id else '')+' ORDER BY rowid',
                            (organization,conversation_id) if conversation_id else (organization,))
            return [self.decode(row,db) for row in rows]

    def update(self,organization,prior,status,detail,*,run_id=None):
        if status not in {'admitting','planning','selecting_audience','preparing','blocked','cancelled','stale','failed','uncertain','needs_input','needs_consent','review_ready'}:
            raise ValueError('Unsupported preparation status')
        if detail is not None and (type(detail) is not str or len(detail)>600):raise ValueError('Use bounded preparation detail')
        with self.database.transaction() as db:
            row=db.execute('SELECT * FROM workflow_preparations WHERE organization=? AND id=?',(organization,prior['id'])).fetchone()
            if row is None:raise NotFound('Preparation not found in this organization')
            current=self.decode(row,db)
            if current['epoch']!=prior['epoch']:return current
            if any(current[k]!=prior[k] for k in ('inputs','planning_context','planning_context_id','plan_request_id','request_id')):
                raise Conflict('Preparation continuation differs from its authoritative intent')
            run=run_id if run_id is not None else current['run_id']
            if run is not None:
                owner=binding(db,organization,run)
                if owner is None or owner.tasks[0].inputs.get('request_id')!=current['plan_request_id'] or owner.source_id!=current['inputs']['conversation_id']:
                    raise Conflict('Preparation run differs from its admitted planning intent')
                if current['run_id'] not in {None,run}:raise Conflict('Preparation already has its original run')
            progress={'status':status,'detail':detail,'run_id':run}
            db.execute('UPDATE workflow_preparations SET epoch=epoch+1,progress=? WHERE organization=? AND id=? AND epoch=?',
                       (canonical(progress),organization,prior['id'],prior['epoch']))
            return current|progress|{'epoch':current['epoch']+1}
