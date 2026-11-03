"""Local interactive sandbox facade. Domain services retain decision authority."""

import csv
import io
import json
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from acquisition.bootstrap import build, build_preparations, agent_catalogue
from acquisition.conversations import ACTIVE_PREPARATION, AudienceSelectionRejected, ActionNotSaved, pending_copy_clarification
from acquisition.adapters.environment import openrouter_key
from acquisition.adapters.openrouter import OpenRouter
from acquisition.adapters.sqlite.workspace_ancestry import initialize_workspace_identity
from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.learning import identifier
from acquisition.reasoning import ModelConfig
from acquisition.creative import validate_fact_pack, fixture_catalog
from acquisition.campaigns import FollowupBrief, build_draft, brief_from
from dataclasses import replace, asdict
from acquisition.reviews import ReviewPolicy, text, ActorUnavailable


REVISION_BLOCKS = {
    "ancestry_unavailable": "Historical campaign ancestry needs recovery. Restore its original workspace relationship before model calls can resume. Usage remains incomplete until that relationship is verified.",
    "evidence_unavailable": "Product evidence is unavailable or outside its review window. Review verified evidence and prepare a current campaign before requesting another revision. This request keeps its frozen inputs.",
    "configuration_unavailable": "Restore the server-side OpenRouter key and the original model settings. This saved request will resume automatically when its configuration is available. Do not submit another revision to retry it.",
    "continuation_unavailable": "Revision continuation is unavailable. Inspect the original run and server storage. The server will recheck this saved request; it will not repeat an uncertain provider call.",
}

CHECKPOINT_BLOCKS = {
    'checkpoint_authority_unavailable':'Review recovery is blocked. Restore a permitted local operator and checkpoint authority, then retry recovery. The stop remains committed; no generation has been repeated.',
    'checkpoint_storage_unavailable':'Review recovery is waiting for local storage. Restore storage and retry recovery. The completed checkpoint and stop receipt are preserved.',
    'checkpoint_validation_unavailable':'Review recovery needs valid checkpoint data. Inspect the saved draft and evidence. No generation or approval has been repeated.',
    'checkpoint_recovery_unavailable':'Review recovery is unavailable for this checkpoint. Inspect its saved case and local storage; other conversations can continue.',
}


class Workspace:
    def __init__(self, root, real_clock=time.time):
        self.real_clock = real_clock
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self.control() as db:
            db.execute("CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, request_hash TEXT NOT NULL, payload TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS commands(session_id TEXT NOT NULL, request_id TEXT NOT NULL, request_hash TEXT NOT NULL, done INTEGER NOT NULL, PRIMARY KEY(session_id,request_id))")
            db.execute("CREATE TABLE IF NOT EXISTS conversation_draft_requests(conversation_id TEXT NOT NULL, request_id TEXT NOT NULL, request_hash TEXT NOT NULL, session_id TEXT NOT NULL, PRIMARY KEY(conversation_id,request_id))")
            db.execute("CREATE TABLE IF NOT EXISTS followup_prepare_requests(organization TEXT NOT NULL, request_id TEXT NOT NULL, request_hash TEXT NOT NULL, session_id TEXT NOT NULL, PRIMARY KEY(organization,request_id))")
            db.execute("CREATE TABLE IF NOT EXISTS copy_revision_blocks(organization TEXT NOT NULL, revision_id TEXT NOT NULL, code TEXT NOT NULL, PRIMARY KEY(organization,revision_id))")
            db.execute('CREATE TABLE IF NOT EXISTS checkpoint_recovery_blocks(organization TEXT NOT NULL, run_id TEXT NOT NULL, code TEXT NOT NULL, PRIMARY KEY(organization,run_id))')
            initialize_workspace_identity(db)
        self.preparations = build_preparations(self.root / "workspace.sqlite", self)
        self.pack = json.loads((Path(__file__).resolve().parents[2] / "config/iwoca-product-facts-v1.json").read_text())

    @contextmanager
    def control(self):
        db = sqlite3.connect(self.root / "workspace.sqlite", timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()

    def _save(self, session):
        with self.control() as db:
            db.execute("UPDATE sessions SET payload=? WHERE id=?", (canonical(session), session["id"]))

    def _session(self, identity):
        identifier(identity)
        with self.control() as db:
            row = db.execute("SELECT payload FROM sessions WHERE id=?", (identity,)).fetchone()
        if row is None:
            raise NotFound("Campaign not found in this workspace")
        return json.loads(row[0])

    def _app(self, session, with_model=False, *, revision_admission=False):
        gateway, config = None, None
        if (with_model or revision_admission) and session["mode"] == "model":
            validate_fact_pack(self.pack, datetime.fromtimestamp(self.real_clock(), timezone.utc).date())
            if with_model:gateway = OpenRouter(openrouter_key(Path(".env.local")))
            config = ModelConfig("openai/gpt-oss-120b", max_calls=10, force_tool_choice=True)
        # Each sandbox has its own durable clock. Live generation starts at real
        # time; explicit outcome simulation alone can advance the sandbox clock.
        conversation_db = session.get("database_scope") == "conversations" or session.get("conversation_plan") or session["organization"] == "local-conversations"
        database = self.root / "conversations.sqlite" if conversation_db else self.root / session["organization"] / "campaign.sqlite"
        return build(database, clock=lambda: max(self.real_clock(), session["clock"]) if session.get("clock_mode") == "REAL" else session["clock"], gateway=gateway, model_config=config, workspace_organization=session['organization'])

    def listing(self):
        with self.control() as db:
            sessions = [json.loads(r[0]) for r in db.execute("SELECT payload FROM sessions ORDER BY rowid DESC LIMIT 50")]
        return {"sessions": [{k: s[k] for k in ("id", "name", "mode", "created_at", "case_id")} for s in sessions],
                "mode": "LOCAL_SYNTHETIC_SANDBOX", "hosted_authentication": False}

    def _conversation_app(self, with_model=False):
        # Scope and database location are server-owned, never model/browser input.
        gateway = OpenRouter(openrouter_key(Path(".env.local"))) if with_model else None
        config = ModelConfig("openai/gpt-oss-120b", max_calls=2, force_tool_choice=True) if with_model else None
        return build(self.root / "conversations.sqlite", clock=self.real_clock, gateway=gateway, model_config=config, workspace_organization='local-conversations')

    def conversations(self):
        return {"conversations": self._conversation_app().conversations.store.listing("local-conversations")}

    def audience_catalogue(self, campaign_key=None):
        return self._conversation_app().audience_discovery.discover("local-conversations", campaign_key)

    def audience_dataset(self, dataset_id, version, checksum, manifest_id):
        return self._conversation_app().audience_discovery.inspect("local-conversations", dataset_id, version, checksum, manifest_id)

    def knowledge(self):
        config = Path(__file__).resolve().parents[2] / "config"
        playbooks = json.loads((config / "campaign-playbooks-v1.json").read_text())
        editorial = json.loads((config / "editorial-v3.json").read_text())
        return {"agent_catalogue": agent_catalogue(), "playbooks": playbooks, "product_facts": self.pack,
                "editorial": {"version": editorial["version"], "rules": editorial["rules"],
                              "situations": editorial["situations"]},
                "learning": "Synthetic outcome memory is scoped to each campaign and is advisory. Inspect it in Learning."}

    def conversation(self, conversation_id):
        self._ensure_descendant_links()
        view = self._conversation_app().conversations.view("local-conversations", conversation_id)
        with self.control() as db:
            sessions = [json.loads(r[0]) for r in db.execute("SELECT payload FROM sessions ORDER BY rowid DESC")]
        return view | {"execution":self._conversation_app().execution.view('local-conversations',conversation_id), "actions":self.action_progress(conversation_id), "preparations": self.preparation_progress(conversation_id), "campaigns": [{"session_id": s["id"], "plan_id": s["conversation_plan"]["id"],
                                      "revision": s["conversation_plan"]["revision"], "case_id": s["case_id"],
                                      "generation": self._generation(s)}
                                     for s in sessions if s.get("conversation_plan", {}).get("conversation_id") == conversation_id]}

    def action_context(self, conversation_id, expected_revision):
        app=self._conversation_app();source=app.conversations.view('local-conversations',conversation_id)
        if source['revision']!=expected_revision:raise Conflict('The brief changed before action admission')
        plan=source['current_plan']['result'] if source['current_plan'] else None
        with self.control() as db:
            sessions=[json.loads(r[0]) for r in db.execute('SELECT payload FROM sessions ORDER BY rowid DESC')]
        session=next((s for s in sessions if s.get('conversation_plan',{}).get('conversation_id')==conversation_id
                      and s['conversation_plan']['revision']==expected_revision),None)
        review=self._app(session).reviews.store.view(session['organization'],session['case_id']) if session and session['case_id'] else None
        preparation=self.preparations.store.for_revision('local-conversations',conversation_id,expected_revision)
        phase=preparation['status'] if preparation else 'not_started'
        if review and not review['validation_report']['review_ready']:phase='blocked'
        if review and review['handoff']:phase='simulated_accepted'
        labels={'selecting_audience':'awaiting audience confirmation','planning':'interpreting the brief',
                'preparing':'preparing the campaign','review_ready':'ready for human review','not_started':'not started',
                'admitting':'saving the preparation request','needs_input':'waiting for clarification',
                'needs_consent':'waiting for generation permission','blocked':'blocked pending inspection',
                'failed':'stopped after a failure','uncertain':'awaiting provider reconciliation',
                'stale':'stopped after a brief change','simulated_accepted':'accepted by the local handoff simulator'}
        refs={'plan_id':plan['id'] if plan else None,'session_id':session['id'] if session else None,
              'subject_id':review['subject']['id'] if review else None,'draft_id':review['subject']['draft_id'] if review else None}
        answers={'inspect_progress':{'text':'Preparation was '+labels.get(phase,phase.replace('_',' '))+' when this snapshot was recorded.',
                    'evidence':refs|{'status':phase,'preparation_id':preparation['id'] if preparation else None}}}
        selected=(review['manifest']['brief'].get('audience_source') if review else
                  app.conversation_audiences.store.get('local-conversations',conversation_id,expected_revision))
        counts=review['manifest']['counts'] if review else None
        if selected:
            audience_text=f"The confirmed synthetic audience is {selected['source']['title']}, version {selected['source']['version']}, with {selected['source']['record_count']} input records. Its segments match the proposed brief."
        elif review:
            audience_text=f"This campaign uses its original generated synthetic audience, with {counts['input']} input records."
        else:audience_text='A source audience has not been confirmed for this brief.'
        if counts:audience_text+=f" The validated draft has {counts['mailed']} mailed assignments and {counts['holdout']} no-mail controls."
        answers['explain_audience']={'text':audience_text,'evidence':refs|{'selection':selected,'counts':counts}}
        reasons=review['manifest']['exclusion_reasons'] if review else None
        explanation='The validated draft is not available yet, so exclusion counts have not been established.'
        if counts:
            explanation=f"The draft excluded {counts['excluded']} input records. "
            reason_labels={'duplicate_business':'duplicate business identity','suppressed':'suppression','product_scope':'outside supported country or entity type',
                'unusable_demo_address':'unusable demo address','missing_score':'missing supplied score','contact_cap':'contact frequency limit',
                'contact_cooldown':'recent contact cooldown','outside_selected_segment':'outside selected segment'}
            explanation+='Recorded reasons: '+', '.join(f"{reason_labels.get(k,k.replace('_',' '))}: {v}" for k,v in sorted(reasons.items()))+'.' if reasons else 'No exclusion reasons were recorded.'
        answers['explain_exclusions']={'text':explanation,'evidence':refs|{'counts':counts,'exclusion_reasons':reasons}}
        report=review['validation_report'] if review else None
        validation='No exact-draft validation report is available yet.'
        if report:
            blocked=[c['label'] for c in report['checks'] if c['required'] and c['status']!='passed']
            validation=('At the recorded check, required machine checks passed and the draft was ready for human review. Approval remains a separate decision.'
                        if report['review_ready'] else 'At the recorded check, review was blocked by: '+', '.join(blocked)+'.')
        answers['explain_validation']={'text':validation,'evidence':refs|{'report':report}}
        target={'organization':'local-conversations','conversation_id':conversation_id,'revision':expected_revision}
        target['id']='brief_target_'+digest(target)[:32]
        context={'schema':'routing-context/v2','target':target,'observed_at':self.real_clock(),'answers':answers,
                 'brief':{k:plan[k] for k in ('objective','segments','budget_pence','copy_mode')} if plan else None}
        copy_targets={'available':False,'reason':'Prepare a grounded model campaign before requesting copy revisions.', 'creatives':[]}
        if review and session['mode']=='model':
            revisions=self._app(session).revisions.view(session['organization'],session['case_id'])
            reason=('Accepted simulated campaigns cannot be revised.' if review['handoff'] else
                    'Restore current evidence and a valid campaign before requesting a revision.' if not review['candidate_valid'] else
                    'A saved revision already owns this subject, or the three-revision limit was reached. Inspect the original request.'
                    if len(revisions)>=3 or any(r['base_subject_id']==review['subject']['id'] for r in revisions) else '')
            copy_targets|={'available':not reason,'reason':reason,'session_id':session['id'],'organization':session['organization'],
                'case_id':session['case_id'],'subject_id':review['subject']['id'],'draft_id':review['subject']['draft_id'],
                'creatives':[{k:c[k] for k in ('id','segment','arm','headline','opening')} for c in review['manifest']['creatives']]}
        context['copy_revision_targets']=copy_targets
        latest_response=next((p for p in reversed(source['plans']) if p['result']),None)
        action_exchange=[]
        for row in app.actions.store.listing('local-conversations',conversation_id):
            if row['inputs']['revision']!=expected_revision or row['confirmed']:continue
            action=app.actions.view('local-conversations',row)
            if action['result']:
                action_exchange.append({'action_id':row['id'],'content':row['inputs']['content'],
                    'response':{k:action['result'][k] for k in ('id','kind','text')}})
        clarifications=[]
        for exchange in reversed(action_exchange):
            if exchange['response']['kind']=='unsupported':break
            if exchange['response']['kind'] in {'clarify','amend_brief'}:clarifications.insert(0,exchange)
        copy_exchange=[]
        for row in app.actions.store.listing('local-conversations',conversation_id):
            if row['confirmed'] or row['inputs']['revision']!=expected_revision:continue
            old_targets=row['context'].get('copy_revision_targets',{})
            if not old_targets.get('subject_id') or old_targets.get('subject_id')!=copy_targets.get('subject_id'):continue
            action=app.actions.view('local-conversations',row)
            if action['result'] and action['result']['kind']=='revise_copy':
                if not pending_copy_clarification(action['result']['copy_revision']):
                    copy_exchange=[]
                else:
                    copy_exchange.append({'action_id':row['id'],'content':row['inputs']['content'],
                        'response':{k:action['result'][k] for k in ('id','kind','text')}})
        context['dialogue']={
            'version':'routing-dialogue/v4',
            'messages':[{k:m[k] for k in ('id','revision','role','content')} for m in source['messages'][-2:]],
            'action_exchange':action_exchange[-2:],
            'clarification_exchange':clarifications,
            'copy_exchange':copy_exchange,
            'planner_response':({'current':latest_response['revision']==expected_revision,
                **{k:latest_response['result'][k] for k in ('id','revision','outcome','question','unsupported_reason')}}
                if latest_response else None),
        }
        return context|{'id':'action_context_'+digest(context)}

    def route_followup(self, conversation_id, request_id, expected_revision, content, allow_model_copy):
        app=self._conversation_app();old=app.actions.store.request('local-conversations',conversation_id,request_id)
        try:
            context=old['context'] if old else self.action_context(conversation_id,expected_revision)
            row=app.actions.admit('local-conversations',conversation_id,request_id,expected_revision,content,allow_model_copy,context)
        except (Conflict,ValueError,NotFound) as error:raise ActionNotSaved(str(error)) from error
        # Admission is durable before any task or provider request. Recovery can
        # reconcile the same identity if this next write is interrupted.
        if old is None and not row['alias']:app.actions.reconcile('local-conversations',row)
        return self.conversation(conversation_id)|{'action_receipt':{'id':row['id'],'revision':row['inputs']['revision']}}

    def confirm_followup(self, conversation_id, action_id, request_id, target_id, expected_revision):
        app=self._conversation_app();row=app.actions.store.get('local-conversations',action_id)
        if row['inputs']['conversation_id']!=conversation_id:raise NotFound('Action belongs to another conversation')
        receipt=app.actions.store.confirm('local-conversations',action_id,request_id,target_id,expected_revision,self.real_clock())
        self._continue_confirmed_action(receipt)
        return self.conversation(conversation_id)|{'action_confirmation':receipt}

    def confirm_copy_followup(self, conversation_id, action_id, request_id, result_id, expected_revision, allow_model_copy):
        if allow_model_copy is not True:raise ValueError('Allow up to five model calls for this exact revision before confirming')
        app=self._conversation_app()
        row=app.actions.store.get('local-conversations',action_id)
        if row['inputs']['conversation_id']!=conversation_id:raise NotFound('Copy action belongs to another conversation')
        value=app.actions.view('local-conversations',row)
        result=value['result']
        if (type(expected_revision) is not int or expected_revision!=row['inputs']['revision'] or not result
                or result['id']!=result_id or result['kind']!='revise_copy' or result['copy_revision']['status']!='ready'):
            raise Conflict('Confirm the exact completed copy-edit proposal')
        proposal=result['copy_revision'];target=proposal['target']
        session=self._session(target['session_id'])
        source=session.get('conversation_plan',{})
        if (source.get('conversation_id')!=conversation_id or source.get('revision')!=expected_revision
                or session['case_id']!=target['case_id'] or session['organization']!=target['organization']):
            raise Conflict('Copy target differs from its original conversation campaign')
        revision_request_id=action_id+':copy'
        native=self._app(session)
        if native.reviews.store.revision_request(session['organization'],revision_request_id) is None:
            native=self._app(session,revision_admission=True)
        reference={'organization':'local-conversations','conversation_id':conversation_id,'action_id':action_id,
                   'result_id':result_id,'revision':expected_revision}
        native.revisions.admit(session['organization'],session['case_id'],revision_request_id,target['subject_id'],
            target['id'],proposal['feedback'],True,conversation_action=reference,confirmation_request_id=request_id)
        return self.conversation(conversation_id)

    def _continue_confirmed_action(self, receipt):
        source=self.preparation_source('local-conversations',receipt['conversation_id'])
        revision=receipt['message_receipt']['revision']
        if source['revision']!=revision or len(source['plans'])>=6:return
        try:
            self.preparations.admit('local-conversations',receipt['conversation_id'],receipt['preparation_request_id'],revision,False,receipt['allow_model_copy'],True)
        except (ValueError,Conflict,NotFound):
            # The confirmed amendment and consent remain discoverable for restart
            # or configuration recovery. Never choose a replacement request ID.
            return

    def action_progress(self, conversation_id):
        app=self._conversation_app();source=app.conversations.view('local-conversations',conversation_id)
        values=[]
        for row in app.actions.store.listing('local-conversations',conversation_id):
            value=app.actions.view('local-conversations',row)
            generation=self._run_generation(app,'local-conversations',value['run_id']) if value['run_id'] else None
            value|={'current':row['inputs']['revision']==source['revision'],'generation':generation}
            if generation and generation.get('budget_exhausted') and value['status']=='failed':
                value |= {'status':'budget_exhausted','detail':'The shared model-call allowance is exhausted. Inspect model usage or start a new conversation.'}
            if generation and generation.get('ancestry_pending'):
                value |= {'status':'blocked','detail':REVISION_BLOCKS['ancestry_unavailable']}
            if value['result'] and value['result']['kind']=='revise_copy' and value['result']['copy_revision']['target']:
                target=value['result']['copy_revision']['target']
                current_review=self.view(target['session_id'])['review']
                value['target_current']=(value['current'] and current_review['subject']['id']==target['subject_id']
                                         and current_review['candidate_valid'] and not current_review['handoff'])
            if value['status'] in {'admitted','queued'} and not row['alias']:
                if row['model_config']!=asdict(app.actions.config):
                    value['status']='blocked'
                    value['detail']='Restore the original routing model and limits to resume this saved request. Its inputs have been preserved.'
                else:
                    try:openrouter_key(Path('.env.local'))
                    except ValueError:
                        value['status']='blocked'
                        value['detail']='Routing is waiting for the server-side OpenRouter key. Restore it to resume this saved request.'
            if value['confirmed']:
                if value['confirmed'].get('kind')=='copy_revision_confirmation':
                    session=self._session(value['confirmed']['session_id'])
                    progress=self._copy_revision_progress(self._app(session),session['organization'],session['case_id'])
                    value['copy_revision_progress']=next((r for r in progress if r['id']==value['confirmed']['revision_id']),None)
                    values.append(value)
                    continue
                revision=value['confirmed']['message_receipt']['revision']
                admitted=self.preparations.store.for_revision('local-conversations',conversation_id,revision)
                value['continuation_pending']=source['revision']==revision and admitted is None
                value['continuation_reason']='planning_budget_exhausted' if len(source['plans'])>=6 else 'configuration_or_admission_unavailable'
            values.append(value)
        return values

    def recover_actions(self):
        # Only call after obtaining the deployment's exclusive server lock.
        # A reserved call from the previous executor is uncertain, not a retry.
        app=self._conversation_app()
        for row in app.actions.store.listing('local-conversations'):
            run=app.tasks.find_run('local-conversations',row['run_request_id']) if not row['alias'] else None
            if run:
                generation=self._run_generation(app,'local-conversations',run)
                if generation['status']=='running' and generation['outcome_uncertain']:
                    app.tasks.cancel('local-conversations',run,self.real_clock())

    def advance_actions(self):
        app=self._conversation_app()
        for row in app.actions.store.listing('local-conversations'):
            try:
                if row['confirmed']:
                    if row['confirmed'].get('kind')!='copy_revision_confirmation':self._continue_confirmed_action(row['confirmed'])
                    continue
                if row['alias']:continue
                source=app.conversations.view('local-conversations',row['inputs']['conversation_id'])
                if source['revision']!=row['inputs']['revision']:continue
                current=app.actions.view('local-conversations',row)
                if current['status'] not in {'admitted','queued','running'}:continue
                with self.lock:
                    configured=self._conversation_app(with_model=True)
                    run=configured.actions.reconcile('local-conversations',row)
                    configured.worker.tick('local-conversations',run_id=run)
            except Exception:
                # The durable admission/runtime journal owns recovery. Do not
                # repeat unknown inference or let one unavailable action starve others.
                continue

    def _generation(self, session):
        app = self._app(session)
        scope = session["organization"]
        run = session["run_id"] or app.tasks.find_run(scope, session["id"])
        if run is None:
            return {"run_id": None, "status": "admitted", "failed_tasks": [], "provider_error": None,
                    "outcome_uncertain": False, "unresolved_calls": []}
        generation=self._run_generation(app, scope, run)
        return generation | {'checkpoint_recovery':self._checkpoint_block(scope,run)}

    @staticmethod
    def _run_generation(app, scope, run):
        state = app.tasks.inspect(scope, run)
        failures = [{"capability": task["capability"], "error_code": (task["output"] or {}).get("error_code")}
                    for task in state["tasks"] if task["status"] == "failed"]
        # Only explicit public codes leave the journal. Provider response bodies and task messages stay private.
        receipts = app.calls.inspect(scope, run)
        codes = [r["error"] for r in receipts if r["error"]]
        provider_error = next((code for code in reversed(codes) if re.fullmatch(r"provider_http_[1-5][0-9]{2}", code)
                               or code in {"provider_outcome_unknown", "provider_request_failed"}), None)
        definitive_rejections = {"provider_http_400", "provider_http_401", "provider_http_403", "provider_http_404", "provider_http_422"}
        unresolved = [{"key": r["key"], "status": r["status"]} for r in receipts
                      if r["status"] == "reserved" or (r["status"] == "unknown" and r["error"] not in definitive_rejections)]
        execution = app.execution.for_run(scope,run)
        return {"run_id": run, "status": state["run"]["status"], "failed_tasks": failures, "provider_error": provider_error,
                'ancestry_pending':app.execution.pending(scope,run),
                "budget_exhausted":bool(execution and execution['remaining']==0),
                "outcome_uncertain": bool(unresolved), "unresolved_calls": unresolved,
                "steps": [{"capability": t["capability"], "status": t["status"]} for t in state["tasks"]]}

    def create_conversation(self, request_id, title):
        return self._conversation_app().conversations.create("local-conversations", request_id, title)

    @staticmethod
    def _preparation_scope(organization):
        if organization != "local-conversations":
            raise NotFound("Conversation organization is not available in this workspace")

    def freeze_preparation_plan(self, organization, conversation_id, request_id, revision, fixture):
        self._preparation_scope(organization)
        app = self._conversation_app(with_model=not fixture)
        return app.conversations.planning_context(organization, conversation_id, request_id, revision, fixture)

    def admit_preparation_plan(self, organization, row):
        self._preparation_scope(organization)
        inputs = row["inputs"]
        app = self._conversation_app(with_model=not inputs["fixture"])
        plan = app.conversations.plan_fixture if inputs["fixture"] else app.conversations.plan
        return plan(organization, inputs["conversation_id"], row["plan_request_id"], inputs["revision"],
                    frozen_context=row["planning_context"])

    def preparation_source(self, organization, conversation_id):
        self._preparation_scope(organization)
        app = self._conversation_app()
        return app.conversations.view(organization, conversation_id) | {'execution':app.execution.view(organization,conversation_id)}

    def stop_execution(self, conversation_id, request_id, expected_revision):
        # Deliberately independent of the executor lock: a provider call may be in flight.
        self._ensure_descendant_links()
        receipt = self._conversation_app().execution.stop('local-conversations',conversation_id,request_id,expected_revision)
        for row in self.preparations.store.listing('local-conversations',conversation_id):
            if row['inputs']['revision'] <= receipt['revision'] and row['status'] in ACTIVE_PREPARATION | {'blocked','needs_consent'}:
                self.preparations.store.update('local-conversations',row,'cancelled','Stopped by you. Send a new brief to start new work; the shared allowance does not reset.')
        self._restore_checkpoint_reviews(receipt)
        return self.conversation(conversation_id) | {'execution_receipt':receipt}

    def _ensure_descendant_links(self, strict_session_id=None):
        with self.control() as db:
            sessions=[json.loads(r[0]) for r in db.execute('SELECT payload FROM sessions ORDER BY rowid')]
        required=set()
        if strict_session_id:
            current=self._session(strict_session_id)
            while current.get('parent_id'):
                if current['id'] in required or len(required)>=10:
                    raise Conflict('Descendant ancestry is cyclic or too deep')
                required.add(current['id'])
                current=self._session(current['parent_id'])
        for session in sessions:
            if not session.get('parent_id') or session.get('followup_id'):
                continue
            try:
                parent=self._session(session['parent_id'])
                if parent['organization']!=session['organization']:
                    raise Conflict('Descendant campaign differs from its parent organization')
                app=self._app(parent)
                run=parent['run_id'] or app.tasks.find_run(parent['organization'],parent['id'])
                if run is None:
                    raise Conflict('Descendant campaign requires its original parent run')
                app.execution.descendant(parent['organization'],session['id'],run)
            except Exception:
                if session['id'] in required:
                    raise
                # Domain migration fences unresolved old ancestry. One unavailable
                # control record cannot stop unrelated conversations.
                continue

    def _checkpoint_block(self, organization, run_id):
        with self.control() as db:
            row=db.execute('SELECT code FROM checkpoint_recovery_blocks WHERE organization=? AND run_id=?',(organization,run_id)).fetchone()
        return {'code':row[0],'detail':CHECKPOINT_BLOCKS[row[0]]} if row and row[0] in CHECKPOINT_BLOCKS else None

    def _set_checkpoint_block(self, organization, run_id, code):
        with self.control() as db:
            if code is None:
                db.execute('DELETE FROM checkpoint_recovery_blocks WHERE organization=? AND run_id=?',(organization,run_id))
            else:
                db.execute('INSERT INTO checkpoint_recovery_blocks VALUES(?,?,?) ON CONFLICT(organization,run_id) DO UPDATE SET code=excluded.code WHERE code<>excluded.code',(organization,run_id,code))

    def _restore_checkpoint_reviews(self, receipt):
        checkpoints={(r['organization'],r['run_id']) for r in receipt.get('checkpoint_runs',[])}
        if not checkpoints:
            return
        with self.control() as db:
            sessions=[json.loads(r[0]) for r in db.execute('SELECT payload FROM sessions ORDER BY rowid')]
        for session in sessions:
            scope=session['organization'];run=session['run_id']
            try:
                app=self._app(session)
                run=run or app.tasks.find_run(scope,session['id'])
                if (scope,run) not in checkpoints:
                    continue
                self._restore_checkpoint_case(session,app,run)
                self._set_checkpoint_block(scope,run,None)
            except Exception as error:
                if (scope,run) not in checkpoints:
                    continue
                code=('checkpoint_authority_unavailable' if isinstance(error,(Conflict,ActorUnavailable)) else
                      'checkpoint_storage_unavailable' if isinstance(error,(OSError,sqlite3.Error)) else
                      'checkpoint_validation_unavailable' if isinstance(error,ValueError) else 'checkpoint_recovery_unavailable')
                try:self._set_checkpoint_block(scope,run,code)
                except Exception:pass  # The original domain stop remains discoverable.

    def _restore_checkpoint_case(self, session, app, run):
        scope=session['organization']
        # Case creation grants no approval. Existing cases still need their
        # presentation journal reconciled after a partial restoration.
        case=({'case_id':session['case_id']} if session['case_id'] else app.reviews.store.open_case(scope,run,'local-operator'))
        review=app.reviews.store.view(scope,case['case_id'])
        if review['run_id']!=run:
            raise Conflict('Checkpoint case differs from its original run')
        with self.control() as db:
            db.execute('BEGIN IMMEDIATE')
            current=json.loads(db.execute('SELECT payload FROM sessions WHERE id=?',(session['id'],)).fetchone()[0])
            if current['case_id'] and current['case_id']!=case['case_id']:
                raise Conflict('Checkpoint session already refers to another case')
            current |= {'run_id':run,'case_id':case['case_id']}
            db.execute('UPDATE sessions SET payload=? WHERE id=?',(canonical(current),session['id']))
            db.commit()
        source=session.get('conversation_plan')
        if source:
            row=self.preparations.store.for_revision('local-conversations',source['conversation_id'],source['revision'])
            if row:
                valid=review['validation_report']['review_ready']
                status='review_ready' if valid else 'blocked'
                detail='Completed draft preserved for human review.' if valid else 'Completed draft preserved; current validation blocks review.'
                if row['status']!=status or row['detail']!=detail:
                    self.preparations.store.update('local-conversations',row,status,detail)

    def recover_execution(self):
        # Only call on exclusive startup or from the supported local executor.
        self._ensure_descendant_links()
        for receipt in self._conversation_app().execution.stopped_checkpoints('local-conversations'):
            self._restore_checkpoint_reviews(receipt)

    def step_preparation_plan(self, organization, row):
        self._preparation_scope(organization)
        with self.lock:
            app = self._conversation_app(with_model=not row["inputs"]["fixture"])
            app.worker.tick(organization, run_id=row["run_id"])
            return self._run_generation(app, organization, row["run_id"])

    def step_preparation_campaign(self, organization, row, plan):
        self._preparation_scope(organization)
        return self.draft_conversation(row["inputs"]["conversation_id"], row["id"] + ":draft",
                                       row["inputs"]["revision"], plan["id"], partial=True)

    def preparation_audience_selected(self, organization, row, plan):
        self._preparation_scope(organization)
        selected = self._conversation_app().conversation_audiences.store.get(organization, row['inputs']['conversation_id'], row['inputs']['revision'])
        return selected is not None and selected['plan_id'] == plan['id']

    def select_conversation_audience(self, conversation_id, **inputs):
        try:
            receipt = self._conversation_app().conversation_audiences.select('local-conversations', conversation_id, **inputs)
        except (Conflict, ValueError, NotFound) as error:
            raise AudienceSelectionRejected(str(error)) from error
        row = self.preparations.store.for_revision('local-conversations', conversation_id, receipt['revision'])
        if row and row['status'] == 'selecting_audience':
            self.preparations.step('local-conversations', row['id'])
        return self.conversation(conversation_id) | {'audience_receipt':receipt}

    def preparation_generation(self, organization, row):
        self._preparation_scope(organization)
        with self.control() as db:
            match = db.execute("SELECT session_id FROM conversation_draft_requests WHERE conversation_id=? AND request_id=?",
                               (row["inputs"]["conversation_id"], row["id"] + ":draft")).fetchone()
        if match:
            return self._generation(self._session(match[0]))
        app = self._conversation_app()
        run_id = row["run_id"]
        if run_id is None:
            source = app.conversations.view(organization, row["inputs"]["conversation_id"])
            plan = next((p for p in source["plans"] if p["request_id"] == row["plan_request_id"]), None)
            run_id = plan["run_id"] if plan else None
        return self._run_generation(app, organization, run_id) if run_id else None

    def start_preparation(self, conversation_id, request_id, expected_revision, fixture, allow_model_copy, use_audience_catalogue=False):
        self.preparations.admit("local-conversations", conversation_id, request_id, expected_revision, fixture, allow_model_copy, use_audience_catalogue)
        return self.conversation(conversation_id)

    def preparation_progress(self, conversation_id):
        source = self.preparation_source("local-conversations", conversation_id)
        values = []
        for row in self.preparations.store.listing("local-conversations", conversation_id):
            generation = self.preparation_generation("local-conversations", row)
            # Frozen model inputs remain server-side. The plan's existing guidance
            # projection is the public inspection surface for that content.
            public = {k: v for k, v in row.items() if k != "planning_context"}
            if row['inputs']['revision'] <= source['execution']['stopped_through'] and row['status'] in ACTIVE_PREPARATION | {'blocked','needs_consent'}:
                public |= {'status':'cancelled','detail':'Stopped by you. Send a new brief to start new work; the shared allowance does not reset.'}
            if generation and generation.get('budget_exhausted') and public['status'] in ACTIVE_PREPARATION | {'failed','blocked'}:
                public |= {'status':'budget_exhausted','detail':'The shared model-call allowance is exhausted. Inspect usage or start a new conversation. Existing consent does not increase this allowance.'}
            if generation and generation.get('checkpoint_recovery'):
                public |= {'status':'blocked','detail':generation['checkpoint_recovery']['detail'],'checkpoint_recovery':generation['checkpoint_recovery']}
            if generation and generation.get('ancestry_pending'):
                public |= {'status':'blocked','detail':REVISION_BLOCKS['ancestry_unavailable']}
            if row["status"] == "review_ready":
                with self.control() as db:
                    admitted = db.execute("SELECT session_id FROM conversation_draft_requests WHERE conversation_id=? AND request_id=?",
                                          (conversation_id, row["id"] + ":draft")).fetchone()
                ready = False
                if admitted:
                    session = self._session(admitted[0])
                    if session["case_id"]:
                        report = self._app(session).reviews.store.view(session["organization"], session["case_id"])["validation_report"]
                        ready = report["review_ready"]
                if not ready:
                    public = public | {"status":"blocked", "detail":"Current campaign validation blocks review. Inspect the campaign validation report."}
            app = self._conversation_app()
            selection = app.conversation_audiences.store.get('local-conversations', conversation_id, row['inputs']['revision'])
            public['audience_selection'] = selection if row['inputs'].get('use_audience_catalogue') else None
            if row['status'] == 'selecting_audience' and source['revision'] == row['inputs']['revision']:
                plan = source['current_plan']
                if plan and plan['result']:
                    try:
                        public['audience_candidates'] = app.conversation_audiences.candidates('local-conversations', conversation_id, source['revision'], plan['result']['id'])
                    except (ValueError, Conflict, NotFound, OSError):
                        public['audience_error'] = 'The audience catalogue is unavailable. Restore the source and refresh this conversation.'
            values.append(public | {"current": source["revision"] == row["inputs"]["revision"], "generation": generation})
        return values

    def advance_preparations(self):
        self.recover_execution()
        self.advance_actions()
        for row in self.preparations.store.listing("local-conversations"):
            if row["status"] in ACTIVE_PREPARATION:
                self.preparations.step("local-conversations", row["id"])
        self.advance_copy_revisions()

    def request_copy_revision(self, identity, request_id, expected_subject, target_id, feedback, allow_model_copy):
        if allow_model_copy is not True:
            raise ValueError("Explicit model-copy permission is required for a revision")
        with self.lock:
            session = self._session(identity)
            if session["mode"] != "model" or not session["case_id"]:
                raise Conflict("Prepare a grounded model campaign before revising copy")
            app = self._app(session)
            prior = app.reviews.store.revision_request(session["organization"], request_id)
            if prior is None:
                app = self._app(session, with_model=True)
            app.revisions.admit(session["organization"], session["case_id"], request_id, expected_subject, target_id, feedback, allow_model_copy)
            return self.view(identity) | {"command_replayed": prior is not None}

    def _copy_revision_progress(self, app, scope, case):
        rows = app.revisions.view(scope, case)
        origin = app.execution.for_run(scope, app.reviews.store.view(scope,case)['run_id']) if rows else None
        for row in rows:
            generation = self._run_generation(app, scope, row["run_id"]) if row["run_id"] else None
            row["generation"] = generation
            with self.control() as db:
                block = db.execute("SELECT code FROM copy_revision_blocks WHERE organization=? AND revision_id=?", (scope, row["id"])).fetchone()
            code = block[0] if block and block[0] in REVISION_BLOCKS else None
            row["block"] = {"code": code, "detail": REVISION_BLOCKS[code]} if code else None
            if code and row["status"] in {"admitted", "queued", "running"}:
                row["status"] = "blocked"
            if origin and origin['run_revision'] <= origin['stopped_through'] and row['status'] in {'admitted','queued','running','stale','blocked'}:
                row['status']='cancelled'
            if generation and generation["outcome_uncertain"] and row["status"] not in {"queued", "running"}:
                row["status"] = "uncertain"
            if generation and generation.get('budget_exhausted') and row['status']=='failed':
                row['status']='budget_exhausted'
            if generation and generation.get('ancestry_pending'):
                row |= {'status':'blocked','block':{'code':'ancestry_unavailable','detail':REVISION_BLOCKS['ancestry_unavailable']}}
        return rows

    def _set_revision_block(self, scope, revision_id, code):
        with self.control() as db:
            if code is None:
                db.execute("DELETE FROM copy_revision_blocks WHERE organization=? AND revision_id=?", (scope, revision_id))
            else:
                if code not in REVISION_BLOCKS:
                    raise ValueError("Use a public revision blocker code")
                db.execute("INSERT INTO copy_revision_blocks VALUES(?,?,?) ON CONFLICT(organization,revision_id) DO UPDATE SET code=excluded.code WHERE code<>excluded.code", (scope, revision_id, code))

    def recover_copy_revisions(self):
        with self.control() as db:
            sessions = [json.loads(r[0]) for r in db.execute("SELECT payload FROM sessions")]
        for session in sessions:
            if not session["case_id"]:
                continue
            app, scope = self._app(session), session["organization"]
            for row in app.revisions.view(scope, session["case_id"]):
                if row["run_id"] and app.tasks.inspect(scope, row["run_id"])["run"]["status"] not in {"failed", "cancelled", "succeeded"} and self._run_generation(app, scope, row["run_id"])["outcome_uncertain"]:
                    app.tasks.cancel(scope, row["run_id"], app.clock())

    def advance_copy_revisions(self):
        with self.control() as db:
            sessions = [json.loads(r[0]) for r in db.execute("SELECT payload FROM sessions")]
        for session in sessions:
            if not session["case_id"]:
                continue
            app, scope = self._app(session), session["organization"]
            for row in app.revisions.view(scope, session["case_id"]):
                blocker = "continuation_unavailable"
                try:
                    if row["status"] == "stale":
                        if row["run_id"]:
                            app.tasks.cancel(scope, row["run_id"], app.clock())
                        continue
                    if row["status"] not in {"admitted", "queued", "running", "complete"}:
                        continue
                    if row["status"] == "complete" and app.tasks.inspect(scope, row["run_id"])["run"]["status"] in {"succeeded", "failed", "cancelled"}:
                        continue
                    with self.lock:
                        receipt = app.reviews.store.revision_request(scope, row["request_id"])
                        blocker = "evidence_unavailable"
                        today = datetime.fromtimestamp(app.clock(), timezone.utc).date()
                        for pack in (self.pack, receipt["context"]["product_facts"], app.reviews.store.evidence(scope)["pack"]):
                            validate_fact_pack(pack, today)
                        blocker = "configuration_unavailable"
                        configured = self._app(session, with_model=True)
                        run = configured.revisions.reconcile(scope, receipt)
                        blocker = "continuation_unavailable"
                        # Configuration is restored before dispatch. Do not let
                        # its old blocker relabel a live reserved call as uncertain.
                        self._set_revision_block(scope, row["id"], None)
                        configured.worker.tick(scope, run_id=run)
                except Exception:
                    # Projection metadata is not task authority. Keep original
                    # admission/consent, leases and inference journals intact.
                    # Raw configuration/provider errors never leave this boundary.
                    self._set_revision_block(scope, row["id"], blocker)

    def message_conversation(self, conversation_id, request_id, expected_revision, content):
        return self._conversation_app().conversations.message("local-conversations", conversation_id, request_id, expected_revision, content)

    def plan_conversation(self, conversation_id, request_id, expected_revision):
        with self.lock:
            app = self._conversation_app(with_model=True)
            run_id = app.conversations.plan("local-conversations", conversation_id, request_id, expected_revision)
            app.worker.drain("local-conversations", run_id=run_id)
            return app.conversations.view("local-conversations", conversation_id)

    def plan_conversation_fixture(self, conversation_id, request_id, expected_revision):
        with self.lock:
            app = self._conversation_app()
            run_id = app.conversations.plan_fixture("local-conversations", conversation_id, request_id, expected_revision)
            app.worker.drain(organization="local-conversations", run_id=run_id)
            return app.conversations.view("local-conversations", conversation_id)

    def draft_conversation(self, conversation_id, request_id, expected_revision, plan_id, *, partial=False):
        identifier(conversation_id), identifier(request_id), identifier(plan_id)
        if type(expected_revision) is not int or expected_revision < 1:
            raise ValueError("Select a current conversation revision")
        fingerprint = digest({"conversation_id": conversation_id, "revision": expected_revision, "plan_id": plan_id})
        session_id = "workspace_" + digest({"conversation_id": conversation_id, "plan_id": plan_id})[:24]
        with self.lock:
            with self.control() as db:
                prior_draft = db.execute("SELECT * FROM conversation_draft_requests WHERE conversation_id=? AND request_id=?", (conversation_id, request_id)).fetchone()
                if prior_draft:
                    if prior_draft["request_hash"] != fingerprint:
                        raise Conflict("Draft request already binds different proposal inputs")
                    return self.prepare(prior_draft["session_id"], partial=partial)
            view = self._conversation_app().conversations.view("local-conversations", conversation_id)
            current = view["current_plan"]
            plan = current["result"] if current and current["status"] == "succeeded" else None
            if view["revision"] != expected_revision or not plan or plan["id"] != plan_id or plan["outcome"] != "brief_proposal":
                raise Conflict("Select the exact current completed brief proposal")
            selection = self._conversation_app().conversation_audiences.store.get('local-conversations', conversation_id, expected_revision)
            preparation = self.preparations.store.for_revision('local-conversations', conversation_id, expected_revision)
            requires_audience = selection is not None or bool(preparation and preparation['inputs'].get('use_audience_catalogue'))
            if requires_audience and selection is None:
                raise Conflict('Confirm an exact audience dataset before campaign preparation')
            model_copy = plan["copy_mode"] == "model"
            start = self.real_clock() if model_copy else datetime.fromisoformat(self.pack["checked_on"]).replace(tzinfo=timezone.utc).timestamp() + 43200
            if model_copy:
                validate_fact_pack(self.pack, datetime.fromtimestamp(start, timezone.utc).date())
            if requires_audience:
                start = max(start, self.real_clock())
            session = {"id": session_id, "name": "Conversation / " + plan["objective"][:70], "mode": plan["copy_mode"],
                       "organization": session_id, "database_scope": "conversations", "clock": start, "parent_id": None,
                       "clock_mode": "REAL" if model_copy else "SIMULATED", "created_at": self.real_clock(), "run_id": None,
                       "case_id": None, "cohort_id": None, "conversation_plan": plan, **({"audience_selection":selection} if requires_audience else {})}
            with self.control() as db:
                db.execute("BEGIN IMMEDIATE")
                try:
                    replay = db.execute("SELECT * FROM conversation_draft_requests WHERE conversation_id=? AND request_id=?", (conversation_id, request_id)).fetchone()
                    if replay is not None and (replay["request_hash"] != fingerprint or replay["session_id"] != session_id):
                        raise Conflict("Draft request already binds different proposal inputs")
                    existing = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
                    if existing is not None and existing["request_hash"] != fingerprint:
                        raise Conflict("Campaign identity already binds different proposal inputs")
                    if existing is None:
                        db.execute("INSERT INTO sessions VALUES(?,?,?)", (session_id, fingerprint, canonical(session)))
                    if replay is None:
                        db.execute("INSERT INTO conversation_draft_requests VALUES(?,?,?,?)", (conversation_id, request_id, fingerprint, session_id))
                    db.commit()
                except BaseException:
                    db.rollback()
                    raise
            return self.prepare(session_id, partial=partial)

    def _followup_progress(self, app, scope, identity):
        rows = []
        for p in app.followups.listing(scope,identity):
            sid = "workspace_" + digest({"followup":p["id"]})[:24]
            try:
                child = self._session(sid)
                p = p | {"session_id":sid,"mode":child["mode"],"case_id":child["case_id"],"generation":self._generation(child)}
            except NotFound:
                p = p | {"session_id":None}
            rows.append(p)
        return rows

    def propose_followup(self, identity, request_id, cohort_id):
        identifier(request_id), identifier(cohort_id)
        with self.lock:
            parent = self._session(identity)
            app, scope = self._app(parent), parent["organization"]
            try:
                old = app.followups.get(scope, "followup-request:" + request_id)
                if old["parent_id"] != identity or old["source_cohort"] != cohort_id:
                    raise Conflict("Follow-up request already binds different source inputs")
                return old
            except NotFound:
                pass
            if parent["cohort_id"] != cohort_id:
                raise Conflict("Select the displayed source cohort")
            source = app.learning.store.view(scope, cohort_id)
            if source["status"] != "finalized":
                raise Conflict("Finalize complete mature learning before proposing a follow-up")
            view = app.reviews.store.view(scope, parent["case_id"])
            segments = tuple(sorted({c["segment"] for c in view["manifest"]["creatives"]}))
            budget = view["manifest"]["brief"]["budget_pence"]
            snapshot = app.followup_population(scope, datetime.fromtimestamp(app.clock(), timezone.utc).date().isoformat())
            excluded = app.followups.excluded(scope)
            snapshot = replace(snapshot, records=tuple(r for r in snapshot.records if r.business_id not in excluded))
            preview_brief = FollowupBrief("preview",budget,segments=segments,followup_id="followup_preview")
            creatives = tuple(c for c in fixture_catalog() if c.segment in segments)
            preview = build_draft(snapshot, preview_brief, creatives)
            hypothesis = "Retest the source recommendation with contrasting A/B hooks and a no-mail control on a disjoint synthetic population; retain A/B comparison and do not assume the earlier lift will repeat."
            memory = app.learning.store.memory_snapshot(scope, segments)
            p = {"parent_id":identity, "source_cohort":cohort_id, "learning":source,
                "model_config":asdict(ModelConfig("openai/gpt-oss-120b",max_calls=10,force_tool_choice=True)), "memory":memory, "brief":{"budget_pence":budget,"unit_cost_pence":85,"max_candidates":1000,"policy_version":"demo-marketing/v1","segments":list(segments)},
                "hypothesis":hypothesis, "snapshot_id":app.audiences.put(snapshot),
                "population":sorted({r["business_id"] for r in csv.DictReader(io.StringIO(preview.assignments_csv))}),
                "contexts":app.followup_contexts(scope,snapshot,segments,memory,hypothesis),
                "epochs":[view["authority"]["evidence_epoch"],view["authority"]["audience_epoch"]],
                "counts":preview.manifest["counts"], "cost_pence":preview.manifest["variable_cost_pence"],
                "eligible":preview.manifest["counts"]["mailed"] > 0 and preview.manifest["counts"]["holdout"] > 0,
                "source_label":"SYNTHETIC_ONLY: bounded 2,000-record inventory, preserving original business identities"}
            return app.followups.put(scope, request_id, p)

    def prepare_followup(self, identity, request_id, proposal_id, mode, allow_model_copy):
        identifier(request_id), identifier(proposal_id)
        if mode not in {"fixture","model"} or type(allow_model_copy) is not bool or (mode == "model" and not allow_model_copy) or (mode == "fixture" and allow_model_copy):
            raise ValueError("Choose fixture copy or explicit model-copy permission")
        with self.lock:
            parent = self._session(identity)
            app = self._app(parent)
            p = app.followups.get(parent["organization"],proposal_id)
            if p["parent_id"] != identity or not p["eligible"]:
                raise Conflict("This proposal belongs to another campaign or has insufficient independent population")
            sid = "workspace_" + digest({"followup":proposal_id})[:24]
            fingerprint = digest({"parent":identity,"proposal":proposal_id,"mode":mode,"allow_model_copy":allow_model_copy})
            session_fingerprint = digest({"proposal":proposal_id,"mode":mode,"allow_model_copy":allow_model_copy})
            with self.control() as db:
                db.execute("BEGIN IMMEDIATE")
                try:
                    request = db.execute("SELECT * FROM followup_prepare_requests WHERE organization=? AND request_id=?",(parent["organization"],request_id)).fetchone()
                    if request and (request["request_hash"] != fingerprint or request["session_id"] != sid):
                        raise Conflict("Follow-up preparation request already binds different inputs")
                    old = db.execute("SELECT * FROM sessions WHERE id=?",(sid,)).fetchone()
                    if old and old["request_hash"] != session_fingerprint:
                        raise Conflict("Follow-up already binds its original copy mode and permission")
                    if not old:
                        app.followups.check(parent["organization"],p,sid)
                        child = {"id":sid,"name":"Follow-up experiment","mode":mode,"organization":parent["organization"],
                            "clock":max(parent["clock"],self.real_clock()),"clock_mode":"SIMULATED","created_at":self.real_clock(),
                            "parent_id":identity,"database_scope":parent.get("database_scope","campaign"),
                            "run_id":None,"case_id":None,"cohort_id":None,"followup_id":proposal_id}
                        db.execute("INSERT INTO sessions VALUES(?,?,?)",(sid,session_fingerprint,canonical(child)))
                    if not request:
                        db.execute("INSERT INTO followup_prepare_requests VALUES(?,?,?,?)",(parent["organization"],request_id,fingerprint,sid))
                    db.commit()
                except BaseException:
                    db.rollback()
                    raise
            return self.prepare(sid)

    def create(self, request_id, mode, parent_id=None):
        identifier(request_id)
        if type(mode) is not str or mode not in {"fixture", "model"}:
            raise ValueError("Choose fixture or model copy")
        identity = "workspace_" + digest({"request_id": request_id})[:24]
        fingerprint = digest({"mode": mode, "parent_id": parent_id})
        with self.lock:
            with self.control() as db:
                old = db.execute("SELECT * FROM sessions WHERE id=?", (identity,)).fetchone()
                if old and old["request_hash"] != fingerprint:
                    raise Conflict("Campaign request already binds another copy mode")
                if old is None:
                    parent = self._session(parent_id) if parent_id else None
                    if parent and (not parent["cohort_id"] or self._app(parent).learning.store.view(parent["organization"], parent["cohort_id"])["status"] != "finalized"):
                        raise Conflict("Only finalized learning can seed the next experiment")
                    start = (datetime.fromisoformat(self.pack["checked_on"]).replace(tzinfo=timezone.utc).timestamp() + 43200
                             if mode == "fixture" else self.real_clock())
                    if parent:
                        start = max(start, parent["clock"])
                    session = {"id": identity, "name": "Working capital / " + ("model copy" if mode == "model" else "offline demo"),
                        "mode": mode, "organization": parent["organization"] if parent else identity, "clock": start,
                        "parent_id": parent_id, "database_scope": (parent.get("database_scope") or ("conversations" if parent.get("conversation_plan") or parent["organization"] == "local-conversations" else "campaign")) if parent else "campaign", "clock_mode": "SIMULATED" if parent or mode == "fixture" else "REAL", "created_at": self.real_clock(), "run_id": None,
                        "case_id": None, "cohort_id": None}
                    db.execute("INSERT INTO sessions VALUES(?,?,?)", (identity, fingerprint, canonical(session)))
            return self.prepare(identity)

    def prepare(self, identity, *, partial=False):
        with self.lock:
            self._ensure_descendant_links(strict_session_id=identity)
            session = self._session(identity)
            if session["case_id"]:
                return self.view(identity)
            app = self._app(session, with_model=True)
            store = app.reviews.store
            scope = session["organization"]
            store.initialize_actor(scope, "local-operator", ("operator",))
            store.initialize_actor(scope, "local-reviewer", ("reviewer",))
            if store.evidence(scope) is None:
                store.activate(scope, "local-operator", "initial-evidence", self.pack, ReviewPolicy())
            start = app.start_model if session["mode"] == "model" else app.start
            # Resume the admitted plan, including after a lost metadata write.
            # Recomputing context here could conflict with newly learned memory.
            run = session["run_id"] or app.tasks.find_run(scope, identity)
            if session.get("conversation_plan") and session["mode"] == "model":
                source = session["conversation_plan"]
                current = app.conversations.view("local-conversations", source["conversation_id"])
                if current["revision"] != source["revision"] or not current["current_plan"] or current["current_plan"]["result"] != source:
                    raise Conflict("Conversation changed before campaign preparation")
            if run is None:
                if session.get("followup_id"):
                    p = app.followups.get(scope,session["followup_id"])
                    app.followups.check(scope,p,identity)
                    brief = brief_from(p["brief"] | {"campaign_id":identity,"followup_id":p["id"]})
                    if session["mode"] == "model":
                        if asdict(app.inference.config) != p["model_config"]:
                            raise Conflict("Restore the model settings frozen in this follow-up proposal")
                        run = app.start_model(scope, identity, snapshot_override=app.audiences.get(scope,p["snapshot_id"]),brief_override=brief,contexts_override=p["contexts"])
                    else:
                        run = app.start_followup(scope,identity,p["snapshot_id"],brief)
                elif session.get("conversation_plan"):
                    source = session["conversation_plan"]
                    current = app.conversations.view("local-conversations", source["conversation_id"])
                    if current["revision"] != source["revision"] or not current["current_plan"] or current["current_plan"]["result"] != source:
                        raise Conflict("Conversation changed before campaign preparation")
                    run = app.start_conversation(scope, identity, source, datetime.fromtimestamp(session["clock"], timezone.utc).date().isoformat(),
                                                 selected_audience=bool(session.get('audience_selection')))
                else:
                    run = start(scope, identity, as_of=datetime.fromtimestamp(session["clock"], timezone.utc).date().isoformat())
            session["run_id"] = run
            self._save(session)
            if session["mode"] == "model":
                today = datetime.fromtimestamp(self.real_clock(), timezone.utc).date()
                validate_fact_pack(store.evidence(scope)["pack"], today)
                admitted = app.tasks.inspect(scope, run)
                for context_id in admitted["tasks"][0]["inputs"]["context_ids"].values():
                    validate_fact_pack(app.memory.get_context(scope, context_id)["product_facts"], today)
            app.worker.drain(scope, max_tasks=1 if partial else 20, run_id=run)
            state = app.tasks.inspect(scope, run)
            if state["run"]["status"] not in {"waiting", "succeeded"}:
                if partial:
                    return self.view(identity)
                raise Conflict("Preparation has not reached review. Inspect the task status before resuming.")
            case = store.open_case(scope, run, "local-operator")
            session["case_id"] = case["case_id"]
            self._save(session)
            return self.view(identity)

    def view(self, identity, *, _attempt=0):
        session = self._session(identity)
        app = self._app(session)
        scope = session["organization"]
        public = {k: v for k, v in session.items() if k != "organization"}
        public["clock"] = app.clock()
        if not session["case_id"]:
            return {"session": public, "review": None, "audience": [], "learning": None,
                    "tasks": app.tasks.inspect(scope, session["run_id"]) if session["run_id"] else None}
        review = app.reviews.store.view(session["organization"], session["case_id"])
        draft = app.drafts.get(session["organization"], review["subject"]["draft_id"])
        snapshot = app.audiences.get(scope, review["subject"]["snapshot_id"])
        assignments = {r["business_id"]: r for r in csv.DictReader(io.StringIO(draft.assignments_csv))}
        population = [{"id": r.business_id, "segment": r.segment, "country": r.country,
            "entity_type": r.entity_type, "suppressed": r.suppressed or r.business_id in review["suppressions"],
            "arm": assignments.get(r.business_id, {}).get("arm", "excluded"),
            "score": r.propensity_ppm, "address": r.address} for r in snapshot.records]
        revisions = self._copy_revision_progress(app, scope, session["case_id"])
        # Admission can reject an approval without changing the subject. Recheck
        # the whole transactional review projection, including decisions and
        # current authority, after reading progress. Only the read time may vary.
        current_review = app.reviews.store.view(scope, session["case_id"])
        def stable_projection(value):
            report = value.get("validation_report", {})
            return {k:v for k,v in value.items() if k not in {"as_of", "validation_report"}} | {
                "validation_report": {k:v for k,v in report.items() if k not in {"id", "evaluated_at"}}}
        if stable_projection(current_review) != stable_projection(review):
            if _attempt >= 3:
                raise Conflict("Campaign changed while loading; refresh the review")
            return self.view(identity, _attempt=_attempt + 1)
        return {"session": public, "review": review, "audience": population,
            "copy_revisions": revisions, "followups": self._followup_progress(app,scope,identity),
            "learning": app.learning.store.view(scope, session["cohort_id"]) if session["cohort_id"] else None,
            "tasks": app.tasks.inspect(scope, session["run_id"])}

    def action(self, identity, action, payload):
        with self.lock:
            session = self._session(identity)
            app = self._app(session)
            scope, case = session["organization"], session["case_id"]
            if not case:
                raise Conflict("Prepare this campaign before recording a decision")
            fields = {"approve": {"subject_id", "reason"}, "reject": {"subject_id", "reason"},
                "refresh": {"subject_id"}, "revoke": {"approval_id", "reason"},
                "suppress": {"business_id", "reason"}, "handoff": {"approval_id"},
                "open-learning": set(), "observe": set(), "finalize": set()}
            # Chat binds each explicit simulation decision to the displayed
            # accepted job/cohort. Retain the existing workspace payloads.
            bound_learning = action in {"open-learning", "observe", "finalize"} and "handoff_id" in payload
            if bound_learning:
                fields[action] = {"handoff_id"} if action == "open-learning" else {"handoff_id", "cohort_id"}
            if action not in fields or set(payload) != fields[action] | {"request_id"}:
                raise ValueError("Use the exact fields for this workspace action")
            for field in fields[action]:
                text(payload[field]) if field == "reason" else identifier(payload[field])
            if bound_learning:
                accepted = app.learning.source.accepted(scope, case)
                if accepted["job_id"] != payload["handoff_id"]:
                    raise Conflict("Learning request refers to a different accepted job")
                if action != "open-learning" and (payload["cohort_id"] != session["cohort_id"] or payload["cohort_id"] != accepted["id"]):
                    raise Conflict("Learning request refers to a different outcome cohort")
            request_id = payload["request_id"]
            identifier(request_id)
            fingerprint = digest({"action": action, "payload": payload})
            with self.control() as db:
                old = db.execute("SELECT * FROM commands WHERE session_id=? AND request_id=?", (identity, request_id)).fetchone()
                if old:
                    if old["request_hash"] != fingerprint:
                        raise Conflict("Workspace request already binds different action inputs")
                    if old["done"]:
                        return self.view(identity) | {"command_replayed": True}
                else:
                    db.execute("INSERT INTO commands VALUES(?,?,?,0)", (identity, request_id, fingerprint))
            store = app.reviews.store
            if action in {"approve", "reject"}:
                store.decide(scope, case, payload["subject_id"], "local-reviewer", action, request_id, payload["reason"], 86400)
            elif action == "refresh":
                app.reviews.refresh(scope, case, payload["subject_id"], "local-operator", request_id)
            elif action == "revoke":
                store.revoke(scope, case, payload["approval_id"], "local-reviewer", request_id, payload["reason"])
            elif action == "suppress":
                # A suppression is an independent operator instruction, never
                # an approval. The domain invalidates affected authority.
                store.suppress(scope, "local-operator", request_id, payload["business_id"], payload["reason"])
            elif action == "handoff":
                store.handoff(scope, case, payload["approval_id"], "local-operator", request_id)
            elif action == "open-learning":
                receipt = app.learning.open(scope, case, "local-operator", request_id)
                session["cohort_id"] = receipt["cohort_id"]
                self._save(session)
            elif action in {"observe", "finalize"}:
                if not session["cohort_id"]:
                    raise Conflict("Open an outcome window first")
                cohort = app.learning.source.accepted(scope, case)
                target = cohort["window_start"] + 7 * 86400 if action == "observe" else cohort["window_end"]
                session["clock"] = max(session["clock"], target)
                session["clock_mode"] = "SIMULATED"
                self._save(session)
                # The existing app's clock closes over this session dictionary.
                rows = []
                for member in cohort["members"]:
                    response = int(digest({"business": member["business_id"], "seed": 81})[:8], 16) % 1000 < {"A": 220, "B": 35, "no_mail": 20}[member["arm"]]
                    if response or action == "finalize":
                        rows.append(member | {"response": response, "observed_at": cohort["window_start"] + 7 * 86400 if response else cohort["window_end"]})
                if rows:
                    app.learning.store.ingest(scope, "local-operator", request_id + ":import", session["cohort_id"],
                        {"schema": "synthetic-outcomes/v1", "mode": "SYNTHETIC_ONLY", "cohort_id": session["cohort_id"], "outcomes": rows})
                if action == "finalize":
                    app.learning.store.finalize(scope, "local-operator", request_id, session["cohort_id"], cohort["window_end"])
            else:
                raise ValueError("Unknown workspace action")
            with self.control() as db:
                db.execute("UPDATE commands SET done=1 WHERE session_id=? AND request_id=?", (identity, request_id))
            return self.view(identity)

    def artifact(self, identity, kind, expected_subject):
        with self.lock:
            session = self._session(identity)
            app = self._app(session)
            review = app.reviews.store.view(session["organization"], session["case_id"])
            if review["subject"]["id"] != expected_subject:
                raise Conflict("Campaign revision changed before download; refresh the workspace")
            draft = app.drafts.get(session["organization"], review["subject"]["draft_id"])
            if kind == "handoff":
                receipt = review["handoff"]
                if receipt is None:
                    raise Conflict("This campaign has no accepted simulated handoff")
                if receipt["subject_id"] != expected_subject or receipt["draft_id"] != draft.id:
                    raise Conflict("Acceptance receipt does not match the displayed subject")
                return canonical(receipt).encode(), "application/json", "handoff.json"
            if kind == "manifest":
                return canonical(draft.manifest).encode(), "application/json", "manifest.json"
            if kind in {"mailing", "assignments"}:
                return getattr(draft, kind + "_csv").encode(), "text/csv; charset=utf-8", kind + ".csv"
            raise NotFound("Unknown artifact")
