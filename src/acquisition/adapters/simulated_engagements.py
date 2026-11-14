"""Installed synthetic email and task transports. No network, credentials or real recipients."""

from acquisition.campaigns import SequenceConnection
from acquisition.contracts import Conflict, digest
from acquisition.engagements import SimulationReceipt


def synthetic_sequence_connections(organization, profile_key):
    domain=profile_key+'.example.invalid'
    return {'email':SequenceConnection(organization,profile_key,'email','synthetic-email','demo-email-'+profile_key,
                    'demo@'+domain,'reply@'+domain),
            'human_call':SequenceConnection(organization,profile_key,'human_call','synthetic-tasks','demo-tasks-'+profile_key,
                    'DEMO ONLY representative '+profile_key+'-rep-1','not_applicable')}


class SyntheticEngagementTransport:
    def __init__(self, connection, scenario='success'):
        if type(connection) is not SequenceConnection or scenario not in {'success','rejection','partial','timeout'}:
            raise ValueError('Select an installed synthetic transport scenario')
        self.connection,self.scenario=connection,scenario
        self.configuration_id='simulation_transport_'+digest({'connection':connection.id,'scenario':scenario,'version':'v1'})

    def submit(self, intent):
        step=intent['step']
        if (intent['mode']!='SYNTHETIC_ONLY' or intent['organization']!=self.connection.organization
                or step['connection_id']!=self.connection.id or step['channel']!=self.connection.channel):
            raise Conflict('Synthetic transport refuses a substituted connection or effect')
        row=step['content']['rendered']
        if self.connection.channel=='email':
            if not row['email']['to'].endswith('.invalid'): raise Conflict('Use exact synthetic recipients')
        elif not row['call']['contact'].startswith('DEMO ONLY DO NOT CALL:'):
            raise Conflict('Use demo human call tasks only')
        if self.scenario=='timeout': raise TimeoutError('Synthetic unknown provider outcome')
        status={'success':'accepted','rejection':'rejected','partial':'partial'}[self.scenario]
        effect_id='synthetic_provider_effect_'+digest(intent) if status in {'accepted','partial'} else None
        cost=step['unit_cost_pence'] if status=='accepted' else 0 if status=='rejected' else None
        return SimulationReceipt(intent['effect_key'],digest(intent),self.connection.id,status,effect_id,cost)
