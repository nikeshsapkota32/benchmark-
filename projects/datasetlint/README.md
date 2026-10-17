# DatasetLint

Check a small text dataset for reused IDs and exact duplicate text within or
across named splits. Runs offline with Python 3.10+ and no runtime dependencies.

```sh
python -m pip install -e .
datasetlint examples/overlap.json
PYTHONPATH=src python -m unittest discover -s tests -v
```

The synthetic example deliberately contains overlap and exits with 1.

Input is a JSON object with integer `schema_version: 1` and a nonempty `splits`
object. Each split is a nonempty list of objects with nonblank string `id` and
`text` fields. Other record fields are ignored. IDs and text match exactly:
whitespace, case and Unicode are not normalized. Duplicate JSON keys are errors.

```json
{"schema_version":1,"splits":{
  "train":[{"id":"a","text":"Example sentence"}],
  "test":[{"id":"b","text":"Example sentence"}]
}}
```

The JSON report contains counts and findings referring to zero-based record
positions, without copying record IDs or text. Splits are visited in sorted
name order. Each repeated value points to its first occurrence: a reference in
the same split is `duplicate_id`/`duplicate_text`, otherwise it is
`overlap_id`/`overlap_text`. It reports repeated occurrences, not every pair.
Split names remain visible in reports.

## Explicit field names

For exports using other keys, select the ID and text fields without rewriting
the records. Both JSON and JSONL modes accept the same options:

```sh
datasetlint exported.json --id-field sample_id --text-field prompt
datasetlint --split train=exported.jsonl --id-field sample_id --text-field prompt
```

The Python APIs `inspect(dataset, id_field="sample_id", text_field="prompt")`
and `inspect_jsonl(splits, id_field="sample_id", text_field="prompt")` use the
same mapping. Field names must be distinct, nonblank strings and are literal
top-level keys: dots do not select nested properties. Names and values are not
trimmed or normalized. Missing configured keys are errors; there is no automatic
fallback to `id`/`text`. Selected values must still be nonblank strings.

For a nondefault mapping, reports include
`"fields": {"id": "sample_id", "text": "prompt"}`. Finding codes continue to
describe the semantic role (`duplicate_id`, `overlap_text`, etc.), not the source
key. The default `id`/`text` mapping omits `fields`. Field names, but not record
values, are included in reports and validation diagnostics.

## JSONL files

For separate split files, use one JSON object per UTF-8 line with the same `id`
and `text` fields. No enclosing `schema_version`/`splits` wrapper is needed:

```sh
datasetlint --split train=examples/train.jsonl --split test=examples/test.jsonl
```

Repeat `--split NAME=PATH` for each split. Names must be unique, and JSON and
JSONL input modes cannot be combined. Paths may contain `=`; quote paths with
spaces as needed. The Python API is `datasetlint.jsonl.inspect_jsonl`, accepting
a dictionary of split names to paths.

Files are read one record at a time. Findings retain zero-based indices and add
`path`, `line`, `first_path` and `first_line`; line numbers are one-based physical
lines. Blank lines, invalid UTF-8/JSON, duplicate JSON keys and empty files are
errors. A final newline is optional. Parsing and record-schema errors identify
the file and line without copying record content. File paths are visible in
reports and diagnostics; review them before sharing.

All files must validate before any report is printed. A malformed later line
returns exit 2 even if earlier records already revealed overlap. JSONL avoids
loading all input records, but retains exact ID/text indexes and findings in
memory; memory usage still grows with unique content and finding count.

JSONL reports also include `source_sha256`, mapping each split name to the
SHA-256 of the exact file bytes consumed by the parser. Hashing happens in the
same pass as validation, without reopening or loading the entire file. This
identifies sources even when a report has no duplicate findings. Whitespace,
record order, line endings and the presence of a final newline affect the hash.
Identical bytes at different paths have the same hash. All files must validate
before hashes or findings are returned; malformed input produces no partial
audit. The JSON-object API does not include file hashes.

Hashes identify the bytes read, not dataset provenance, privacy or a verified
snapshot of a file being modified concurrently. Keep source files stable during
inspection. They do not prove that a model trained on or evaluated these files.

Exit codes: 0 clean, 1 duplicate/overlap findings, 2 malformed input/file error.
An exact match is a reason to investigate leakage, not proof that leakage has
occurred. The tool cannot find paraphrases, image duplicates or train/test
contamination absent from these files. The original JSON-object input loads the
whole dataset. Both input modes retain the duplicate indexes in memory.

MIT licensed. Developed with AI assistance. All shipped examples are synthetic.
