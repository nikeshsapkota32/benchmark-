"""Regression checks for the installed-package harness's fail-closed guards."""

from types import SimpleNamespace
from email.message import Message
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


class InstalledLicenseTests(unittest.TestCase):
    def installed(self, expression="MIT", files=("LICENSE",), text="synthetic license text\n"):
        metadata = Message()
        if expression is not None:
            metadata["License-Expression"] = expression
        for filename in files:
            metadata["License-File"] = filename
        def read_text(path):
            self.assertEqual(path, "licenses/LICENSE")
            return text
        return SimpleNamespace(metadata=metadata, read_text=read_text)

    def test_matching_license_is_accepted(self):
        checker.check_license("example", self.installed(), "synthetic license text\n")

    def test_missing_or_wrong_expression_is_rejected(self):
        for expression in (None, "BSD-3-Clause"):
            with self.subTest(expression=expression), self.assertRaisesRegex(RuntimeError, "MIT license expression"):
                checker.check_license("example", self.installed(expression=expression), "synthetic license text\n")

    def test_missing_wrong_or_duplicate_file_declaration_is_rejected(self):
        for files in ((), ("COPYING",), ("LICENSE", "LICENSE")):
            with self.subTest(files=files), self.assertRaisesRegex(RuntimeError, "unique LICENSE declaration"):
                checker.check_license("example", self.installed(files=files), "synthetic license text\n")

    def test_missing_or_changed_license_text_is_rejected(self):
        for text in (None, "", "different text\n"):
            with self.subTest(text=text), self.assertRaisesRegex(RuntimeError, "differs from the source"):
                checker.check_license("example", self.installed(text=text), "synthetic license text\n")


if __name__ == "__main__":
    unittest.main()
