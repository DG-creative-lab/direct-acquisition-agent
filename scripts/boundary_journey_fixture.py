"""Native #93 fixtures over the existing #23/#25/#33 acceptance paths.

Invoked in fresh interpreters by evaluate_boundary_journey. Every retained store
is synthetic. The evaluator installs a network-denial audit hook in all children.
"""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src'), str(ROOT / 'tests')]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def records(path):
    """Observe all authoritative rows independently of workspace projections."""
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        tables = sorted(r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"))
        return {table: sorted((repr(tuple(row)) for row in db.execute('SELECT * FROM "' + table.replace('"', '""') + '"')))
                for table in tables}


def authoritative(root):
    return {p.relative_to(root).as_posix(): records(p) for p in sorted(root.rglob('*.sqlite')) if p.name != 'workspace.sqlite'}


def command(args, directory):
    run = subprocess.run([sys.executable, *map(str, args)], cwd=ROOT, env=os.environ,
                         capture_output=True, text=True, timeout=120)
    with (directory / 'processes.jsonl').open('a') as stream:
        stream.write(json.dumps({'args': list(map(str, args)), 'exit_code': run.returncode,
                                 'stdout': run.stdout, 'stderr': run.stderr}) + '\n')
    if run.returncode:
        raise AssertionError(run.stderr or run.stdout)
    return json.loads(run.stdout)


def verified(directory):
    # Reuse the merged crash-after-draft fixture and every original oracle.
    from test_fixture_activation import FixtureActivationTests
    case = FixtureActivationTests('test_offline_journey_restarts_after_draft_commit_and_finishes_once')
    case.parent, case.root, case.now = directory, directory / 'workspace', 1793016000.
    command(['-m', 'acquisition.workspace_fixture', '--root', case.root], directory)
    case.w = case.workspace()
    with patch('acquisition.bootstrap.workspace_gateway', side_effect=AssertionError('Provider must remain unused')):
        evidence = case.offline_journey()
    return verify_rebuild_replay(case, directory, evidence)


def verify_rebuild_replay(case, directory, evidence):
    """Check the same journey after losing and rebuilding its projection."""
    before = authoritative(case.root)
    save(directory / 'authoritative-before.json', before)
    for suffix in ('', '-wal', '-shm', '-journal'):
        (case.root / ('workspace.sqlite' + suffix)).unlink(missing_ok=True)
    inspected = command(['-m', 'acquisition.workspace_rebuild', '--root', case.root, 'inspect'], directory)
    rebuilt = command(['-m', 'acquisition.workspace_rebuild', '--root', case.root,
                       '--expected-plan', inspected['plan_id'], 'rebuild'], directory)
    if rebuilt['status'] != 'rebuilt' or authoritative(case.root) != before:
        raise AssertionError('Projection rebuild changed authoritative facts')
    save(directory / 'replay-input.json', evidence | {'clock': case.now, 'root': str(case.root)})
    replay = command(['-m', 'scripts.boundary_journey_fixture', 'replay-verified', directory], directory)
    after = authoritative(case.root)
    save(directory / 'authoritative-after.json', after)
    if after != before or not replay['handoff_replayed'] or not replay['finalize_replayed']:
        raise AssertionError('Fresh-process replay changed authoritative history')
    return evidence | {'projection_preserved_authority': True, 'fresh_process_replay': replay,
                       'authoritative_sha256': sha(json.dumps(before, sort_keys=True).encode()),
                       'rebuilt_plan_id': inspected['plan_id']}


def replay_verified(directory):
    from acquisition.bootstrap import build_workspace
    from acquisition.contracts import Conflict
    data = json.loads((directory / 'replay-input.json').read_text())
    w = build_workspace(Path(data['root']), real_clock=lambda: data['clock'])
    sid = data['session_id']
    handoff = w.action(sid, 'handoff', data['handoff_command'])
    final = w.action(sid, 'finalize', data['finalize_command'])
    try:
        w.action(sid, 'handoff', {'request_id': 'handoff', 'approval_id': 'changed-approval'})
    except Conflict:
        changed_rejected = True
    else:
        raise AssertionError('A changed replay input was accepted')
    return {'pid': os.getpid(), 'handoff_replayed': handoff.get('command_replayed') is True,
            'finalize_replayed': final.get('command_replayed') is True, 'changed_input_rejected': changed_rejected}


def compatibility(directory):
    from scripts.evaluate_conversational_agent import run_case
    corpus = json.loads((ROOT / 'config/conversation-offline-evaluation-v1.json').read_text())
    case = next(c for c in corpus['cases'] if c['expected'].get('review_ready') and c['expected'].get('segments') == ['contractors'])
    result = run_case(case, directory=directory / 'workspace')
    facts = authoritative(directory / 'workspace')
    save(directory / 'authoritative.json', facts)
    result['recorded_model_calls'] = sum(len(db.get('model_calls', [])) for db in facts.values())
    return result


def uncertain(directory):
    from scripts.evaluate_conversational_agent import uncertain_restart
    result = uncertain_restart(directory=directory / 'workspace')
    before = authoritative(directory / 'workspace')
    replay = command(['-m', 'scripts.boundary_journey_fixture', 'replay-uncertain', directory], directory)
    after = authoritative(directory / 'workspace')
    save(directory / 'authoritative-before.json', before); save(directory / 'authoritative-after.json', after)
    if before != after:
        raise AssertionError('Uncertain restart mutated authoritative records')
    return result | {'fresh_process_replay': replay, 'authoritative_unchanged': True}


def replay_uncertain(directory):
    from acquisition.bootstrap import build_workspace
    from scripts.evaluate_conversational_agent import NOW
    with patch('acquisition.bootstrap.workspace_gateway', side_effect=AssertionError('Repeated uncertain provider call')):
        w = build_workspace(directory / 'workspace', real_clock=lambda: NOW)
        conversation = w.conversations()['conversations'][0]['id']
        w.recover_execution(); w.advance_preparations()
        view = w.conversation(conversation)
        if view['campaigns'] or view['execution']['used'] != 1:
            raise AssertionError('Uncertain work resumed or lost its allowance')
    return {'pid': os.getpid(), 'used': view['execution']['used'], 'campaigns': len(view['campaigns'])}


def profiles(directory):
    from acquisition.bootstrap import build_profile_preparation
    from acquisition.contracts import Conflict
    path = directory / 'profiles.sqlite'; now = datetime(2026, 11, 13, tzinfo=timezone.utc).timestamp()
    rows = []
    for key, segments in [('fielddesk', ('maintenance', 'installations')), ('iwoca', ('inventory', 'contractors'))]:
        app = build_profile_preparation(path, 'one', key, lambda: now)
        inputs = dict(objective='Compare response to hypothetical business planning questions.', budget_pence=60000,
                      segments=segments, country='UK', currency='GBP', channel='direct_mail', size=100)
        receipt = app.prepare('one', key, key, 'v1', **inputs)
        draft = app.proposals.get('one', receipt['draft_id'])
        if draft.manifest['counts'] != {'input': 100, 'excluded': 24, 'eligible_unselected': 0, 'holdout': 6, 'mailed': 70}:
            raise AssertionError('Profile population differs from the independent fixture counts')
        before = records(path)
        replay = command(['-m', 'acquisition.profile_cli', '--db', path, '--organization', 'one', '--profile', key,
                          '--version', 'v1', '--request-id', key, '--objective', inputs['objective'], '--budget-pence', '60000',
                          '--segments', *segments, '--country', 'UK', '--currency', 'GBP', '--channel', 'direct_mail',
                          '--size', '100'], directory)
        if replay['draft_id'] != draft.id or records(path) != before:
            raise AssertionError('Profile replay changed identities or facts')
        try: app.prepare('one', key, key, 'v1', **(inputs | {'budget_pence': 50000}))
        except Conflict: pass
        else: raise AssertionError('Changed profile inputs reused a key')
        if records(path) != before: raise AssertionError('Rejected profile replay changed facts')
        save(directory / (key + '-manifest.json'), draft.manifest)
        rows.append({'profile': key, 'draft_id': draft.id, 'manifest_sha256': sha(json.dumps(draft.manifest,sort_keys=True).encode()),
                     'counts': draft.manifest['counts'], 'cost_pence': draft.manifest['variable_cost_pence'],
                     'approval': replay['approval'], 'execution': replay['execution']})
    with closing(sqlite3.connect(path)) as db:
        calls = db.execute('SELECT COUNT(*) FROM model_calls').fetchone()[0]
    return {'profiles': rows, 'changed_input_rejected': True, 'model_calls': calls}


def engagement(directory):
    # Reuse current attested contact, recipient, channel and sequence fixtures.
    from test_sequences import SequenceTests, NOW
    from acquisition.bootstrap import build_sequence_simulation
    class Fixture(SequenceTests):
        profiles = ('fielddesk',)
    Fixture.setUpClass()
    try:
        case = Fixture('test_new_process_replay_and_advance_preserve_one_logical_effect')
        case.path, case.now = directory / 'engagement.sqlite', NOW
        case.copy_template(); app, proposal, simulation = case.start()
        first = app.engagements.advance('one', simulation)
        before = case.counts()
        all_before = records(case.path)
        save(directory / 'authoritative-before.json', all_before)
        save(directory / 'engagement-input.json', {'simulation_id': simulation, 'clock': NOW})
        replay = command(['-m', 'scripts.boundary_journey_fixture', 'replay-engagement', directory], directory)
        if replay['receipt'] != first or case.counts() != before or records(case.path) != all_before:
            raise AssertionError('Engagement replay repeated an effect')
        save(directory / 'authoritative.json', records(case.path))
        return {'simulation_id': simulation, 'proposal_id': proposal['proposal_id'], 'counts': before,
                'fresh_process_pid': replay['pid'], 'same_receipt': True}
    finally:
        Fixture.tearDownClass()


def replay_engagement(directory):
    from acquisition.bootstrap import build_sequence_simulation
    data = json.loads((directory / 'engagement-input.json').read_text())
    with patch('acquisition.adapters.simulated_engagements.SyntheticEngagementTransport.submit',
               side_effect=AssertionError('Repeated synthetic submission')):
        app = build_sequence_simulation(directory / 'engagement.sqlite', 'one', 'fielddesk', lambda: data['clock'])
        receipt = app.engagements.advance('one', data['simulation_id'])
    return {'pid': os.getpid(), 'receipt': receipt}


CASES = {'verified-commit-rebuild-replay': verified, 'compatibility-model-journey': compatibility,
         'uncertain-restart': uncertain, 'profile-replay': profiles, 'engagement-replay': engagement}


def main():
    mode, location = sys.argv[1:]
    directory = Path(location)
    operation = {'replay-verified': replay_verified, 'replay-uncertain': replay_uncertain,
                 'replay-engagement': replay_engagement}.get(mode) or CASES[mode]
    value = operation(directory)
    value['process_pid'] = os.getpid()
    print(json.dumps(value, sort_keys=True))


if __name__ == '__main__':
    main()
