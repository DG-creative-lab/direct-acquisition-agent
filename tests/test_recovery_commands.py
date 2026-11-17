"""Offline CLI failures preserve storage and keep native errors behind the adapter."""
import io
import sqlite3
import unittest
from contextlib import closing, redirect_stderr
from unittest.mock import patch
from acquisition.entrypoints import legacy_migration, workspace_checkpoint, workspace_fixture, workspace_rebuild


class RecoveryCommandTests(unittest.TestCase):
    def test_native_storage_failures_use_each_commands_existing_error_contract(self):
        def unavailable(*args, **kwargs):
            with closing(sqlite3.connect(':memory:')) as database:
                database.execute('SELECT * FROM missing_recovery_metadata')

        cases = [
            (workspace_fixture, 'initialize_fixture_workspace', ['--root', 'unused'], 'missing_recovery_metadata'),
            (workspace_checkpoint, 'build_workspace_checkpoint', ['verify', '--bundle', 'unused'], 'Preserve the originals'),
            (workspace_rebuild, 'build_workspace_projection', ['--root', 'unused', 'inspect'], 'Recovery metadata is incomplete'),
            (legacy_migration, 'build_legacy_migration_inventory', ['--root', 'unused', 'inspect'], 'Legacy sources are unavailable'),
        ]
        for command, factory, args, message in cases:
            with self.subTest(command=command.__name__), patch.object(command, factory, unavailable), patch('sys.argv', ['recovery', *args]):
                error = io.StringIO()
                with redirect_stderr(error), self.assertRaises(SystemExit) as stopped:
                    command.main()
                self.assertEqual(stopped.exception.code, 2)
                self.assertIn(message, error.getvalue())
                self.assertNotIn('Traceback', error.getvalue())
