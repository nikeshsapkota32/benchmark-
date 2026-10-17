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
model explanations need an explicit future extraction policy.

For arithmetic, each record also has two integer `operands` and `operator` of
`+`, `-` or `*`. Target must equal the computed result; inconsistent labels are
input errors. Prediction must be an integer or null. Booleans are rejected.
Exact-match accuracy reports correct answers against the validated targets.
No expression strings are executed. It does not assess reasoning steps or
separate recognition errors from arithmetic errors.

The JSON report retains run metadata and aggregate counts/scores. Exit 0 means
scoring completed, even for poor scores; exit 2 means invalid input/file error.
No pass/fail quality threshold or significance test is implied. The metadata is
supplied by the caller and its provenance is not verified. All example data is
synthetic. MIT licensed; developed with AI assistance.
