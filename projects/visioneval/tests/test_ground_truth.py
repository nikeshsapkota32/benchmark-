from copy import deepcopy
import hashlib
import json
import unittest

from visioneval.export import to_benchguard
from test_export import fixture


def fingerprint(data):
    return json.loads(to_benchguard(data)["protocol"])["ground_truth_sha256"]


class GroundTruthTests(unittest.TestCase):
    def test_changed_target_is_detected_even_when_scores_and_ids_match(self):
        baseline = fixture()
        candidate = deepcopy(baseline)
        candidate["records"][0].update(target="008", prediction="008")
        before, after = to_benchguard(baseline), to_benchguard(candidate)
        self.assertEqual(before["results"], after["results"])
        self.assertEqual(before["dataset_revision"], after["dataset_revision"])
        self.assertNotEqual(before["protocol"], after["protocol"])

    def test_order_model_predictions_and_extra_fields_do_not_change_fingerprint(self):
        baseline = fixture()
        original = deepcopy(baseline)
        candidate = deepcopy(baseline)
        candidate["records"].reverse()
        candidate["model"] = "another-model"
        for row in candidate["records"]:
            row["prediction"] = None
            row["private_note"] = "excluded from fingerprint"
        self.assertEqual(fingerprint(baseline), fingerprint(candidate))
        self.assertEqual(baseline, original)

    def test_label_to_id_association_and_leading_zeros_are_preserved(self):
        baseline = fixture()
        candidate = deepcopy(baseline)
        candidate["records"][0]["target"], candidate["records"][1]["target"] = (
            candidate["records"][1]["target"], candidate["records"][0]["target"])
        self.assertNotEqual(fingerprint(baseline), fingerprint(candidate))
        candidate = deepcopy(baseline)
        candidate["records"][0]["target"] = "7"
        self.assertNotEqual(fingerprint(baseline), fingerprint(candidate))

    def test_same_arithmetic_answer_with_changed_problem_is_detected(self):
        baseline = fixture("arithmetic")
        for operands, operation in (([4, 3], "+"), ([8, 1], "-"), ([7, 1], "*")):
            candidate = deepcopy(baseline)
            candidate["records"][0].update(operands=operands, operator=operation)
            self.assertEqual(to_benchguard(baseline)["results"], to_benchguard(candidate)["results"])
            self.assertNotEqual(fingerprint(baseline), fingerprint(candidate))

    def test_canonical_payload_is_documented_and_unicode_is_ascii_escaped(self):
        data = fixture()
        data["records"] = [{"id": "é", "target": "01", "prediction": None}]
        payload = b'{"kind":"digits","records":[{"id":"\\u00e9","target":"01"}],"schema_version":1}'
        self.assertEqual(fingerprint(data), hashlib.sha256(payload).hexdigest())
        data = fixture("arithmetic")
        data["records"] = [{"id": "a", "operands": [-10, 3], "operator": "+",
                            "target": -7, "prediction": None}]
        payload = b'{"kind":"arithmetic","records":[{"id":"a","operands":["-0xa","0x3"],"operator":"+","target":"-0x7"}],"schema_version":1}'
        self.assertEqual(fingerprint(data), hashlib.sha256(payload).hexdigest())

    def test_large_valid_arithmetic_integers_do_not_need_decimal_conversion(self):
        data = fixture("arithmetic")
        value = 10 ** 5000
        data["records"] = [{"id": "large", "operands": [value, 1], "operator": "+",
                            "target": value + 1, "prediction": None}]
        self.assertRegex(fingerprint(data), r"^[0-9a-f]{64}$")
