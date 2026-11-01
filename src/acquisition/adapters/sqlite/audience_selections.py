"""Selection and verified source bytes commit together with revision fencing."""
import json
import math
import time
from datetime import datetime, timezone
from acquisition.audiences import DatasetVersion, validate_dataset, validate_dataset_freshness
from dataclasses import asdict

from acquisition.contracts import Conflict, canonical, digest


class SqliteAudienceSelections:
    def __init__(self, database, clock=time.time):
        self.database, self.clock = database, clock

    def request(self, organization, request_id):
        with self.database.connect() as db:
            row=db.execute('SELECT payload FROM audience_selection_requests WHERE organization=? AND request_id=?',
                           (organization,request_id)).fetchone()
            return json.loads(row[0]) if row else None

    def get(self, organization, conversation_id, revision):
        with self.database.connect() as db:
            row=db.execute('SELECT payload FROM conversation_audiences WHERE organization=? AND conversation_id=? AND revision=?',
                           (organization,conversation_id,revision)).fetchone()
            return json.loads(row[0]) if row else None

    def select(self, organization, request_id, inputs, receipt, snapshot, now):
        if not math.isfinite(now):
            raise ValueError('Audience selection requires a finite timestamp')
        with self.database.transaction() as db:
            # Authorization time must include time spent waiting for this lock.
            now = self.clock()
            if not math.isfinite(now):
                raise ValueError('Audience selection requires a finite timestamp')
            prior=db.execute('SELECT payload FROM audience_selection_requests WHERE organization=? AND request_id=?',
                             (organization,request_id)).fetchone()
            if prior:
                value=json.loads(prior[0])
                if value['inputs'] != inputs:
                    raise Conflict('Audience request already binds different selection inputs')
                return value['receipt']
            source=db.execute('SELECT revision FROM conversations WHERE organization=? AND id=?',
                              (organization,inputs['conversation_id'])).fetchone()
            if source is None or source[0] != inputs['revision']:
                raise Conflict('Conversation changed before audience confirmation')
            plan=db.execute('''SELECT t.output FROM conversation_plans p JOIN runs r ON r.organization=p.organization
                JOIN tasks t ON t.run_id=r.id WHERE p.organization=? AND p.conversation_id=? AND p.revision=?
                AND r.request_id=json_extract(p.payload,'$.run_request_id') AND r.status='succeeded' AND t.status='succeeded'
                AND t.capability IN ('conversations.plan.v1','conversations.fixture_plan.v1')''',
                (organization,inputs['conversation_id'],inputs['revision'])).fetchone()
            result=json.loads(plan[0]) if plan else {}
            if result.get('id') != inputs['plan_id'] or result.get('outcome') != 'brief_proposal' or set(result['segments']) != set(receipt['source']['segments']):
                raise Conflict('Audience confirmation requires its exact completed proposal')
            old=db.execute('SELECT payload FROM conversation_audiences WHERE organization=? AND conversation_id=? AND revision=?',
                           (organization,inputs['conversation_id'],inputs['revision'])).fetchone()
            if old and canonical(json.loads(old[0])) != canonical(receipt):
                raise Conflict('This brief already binds another audience. Send a new message to change it.')
            manifest=DatasetVersion(**(receipt['source'] | {'segments':tuple(receipt['source']['segments'])}))
            if manifest.id != inputs['manifest_id'] or manifest.checksum != inputs['checksum']:
                raise Conflict('Audience manifest differs from confirmation inputs')
            validate_dataset(manifest,snapshot,organization,datetime.fromtimestamp(now,timezone.utc).date())
            payload=canonical(asdict(snapshot))
            previous=db.execute('SELECT payload FROM audiences WHERE organization=? AND id=?',(organization,snapshot.id)).fetchone()
            if snapshot.organization != organization or receipt['source_snapshot_id'] != snapshot.id or (previous and previous[0] != payload):
                raise Conflict('Audience selection snapshot integrity failure')
            db.execute('INSERT OR IGNORE INTO audiences VALUES(?,?,?)',(organization,snapshot.id,payload))
            db.execute('INSERT OR IGNORE INTO conversation_audiences VALUES(?,?,?,?)',
                       (organization,inputs['conversation_id'],inputs['revision'],canonical(receipt)))
            db.execute('INSERT INTO audience_selection_requests VALUES(?,?,?)',
                       (organization,request_id,canonical({'inputs':inputs,'receipt':receipt})))
            # Serialization, validation and SQL writes may cross the deadline.
            # Keep this cheap fence last so expiry rolls back the whole selection.
            commit_time = self.clock()
            if not math.isfinite(commit_time):
                raise ValueError('Audience selection requires a finite timestamp')
            validate_dataset_freshness(manifest, datetime.fromtimestamp(commit_time, timezone.utc).date())
        return receipt
