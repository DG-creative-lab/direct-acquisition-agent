import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("architecture", ROOT / "scripts/check_architecture.py")
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


class ArchitectureTests(unittest.TestCase):
    def test_harmful_boundary_mutations_are_detected(self):
        examples = [
            ("acquisition.runtime.application", "from acquisition.campaigns import Brief"),
            ("acquisition.adapters.http.workspace_server", "import sqlite3"),
            ("acquisition.adapters.http.workspace_server", "from acquisition.bootstrap import build"),
            ("acquisition.application.workspace.service", "from acquisition.workspace import Workspace"),
            ("acquisition.adapters.openrouter", "from acquisition.__main__ import main"),
            ("acquisition.campaigns.application", "from acquisition.adapters.sqlite import database"),
            ("acquisition.campaigns.domain", "from acquisition.audiences.domain import Snapshot"),
            ("acquisition.campaigns.domain", "from .application import CampaignService"),
            ("acquisition.learning.domain", "import sqlite3"),
            ("acquisition.runtime.application", "from acquisition import adapters"),
            ("acquisition.campaigns.application", "from acquisition.audiences import domain"),
            ("acquisition.conversations.application", "from acquisition.adapters.sqlite import conversations"),
            ("acquisition.conversations.application", "from acquisition.reviews import ReviewService"),
            ("acquisition.creative.recipient_application", "from acquisition.audiences.contacts import NativeReference"),
            ("acquisition.runtime.domain", "from acquisition.creative import RecipientTarget"),
            ("acquisition.runtime.application", "from acquisition.engagements import EngagementSimulator"),
            ("acquisition.engagements.domain", "import sqlite3"),
            ("acquisition.engagements.application", "from acquisition.adapters import simulated_engagements"),
            ("acquisition.campaigns.application", "from acquisition.engagements import EngagementSimulator"),
            ("acquisition.workflows.monthly_mail", "from acquisition.adapters.sqlite.drafts import SqliteDrafts"),
            ("acquisition.campaigns.application", "import sqlite3 as storage"),
            ("acquisition.creative.channel_agent", "from urllib.request import urlopen as fetch"),
            ("acquisition.conversations.actions", "import requests as provider"),
            ("acquisition.workflows.monthly_mail", "from acquisition.bootstrap import build"),
            ("acquisition.adapters.openrouter", "from acquisition.entrypoints.cli import main"),
            ("acquisition.adapters.openrouter", "from acquisition.workflows.monthly_mail import MonthlyMail"),
            ("acquisition.campaigns.domain", "from acquisition.creative import CopyAgent as CreativeValue"),
            ("acquisition.creative.recipient_context", "from acquisition.audiences import ContactDirectory as Reference"),
            ("acquisition.campaigns.domain", "import acquisition.creative as creative"),
            ("acquisition.campaigns.domain", "from acquisition import creative as creative"),
            ("acquisition.campaigns.domain", "from acquisition.creative import *"),
            ("acquisition.campaigns.application", "import tests.test_domain"),
            ("acquisition.adapters.openrouter", "from scripts import check_architecture"),
            ("acquisition.campaigns.application", "__import__('sqlite3')"),
            ("acquisition.adapters.openrouter", "from importlib import import_module as load"),
            ("acquisition.workflows.monthly_mail", "from builtins import __import__ as load"),
            ("acquisition.campaigns.application", "import pathlib"),
        ]
        for module, source in examples:
            with self.subTest(module=module, source=source):
                self.assertTrue(CHECKER.violations(source, module))
        self.assertFalse(CHECKER.violations('from acquisition.audiences import NativeReference',
                                            'acquisition.creative.recipient_context'))
        self.assertFalse(CHECKER.violations('from acquisition.campaigns import SequenceConnection',
                                            'acquisition.engagements.domain'))


class ArchitectureRepositoryTests(unittest.TestCase):
    """Observe checker exit diagnostics on small independently authored repositories."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.roles = {}
        self.exceptions = []

    def source(self, module, role, source='', package=False):
        path = self.root / 'src' / Path(*module.split('.'))
        path = path / '__init__.py' if package else path.with_suffix('.py')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
        if role is not None:
            self.roles[module] = role
        return path

    def check(self):
        policy = self.root / 'scripts/architecture_policy.json'
        policy.parent.mkdir(parents=True, exist_ok=True)
        policy.write_text(json.dumps({'version': 1, 'modules': self.roles,
                                      'exceptions': self.exceptions}))
        return CHECKER.check(self.root)

    def test_current_production_inventory_matches_reviewed_exceptions(self):
        self.assertEqual(CHECKER.check(ROOT), [])

    def test_unknown_new_files_and_stale_inventory_fail(self):
        self.source('acquisition.campaigns.new_rules', None)
        self.roles['acquisition.missing'] = 'application'
        errors = '\n'.join(self.check())
        self.assertIn('Unclassified production module', errors)
        self.assertIn('Classification has no production file', errors)
        self.source('acquisition.campaigns.new_rules', 'domain', package=True)
        self.assertIn('Ambiguous production module', '\n'.join(self.check()))

    def test_supporting_domain_files_obey_purity_and_report_locations(self):
        self.source('acquisition.creative.recipient_context', 'domain', 'import sqlite3\n')
        self.assertEqual(len(self.check()), 1)
        self.assertIn('src/acquisition/creative/recipient_context.py:1: [pure-import]', self.check()[0])

    def test_domain_reexports_resolve_alias_chains_without_certifying_sibling_services(self):
        self.source('acquisition', 'public_api', package=True)
        self.source('acquisition.creative.domain', 'domain', 'class Creative: pass\n')
        self.source('acquisition.creative.application', 'application', 'class CopyAgent: pass\n')
        api = self.source('acquisition.creative', 'public_api',
                          'from .domain import Creative as Value\n'
                          'from .application import CopyAgent as Service\n'
                          'Export = Value\n', package=True)
        self.source('acquisition.campaigns.domain', 'domain',
                    'from acquisition.creative import Export as Creative\n')
        self.assertEqual(self.check(), [])
        # Retain every file/import and swap just the facade alias target.
        api.write_text(api.read_text().replace('Export = Value', 'Export = Service'))
        self.assertIn('domain may not depend on application', '\n'.join(self.check()))
        api.write_text('from .domain import Creative as Export\n'
                       'if some_configuration:\n    from .application import CopyAgent as Export\n')
        self.assertIn('no statically resolvable origin', '\n'.join(self.check()))
        header = 'from .domain import Creative as Value\nfrom .application import CopyAgent as Service\n'
        for assignments, expected in (('Export = Service\nService = Value\n', 'service'),
                                      ('Export = Value\nValue = Service\n', 'pure')):
            with self.subTest(expected=expected):
                api.write_text(header + assignments)
                observed = subprocess.run(
                    [sys.executable, '-B', '-c', 'import sys; sys.path.insert(0, sys.argv[1]); '
                     'from acquisition.creative import Export; '
                     'from acquisition.creative.domain import Creative; '
                     'from acquisition.creative.application import CopyAgent; '
                     'assert Export is (Creative if sys.argv[2] == "pure" else CopyAgent)',
                     str(self.root / 'src'), expected], capture_output=True, text=True, timeout=10)
                self.assertEqual(observed.returncode, 0, observed.stderr)
                if expected == 'pure':
                    self.assertEqual(self.check(), [])
                else:
                    self.assertIn('domain may not depend on application', '\n'.join(self.check()))

        api.write_text('from .domain import Creative as Value\n'
                       'class Factory: pass\nExport = Factory\nFactory = Value\n')
        self.assertIn('domain may not depend on public_api', '\n'.join(self.check()))

    def test_relative_alias_and_reexport_cycles_cannot_hide_a_service(self):
        self.source('acquisition.campaigns.application', 'application', 'class Service: pass\n')
        self.source('acquisition.campaigns', 'public_api',
                    'from .application import Service as Value\n', package=True)
        self.source('acquisition.campaigns.domain', 'domain', 'from . import Value as Model\n')
        self.assertIn('domain may not depend on application', '\n'.join(self.check()))
        api = self.source('acquisition.creative', 'public_api',
                          'First = Second\nSecond = First\n', package=True)
        self.source('acquisition.campaigns.domain', 'domain',
                    'from acquisition.creative import First\n')
        self.assertIn('no statically resolvable origin', '\n'.join(self.check()))
        api.write_text('from .application import *\n')
        self.assertIn('[wildcard]', '\n'.join(self.check()))

    def test_pure_public_contracts_ports_and_adapter_validators_are_allowed(self):
        self.source('acquisition.campaigns.domain', 'domain', 'def validate(): pass\n')
        self.source('acquisition.campaigns.ports', 'ports', 'class Store: pass\n')
        self.source('acquisition.campaigns', 'public_api',
                    'from .domain import validate\nfrom .ports import Store\n', package=True)
        self.source('acquisition.engagements.domain', 'domain',
                    'from acquisition.campaigns import validate as check\n')
        self.source('acquisition.engagements.application', 'application',
                    'from acquisition.campaigns import Store\n')
        self.source('acquisition.adapters.sqlite.example', 'adapter',
                    'import sqlite3\nfrom acquisition.campaigns import validate\n')
        self.assertEqual(self.check(), [])

    def test_reverse_composition_and_entrypoint_imports_fail(self):
        self.source('acquisition.bootstrap', 'composition', 'def build(): pass\n')
        self.source('acquisition.__main__', 'entrypoint', 'from .bootstrap import build\n')
        self.assertEqual(self.check(), [])
        self.source('acquisition.workflows.example', 'workflow',
                    'from acquisition.bootstrap import build\n')
        self.source('acquisition.adapters.example', 'adapter',
                    'import acquisition.__main__\n')
        errors = '\n'.join(self.check())
        self.assertIn('workflow may not depend on composition', errors)
        self.assertIn('adapter may not depend on entrypoint', errors)

    def test_compatibility_wrappers_cannot_hide_effects_or_reverse_dependencies(self):
        self.source('acquisition.entrypoints.cli', 'entrypoint', 'def main(): pass\n')
        wrapper = self.source('acquisition.__main__', 'wrapper',
            'from acquisition.entrypoints.cli import main\nif __name__ == "__main__":\n    main()\n')
        self.assertEqual(self.check(), [])
        for module, role in [('acquisition.bootstrap', 'composition'),
                             ('acquisition.adapters.example', 'adapter'),
                             ('acquisition.application.example', 'application')]:
            self.source(module, role, 'from acquisition.__main__ import main\n')
        errors = '\n'.join(self.check())
        for role in ('composition', 'adapter', 'application'):
            self.assertIn(role + ' may not depend on wrapper', errors)
        wrapper.write_text('from acquisition.entrypoints.cli import main\ndef start(): main()\n')
        self.assertIn('[wrapper]', '\n'.join(self.check()))
        wrapper.write_text('from acquisition.bootstrap import build\n')
        self.assertIn('wrapper may not depend on composition', '\n'.join(self.check()))

    def test_eager_module_and_deferred_package_cycles_fail(self):
        self.source('acquisition.audiences.left', 'domain', 'from .right import Value\nclass Value: pass\n')
        self.source('acquisition.audiences.right', 'domain', 'from .left import Value\nclass Value: pass\n')
        self.assertIn('[module-cycle]', '\n'.join(self.check()))
        # Cross-package dependency direction remains checked inside functions.
        self.source('acquisition.workflows.example', 'workflow',
                    'def late():\n    import acquisition.bootstrap\n')
        self.source('acquisition.bootstrap', 'composition', 'import acquisition.workflows.example\n')
        self.assertIn('[package-cycle]', '\n'.join(self.check()))

    def test_submodule_import_checks_implicit_parent_initialization(self):
        self.source('acquisition', 'public_api', package=True)
        self.source('acquisition.audiences', 'public_api', package=True)
        parent = self.source('acquisition.audiences.nested', 'public_api',
                             'from ..left import VALUE\n', package=True)
        self.source('acquisition.audiences.nested.child', 'domain', 'VALUE = 2\n')
        imports = ('import acquisition.audiences.nested.child as child',
                   'from .nested.child import VALUE as CHILD',
                   'from .nested import child')
        for statement in imports:
            with self.subTest(statement=statement):
                self.source('acquisition.audiences.left', 'domain', statement + '\nVALUE = 1\n')
                observed = subprocess.run(
                    [sys.executable, '-c', 'import sys; sys.path.insert(0, sys.argv[1]); '
                     'import acquisition.audiences.left', str(self.root / 'src')],
                    capture_output=True, text=True, timeout=10)
                self.assertNotEqual(observed.returncode, 0)
                self.assertIn('partially initialized module', observed.stderr)
                errors = '\n'.join(self.check())
                self.assertIn('[module-cycle]', errors)
                self.assertIn('acquisition.audiences.left', errors)
                self.assertIn('acquisition.audiences.nested', errors)
        parent.write_text('')
        self.assertEqual(self.check(), [])

    def test_parent_initializer_can_import_a_child_that_imports_a_sibling(self):
        self.source('acquisition', 'public_api', package=True)
        self.source('acquisition.audiences', 'public_api', 'from .left import VALUE\n', package=True)
        self.source('acquisition.audiences.left', 'domain', 'from .right import OTHER\nVALUE = OTHER\n')
        self.source('acquisition.audiences.right', 'domain', 'OTHER = 1\n')
        observed = subprocess.run(
            [sys.executable, '-c', 'import sys; sys.path.insert(0, sys.argv[1]); '
             'import acquisition.audiences.left', str(self.root / 'src')],
            capture_output=True, text=True, timeout=10)
        self.assertEqual(observed.returncode, 0, observed.stderr)
        self.assertEqual(self.check(), [])

    def test_asyncio_network_and_process_dependencies_stay_in_adapters(self):
        roles = {'acquisition.audiences.application': 'application',
                 'acquisition.audiences.ports': 'ports',
                 'acquisition.audiences': 'public_api',
                 'acquisition.workflows.example': 'workflow',
                 'acquisition.__main__': 'entrypoint',
                 'acquisition.workspace_server': 'transport'}
        for module, role in roles.items():
            self.source(module, role, package=role == 'public_api')
        snippets = (
            "import asyncio as io\nasync def effect():\n    return await io.open_connection('example.test', 443)\n",
            "from asyncio import create_subprocess_exec as launch\nasync def effect():\n    return await launch('example')\n",
            'import asyncio.subprocess as processes\n',
        )
        for module, role in roles.items():
            for source in snippets:
                with self.subTest(role=role, source=source):
                    path = self.source(module, role, source, package=role == 'public_api')
                    errors = self.check()
                    self.assertTrue(any('[infrastructure]' in error and 'asyncio' in error for error in errors), errors)
                    path.write_text('')
        self.source('acquisition.adapters.example', 'adapter', 'import asyncio\n')
        self.assertEqual(self.check(), [])

    def test_unpacking_cannot_retain_an_earlier_pure_export_origin(self):
        self.source('acquisition', 'public_api', package=True)
        self.source('acquisition.creative.domain', 'domain', 'class Creative: pass\n')
        self.source('acquisition.creative.application', 'application', 'class CopyAgent: pass\n')
        header = ('from .domain import Creative as Export\n'
                  'from .application import CopyAgent\n')
        api = self.source('acquisition.creative', 'public_api', header, package=True)
        self.source('acquisition.campaigns.domain', 'domain',
                    'from acquisition.creative import Export as Value\n')
        self.assertEqual(self.check(), [])
        assignments = (
            'Export, other = CopyAgent, None',
            '[Export, other] = [CopyAgent, None]',
            '(other, [Export]) = (None, [CopyAgent])',
            '(Export, *others) = (CopyAgent, None)',
            'others = (Export, other) = (CopyAgent, None)',
            '([other, *rest], Export) = ([None, None], CopyAgent)',
        )
        for assignment in assignments:
            with self.subTest(assignment=assignment):
                api.write_text(header + assignment + '\n')
                observed = subprocess.run(
                    [sys.executable, '-B', '-c', 'import sys; sys.path.insert(0, sys.argv[1]); '
                     'from acquisition.creative import Export, CopyAgent; assert Export is CopyAgent',
                     str(self.root / 'src')], capture_output=True, text=True, timeout=10)
                self.assertEqual(observed.returncode, 0, observed.stderr)
                self.assertIn('[unresolved-export]', '\n'.join(self.check()))
        api.write_text(header + 'left, right = None, None\n')
        self.assertEqual(self.check(), [])

    def test_alternate_infrastructure_imports_do_not_rely_on_a_denylist(self):
        roles = {'acquisition.audiences.application': 'application',
                 'acquisition.audiences.ports': 'ports',
                 'acquisition.audiences': 'public_api',
                 'acquisition.workflows.example': 'workflow',
                 'acquisition.__main__': 'entrypoint',
                 'acquisition.workspace_server': 'transport'}
        for module, role in roles.items():
            self.source(module, role, package=role == 'public_api')
        snippets = (
            'from _socket import socket as connect\n',
            'from _sqlite3 import connect as database\n',
            'from posix import system as launch\n',
            'import nt as processes\n',
            'from ctypes import CDLL as library\n',
            'from io import open as read_file\n',
            'import io as files\n',
            'import _io as files\n',
            'import concurrent.futures as workers\n',
            'import logging.config as configuration\n',
            'import json.tool as command\n',
            'from json import tool as command\n',
            'from pickle import loads as decode\n',
        )
        for module, role in roles.items():
            for snippet in snippets:
                with self.subTest(role=role, snippet=snippet):
                    path = self.source(module, role, snippet, package=role == 'public_api')
                    self.assertTrue(any('[infrastructure]' in error for error in self.check()), snippet)
                    path.write_text('')
        # Value/coordination contracts remain available without broad module access.
        self.source('acquisition.audiences.application', 'application',
                    'from collections.abc import Callable\nfrom io import StringIO as Buffer\n'
                    'from urllib.parse import urlparse\nfrom threading import Lock\n')
        self.source('acquisition.adapters.example', 'adapter', ''.join(snippets))
        self.assertEqual(self.check(), [])

    def test_transport_admits_protocol_dependencies_but_rejects_other_infrastructure(self):
        allowed = ('from http.server import BaseHTTPRequestHandler as Handler, ThreadingHTTPServer\n'
                   'from pathlib import Path\nfrom contextlib import ExitStack\n'
                   'from urllib.parse import urlsplit, parse_qs\n'
                   'import mimetypes\nimport argparse\nimport threading\n')
        path = self.source('acquisition.workspace_server', 'transport', allowed)
        self.assertEqual(self.check(), [])
        for forbidden in ('import sqlite3 as storage', 'import requests as provider',
                          'from urllib.request import urlopen as fetch',
                          'from http.client import HTTPSConnection', 'from http import client',
                          'import http.server as server', 'from http.server import socketserver',
                          'from mimetypes import os'):
            with self.subTest(forbidden=forbidden):
                path.write_text(allowed + forbidden + '\n')
                self.assertTrue(any('[infrastructure]' in error for error in self.check()), forbidden)
        path.write_text(allowed)
        self.assertEqual(self.check(), [])

    def test_deferred_internal_adapter_import_does_not_claim_an_initialization_cycle(self):
        self.source('acquisition.adapters.left', 'adapter',
                    'def value():\n    from .right import value\n')
        self.source('acquisition.adapters.right', 'adapter', 'from .left import value\n')
        self.assertEqual(self.check(), [])

    def test_closed_migration_rejects_even_an_exact_former_exception(self):
        path = self.source('acquisition.workspace', 'application', 'import sqlite3\n')
        for issue in (90, 91, 92, 93):
            with self.subTest(issue=issue):
                self.exceptions = [{'module': 'acquisition.workspace', 'rule': 'infrastructure',
                                    'target': 'sqlite3', 'occurrences': 1, 'issue': issue,
                                    'reason': 'Former migration allowance.'}]
                self.assertIn('migration is closed', '\n'.join(self.check()))
        path.write_text('')
        self.assertIn('migration is closed', '\n'.join(self.check()))
        self.exceptions = []
        self.assertEqual(self.check(), [])

    def test_nonempty_or_malformed_exception_ledgers_cannot_reopen_migration(self):
        self.source('acquisition.workspace', 'application', 'import socket\n')
        for exceptions in ([{}], [None], ['legacy'], False, {}, None):
            with self.subTest(exceptions=exceptions):
                self.exceptions = exceptions
                self.assertIn('exceptions must be an empty list', '\n'.join(self.check()))
        self.exceptions = []
        self.assertIn('[infrastructure]', '\n'.join(self.check()))

    def test_duplicate_policy_keys_cannot_replace_the_closed_ledger(self):
        self.check()
        policy = self.root / CHECKER.POLICY
        policy.write_text('{"version": 1, "version": 1, "modules": {}, "exceptions": []}')
        self.assertIn('Duplicate policy key', '\n'.join(CHECKER.check(self.root)))

    def test_command_returns_nonzero_for_a_new_infrastructure_dependency(self):
        path = self.source('acquisition.campaigns.application', 'application', 'import sqlite3\n')
        self.check()  # Write the independently specified fixture policy.
        script = self.root / 'scripts/check_architecture.py'
        script.write_text((ROOT / 'scripts/check_architecture.py').read_text())
        failed = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
        self.assertEqual(failed.returncode, 1, failed.stderr)
        self.assertIn('campaigns/application.py:1: [infrastructure]', failed.stdout)
        path.write_text('')
        passed = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
        self.assertEqual(passed.returncode, 0, passed.stdout + passed.stderr)
        self.assertIn('0 explicit temporary dependency exceptions', passed.stdout)
