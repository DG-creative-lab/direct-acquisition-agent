"""Application-owned sandbox records, with a bound server-side store catalogue.

The root catalogue locates stores. Only the environment's own application
records carry intent, time, commands and domain links. Locations cannot run work.
"""
import json
import re
from contextlib import ExitStack
from pathlib import Path
from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.conversations import EnvironmentIntent, WORKSPACE_OWNER, environment_time
from .database import Database
from .admission_guard import verified_required, binding
from .actors import require_actor


class SqliteWorkspaceState:
    def __init__(self,root,database,clock,validate_source,validate_run):
        self.root,self.database,self.real_clock,self.validate_source=Path(root),database,clock,validate_source
        self.validate_run=validate_run

    @staticmethod
    def store_identity(database):
        with database.connect() as db:
            row=db.execute('SELECT id FROM application_store_identity WHERE singleton=1').fetchone()
            if row is None:raise Conflict('Application store identity is unavailable')
            return row[0]

    def path(self,scope,key):
        if scope=='conversations' and key=='conversations':path=self.root/'conversations.sqlite'
        elif scope=='campaign' and type(key) is str and re.fullmatch(r'workspace_[0-9a-f]{24}',key):
            path=self.root/key/'campaign.sqlite'
        else:raise Conflict('Unsupported server-owned sandbox storage scope')
        if not path.resolve().is_relative_to(self.root.resolve()):
            raise Conflict('Sandbox storage must remain inside its server-owned root')
        return path

    def location(self,identity):
        with self.database.connect() as db:
            row=db.execute('SELECT * FROM workspace_locations WHERE organization=? AND id=?',(WORKSPACE_OWNER,identity)).fetchone()
            return dict(row) if row else None

    def target(self,location):
        path=self.path(location['store_scope'],location['store_key'])
        if not path.exists():raise Conflict('The authoritative sandbox store is missing; restore its original store')
        database=self.database if location['store_scope']=='conversations' else type(self.database).existing(path)
        if self.store_identity(database)!=location['store_identity']:
            raise Conflict('Sandbox location refers to a different application store')
        return database

    def ensure_location(self,session):
        old=self.location(session['id'])
        if old:
            if old['run_organization']!=session['organization'] or old['store_scope']!=session['database_scope']:
                raise Conflict('Sandbox identity already has a different authoritative location')
            return old,self.target(old)
        if session.get('parent_id'):
            parent=self.location(session['parent_id'])
            if parent is None or self.get(session['parent_id']) is None:
                raise Conflict('Legacy parent environment requires explicit migration before verified continuation')
            if parent['run_organization']!=session['organization'] or parent['store_scope']!=session['database_scope']:
                raise Conflict('A child must retain its parent application scope')
            key=parent['store_key']
        else:
            key='conversations' if session['database_scope']=='conversations' else session['organization']
        path=self.path(session['database_scope'],key)
        database=self.database if session['database_scope']=='conversations' else Database(path)
        # Format selection precedes any environment or runtime work in a new store.
        from .admissions import SqliteAdmissions
        SqliteAdmissions(database,None,self.real_clock).seal_legacy_writes()
        location={'organization':WORKSPACE_OWNER,'id':session['id'],'run_organization':session['organization'],
                  'store_scope':session['database_scope'],'store_key':key,'store_identity':self.store_identity(database)}
        with self.database.transaction() as db:
            if not verified_required(db):raise Conflict('Select verified admission before recording sandbox locations')
            db.execute('INSERT OR IGNORE INTO workspace_locations VALUES(?,?,?,?,?,?)',tuple(location.values()))
            actual=dict(db.execute('SELECT * FROM workspace_locations WHERE organization=? AND id=?',(WORKSPACE_OWNER,session['id'])).fetchone())
            if actual!=location:raise Conflict('Concurrent sandbox location differs from its original store')
        return location,database

    @staticmethod
    def decode(row):
        intent=EnvironmentIntent(row['organization'],row['intent'])
        if intent.fingerprint!=row['fingerprint'] or intent.session['id']!=row['id']:
            raise Conflict('Sandbox intent failed integrity checks')
        environment_time(row['clock'])
        if row['clock']<intent.session['clock'] or row['clock_mode'] not in {'REAL','SIMULATED'} or (intent.session['mode']=='fixture' and row['clock_mode']!='SIMULATED'):
            raise Conflict('Sandbox time differs from its admitted environment')
        return intent.session|{k:row[k] for k in ('clock','clock_mode','run_id','case_id','cohort_id')}

    def read(self,db,org,identity):
        row=db.execute('SELECT * FROM campaign_environments WHERE organization=? AND id=?',(org,identity)).fetchone()
        if row is None:return None
        value=SqliteWorkspaceState.decode(row)
        self.validate_links(db,org,identity,value)
        return value

    def get(self,identity):
        location=self.location(identity)
        if location is None:return None
        with self.target(location).connect() as db:
            db.execute('BEGIN')
            return self.read(db,location['run_organization'],identity)

    def listing(self):
        with self.database.connect() as db:
            locations=[dict(row) for row in db.execute('SELECT * FROM workspace_locations WHERE organization=? ORDER BY rowid DESC',(WORKSPACE_OWNER,))]
        result=[]
        for location in locations:
            with self.target(location).connect() as db:
                db.execute('BEGIN')
                row=self.read(db,location['run_organization'],location['id'])
                if row is not None:result.append(row)
        return result

    def projection(self):
        """Read known stores only. No migration, enrollment or current context rebuild."""
        from .preparation_intents import SqlitePreparationIntents
        from .workspace_projection import ReadOnlyDatabase
        self.path('conversations','conversations')
        result={'sessions':[], 'requests':[], 'commands':[], 'preparations':[], 'stores':[], 'pending_locations':[],
                'diagnostics':{'checkpoint_recovery_blocks':[], 'copy_revision_blocks':[]}}
        with ExitStack() as stack:
            root=stack.enter_context(ReadOnlyDatabase.existing(self.database.path).connect())
            root.execute('BEGIN')
            if not verified_required(root):raise Conflict('Projection rebuild requires an already selected verified-paused store')
            locations=[dict(r) for r in root.execute('SELECT * FROM workspace_locations WHERE organization=? ORDER BY id',(WORKSPACE_OWNER,))]
            connections={('conversations','conversations'):root}
            result['root_identity']=root.execute('SELECT id FROM application_store_identity WHERE singleton=1').fetchone()[0]
            for location in locations:
                key=(location['store_scope'],location['store_key'])
                if key not in connections:
                    db=stack.enter_context(ReadOnlyDatabase.existing(self.path(*key)).connect())
                    db.execute('BEGIN');connections[key]=db
                db=connections[key]
                identity=db.execute('SELECT id FROM application_store_identity WHERE singleton=1').fetchone()
                if identity is None or identity[0]!=location['store_identity']:
                    raise Conflict('Projection source differs from its registered application store')
                if not verified_required(db):raise Conflict('Every projection source must remain verified-paused')
                session=self.read(db,location['run_organization'],location['id'])
                if session is None:
                    result['pending_locations'].append(location['id']);continue
                if session['database_scope']!=location['store_scope'] or session['organization']!=location['run_organization']:
                    raise Conflict('Projection source differs from its registered organization')
                result['sessions'].append(session)
                if session['run_id'] is not None:
                    result['diagnostics']['checkpoint_recovery_blocks'].append((session['organization'],session['run_id']))
                if session['case_id'] is not None:
                    for row in db.execute('SELECT receipt FROM review_commands WHERE organization=? ORDER BY rowid',(session['organization'],)):
                        receipt=json.loads(row[0])
                        if receipt.get('kind')=='copy_revision_admission' and receipt['inputs']['case_id']==session['case_id']:
                            result['diagnostics']['copy_revision_blocks'].append((session['organization'],receipt['id']))
                requests=[dict(r) for r in db.execute('SELECT * FROM workspace_requests WHERE environment_organization=? AND environment_id=? ORDER BY scope,request_id',
                                                     (session['organization'],session['id']))]
                if not requests:raise Conflict('Projection source is missing its original creation command')
                for request in requests:
                    request['inputs']=json.loads(request['inputs']);result['requests'].append(request)
                for command in db.execute('SELECT * FROM workspace_commands WHERE organization=? AND environment_id=? ORDER BY request_id',
                                          (session['organization'],session['id'])):
                    command=dict(command);command['inputs']=json.loads(command['inputs']);result['commands'].append(command)
            for key,db in sorted(connections.items()):
                if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise Conflict('Projection source failed SQLite integrity checks')
                known={(l['run_organization'],l['id']) for l in locations if (l['store_scope'],l['store_key'])==key}
                for organization in sorted({org for org,_ in known}):
                    if any((organization,r[0]) not in known for r in db.execute('SELECT id FROM campaign_environments WHERE organization=?',(organization,))):
                        raise Conflict('An authoritative environment is missing its registered location')
                result['stores'].append({'scope':key[0],'key':key[1],
                                         'identity':db.execute('SELECT id FROM application_store_identity WHERE singleton=1').fetchone()[0]})
            result['preparations']=[SqlitePreparationIntents.decode(r,root) for r in root.execute(
                'SELECT * FROM workflow_preparations WHERE organization=? ORDER BY id',('local-conversations',))]
            result['fingerprint']=digest(result)
        return result

    def request(self,kind,scope,request_id,*,parent_id=None):
        if kind in {'root','conversation'}:database=self.database if kind=='conversation' else None
        elif kind=='followup':
            location=self.location(parent_id)
            if location is None:raise Conflict('Legacy parent environment requires explicit migration')
            database=self.target(location)
        else:raise ValueError('Unsupported workspace creation request')
        if kind=='root':return None  # Its stable session identity resolves this request directly.
        owner='local-conversations' if kind=='conversation' else self.get(parent_id)['organization']
        with database.connect() as db:
            row=db.execute('SELECT * FROM workspace_requests WHERE organization=? AND scope=? AND request_id=?',(owner,scope,request_id)).fetchone()
            return {'kind':row['kind'],'inputs':json.loads(row['inputs']),'session_id':row['environment_id']} if row else None

    def create(self,intent,kind,scope,request_id,inputs):
        session=intent.session;location,database=self.ensure_location(session);org=intent.organization
        owner='local-conversations' if kind=='conversation' else org
        with database.transaction() as db:
            if not verified_required(db):raise Conflict('Verified environment storage is not selected')
            old=self.read(db,org,session['id'])
            request=db.execute('SELECT * FROM workspace_requests WHERE organization=? AND scope=? AND request_id=?',(owner,scope,request_id)).fetchone()
            if request and (request['kind']!=kind or request['inputs']!=canonical(inputs) or request['environment_id']!=session['id']):
                raise Conflict('Workspace request already binds different inputs')
            if old is not None:
                original=db.execute('SELECT scope,request_id,kind,inputs FROM workspace_requests WHERE environment_organization=? AND environment_id=? ORDER BY rowid LIMIT 1',
                                    (org,session['id'])).fetchone()
                if (original is None or original['scope']!=scope or original['kind']!=kind or original['inputs']!=canonical(inputs) or
                        (kind=='root' and original['request_id']!=request_id)):
                    raise Conflict('Sandbox creation differs from its original admitted command')
                # Initial timestamps are server snapshots, not arguments a retry may reset.
                compare={k:v for k,v in session.items() if k not in {'clock','clock_mode','created_at','run_id','case_id','cohort_id'}}
                original=json.loads(db.execute('SELECT intent FROM campaign_environments WHERE organization=? AND id=?',(org,session['id'])).fetchone()[0])
                if compare!={k:original[k] for k in compare}:raise Conflict('Sandbox identity already binds another operation')
            else:
                if db.execute('SELECT 1 FROM runs WHERE organization=? AND request_id=?',(org,session['id'])).fetchone():
                    raise Conflict('Legacy campaign environment requires explicit migration')
                intent=self.validate_source(db,session,kind,inputs,self.real_clock(),request_id)
                session=intent.session
                db.execute('INSERT INTO campaign_environments VALUES(?,?,?,?,0,?,?,NULL,NULL,NULL)',
                           (org,session['id'],intent.session_json,intent.fingerprint,session['clock'],session['clock_mode']))
            if request is None:
                db.execute('INSERT INTO workspace_requests VALUES(?,?,?,?,?,?,?)',(owner,scope,request_id,kind,canonical(inputs),org,session['id']))
            return self.read(db,org,session['id'])

    def validate_links(self,db,org,identity,session):
        run,case,cohort=(session[k] for k in ('run_id','case_id','cohort_id'))
        if run is not None:
            admitted=binding(db,org,run)
            actual=db.execute('SELECT request_id FROM runs WHERE organization=? AND id=?',(org,run)).fetchone()
            if admitted is None or actual is None or actual[0]!=identity:raise Conflict('Sandbox run differs from its verified operation')
            row=db.execute('SELECT intent FROM campaign_environments WHERE organization=? AND id=?',(org,identity)).fetchone()
            original=EnvironmentIntent(org,row['intent']).session
            creation=db.execute('SELECT * FROM workspace_requests WHERE environment_organization=? AND environment_id=? ORDER BY rowid LIMIT 1',
                                (org,identity)).fetchone()
            if creation is None:raise Conflict('Sandbox creation command is unavailable')
            request=db.execute('SELECT inputs,source FROM admission_requests WHERE organization=? AND request_id=?',
                               (org,admitted.request_id)).fetchone()
            parent=self.read(db,org,original['parent_id']) if original['parent_id'] else None
            self.validate_run(original,dict(creation),admitted,json.loads(request['inputs']),json.loads(request['source']),parent)
        if case is not None:
            actual=db.execute('SELECT run_id FROM review_cases WHERE organization=? AND id=?',(org,case)).fetchone()
            if actual is None or actual[0]!=run:raise Conflict('Review case belongs to another sandbox run')
        if cohort is not None:
            actual=db.execute('SELECT j.case_id FROM learning_cohorts c JOIN simulated_agency_jobs j ON j.organization=c.organization AND j.id=c.job_id WHERE c.organization=? AND c.id=?',(org,cohort)).fetchone()
            if actual is None or actual[0]!=case:raise Conflict('Learning cohort belongs to another accepted campaign')

    def save_links(self,identity,session):
        location=self.location(identity)
        if location is None:raise Conflict('Sandbox environment is not authoritative')
        database=self.target(location);org=location['run_organization']
        with database.transaction() as db:
            current=self.read(db,org,identity)
            if current is None:raise NotFound('Sandbox intent is unavailable')
            immutable=set(current)-{'run_id','case_id','cohort_id'}
            if any(session.get(k)!=current[k] for k in immutable):
                raise Conflict('Sandbox routing, mode and time cannot change through a projection update')
            run=session['run_id'];case=session['case_id'];cohort=session['cohort_id']
            if any(current[k] is not None and current[k]!=session[k] for k in ('run_id','case_id','cohort_id')):
                raise Conflict('Sandbox domain links cannot replace an earlier result')
            self.validate_links(db,org,identity,session)
            if all(current[k]==session[k] for k in ('run_id','case_id','cohort_id')):return current
            db.execute('UPDATE campaign_environments SET run_id=?,case_id=?,cohort_id=?,epoch=epoch+1 WHERE organization=? AND id=?',
                       (run,case,cohort,org,identity))
            return self.read(db,org,identity)

    def clock(self,identity,real_time):
        session=self.get(identity)
        if session is None:raise Conflict('Authoritative sandbox clock is unavailable')
        return max(real_time,session['clock']) if session['clock_mode']=='REAL' else session['clock']

    def begin_command(self,identity,action,payload):
        location=self.location(identity)
        if location is None:raise Conflict('Legacy sandbox decisions require environment migration')
        database=self.target(location);org=location['run_organization'];inputs=canonical({'action':action,'payload':payload})
        with database.transaction() as db:
            session=self.read(db,org,identity)
            if session is None:raise NotFound('Sandbox intent is unavailable')
            old=db.execute('SELECT * FROM workspace_commands WHERE organization=? AND environment_id=? AND request_id=?',
                           (org,identity,payload['request_id'])).fetchone()
            if old:
                if old['inputs']!=inputs:raise Conflict('Workspace request already binds different action inputs')
                return bool(old['done'])
            if action in {'observe','finalize'}:
                require_actor(db,org,'local-operator','operator')
                row=db.execute('''SELECT c.payload FROM learning_cohorts c JOIN simulated_agency_jobs j
                    ON j.organization=c.organization AND j.id=c.job_id WHERE c.organization=? AND c.id=? AND j.case_id=?''',
                    (org,session['cohort_id'],session['case_id'])).fetchone()
                if row is None:raise Conflict('An accepted outcome cohort is required before advancing sandbox time')
                cohort=json.loads(row[0]);target=cohort['window_start']+7*86400 if action=='observe' else cohort['window_end']
                environment_time(target)
                db.execute("UPDATE campaign_environments SET clock=?,clock_mode='SIMULATED',epoch=epoch+1 WHERE organization=? AND id=?",
                           (max(session['clock'],target),org,identity))
            db.execute('INSERT INTO workspace_commands VALUES(?,?,?,?,0)',(org,identity,payload['request_id'],inputs))
            return False

    def complete_command(self,identity,request_id):
        location=self.location(identity)
        if location is None:raise Conflict('Sandbox command is not authoritative')
        with self.target(location).transaction() as db:
            changed=db.execute('UPDATE workspace_commands SET done=1 WHERE organization=? AND environment_id=? AND request_id=?',
                               (location['run_organization'],identity,request_id)).rowcount
            if not changed:raise NotFound('Original sandbox command is unavailable')
