"""Local recorded outcomes. Browser identity never supplies organization or authority."""
from acquisition.contracts import Conflict, digest
from acquisition.learning import ExternalOutcomes


class WorkspaceOutcomes:
    organization = 'local-conversations'
    actor = 'local-operator'

    def __init__(self, application: ExternalOutcomes):self.application=application
    def store_identity(self):return self.application.store_identity()
    def listing(self,**page):return self.application.listing(self.organization,**page)
    def view(self,cohort_id):return self.application.view(self.organization,cohort_id)
    def snapshot(self,cohort_id,report_id):
        value=self.application.snapshot(self.organization,cohort_id,report_id)
        return value|{'snapshot_id':digest(value)}
    def receipt(self,operation,key):
        return self.envelope(operation,key,self.application.receipt(self.organization,self.actor,operation,key))
    def envelope(self,operation,key,result):
        return {'operation':operation,'request_id':key,'store_id':self.store_identity(),'result':result}
    @staticmethod
    def fields(payload,expected):
        if type(payload) is not dict or set(payload)!=expected:raise ValueError('Use the exact recorded outcome fields')
    def preview(self,operation,payload):
        if operation=='register':
            self.fields(payload,{'source','selection'})
            return self.application.preview(self.organization,operation,
                payload=self.application.parse_document(payload['source']),selection=payload['selection'])
        if operation=='import':
            self.fields(payload,{'source','cohort_id'})
            return self.application.preview(self.organization,operation,
                payload=self.application.parse_document(payload['source']),cohort_id=payload['cohort_id'])
        self.fields(payload,{'cohort_id'})
        return self.application.preview(self.organization,operation,cohort_id=payload['cohort_id'])
    def command(self,operation,payload):
        expected={'request_id','preview_id'}|({'source','selection'} if operation=='register' else
            {'source','cohort_id'} if operation=='import' else {'cohort_id'})
        self.fields(payload,expected)
        if type(payload['preview_id']) is not str or not payload['preview_id']:raise ValueError('Review the displayed evidence first')
        key=payload['request_id'];review={'preview_id':payload['preview_id']}
        if operation=='register':
            result=self.application.register(self.organization,self.actor,key,self.application.parse_document(payload['source']),
                selection=payload['selection'],**review)
        elif operation=='import':
            result=self.application.ingest(self.organization,self.actor,key,payload['cohort_id'],self.application.parse_document(payload['source']),**review)
        elif operation=='finalize':
            result=self.application.finalize(self.organization,self.actor,key,payload['cohort_id'],**review)
        else:raise ValueError('Use an installed recorded outcome operation')
        return self.envelope(operation,key,result)
    def not_committed(self,operation,key):
        return self.application.not_committed(self.organization,self.actor,operation,key)
