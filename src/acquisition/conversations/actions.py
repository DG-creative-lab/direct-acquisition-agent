"""Persistent action interpretation. Inspection never appends a brief amendment."""
from dataclasses import asdict
import json
from acquisition.contracts import Conflict, canonical, digest
from acquisition.runtime import TaskSpec
from .domain import ACTION_CAPABILITY, action_alias, identity, revision_number, text, validate_action
from .ports import ConversationActionStore


class ActionNotSaved(Conflict):
    pass


class ConversationActions:
    def __init__(self, store: ConversationActionStore, tasks, clock, config, preflight, assets=None):
        self.store, self.tasks, self.clock, self.config, self.preflight = store, tasks, clock, config, preflight
        self.assets=assets

    def admit(self, organization, conversation_id, request_id, expected_revision, content, allow_model_copy, context):
        for v in (organization,conversation_id,request_id):identity(v)
        revision_number(expected_revision);text(content)
        if expected_revision < 1 or type(allow_model_copy) is not bool:
            raise ValueError('Follow-up routing requires a current brief and explicit copy permission')
        inputs={'conversation_id':conversation_id,'revision':expected_revision,'content':content,'allow_model_copy':allow_model_copy}
        old=self.store.request(organization,conversation_id,request_id)
        if old:
            if old['inputs']!=inputs:raise Conflict('Action request already binds different inputs or permission')
            return old
        quick=action_alias(content)
        if not quick and len(context.get('dialogue',{}).get('clarification_exchange',[]))>4:
            raise ValueError('Clarification context limit reached. Restate the complete change in a new conversation.')
        if quick is None and self.config is None:
            raise ValueError('Configure the routing model, or use a supported inspection shortcut')
        context=json.loads(canonical(context))
        if self.assets:
            context=json.loads(canonical(self.assets(organization,context)))
        frozen={'schema':'conversation-action/v1','organization':organization,'inputs':inputs,'context':context,
                'method':'authored_alias/v1' if quick else 'model/v1','alias':quick,
                'model_config':asdict(self.config) if not quick else None,
                'run_request_id':'conversation-action:'+digest({'organization':organization,'conversation_id':conversation_id,'request_id':request_id})}
        validate_action({"action":"clarify"},frozen)
        if not quick:self.preflight(frozen)
        return self.store.admit(organization,conversation_id,request_id,frozen,self.clock())

    def reconcile(self, organization, row):
        saved=self.store.get(organization,row["id"])
        if canonical({k:v for k,v in saved.items() if k!="confirmed"})!=canonical({k:v for k,v in row.items() if k!="confirmed"}):
            raise Conflict("Routing continuation differs from its durable admission")
        if row['alias']:return None
        if self.config is None or row['model_config']!=asdict(self.config):
            raise ValueError('Restore the original routing model and limits')
        self.preflight(row)
        return self.tasks.create(organization,row['run_request_id'],[TaskSpec(ACTION_CAPABILITY,{k:v for k,v in row.items() if k!='confirmed'})],self.clock())

    def view(self, organization, row):
        run=self.tasks.find_run(organization,row['run_request_id']) if not row['alias'] else None
        state=self.tasks.inspect(organization,run) if run else None
        result=validate_action({'action':row['alias']},row) if row['alias'] else None
        status='succeeded' if result else state['run']['status'] if state else 'admitted'
        if state and state['tasks'][0]['status']=='succeeded':
            output=state['tasks'][0]['output']
            if validate_action({'action':output['kind']},row)!=output:
                raise Conflict('Saved routing result failed integrity checks')
            result=output
        return {'id':row['id'],'request_id':row['request_id'],'revision':row['inputs']['revision'],
                'content':row['inputs']['content'],'allow_model_copy':row['inputs']['allow_model_copy'],
                'method':row['method'],'status':status,'run_id':run,'result':result,
                'guidance':row['context']['agent_assets'],
                'confirmed':row.get('confirmed'),'created_at':row['created_at']}
