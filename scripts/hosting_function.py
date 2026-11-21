"""Private feasibility endpoint, packaged separately from the runnable product."""

import hmac
from http.server import BaseHTTPRequestHandler
import json
import os
from pathlib import Path
import re
import tempfile
from uuid import uuid4

from scripts.hosting_probe import CASES, Probe


class handler(BaseHTTPRequestHandler):
    def respond(self, status, body):
        data = json.dumps(body, sort_keys=True).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.respond(200, {'schema': 'hosting-feasibility-endpoint/v1',
                          'purpose': 'Private infrastructure experiment', 'product_ready': False})

    def do_POST(self):
        token = os.environ.get('HOSTING_PROBE_TOKEN', '')
        if not token:
            return self.respond(503, {'error': 'probe_not_configured'})
        if not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token):
            return self.respond(403, {'error': 'probe_authorization_required'})
        try:
            length = int(self.headers.get('Content-Length', ''))
            if not 1 <= length <= 1024:
                raise ValueError()
            body = json.loads(self.rfile.read(length))
            if (not isinstance(body, dict) or set(body) != {'case', 'probe_id'}
                    or body['case'] not in CASES or not isinstance(body['probe_id'], str)
                    or re.fullmatch('[a-f0-9]{32}', body['probe_id']) is None):
                raise ValueError()
        except (ValueError, TypeError):
            return self.respond(400, {'error': 'invalid_probe_request'})
        try:
            with tempfile.TemporaryDirectory() as root:
                result = Probe('remote', body['probe_id'], Path(root) / 'probe.sqlite').run(body['case'])
            self.respond(200, result | {'invocation_id': uuid4().hex, 'process_id': os.getpid()})
        except Exception:
            self.respond(503, {'error': 'probe_configuration_or_transport_failure'})

    def log_message(self, *args):
        # Do not echo headers, request bodies or provider failures into routine logs.
        pass
