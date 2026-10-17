# Roadmap

- Implemented: digit exact match and edit-based error rate, integer arithmetic
  scoring with target consistency checks, missing-prediction accounting, CLI,
  and opt-in per-example status/error counts without copying raw record content.
- Implemented: opt-in `numeric-text-v1` whole-response parsing, preserving digit
  leading zeros, recording the policy and rejecting ambiguous text without a
  partial report. Strict typed predictions remain the default.
- Next: reviewed format adapters; broader response policies require a defined
  protocol and explicit accounting for unparseable responses, not answer guessing.
- Review licenses before adding real handwritten-number fixtures or adapters.
- Implemented: opt-in BenchGuard saved-run exports with metric directions,
  stable sample IDs and versioned protocol encoding that pins kind and response
  policy. Input metadata remains caller-supplied, not verified provenance.
- Evaluate paired uncertainty only with appropriate sample-level data.
