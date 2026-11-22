"""Protected operator HTTP surface. Authentication precedes storage composition."""
import secrets
from http.server import BaseHTTPRequestHandler
import json
from urllib.parse import urlsplit, parse_qs
from acquisition.contracts import Conflict, NotFound


def preparation_handler(factory, token, hosts, origins):
    hosts, origins = frozenset(hosts), frozenset(origins)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def respond(self,status,body):
            payload=json.dumps(body).encode()
            self.send_response(status)
            self.send_header('Content-Type','application/json')
            self.send_header('Cache-Control','no-store')
            self.send_header('Content-Length',str(len(payload)))
            self.end_headers()
            try:self.wfile.write(payload)
            except (BrokenPipeError,ConnectionResetError):pass
        def authorized(self):
            if len(token)<32 or not hosts:
                self.respond(503,{'error':'operator_surface_not_configured'});return False
            if (len(self.headers.get_all('Host',[]))!=1 or len(self.headers.get_all('Authorization',[]))!=1 or
                len(self.headers.get_all('Origin',[]))>1 or self.headers.get('Host') not in hosts or
                self.headers.get('Origin') is not None and self.headers['Origin'] not in origins or
                not secrets.compare_digest(self.headers.get('Authorization','').encode(),('Bearer '+token).encode())):
                self.respond(403,{'error':'operator_authorization_required'});return False
            return True
        def do_GET(self):
            if not self.authorized():return
            route=urlsplit(self.path)
            query=parse_qs(route.query,keep_blank_values=True)
            if route.path!='/api/preparation' or set(query)!={'journey_id'} or len(query['journey_id'])!=1:
                return self.respond(400,{'error':'invalid_status_request'})
            self.invoke('status',{'journey_id':query['journey_id'][0]})
        def do_POST(self):
            if not self.authorized():return
            try:
                if self.path!='/api/preparation' or self.headers.get('Content-Type')!='application/json':raise ValueError()
                if self.headers.get('Transfer-Encoding') is not None:raise ValueError()
                if len(self.headers.get_all('Content-Length',[]))!=1:raise ValueError()
                self.connection.settimeout(10)
                size=int(self.headers.get('Content-Length',''))
                if not 1<=size<=2048:raise ValueError()
                def unique(pairs):
                    result={}
                    for key,value in pairs:
                        if key in result:raise ValueError()
                        result[key]=value
                    return result
                body=json.loads(self.rfile.read(size),object_pairs_hook=unique)
                if type(body) is not dict:raise ValueError()
                action=body.pop('action',None)
                fields={'start':{'request_id','profile_key','budget_pence','allow_generation'},
                        'continue':{'journey_id','expected_stage'},'stop':{'journey_id','request_id'}}
                if type(action) is not str or action not in fields or set(body)!=fields[action]:raise ValueError()
            except (ValueError,TypeError,UnicodeError,OSError):return self.respond(400,{'error':'invalid_preparation_request'})
            self.invoke(action,body)
        def invoke(self,action,body):
            try:service=factory()
            except Exception:
                return self.respond(503,{'error':'preparation_unavailable_resume_original'})
            try:
                operation={'status':'status','start':'start','continue':'advance','stop':'stop'}[action]
                self.respond(200,getattr(service,operation)(**body))
            except NotFound:self.respond(404,{'error':'preparation_not_found'})
            except Conflict:self.respond(409,{'error':'preparation_conflict_reload_original'})
            except (ValueError,TypeError):self.respond(400,{'error':'invalid_preparation_request'})
            except Exception:self.respond(503,{'error':'preparation_unavailable_resume_original'})
    return Handler
