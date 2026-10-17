# Roadmap

- Implemented: schema validation, exact ID/text duplicates, split overlap, JSON
  CLI reports, exit codes and standard-library tests.
- Next: streaming JSONL inputs with deterministic file/line locations and tests.
- Add explicit configurable field names and opt-in normalization policies.
- Add source hashes and format adapters only with documented licensed fixtures.
- Evaluate approximate duplicate detection separately; never silently equate a
  fuzzy match with proven leakage.
