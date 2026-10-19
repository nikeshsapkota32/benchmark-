# Roadmap

- Implemented: schema validation, exact ID/text duplicates, split overlap, JSON
  CLI reports, exit codes and standard-library tests. JSONL files are read one
  record at a time with deterministic file/line locations and strict errors.
- JSONL split files are opened sequentially, with at most one input file open
  at a time and explicit cleanup on validation/read failures. Hashes and finding
  order are unchanged; later file errors still prevent any partial report.
- JSON and JSONL file parsers consistently reject nonstandard NaN/Infinity
  constants even in ignored fields; quoted strings and valid extras are unchanged.
- Decoder nesting-limit failures become normal input errors in both file modes,
  with JSONL file/line diagnostics and no partial reports. No recursion-limit
  changes or fixed resource bounds are implied.
- Implemented: explicit top-level ID/text field selection for JSON and JSONL,
  with mapping metadata and unchanged default reports.
- Implemented: opt-in `ascii-whitespace-v1` text matching with explicit policy
  metadata. IDs and source hashes stay exact; default reports remain unchanged.
- Any broader normalization needs a separately versioned, reviewed policy.
- Implemented: opt-in finding limits with full totals and explicit truncation;
  validation and source hashing continue through all records. Zero retained
  findings never suppresses a failing audit. Default reports are unchanged.
- Implemented: opt-in temporary SQLite exact-match indexes for JSON and JSONL,
  preserving reports and validation while moving unique keys out of Python
  dictionaries. Pair JSONL with a finding limit; total memory is not guaranteed.
- Implemented: reproducible Linux-only synthetic profiling script with separate
  worker processes, peak process RSS, elapsed scan time, source/code hashes and
  complete backend-report equivalence checks. One host's raw trials are recorded.
- Implemented: Linux filesystem input/output counter deltas around each profile
  scan, including cleanup, with documented units and valid zero observations.
  These are not byte counts, syscall counts or physical-device measurements.
- Next: characterize disk space and representative workloads on more hosts;
  consider streaming finding output separately. Do not generalize one host's RSS.
- Implemented: SHA-256 hashes of the exact JSONL bytes consumed during validation.
- Add format adapters only with documented licensed fixtures.
- Evaluate approximate duplicate detection separately; never silently equate a
  fuzzy match with proven leakage.
