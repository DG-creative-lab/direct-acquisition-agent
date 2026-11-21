"""Build a small, private probe deployment with an explicit file allowlist."""

import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def package(output, *, commit='HEAD'):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError('Use a new probe package destination')
    link = json.loads((ROOT / '.vercel/project.json').read_text())
    if link.get('projectName') != 'direct-acquisition-feasibility':
        raise ValueError('Packaging requires the isolated feasibility project link')
    # Resolve once, then read immutable objects. Neither the index nor working
    # tree supplies deployable bytes, even if it changes while packaging runs.
    revision = subprocess.check_output(['git', 'rev-parse', '--verify', '--end-of-options',
                                        commit + '^{commit}'], cwd=ROOT, text=True).strip()
    entries = {'scripts/hosting_probe.py': 'scripts/hosting_probe.py',
               'scripts/hosting_function.py': 'api/probe.py'}
    tree = subprocess.check_output(['git', 'ls-tree', '-rz', revision, '--',
                                    'src', 'config', *entries], cwd=ROOT)
    payload, origins = {}, {}
    for record in filter(None, tree.split(b'\0')):
        metadata, name = record.split(b'\t', 1)
        mode, kind, identity = metadata.decode().split()
        if mode not in {'100644', '100755'} or kind != 'blob':
            raise ValueError('Probe packages require regular checked-in source files')
        source = name.decode()
        target = entries.get(source, source)
        payload[target] = subprocess.check_output(['git', 'cat-file', 'blob', identity], cwd=ROOT)
        origins[target] = source
    if not set(entries.values()) <= payload.keys():
        raise ValueError('The selected commit must include both reviewed probe entry files')
    payload['public/index.txt'] = b'Private infrastructure feasibility probe. Not a product release.\n'
    payload['pyproject.toml'] = ('[project]\nname="acquisition-hosting-probe"\n'
        'version="0.0.1"\nrequires-python=">=3.14,<3.15"\ndependencies=["libsql==0.1.11"]\n').encode()
    payload['vercel.json'] = (json.dumps({'framework': None, 'buildCommand': '',
        'installCommand': '', 'outputDirectory': 'public', 'regions': ['dub1'],
        'functions': {'api/probe.py': {'maxDuration': 180}}}, indent=2) + '\n').encode()
    payload['.vercel/project.json'] = (json.dumps(
        {k: link[k] for k in ('orgId', 'projectId', 'projectName')}) + '\n').encode()
    manifest = {'schema': 'hosting-probe-package/v1', 'source_commit': revision,
                'git_paths': origins,
                'files': {name: {'sha256': hashlib.sha256(raw).hexdigest()}
                          for name, raw in sorted(payload.items())}}
    payload['hosting-probe-source.json'] = (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode()
    output.mkdir(parents=True)
    for relative, raw in payload.items():
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    return output


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--commit', default='HEAD', help='Reviewed commit containing source, config and probe entries')
    args = parser.parse_args()
    print(package(args.output, commit=args.commit))
