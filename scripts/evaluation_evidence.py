"""Source attribution shared by offline evaluations."""

import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def source_state(root=ROOT, prefixes=('src', 'tests', 'config', 'scripts')):
    """Record actual import/configuration inputs, including uncommitted files."""
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=root, stderr=subprocess.PIPE).decode()

    head = git('rev-parse', 'HEAD').strip()
    tracked = {entry.split('\t', 1)[1]: entry.split('\t', 1)[0].split()[2]
               for entry in git('ls-tree', '-r', '-z', 'HEAD', '--', *prefixes).split('\0') if entry}
    object_format = git('rev-parse', '--show-object-format').strip()
    paths = set(tracked)
    for prefix in prefixes:
        if (root / prefix).is_file():
            paths.add(prefix)
        paths.update(p.relative_to(root).as_posix() for p in (root / prefix).rglob('*')
                     if (p.is_file() or p.is_symlink()) and '__pycache__' not in p.parts
                     and p.suffix not in {'.pyc', '.pyo'})
    files = {}
    changes_to_head = []
    for relative in sorted(paths):
        path = root / relative
        content = path.read_bytes() if path.is_file() else None
        record = {'sha256': hashlib.sha256(content).hexdigest() if content is not None else None}
        blob = hashlib.new(object_format, b'blob ' + str(len(content)).encode() + b'\0' + content).hexdigest() if content is not None else None
        if blob != tracked.get(relative) or relative not in tracked or path.is_symlink():
            changes_to_head.append(relative)
        if path.is_symlink():
            record['symlink_target'] = str(path.readlink())
        files[relative] = record
    status = list(filter(None, git('status', '--porcelain=v1', '-z', '--untracked-files=all', '--', *prefixes).split('\0')))
    digest = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'head_commit': head, 'worktree_dirty': bool(status or changes_to_head),
            'git_status': status, 'changes_to_head': changes_to_head, 'files_sha256': digest, 'files': files}
