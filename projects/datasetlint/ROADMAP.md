# Roadmap

- Implemented: schema validation, exact ID/text duplicates, split overlap, JSON
  CLI reports, exit codes and standard-library tests. JSONL files are read one
  record at a time with deterministic file/line locations and strict errors.
- Implemented: explicit top-level ID/text field selection for JSON and JSONL,
  with mapping metadata and unchanged default reports.
- Next: opt-in normalization policies with explicit report metadata.
- Consider disk-backed duplicate indexes and finding output for large datasets;
  the JSONL reader alone does not provide bounded-memory duplicate detection.
- Implemented: SHA-256 hashes of the exact JSONL bytes consumed during validation.
- Add format adapters only with documented licensed fixtures.
- Evaluate approximate duplicate detection separately; never silently equate a
  fuzzy match with proven leakage.
