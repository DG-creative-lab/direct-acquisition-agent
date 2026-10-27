import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("architecture", ROOT / "scripts/check_architecture.py")
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


class ArchitectureTests(unittest.TestCase):
    def test_actual_module_imports_and_cycles(self):
        self.assertEqual(CHECKER.check(ROOT), [])

    def test_harmful_boundary_mutations_are_detected(self):
        examples = [
            ("acquisition.runtime.application", "from acquisition.campaigns import Brief"),
            ("acquisition.campaigns.application", "from acquisition.adapters.sqlite import database"),
            ("acquisition.campaigns.domain", "from acquisition.audiences.domain import Snapshot"),
            ("acquisition.campaigns.domain", "from .application import CampaignService"),
            ("acquisition.learning.domain", "import sqlite3"),
            ("acquisition.runtime.application", "from acquisition import adapters"),
            ("acquisition.campaigns.application", "from acquisition.audiences import domain"),
            ("acquisition.conversations.application", "from acquisition.adapters.sqlite import conversations"),
            ("acquisition.conversations.application", "from acquisition.reviews import ReviewService"),
        ]
        for module, source in examples:
            with self.subTest(module=module, source=source):
                self.assertTrue(CHECKER.violations(source, module))
