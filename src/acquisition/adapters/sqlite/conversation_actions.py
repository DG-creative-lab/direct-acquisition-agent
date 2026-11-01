"""Immutable routing admissions and atomic, exact-input brief confirmations."""
import json
from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.conversations import ACTION_CAPABILITY, identity, revision_number, text, validate_action
from .conversations import scoped_conversation, append_message
from .tasks import finite_time


class SqliteConversationActions:
    def __init__(self,database,clock):self.database,self.clock=database,clock

    @staticmethod
    def decode(row):
        return json.loads(row['payload']) | {'confirmed':json.loads(row['confirmed']) if row['confirmed'] else None}

    def request(self,organization,conversation_id,request_id):
        with self.database.connect() as db:
            row=db.execute('SELECT * FROM conversation_actions WHERE organization=? AND conversation_id=? AND request_id=?',
                           (organization,conversation_id,request_id)).fetchone()
            return self.decode(row) if row else None

    def get(self,organization,action_id):
        with self.database.connect() as db:
            row=db.execute('SELECT * FROM conversation_actions WHERE organization=? AND id=?',(organization,action_id)).fetchone()
            if row is None:raise NotFound('Conversation action not found in this organization')
            return self.decode(row)

    def listing(self,organization,conversation_id=None):
        identity(organization)
        with self.database.connect() as db:
            return [self.decode(r) for r in db.execute('SELECT * FROM conversation_actions WHERE organization=?'+
                (' AND conversation_id=?' if conversation_id else '')+' ORDER BY rowid',
                (organization,conversation_id) if conversation_id else (organization,))]

    def admit(self,organization,conversation_id,request_id,frozen,now):
        finite_time(now)
        payload=canonical(frozen)
        if len(payload.encode())>64000:raise ValueError('Conversation action context limit exceeded')
        with self.database.transaction() as db:
            now=self.clock();finite_time(now)
            conversation=scoped_conversation(db,organization,conversation_id)
            old=db.execute('SELECT * FROM conversation_actions WHERE organization=? AND conversation_id=? AND request_id=?',
                           (organization,conversation_id,request_id)).fetchone()
            if old:
                value=self.decode(old)
                if value['inputs']!=frozen['inputs']:raise Conflict('Action request already binds different inputs or permission')
                return value
            if conversation['revision']!=frozen['inputs']['revision']:
                raise Conflict('The brief changed before this action was saved')
            target=frozen['context']['target']
            if target['conversation_id']!=conversation_id or target['revision']!=conversation['revision']:
                raise Conflict('Action context targets another brief')
            history=db.execute('SELECT payload FROM conversation_actions WHERE organization=? AND conversation_id=?',
                               (organization,conversation_id)).fetchall()
            values=[json.loads(r[0]) for r in history]
            if len(values)>=40 or sum(len(v['inputs']['content'].encode()) for v in values)+len(frozen['inputs']['content'].encode())>16000:
                raise ValueError('Conversation follow-up limit reached')
            if not frozen['alias'] and sum(not v['alias'] for v in values)>=12:
                raise ValueError('Conversation routing budget exhausted')
            value=frozen | {'id':'conversation_action_'+digest({'organization':organization,'conversation_id':conversation_id,'request_id':request_id})[:32],
                            'request_id':request_id,'created_at':now}
            db.execute('INSERT INTO conversation_actions VALUES(?,?,?,?,?,?,NULL,?)',
                (organization,value['id'],conversation_id,request_id,conversation['revision'],canonical(value),now))
        return value | {'confirmed':None}

    def confirm(self,organization,action_id,request_id,target_id,expected_revision,now):
        for v in (organization,action_id,request_id,target_id):identity(v)
        revision_number(expected_revision);finite_time(now)
        inputs={'action_id':action_id,'target_id':target_id,'revision':expected_revision}
        with self.database.transaction() as db:
            prior=db.execute('SELECT inputs,receipt FROM conversation_action_commands WHERE organization=? AND request_id=?',
                             (organization,request_id)).fetchone()
            if prior:
                if canonical(json.loads(prior['inputs']))!=canonical(inputs):raise Conflict('Confirmation request already binds different inputs')
                return json.loads(prior['receipt'])
            row=db.execute('SELECT * FROM conversation_actions WHERE organization=? AND id=?',(organization,action_id)).fetchone()
            if row is None:raise NotFound('Conversation action not found in this organization')
            frozen=json.loads(row['payload']);target=frozen['context']['target']
            if target['id']!=target_id or row['revision']!=expected_revision:
                raise Conflict('Confirmation differs from the displayed brief-change proposal')
            if row['confirmed']:
                receipt=json.loads(row['confirmed'])
            else:
                conversation=scoped_conversation(db,organization,row['conversation_id'])
                if conversation['revision']!=expected_revision:raise Conflict('The proposed change belongs to an older brief')
                task=db.execute('''SELECT t.output,t.inputs FROM runs r JOIN tasks t ON t.run_id=r.id
                    WHERE r.organization=? AND r.request_id=? AND r.status='succeeded' AND t.status='succeeded' AND t.capability=?''',
                    (organization,frozen['run_request_id'],ACTION_CAPABILITY)).fetchone()
                if task is None:raise Conflict('A completed amendment proposal is required')
                result=json.loads(task['output'])
                if (result.get('kind')!='amend_brief' or validate_action({'action':'amend_brief'},frozen)!=result
                        or json.loads(task['inputs'])!=frozen):
                    raise Conflict('This action grants no brief-amendment authority')
                exchange=result.get('amendment_exchange')
                if exchange:
                    self._verify_exchange(db,organization,row,exchange[:-1])
                now=self.clock();finite_time(now)
                carried=[]
                for index,entry in enumerate(exchange[:-1] if exchange else []):
                    message=append_message(db,organization,row['conversation_id'],action_id+':context:'+str(index),
                                           expected_revision,entry['content'],now)
                    carried.append(message)
                    expected_revision=message['revision']
                message=append_message(db,organization,row['conversation_id'],action_id+':amend',expected_revision,
                                       frozen['inputs']['content'],now)
                receipt={'action_id':action_id,'conversation_id':row['conversation_id'],'message_receipt':message,
                         'allow_model_copy':frozen['inputs']['allow_model_copy'],'preparation_request_id':action_id+':prepare'}
                if exchange:receipt|={'exchange':exchange,'message_receipts':carried+[message]}
                db.execute('UPDATE conversation_actions SET confirmed=? WHERE organization=? AND id=?',
                           (canonical(receipt),organization,action_id))
            db.execute('INSERT INTO conversation_action_commands VALUES(?,?,?,?)',(organization,request_id,canonical(inputs),canonical(receipt)))
        return receipt

    @staticmethod
    def _verify_exchange(db,organization,current,exchange):
        previous_sequence=None
        current_sequence=db.execute('SELECT rowid FROM conversation_actions WHERE organization=? AND id=?',
                                    (organization,current['id'])).fetchone()[0]
        for entry in exchange:
            row=db.execute('SELECT rowid AS admission_sequence,payload,confirmed FROM conversation_actions WHERE organization=? AND id=? AND conversation_id=? AND revision=?',
                (organization,entry['action_id'],current['conversation_id'],current['revision'])).fetchone()
            if row is None or row['confirmed']:raise Conflict('The displayed clarification belongs to another brief')
            if (row['admission_sequence']>=current_sequence or
                    (previous_sequence is not None and row['admission_sequence']<=previous_sequence)):
                raise Conflict('Clarification admission order differs from the displayed exchange. Request a new interpretation.')
            previous_sequence=row['admission_sequence']
            frozen=json.loads(row['payload'])
            task=db.execute('''SELECT t.output,t.inputs FROM runs r JOIN tasks t ON t.run_id=r.id
                WHERE r.organization=? AND r.request_id=? AND r.status='succeeded' AND t.status='succeeded' AND t.capability=?''',
                (organization,frozen['run_request_id'],ACTION_CAPABILITY)).fetchone()
            if task is None:raise Conflict('A completed clarification exchange is required')
            result=json.loads(task['output'])
            if (result.get('kind') not in {'clarify','amend_brief'} or validate_action({'action':result['kind']},frozen)!=result
                    or json.loads(task['inputs'])!=frozen
                    or entry!={'action_id':entry['action_id'],'content':frozen['inputs']['content'],
                               'response':{k:result[k] for k in ('id','kind','text')}}):
                raise Conflict('Clarification differs from the exact displayed exchange')
