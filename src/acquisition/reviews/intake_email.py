"""Purpose-specific exact email review. Approval authorizes a synthetic export only."""
from acquisition.contracts import canonical,digest
from .domain import text,timestamp
from .ports import IntakeEmailReviewStore

EMAIL_EXPORT_PURPOSE='synthetic_intake_email_export/v1'


def intake_email_subject(batch,basis):
    payload={'schema':'intake-email-subject/v1','organization':batch['organization'],
        'batch_id':batch['id'],'purpose':EMAIL_EXPORT_PURPOSE,'content_hash':digest(batch),'basis':basis}
    return payload|{'id':'intake_email_subject_'+digest(payload)}


def intake_email_decision(subject,actor,generation,decision,reason,now,expires,request_id):
    if decision not in {'approve','reject'}:raise ValueError('Choose approve or reject')
    text(reason,1000);timestamp(now);timestamp(expires)
    if not now<expires<=now+86400:raise ValueError('Bound email export review to one day')
    p={'schema':'intake-email-decision/v1','organization':subject['organization'],'batch_id':subject['batch_id'],
       'subject_id':subject['id'],'purpose':EMAIL_EXPORT_PURPOSE,'actor':actor,'actor_generation':generation,
       'request_id':request_id,'decision':decision,'reason':reason,'at':now,'expires_at':expires,'live_send_authority':'none'}
    return p|{'id':'intake_email_approval_'+digest(p)}


def intake_email_export(batch,subject,approval):
    if (approval['purpose']!=EMAIL_EXPORT_PURPOSE or approval['subject_id']!=subject['id']
            or approval['batch_id']!=batch['id'] or approval['decision']!='approve'):
        raise ValueError('Export must bind this exact reviewed email batch')
    return {'schema':'reviewed-intake-email-export/v1','mode':'SYNTHETIC_ONLY','purpose':EMAIL_EXPORT_PURPOSE,
        'subject_id':subject['id'],'batch_id':batch['id'],'approval':approval,'company_source_review':batch['binding'],
        'requirements':batch['binding']['requirements'],'emails':batch['content']['rows'],
        'product_evidence':batch['content']['context']['product_facts'],
        'recipient_permission_evidence':batch['contacts'],
        'limitations':['Fictional recipients and sender. Do not send.','Contacts are not matched to the requested audience.',
                      'Fixed authored framing, no live model or independent fact verification.',
                      'Approval authorizes this exact synthetic export only.'], 'live_send_authority':'none'}


class IntakeEmailReviews:
    def __init__(self,store: IntakeEmailReviewStore):self.store=store
    def view(self,organization,request_id):return self.store.view(organization,request_id)
    def decide(self,organization,actor,key,request_id,subject_id,decision,reason,ttl_seconds=86400):
        return self.store.decide(organization,actor,key,request_id,subject_id,decision,reason,ttl_seconds)
    def revoke(self,organization,actor,key,request_id,approval_id,reason):
        return self.store.revoke(organization,actor,key,request_id,approval_id,reason)
    def export(self,organization,actor,key,request_id,subject_id,approval_id):
        return self.store.export(organization,actor,key,request_id,subject_id,approval_id)
    def not_committed(self,organization,actor,op,key):return self.store.not_committed(organization,actor,op,key)
    def receipt(self,organization,actor,op,key):return self.store.receipt(organization,actor,op,key)
    def download(self,organization,actor,key,subject_id):return self.store.download(organization,actor,key,subject_id)
