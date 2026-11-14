"""Deterministic local proposal and independent screen adapter. No live model or provider account."""

import json


class OfflineChannelModel:
    def complete(self, request):
        name = request['tools'][0]['function']['name']
        if name=='read_channel_context': arguments = {}
        elif name in {'submit_contextual_email','submit_call_guidance'}:
            context = next(json.loads(m['content']) for m in request['messages'] if m['role']=='tool')
            repaired = request['messages'][-1]['role']=='user'
            frames = list(context['guidance']['frames'])
            arguments = {'context_id':context['context_id'],'rows':[
                {'recipient_context_id':r['recipient_context_id'],
                 'frame_key':frames[(frames.index(context['style'])+int(repaired)+index)%len(frames)],
                 'product_fact_id':context['product_facts']['facts'][index%len(context['product_facts']['facts'])]['id'],
                 'recipient_fact_ids':[f['fact_id'] for f in r['facts'][:2]]}
                for index,r in enumerate(context['recipients'])]}
        elif name=='record_channel_screen':
            context = json.loads(request['messages'][-1]['content'])
            arguments = {'candidate_hash':context['candidate_hash'],'rows':[
                {'recipient_context_id':r['recipient_context_id'],'verdict':'pass','reason':'none'} for r in context['rendered']]}
        else: raise ValueError('Unknown installed offline channel tool')
        return {'message':{'role':'assistant','tool_calls':[{'id':'offline-'+name,'type':'function',
            'function':{'name':name,'arguments':json.dumps(arguments)}}]},'usage':{'prompt_tokens':0,'completion_tokens':0},
            'provenance':'deterministic_offline_fixture_not_live_model'}
