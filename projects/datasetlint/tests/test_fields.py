from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from datasetlint import inspect
from datasetlint.__main__ import main
from datasetlint.jsonl import inspect_jsonl


class FieldMappingTests(unittest.TestCase):
    def setUp(self):
        self.options = {"id_field": "sample_id", "text_field": "prompt"}
        self.data = {"schema_version": 1, "splits": {
            "train": [{"sample_id": "private-a", "prompt": "private-text"}] * 2,
            "test": [{"sample_id": "private-b", "prompt": "private-text"}]}}
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_custom_fields_preserve_semantic_codes_and_input(self):
        original = deepcopy(self.data)
        report = inspect(self.data, **self.options)
        self.assertEqual(self.data, original)
        self.assertEqual(report["fields"], {"id": "sample_id", "text": "prompt"})
        self.assertEqual(report["counts"], {"test": 1, "train": 2})
        self.assertEqual([item["code"] for item in report["findings"]],
                         ["overlap_text", "duplicate_id", "overlap_text"])
        self.assertFalse(report["passed"])
        self.assertNotIn("private-", json.dumps(report))

    def test_jsonl_custom_fields_match_json_and_keep_locations(self):
        paths = {}
        for split, rows in self.data["splits"].items():
            paths[split] = self.root / (split + ".jsonl")
            paths[split].write_text("\n".join(map(json.dumps, rows)), encoding="utf-8")
        report = inspect_jsonl(paths, **self.options)
        self.assertEqual(set(report.pop("source_sha256")), set(paths))
        expected = inspect(self.data, **self.options)
        for finding in report["findings"]:
            self.assertEqual(finding.pop("path"), str(paths[finding["split"]]))
            self.assertEqual(finding.pop("line"), finding["index"] + 1)
            self.assertEqual(finding.pop("first_path"), str(paths[finding["first_split"]]))
            self.assertEqual(finding.pop("first_line"), finding["first_index"] + 1)
        self.assertEqual(report, expected)

    def test_default_report_is_unchanged(self):
        data = {"schema_version": 1, "splits": {"train": [{"id": "a", "text": "one"}]}}
        expected = {"schema_version": 1, "passed": True, "counts": {"train": 1}, "findings": []}
        self.assertEqual(inspect(data), expected)
        self.assertEqual(inspect(data, id_field="id", text_field="text"), expected)

    def test_invalid_fields_fail_before_jsonl_opens_files(self):
        cases = [(value, "text") for value in (None, 1, True, [], "", " \n")]
        cases += [("id", value) for value in (None, 1, True, [], "", " \n")]
        cases += [("same", "same")]
        for id_field, text_field in cases:
            with self.subTest(id_field=id_field, text_field=text_field):
                options = {"id_field": id_field, "text_field": text_field}
                with self.assertRaises(ValueError):
                    inspect(self.data, **options)
                with patch.object(Path, "open") as opened, self.assertRaises(ValueError):
                    inspect_jsonl({"train": self.root / "missing.jsonl"}, **options)
                opened.assert_not_called()

    def test_configured_fields_do_not_fall_back_to_defaults(self):
        row = {"id": "a", "text": "one", "sample_id": "b", "prompt": "two"}
        for field in ("sample_id", "prompt"):
            for value in (None, "", 3):
                with self.subTest(field=field, value=value):
                    invalid = dict(row, **{field: value})
                    data = {"schema_version": 1, "splits": {"train": [invalid]}}
                    with self.assertRaisesRegex(ValueError, field):
                        inspect(data, **self.options)
            invalid = {key: value for key, value in row.items() if key != field}
            with self.assertRaisesRegex(ValueError, field):
                inspect({"schema_version": 1, "splits": {"train": [invalid]}}, **self.options)

    def test_keys_are_literal_and_roles_can_be_swapped(self):
        for id_field, text_field in (("meta.id", "प्रश्न"), ("text", "id"), (" id ", " text ")):
            with self.subTest(id_field=id_field, text_field=text_field):
                data = {"schema_version": 1, "splits": {"train": [
                    {id_field: "a", text_field: "same"}, {id_field: "b", text_field: "same"}]}}
                report = inspect(data, id_field=id_field, text_field=text_field)
                self.assertEqual([item["code"] for item in report["findings"]], ["duplicate_text"])

    def test_cli_mapping_in_both_modes_and_validation_errors(self):
        json_path = self.root / "data.json"
        json_path.write_text(json.dumps(self.data), encoding="utf-8")
        jsonl_path = self.root / "train.jsonl"
        jsonl_path.write_text("\n".join(map(json.dumps, self.data["splits"]["train"])), encoding="utf-8")
        for args in ([str(json_path)], ["--split", f"train={jsonl_path}"]):
            for flags, code in ((["--id-field", "sample_id", "--text-field", "prompt"], 1),
                                (["--id-field", "same", "--text-field", "same"], 2),
                                (["--id-field", "missing"], 2)):
                with self.subTest(args=args, flags=flags):
                    out, err = io.StringIO(), io.StringIO()
                    with redirect_stdout(out), redirect_stderr(err):
                        self.assertEqual(main(args + flags), code)
                    if code == 1:
                        self.assertEqual(json.loads(out.getvalue())["fields"],
                                         {"id": "sample_id", "text": "prompt"})
                        self.assertEqual(err.getvalue(), "")
                    else:
                        self.assertEqual(out.getvalue(), "")
                        self.assertTrue(err.getvalue())
