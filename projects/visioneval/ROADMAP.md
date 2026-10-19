# Roadmap

- Implemented: digit exact match and edit-based error rate, integer arithmetic
  scoring with target consistency checks, missing-prediction accounting, CLI,
  and opt-in per-example status/error counts without copying raw record content.
- Implemented: strict file parsing rejects nonstandard NaN/Infinity constants,
  including in ignored fields, before normal reporting or BenchGuard export.
- Implemented: JSON decoder nesting-limit failures return input-error exit 2
  without a traceback, partial report or export; supported nested extras remain
  ignored. No fixed nesting limit or resource bound is implied.
- Implemented: opt-in `numeric-text-v1` whole-response parsing, preserving digit
  leading zeros, recording the policy and rejecting ambiguous text without a
  partial report. Strict typed predictions remain the default.
- Implemented: opt-in `numeric-text-count-v1` retains unparseable text responses
  in all scoring denominators, separates them from missing answers, and reports
  counts/rates overall, by operator and in BenchGuard exports. The versioned
  policy specifies no-extracted-answer penalties; no answer guessing is used.
- Next: reviewed format adapters; any broader extraction grammar requires a
  separate defined protocol and explicit unparseable-response accounting.
- Review licenses before adding real handwritten-number fixtures or adapters.
- Implemented: opt-in BenchGuard saved-run exports with metric directions,
  stable sample IDs and versioned protocol encoding that pins kind and response
  policy. Input metadata remains caller-supplied, not verified provenance.
- Implemented: export protocol v2 fingerprints targets associated with sample IDs
  and arithmetic operands/operator, independent of record order. Re-export both
  sides when migrating from v1. Image/input-content verification remains outside
  this reported-ground-truth check.
- Implemented: opt-in arithmetic operator breakdown with counts, missing
  predictions and exact match for each operator present. Overall scoring and
  BenchGuard exports remain aggregate only.
- Evaluate paired uncertainty only with appropriate sample-level data.
- Implemented: exact edit-distance fast paths and common-end trimming, with
  shorter residual working rows. Exhaustive short-string and seeded oracle tests
  preserve scoring semantics; long dissimilar inputs remain quadratic-time.
