from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import random
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from datasetlint import inspect
from datasetlint.__main__ import main
from datasetlint.indexes import open_indexes
from datasetlint.jsonl import inspect_jsonl


def fixture():
    return {"schema_version": 1, "splits": {
        "train": [{"id": "a", "text": "first"}, {"id": "a", "text": "second"}],
        "test": [{"id": "b", "text": "first"}, {"id": "b", "text": "first"}]}}


class SqliteIndexTests(unittest.TestCase):
    def test_same_deterministic_findings_and_original_first_locations(self):
        data = fixture()
        original = deepcopy(data)
        expected = inspect(data)
        self.assertEqual(inspect(data, index_backend="sqlite"), expected)
        self.assertEqual(inspect(data, index_backend="memory"), expected)
        self.assertEqual(data, original)
        self.assertEqual(expected["findings"][0]["first_index"], 0)
        self.assertEqual(expected["findings"][0]["first_split"], "test")

    def test_exact_unicode_nul_surrogates_and_separate_id_text_namespaces(self):
        values = ["A", "a", "a\0b", "a\0c", "é", "e\u0301", "नमस्ते", "\ud800", "𝄞", "\ud834\udd1e"]
        rows = [{"id": value, "text": values[(i + 1) % len(values)]} for i, value in enumerate(values)]
        data = {"schema_version": 1, "splits": {"split\udfff": rows}}
        self.assertTrue(inspect(data, index_backend="sqlite")["passed"])
        data["splits"]["z"] = deepcopy(rows)
        self.assertEqual(inspect(data, index_backend="sqlite"), inspect(data))

    def test_field_mapping_text_policy_and_all_finding_limits_match(self):
        data = {"schema_version": 1, "splits": {"train": [
            {"key": "a", "prompt": " alpha\t beta "},
            {"key": "b", "prompt": "alpha beta"},
            {"key": "a", "prompt": "alpha beta"}]}}
        for policy in ("exact", "ascii-whitespace-v1"):
            for limit in (None, 0, 1, 100):
                options = dict(id_field="key", text_field="prompt", text_policy=policy, max_findings=limit)
                with self.subTest(policy=policy, limit=limit):
                    self.assertEqual(inspect(data, index_backend="sqlite", **options), inspect(data, **options))

    def test_jsonl_locations_hashes_and_truncation_match(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = {}
            for name, rows in fixture()["splits"].items():
                path = Path(directory) / (name + ".jsonl")
                path.write_bytes("\r\n".join(json.dumps(row) for row in rows).encode("utf-8"))
                paths[name] = path
            for limit in (None, 0, 1):
                with self.subTest(limit=limit):
                    self.assertEqual(inspect_jsonl(paths, index_backend="sqlite", max_findings=limit),
                                     inspect_jsonl(paths, max_findings=limit))

    def test_randomized_multi_split_equivalence(self):
        rng = random.Random(17)
        data = {"schema_version": 1, "splits": {name: [
            {"id": str(rng.randrange(100)), "text": str(rng.randrange(200))}
            for _ in range(500)] for name in ("train", "validation", "test")}}
        for limit in (None, 0, 13):
            self.assertEqual(inspect(data, index_backend="sqlite", max_findings=limit),
                             inspect(data, max_findings=limit))

    def test_database_is_file_backed_and_closed_and_removed_on_success_or_failure(self):
        for fail in (False, True):
            with self.subTest(fail=fail):
                def use_index():
                    nonlocal database, connection
                    with open_indexes("sqlite") as (ids, texts):
                        connection = ids.connection
                        database = Path(connection.execute("PRAGMA database_list").fetchone()[2])
                        self.assertTrue(database.is_file())
                        ids["private-example"] = ("train", 0)
                        self.assertEqual(ids.get("private-example"), ("train", 0))
                        self.assertIsNone(texts.get("private-example"))
                        if fail:
                            raise ValueError("synthetic later validation failure")
                database = connection = None
                if fail:
                    with self.assertRaisesRegex(ValueError, "later validation"):
                        use_index()
                else:
                    use_index()
                self.assertFalse(database.parent.exists())
                with self.assertRaises(sqlite3.ProgrammingError):
                    connection.execute("SELECT 1")

    def test_invalid_backend_is_rejected_before_opening_files(self):
        for backend in (None, True, 1, "unknown", [], {}):
            with self.subTest(backend=backend), self.assertRaisesRegex(ValueError, "index_backend"):
                inspect_jsonl({"train": "does-not-exist"}, index_backend=backend)
            with self.subTest(backend=backend), self.assertRaisesRegex(ValueError, "index_backend"):
                inspect(fixture(), index_backend=backend)

    def test_late_validation_and_empty_split_fail_even_with_zero_findings(self):
        for invalid in ([{"id": "a", "text": "first"}, {"id": "bad"}], []):
            data = fixture()
            data["splits"]["z"] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                inspect(data, index_backend="sqlite", max_findings=0)

    def test_cli_json_and_jsonl_exit_codes_and_no_partial_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.json"
            source.write_text(json.dumps(fixture()), encoding="utf-8")
            linefile = Path(directory) / "input.jsonl"
            linefile.write_text('{"id":"a","text":"first"}\n', encoding="utf-8")
            cases = [([str(source)], 1), (["--split", "train=" + str(linefile)], 0)]
            for args, expected in cases:
                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err):
                    code = main(args + ["--index-backend", "sqlite", "--max-findings", "0"])
                self.assertEqual((code, err.getvalue()), (expected, ""))
                self.assertEqual(json.loads(out.getvalue())["passed"], expected == 0)
            linefile.write_text('{"id":"a","text":"first"}\nnot-json\n', encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = main(["--split", "train=" + str(linefile), "--index-backend", "sqlite"])
            self.assertEqual((code, out.getvalue()), (2, ""))
            self.assertIn(":2:", err.getvalue())

    def test_database_failure_is_sanitized_and_never_returns_partial_results(self):
        for target in ("sqlite3.connect", "datasetlint.indexes._SqliteIndex.__setitem__"):
            with self.subTest(target=target), patch(target, side_effect=sqlite3.OperationalError("private example")):
                with self.assertRaisesRegex(ValueError, "^SQLite index operation failed$"):
                    inspect(fixture(), index_backend="sqlite")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.json"
            source.write_text(json.dumps(fixture()), encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            with patch("sqlite3.connect", side_effect=sqlite3.OperationalError("private example")), redirect_stdout(out), redirect_stderr(err):
                code = main([str(source), "--index-backend", "sqlite"])
            self.assertEqual((code, out.getvalue()), (2, ""))
            self.assertEqual(err.getvalue(), "datasetlint: SQLite index operation failed\n")

    def test_default_backend_does_not_create_temp_storage(self):
        with patch("datasetlint.indexes.TemporaryDirectory") as directory:
            inspect(fixture())
        directory.assert_not_called()
