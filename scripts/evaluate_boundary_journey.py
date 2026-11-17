"""Retain bounded, attributable #93 offline lifecycle and recovery evidence.

The #23 browser journey remains independently scoped. This runner reuses its
native fixture approach and source attribution, merged #25 control scenarios,
#33 recovery oracles, and current profile/engagement fixtures. The regular
interface gate separately exercises the real browser and inbound adapter.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluation_evidence import source_state

PREFIXES = ('src', 'tests', 'config', 'scripts', 'frontend/src', 'frontend/tests', 'frontend/scripts',
            'frontend/public', 'frontend/package.json', 'frontend/pnpm-lock.yaml', 'frontend/playwright.config.ts',
            'frontend/tsconfig.json', 'frontend/vite.config.ts', 'frontend/index.html', '.github',
            'Makefile', '.gitignore', 'AGENTS.md', 'README.md', 'docs/architecture.md', 'docs/workspace.md', 'docs/user-guide.md')
CASES = ('compatibility-model-journey', 'verified-commit-rebuild-replay', 'uncertain-restart', 'profile-replay', 'engagement-replay')
COUNTS = {'input': 100, 'excluded': 24, 'eligible_unselected': 0, 'holdout': 6, 'mailed': 70}
# An audit hook remains active in nested fresh CLI processes, even when a
# dependency catches the raised exception. Count attempts, not just exceptions.
NETWORK_GUARD = '''import json,os,sys,subprocess
from pathlib import Path
path = os.environ.get('BOUNDARY_NETWORK_LOG')
def guard(event, args):
    if event in {'socket.connect','socket.getaddrinfo','socket.gethostbyname','socket.gethostbyaddr','socket.getnameinfo','socket.sendto','socket.sendmsg'}:
        if path:
            with Path(path).open('a') as stream: stream.write(json.dumps({'event':event})+'\\n')
        raise RuntimeError('Network disabled in offline boundary evaluation')
sys.addaudithook(guard)
_original_popen = subprocess.Popen
class OfflineProcess(_original_popen):
    def __init__(self,*args,**kwargs):
        provided = kwargs.get('env')
        environment = dict(os.environ if provided is None else provided)
        environment['BOUNDARY_NETWORK_LOG'] = path or ''
        environment['PYTHONPATH'] = str(Path(__file__).parent)+os.pathsep+environment.get('PYTHONPATH','')
        kwargs['env'] = environment
        super().__init__(*args,**kwargs)
subprocess.Popen = OfflineProcess
'''


def digest(value):
    return hashlib.sha256(value).hexdigest()


def artifacts(directory):
    return {p.relative_to(directory).as_posix(): {'sha256': digest(p.read_bytes()), 'bytes': p.stat().st_size}
            for p in sorted(directory.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}


def grade(rows):
    """Independent acceptance values; missing, duplicate or false evidence fails."""
    failures = []
    if type(rows) is not list or len(rows) != len(CASES) or any(type(r) is not dict for r in rows):
        return ['Expected every bounded case exactly once']
    if any(type(r.get('id')) is not str for r in rows) or sorted(r['id'] for r in rows) != sorted(CASES):
        return ['Missing, repeated or unexpected case identity']
    for row in rows:
        if not valid_case(row): failures.append(row['id'] + ': incomplete or failed authoritative evidence')
    return failures


def count(value, expected):
    return type(value) is int and value == expected


def fingerprint(value):
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def valid_case(row):
    try:
        identity = row['id']; value = row.get('observed', {})
        valid = (type(row.get('exit_code')) is int and row['exit_code'] == 0 and type(value) is dict and type(value.get('process_pid')) is int
                 and type(row.get('artifacts')) is dict and bool(row['artifacts'])
                 and all(type(v) is dict and type(v.get('bytes')) is int and v['bytes'] >= 0
                         and type(v.get('sha256')) is str and len(v['sha256']) == 64 for v in row['artifacts'].values())
                 and type(row.get('network_attempts')) is int and row['network_attempts'] == 0)
        if identity == 'compatibility-model-journey':
            journey = value.get('journey', {})
            valid = valid and value.get('passed') is True and value.get('outcome_category') == 'accepted' and (
                type(value.get('fake_provider_calls')) is int and value['fake_provider_calls'] > 0 and count(value.get('recorded_model_calls'), value['fake_provider_calls'])
                and count(journey.get('replay_added_calls'), 0) and count(journey.get('inspection_added_calls'), 0)
                and journey.get('confirmed_amendment_budget_pence') == 51200)
        elif identity == 'verified-commit-rebuild-replay':
            replay = value.get('fresh_process_replay', {})
            valid = valid and (value.get('projection_preserved_authority') is True and fingerprint(value.get('authoritative_sha256'))
                and type(value.get('population')) is int and value['population'] > 0
                and value['population'] == value.get('received') and type(value.get('model_calls')) is int and value['model_calls'] == 0
                and all(replay.get(k) is True for k in ('handoff_replayed','finalize_replayed','changed_input_rejected'))
                and type(replay.get('pid')) is int and replay['pid'] != value['process_pid'])
        elif identity == 'uncertain-restart':
            replay = value.get('fresh_process_replay', {})
            valid = valid and (value.get('passed') is True and type(value.get('fake_provider_calls')) is int and value['fake_provider_calls'] == 1
                and type(value.get('replay_added_calls')) is int and value['replay_added_calls'] == 0 and type(value.get('used')) is int and value['used'] == 1 and value.get('authoritative_unchanged') is True
                and count(replay.get('used'), 1) and count(replay.get('campaigns'), 0)
                and type(replay.get('pid')) is int and replay['pid'] != value['process_pid'])
        elif identity == 'profile-replay':
            profiles = value.get('profiles', [])
            valid = valid and (type(profiles) is list and len(profiles) == 2 and {p.get('profile') for p in profiles} == {'iwoca','fielddesk'}
                and all(type(p.get('draft_id')) is str and p['draft_id'] and fingerprint(p.get('manifest_sha256')) for p in profiles)
                and len({p['draft_id'] for p in profiles}) == 2 and value.get('changed_input_rejected') is True
                and type(value.get('model_calls')) is int and value['model_calls'] == 0 and all(p.get('counts') == COUNTS and all(type(v) is int for v in p['counts'].values()) and count(p.get('cost_pence'), 5950)
                    and p.get('approval') == 'not_granted' and p.get('execution') == 'not_performed' for p in profiles))
        elif identity == 'engagement-replay':
            counts = value.get('counts', {})
            valid = valid and (value.get('same_receipt') is True and count(counts.get('engagement_simulations'), 1)
                and count(counts.get('engagement_enrollments'), 2) and count(counts.get('engagement_steps'), 6)
                and count(counts.get('engagement_dispatches'), 2) and type(value.get('fresh_process_pid')) is int
                and value['fresh_process_pid'] != value['process_pid'])
        else:
            return False
        return bool(valid)
    except (KeyError, TypeError, AttributeError, ValueError):
        return False


def historical(root):
    paths = subprocess.check_output(['git','ls-tree','-r','--name-only','HEAD','--','docs/evaluations'],cwd=root,text=True).splitlines()
    return {name: {'expected': digest(subprocess.check_output(['git','show','HEAD:'+name],cwd=root)),
                   'actual': digest((root/name).read_bytes()) if (root/name).is_file() else None} for name in paths}


def evaluate(output, root=ROOT):
    before = source_state(root, PREFIXES)  # Before any production or fixture imports.
    from scripts.check_architecture import check
    architecture_errors = check(root)
    policy = json.loads((root / 'scripts/architecture_policy.json').read_text())
    history_before = historical(root)
    guard = output / 'guard'; guard.mkdir(); (guard / 'sitecustomize.py').write_text(NETWORK_GUARD)
    rows = []
    for identity in CASES:
        directory = output / identity; directory.mkdir()
        network_log = directory / 'network-attempts.jsonl'
        env = dict(os.environ, OPENROUTER_API_KEY='offline-tests-must-not-use-live-credentials',
                   PYTHONPATH=os.pathsep.join(map(str,(guard,root,root/'src',root/'tests'))), BOUNDARY_NETWORK_LOG=str(network_log))
        try:
            run = subprocess.run([sys.executable,'-m','scripts.boundary_journey_fixture',identity,str(directory)],
                                 cwd=root,env=env,capture_output=True,text=True,timeout=240)
            (directory/'stdout.log').write_text(run.stdout); (directory/'stderr.log').write_text(run.stderr)
            try: observed = json.loads(run.stdout.splitlines()[-1])
            except (ValueError,IndexError): observed = {}
            code = run.returncode
        except (OSError,subprocess.TimeoutExpired) as error:
            (directory/'stderr.log').write_text(type(error).__name__+': '+str(error)); observed={}; code=127
        attempts = len(network_log.read_text().splitlines()) if network_log.exists() else 0
        rows.append({'id':identity,'exit_code':code,'observed':observed,'network_attempts':attempts,'artifacts':artifacts(directory)})
        print(identity + ': ' + ('PASS' if not grade_case(rows[-1]) else 'FAIL'),flush=True)
    after = source_state(root, PREFIXES); history_after=historical(root)
    stable = before['files_sha256']==after['files_sha256'] and before['head_commit']==after['head_commit']
    historical_unchanged = history_before==history_after and all(r['expected']==r['actual'] for r in history_after.values())
    failures = grade(rows) + ['Architecture: '+error for error in architecture_errors]
    if not stable: failures.append('Evaluated source inputs changed during execution')
    if not historical_unchanged: failures.append('Historical evidence bytes differ from committed artifacts')
    return {'schema':'hexagonal-boundary-evaluation/v1','evaluated_at':datetime.now(timezone.utc).isoformat(),
            'base_commit':before['head_commit'],'evaluated_commit':before['head_commit'] if stable and not before['worktree_dirty'] else None,
            'source_state':before,'source_state_after':{k:v for k,v in after.items() if k!='files'},
            'source_state_stable':stable,'historical_artifacts':history_after,'historical_bytes_unchanged':historical_unchanged,
            'results':rows,'failures':failures,'passed':not failures,
            'architecture':{'classified_modules':len(policy['modules']),'temporary_exceptions':len(policy['exceptions']),'errors':architecture_errors},
            'limits':['Deterministic synthetic control evidence, not model quality, live transport or customer performance.',
                      'One local worker per root. Browser behavior is covered by the separate interface gate.',
                      'Bounded native reuse of unmerged #23 tooling. Does not close #23, #60, #68, #69, #70, #74 or #77.']}


def grade_case(row):
    return [] if valid_case(row) else ['Incomplete or failed authoritative evidence']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=ROOT/'.local'/'boundary-evidence'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8]))
    args=parser.parse_args(); output=args.output_dir.resolve()
    if any(output.is_relative_to((ROOT/prefix).resolve()) for prefix in PREFIXES):parser.error('Evidence output must be outside evaluated input paths')
    if output.exists() and any(output.iterdir()):parser.error('Evidence destination must be empty; previous evidence is never overwritten')
    output.mkdir(parents=True,exist_ok=True)
    report=evaluate(output); (output/'results.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    lines=['# Hexagonal boundary evaluation','',('PASS' if report['passed'] else 'FAIL'),'',
           'Base commit: '+report['base_commit'],'Source fingerprint: '+report['source_state']['files_sha256'],'',
           *[r['id']+': '+('PASS' if not grade_case(r) else 'FAIL') for r in report['results']],
           '',*report['failures'],'',*report['limits']]
    (output/'evidence.md').write_text('\n'.join(lines)+'\n'); print(str(output/'results.json'))
    return int(not report['passed'])


if __name__=='__main__':
    raise SystemExit(main())
