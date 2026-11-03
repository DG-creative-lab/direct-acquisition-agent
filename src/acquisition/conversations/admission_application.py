"""Explicit caller admission, with original-command recovery before input work."""
from dataclasses import asdict
from acquisition.contracts import Conflict, canonical, digest
from .ports import AdmissionStore


class WorkflowAdmissions:
    def __init__(self, store: AdmissionStore, clock):
        self.store,self.clock=store,clock

    def required(self):
        return self.store.required()

    def legacy_workflow(self, organization, runtime_request_id, task_factory):
        """Observe an original native plan without creating verified authority."""
        if self.store.legacy_tasks(organization,runtime_request_id) is None:return None
        return self.store.replay_legacy(organization,runtime_request_id,task_factory())

    def source_request_id(self, organization, kind, source_id, native_request_id, references):
        # Preserve native-spelled wrappers, then discover separately keyed sources.
        old=self.store.request_inputs(organization,native_request_id)
        if old and old.get('kind')==kind and old.get('references')==references:
            return native_request_id
        saved=self.store.request_for_source(organization,kind,source_id,references)
        if saved is not None:return saved
        return 'source_'+digest({'kind':kind,'source_id':source_id})

    def planning(self, organization, conversation_id, request_id, revision, *, fixture, config,
                 context_factory, frozen_context=None):
        legacy=self.store.legacy_planning(organization,conversation_id,request_id,revision,
            fixture=fixture,config=config,frozen_context=frozen_context)
        if legacy is not None:return legacy
        admission_key=self.store.request_for_planning(organization,conversation_id,request_id)
        if admission_key is None:
            admission_key='planning_'+digest({'organization':organization,'conversation_id':conversation_id,'request_id':request_id})
        old=self.store.request_inputs(organization,admission_key)
        native_request=request_id if old is None or 'native_request_id' in old else None
        if old:
            expected={'conversation_id':conversation_id,'revision':revision,'fixture':fixture,
                      'allow_model':not fixture,'model_config':asdict(config) if config else None}
            if native_request is not None:expected['native_request_id']=native_request
            if {k:v for k,v in old.items() if k!='context'}!=expected:
                raise Conflict('Planning command differs from its saved admission')
            if frozen_context is not None and canonical(frozen_context)!=canonical(old['context']):
                raise Conflict('Planning continuation differs from its original context')
            context=old['context']
        else:
            context=frozen_context if frozen_context is not None else context_factory()
        intent=self.store.request_planning(organization,conversation_id,admission_key,revision,context,
            fixture=fixture,allow_model=not fixture,model_config=config,native_request_id=native_request)
        return self.store.admit(intent,self.clock()).run_id

    def workflow(self, organization, request_id, kind, entrypoint, references, *, allow_model, config):
        # Canonicalize before any callback can mutate caller-owned values.
        command=canonical(entrypoint)
        if type(allow_model) is not bool:raise ValueError('Use an explicit model-generation decision')
        saved_entrypoint=entrypoint
        old=self.store.request_inputs(organization,request_id)
        if old:
            if (old.get('kind')!=kind or old.get('allow_model')!=allow_model or
                    old.get('model_config')!=(asdict(config) if config else None)):
                raise Conflict('Execution command differs from its saved inputs or model permission')
            refs=old['references']
            if 'entrypoint' in old:
                if canonical(old['entrypoint'])!=command:
                    raise Conflict('Execution command differs from its saved entrypoint')
            else:
                # Only native source commands are fully described by references.
                key={'routing':'action_id','copy-revision':'revision_request_id'}.get(kind)
                if (key is None or set(refs)!={key} or canonical(refs)!=command or
                        canonical(references())!=command):
                    raise Conflict('Older admission does not prove this exact native command')
                saved_entrypoint=None  # Replay the original field-absent envelope.

        else:
            refs=references()
        intent=self.store.request_workflow(organization,request_id,kind,refs,allow_model=allow_model,
            model_config=config,entrypoint=saved_entrypoint)
        return self.store.admit(intent,self.clock()).run_id
