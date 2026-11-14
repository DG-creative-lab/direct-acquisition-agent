"""Bounded explicit simulation. Unknown submissions are observations, never retry instructions."""

import json

from acquisition.contracts import canonical, digest
from .domain import SimulationReceipt
from .ports import EngagementStore, SimulationTransport


class EngagementSimulator:
    def __init__(self, store: EngagementStore, email: SimulationTransport, calls: SimulationTransport):
        self.store, self.email, self.calls = store, email, calls

    def configuration(self):
        return {p.connection.channel:{'connection_id':p.connection.id,'configuration_id':p.configuration_id}
                for p in (self.email,self.calls)}

    def start(self, organization, request_id, proposal_id):
        return self.store.start(organization,request_id,proposal_id,self.configuration())

    def advance(self, organization, simulation_id, *, max_steps=18):
        if type(max_steps) is not int or not 1<=max_steps<=18: raise ValueError('Advance one to eighteen bounded simulated steps')
        for _ in range(max_steps):
            claim=self.store.claim(organization,simulation_id,self.configuration(),180)
            if claim is None: break
            provider=self.email if claim.intent['step']['channel']=='email' else self.calls
            try: receipt=provider.submit(json.loads(canonical(claim.intent)))
            except Exception:
                receipt=SimulationReceipt(claim.intent['effect_key'],digest(claim.intent),provider.connection.id,'unknown',None,None)
            self.store.settle(claim,receipt)
        return self.store.inspect(organization,simulation_id)

    def inspect(self, organization, simulation_id): return self.store.inspect(organization,simulation_id)

    def observe(self, organization, request_id, simulation_id, step_id, provider_effect_id, kind, occurred_at):
        return self.store.observe(organization,request_id,simulation_id,step_id,provider_effect_id,kind,occurred_at)

    def stop(self, organization, request_id, simulation_id): return self.store.stop(organization,request_id,simulation_id)
