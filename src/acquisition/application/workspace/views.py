"""Read-only workspace projections and user-facing blocker wording."""
import csv
from io import StringIO
import re
from acquisition.conversations import ACTIVE_PREPARATION
from acquisition.contracts import Conflict, NotFound, digest

def _partial_delivery(review):
    delivery = review.get('delivery') if review else None
    return delivery if delivery and delivery['status'] == 'partially_accepted' else None


REVISION_BLOCKS = {
    "ancestry_unavailable": "Historical campaign ancestry needs recovery. Restore its original workspace relationship before model calls can resume. Usage remains incomplete until that relationship is verified.",
    "evidence_unavailable": "Product evidence is unavailable or outside its review window. Review verified evidence and prepare a current campaign before requesting another revision. This request keeps its frozen inputs.",
    "configuration_unavailable": "Restore the server-side OpenRouter key and the original model settings. This saved request will resume automatically when its configuration is available. Do not submit another revision to retry it.",
    "browser_configuration_unavailable": "Continue this revision in its original OpenRouter browser session. It keeps the selected model and its original limits.",
    "continuation_unavailable": "Revision continuation is unavailable. Inspect the original run and server storage. The server will recheck this saved request; it will not repeat an uncertain provider call.",
}


CHECKPOINT_BLOCKS = {
    'checkpoint_authority_unavailable':'Review recovery is blocked. Restore a permitted local operator and checkpoint authority, then retry recovery. The stop remains committed; no generation has been repeated.',
    'checkpoint_storage_unavailable':'Review recovery is waiting for local storage. Restore storage and retry recovery. The completed checkpoint and stop receipt are preserved.',
    'checkpoint_validation_unavailable':'Review recovery needs valid checkpoint data. Inspect the saved draft and evidence. No generation or approval has been repeated.',
    'checkpoint_recovery_unavailable':'Review recovery is unavailable for this checkpoint. Inspect its saved case and local storage; other conversations can continue.',
}


class WorkspaceViews:
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
                partial = _partial_delivery(current_review)
                value['target_current']=(value['current'] and current_review['subject']['id']==target['subject_id']
                                         and current_review['candidate_valid'] and not current_review['handoff']
                                         and not partial)
                if partial:
                    value['target_blocked_reason'] = 'Partial simulated delivery closes this campaign to copy revisions.'
            if value['status'] in {'admitted','queued'} and not row['alias']:
                if app.admissions.required():
                    value |= {'status':'blocked','detail':'Execution remains paused pending cutover activation. Inspect the original request and run.'}
                elif row['model_config'].get('browser_binding'):
                    value['detail']='Continue in the original OpenRouter browser session.'
                elif row['model_config'] != app.actions.config.payload():
                    value |= {'status':'blocked','detail':'Restore the original routing model and limits to resume this saved request.'}
                else:
                    try:
                        if not self.models.legacy_available():
                            raise ValueError("Missing server key")
                    except ValueError:
                        value |= {'status':'blocked','detail':'Routing is waiting for the server-side OpenRouter key. Restore it to resume this saved request.'}
            if value['confirmed']:
                if value['confirmed'].get('kind') == 'typed_action_confirmation':
                    receipt = value['confirmed']
                    value['typed_effect'] = self._typed_effect(app, receipt)
                    value['continuation_pending'] = value['typed_effect'] is None and value['current']
                    if value['continuation_pending']:
                        try:
                            app.actions.store.validate_typed_confirmation('local-conversations', receipt)
                            if receipt['action'] == 'propose_next_experiment' and self._experiment_target(source, self._sessions()) != receipt['target']:
                                raise Conflict('Source experiment changed')
                            if receipt['action'] == 'prepare_campaign' and 'plan_id' not in receipt['target']:
                                if self._prepare_target(conversation_id, source, self._sessions()) != receipt['target']:
                                    raise Conflict('Another preparation owns the current brief')
                            if receipt['action'] == 'prepare_campaign' and 'plan_id' in receipt['target']:
                                choice = self._preparation_audience_choice(app, conversation_id, receipt['revision'], receipt['target']['plan_id'])
                                if not choice['audience_selection']:
                                    value['audience_choice'] = choice | {'status': 'selecting_audience', 'current': True,
                                                                         'inputs': {'revision': receipt['revision']}}
                                    value['continuation_pending'] = False
                        except (Conflict, NotFound):
                            value['continuation_pending'] = False
                    values.append(value)
                    continue
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

    def _generation(self, session):
        app = self._app(session)
        scope = session["organization"]
        run = session["run_id"] or app.tasks.find_run(scope, session["id"])
        if run is None:
            return {"run_id": None, "status": "admitted", "failed_tasks": [], "provider_error": None,
                    "outcome_uncertain": False, "unresolved_calls": []}
        generation=self._run_generation(app, scope, run)
        # A progress read can capture old cancelled metadata after recovery has
        # cleared its blocker. The immutable stop receipt still proves that the
        # executor retries this exact checkpoint, unlike an ordinary blocked run.
        source=session.get('conversation_plan')
        recovery_pending=bool(not session['case_id'] and source and any(
            checkpoint['organization']==scope and checkpoint['run_id']==run
            for receipt in self._conversation_app().execution.stopped_checkpoints('local-conversations')
            if receipt['conversation_id']==source['conversation_id']
            for checkpoint in receipt['checkpoint_runs']))
        return generation | {'checkpoint_recovery':self._checkpoint_block(scope,run),
                             'checkpoint_recovery_pending':recovery_pending}

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
                **({'admission_paused':True} if state.get('admission',{}).get('status')=='paused' else {}),
                'ancestry_pending':app.execution.pending(scope,run),
                "budget_exhausted":bool(execution and execution['remaining']==0),
                "outcome_uncertain": bool(unresolved), "unresolved_calls": unresolved,
                "steps": [{"capability": t["capability"], "status": t["status"]} for t in state["tasks"]]}

    def preparation_progress(self, conversation_id):
        source = self.preparation_source("local-conversations", conversation_id)
        values = []
        for row in self.preparations.store.listing("local-conversations", conversation_id):
            generation = self.preparation_generation("local-conversations", row)
            # Frozen model inputs remain server-side. The plan's existing guidance
            # projection is the public inspection surface for that content.
            public = {k: v for k, v in row.items() if k != "planning_context"}
            if generation and generation.get('admission_paused'):
                public |= {'status':'blocked','detail':'Execution remains paused pending cutover activation. Inspect the original request and run.'}
            elif row['status'] in {'admitting', 'planning', 'preparing'} and (row['planning_context'].get('model_config') or {}).get('browser_binding'):
                public['detail'] = 'Continue in the original OpenRouter browser session.'
            if row['inputs']['revision'] <= source['execution']['stopped_through'] and row['status'] in ACTIVE_PREPARATION | {'blocked','needs_consent'}:
                public |= {'status':'cancelled','detail':'Stopped by you. Send a new brief to start new work; the shared allowance does not reset.'}
            if generation and generation.get('budget_exhausted') and public['status'] in ACTIVE_PREPARATION | {'failed','blocked'}:
                public |= {'status':'budget_exhausted','detail':'The shared model-call allowance is exhausted. Inspect usage or start a new conversation. Existing consent does not increase this allowance.'}
            if generation and generation.get('checkpoint_recovery'):
                public |= {'status':'blocked','detail':generation['checkpoint_recovery']['detail'],'checkpoint_recovery':generation['checkpoint_recovery']}
            if generation and generation.get('ancestry_pending'):
                public |= {'status':'blocked','detail':REVISION_BLOCKS['ancestry_unavailable']}
            if row["status"] == "review_ready":
                admitted=self._draft_session_id(conversation_id,row['id']+':draft')
                ready = False
                if admitted:
                    session = self._session(admitted)
                    if session["case_id"]:
                        report = self._app(session).reviews.store.view(session["organization"], session["case_id"])["validation_report"]
                        ready = report["review_ready"]
                if not ready:
                    public = public | {"status":"blocked", "detail":"Current campaign validation blocks review. Inspect the campaign validation report."}
            app = self._conversation_app()
            selection = app.conversation_audiences.store.get('local-conversations', conversation_id, row['inputs']['revision'])
            public['audience_selection'] = selection if row['status'] == 'selecting_audience' or self.preparation_uses_catalogue('local-conversations', row) else None
            if row['status'] == 'selecting_audience' and source['revision'] == row['inputs']['revision']:
                plan = source['current_plan']
                if plan and plan['result']:
                    public |= self._preparation_audience_choice(app, conversation_id, source['revision'], plan['result']['id'])
            values.append(public | {"current": source["revision"] == row["inputs"]["revision"], "generation": generation})
        return values

    def _copy_revision_progress(self, app, scope, case):
        rows = app.revisions.view(scope, case)
        origin = app.execution.for_run(scope, app.reviews.store.view(scope,case)['run_id']) if rows else None
        for row in rows:
            generation = self._run_generation(app, scope, row["run_id"]) if row["run_id"] else None
            row["generation"] = generation
            block = self.control_store.revision_block(scope, row['id'])
            code = block if block in REVISION_BLOCKS else None
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

    def view(self, identity, *, _attempt=0):
        session = self._session(identity)
        app = self._app(session)
        scope = session["organization"]
        public = {k: v for k, v in session.items() if k != "organization"}
        public["clock"] = app.clock()
        if not session["case_id"]:
            state=app.tasks.inspect(scope,session['run_id']) if session['run_id'] else None
            return {"session": public, "review": None, "audience": [], "learning": None, "tasks":state,
                    **({'generation':self._generation(session)} if state and state.get('admission') else {})}
        review = app.reviews.store.view(session["organization"], session["case_id"])
        draft = app.drafts.get(session["organization"], review["subject"]["draft_id"])
        snapshot = app.audiences.get(scope, review["subject"]["snapshot_id"])
        assignments = {r["business_id"]: r for r in csv.DictReader(StringIO(draft.assignments_csv))}
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
        learning = None
        if session["cohort_id"]:
            monitoring = app.learning.monitoring.status(scope, session["cohort_id"])
            learning = app.learning.store.view(scope, session["cohort_id"])
            if monitoring is not None:
                learning["monitoring"] = monitoring
        return {"session": public, "review": review, "audience": population,
            "copy_revisions": revisions, "followups": self._followup_progress(app,scope,identity),
            "learning": learning,
            "tasks": app.tasks.inspect(scope, session["run_id"])}
