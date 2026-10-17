# Roadmap

- Implemented: digit exact match and edit-based error rate, integer arithmetic
  scoring with target consistency checks, missing-prediction accounting, CLI,
  and opt-in per-example status/error counts without copying raw record content.
- Next: explicit extraction policies for free-form VLM responses, with ambiguous
  outputs rejected instead of silently selecting a number.
- Review licenses before adding real handwritten-number fixtures or adapters.
- Add BenchGuard exports with pinned dataset/protocol and stable sample IDs.
- Evaluate paired uncertainty only with appropriate sample-level data.
