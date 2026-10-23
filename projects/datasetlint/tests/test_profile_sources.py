"""Source identity must agree before resource measurements can be combined."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch


script = Path(__file__).resolve().parents[1] / "scripts" / "profile_indexes.py"
spec = importlib.util.spec_from_file_location("profile_sources", script)
profiler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profiler)


@unittest.skipUnless(sys.platform == "linux", "Linux profiling workers")
class ProfileSourceTests(unittest.TestCase):
    def assert_cli_error(self, argv, message):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = profiler.main(argv)
        self.assertEqual((code, out.getvalue()), (2, ""))
        self.assertIn(message, err.getvalue())
        self.assertNotIn("synthetic source change", err.getvalue())

    def test_different_worker_script_or_imported_sources_discard_measurements(self):
        run = profiler.subprocess.run
        for target in ("script", "__init__.py", "indexes.py", "jsonl.py"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                copied_script = root / "profile_indexes.py"
                copied_script.write_bytes(script.read_bytes())
                package = root / "datasetlint"
                shutil.copytree(Path(profiler.datasetlint.__file__).parent, package,
                                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
                changed = copied_script if target == "script" else package / target
                changed.write_bytes(changed.read_bytes() + b"\n# synthetic source change\n")
                reports = []

                def different_worker(command, **kwargs):
                    command = list(command)
                    if reports:
                        command[1] = str(copied_script)
                        kwargs["env"] = dict(os.environ, PYTHONPATH=str(root), PYTHONNOUSERSITE="1")
                    result = run(command, **kwargs)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    reports.append(json.loads(result.stdout)["report"])
                    return result

                with patch.object(profiler.subprocess, "run", side_effect=different_worker):
                    self.assert_cli_error(["--records", "10", "--text-bytes", "32",
                                           "--trials", "1"], "worker sources differ")
                self.assertEqual(reports[0]["counts"], {"train": 10, "test": 1})
                self.assertEqual(reports[0]["total_findings"], 2)
                self.assertEqual(len(reports), 2)
                self.assertEqual(reports[0], reports[1])

    def test_identical_sources_at_different_paths_are_accepted(self):
        run = profiler.subprocess.run
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copied_script = root / "profile_indexes.py"
            copied_script.write_bytes(script.read_bytes())
            shutil.copytree(Path(profiler.datasetlint.__file__).parent, root / "datasetlint",
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

            def relocated_worker(command, **kwargs):
                command = list(command)
                command[1] = str(copied_script)
                env = dict(os.environ, PYTHONPATH=str(root), PYTHONNOUSERSITE="1")
                return run(command, env=env, **kwargs)

            with patch.object(profiler.subprocess, "run", side_effect=relocated_worker):
                result = profiler.profile(10, 32, 1)
            self.assertEqual(len(result["runs"]), 2)
            for row in result["runs"]:
                self.assertEqual(row["script_sha256"], result["script_sha256"])
                self.assertEqual(row["implementation_sha256"], result["implementation_sha256"])

    def test_missing_worker_fingerprints_cannot_be_silently_accepted(self):
        run = profiler.subprocess.run

        def missing_sources(command, **kwargs):
            result = run(command, **kwargs)
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            payload.pop("script_sha256", None)
            payload.pop("implementation_sha256", None)
            result.stdout = json.dumps(payload)
            return result

        with patch.object(profiler.subprocess, "run", side_effect=missing_sources):
            self.assert_cli_error(["--records", "10", "--trials", "1"],
                                  "worker sources differ")

    def test_worker_rejects_persistent_source_changes_during_scan(self):
        inspect_jsonl = profiler.jsonl.inspect_jsonl
        original_hook = profiler.datasetlint.open_indexes
        for module in (profiler, profiler.datasetlint, profiler.indexes, profiler.jsonl):
            with self.subTest(module=module.__name__), tempfile.TemporaryDirectory() as directory:
                paths = profiler.write_synthetic(directory, 10, 32)
                copied_source = Path(directory) / "source.py"
                copied_source.write_bytes(Path(module.__file__).read_bytes())

                def changing_scan(*args, **kwargs):
                    report = inspect_jsonl(*args, **kwargs)
                    copied_source.write_bytes(copied_source.read_bytes()
                                              + b"\n# synthetic source change\n")
                    return report

                with patch.object(module, "__file__", str(copied_source)), \
                        patch.object(profiler.jsonl, "inspect_jsonl", side_effect=changing_scan):
                    self.assert_cli_error(["--worker", "sqlite", str(paths["train"]),
                                           str(paths["test"])], "sources changed during worker")
                self.assertIs(profiler.datasetlint.open_indexes, original_hook)

    def test_parent_rejects_source_changes_after_last_worker(self):
        run = profiler.subprocess.run
        with tempfile.TemporaryDirectory() as directory:
            copied_script = Path(directory) / "profile_indexes.py"
            copied_script.write_bytes(script.read_bytes())
            calls = 0

            def changing_parent(command, **kwargs):
                nonlocal calls
                result = run(command, **kwargs)
                self.assertEqual(result.returncode, 0, result.stderr)
                calls += 1
                if calls == 2:
                    copied_script.write_bytes(copied_script.read_bytes()
                                              + b"\n# synthetic source change\n")
                return result

            with patch.object(profiler, "__file__", str(copied_script)), \
                    patch.object(profiler.subprocess, "run", side_effect=changing_parent):
                self.assert_cli_error(["--records", "10", "--trials", "1"],
                                      "sources changed during profile")
            self.assertEqual(calls, 2)
