# VisionEval

Score saved handwritten-digit or arithmetic/VLM predictions offline. This tool
evaluates prediction files; it does not read images or run a vision model.
Python 3.10+, no runtime dependencies.

```sh
python -m pip install -e .
visioneval examples/digits.json
visioneval examples/arithmetic.json
PYTHONPATH=src python -m unittest discover -s tests -v
```

Input requires integer `schema_version: 1`, nonblank `model`, `dataset_revision`
and `protocol` strings, `kind` (`digits` or `arithmetic`), and a nonempty `records`
list. Every record requires a unique nonblank string `id`, a `target` and an
explicit `prediction`. Use null for missing predictions; they remain in the
denominator. Duplicate JSON keys and duplicate IDs are rejected.

For digits, target is a nonempty ASCII digit string. Prediction is an ASCII
digit string (possibly empty) or null. Leading zeros matter. Exact-match accuracy
counts whole correct strings. Character error rate is summed Levenshtein edit
distance divided by summed target digits, accounting for insertions, deletions
and substitutions. This rate can exceed 1; it is not a positionwise accuracy.
Empty predictions count as missing. Non-ASCII numeral scripts and free-form
model explanations are not supported.

The edit-distance implementation skips exact matches and empty strings, trims
shared prefixes/suffixes, and keeps dynamic-programming rows on the shorter
remaining string. These are exact optimizations, not approximate matching or
normalization: leading zeros and insertion/deletion/substitution costs are
unchanged. Long dissimilar strings can still take quadratic time. Working rows
scale with the shorter residual string; input records and sliced strings still
consume memory. No total-memory or model-inference speed claim is implied.

For arithmetic, each record also has two integer `operands` and `operator` of
`+`, `-` or `*`. Target must equal the computed result; inconsistent labels are
input errors. Prediction must be an integer or null. Booleans are rejected.
Exact-match accuracy reports correct answers against the validated targets.
No expression strings are executed. It does not assess reasoning steps or
separate recognition errors from arithmetic errors.

## Inspect arithmetic accuracy by operator

```sh
visioneval examples/arithmetic.json --by-operator
```

The Python API is `evaluate(data, by_operator=True)`. This adds an
`operator_breakdown` object to arithmetic JSON reports. For each operator
present in the input, in `+`, `-`, `*` order, it records `samples`, `correct`,
`missing` and `exact_match`. Each operator's exact match is its correct count
divided by all records using that operator, including missing predictions.
Operators with no records are omitted; a zero score is not reported for an
unevaluated operator. The counts across operators add up to the report's
overall counts. The overall exact match remains correct predictions divided
by **all** records, not an unweighted average of operator scores.

This option works with `--details` and `--response-policy numeric-text-v1`.
Invalid responses or inconsistent arithmetic targets still abort with exit 2
and no partial report. The default report shape is unchanged; `--by-operator`
requires arithmetic input and cannot be combined with `--format benchguard`.
The BenchGuard export continues to contain only overall arithmetic exact match.
The breakdown contains counts and rates, not record IDs, operands, predictions,
targets or explanation text. It is a diagnostic for the supplied mix of problems,
not a normalized comparison across datasets with different operator mixes.

## Opt in to whole-response numeric text

The default `strict` policy retains the types and exact matching above. For
saved model responses consisting only of a numeric answer, explicitly select:

```sh
visioneval examples/numeric-responses.json --response-policy numeric-text-v1 --details
```

The Python equivalent is `evaluate(data, response_policy="numeric-text-v1")`.
In this mode every prediction must be a string or null, including arithmetic
answers. Only leading/trailing ASCII whitespace (space, tab, CR, LF, vertical tab
and form feed) is removed. Null or a blank response counts as missing and remains
in the denominator. Targets are never normalized; arithmetic labels still must
agree with their operands/operator.

Digit responses must contain only ASCII digits after trimming: `" 007\n"`
becomes `"007"`, not `"7"`. Arithmetic responses allow one optional ASCII `+`
or `-` followed by digits: `" +003 "` becomes integer 3 and `"-0"` becomes 0.
Arithmetic response strings are limited to 1000 digits before integer conversion.
This is whole-response parsing, not a search for a plausible answer. Explanations,
multiple answers, expressions, decimal/scientific notation, grouping separators,
Markdown fences, Unicode digits and Unicode whitespace are rejected.

A rejected response aborts the entire evaluation with exit 2 and no partial
report; the error identifies its zero-based record index without echoing its
content. It is not silently counted as missing or scored as wrong. This policy
therefore requires a numeric-output protocol, not arbitrary free-form VLM output.
Do not drop rejected records to obtain a score: that would change the evaluation
set. Keep the original responses and choose/document an appropriate protocol.

Opt-in reports include `"response_policy": "numeric-text-v1"`; default strict
reports are unchanged. Compare runs only with the same response policy and pin
it in the caller-supplied `protocol` as well. This versioned policy is distinct
from model accuracy. The bundled response example is synthetic, not inference
output, and scores one correct answer and one missing answer out of two.

## Inspect per-example outcomes

```sh
visioneval examples/digits.json --details
```

The Python equivalent is `evaluate(data, include_details=True)`. Default reports
remain aggregate-only. With the option enabled, a `details` list follows input
record order. Each entry has a zero-based `index` into the original `records`
array and a `status`: `correct`, `incorrect` or `missing`. For digits, it also
includes `digit_edit_errors` and `target_digits`. Those counts sum to the report's
aggregate counts. Missing digit predictions (null or empty) count as deleting
every target digit. Arithmetic details contain only index and status; integer
zero is a valid prediction, not a missing value.

Details omit record IDs, targets, predictions, operands, image paths and extra
record fields. Use the index to inspect the original file locally. Indices are
only meaningful for that file's ordering and must not be used to pair reordered
runs. Reports still include caller-supplied model/dataset/protocol metadata,
lengths and outcomes; this is not anonymization. Review reports before sharing.
All records must validate before any output is printed, even in details mode.

## Export a BenchGuard run

Use the opt-in export to gate saved evaluations with BenchGuard:

```sh
visioneval baseline-predictions.json --format benchguard > baseline-run.json
visioneval candidate-predictions.json --format benchguard > candidate-run.json
benchguard baseline-run.json candidate-run.json --tolerance 0.01
```

BenchGuard is installed separately; VisionEval does not import it or execute
it. The Python API is `from visioneval.export import to_benchguard`, followed by
`to_benchguard(data, response_policy="strict")`. The default CLI `--format json`
and `evaluate()` reports are unchanged. `--details` cannot be combined with
`--format benchguard`. Use output paths distinct from prediction inputs: shell
redirection can truncate a file before the evaluator starts.

Export schema version 1 retains the caller's model and dataset revision. Task
names are `visioneval/digits` and `visioneval/arithmetic`. Both export
`exact_match` (higher is better); digits also export `character_error_rate`
(lower is better, not clipped to 1). Every metric includes all evaluated record
IDs as `sample_ids` and the number of records as `samples`, including missing
predictions. For character error rate, `samples` still counts records; the score
denominator remains total target digits, not record count. BenchGuard checks
sample-ID sets independently of record order.

The exported protocol string is compact, key-sorted, ASCII-escaped JSON with
`export: "visioneval-benchguard-v2"`, `kind`, the original `protocol`, the
explicit `response_policy` (including `strict`), and `ground_truth_sha256`.
This prevents accidental
comparisons across evaluator kinds or response policies even if the caller's
protocol was not updated. Model identifiers may differ across a comparison.
Pin dataset revisions and include prompt, sampling and inference settings in
the original protocol; the exporter cannot verify that metadata. Exported scores are deterministic
aggregates, not statistical significance estimates.

The ground-truth fingerprint detects changed targets behind reused IDs and
dataset revisions, even when the aggregate scores stay the same. For arithmetic
it also pins the ordered operands and operator, so different problems with the
same answer are not treated as the same evaluation set. Input record ordering,
model name, predictions and extra record fields do not affect the fingerprint.
IDs and digit targets are preserved exactly, including Unicode IDs and leading
zeros. No Unicode normalization is applied.

The SHA-256 input is ASCII-encoded, key-sorted compact JSON (separators `,` and
`:`; `ensure_ascii=True`) containing `schema_version: 1`, `kind`, and `records`
sorted by their ID strings. Each digit record contains only `id` and `target`.
Each arithmetic record contains `id`, `target`, `operands` and `operator`;
all arithmetic integers are represented using Python's lowercase `hex()` string
format, including `0x` and any leading minus sign. This avoids decimal conversion
limits for large integers. This hash identifies reported ground truth, not the
underlying images, input data, provenance or correctness of labels. It is not
encryption and does not make small, guessable labels private.

Protocol v2 exports intentionally do not compare with older v1 exports. Re-export
both baseline and candidate with the same version; do not strip the fingerprint
to bypass a mismatch. The BenchGuard input `schema_version` remains 1, and the
normal VisionEval JSON reports and metric definitions are unchanged.

Unlike the normal report, **exports contain raw sample IDs**. They omit targets,
predictions, operands and extra record fields, but are not anonymized. Use stable
non-sensitive dataset IDs and review exports before sharing. All records must
validate before an export is emitted; no rejected record is silently dropped.
Exit 0 only means the export succeeded. The subsequent BenchGuard command makes
the pass/fail decision; no inference or hardware benchmark is performed here.

The normal JSON report retains run metadata and aggregate counts/scores. Exit 0 means
scoring completed, even for poor scores; exit 2 means invalid input/file error.
No pass/fail quality threshold or significance test is implied. The metadata is
supplied by the caller and its provenance is not verified. All example data is
synthetic. MIT licensed; developed with AI assistance.
