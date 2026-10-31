"""Scoped frozen follow-up proposals in the existing command journal."""
import json
import csv
import io
from acquisition.contracts import Conflict, NotFound, canonical, digest
from .actors import require_actor


def excluded_businesses(db, organization, own_draft=None):
    ids = {r[0] for r in db.execute('SELECT business_id FROM learning_members WHERE organization=?', (organization,))}
    own = set()
    for r in db.execute('SELECT payload FROM simulated_agency_jobs WHERE organization=?', (organization,)):
        job = json.loads(r[0])
        row = db.execute('SELECT assignments FROM drafts WHERE organization=? AND id=?', (organization, job['draft_id'])).fetchone()
        members = {m['business_id'] for m in csv.DictReader(io.StringIO(row[0]))}
        if job['draft_id'] == own_draft:
            own |= members
        else:
            ids |= members
    ids -= own
    ids |= {r[0] for r in db.execute('SELECT business_id FROM review_suppressions WHERE organization=?', (organization,))}
    return ids


def require_followup(db, organization, inputs, own_draft=None):
    brief = inputs.get('brief', {})
    if 'followup_id' not in brief:
        return
    row = db.execute('SELECT receipt FROM review_commands WHERE organization=? AND request_id=?', (organization, brief['followup_id'])).fetchone()
    if row is None:
        raise Conflict('Follow-up lacks its frozen proposal')
    p = json.loads(row[0])
    if p['id'] != 'followup_' + digest({k:v for k,v in p.items() if k!='id'}):
        raise Conflict('Follow-up proposal integrity failure')
    if brief['campaign_id'] != 'workspace_' + digest({'followup':p['id']})[:24]:
        raise Conflict('Follow-up campaign identity changed')
    expected = p['brief'] | {'campaign_id':brief['campaign_id'], 'followup_id':p['id']}
    if canonical(brief) != canonical(expected) or inputs.get('snapshot_id',p['snapshot_id']) != p['snapshot_id']:
        raise Conflict('Follow-up inputs differ from the frozen proposal')
    if 'context_ids' in inputs and inputs['context_ids'] != p['contexts']:
        raise Conflict('Follow-up model context differs from the frozen proposal')
    authority = db.execute('SELECT evidence_epoch,audience_epoch FROM review_authorities WHERE organization=?', (organization,)).fetchone()
    if list(authority) != p['epochs']:
        raise Conflict('Follow-up evidence or suppressions changed; propose again')
    if set(p['population']) & excluded_businesses(db, organization, own_draft):
        raise Conflict('Follow-up population is no longer independent; propose again')


class SqliteFollowups:
    def __init__(self, database): self.database=database

    def get(self, organization, identity):
        with self.database.connect() as db:
            row=db.execute('SELECT receipt FROM review_commands WHERE organization=? AND request_id=?',(organization,identity)).fetchone()
        if row is None: raise NotFound('Follow-up proposal not found in this organization')
        p=json.loads(row[0])
        if p.get('kind')!='followup_proposal' or p['id'] != 'followup_' + digest({k:v for k,v in p.items() if k!='id'}):
            raise Conflict('Follow-up proposal integrity failure')
        return p

    def put(self, organization, request, p):
        key='followup-request:'+request
        with self.database.transaction() as db:
            require_actor(db, organization, 'local-operator', 'operator')
            old=db.execute('SELECT receipt FROM review_commands WHERE organization=? AND request_id=?',(organization,key)).fetchone()
            if old: return json.loads(old[0])
            row=db.execute('SELECT finalization FROM learning_cohorts WHERE organization=? AND id=?',(organization,p['source_cohort'])).fetchone()
            if row is None or json.loads(row[0] or 'null') != p['learning']['finalization']:
                raise Conflict('Finalized source learning changed')
            if set(p['population']) & excluded_businesses(db, organization):
                raise Conflict('Population changed while proposing; retry')
            p=p|{'kind':'followup_proposal'}
            p=p|{'id':'followup_'+digest(p)}
            for identity in (key,p['id']):
                db.execute('INSERT OR IGNORE INTO review_commands VALUES(?,?,?,?)',(organization,identity,digest(p),canonical(p)))
            return p

    def excluded(self, organization):
        with self.database.connect() as db:
            db.execute('BEGIN')
            return excluded_businesses(db,organization)

    def check(self, organization, proposal, campaign_id):
        with self.database.connect() as db:
            require_actor(db, organization, 'local-operator', 'operator')
            require_followup(db,organization,{'brief':proposal['brief']|{'campaign_id':campaign_id,'followup_id':proposal['id']},'snapshot_id':proposal['snapshot_id']})

    def listing(self, organization, parent_id):
        with self.database.connect() as db:
            return [p for r in db.execute('SELECT request_id,receipt FROM review_commands WHERE organization=? ORDER BY rowid',(organization,))
                if (p:=json.loads(r['receipt'])).get('kind')=='followup_proposal' and r['request_id']==p['id'] and p['parent_id']==parent_id]
