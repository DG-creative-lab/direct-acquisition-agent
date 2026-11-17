"""Authoritative revision-bound continuation, separate from immutable channel artifacts."""

import json
from contextlib import contextmanager
from uuid import uuid4

from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.audiences import ContactConnection
from acquisition.conversations import journey_commands, identity, revision_number, text
from .admission_guard import require_legacy_writer
from .conversations import scoped_conversation, messages, append_message
from .execution import require_active, account


SEQUENCE_JOURNEYS = '''
CREATE TABLE IF NOT EXISTS sequence_journeys (
 organization TEXT NOT NULL,id TEXT NOT NULL,conversation_id TEXT NOT NULL,revision INTEGER NOT NULL,
 request_id TEXT NOT NULL,inputs TEXT NOT NULL,state TEXT NOT NULL,
 PRIMARY KEY(organization,id),UNIQUE(organization,conversation_id,revision),UNIQUE(organization,request_id),
 FOREIGN KEY(organization,conversation_id) REFERENCES conversations(organization,id));
CREATE TABLE IF NOT EXISTS sequence_journey_bindings (
 organization TEXT NOT NULL,request_id TEXT NOT NULL,owner_organization TEXT NOT NULL,journey_id TEXT NOT NULL,role TEXT NOT NULL,
 PRIMARY KEY(organization,request_id),
 FOREIGN KEY(owner_organization,journey_id) REFERENCES sequence_journeys(organization,id));
CREATE TABLE IF NOT EXISTS sequence_journey_commands (
 organization TEXT NOT NULL,request_id TEXT NOT NULL,inputs TEXT NOT NULL,receipt TEXT NOT NULL,
 PRIMARY KEY(organization,request_id));
CREATE TABLE IF NOT EXISTS sequence_journey_events (
 organization TEXT NOT NULL,id TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(organization,id));
CREATE TRIGGER IF NOT EXISTS sequence_journeys_identity_immutable BEFORE UPDATE OF
 organization,id,conversation_id,revision,request_id,inputs ON sequence_journeys
 BEGIN SELECT RAISE(ABORT,'Immutable conversation sequence inputs'); END;
'''
for _table in ('sequence_journeys','sequence_journey_bindings','sequence_journey_commands','sequence_journey_events'):
    SEQUENCE_JOURNEYS += f'''
CREATE TRIGGER IF NOT EXISTS {_table}_no_delete BEFORE DELETE ON {_table}
 BEGIN SELECT RAISE(ABORT,'Immutable conversation sequence history'); END;
CREATE TRIGGER IF NOT EXISTS {_table}_no_replace BEFORE INSERT ON {_table}
 WHEN EXISTS(SELECT 1 FROM {_table} WHERE organization=NEW.organization AND {'request_id=NEW.request_id' if _table in {'sequence_journey_bindings','sequence_journey_commands'} else 'id=NEW.id'})
 BEGIN SELECT RAISE(ABORT,'Immutable conversation sequence history'); END;
'''
    if _table!='sequence_journeys':
        SEQUENCE_JOURNEYS += f"CREATE TRIGGER IF NOT EXISTS {_table}_no_update BEFORE UPDATE ON {_table} BEGIN SELECT RAISE(ABORT,'Immutable conversation sequence history'); END;\n"
SEQUENCE_JOURNEYS += 'PRAGMA user_version=23;'


def validate_sequence_journey_schema(db):
    for table,columns in {
        'sequence_journeys':'organization,id,conversation_id,revision,request_id,inputs,state',
        'sequence_journey_bindings':'organization,request_id,owner_organization,journey_id,role',
        'sequence_journey_commands':'organization,request_id,inputs,receipt',
        'sequence_journey_events':'organization,id,payload',
    }.items():db.execute('SELECT '+columns+' FROM '+table+' LIMIT 0')


def saved_journey(db, organization, journey_id):
    if db.execute('PRAGMA user_version').fetchone()[0]<23:raise Conflict('Conversation sequence history is unavailable in this schema')
    row=db.execute('SELECT * FROM sequence_journeys WHERE organization=? AND id=?',(organization,journey_id)).fetchone()
    if row is None:raise NotFound('Conversation sequence is unavailable in this organization')
    frozen=json.loads(row['inputs']);state=json.loads(row['state'])
    if (frozen.get('id')!=journey_id or frozen.get('organization')!=organization
            or frozen.get('conversation_id')!=row['conversation_id'] or frozen.get('revision')!=row['revision']
            or frozen.get('request_id')!=row['request_id']
            or journey_id!='journey_'+digest({k:v for k,v in frozen.items() if k!='id'})):
        raise Conflict('Conversation sequence input integrity failure')
    return {'id':journey_id,'organization':organization,'inputs':frozen,**state}


def require_journey(db, organization, journey_id):
    value=saved_journey(db,organization,journey_id)
    frozen=value['inputs']
    if (scoped_conversation(db,organization,frozen['conversation_id'])['revision']!=frozen['revision']
            or messages(db,organization,frozen['conversation_id'])!=frozen['messages']):
        raise Conflict('Conversation changed; this sequence is historical')
    require_active(db,organization,frozen['conversation_id'],frozen['revision'])
    if value['status'] in {'cancelled','historical','clarification','unsupported','consent_required','blocked'}:
        raise Conflict('Conversation sequence is stopped, incomplete or blocked')
    if frozen['allow_generation'] is not True:raise Conflict('This revision has no bounded generation consent')
    return value


def journey_command(db, organization, request_id, *, required=False, current=True):
    if db.execute('PRAGMA user_version').fetchone()[0]<23:
        if required:raise Conflict('Conversation sequence provenance is unavailable')
        return None
    row=db.execute('SELECT * FROM sequence_journey_bindings WHERE organization=? AND request_id=?',
        (organization,request_id)).fetchone()
    if row is None:
        if required:raise Conflict('Restore the original conversation sequence command binding')
        return None
    journey=(require_journey if current else saved_journey)(db,row['owner_organization'],row['journey_id'])
    if (journey['inputs']['native_organization']!=organization
            or journey_commands(journey['id']).get(row['role'])!=request_id):
        raise Conflict('Conversation sequence command differs from its frozen scope')
    return {'schema':'conversation-sequence-origin/v1','organization':row['owner_organization'],
        'conversation_id':journey['inputs']['conversation_id'],'revision':journey['inputs']['revision'],
        'journey_id':journey['id'],'request_id':request_id}


def require_journey_origin(db, organization, origin, *, current=True):
    if journey_command(db,organization,origin['request_id'],required=True,current=current)!=origin:
        raise Conflict('Conversation sequence origin differs from its original native command')


def journey_owned_source(db,organization,source_id,connection_id=None,*,journey_ids=None):
    """Derive ownership from frozen discovery, independently of assessment keys."""
    if db.execute('PRAGMA user_version').fetchone()[0]<23:return False
    if connection_id is None:
        source=db.execute('SELECT payload FROM contact_sources WHERE organization=? AND id=?',
            (organization,source_id)).fetchone()
        if source is None:raise Conflict('Restore the original scoped contact source')
        connection_id=ContactConnection(**json.loads(source['payload'])['connection']).id
    for row in db.execute("SELECT organization,id FROM sequence_journeys WHERE json_extract(inputs,'$.native_organization')=?",(organization,)):
        if journey_ids is not None and row['id'] not in journey_ids:continue
        frozen=saved_journey(db,row['organization'],row['id'])['inputs']
        profile=next(p for p in frozen['catalogue']['profiles'] if p['key']==frozen['interpretation']['profile_key'])
        connection=next(c for c in profile['connections'] if c['key']==frozen['interpretation']['connection_key'])
        if source_id==connection['source_id'] or connection_id==connection['connection_id']:return True
    return False


def assessment_journey_origin(db,organization,request_id,snapshot):
    origin=journey_command(db,organization,request_id)
    if not journey_owned_source(db,organization,snapshot.id,snapshot.connection.id) and origin is None:return None
    if origin is None:raise Conflict('Contact reassessment must retain its original conversation source binding')
    row=require_journey(db,origin['organization'],origin['journey_id'])
    commands=journey_commands(row['id'])
    if request_id not in (commands['email-assessment'],commands['call-assessment']):
        raise Conflict('Use the original bound assessment command')
    profile=next(p for p in row['inputs']['catalogue']['profiles'] if p['key']==row['inputs']['interpretation']['profile_key'])
    connection=next(c for c in profile['connections'] if c['key']==row['inputs']['interpretation']['connection_key'])
    if snapshot.id!=connection['source_id']:raise Conflict('Assessment differs from its frozen conversation source')
    return origin


def recipient_journey_origin(db,organization,request_id,request,*,journey_ids=None):
    """Assessment provenance survives a new recipient-context request key."""
    origin=journey_command(db,organization,request_id)
    if db.execute('PRAGMA user_version').fetchone()[0]<23:return None
    assessment=request.assessment_id if not isinstance(request,dict) else request['assessment_id']
    source=db.execute("SELECT json_extract(payload,'$.request.source_id') FROM contact_assessments WHERE organization=? AND id=?",
        (organization,assessment)).fetchone()
    if source is None:raise Conflict('Restore the original scoped contact assessment')
    if not journey_owned_source(db,organization,source[0],journey_ids=journey_ids) and origin is None:return None
    if origin is None:raise Conflict('Recipient context must retain its original conversation assessment binding')
    row=require_journey(db,origin['organization'],origin['journey_id'])
    commands=journey_commands(row['id'])
    channels=[channel for channel in ('email','human_call')
              if request_id in [commands[channel+'-context-'+str(i)] for i in range(6)]]
    if len(channels)!=1:raise Conflict('Use the original bound recipient-context command')
    channel=channels[0]
    key=commands['email-assessment' if channel=='email' else 'call-assessment']
    source=db.execute('SELECT receipt FROM contact_commands WHERE organization=? AND request_id=?',
        (organization,key)).fetchone()
    if source is None or json.loads(source['receipt']).get('assessment_id')!=assessment:
        raise Conflict('Recipient context differs from its original conversation assessment')
    return origin


def channel_journey_origin(db,organization,request_id,command,*,journey_ids=None):
    """A new generation key cannot detach conversation-owned recipient inputs."""
    origin=journey_command(db,organization,request_id)
    sources=[]
    for key in command.recipient_requests:
        context=db.execute("""SELECT r.payload FROM recipient_context_commands c JOIN recipient_contexts r
            ON r.organization=c.organization AND r.id=json_extract(c.receipt,'$.context_id')
            WHERE c.organization=? AND c.request_id=?""",(organization,key)).fetchone()
        source=(recipient_journey_origin(db,organization,key,json.loads(context['payload'])['request'],journey_ids=journey_ids)
                if context is not None else journey_command(db,organization,key))
        sources.append(source)
    bound=[o for o in sources if o is not None]
    if not bound and origin is None:return None
    if origin is None or len(bound)!=len(sources):
        raise Conflict('Channel preparation must retain its original conversation binding')
    root={k:v for k,v in origin.items() if k!='request_id'}
    if any({k:v for k,v in source.items() if k!='request_id'}!=root for source in bound):
        raise Conflict('Recipient context belongs to a different conversation sequence')
    row=require_journey(db,origin['organization'],origin['journey_id'])
    commands=journey_commands(row['id'])
    stage=next((s for s in ('initial','call','followup') if commands[s]==request_id),None)
    if stage is None:raise Conflict('Use the original bound channel stage command')
    channel='human_call' if stage=='call' else 'email'
    if (command.profile_key!=row['inputs']['interpretation']['profile_key'] or command.channel!=channel
            or list(command.recipient_requests)!=row['outputs'].get(channel+'-contexts')
            or command.style!=('practical' if stage=='followup' else 'explore')
            or command.parent_id!=(row['outputs'].get('initial-artifact') if stage=='followup' else None)):
        raise Conflict('Channel generation differs from its frozen conversation stage')
    return origin


def channel_admission_journeys(db,organization,context):
    """Exclude later ownership only when independent admission is evidenced."""
    if context.get('journey') is not None or db.execute('PRAGMA user_version').fetchone()[0]<23:return None
    identity='context_'+digest({'organization':organization,**context})
    admitted=db.execute("""SELECT p.run_id FROM channel_preparations p
        JOIN runs r ON r.id=p.run_id AND r.organization=p.organization
        WHERE p.organization=? AND p.request_id=? AND p.context_id=?""",
        (organization,context['preparation_request_id'],identity)).fetchone()
    if admitted is None:return None
    applicable=[]
    for row in db.execute("SELECT organization,id FROM sequence_journeys WHERE json_extract(inputs,'$.native_organization')=?",(organization,)):
        saved_journey(db,row['organization'],row['id'])
        event=db.execute("""SELECT payload FROM sequence_journey_events WHERE organization=?
            AND json_extract(payload,'$.kind')='requested'
            AND json_extract(payload,'$.data.journey_id')=?""",(row['organization'],row['id'])).fetchone()
        data=json.loads(event['payload'])['data'] if event is not None else {}
        prior=data.get('prior_channel_runs')
        if prior is not None:
            if type(prior) is not list or any(type(r) is not list or len(r)!=2 or any(type(v) is not str for v in r) for r in prior):
                raise Conflict('Restore the original channel admission ordering receipt')
            if [admitted['run_id'],identity] in prior:continue
        applicable.append(row['id'])
    return applicable


def require_channel_context_origin(db,organization,context):
    """Reconstruct saved input ownership even when an old context has no origin."""
    from acquisition.creative import ChannelContentRequest
    command=ChannelContentRequest(**(context['command'] | {'recipient_requests':tuple(context['command']['recipient_requests'])}))
    origin=channel_journey_origin(db,organization,context['preparation_request_id'],command,
        journey_ids=channel_admission_journeys(db,organization,context))
    if origin!=context.get('journey'):
        raise Conflict('Channel context differs from its derived conversation origin')


def prior_standalone_channel_run(db,organization,run_id,owner,conversation_id):
    """Use the continuation ownership decision for conversation accounting too."""
    from .creative import read_context
    if db.execute('PRAGMA user_version').fetchone()[0]<23:return False
    preparation=db.execute('SELECT context_id FROM channel_preparations WHERE organization=? AND run_id=?',
        (organization,run_id)).fetchone()
    if preparation is None:return False
    context=read_context(db,organization,preparation['context_id'])
    if context.get('journey') is not None:return False
    keys=[context['preparation_request_id'],*context['command']['recipient_requests']]
    if any(journey_command(db,organization,key,current=False) is not None for key in keys):return False
    relevant={r['id'] for r in db.execute("""SELECT id FROM sequence_journeys
        WHERE organization=? AND conversation_id=? AND json_extract(inputs,'$.native_organization')=?""",
        (owner,conversation_id,organization))}
    applicable=channel_admission_journeys(db,organization,context)
    if not relevant or applicable is None or relevant.intersection(applicable):return False
    # A later receipt cannot erase an earlier source owner or a native binding.
    require_channel_context_origin(db,organization,context)
    return True


def sequence_journey_origin(db,organization,request_id,request):
    from .creative import read_context
    origins=[]
    for key in ('initial_content','call_content','followup_content'):
        native=getattr(request,key) if not isinstance(request,dict) else request[key]
        row=db.execute('SELECT context_id FROM channel_preparations WHERE organization=? AND request_id=?',
            (organization,native)).fetchone()
        context=read_context(db,organization,row[0]) if row else {}
        if 'journey' in context:origins.append(context['journey'])
    if not origins:return None
    root={k:v for k,v in origins[0].items() if k!='request_id'}
    if len(origins)!=3 or any({k:v for k,v in origin.items() if k!='request_id'}!=root for origin in origins):
        raise Conflict('All content stages must retain the same conversation sequence origin')
    expected=journey_commands(root['journey_id'])
    if request_id!=expected['sequence'] or [o['request_id'] for o in origins]!=[expected[k] for k in ('initial','call','followup')]:
        raise Conflict('A new command cannot detach content from its admitted conversation sequence')
    for origin in origins:require_journey_origin(db,organization,origin)
    return journey_command(db,organization,request_id,required=True)


def require_journey_approval(db,organization,proposal,approval):
    origin=sequence_journey_origin(db,organization,proposal['request_id'],proposal['request'])
    if origin is None:return
    journey=require_journey(db,origin['organization'],origin['journey_id'])
    confirmation=journey['outputs'].get('approval_request_id')
    row=db.execute('SELECT inputs FROM sequence_journey_commands WHERE organization=? AND request_id=?',
        (origin['organization'],confirmation)).fetchone() if confirmation else None
    inputs=json.loads(row[0]) if row else {}
    if (inputs.get('kind')!='approve_sequence' or inputs.get('journey_id')!=journey['id']
            or inputs.get('revision')!=origin['revision'] or inputs.get('subject_id')!=approval['subject_id']
            or inputs.get('actor_generation')!=approval['actor_generation']
            or approval['actor']!='local-reviewer' or approval['decision']!='approve'
            or approval['request_id']!=journey_commands(journey['id'])['review-approve']):
        raise Conflict('The native approval lacks its exact current conversation confirmation')


@contextmanager
def journey_transaction(database,organization,request_id):
    """Fence only native business commands; late model/provider observations stay recordable."""
    with database.transaction() as db:
        origin=journey_command(db,organization,request_id)
        yield db
        if origin is not None:require_journey_origin(db,organization,origin)


class SqliteSequenceJourneys:
    def __init__(self,database,clock):self.database,self.clock=database,clock

    def _event(self,db,organization,kind,value):
        db.execute('INSERT INTO sequence_journey_events VALUES(?,?,?)',
            (organization,'journey_event_'+uuid4().hex,canonical({'kind':kind,'at':self.clock(),'data':value})))

    def source(self,organization,conversation_id,revision):
        with self.database.connect() as db:
            db.execute('BEGIN')
            row=scoped_conversation(db,organization,conversation_id)
            if row['revision']!=revision:raise Conflict('Conversation changed before sequence admission')
            if revision>0:require_active(db,organization,conversation_id,revision)
            return {'messages':messages(db,organization,conversation_id)}

    def request(self,organization,conversation_id,request_id,revision,allow_generation):
        for value in (organization,conversation_id,request_id):identity(value)
        revision_number(revision)
        if type(allow_generation) is not bool:raise ValueError('Choose explicit bounded generation consent')
        with self.database.connect() as db:
            scoped_conversation(db,organization,conversation_id)
            if db.execute('PRAGMA user_version').fetchone()[0]<23:raise Conflict('Migrate the live store before conversation sequence admission')
            row=db.execute('SELECT id FROM sequence_journeys WHERE organization=? AND request_id=?',
                (organization,request_id)).fetchone()
            if row:
                value=saved_journey(db,organization,row[0]);frozen=value['inputs']
                if (frozen['conversation_id'],frozen['revision'],frozen['allow_generation'])!=(conversation_id,revision,allow_generation):
                    raise Conflict('Sequence request already binds different exact inputs')
                return value|{'observation':'historical_receipt'}
            prior=db.execute('SELECT id FROM sequence_journeys WHERE organization=? AND conversation_id=? AND revision=?',
                (organization,conversation_id,revision)).fetchone()
            if prior:raise Conflict('This revision already has a sequence request; resume its original identity')
        return None

    def admit(self,organization,frozen):
        with self.database.transaction() as db:
            return self._admit(db,organization,frozen)

    def admit_message(self,organization,frozen,revision,request_id,content):
        with self.database.transaction() as db:
            old=db.execute('SELECT id FROM sequence_journeys WHERE organization=? AND request_id=?',
                (organization,frozen['request_id'])).fetchone()
            if old:
                value=saved_journey(db,organization,old[0]);message=value['inputs']['messages'][-1]
                if (message['id'],message['revision'],message['content'],value['inputs']['allow_generation'])!=(request_id,revision+1,content,frozen['allow_generation']):
                    raise Conflict('Sequence message already binds different exact inputs')
                return value
            append_message(db,organization,frozen['conversation_id'],request_id,revision,content,frozen['created_at'])
            return self._admit(db,organization,frozen)

    def _admit(self,db,organization,frozen):
        require_legacy_writer(db)
        source=scoped_conversation(db,organization,frozen['conversation_id'])
        existing=db.execute('SELECT id FROM sequence_journeys WHERE organization=? AND request_id=?',
            (organization,frozen['request_id'])).fetchone()
        if existing:
            old=saved_journey(db,organization,existing[0])
            if old['inputs']!=frozen:raise Conflict('Sequence admission changed while resolving the request')
            return old
        if db.execute('SELECT 1 FROM sequence_journeys WHERE organization=? AND conversation_id=? AND revision=?',(organization,frozen['conversation_id'],frozen['revision'])).fetchone():
            raise Conflict('This revision already has its original sequence admission')
        if source['revision']!=frozen['revision'] or messages(db,organization,frozen['conversation_id'])!=frozen['messages']:
            raise Conflict('Conversation changed before sequence admission committed')
        if db.execute('SELECT count(*) FROM sequence_journeys WHERE organization=? AND conversation_id=?',
                (organization,frozen['conversation_id'])).fetchone()[0]>=6:
            raise Conflict('The six-request conversation sequence allowance is exhausted')
        require_active(db,organization,frozen['conversation_id'],frozen['revision'])
        account(db,organization,frozen['conversation_id'])
        outcome=frozen['interpretation']['outcome']
        status=outcome if outcome!='sequence' else 'preparing' if frozen['allow_generation'] else 'consent_required'
        state={'status':status,'stage':0,'outputs':{},'detail':frozen['interpretation']['question'] or frozen['interpretation']['reason'] or None}
        db.execute('INSERT INTO sequence_journeys VALUES(?,?,?,?,?,?,?)',(organization,frozen['id'],
            frozen['conversation_id'],frozen['revision'],frozen['request_id'],canonical(frozen),canonical(state)))
        if outcome=='sequence':
            for role,key in journey_commands(frozen['id']).items():
                db.execute('INSERT INTO sequence_journey_bindings VALUES(?,?,?,?,?)',
                    (frozen['native_organization'],key,organization,frozen['id'],role))
        prior_channel_runs=[list(r) for r in db.execute(
            'SELECT run_id,context_id FROM channel_preparations WHERE organization=? ORDER BY run_id',
            (frozen['native_organization'],))]
        self._event(db,organization,'requested',{'journey_id':frozen['id'],'status':status,
            'prior_channel_runs':prior_channel_runs})
        return saved_journey(db,organization,frozen['id'])

    def get(self,organization,journey_id):
        with self.database.connect() as db:return saved_journey(db,organization,journey_id)

    def current(self,organization,journey_id):
        with self.database.connect() as db:
            value=saved_journey(db,organization,journey_id)
            frozen=value['inputs']
            try:
                if (scoped_conversation(db,organization,frozen['conversation_id'])['revision']!=frozen['revision']
                        or messages(db,organization,frozen['conversation_id'])!=frozen['messages']):
                    raise Conflict('Historical sequence source')
                require_active(db,organization,frozen['conversation_id'],frozen['revision'])
            except (Conflict,ValueError):return value|{'current':False}
            return value|{'current':True}

    def listing(self,organization,conversation_id):
        with self.database.connect() as db:
            scoped_conversation(db,organization,conversation_id)
            if db.execute('PRAGMA user_version').fetchone()[0]<23:return []
            return [saved_journey(db,organization,r[0]) for r in db.execute(
                'SELECT id FROM sequence_journeys WHERE organization=? AND conversation_id=? ORDER BY rowid',
                (organization,conversation_id))]

    def pending(self,organization):
        with self.database.connect() as db:
            if db.execute('PRAGMA user_version').fetchone()[0]<23:return []
            return [r[0] for r in db.execute("""SELECT j.id FROM sequence_journeys j
                JOIN conversations c ON c.organization=j.organization AND c.id=j.conversation_id AND c.revision=j.revision
                WHERE j.organization=? AND json_extract(j.state,'$.status') IN ('preparing','approving','approved','simulating')
                ORDER BY j.rowid""",(organization,))]

    def progress(self,organization,prior,result):
        if set(result)-{'status','stage','outputs','detail'}:raise ValueError('Unsupported sequence continuation fields')
        with self.database.transaction() as db:
            current=require_journey(db,organization,prior['id'])
            if any(current[k]!=prior[k] for k in ('stage','status','outputs')):
                return current
            state={k:current[k] for k in ('status','stage','outputs','detail')}|result
            if all(state[k]==current[k] for k in state):return current
            db.execute('UPDATE sequence_journeys SET state=? WHERE organization=? AND id=?',
                (canonical(state),organization,prior['id']))
            self._event(db,organization,'progress',{'journey_id':prior['id'],'status':state['status'],'stage':state['stage']})
            return saved_journey(db,organization,prior['id'])

    def block(self,organization,journey_id,reason):
        with self.database.transaction() as db:
            value=saved_journey(db,organization,journey_id)
            if value['status'] in {'cancelled','complete','blocked'}:return value
            frozen=value['inputs']
            if scoped_conversation(db,organization,frozen['conversation_id'])['revision']!=frozen['revision']:return value
            state={k:value[k] for k in ('status','stage','outputs','detail')}
            state|={'status':'blocked','detail':reason[:600]}
            db.execute('UPDATE sequence_journeys SET state=? WHERE organization=? AND id=?',(canonical(state),organization,journey_id))
            self._event(db,organization,'blocked',{'journey_id':journey_id,'detail':state['detail']})
            return saved_journey(db,organization,journey_id)

    def stop(self,organization,journey_id,request_id,revision):
        for value in (organization,journey_id,request_id):identity(value)
        revision_number(revision)
        inputs={'kind':'stop_sequence','journey_id':journey_id,'revision':revision}
        with self.database.transaction() as db:
            require_legacy_writer(db)
            old=db.execute('SELECT inputs,receipt FROM sequence_journey_commands WHERE organization=? AND request_id=?',
                (organization,request_id)).fetchone()
            if old:
                if json.loads(old['inputs'])!=inputs:raise Conflict('Stop request already binds different exact inputs')
                return json.loads(old['receipt'])|{'observation':'historical_receipt'}
            value=saved_journey(db,organization,journey_id)
            if value['inputs']['revision']!=revision or scoped_conversation(db,organization,value['inputs']['conversation_id'])['revision']!=revision:
                raise Conflict('Stop confirmation is historical')
            state={k:value[k] for k in ('status','stage','outputs','detail')}|{'status':'cancelled','detail':'Sequence stopped by the user.'}
            db.execute('UPDATE sequence_journeys SET state=? WHERE organization=? AND id=?',(canonical(state),organization,journey_id))
            receipt={'journey_id':journey_id,'status':'cancelled','authority':'none'}
            db.execute('INSERT INTO sequence_journey_commands VALUES(?,?,?,?)',(organization,request_id,canonical(inputs),canonical(receipt)))
            self._event(db,organization,'cancelled',receipt)
            return receipt

    def begin_approval(self,organization,journey_id,request_id,revision,subject_id,reason):
        from .actors import require_actor
        for value in (organization,journey_id,request_id,subject_id):identity(value)
        revision_number(revision);text(reason,600)
        base={'kind':'approve_sequence','journey_id':journey_id,'revision':revision,
            'subject_id':subject_id,'reason':reason}
        with self.database.transaction() as db:
            require_legacy_writer(db)
            old=db.execute('SELECT inputs FROM sequence_journey_commands WHERE organization=? AND request_id=?',
                (organization,request_id)).fetchone()
            if old:
                saved=json.loads(old[0])
                if {k:v for k,v in saved.items() if k!='actor_generation'}!=base:
                    raise Conflict('Approval confirmation already binds different exact inputs')
                return saved_journey(db,organization,journey_id)
            current=require_journey(db,organization,journey_id)
            if (current['inputs']['revision']!=revision or current['status']!='ready'
                    or current['outputs'].get('subject_id')!=subject_id or current['outputs'].get('approval_request_id')):
                raise Conflict('Approve the exact currently displayed unapproved sequence')
            actor=require_actor(db,current['inputs']['native_organization'],'local-reviewer','reviewer')
            inputs=base|{'actor_generation':actor['generation']}
            receipt={'journey_id':journey_id,'subject_id':subject_id,'observation':'approval_confirmation_saved',
                'authority':'none'}
            db.execute('INSERT INTO sequence_journey_commands VALUES(?,?,?,?)',(organization,request_id,canonical(inputs),canonical(receipt)))
            outputs=current['outputs']|{'approval_request_id':request_id}
            state={'status':'approving','stage':current['stage'],'outputs':outputs,'detail':None}
            db.execute('UPDATE sequence_journeys SET state=? WHERE organization=? AND id=?',(canonical(state),organization,journey_id))
            self._event(db,organization,'approval_confirmation_saved',receipt)
            require_journey(db,organization,journey_id)
            return saved_journey(db,organization,journey_id)

    def approval_intent(self,organization,journey_id):
        with self.database.connect() as db:
            current=saved_journey(db,organization,journey_id)
            key=current['outputs'].get('approval_request_id')
            row=db.execute('SELECT inputs FROM sequence_journey_commands WHERE organization=? AND request_id=?',
                (organization,key)).fetchone() if key else None
            if row is None:raise Conflict('The original human approval confirmation is unavailable')
            inputs=json.loads(row[0])
            if (inputs.get('kind')!='approve_sequence' or inputs.get('journey_id')!=journey_id
                    or inputs.get('subject_id')!=current['outputs'].get('subject_id')
                    or inputs.get('revision')!=current['inputs']['revision']):
                raise Conflict('Approval confirmation differs from its exact journey source')
            return inputs

    def begin_task_observation(self,organization,journey_id,request_id,revision,step_id):
        for value in (organization,journey_id,request_id,step_id):identity(value)
        revision_number(revision)
        inputs={'kind':'task_completed','journey_id':journey_id,'revision':revision,'step_id':step_id}
        with self.database.transaction() as db:
            require_legacy_writer(db)
            old=db.execute('SELECT inputs FROM sequence_journey_commands WHERE organization=? AND request_id=?',
                (organization,request_id)).fetchone()
            if old:
                saved=json.loads(old[0])
                if {k:v for k,v in saved.items() if k!='occurred_at'}!=inputs:raise Conflict('Task observation already binds different exact inputs')
                return saved
            row=require_journey(db,organization,journey_id)
            if row['inputs']['revision']!=revision or row['status'] not in {'simulating','awaiting_human'}:
                raise Conflict('The human task observation is historical or not yet applicable')
            previous=db.execute("""SELECT inputs FROM sequence_journey_commands WHERE organization=?
                AND json_extract(inputs,'$.kind')='task_completed' AND json_extract(inputs,'$.journey_id')=?
                AND json_extract(inputs,'$.step_id')=? ORDER BY rowid LIMIT 1""",(organization,journey_id,step_id)).fetchone()
            # A stale tab may use a second key for the same accepted human task.
            # Preserve the first explicit observation time rather than fabricating another.
            occurred_at=json.loads(previous[0])['occurred_at'] if previous else self._simulation_time(db,organization,journey_id)
            inputs=inputs|{'occurred_at':occurred_at}
            db.execute('INSERT INTO sequence_journey_commands VALUES(?,?,?,?)',
                (organization,request_id,canonical(inputs),canonical({'observation':'task_observation_requested','authority':'none'})))
            state={k:row[k] for k in ('status','stage','outputs','detail')}|{'status':'simulating','detail':None}
            db.execute('UPDATE sequence_journeys SET state=? WHERE organization=? AND id=?',
                (canonical(state),organization,journey_id))
            return inputs

    def task_intents(self,organization,journey_id):
        with self.database.connect() as db:
            saved_journey(db,organization,journey_id)
            return [json.loads(r['inputs'])|{'request_id':r['request_id']} for r in db.execute(
                "SELECT request_id,inputs FROM sequence_journey_commands WHERE organization=? AND json_extract(inputs,'$.kind')='task_completed' AND json_extract(inputs,'$.journey_id')=? ORDER BY rowid",
                (organization,journey_id))]

    def _simulation_time(self,db,organization,journey_id):
        from acquisition.campaigns import sequence_time
        value=saved_journey(db,organization,journey_id)
        point=value['inputs']['created_at']
        for row in db.execute("SELECT payload FROM sequence_journey_events WHERE organization=? AND json_extract(payload,'$.kind')='clock_advanced' AND json_extract(payload,'$.data.journey_id')=? ORDER BY rowid",
                (organization,journey_id)):
            data=json.loads(row[0])['data'];sequence_time(data['at'])
            if not point<data['at']<value['inputs']['created_at']+7*86400:
                raise Conflict('Synthetic simulation clock history is inconsistent')
            point=data['at']
        now=self.clock();sequence_time(now)
        return max(now,point)

    def simulation_time(self,organization,journey_id):
        with self.database.connect() as db:return self._simulation_time(db,organization,journey_id)

    def advance_time(self,organization,journey_id):
        with self.database.transaction() as db:
            value=require_journey(db,organization,journey_id)
            native=value['inputs']['native_organization'];simulation=value['outputs'].get('simulation_id')
            if not simulation:raise Conflict('A bound simulation is required to advance synthetic time')
            if db.execute("SELECT 1 FROM engagement_steps WHERE organization=? AND simulation_id=? AND status='dispatching'",(native,simulation)).fetchone():
                return
            now=self._simulation_time(db,organization,journey_id)
            due=db.execute("SELECT MIN(due_at) FROM engagement_steps WHERE organization=? AND simulation_id=? AND status='pending' AND due_at>?",
                (native,simulation,now)).fetchone()[0]
            if due is not None:
                if due>=value['inputs']['created_at']+7*86400:raise Conflict('Synthetic clock cannot outlive the sequence')
                self._event(db,organization,'clock_advanced',{'journey_id':journey_id,'at':due})

    def interaction(self,organization,conversation_id,journey_id,request_id,revision,content,*,stop=False):
        """Archive an exact status question without changing the preparation revision."""
        for value in (organization,conversation_id,journey_id,request_id):identity(value)
        revision_number(revision);text(content)
        if type(stop) is not bool:raise ValueError('Choose an explicit stop action')
        inputs={'kind':'sequence_stop_message' if stop else 'sequence_inspection','conversation_id':conversation_id,'journey_id':journey_id,
                'revision':revision,'content':content}
        with self.database.transaction() as db:
            require_legacy_writer(db)
            old=db.execute('SELECT inputs,receipt FROM sequence_journey_commands WHERE organization=? AND request_id=?',
                (organization,request_id)).fetchone()
            if old:
                if {k:v for k,v in json.loads(old['inputs']).items() if k!='journey_id'}!={k:v for k,v in inputs.items() if k!='journey_id'}:
                    raise Conflict('Conversation question already binds different inputs')
                return json.loads(old['receipt'])
            value=saved_journey(db,organization,journey_id)
            if (value['inputs']['conversation_id']!=conversation_id or value['inputs']['revision']!=revision
                    or scoped_conversation(db,organization,conversation_id)['revision']!=revision):
                raise Conflict('The conversation changed before this question was saved')
            if stop:
                state={k:value[k] for k in ('status','stage','outputs','detail')}|{'status':'cancelled','detail':'Sequence stopped by the user.'}
                db.execute('UPDATE sequence_journeys SET state=? WHERE organization=? AND id=?',(canonical(state),organization,journey_id))
                self._event(db,organization,'cancelled',{'journey_id':journey_id,'request_id':request_id})
            receipt={'journey_id':journey_id,'revision':revision,'authority':'none',
                     'content':'This sequence is stopped. In-flight observations remain recordable.' if stop else 'The current sequence status and exact proposal are shown below. Use its approval control to authorize bounded synthetic simulation.'}
            db.execute('INSERT INTO sequence_journey_commands VALUES(?,?,?,?)',
                (organization,request_id,canonical(inputs),canonical(receipt)))
            return receipt

    def interactions(self,organization,conversation_id):
        with self.database.connect() as db:
            scoped_conversation(db,organization,conversation_id)
            if db.execute('PRAGMA user_version').fetchone()[0]<23:return []
            return [dict(id=r['request_id'],**json.loads(r['inputs']),response=json.loads(r['receipt'])['content'])
                for r in db.execute("SELECT request_id,inputs,receipt FROM sequence_journey_commands WHERE organization=? AND json_extract(inputs,'$.kind') IN ('sequence_inspection','sequence_stop_message') AND json_extract(inputs,'$.conversation_id')=? ORDER BY rowid",
                    (organization,conversation_id))]
