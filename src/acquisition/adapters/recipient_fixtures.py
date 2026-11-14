"""Installed reviewed synthetic evidence. No arbitrary HTTP, uploads or customer data."""

from dataclasses import asdict
from datetime import datetime, timezone
import json

from acquisition.contracts import NotFound, canonical
from acquisition.creative import (RecipientTarget, RecipientDocument, RecipientFact, RecipientEvidence,
                                  recipient_evidence_from)


class RecordedRecipientContextSource:
    def __init__(self, organization, evidence):
        self.organization = organization
        self._payloads, self._manifests = {}, {}
        for item in evidence:
            if item.target.organization!=organization: raise ValueError('Context source belongs to another organization')
            key = (item.target.id,item.source_key,item.version)
            if key in self._payloads: raise ValueError('A context source version must have one exact identity')
            self._payloads[key] = canonical(asdict(item))
            self._manifests[key] = canonical(item.manifest())

    def _key(self, organization, source_key, version, target):
        if organization!=self.organization or target.organization!=organization or type(version) is not int:
            raise NotFound('Recipient evidence is unavailable in this organization')
        key = (target.id,source_key,version)
        if key not in self._payloads: raise NotFound('Unknown installed recipient evidence source')
        return key

    def read(self, organization, source_key, version, target):
        key = self._key(organization,source_key,version,target)
        return recipient_evidence_from(json.loads(self._payloads[key]))

    def manifest(self, organization, source_key, version, target):
        key = self._key(organization,source_key,version,target)
        return json.loads(self._manifests[key])


def synthetic_recipient_evidence(snapshot):
    observed = datetime(2026,11,13,tzinfo=timezone.utc).timestamp()-1800
    expiry = datetime(2026,11,24,tzinfo=timezone.utc).timestamp()
    accounts = {a.ref.id:a for a in snapshot.accounts}
    for person in snapshot.contacts:
        account = accounts[person.accounts[0].id]
        target = RecipientTarget(snapshot.connection.organization,snapshot.profile_id,person.ref,account.ref,account.experiment_unit)
        for key in ('reviewed-context-a','reviewed-context-b'):
            for version in (1,2,3,4):
                documents, facts = [], []
                for slot, code, kind in (('contact_role','operations_manager','crm_note'),
                    ('prior_interaction','requested_overview','inbound_body'),
                    ('account_activity','equipment_quote','attachment'),('business_signal','new_location','webpage')):
                    if version==4 and slot=='business_signal': continue
                    state = 'withdrawn' if version==2 and slot=='contact_role' else 'asserted'
                    if version==3 and slot=='contact_role': code = 'procurement_manager'
                    if state=='withdrawn': code = None
                    body = 'SYNTHETIC reviewed observation: ' + slot + '=' + (code or state) + '.'
                    documents.append(RecipientDocument(slot,kind,body))
                    subject = target.contact if slot in {'contact_role','prior_interaction'} else target.account
                    facts.append(RecipientFact(subject.id,slot,code,
                        None if slot=='contact_role' or state!='asserted' else '2026-11-12',slot,0,len(body),
                        observed+(version-1)*60 if slot=='contact_role' else observed,expiry,
                        ('email:acquisition','human_call:acquisition'),'synthetic-review-v1',state))
                yield RecipientEvidence(target,key,version,observed+(version-1)*60,expiry,
                    ('email:acquisition','human_call:acquisition'),version!=4,4,4,tuple(documents),tuple(facts))
