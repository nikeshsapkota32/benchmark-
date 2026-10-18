from copy import deepcopy
from itertools import product
import random
import unittest

from visioneval import edit_distance, evaluate
from visioneval.export import to_benchguard
from test_scoring import data


def reference(a, b):
    """Small full-matrix oracle, deliberately without trimming or symmetry swaps."""
    matrix = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        matrix[i][0] = i
    for j in range(len(b) + 1):
        matrix[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            matrix[i][j] = min(matrix[i - 1][j] + 1, matrix[i][j - 1] + 1,
                               matrix[i - 1][j - 1] + (a[i - 1] != b[j - 1]))
    return matrix[-1][-1]


class EditDistanceTests(unittest.TestCase):
    def test_exhaustive_short_strings_match_full_matrix_oracle(self):
        strings = ["".join(chars) for size in range(5) for chars in product("012", repeat=size)]
        for a in strings:
            for b in strings:
                self.assertEqual(edit_distance(a, b), reference(a, b), (a, b))

    def test_seeded_random_strings_and_shared_ends_match_oracle(self):
        rng = random.Random(31)
        for _ in range(150):
            a = "".join(rng.choices("0123456789", k=rng.randrange(25)))
            b = "".join(rng.choices("0123456789", k=rng.randrange(25)))
            for left, right in ((a, b), ("000" + a + "99", "000" + b + "99")):
                self.assertEqual(edit_distance(left, right), reference(left, right))
                self.assertEqual(edit_distance(right, left), reference(left, right))

    def test_long_exact_missing_and_near_matches(self):
        zeros = "0" * 10000
        for a, b, expected in ((zeros, zeros, 0), (zeros, "", 10000), ("", zeros, 10000),
                               (zeros, zeros[:5000] + "1" + zeros[5001:], 1),
                               (zeros, zeros + "1", 1), ("1" + zeros, zeros, 1),
                               (zeros + "12", zeros + "21", 2)):
            with self.subTest(expected=expected, lengths=(len(a), len(b))):
                self.assertEqual(edit_distance(a, b), expected)

    def test_asymmetric_lengths_and_nonpositional_edits(self):
        for a, b in (("1", "2" * 1000), ("00123", "0123"), ("012", "120"),
                     ("0000001", "1000000"), ("012345", "543210")):
            expected = reference(a, b)
            self.assertEqual(edit_distance(a, b), expected)
            self.assertEqual(edit_distance(b, a), expected)

    def test_scores_details_and_exports_preserve_metric_semantics(self):
        item = data()
        pairs = [("000123", "000123"), ("012", "120"), ("1", "1111"),
                 ("123", None), ("0002", "000")]
        item["records"] = [{"id": str(i), "target": target, "prediction": prediction}
                           for i, (target, prediction) in enumerate(pairs)]
        original = deepcopy(item)
        expected_edits = [reference(target, prediction or "") for target, prediction in pairs]
        report = evaluate(item, include_details=True)
        self.assertEqual(report["digit_edit_errors"], sum(expected_edits))
        self.assertEqual([row["digit_edit_errors"] for row in report["details"]], expected_edits)
        self.assertEqual(report["target_digits"], sum(len(target) for target, _ in pairs))
        self.assertEqual(report["missing"], 1)
        self.assertEqual(report["exact_match"], 1 / len(pairs))
        exported = to_benchguard(item)
        metrics = {row["metric"]: row["value"] for row in exported["results"]}
        self.assertEqual(metrics["character_error_rate"], sum(expected_edits) / report["target_digits"])
        self.assertEqual(metrics["exact_match"], report["exact_match"])
        self.assertEqual(item, original)

    def test_fast_paths_do_not_bypass_input_validation(self):
        for target, prediction in (("not digits", "not digits"), ("", ""), ("१२", "१२")):
            item = data()
            item["records"][0].update(target=target, prediction=prediction)
            with self.assertRaises(ValueError):
                evaluate(item)
