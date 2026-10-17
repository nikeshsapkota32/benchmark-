# Roadmap

- Implemented: schema validation, exact ID/text duplicates, split overlap, JSON
  CLI reports, exit codes and standard-library tests. JSONL files are read one
  record at a time with deterministic file/line locations and strict errors.
- Next: explicit configurable field names and opt-in normalization policies.
- Consider disk-backed duplicate indexes and finding output for large datasets;
  the JSONL reader alone does not provide bounded-memory duplicate detection.
- Add source hashes and format adapters only with documented licensed fixtures.
- Evaluate approximate duplicate detection separately; never silently equate a
  fuzzy match with proven leakage.
