"""Reviewed company facts compose with explicit synthetic contact permissions."""
from dataclasses import asdict
from datetime import datetime,timezone
import json

from acquisition.audiences import (AudienceTaxonomy,AudienceSegment,ContactConnection,NativeReference,
    ContactAccount,ContactPerson,PermissionObservation,ContactPressure,ContactSnapshot)
from acquisition.campaigns import EmailCampaignProfile,evaluate_contact_eligibility
from acquisition.contracts import Conflict,canonical,digest
from acquisition.creative import grounded_intake_product,render_intake_email


class IntakeEmailBuilder:
    def build(self,organization,actor,request_id,request,preview,now):
        if preview['blockers'] or request.preview_id!=preview['id']:
            raise Conflict('Reload email eligibility and resolve blockers before preparing')
        context=preview['context'];today=datetime.fromtimestamp(now,timezone.utc).date()
        taxonomy=AudienceTaxonomy('intake-email-fixture','v1',(AudienceSegment('businesses',
            'Synthetic businesses','Fictional contacts, not matched to requested audience.'),))
        product,pack=grounded_intake_product(context,request.evidence,taxonomy,today)
        profile=EmailCampaignProfile(product.key,'v1',product.brand_key,product.key,product.id,taxonomy)
        expiry=min(context['review_expires_at'],now+request.evidence.review_days*86400)
        connection=ContactConnection(organization,product.key+'-email-fixture','synthetic-crm',product.key,'intake-email-v1')
        size=preview['settings']['size']
        accounts=tuple(ContactAccount(NativeReference(connection,'Company',str(i),'account'),
            product.key+'-business-'+str(i),'businesses') for i in range(size))
        people=tuple(ContactPerson(NativeReference(connection,'Person',str(i),'contact'),(a.ref,),
            'person'+str(i)+'@'+product.key+'.example.invalid',None) for i,a in enumerate(accounts))
        permissions=tuple(PermissionObservation(p.ref,'email','acquisition','granted',
            'synthetic-intake-email-permission/v1',now,expiry) for p in people)
        pressure=tuple(ContactPressure(p.ref,a.experiment_unit,0,0,now-90*86400,now,expiry,True,
            'synthetic-intake-email-pressure/v1') for p,a in zip(people,accounts,strict=True))
        snapshot=ContactSnapshot(connection,1,profile.id,now,expiry,size,size,True,None,accounts,people,permissions,pressure)
        readiness=evaluate_contact_eligibility(snapshot,profile,'email','acquisition',now,set(),set(),set(),set(),set())
        if not readiness['ready_for_proposal'] or len(readiness['eligible'])!=size:
            raise Conflict('Every synthetic email recipient requires complete preparation permission')
        binding={'schema':'intake-email-binding/v1','organization':organization,'actor':actor,'request_id':request_id,
            'request':json.loads(canonical(asdict(request))), 'context_request_id':request.context_request_id,
            'context_fingerprint':context['fingerprint'],'store_id':context['store_id'],
            'prepared_at':now,'expires_at':expiry,'requirements':context['requirements'],'settings':preview['settings']}
        content=render_intake_email(organization,product,pack,profile.id,snapshot,context['selected_inputs'],digest(binding),today)
        payload={'schema':'intake-email-batch/v1','organization':organization,'request_id':request_id,
            'binding':binding,'profile':json.loads(canonical(asdict(profile))),
            'product_profile':json.loads(canonical(asdict(product))), 'contacts':json.loads(canonical(asdict(snapshot))),
            'readiness':readiness,'content':content,'mode':'SYNTHETIC_ONLY','approval':'not_granted',
            'targeting':'synthetic_not_matched_to_user_audience','cost_minor':size*2,'live_send_authority':'none'}
        if len(canonical(payload).encode())>512000:raise ValueError('Email preparation exceeds its bounded package size')
        return payload|{'id':'intake_email_batch_'+digest(payload)}
