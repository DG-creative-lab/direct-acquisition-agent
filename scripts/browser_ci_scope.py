"""Select PR smoke or full browser coverage without changing backend coverage."""

import json
import os
from pathlib import Path
import re
import subprocess


PRODUCT_PREFIXES = (
    'frontend/src/', 'frontend/public/', 'config/',
    'src/acquisition/adapters/http/', 'src/acquisition/adapters/sqlite/',
    'src/acquisition/adapters/turso/',
    'src/acquisition/application/workspace/', 'src/acquisition/runtime/',
    'src/acquisition/workflows/',
)
PRODUCT_FILES = frozenset({
    'frontend/index.html', 'frontend/package.json', 'frontend/pnpm-lock.yaml',
    'frontend/vite.config.ts', 'frontend/tsconfig.json',
    'src/acquisition/bootstrap.py', 'src/acquisition/entrypoints/workspace.py',
    'src/acquisition/workspace_server.py', 'pyproject.toml',
})
BROWSER_PREFIXES = ('frontend/tests/', 'frontend/scripts/')
BROWSER_FILES = frozenset({
    'frontend/playwright.config.ts', 'frontend/browser-smoke.json',
    '.github/workflows/ci.yml', 'scripts/browser_ci_scope.py',
    'scripts/offline_journey_fixture.py',
    # Python helpers imported by browser drivers are part of their harness too.
    'tests/test_preparations.py', 'tests/test_conversations.py',
    'tests/test_conversation_actions.py', 'tests/test_conversational_copy_revision.py',
    'tests/test_copy_revisions.py', 'tests/test_model_copy.py',
    'tests/prepared_workspace_fixture.py',
})
FAST_PREFIXES = (
    'docs/', 'tests/', 'scripts/', '.github/',
    'src/acquisition/audiences/', 'src/acquisition/campaigns/',
    'src/acquisition/creative/', 'src/acquisition/reasoning/',
    'src/acquisition/learning/', 'src/acquisition/reviews/',
    'src/acquisition/conversations/', 'src/acquisition/engagements/',
)
FAST_FILES = frozenset({
    'README.md', 'AGENTS.md', '.gitignore', 'Makefile',
})


def select_suite(event_name, labels, paths):
    labels = {label.casefold() for label in labels}
    if event_name != 'pull_request':
        return 'full', 'Main always runs the full browser suite'
    if 'full-browser-checks' in labels:
        return 'full', 'Explicit full-browser-checks label'
    if paths is None:
        return 'full', 'Changed paths could not be established'
    if any(path in BROWSER_FILES or path.startswith(BROWSER_PREFIXES) for path in paths):
        return 'full', 'Browser tests, shared harness or coverage configuration changed'
    if 'skip-browser-checks' in labels:
        return 'skip', 'Explicit skip-browser-checks label'
    if any(path in PRODUCT_FILES or path.startswith(PRODUCT_PREFIXES) for path in paths):
        return 'full', 'Product UI, HTTP, persistence, runtime or composition changed'
    if any(path.startswith('src/') and any(term in Path(path).name for term in ('recovery', 'checkpoint'))
           for path in paths):
        return 'full', 'Recovery or checkpoint code changed'
    if any(path not in FAST_FILES and not path.startswith(FAST_PREFIXES) for path in paths):
        return 'full', 'Unclassified paths require full browser coverage'
    return 'smoke', 'Routine PR: critical browser journeys; full portfolio on main'


def changed_paths(base):
    if not isinstance(base, str) or not re.fullmatch(r'[0-9a-fA-F]{40}', base):
        return None
    try:
        # Include both ends of renames, so moving a product file cannot avoid full coverage.
        result = subprocess.run(['git', 'diff', '--no-renames', '--name-only', '-z',
                                 base + '...HEAD'], capture_output=True, check=True)
        return result.stdout.decode('utf-8', errors='surrogateescape').rstrip('\0').split('\0')
    except (OSError, subprocess.CalledProcessError):
        return None


def main():
    try:
        event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    except (OSError, KeyError, ValueError):
        event = {}
    name = os.environ.get('GITHUB_EVENT_NAME', '')
    pr = event.get('pull_request', {}) if isinstance(event, dict) else {}
    labels = [label['name'] for label in pr.get('labels', [])
              if isinstance(label, dict) and isinstance(label.get('name'), str)]
    paths = changed_paths(pr.get('base', {}).get('sha')) if name == 'pull_request' else None
    suite, reason = select_suite(name, labels, paths)
    with Path(os.environ['GITHUB_OUTPUT']).open('a') as stream:
        stream.write(f'suite={suite}\nreason={reason}\n')
    print(f'Browser coverage: {suite}. {reason}.')


if __name__ == '__main__':
    main()
