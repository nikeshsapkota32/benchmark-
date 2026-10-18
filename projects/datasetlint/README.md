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
`text` fields. Other record fields are ignored. By default, IDs and text match
exactly: whitespace, case and Unicode are not normalized. Duplicate JSON keys
are errors. Text-only whitespace matching is an explicit opt-in described below.

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

## Limit finding output without skipping validation

Highly duplicated data can produce more findings than records. Use
`--max-findings N` to retain only the first N findings in the usual deterministic
order, while still scanning and validating every record in every split:

```sh
datasetlint dataset.json --max-findings 100
datasetlint --split train=train.jsonl --split test=test.jsonl --max-findings 0
```

Both Python APIs accept `max_findings=N`. N must be a nonnegative integer;
zero returns summary metadata with an empty `findings` list. Omitting the option
(or using `None` in Python) preserves the existing unlimited report shape.
An explicit limit adds three fields to the report:

| Field | Meaning |
| --- | --- |
| `max_findings` | Requested maximum number of retained findings |
| `total_findings` | All duplicate/overlap occurrences found, including omitted findings |
| `findings_truncated` | Whether any findings were omitted from the list |

The total counts findings, not affected records: a repeated ID and repeated text
in the same record count separately. `passed` and exit status depend on the full
total, not the retained list. In particular, `--max-findings 0` still exits 1
when findings exist. A clean report has `total_findings: 0` and
`findings_truncated: false`, even with a zero limit.

The limit works with custom field names and text policies. JSONL hashes still
cover every input byte and retained findings keep their original file/line
locations. Invalid later records or empty later splits still cause exit 2 with
no partial report. Limiting findings bounds the retained finding list, **not**
the ID/text indexes, total input size or scan time. JSON-object mode still loads
the entire dataset; this is not a bounded-memory duplicate detection backend.

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
trimmed or normalized by default. Missing configured keys are errors; there is no automatic
fallback to `id`/`text`. Selected values must still be nonblank strings.

For a nondefault mapping, reports include
`"fields": {"id": "sample_id", "text": "prompt"}`. Finding codes continue to
describe the semantic role (`duplicate_id`, `overlap_text`, etc.), not the source
key. The default `id`/`text` mapping omits `fields`. Field names, but not record
values, are included in reports and validation diagnostics.

## Opt in to ASCII-whitespace text matching

Formatting differences can hide duplicate text. Both input modes support an
explicit, versioned matching policy:

```sh
datasetlint dataset.json --text-policy ascii-whitespace-v1
datasetlint --split train=train.jsonl --split test=test.jsonl --text-policy ascii-whitespace-v1
```

The Python APIs accept `text_policy="ascii-whitespace-v1"` as a keyword to
`inspect()` or `inspect_jsonl()`. The default `exact` policy leaves existing
matching and report shapes unchanged, even when selected explicitly.

`ascii-whitespace-v1` trims leading/trailing ASCII space, tab, CR, LF, vertical
tab and form feed, then replaces each internal run of those six characters
with one ASCII space. For example, `" alpha\t beta\n"` matches `"alpha beta"`.
Only the selected text field's matching key is transformed. IDs, field names,
split names, input records and files are never rewritten or normalized. This
also works with `--text-field prompt` or other explicit field mappings.

Reports include `"text_policy": "ascii-whitespace-v1"`, including clean reports.
`duplicate_text` and `overlap_text` now mean equality **under this policy**, not
necessarily identical raw text. Finding locations still point to original
records and their first matching occurrence. ID findings retain exact equality.
JSONL `source_sha256` still hashes the original file bytes, not normalized text;
the same files have the same hashes regardless of matching policy. Neither raw
nor normalized record text is copied into reports.

Case, punctuation, Unicode composition, nonbreaking/em spaces and zero-width
characters are not normalized. `"alphabeta"` does not match `"alpha beta"`.
Existing nonblank-string validation applies before matching; blank values and
malformed later records still abort without a partial report. Unknown policies
are errors. This policy may remove meaningful formatting, particularly in code
or structured text, so inspect findings before deciding whether examples are
duplicates. A match is a review signal, not proof of semantic equivalence or
training-data leakage. No fuzzy matching or automatic deduplication is done.

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
loading all input records, but retains ID/text matching indexes and findings in
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
