"""Call the private hosted experiment without placing its token in command arguments."""

import argparse
import json
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import urlsplit
from uuid import uuid4

from scripts.hosting_probe import CASES


def invoke(deployment, case, identity, token, *, authorized=True):
    # Curl reads the private header from a mode-0600 file. No secret enters argv.
    with tempfile.NamedTemporaryFile(mode='w', suffix='.curl') as config:
        if authorized:
            config.write('header = ' + json.dumps('Authorization: Bearer ' + token) + '\n')
        config.write('header = "Content-Type: application/json"\nrequest = "POST"\n')
        config.write('data = ' + json.dumps(json.dumps({'case': case, 'probe_id': identity})) + '\n')
        config.flush()
        result = subprocess.run(['vercel', 'curl', '/api/probe', '--deployment', deployment,
            '--', '--silent', '--show-error', '--max-time', '185', '--config', config.name,
            '--write-out', '\n%{http_code}'], capture_output=True, text=True, timeout=210)
    try:
        body, status = result.stdout.rsplit('\n', 1)
        value = json.loads(body)
        return int(status), value
    except (ValueError, TypeError):
        return 0, {'passed': False, 'error_type': 'InvalidOrMissingHostedResponse',
                   'client_exit': result.returncode}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deployment', required=True)
    parser.add_argument('--token-file', type=Path, required=True)
    parser.add_argument('--probe-id', default=None)
    parser.add_argument('--case', choices=CASES, action='append')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    target = urlsplit(args.deployment)
    if (target.scheme != 'https' or not target.hostname
            or not target.hostname.startswith('direct-acquisition-feasibility-')
            or not target.hostname.endswith('.vercel.app') or target.username or target.password
            or target.path not in {'', '/'} or target.query or target.fragment or target.port):
        parser.error('Use the isolated protected feasibility deployment')
    identity = args.probe_id or uuid4().hex
    if re.fullmatch('[a-f0-9]{32}', identity) is None:
        parser.error('Use the original hexadecimal probe identity')
    token = args.token_file.read_text().strip()
    if re.fullmatch('[A-Za-z0-9_-]{32,128}', token) is None:
        parser.error('Use the generated private probe token')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    status, rejection = invoke(args.deployment, 'transport', identity, token, authorized=False)
    report = {'schema': 'hosted-storage-feasibility/v1', 'deployment': args.deployment,
              'probe_id': identity, 'unauthorized_status': status, 'results': [],
              'product_ready': False, 'live_model_calls': 0}
    if status != 403 or rejection.get('error') != 'probe_authorization_required':
        report['passed'] = False
        args.output.write_text(json.dumps(report, indent=2) + '\n')
        return 1
    for case in args.case or CASES:
        status, value = invoke(args.deployment, case, identity, token)
        report['results'].append({'case': case, 'http_status': status, 'result': value})
        report['passed'] = all(r['http_status'] == 200 and r['result'].get('passed') is True
                               for r in report['results'])
        report['complete_corpus'] = {r['case'] for r in report['results']} == set(CASES)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        # Even unexpected provider output cannot copy the operator's token into evidence.
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True).replace(token, '[redacted]') + '\n')
        print(case + ': ' + ('PASS' if status == 200 and value.get('passed') else 'FAIL'), flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
