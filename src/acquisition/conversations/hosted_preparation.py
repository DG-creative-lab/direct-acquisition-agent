"""Protected synthetic preparation using the existing conversation journey journal."""
from acquisition.contracts import Conflict, digest
from .domain import identity
from .ports import ConversationStore
from .sequence_journey import SequenceJourneys


class HostedPreparations:
    def __init__(self, organization: str, conversations: ConversationStore, journeys: SequenceJourneys, clock):
        identity(organization)
        self.organization, self.conversations, self.journeys, self.clock = organization, conversations, journeys, clock

    @staticmethod
    def command(profile_key, budget_pence, allow_generation):
        if type(profile_key) is not str or profile_key not in {'iwoca','fielddesk'}:
            raise ValueError('Choose an installed synthetic profile')
        if type(budget_pence) is not int or not 104 <= budget_pence <= 1_000_000:
            raise ValueError('Choose a bounded total synthetic budget')
        if allow_generation is not True:raise ValueError('Explicit synthetic generation consent is required')
        return {'schema':'hosted-synthetic-preparation/v1','profile_key':profile_key,
                'budget_pence':budget_pence,'allow_generation':True}

    @staticmethod
    def title(command):return 'Hosted synthetic preparation '+digest(command)

    @staticmethod
    def message(command):
        pounds, pence = divmod(command['budget_pence'],100)
        return ('Prepare a '+command['profile_key']+' email and human call sequence for UK contacts with a £'+
                str(pounds)+'.'+str(pence).zfill(2)+' total budget.')

    def start(self, request_id, profile_key, budget_pence, allow_generation):
        identity(request_id)
        command=self.command(profile_key,budget_pence,allow_generation)
        # The original request key reserves an exact immutable command before
        # message/journey admission. A lost response resumes these same keys.
        key='hosted_'+digest({'request_id':request_id})
        conversation=self.conversations.create(self.organization,key,self.title(command),self.clock())
        row=self.journeys.send(self.organization,conversation,'hosted-message-v1',0,self.message(command),True)
        return self.status(row['id'])

    def _owned(self, journey_id):
        identity(journey_id)
        row=self.journeys.store.get(self.organization,journey_id)
        frozen=row['inputs'];interpretation=frozen['interpretation']
        command=self.command(interpretation['profile_key'],interpretation['budget_pence'],frozen['allow_generation'])
        conversation=self.conversations.snapshot(self.organization,frozen['conversation_id'])
        if (conversation['title']!=self.title(command) or len(frozen['messages'])!=1 or
                frozen['messages'][0]['id']!='hosted-message-v1' or
                frozen['messages'][0]['content']!=self.message(command) or
                frozen['catalogue'].get('preparation_clock')!='real-invocation/v1' or
                frozen['mode']!='SYNTHETIC_ONLY' or frozen['model_config']['model']!='offline/channel-content-v1'):
            raise Conflict('Select an original hosted synthetic preparation')
        return row

    def status(self, journey_id):
        row=self._owned(journey_id)
        return {'receipt':{'schema':'hosted-synthetic-preparation-receipt/v1','journey_id':row['id'],
                          'conversation_id':row['inputs']['conversation_id'],
                          'command_fingerprint':digest(self.command(row['inputs']['interpretation']['profile_key'],
                              row['inputs']['interpretation']['budget_pence'],True)),
                          'mode':'SYNTHETIC_ONLY','authority':'none'},
                'progress':self.journeys.view(self.organization,journey_id) | {
                    'clock':'Real invocation time for preparation leases; all inputs and generation are synthetic.'}}

    def advance(self, journey_id, expected_stage):
        if type(expected_stage) is not int or not 0 <= expected_stage < 7:
            raise ValueError('Continue one displayed preparation stage')
        row=self._owned(journey_id)
        if row['stage'] < expected_stage:raise Conflict('Reload the current preparation stage')
        if row['stage'] > expected_stage:
            return {'observation':'already_advanced',**self.status(journey_id)}
        # Preparing is the only executable phase on this surface. Ready means
        # an unapproved subject exists; no approval or dispatch is exposed.
        if row['status']=='preparing':self.journeys.advance(self.organization,journey_id)
        return {'observation':'step_observed',**self.status(journey_id)}

    def stop(self, journey_id, request_id):
        identity(request_id)
        row=self._owned(journey_id)
        receipt=self.journeys.stop(self.organization,journey_id,'hosted-stop_'+digest(request_id),row['inputs']['revision'])
        return {'stop_receipt':receipt,**self.status(journey_id)}
