"""Atomic frozen decisions in the audiences-owned contact command journal (schema 18)."""

from dataclasses import asdict
import json

from acquisition.audiences import (FeatureBatch, FeatureRow, bounded, feature_batch_from,
                                  decision_request_from, strategy_run_from)
from acquisition.campaigns import contact_decision_plan
from acquisition.contracts import Conflict, NotFound, canonical, digest


class SqliteAudienceDecisions:
    def __init__(self, contacts, categorizer_spec, decision_spec):
        self.contacts = contacts
        # Trusted composition attests implementations separately from candidate results.
        self.categorizer_spec, self.decision_spec = categorizer_spec, decision_spec

    def _inputs(self, request):
        if request.categorizer != self.categorizer_spec or request.decision != self.decision_spec:
            raise Conflict('Decision request differs from installed strategy contracts')
        return {'kind':'audience-decision/v1','request':asdict(request)}

    def _receipt(self, db, row, organization):
        receipt = json.loads(row['receipt'])
        payload = receipt.get('decision')
        if (receipt.get('kind')!='audience_decision_prepared' or type(payload) is not dict
                or payload.get('organization')!=organization
                or receipt.get('decision_id')!='audience_decision_'+digest(payload)
                or json.loads(row['inputs'])!={'kind':'audience-decision/v1','request':payload['request']}):
            raise Conflict('Stored audience decision integrity failure')
        batch = feature_batch_from(payload['feature_batch'])
        request = decision_request_from(payload['request'])
        report = self.contacts.assessment(db,organization,request.assessment_id)['report']
        if (payload['schema']!='audience-decision/v1' or batch.organization!=organization
                or batch.assessment_id!=request.assessment_id or payload['feature_batch_id']!=batch.id
                or payload['feature_digest']!=batch.feature_digest
                or contact_decision_plan(batch,request,strategy_run_from(payload['run']),report)!=payload['plan']):
            raise Conflict('Stored audience decision derivation failure')
        return receipt

    def replay(self, organization, request_id, request):
        inputs = self._inputs(request)
        with self.contacts.database.connect() as db:
            self.contacts._writable(db)
            old = db.execute('SELECT inputs,receipt FROM contact_commands WHERE organization=? AND request_id=?',
                             (organization,request_id)).fetchone()
            bounded(request_id)
            if old is None: return None
            if old['inputs']!=canonical(inputs): raise Conflict('Decision request already binds different exact inputs')
            return self._receipt(db,old,organization) | {'observation':'historical_receipt','authority':'none'}

    def _capture(self, db, organization, request):
        self._inputs(request)
        snapshot, report, profile = self.contacts.decision_evidence(db,organization,request.assessment_id)
        accounts = {a.ref.id:a for a in snapshot.accounts}
        rows = []
        for person in sorted(snapshot.contacts,key=lambda p:p.ref.id):
            account = accounts.get(person.accounts[0].id) if len(person.accounts)==1 else None
            rows.append(FeatureRow(person.ref.id,account.experiment_unit if account else None,
                                   account.segment if account else None))
        return FeatureBatch(organization,request.assessment_id,profile.id,snapshot.id,digest(report),
                            report['channel'],report['purpose'],profile.taxonomy,profile.objective,tuple(rows)), report

    def capture(self, organization, request):
        with self.contacts.database.connect() as db:
            db.execute('BEGIN')
            self.contacts._writable(db)
            return self._capture(db,organization,request)[0]

    def publish(self, organization, request_id, request, batch, run):
        inputs = self._inputs(request)
        with self.contacts.database.transaction() as db:
            self.contacts._writable(db)
            # A racing request cannot replace the first result or re-attest current authority.
            replay = self.contacts._replay(db,organization,request_id,inputs)
            if replay: return replay
            expected, readiness = self._capture(db,organization,request)
            if batch != expected: raise Conflict('Features differ from independently reconstructed evidence')
            plan = contact_decision_plan(batch,request,run,readiness)
            payload = {'schema':'audience-decision/v1','organization':organization,'request':asdict(request),
                'checked_at':self.contacts._now(),'feature_batch':asdict(batch),'feature_batch_id':batch.id,
                'feature_digest':batch.feature_digest,'run':asdict(run),'plan':plan}
            # First response and replay expose identical JSON values, including tuple-backed contracts.
            payload = json.loads(canonical(payload))
            receipt = {'kind':'audience_decision_prepared','decision_id':'audience_decision_'+digest(payload),
                       'decision':payload}
            result = self.contacts._record(db,organization,request_id,inputs,receipt)
            if self._capture(db,organization,request)[0] != batch:
                raise Conflict('Evidence changed before decision commit')
            return result

    def inspect(self, organization, request_id):
        with self.contacts.database.connect() as db:
            db.execute('BEGIN')
            bounded(request_id)
            row = db.execute('SELECT inputs,receipt FROM contact_commands WHERE organization=? AND request_id=?',
                             (organization,request_id)).fetchone()
            if row is None or json.loads(row['inputs']).get('kind')!='audience-decision/v1':
                raise NotFound('Decision is unavailable in this organization')
            receipt = self._receipt(db,row,organization)
            payload = receipt['decision']
            try:
                snapshot, report, profile = self.contacts.decision_evidence(db,organization,payload['request']['assessment_id'])
                applicable = (snapshot.id==payload['feature_batch']['source_id']
                              and profile.id==payload['feature_batch']['profile_id']
                              and digest(report)==payload['feature_batch']['readiness_digest'])
            except (Conflict,NotFound):
                applicable = False
            return {'saved':receipt,'currently_applicable':applicable,
                    'complete_proposal':applicable and payload['plan']['status']=='complete','authority':'none'}
