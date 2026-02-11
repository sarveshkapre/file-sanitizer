# INCIDENTS

## Incident Log

- 2026-02-11: No production reliability incidents or regressions were observed during this cycle.
  - Validation scope: local quality gate (`make check`) and CLI smoke runs for recursive nested ZIP sanitization and allowlist-by-detected-type behavior.
  - Prevention rules reaffirmed:
    - Treat content-type detection and allowlist behavior as one contract; enforce with mismatch regression tests.
    - Keep recursive nested archive processing bounded by explicit depth and aggregate-byte limits.

- 2026-02-09: No production reliability incidents or regressions were observed during this cycle.
  - Validation scope: local quality gate (`make check`) and CLI smoke runs for ZIP normal mode, strict dry-run mode, and nested-archive copy policy.
  - Prevention rules reaffirmed:
    - Keep ZIP guardrail checks before decompression whenever possible.
    - Maintain deterministic warning/report ordering to reduce CI noise and aid triage.
    - Require regression tests for every new safety control and CLI policy flag.
