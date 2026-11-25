"""Loopback request routing, serialization and browser security boundaries."""
import json
import mimetypes
import secrets
import threading
from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from html import escape
from urllib.parse import urlsplit, parse_qs
from acquisition.contracts import Conflict, NotFound
from acquisition.conversations import ActionNotSaved, AudienceSelectionRejected, MessageRejectedConflict, MessageRejectedInvalid, MessageRejectedNotFound
from acquisition.reasoning import ModelError
from acquisition.youtube import YouTubeError
from acquisition.application.workspace import MonitoringRejected, ModelSelectionRejected, ModelSessionExpired
from acquisition.conversations import IntakePlanningRejected


class WorkspaceHTTPServer(ThreadingHTTPServer):
    # Closing waits for handlers that can reserve inference or commit state.
    daemon_threads = False

    def __init__(self, port, workspace, assets):
        self.workspace, self.assets = workspace, Path(assets).resolve()
        self.token = secrets.token_urlsafe(32)
        self.request_gate = threading.Lock()
        self.closing = False
        super().__init__(("127.0.0.1", port), Handler)
        self.workspace.youtube_origin = 'http://127.0.0.1:' + str(self.server_port)
        # Initialize the installed local capability at server startup, not during
        # a read-only package/preview request.
        self.workspace.youtube

    def process_request(self, request, client_address):
        with self.request_gate:
            if self.closing:
                self.shutdown_request(request)
                return
            super().process_request(request, client_address)


class Handler(BaseHTTPRequestHandler):
    server: WorkspaceHTTPServer
    timeout = 15  # Bound idle socket reads while the server drains handlers.

    def log_message(self, *args):
        pass

    def _send(self, code, body, content_type="application/json", filename=None):
        if isinstance(body, dict):
            body = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; font-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if filename:
            self.send_header("Content-Disposition", 'attachment; filename="' + filename + '"')
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass  # A closed polling tab does not change committed work.

    def _guard(self, mutation=False):
        try:
            self.parsed_target = urlsplit(self.path)
        except ValueError:
            self._send(400, {"error": "Use an origin-form workspace request target"})
            return False
        if (self.parsed_target.scheme or self.parsed_target.netloc or self.parsed_target.fragment
                or not self.path.startswith("/")):
            self._send(400, {"error": "Use an origin-form workspace request target"})
            return False
        host = self.headers.get("Host", "")
        hosts = {"127.0.0.1:" + str(self.server.server_port), "localhost:" + str(self.server.server_port)}
        if host not in hosts:
            self._send(403, {"error": "Use the local workspace origin"})
            return False
        if self.parsed_target.path.startswith("/api/"):
            token = self.headers.get("X-Workspace-Token", "")
            if not secrets.compare_digest(token, self.server.token):
                self._send(403, {"error": "Reload the workspace to establish a local session"})
                return False
            if mutation and self.headers.get("Origin") != "http://" + host:
                self._send(403, {"error": "Workspace actions require the same local origin"})
                return False
        return True

    def do_GET(self):
        if not self._guard():
            return
        try:
            path = self.parsed_target.path
            parts = path.strip('/').split('/')
            if path == '/api/youtube/store' and not self.parsed_target.query:
                return self._send(200, {'store_id': self.server.workspace.youtube.campaigns.store_identity()})
            if len(parts) == 4 and parts[:3] == ['api', 'youtube', 'campaigns'] and not self.parsed_target.query:
                return self._send(200, self.server.workspace.youtube.campaigns.read(parts[3]))
            if len(parts) == 3 and parts[:2] in (['youtube', 'media'], ['youtube', 'compare']):
                query = parse_qs(self.parsed_target.query, keep_blank_values=True)
                field = 'sha256' if parts[1] == 'media' else 'content'
                if set(query) != {field} or len(query[field]) != 1:
                    raise ValueError('Use an exact bundled media fingerprint')
                app = self.server.workspace.youtube.campaigns
                if parts[1] == 'media':
                    data = app.media(parts[2], query[field][0])
                    return self._send(200, data, 'video/mp4' if parts[2].endswith('.mp4') else 'audio/mpeg')
                content = app.preview(parts[2], query[field][0])
                players = ''.join('<section><h2>' + escape(take['label']) + '</h2><'
                    + ('video' if take['asset'].endswith('.mp4') else 'audio')
                    + ' controls preload="metadata" src="' + escape(take['url'], quote=True) + '"></'
                    + ('video' if take['asset'].endswith('.mp4') else 'audio') + '></section>'
                    for take in content['takes'])
                page = ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                        '<title>' + escape(content['title']) + '</title><style>body{font:18px/1.6 system-ui;max-width:760px;margin:3rem auto;padding:1rem}'
                        'video,audio{width:100%;border-radius:12px}section{margin-block:2rem}</style>'
                        '<main><p>Authored preview with AI-generated voice and imagery</p><h1>' + escape(content['title']) + '</h1><p>'
                        + escape(content['instruction']) + '</p><p>Transcript: ' + escape(content['passage']) + '</p>'
                        + players + '<p>Preview only. No playback or choice events are collected.</p></main></html>')
                return self._send(200, page.encode(), 'text/html; charset=utf-8')
            if path == '/api/intake/store' and not self.parsed_target.query:
                return self._send(200, {'store_id': self.server.workspace.intake.store_identity()})
            if path == '/api/intake/eligibility':
                query = parse_qs(self.parsed_target.query, keep_blank_values=True)
                if set(query) != {'context_request_id'} or len(query['context_request_id']) != 1:
                    return self._send(400, {'error': 'Select one exact reviewed context request'})
                return self._send(200, self.server.workspace.intake.preparation_eligibility(query['context_request_id'][0]))
            if len(parts) == 5 and parts[:4] == ['api','intake','preparations','requests'] and not self.parsed_target.query:
                return self._send(200, self.server.workspace.intake.grounded_request(parts[4]))
            if path == '/api/intake/contexts/preview':
                query = parse_qs(self.parsed_target.query, keep_blank_values=True)
                if set(query) != {'brief_id','revision'} or any(len(value) != 1 for value in query.values()):
                    return self._send(400, {'error':'Select one exact brief version for preparation review'})
                return self._send(200, self.server.workspace.intake.preparation_preview(query['brief_id'][0],int(query['revision'][0])))
            if path == '/api/intake/contexts':
                query = parse_qs(self.parsed_target.query, keep_blank_values=True)
                if set(query) != {'brief_id'} or len(query['brief_id']) != 1:
                    return self._send(400, {'error':'Select one brief for preparation history'})
                return self._send(200, self.server.workspace.intake.preparation_history(query['brief_id'][0]))
            if len(parts) == 5 and parts[:4] == ['api','intake','contexts','requests'] and not self.parsed_target.query:
                return self._send(200, self.server.workspace.intake.preparation_request(parts[4]))
            if path == '/api/intake/plans':
                query = parse_qs(self.parsed_target.query, keep_blank_values=True)
                if set(query) != {'brief_id'} or len(query['brief_id']) != 1:
                    return self._send(400, {'error': 'Select one saved brief for planning history'})
                return self._send(200, self.server.workspace.intake_plans(query['brief_id'][0]))
            if len(parts) == 4 and parts[:3] == ['api', 'intake', 'plans'] and not self.parsed_target.query:
                return self._send(200, self.server.workspace.intake_plan(parts[3]))
            if len(parts) == 5 and parts[:3] == ['api', 'intake', 'briefs'] and parts[4] == 'readiness':
                query = parse_qs(self.parsed_target.query, keep_blank_values=True)
                if set(query) != {'revision'} or len(query['revision']) != 1:
                    return self._send(400, {'error': 'Select the exact saved brief revision'})
                return self._send(200, self.server.workspace.intake.readiness(parts[3], int(query['revision'][0])))
            if len(parts) in {3, 4} and parts[:2] == ['api', 'intake'] and parts[2] in {'companies', 'briefs'}:
                try:
                    query = parse_qs(self.parsed_target.query, keep_blank_values=True)
                    allowed = {'after_id', 'limit'} if len(parts) == 3 else {'revision'}
                    if set(query) - allowed or any(len(v) != 1 for v in query.values()):
                        raise ValueError('Use exact intake query fields')
                    intake = self.server.workspace.intake
                    if len(parts) == 3:
                        return self._send(200, intake.listing(parts[2], query.get('after_id', [''])[0],
                                                            int(query.get('limit', ['50'])[0])))
                    revision = int(query['revision'][0]) if 'revision' in query else None
                    return self._send(200, intake.get(parts[2], parts[3], revision))
                except ValueError as error:
                    if isinstance(error, Conflict):raise
                    return self._send(400, {'error': str(error)})
            if path == "/api/sessions":
                return self._send(200, self.server.workspace.listing())
            if path == "/api/openrouter/models":
                return self._send(200, {"models": self.server.workspace.models.catalogue()})
            if path == "/api/conversations":
                return self._send(200, self.server.workspace.conversations())
            if path == "/api/knowledge":
                return self._send(200, self.server.workspace.knowledge())
            if path == "/api/audience-catalogue":
                query = parse_qs(self.parsed_target.query, keep_blank_values=True)
                if set(query) - {"campaign_key"} or any(len(v) != 1 for v in query.values()):
                    raise ValueError("Use one optional campaign key")
                return self._send(200, self.server.workspace.audience_catalogue(query.get("campaign_key", [None])[0]))
            if path == "/api/audience-dataset":
                query = parse_qs(self.parsed_target.query, keep_blank_values=True)
                if set(query) != {"dataset_id", "version", "checksum", "manifest_id"} or any(len(v) != 1 for v in query.values()):
                    raise ValueError("Select the exact dataset version, checksum and manifest")
                return self._send(200, self.server.workspace.audience_dataset(**{k:v[0] for k,v in query.items()}))
            parts = path.strip("/").split("/")
            if len(parts) == 3 and parts[:2] == ["api", "conversations"]:
                return self._send(200, self.server.workspace.conversation(parts[2]))
            if len(parts) == 3 and parts[:2] == ["api", "sessions"]:
                return self._send(200, self.server.workspace.view(parts[2]))
            if len(parts) == 5 and parts[:2] == ["api", "sessions"] and parts[3] == "artifacts":
                query = parse_qs(self.parsed_target.query)
                if set(query) != {"subject_id"} or len(query["subject_id"]) != 1:
                    raise ValueError("Download requires the exact displayed subject")
                body, content_type, filename = self.server.workspace.artifact(parts[2], parts[4], query["subject_id"][0])
                return self._send(200, body, content_type, filename)
            if path.startswith("/api/"):
                raise NotFound("Unknown workspace route")
            target = self.server.assets / ("index.html" if path == "/" else path.lstrip("/"))
            target = target.resolve()
            if not target.is_relative_to(self.server.assets) or not target.is_file():
                raise NotFound("Workspace asset not found")
            body = target.read_bytes()
            if target.name == "index.html":
                body = body.replace(b"__WORKSPACE_TOKEN__", self.server.token.encode())
            self._send(200, body, mimetypes.guess_type(target)[0] or "application/octet-stream")
        except YouTubeError as error:
            self._send(409, {'error': str(error), 'code': error.code, 'message_not_saved': error.message_not_saved})
        except PermissionError:
            self._send(403, {'error': 'This operation is unavailable'})
        except (NotFound, ValueError, Conflict, ModelError) as error:
            self._send(404 if isinstance(error, NotFound) else 409, {"error": str(error)})
        except Exception:
            self._send(500, {"error": "The workspace could not load this state. Retry or inspect the local database."})

    def do_POST(self):
        if not self._guard(mutation=True):
            return
        browser = ExitStack()
        try:
            path = self.parsed_target.path
            parts = path.strip("/").split("/")
            monitoring_upload = (len(parts) == 4 and parts[:2] == ["api", "sessions"]
                                 and parts[3] == "monitoring-start")
            length = int(self.headers.get("Content-Length", "0"))
            intake_save = path in {'/api/intake/companies', '/api/intake/briefs'}
            context_save = path == '/api/intake/contexts'
            grounded_save = path == '/api/intake/preparations'
            limit = 34 * 1024 * 1024 if monitoring_upload else 70 * 1024 if intake_save or context_save else 16384
            if not 0 < length <= limit or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                return self._send(400, {"error": "Use a bounded JSON request"} |
                                  ({'intake_not_saved': True} if intake_save else {}))
            try:
                raw = self.rfile.read(length)
                def unique_pairs(pairs):
                    result = {}
                    for key, value in pairs:
                        if key in result:
                            raise ValueError('Duplicate JSON field')
                        result[key] = value
                    return result
                youtube_request = path.startswith('/api/youtube/') or path.endswith('/youtube-messages')
                data = json.loads(raw, object_pairs_hook=unique_pairs) if youtube_request or grounded_save else json.loads(raw)
                if not isinstance(data, dict):
                    raise ValueError("Use a JSON object")
            except ValueError:
                if intake_save:
                    return self._send(400, {'error': 'Use a bounded JSON object', 'intake_not_saved': True})
                raise
            path = self.parsed_target.path
            authorization = self.headers.get("Authorization")
            handle = self.headers.get("X-OpenRouter-Handle")
            tab = self.headers.get("X-OpenRouter-Session")
            if youtube_request:
                if (authorization is not None or handle is not None or tab is not None or self.parsed_target.query
                        or any(len(self.headers.get_all(name, [])) != 1 for name in
                               ('Host', 'Origin', 'X-Workspace-Token', 'X-YouTube-Store'))):
                    raise ValueError('Use a scoped offline YouTube command without model funding')
                app = self.server.workspace.youtube.campaigns
                if self.headers.get('X-YouTube-Store') != app.store_identity():
                    return self._send(409, {'error': 'Restore the original YouTube workspace before retrying.',
                                            'code': 'store_mismatch'})
                if len(parts) == 4 and parts[:2] == ['api', 'conversations'] and parts[3] == 'youtube-messages':
                    if set(data) != {'request_id', 'expected_revision', 'content', 'draft_permission'}:
                        raise ValueError('Use exact YouTube message fields')
                    return self._send(200, self.server.workspace.youtube_message(parts[2], **data))
                if path == '/api/youtube/resume':
                    if set(data) != {'request_id', 'operation_id', 'conversation_id'}:
                        raise ValueError('Resume the exact original YouTube operation')
                    return self._send(200, self.server.workspace.youtube_resume(data['operation_id'], data['conversation_id']))
                if len(parts) == 3 and parts[:2] == ['api', 'youtube'] and parts[2] in {'save', 'approve', 'revoke', 'export'}:
                    return self._send(200, self.server.workspace.youtube_command(parts[2], data))
                raise ValueError('Use an installed YouTube command')
            if path == "/api/openrouter/check":
                if data or not authorization or not authorization.startswith("Bearer "):
                    raise ValueError("Use an OpenRouter bearer key.")
                connection = self.server.workspace.models.connect(authorization.removeprefix("Bearer "), tab, handle)
                return self._send(200, connection)
            if authorization is not None:
                if intake_save:
                    return self._send(400, {'error': 'Intake saves do not use model funding', 'intake_not_saved': True})
                raise ValueError("Use an OpenRouter connection handle.")
            if grounded_save:
                intake = self.server.workspace.intake
                if (self.parsed_target.query or handle is not None or tab is not None
                        or any(len(self.headers.get_all(name, [])) != 1 for name in
                               ('Host', 'Origin', 'X-Workspace-Token', 'X-Intake-Store'))):
                    raise ValueError('Use an exact offline preparation command without model funding')
                if self.headers.get('X-Intake-Store') != intake.store_identity():
                    return self._send(409, {'error': 'Restore the original store before reconciling this preparation.',
                                           'code': 'store_mismatch'})
                try:
                    return self._send(200, intake.prepare_grounded(data))
                except (ValueError, TypeError, NotFound) as error:
                    try: definite = intake.grounded_not_committed(data.get('request_id'))
                    except ValueError: definite = False
                    return self._send(409, {'error': str(error), 'preparation_not_saved': definite,
                                           'store_id': intake.store_identity()})
            if context_save:
                intake = self.server.workspace.intake
                store_id = intake.store_identity()
                if self.headers.get('X-Intake-Store') != store_id:
                    return self._send(409, {'error':'Restore the original workspace store before retrying its preparation review.'})
                try:
                    if handle is not None or tab is not None or self.parsed_target.query:
                        raise ValueError('Preparation input review uses no model funding or query fields')
                    return self._send(200, intake.confirm_preparation(data))
                except (ValueError, TypeError, NotFound) as error:
                    request_id = data.get('request_id')
                    try:definite = intake.preparation_not_committed(request_id)
                    except ValueError:definite = False
                    return self._send(409, {'error':str(error), 'context_not_saved':definite, 'store_id':store_id})
            if intake_save:
                intake = self.server.workspace.intake
                store_id = intake.store_identity()
                if self.headers.get('X-Intake-Store') != store_id:
                    # This request may already have committed in its original store.
                    # Never classify a different store's refusal as original reconciliation.
                    return self._send(409, {'error': 'Restore the original workspace store and retry. '
                                          'The original save has been kept.', 'intake_store_mismatch': True})
                try:
                    if handle is not None or tab is not None or self.parsed_target.query:
                        raise ValueError('Use an intake save without model funding or query fields')
                    return self._send(200, intake.save(parts[2], data) | {'store_id': store_id})
                except (NotFound, ValueError) as error:
                    return self._send(404 if isinstance(error, NotFound) else 409 if isinstance(error, Conflict) else 400,
                                      {'error': str(error), 'intake_not_saved': True, 'store_id': store_id})
            if path == "/api/openrouter/disconnect":
                if not handle or not tab or data:
                    raise ValueError("Use the connected OpenRouter browser session.")
                self.server.workspace.models.disconnect(handle, tab)
                return self._send(200, {"ok": True})
            if handle is not None or tab is not None:
                browser.enter_context(self.server.workspace.models.browser(
                    handle, tab, self.headers.get("X-OpenRouter-Model"), self.headers.get("X-OpenRouter-Tier")))
            if path == '/api/intake/plans':
                store_id = self.server.workspace.intake.store_identity()
                if self.headers.get('X-Intake-Store') != store_id:
                    return self._send(409, {'error': 'Restore the original workspace store before resuming its planning request.'})
                if (self.parsed_target.query or set(data) != {'request_id', 'brief_id', 'brief_revision', 'allow_model'}
                        or data['allow_model'] is not True):
                    return self._send(400, {'error': 'Use an exact saved brief selection and explicit planning permission'})
                try:
                    return self._send(200, self.server.workspace.request_intake_plan(**data))
                except IntakePlanningRejected as error:
                    return self._send(409, {'error': str(error), 'intake_plan_not_admitted': True, 'store_id': store_id})
            if path == "/api/openrouter/advance":
                if handle is None or data:
                    raise ValueError("Use the connected OpenRouter browser session.")
                self.server.workspace.advance_browser_model()
                return self._send(200, {"ok": True})
            if path == "/api/conversations":
                if set(data) != {"request_id", "title"}:
                    raise ValueError("Use exact conversation creation fields")
                return self._send(200, self.server.workspace.create_conversation(data["request_id"], data["title"]))
            parts = path.strip("/").split("/")
            if len(parts) == 4 and parts[:2] == ["api", "conversations"]:
                if parts[3] == 'writing-preferences' and set(data) == {'request_id','session_id','comment_id','preference_id','action','expected_revision','segments','preferred','avoid','reason','confirmed'}:
                    return self._send(200,self.server.workspace.change_writing_preference(parts[2],**data))
                if parts[3] == 'artifact-comments' and set(data) == {'request_id','session_id','expected_subject','target_id','expected_revision','feedback'}:
                    return self._send(200,self.server.workspace.comment_artifact(parts[2],**data))
                if parts[3] == 'stop' and set(data)=={'request_id','expected_revision'}:
                    return self._send(200,self.server.workspace.stop_execution(parts[2],**data))
                sequence_fields={'sequence-approve':{'subject_id','reason'},'sequence-stop':set(),'sequence-task-completed':{'step_id'},'sequence-replied':{'step_id'}}
                if parts[3] in sequence_fields and set(data)=={'journey_id','request_id','expected_revision'}|sequence_fields[parts[3]]:
                    return self._send(202,self.server.workspace.sequence_command(parts[2],parts[3],**data))
                if parts[3] == 'actions' and set(data)=={'request_id','expected_revision','content','allow_model_copy'}:
                    return self._send(202,self.server.workspace.route_followup(parts[2],**data))
                if parts[3] == 'confirm-action' and set(data)=={'request_id','action_id','target_id','expected_revision'}:
                    return self._send(200,self.server.workspace.confirm_followup(parts[2],**data))
                if parts[3] == 'confirm-typed-action' and set(data) == {'request_id', 'action_id', 'result_id', 'expected_revision'}:
                    return self._send(200,self.server.workspace.confirm_typed_action(parts[2],**data))
                if parts[3] == 'confirm-copy-action' and set(data)=={'request_id','action_id','result_id','expected_revision','allow_model_copy'}:
                    return self._send(200,self.server.workspace.confirm_copy_followup(parts[2],**data))
                if parts[3] == 'budget-replies' and set(data) == {'request_id', 'expected_revision', 'plan_id', 'content'}:
                    return self._send(200, self.server.workspace.reply_budget_conversation(parts[2], **data))
                if parts[3] == "sequence-messages" and set(data) == {"request_id", "expected_revision", "content"}:
                    return self._send(202,self.server.workspace.message_conversation(parts[2],**data))
                if parts[3] == "messages" and set(data) == {"request_id", "expected_revision", "content"}:
                    return self._send(200, self.server.workspace.message_conversation(parts[2], **data))
                if parts[3] == "plan" and set(data) == {"request_id", "expected_revision"}:
                    return self._send(200, self.server.workspace.plan_conversation(parts[2], **data,
                        replay_only=self.headers.get("X-Workspace-Plan-Replay") == "1"))
                if parts[3] == "plan-fixture" and set(data) == {"request_id", "expected_revision"}:
                    return self._send(200, self.server.workspace.plan_conversation_fixture(parts[2], **data))
                if parts[3] == "draft" and set(data) == {"request_id", "expected_revision", "plan_id"}:
                    return self._send(200, self.server.workspace.draft_conversation(parts[2], **data))
                if parts[3] == "preparations" and set(data) in ({"request_id", "expected_revision", "fixture", "allow_model_copy"}, {"request_id", "expected_revision", "fixture", "allow_model_copy", "use_audience_catalogue"}):
                    return self._send(202, self.server.workspace.start_preparation(parts[2], **data))
                if parts[3] == 'audience' and set(data) == {'request_id','expected_revision','plan_id','dataset_id','version','checksum','manifest_id'}:
                    return self._send(200, self.server.workspace.select_conversation_audience(parts[2], **data))
                raise ValueError("Use exact fields for a supported conversation action")
            if path == "/api/sessions":
                if set(data) - {"request_id", "mode", "parent_id"}:
                    raise ValueError("Unknown campaign creation fields")
                return self._send(200, self.server.workspace.create(data["request_id"], data["mode"], data.get("parent_id")))
            parts = path.strip("/").split("/")
            if len(parts) == 4 and parts[:2] == ["api", "sessions"]:
                if parts[3] in {"monitoring-start", "monitoring-update"}:
                    return self._send(200, self.server.workspace.monitoring_command(parts[2], parts[3], data))
                if parts[3] == "followup-proposal" and set(data) == {"request_id", "cohort_id"}:
                    return self._send(200, self.server.workspace.propose_followup(parts[2], **data))
                if parts[3] == "followup-prepare" and set(data) == {"request_id", "proposal_id", "mode", "allow_model_copy"}:
                    return self._send(200, self.server.workspace.prepare_followup(parts[2], **data))
                if parts[3] == "copy-revisions" and set(data) == {"request_id", "expected_subject", "target_id", "feedback", "allow_model_copy"}:
                    return self._send(202, self.server.workspace.request_copy_revision(parts[2], **data))
                if parts[3] == "prepare":
                    return self._send(200, self.server.workspace.prepare(parts[2]))
                return self._send(200, self.server.workspace.action(parts[2], parts[3], data))
            raise NotFound("Unknown workspace route")
        except YouTubeError as error:
            self._send(409, {'error': str(error), 'code': error.code, 'message_not_saved': error.message_not_saved})
        except PermissionError:
            self._send(403, {'error': 'This operation is unavailable'})
        except MonitoringRejected as error:
            self._send(409, {"error": str(error), "monitoring_not_saved": error.not_saved})
        except ModelSessionExpired as error:
            self._send(409, {"error": str(error), "openrouter_disconnected": True})
        except ModelSelectionRejected as error:
            self._send(409, {"error": str(error), "model_selection_not_saved": True})
        except ActionNotSaved as error:
            self._send(409,{"error":str(error),"action_not_saved":True})
        except AudienceSelectionRejected as error:
            self._send(409, {"error":str(error), "audience_not_saved":True})
        except (MessageRejectedConflict, MessageRejectedInvalid, MessageRejectedNotFound) as error:
            self._send(409 if isinstance(error, MessageRejectedConflict) else 404 if isinstance(error, MessageRejectedNotFound) else 400,
                       {"error": str(error), "message_not_saved": True})
        except (NotFound, ValueError, Conflict, ModelError, KeyError) as error:
            self._send(404 if isinstance(error, NotFound) else 409 if isinstance(error, Conflict) else 400,
                {"error": str(error) if not isinstance(error, KeyError) else "Missing required workspace field"})
        except Exception:
            self._send(500, {"error": "The action did not return a confirmed result. Refresh before retrying; existing domain receipts prevent duplicate effects."})
        finally:
            browser.close()
