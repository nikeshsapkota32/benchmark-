from contextlib import redirect_stderr, redirect_stdout
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest

from datasetlint import inspect
from datasetlint.__main__ import main


def clean():
    return {"schema_version": 1, "splits": {
        "train": [{"id": "a", "text": "one"}], "test": [{"id": "b", "text": "two"}]}}


class LintTests(unittest.TestCase):
    def test_clean_and_no_mutation(self):
        data = clean()
        original = copy.deepcopy(data)
        self.assertTrue(inspect(data)["passed"])
        self.assertEqual(data, original)

    def test_duplicate_and_overlap(self):
        data = clean()
        data["splits"]["train"].append({"id": "a", "text": "one"})
        data["splits"]["test"].append({"id": "a", "text": "one"})
        report = inspect(data)
        self.assertFalse(report["passed"])
        self.assertEqual({x["code"] for x in report["findings"]}, {"overlap_id", "overlap_text"})
        # Canonical split order means test is the first occurrence.
        self.assertTrue(all(x["first_split"] == "test" for x in report["findings"]))
        del data["splits"]["test"]
        self.assertEqual({x["code"] for x in inspect(data)["findings"]},
                         {"duplicate_id", "duplicate_text"})

    def test_text_overlap_with_different_ids(self):
        data = clean()
        data["splits"]["train"][0]["text"] = "two"
        self.assertEqual([x["code"] for x in inspect(data)["findings"]], ["overlap_text"])

    def test_matching_is_exact_and_reports_omit_content(self):
        data = clean()
        data["splits"]["train"][0]["text"] = " two "
        self.assertTrue(inspect(data)["passed"])
        data["splits"]["train"][0]["text"] = "two"
        self.assertNotIn('"two"', json.dumps(inspect(data)))

    def test_invalid_schema(self):
        for data in ({}, {"schema_version": True}, {"schema_version": 1, "splits": {}},
                     {"schema_version": 1, "splits": {"train": []}}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                inspect(data)
        for value in (None, 1, "", " "):
            data = clean()
            data["splits"]["train"][0]["text"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                inspect(data)

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.json"
            overlapping = clean()
            overlapping["splits"]["train"][0]["text"] = "two"
            for contents, expected in ((json.dumps(clean()), 0), (json.dumps(overlapping), 1),
                                       ('{"splits": {}, "splits": {}}', 2), ('{', 2)):
                path.write_text(contents, encoding="utf-8")
                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err):
                    self.assertEqual(main([str(path)]), expected)
                self.assertEqual(bool(err.getvalue()), expected == 2)
                if expected == 2:
                    self.assertEqual(out.getvalue(), "")
