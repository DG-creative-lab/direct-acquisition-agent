"""Bounded installed-language interpreter. Replace through its conversation-owned port."""

import re

from acquisition.conversations import explicit_budget, mentioned_profiles, effective_sequence_messages, sequence_literal_issue




class OfflineSequenceInterpreter:
    """Reviewed synthetic vocabulary, with explicit uncertainty rather than paid inference."""
    def interpret(self,messages,catalogue):
        result={'outcome':'clarification','profile_key':'','connection_key':'','budget_pence':None,'question':'','reason':''}
        messages=effective_sequence_messages(messages,catalogue)
        all_text=' '.join(m['content'] for m in messages)
        issue=sequence_literal_issue(messages)
        if issue:
            result.update(outcome='unsupported',reason=issue)
            return result
        # Resolve the latest mentioned company against the authoritative installed list.
        profiles=catalogue['profiles'];chosen=[]
        for message in reversed(messages):
            chosen=mentioned_profiles(message['content'],profiles)
            if chosen:break
        if len(chosen)!=1:
            result['question']='Which company is this for: '+', '.join(p['label'] for p in profiles)+'?'
            return result
        profile=chosen[0];result['profile_key']=profile['key']
        issue=sequence_literal_issue(messages,profile)
        if issue:
            result.update(outcome='unsupported',reason=issue)
            return result
        connections=[]
        for message in reversed(messages):
            body=message['content'].casefold()
            connections=[c for c in profile['connections'] if c['key'] in body or any(a in body for a in c['aliases'])]
            if connections:break
        if len(connections)>1:
            result['question']='Which source should I use: '+', '.join(c['label'] for c in connections)+'?'
            return result
        connection=connections[0] if connections else next(c for c in profile['connections'] if c['primary'])
        result['connection_key']=connection['key']
        budget=explicit_budget(messages)
        if budget is None or not 104<=budget['budget_pence']<=1_000_000:
            result['question']='What is the total synthetic sequence budget in GBP, between £1.04 and £10,000?'
            return result
        # The offline interpreter supports a deliberately bounded vocabulary.
        # Unknown material scope is not a reason to substitute a familiar campaign.
        remainder=all_text.casefold()
        for p in profiles:
            for alias in (*p['aliases'],p['key']):remainder=remainder.replace(alias.casefold(),' ')
        for c in profile['connections']:
            for alias in (*c['aliases'],c['key']):remainder=remainder.replace(alias.casefold(),' ')
        remainder=re.sub(r'(?:£\s*|\bgbp\s+)\d[\d,.]*',' ',remainder)
        words=set(re.findall(r'[a-z]+',remainder))
        words={w for w in words if not (len(w)>=5 and len(mentioned_profiles(w,profiles))==1)}
        supported=set('prepare create build plan run simulate start please a an the for of to from using use with and or then total budget campaign acquisition response experiment sequence multichannel multi channel contextual personalised personalized personalisation email emails e mail mails human call calls phone telephone script scripts followup followups follow up uk united kingdom gbp primary crm company profile connection audience strategy market country currency all installed eligible contacts accounts customers recipients synthetic demonstration demo offline practical explore yes generate generation consent i want need we our business product software visit planner flexi loan lending request now change make set instead is it'.split())
        if words-supported:
            result.update(outcome='unsupported',reason='This offline interpreter cannot verify the additional requested scope: '+', '.join(sorted(words-supported)[:6])+'. Use an installed company, UK contacts, primary CRM, email/call/follow-up and an explicit GBP budget.')
            return result
        result.update(outcome='sequence',budget_pence=budget['budget_pence'])
        return result
