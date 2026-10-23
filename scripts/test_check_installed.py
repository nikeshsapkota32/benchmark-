"""Regression checks for the installed-package harness's fail-closed guards."""

from types import SimpleNamespace
import unittest
from unittest.mock import patch

import check_installed as checker


class InstalledGuardTests(unittest.TestCase):
    def test_isolated_mode_is_required(self):
        with patch.object(checker.sys, "flags", SimpleNamespace(isolated=0)):
            with self.assertRaisesRegex(RuntimeError, "Python and -I"):
                checker.main()

    def test_virtual_environment_is_required(self):
        with patch.object(checker.sys, "flags", SimpleNamespace(isolated=1)), patch.object(
                checker.sys, "prefix", checker.sys.base_prefix):
            with self.assertRaisesRegex(RuntimeError, "fresh virtual environment"):
                checker.main()

    def check_bad_install(self, origin, entrypoints, message):
        site = checker.ROOT / "unused-test-site"
        with patch.object(checker.sys, "flags", SimpleNamespace(isolated=1)), patch.object(
                checker.sys, "prefix", str(site)), patch.object(
                checker.sysconfig, "get_path", return_value=str(site)), patch.object(
                checker.importlib, "import_module", return_value=SimpleNamespace(__file__=str(origin))), patch.object(
                checker, "distribution", return_value=SimpleNamespace(entry_points=entrypoints)), patch.object(
                checker.subprocess, "run") as run:
            with self.assertRaisesRegex(RuntimeError, message):
                checker.main()
            run.assert_not_called()

    def test_source_checkout_import_is_rejected(self):
        self.check_bad_install(checker.ROOT / "src/benchguard/__init__.py", [], "site-packages")

    def test_missing_or_duplicate_console_entrypoint_is_rejected(self):
        origin = checker.ROOT / "unused-test-site/benchguard/__init__.py"
        entry = SimpleNamespace(group="console_scripts", name="benchguard")
        for entries in ([], [entry, entry], [SimpleNamespace(group="other", name="benchguard")]):
            with self.subTest(entries=entries):
                self.check_bad_install(origin, entries, "unique console entry point")


if __name__ == "__main__":
    unittest.main()
