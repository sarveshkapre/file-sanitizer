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

### 2026-02-09 - Structured warning codes, Office macro signals, and risky-policy block mode
- Decision: Switch JSONL report warnings from free-form strings to structured objects with `code` and `message`.
- Decision: Add Office macro warnings for macro-enabled OOXML extensions and `vbaProject.bin` indicators, including within ZIP members.
- Decision: Add `--risky-policy {warn,block}`; when set to `block`, skip writing outputs for risky PDFs and ZIPs (report action `blocked`).
- Why: Makes findings machine-actionable, improves auditability, and lets users enforce trust gates without relying on brittle string matching.
- Evidence:
  - Code: `src/file_sanitizer/sanitizer.py`, `src/file_sanitizer/cli.py`
  - Tests: `tests/test_sanitizer.py`, `tests/test_fixtures.py`, `tests/test_smoke.py`
  - Verification: `make check` (pass, `35 passed`)
  - Smoke: `.venv/bin/python -m file_sanitizer sanitize --input tests/fixtures/mixed-bundle.zip --out "$tmpdir/out" --report "$tmpdir/report.jsonl" --report-summary` (pass, `rc=0`, warnings are structured as `code` + `message`)
  - Smoke: `.venv/bin/python -m file_sanitizer sanitize --input tests/fixtures/mixed-bundle.zip --out "$tmpdir/out" --report "$tmpdir/report.jsonl" --risky-policy block` (expected block, `rc=2`, `action=blocked`)
- Commits:
  - Structured warning objects: `75c50a4dcd1a8de77b5bf0eb84b6678404c6ae92`
  - Office macro warnings: `2b81c82e5c1c8a3429c8cfe2ac0db85c746d1cc5`
  - Risky-policy block mode: `dc6734107354418dba5955b4384a0d9793db59a3`
- Confidence: High
- Trust label: verified-local
- Follow-ups:
  - Document the report schema/warning codes as a stable contract (and optionally ship a JSON Schema).
  - Add content-type sniffing to reduce extension-based misclassification.

## Open Follow-ups
- Document the report schema/warning codes as a stable contract (and optionally ship a JSON Schema).
- Add content-type sniffing to reduce extension-based misclassification.
- Add performance benchmark coverage for large ZIP and directory workloads.
- Add optional recursive nested-archive sanitization with a depth budget.
