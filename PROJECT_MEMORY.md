# PROJECT_MEMORY

## Decision Log

### 2026-02-09 - ZIP guardrails and nested-archive policy
- Decision: Enforce ZIP safety guardrails during archive processing using configurable limits for member count, per-member expanded bytes, total expanded bytes, and compression ratio.
- Decision: Treat nested ZIP members as risky by default (`nested_archive_policy=skip`) with an explicit opt-in to copy (`copy`).
- Why: Current ZIP processing previously allowed fully compressed/high-expansion payloads and nested bundles to pass through when unsupported-copy mode was enabled.
- Evidence:
  - Code: `src/file_sanitizer/sanitizer.py`, `src/file_sanitizer/cli.py`
  - Tests: `tests/test_sanitizer.py` (`test_zip_guardrail_*`, nested policy tests, dry-run parity, option validation)
  - Verification: `make check` (pass, `29 passed`)
  - Smoke: CLI run with fixture ZIP (`rc=0` normal, `rc=3` strict dry-run), CLI nested-copy policy run (`rc=0`)
- Commit: `91bee26b2077497ae508602ab755069c2fe4d3d3`
- Confidence: High
- Trust label: verified-local
- Follow-ups:
  - Add macro detection for Office docs and OOXML macro indicators.
  - Add warning taxonomy (`code` + `message`) for policy automation.
  - Add optional recursive nested sanitization with depth budget.

## Open Follow-ups
- Add risky-content policy mode (`warn` vs `block`) for PDF/ZIP findings.
- Add performance benchmark coverage for large ZIP and directory workloads.
