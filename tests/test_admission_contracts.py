"""Admission values bind exact inputs; they do not verify or grant authority."""

import json
import unittest
from dataclasses import replace

from acquisition.contracts import Conflict, canonical
from acquisition.conversations import (
    ADMISSION_SCHEMA, AdmissionIntent, AdmissionReceipt, ExecutionOwnership,
)
from acquisition.reasoning import ModelConfig
from acquisition.runtime import TaskSpec


def intent(**changes):
    values=dict(organization='campaign-org', request_id='prepare-1',
                workflow_version='conversation-model-mail/v3',
                ownership=ExecutionOwnership('conversation','conversation-org','chat-1',1),
                source_id='proposal-1', source_fingerprint='a'*64, context_fingerprint='b'*64,
                consent_id='consent-1', model_config=ModelConfig('test/model'))
    values.update(changes)
    return AdmissionIntent.from_tasks(tasks=[TaskSpec('creative.generate_conversation.v3',
        {'snapshot_id':'audience-1','context_ids':['context-1']})],**values)


class AdmissionContractTests(unittest.TestCase):
    def test_ownership_is_explicit_and_revision_does_not_reset_account(self):
        owner=ExecutionOwnership('conversation','org','chat',1)
        self.assertEqual(owner.account_key,replace(owner,revision=2).account_key)
        self.assertNotEqual(owner.account_key,replace(owner,scope_id='another-chat').account_key)
        self.assertNotEqual(owner.account_key,replace(owner,organization='another-org').account_key)
        standalone=ExecutionOwnership('standalone','org','root-admission')
        self.assertNotEqual(standalone.account_key,owner.account_key)
        for changes in ({'ownership':None},{'ownership':{'kind':'standalone'}}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):intent(**changes)
        for kind,revision in (('unknown',None),('conversation',None),('conversation',True),
                              ('conversation',0),('standalone',1)):
            with self.subTest(kind=kind,revision=revision),self.assertRaises(ValueError):
                ExecutionOwnership(kind,'org','scope',revision)

    def test_exact_input_fingerprint_changes_without_changing_request_identity(self):
        original=intent()
        alternatives=[replace(original,workflow_version='conversation-model-mail/v4'),
            replace(original,source_id='proposal-2'),replace(original,source_fingerprint='c'*64),
            replace(original,context_fingerprint='d'*64),replace(original,parent_run_id='parent-1'),
            replace(original,consent_id='consent-2'),
            replace(original,model_config=replace(original.model_config,max_calls=2)),
            replace(original,ownership=replace(original.ownership,scope_id='chat-2')),
            replace(original,ownership=replace(original.ownership,revision=2)),
            replace(original,task_plan_json=canonical([{'capability':'other.task','inputs':{},'max_attempts':1}]))]
        for changed in alternatives:
            with self.subTest(changed=changed):
                self.assertEqual(original.id,changed.id)
                self.assertNotEqual(original.fingerprint,changed.fingerprint)
        self.assertNotEqual(original.id,replace(original,organization='other-org').id)
        self.assertNotEqual(original.id,replace(original,request_id='another-key').id)

    def test_frozen_task_inputs_survive_mutation_of_every_external_copy(self):
        inputs={'nested':{'selected':['a']}}
        tasks=[TaskSpec('test.task',inputs)]
        original=replace(intent(),task_plan_json=canonical([{'capability':'test.task','inputs':inputs,'max_attempts':3}]))
        frozen=AdmissionIntent.from_tasks(tasks=tasks,**{k:v for k,v in original.__dict__.items() if k!='task_plan_json'})
        before=frozen.fingerprint
        inputs['nested']['selected'].append('b')
        tasks.append(TaskSpec('unexpected.task',{}))
        frozen.tasks[0].inputs['nested']['selected'].append('c')
        frozen.payload()['tasks'][0]['inputs']['nested']['selected'].append('d')
        self.assertEqual(frozen.tasks[0].inputs,{'nested':{'selected':['a']}})
        self.assertEqual(frozen.fingerprint,before)

    def test_wire_round_trip_rejects_unknown_missing_and_downgraded_fields(self):
        original=intent();payload=original.payload()
        self.assertEqual(payload['schema'],ADMISSION_SCHEMA)
        self.assertEqual(AdmissionIntent.from_payload(json.loads(canonical(payload))),original)
        malformed=[payload|{'schema':'execution-admission/v0'},payload|{'extra':True},
                   {k:v for k,v in payload.items() if k!='ownership'},
                   payload|{'ownership':{'kind':'standalone','organization':'org','scope_id':'x','unexpected':True}},
                   payload|{'model_config':payload['model_config']|{'api_key':'not-a-credential-field'}}]
        for value in malformed:
            with self.subTest(value=value),self.assertRaises(ValueError):AdmissionIntent.from_payload(value)

    def test_model_settings_and_consent_are_a_pair_not_an_execution_grant(self):
        original=intent()
        for changes in ({'consent_id':None},{'model_config':None},{'model_config':{'model':'test/model'}}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):replace(original,**changes)
        deterministic=replace(original,consent_id=None,model_config=None)
        self.assertIsNone(deterministic.payload()['model_config'])
        # Shape validation cannot tell whether a capability makes paid calls.
        # The future store must resolve its registered effect requirements.
        self.assertEqual(deterministic.tasks,original.tasks)

    def test_model_config_rejects_mutable_and_other_non_string_model_ids(self):
        for model in (['test/model'],{'test/model':True},('test/model',),{'test/model'},
                      None,123,True,b'test/model'):
            with self.subTest(model=model),self.assertRaises(ValueError):ModelConfig(model=model)
        self.assertEqual(ModelConfig('vendor/model:free').model,'vendor/model:free')

    def test_admission_payload_rejects_mutable_model_id_and_valid_settings_do_not_alias(self):
        original=intent();payload=original.payload()
        payload['model_config']['model']=['test/model']
        with self.assertRaises(ValueError):AdmissionIntent.from_payload(payload)
        payload['model_config']['model']={'test/model':True}
        with self.assertRaises(ValueError):AdmissionIntent.from_payload(payload)

        payload=original.payload()
        frozen=AdmissionIntent.from_payload(payload)
        before=frozen.fingerprint
        payload['model_config']['model']='different/model'
        payload['model_config']['max_calls']=1
        frozen.payload()['model_config']['model']='another/model'
        self.assertEqual(frozen.model_config,original.model_config)
        self.assertEqual(frozen.fingerprint,before)

    def test_descendant_requires_exact_loaded_parent_account_and_original_revision(self):
        child=intent(parent_run_id='parent-1')
        parent=dict(organization=child.organization,run_id='parent-1',ownership=child.ownership)
        child.validate_parent(**parent)
        for changes in ({'organization':'other-org'},{'run_id':'other-parent'},
                        {'ownership':replace(child.ownership,scope_id='another-chat')},
                        {'ownership':replace(child.ownership,organization='another-owner-org')},
                        {'ownership':replace(child.ownership,revision=2)},
                        {'ownership':ExecutionOwnership('standalone','conversation-org','root')}):
            with self.subTest(changes=changes),self.assertRaises(Conflict):child.validate_parent(**(parent|changes))
        with self.assertRaises(Conflict):intent().validate_parent(**parent)

    def test_task_envelope_cannot_hide_extra_fields_nonfinite_values_or_unbounded_work(self):
        original=intent();task=original.payload()['tasks'][0]
        invalid=[[],[task]*21,[task|{'extra':True}],[task|{'inputs':[]}],
                 [task|{'capability':' test.task'}],[task|{'max_attempts':True}],
                 [task|{'max_attempts':6}]]
        for plan in invalid:
            with self.subTest(plan=plan),self.assertRaises(ValueError):
                replace(original,task_plan_json=canonical(plan))
        for plan in ('[] ', '[{"capability":"x","inputs":{"x":NaN},"max_attempts":1}]',
                     '[{"capability":"x","inputs":{"x":Infinity},"max_attempts":1}]',
                     ' '*1_048_577):
            with self.subTest(size=len(plan)),self.assertRaises(ValueError):replace(original,task_plan_json=plan)
        for field in ('source_fingerprint','context_fingerprint'):
            with self.subTest(field=field),self.assertRaises(ValueError):replace(original,**{field:'not-a-hash'})

    def test_receipt_scope_fingerprint_and_time_are_bounded(self):
        original=intent()
        receipt=AdmissionReceipt(original.organization,original.id,'run-1',original.fingerprint,1.0)
        for changes in ({'fingerprint':'a'*63},{'organization':''},{'created_at':float('inf')},
                        {'created_at':float('nan')},{'created_at':True},{'created_at':10**1000}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):replace(receipt,**changes)


if __name__=='__main__':unittest.main()
