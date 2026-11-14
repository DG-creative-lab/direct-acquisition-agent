"""Reserved synthetic effects, immutable observations and lease-fenced step transitions."""

from dataclasses import asdict
import json
import uuid

from acquisition.campaigns import sequence_text, sequence_time
from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.engagements import (DispatchClaim, SimulationReceipt, make_intent,
    validate_simulation_receipt, validate_observation, simulation_totals, validate_step_transition, applicable_stop, step_wait_reason)
from acquisition.runtime import LeaseLost


class SqliteEngagements:
    def __init__(self, proposals):
        self.proposals,self.database=proposals,proposals.database

    def _now(self): return self.proposals._now()
    def _writable(self, db): self.proposals.writable(db)

    def _event(self, db, organization, simulation_id, kind, **data):
        payload={'kind':kind,'at':self._now(),**data}
        db.execute('INSERT INTO engagement_events VALUES(?,?,?,?)',
            (organization,'engagement_event_'+uuid.uuid4().hex,simulation_id,canonical(payload)))

    def _command(self, db, organization, request_id, inputs, receipt=None):
        sequence_text(request_id)
        row=db.execute('SELECT inputs,receipt FROM engagement_commands WHERE organization=? AND request_id=?',(organization,request_id)).fetchone()
        if row:
            if row['inputs']!=canonical(inputs): raise Conflict('Engagement request already binds different exact inputs')
            return json.loads(row['receipt'])
        if receipt is not None:
            db.execute('INSERT INTO engagement_commands VALUES(?,?,?,?)',(organization,request_id,canonical(inputs),canonical(receipt)))
        return None

    def _simulation(self, db, organization, simulation_id):
        row=db.execute('SELECT * FROM engagement_simulations WHERE organization=? AND id=?',(organization,simulation_id)).fetchone()
        if row is None: raise NotFound('Simulation is unavailable in this organization')
        if simulation_id!='simulation_'+digest({'organization':organization,'proposal_id':row['proposal_id']}):
            raise Conflict('Simulation identity differs from its frozen proposal')
        proposal=self.proposals.get(db,organization,row['proposal_id'])
        expected=[{'organization':organization,'id':'enrollment_'+digest({'simulation_id':simulation_id,'unit':m['experiment_unit']}),
            'simulation_id':simulation_id,'experiment_unit':m['experiment_unit'],'contact_id':m['contact_id'],
            'account_id':m['account_id'],'arm':m['arm']} for m in proposal['population']]
        actual=[dict(r) for r in db.execute('SELECT * FROM engagement_enrollments WHERE organization=? AND simulation_id=?',(organization,simulation_id))]
        if sorted(actual,key=lambda r:r['id'])!=sorted(expected,key=lambda r:r['id']):
            raise Conflict('Enrollment population differs from the immutable campaign assignments')
        return row,proposal

    def _intent(self, row, proposal):
        intent=json.loads(row['intent'])
        members=[m for m in proposal['population'] if row['enrollment_id']=='enrollment_'+digest(
            {'simulation_id':row['simulation_id'],'unit':m['experiment_unit']})]
        if len(members)!=1: raise Conflict('Step enrollment differs from frozen assignments')
        member=members[0];steps=[s for s in member['steps'] if s['ordinal']==row['ordinal']]
        if len(steps)!=1: raise Conflict('Step is absent from the exact frozen strategy')
        expected=make_intent(row['organization'],row['simulation_id'],'sequence_proposal_'+digest(proposal),member,steps[0])
        if (intent!=expected or row['id']!='engagement_step_'+digest(expected)
                or row['contact_id']!=member['contact_id'] or row['account_id']!=member['account_id']
                or row['channel']!=steps[0]['channel'] or row['due_at']!=steps[0]['due_at']):
            raise Conflict('Step intent differs from its immutable campaign proposal')
        return intent

    def _step(self, db, organization, simulation_id, step_id):
        row=db.execute('SELECT * FROM engagement_steps WHERE organization=? AND simulation_id=? AND id=?',
            (organization,simulation_id,step_id)).fetchone()
        if row is None: raise NotFound('Step is unavailable in this simulation')
        _,proposal=self._simulation(db,organization,simulation_id)
        return row,self._intent(row,proposal)

    def start(self, organization, request_id, proposal_id, configuration):
        inputs={'kind':'start_simulation/v1','proposal_id':proposal_id,'configuration':configuration}
        with self.database.transaction() as db:
            self._writable(db)
            replay=self._command(db,organization,request_id,inputs)
            if replay: return replay|{'observation':'historical_receipt'}
            proposal=self.proposals.get(db,organization,proposal_id)
            old=db.execute('SELECT * FROM engagement_simulations WHERE organization=? AND proposal_id=?',(organization,proposal_id)).fetchone()
            if old:
                if old['configuration']!=canonical(configuration): raise Conflict('Resume with the frozen simulation transport configuration')
                result={'simulation_id':old['id'],'proposal_id':proposal_id,'mode':'SYNTHETIC_ONLY','authority':'none'}
                self._command(db,organization,request_id,inputs,result)
                return result|{'observation':'historical_receipt'}
            self.proposals.current(db,organization,proposal)
            expected={s['channel']:s['connection_id'] for m in proposal['population'] for s in m['steps']}
            if (set(configuration)!={'email','human_call'} or any(configuration[channel]['connection_id']!=identity for channel,identity in expected.items())):
                raise Conflict('Simulation transport differs from frozen sequence connections')
            simulation_id='simulation_'+digest({'organization':organization,'proposal_id':proposal_id})
            db.execute('INSERT INTO engagement_simulations VALUES(?,?,?,?)',(organization,simulation_id,proposal_id,canonical(configuration)))
            for member in proposal['population']:
                enrollment_id='enrollment_'+digest({'simulation_id':simulation_id,'unit':member['experiment_unit']})
                db.execute('INSERT INTO engagement_enrollments VALUES(?,?,?,?,?,?,?)',
                    (organization,enrollment_id,simulation_id,member['experiment_unit'],member['contact_id'],member['account_id'],member['arm']))
                for step in member['steps']:
                    intent=make_intent(organization,simulation_id,proposal_id,member,step)
                    step_id='engagement_step_'+digest(intent)
                    db.execute('''INSERT INTO engagement_steps(organization,id,simulation_id,enrollment_id,ordinal,channel,
                        contact_id,account_id,due_at,status,intent) VALUES(?,?,?,?,?,?,?,?,?,'pending',?)''',
                        (organization,step_id,simulation_id,enrollment_id,step['ordinal'],step['channel'],
                         member['contact_id'],member['account_id'],step['due_at'],canonical(intent)))
            result={'simulation_id':simulation_id,'proposal_id':proposal_id,'mode':'SYNTHETIC_ONLY','authority':'none'}
            self._event(db,organization,simulation_id,'simulation_enrolled',counts=proposal['counts'])
            self._command(db,organization,request_id,inputs,result)
            self.proposals.current(db,organization,proposal); self._writable(db)
            return result|{'observation':'simulation_started'}

    def _stop_action(self, db, organization, simulation_id, row):
        stops=[dict(r) for r in db.execute('SELECT * FROM engagement_stops WHERE organization=? AND (simulation_id IS NULL OR simulation_id=?)',
                                          (organization,simulation_id))]
        return applicable_stop(stops,simulation_id,row['contact_id'],row['account_id'])

    def _allowed(self, db, organization, simulation_id, row, proposal, intent):
        action=self._stop_action(db,organization,simulation_id,row)
        if action: return action
        try: self.proposals.current_step(db,organization,proposal,intent['step'])
        except (Conflict,NotFound,ValueError): return 'blocked'
        return None

    def _transition(self, db, row, status):
        if row['status']==status:return
        validate_step_transition(row['status'],status)
        db.execute('UPDATE engagement_steps SET status=?,token=NULL,lease_until=NULL WHERE organization=? AND id=?',
            (status,row['organization'],row['id']))
        self._event(db,row['organization'],row['simulation_id'],'step_'+status,step_id=row['id'])

    def claim(self, organization, simulation_id, configuration, lease_seconds):
        if type(lease_seconds) is not int or not 1<=lease_seconds<=300: raise ValueError('Use a bounded step lease')
        with self.database.transaction() as db:
            self._writable(db); simulation,proposal=self._simulation(db,organization,simulation_id)
            if simulation['configuration']!=canonical(configuration): raise Conflict('Use the frozen simulation provider configuration')
            now=self._now()
            for expired in db.execute("SELECT * FROM engagement_steps WHERE organization=? AND simulation_id=? AND status='dispatching' AND lease_until<=?",
                (organization,simulation_id,now)).fetchall(): self._transition(db,expired,'unknown')
            rows=db.execute("SELECT * FROM engagement_steps WHERE organization=? AND simulation_id=? AND status='pending' ORDER BY due_at,id",
                (organization,simulation_id)).fetchall()
            for row in rows:
                intent=self._intent(row,proposal)
                denied=self._allowed(db,organization,simulation_id,row,proposal,intent)
                if denied:
                    self._transition(db,row,denied); continue
                if row['due_at']>self._now(): continue
                previous=db.execute('SELECT * FROM engagement_steps WHERE organization=? AND enrollment_id=? AND ordinal=?',
                    (organization,row['enrollment_id'],row['ordinal']-1)).fetchone() if row['ordinal'] else None
                completed=previous is not None and db.execute(
                    "SELECT 1 FROM engagement_observations WHERE organization=? AND step_id=? AND kind='task_completed'",
                    (organization,previous['id'])).fetchone() is not None
                if step_wait_reason(row,previous,completed,self._now())!='due':continue
                token=uuid.uuid4().hex; deadline=self._now()+lease_seconds
                validate_step_transition(row['status'],'dispatching')
                db.execute("UPDATE engagement_steps SET status='dispatching',token=?,lease_until=? WHERE organization=? AND id=?",
                    (token,deadline,organization,row['id']))
                db.execute('INSERT INTO engagement_dispatches VALUES(?,?,?,?,?,?,NULL)',
                    (organization,row['id'],intent['effect_key'],digest(intent),token,self._now()))
                self._event(db,organization,simulation_id,'step_reserved',step_id=row['id'])
                if self._allowed(db,organization,simulation_id,row,proposal,intent) is not None:
                    raise Conflict('Step authority changed before reservation committed')
                self._writable(db)
                if self._now()>=deadline: raise LeaseLost('Simulation lease expired before reservation commit')
                return DispatchClaim(organization,simulation_id,row['id'],token,deadline,intent)
            return None

    def _record_receipt(self, claim, receipt):
        # A late observation may survive stop/lease loss. It cannot authorize continuation.
        if self.proposals.read_only: raise Conflict('Inspection cannot record submission observations')
        with self.database.transaction() as db:
            row,intent=self._step(db,claim.organization,claim.simulation_id,claim.step_id)
            dispatch=db.execute('SELECT * FROM engagement_dispatches WHERE organization=? AND step_id=?',
                (claim.organization,claim.step_id)).fetchone()
            if (dispatch is None or dispatch['token']!=claim.token or dispatch['request_hash']!=digest(intent)
                    or dispatch['effect_key']!=intent['effect_key'] or claim.intent!=intent): raise Conflict('Submission differs from its reserved exact effect')
            validate_simulation_receipt(intent,receipt)
            if dispatch['receipt'] is not None:
                if dispatch['receipt']!=canonical(asdict(receipt)): raise Conflict('Submission observation is immutable')
                return
            db.execute('UPDATE engagement_dispatches SET receipt=? WHERE organization=? AND step_id=?',
                (canonical(asdict(receipt)),claim.organization,claim.step_id))
            self._event(db,claim.organization,claim.simulation_id,'submission_observed',step_id=claim.step_id,status=receipt.status)

    def _settle(self, db, claim, receipt):
        self._writable(db); simulation,proposal=self._simulation(db,claim.organization,claim.simulation_id)
        row,intent=self._step(db,claim.organization,claim.simulation_id,claim.step_id)
        observation=db.execute('SELECT receipt FROM engagement_dispatches WHERE organization=? AND step_id=?',
            (claim.organization,claim.step_id)).fetchone()
        if observation is None or observation['receipt']!=canonical(asdict(receipt)):
            raise Conflict('Step completion lacks its exact recorded provider observation')
        if row['status']!='dispatching' or row['token']!=claim.token or row['lease_until']<=self._now():
            # Original receipt remains an observation, while uncertain step state cannot advance.
            return
        denied=self._allowed(db,claim.organization,claim.simulation_id,row,proposal,intent)
        self._transition(db,row,denied or receipt.status)
        self._writable(db)
        if self._now()>=row['lease_until']: raise LeaseLost('Simulation lease expired before completion commit')
        if self._allowed(db,claim.organization,claim.simulation_id,row,proposal,intent)!=denied:
            raise Conflict('Step authority changed while completion was written')

    def settle(self, claim, receipt):
        self._record_receipt(claim,receipt)
        with self.database.transaction() as db: self._settle(db,claim,receipt)

    def _save_stop(self, db, organization, simulation_id, scope, subject, action, payload):
        identity='engagement_stop_'+digest(payload)
        db.execute('INSERT INTO engagement_stops VALUES(?,?,?,?,?,?,?)',
            (organization,identity,simulation_id,scope,subject,action,canonical(payload)))
        parameters=[organization]; clause=''
        if simulation_id is not None: clause+=' AND simulation_id=?'; parameters.append(simulation_id)
        column={'contact':'contact_id','account':'account_id','simulation':'simulation_id'}[scope]
        clause+=' AND '+column+'=?'; parameters.append(subject)
        for row in db.execute("SELECT * FROM engagement_steps WHERE organization=? AND status IN ('pending','paused')"+clause,parameters).fetchall():
            self._transition(db,row,'stopped' if action=='stop' else 'paused')

    def observe(self, organization, request_id, simulation_id, step_id, provider_effect_id, kind, occurred_at):
        inputs={'kind':'simulate_observation/v1','simulation_id':simulation_id,'step_id':step_id,
            'provider_effect_id':provider_effect_id,'observation':kind,'occurred_at':occurred_at}
        with self.database.transaction() as db:
            self._writable(db); self._simulation(db,organization,simulation_id)
            replay=self._command(db,organization,request_id,inputs)
            if replay: return replay
            row,intent=self._step(db,organization,simulation_id,step_id)
            dispatch=db.execute('SELECT * FROM engagement_dispatches WHERE organization=? AND step_id=?',(organization,step_id)).fetchone()
            if dispatch is None or dispatch['receipt'] is None: raise Conflict('Observation has no recorded accepted submission')
            receipt=SimulationReceipt(**json.loads(dispatch['receipt']))
            validate_observation(intent,receipt,kind,occurred_at,self._now())
            if provider_effect_id!=receipt.provider_effect_id or occurred_at<dispatch['reserved_at']:
                raise Conflict('Observation differs from its exact provider effect')
            existing=db.execute('SELECT payload FROM engagement_observations WHERE organization=? AND step_id=? AND kind=?',
                (organization,step_id,kind)).fetchone()
            if existing:
                value=json.loads(existing[0])
                if value['provider_effect_id']!=provider_effect_id or value['occurred_at']!=occurred_at:
                    raise Conflict('Observation already binds different exact evidence')
                self._command(db,organization,request_id,inputs,value); return value
            if kind in {'delivered','bounced'} and db.execute(
                "SELECT 1 FROM engagement_observations WHERE organization=? AND step_id=? AND kind IN ('delivered','bounced')",
                (organization,step_id)).fetchone(): raise Conflict('Contradictory delivery evidence requires a separate correction contract')
            value={'schema':'simulated-observation/v1','mode':'SYNTHETIC_ONLY','organization':organization,
                'simulation_id':simulation_id,'step_id':step_id,'provider_effect_id':provider_effect_id,'kind':kind,'occurred_at':occurred_at}
            identity='simulated_observation_'+digest(value)
            db.execute('INSERT INTO engagement_observations VALUES(?,?,?,?,?,?)',(organization,identity,simulation_id,step_id,kind,canonical(value)))
            if kind in {'replied','objected'}:
                scope=intent['step']['stop_scope']; subject=intent['contact_id'] if scope=='contact' else intent['step']['content']['target']['account_id']
                self._save_stop(db,organization,None if kind=='objected' else simulation_id,scope,subject,
                    'stop' if kind=='objected' else 'pause',value)
            self._event(db,organization,simulation_id,'observation_recorded',observation_id=identity)
            self._command(db,organization,request_id,inputs,value); self._writable(db)
            return value

    def stop(self, organization, request_id, simulation_id):
        inputs={'kind':'stop_simulation/v1','simulation_id':simulation_id}
        with self.database.transaction() as db:
            self._writable(db); self._simulation(db,organization,simulation_id)
            replay=self._command(db,organization,request_id,inputs)
            if replay: return replay
            receipt={'mode':'SYNTHETIC_ONLY','simulation_id':simulation_id,'stopped':True,'authority':'none','request_id':request_id}
            self._save_stop(db,organization,simulation_id,'simulation',simulation_id,'stop',receipt)
            self._event(db,organization,simulation_id,'simulation_stopped',request_id=request_id)
            self._command(db,organization,request_id,inputs,receipt); self._writable(db)
            return receipt

    def inspect(self, organization, simulation_id):
        with self.database.connect() as db:
            db.execute('BEGIN'); simulation,proposal=self._simulation(db,organization,simulation_id)
            steps=[]
            for row in db.execute('SELECT * FROM engagement_steps WHERE organization=? AND simulation_id=? ORDER BY enrollment_id,ordinal',(organization,simulation_id)):
                intent=self._intent(row,proposal)
                dispatch=db.execute('SELECT * FROM engagement_dispatches WHERE organization=? AND step_id=?',(organization,row['id'])).fetchone()
                receipt=json.loads(dispatch['receipt']) if dispatch and dispatch['receipt'] else None
                expired=row['status']=='dispatching' and row['lease_until']<=self._now()
                steps.append({k:row[k] for k in ('id','enrollment_id','ordinal','channel','contact_id','account_id','due_at','status')}|
                    {'stored_status':row['status'],'status':'unknown' if expired else row['status'],
                     'unit_cost_pence':intent['step']['unit_cost_pence'],'intent':intent,'submission':receipt})
            observations=[]
            for row in db.execute('SELECT * FROM engagement_observations WHERE organization=? AND simulation_id=? ORDER BY rowid',(organization,simulation_id)):
                value=json.loads(row['payload'])
                if (row['id']!='simulated_observation_'+digest(value) or value['organization']!=organization
                        or value['simulation_id']!=simulation_id or value['step_id']!=row['step_id'] or value['kind']!=row['kind']):
                    raise Conflict('Stored observation integrity failure')
                observations.append(value)
            for step in steps:
                step['waiting_on']=None
                if step['status']!='pending': continue
                prior=next((r for r in steps if r['enrollment_id']==step['enrollment_id'] and r['ordinal']==step['ordinal']-1),None)
                completed=prior is not None and any(o['step_id']==prior['id'] and o['kind']=='task_completed' for o in observations)
                step['waiting_on']=step_wait_reason(step,prior,completed,self._now())
            totals=simulation_totals(proposal,steps,observations)
            states=totals['states']
            status=('uncertain' if states['unknown'] or states['partial'] else 'in_progress' if states['dispatching'] else
                'paused' if states['paused'] else 'blocked' if states['blocked'] else
                'waiting_for_human_completion' if states['pending'] and all(s['waiting_on']=='human_task_completion' for s in steps if s['status']=='pending') else
                'scheduled' if states['pending'] else
                'stopped' if states['stopped'] else 'submissions_complete')
            return {'simulation_id':simulation_id,'proposal_id':simulation['proposal_id'],'mode':'SYNTHETIC_ONLY',
                'status':status,'assignments':proposal['population'],'steps':steps,'observations':observations,'totals':totals,
                'enrollments':[dict(r) for r in db.execute('SELECT * FROM engagement_enrollments WHERE organization=? AND simulation_id=? ORDER BY id',(organization,simulation_id))],
                'authority':'none','approval':'not_granted'}
