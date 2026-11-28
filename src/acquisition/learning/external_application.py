"""Read-only external evidence intake. No provider execution or synthetic-memory write."""
from acquisition.contracts import canonical
from .ports import ExternalOutcomeStore, ReportSource


class ExternalOutcomes:
    def __init__(self, store: ExternalOutcomeStore, files: ReportSource):self.store,self.files=store,files
    @staticmethod
    def bounded(payload):
        try:
            if type(payload) is not dict or len(canonical(payload).encode())>4*1024*1024:
                raise ValueError('External evidence files are bounded to four MiB')
        except (TypeError,RecursionError) as error:raise ValueError('Use bounded JSON evidence') from error
    def register(self,organization,actor,request_id,payload,**review):
        self.bounded(payload)
        try:return self.store.register(organization,actor,request_id,payload,**review)
        except (KeyError,TypeError,RecursionError) as error:raise ValueError('Malformed external registration') from error
    def ingest(self,organization,actor,request_id,cohort_id,payload,**review):
        self.bounded(payload)
        try:return self.store.ingest(organization,actor,request_id,cohort_id,payload,**review)
        except (KeyError,TypeError,RecursionError) as error:raise ValueError('Malformed external report') from error
    def register_file(self,organization,actor,request_id,path):return self.register(organization,actor,request_id,self.files.read(path))
    def ingest_file(self,organization,actor,request_id,cohort_id,path):return self.ingest(organization,actor,request_id,cohort_id,self.files.read(path))
    def finalize(self,organization,actor,request_id,cohort_id,**review):return self.store.finalize(organization,actor,request_id,cohort_id,**review)
    def view(self,organization,cohort_id):return self.store.view(organization,cohort_id)
    def snapshot(self,organization,cohort_id,report_id):return self.store.snapshot(organization,cohort_id,report_id)
    def receipt(self,organization,actor,operation,request_id):return self.store.receipt(organization,actor,operation,request_id)

    def parse_document(self,source):
        if type(source) is not str:raise ValueError('Upload JSON text, not a local file path')
        return self.files.parse(source.encode('utf-8'))
    def store_identity(self):return self.store.identity()
    def listing(self,organization,**page):return self.store.listing(organization,**page)
    def preview(self,organization,operation,**value):return self.store.preview(organization,operation,**value)
    def not_committed(self,organization,actor,operation,key):return self.store.not_committed(organization,actor,operation,key)
