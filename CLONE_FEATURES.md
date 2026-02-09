# Clone Feature Tracker

## Context Sources
- README and docs
- TODO/FIXME markers in code
- Test and build failures
- Gaps found during codebase exploration

## Candidate Features To Do
- [ ] P0: Add Office document macro detection (`.docm/.xlsm/.pptm`) with clear warning taxonomy in the JSONL report.
- [ ] P0: Add nested-archive guardrails (depth/expanded-size/member-count limits) to reduce zip-bomb risk.
- [ ] P1: Add policy mode for risky content (`warn` vs `block`) for PDF/ZIP active-content findings.
- [ ] P1: Add perf/regression benchmark job for large directory + large ZIP runs.

## Implemented
- [x] 2026-02-09: Added ZIP archive sanitization support for `.zip` inputs.
  Evidence: `src/file_sanitizer/sanitizer.py`, `tests/test_sanitizer.py`.
- [x] 2026-02-09: Hardened ZIP member handling for unsafe paths, symlinks, encrypted members, and duplicates (warning + skip).
  Evidence: `src/file_sanitizer/sanitizer.py`, `tests/test_sanitizer.py`, `tests/test_fixtures.py`.
- [x] 2026-02-09: Made directory and ZIP member processing deterministic for stable report ordering.
  Evidence: `src/file_sanitizer/sanitizer.py`, `tests/test_sanitizer.py`.
- [x] 2026-02-09: Added committed fixture corpus and fixture-backed regression tests.
  Evidence: `tests/fixtures/exif-photo.jpg`, `tests/fixtures/risky.pdf`, `tests/fixtures/mixed-bundle.zip`, `tests/test_fixtures.py`.
- [x] 2026-02-09: Updated product docs and release memory for current behavior.
  Evidence: `README.md`, `PLAN.md`, `ROADMAP.md`, `CHANGELOG.md`, `UPDATE.md`.
- [x] 2026-02-09: Verification evidence captured.
  Commands:
  - `make check` -> pass (`21 passed`, mypy/ruff/build clean).
  - `.venv/bin/python -m file_sanitizer sanitize --input tests/fixtures/mixed-bundle.zip --out "$tmpdir/out" --report "$tmpdir/report.jsonl" --report-summary` -> pass (`rc=0`, `zip_sanitized: 1`, output ZIP entries: `docs/readme.txt`, `images/exif-photo.jpg`, `pdfs/risky.pdf`).
  - `.venv/bin/python -m file_sanitizer sanitize --input tests/fixtures/mixed-bundle.zip --out "$tmpdir/out" --report "$tmpdir/report.jsonl" --dry-run --fail-on-warnings` -> expected strict failure (`rc=3`, `would_zip_sanitize: 1`).

## Insights
- Deterministic iteration improves CI reproducibility and reduces flaky report diffs.
- ZIP sanitization is only as safe as member policy; warning+skip for unsafe members is required even in metadata-focused tools.
- Fixture-backed binary tests catch parser/serialization regressions that synthetic-only tests may miss.

## Notes
- This file is maintained by the autonomous clone loop.
