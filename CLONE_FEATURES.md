# Clone Feature Tracker

## Context Sources
- README and docs
- TODO/FIXME markers in code
- Test and build failures
- Gaps found during codebase exploration

## Candidate Features To Do
- [ ] P0 (selected; impact: high, effort: low, risk: low, confidence: high): Prune excluded directories during traversal for performance (avoid walking into `.git`, `node_modules`, etc).
- [ ] P1 (selected; impact: high, effort: low, risk: low, confidence: med): Add allowlist mode (only export a configured set of extensions; skip everything else by default).
- [ ] P1 (impact: med, effort: low, risk: low, confidence: med): Support writing the JSONL report to stdout (`--report -`) for easier piping/automation.
- [ ] P1 (impact: med, effort: med, risk: low, confidence: med): Add benchmark/regression coverage for large directory and ZIP inputs (track runtime and memory).
- [ ] P2 (impact: med, effort: high, risk: med, confidence: med): Add optional recursive nested-archive sanitization with a depth budget and expanded-bytes budget.
- [ ] P2 (impact: med, effort: med, risk: low, confidence: low): Expand image support beyond JPEG/PNG/WebP (HEIC/TIFF) if dependency footprint remains acceptable.

## Implemented
- [x] 2026-02-09: Added directory traversal guardrails for large directory inputs (`--max-files`, `--max-bytes`) and switched directory walking to a streaming deterministic iterator.
  Evidence: `src/file_sanitizer/cli.py`, `src/file_sanitizer/sanitizer.py`, `tests/test_sanitizer.py`, `README.md`.
- [x] 2026-02-09: Added magic-bytes content-type sniffing to reduce extension spoofing and avoid hard errors on invalid `.pdf` inputs (with OOXML heuristics to avoid treating Office docs as raw ZIP archives).
  Evidence: `src/file_sanitizer/sanitizer.py`, `tests/test_sanitizer.py`.
- [x] 2026-02-09: Published report contract docs and schema; report records now include `report_version` and the CLI summary record includes `report_version`.
  Evidence: `docs/report.md`, `docs/report.schema.json`, `src/file_sanitizer/sanitizer.py`, `src/file_sanitizer/cli.py`, `tests/test_sanitizer.py`, `README.md`.
- [x] 2026-02-09: Added structured warning taxonomy (`code` + `message`) for JSONL report warnings.
  Evidence: `src/file_sanitizer/sanitizer.py`, `tests/test_sanitizer.py`, `tests/test_fixtures.py`.
- [x] 2026-02-09: Added Office macro warnings for macro-enabled OOXML extensions and `vbaProject.bin` indicators (local files and ZIP members).
  Evidence: `src/file_sanitizer/sanitizer.py`, `tests/test_sanitizer.py`.
- [x] 2026-02-09: Added `--risky-policy {warn,block}` to optionally block writing outputs when risky PDF/ZIP/Office findings are present.
  Evidence: `src/file_sanitizer/cli.py`, `src/file_sanitizer/sanitizer.py`, `tests/test_sanitizer.py`, `tests/test_smoke.py`, `README.md`.
- [x] 2026-02-09: Added ZIP bomb guardrails for ZIP inputs (entry-count, per-member expanded-size, total expanded-size, compression-ratio checks).
  Evidence: `src/file_sanitizer/sanitizer.py`, `tests/test_sanitizer.py`.
- [x] 2026-02-09: Added nested ZIP member policy with secure default skip and optional copy mode.
  Evidence: `src/file_sanitizer/sanitizer.py`, `src/file_sanitizer/cli.py`, `tests/test_sanitizer.py`.
- [x] 2026-02-09: Exposed configurable archive guardrail flags in CLI (`--zip-max-*`, `--nested-archive-policy`).
  Evidence: `src/file_sanitizer/cli.py`, `README.md`.
- [x] 2026-02-09: Added regression tests for guardrails and option validation (member limits/size/ratio/total-size/nested-policy/dry-run parity).
  Evidence: `tests/test_sanitizer.py`.
- [x] 2026-02-09: Updated docs and trackers to align with current ZIP safety behavior.
  Evidence: `README.md`, `ROADMAP.md`, `PLAN.md`, `CHANGELOG.md`, `UPDATE.md`, `CLONE_FEATURES.md`.
- [x] 2026-02-09: Added structured project memory artifacts for decisions and incidents.
  Evidence: `PROJECT_MEMORY.md`, `INCIDENTS.md`.
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
  - `make check` -> pass (`41 passed`, mypy/ruff/build clean).
  - `.venv/bin/python -m file_sanitizer sanitize --input tests/fixtures/mixed-bundle.zip --out "$tmpdir/out" --report "$tmpdir/report.jsonl" --report-summary` -> pass (`rc=0`, `zip_sanitized: 1`, output ZIP entries: `docs/readme.txt`, `images/exif-photo.jpg`, `pdfs/risky.pdf`, and report warnings are structured via `code` + `message`).
  - `.venv/bin/python -m file_sanitizer sanitize --input tests/fixtures/mixed-bundle.zip --out "$tmpdir/out" --report "$tmpdir/report.jsonl" --risky-policy block` -> expected policy block (`rc=2`, `action=blocked`, output ZIP not written).
  - `.venv/bin/python -m file_sanitizer sanitize --input "$tmpdir/macro.docm" --out "$tmpdir/out" --report "$tmpdir/report.jsonl"` -> pass (`rc=0`, warnings include `office_macro_enabled`, `office_macro_indicator_vbaproject`).
  - `.venv/bin/python -m file_sanitizer sanitize --input tests/fixtures/mixed-bundle.zip --out "$tmpdir/out" --report "$tmpdir/report.jsonl" --dry-run --fail-on-warnings` -> expected strict failure (`rc=3`, `would_zip_sanitize: 1`).
  - `.venv/bin/python -m file_sanitizer sanitize --input "$tmpdir/outer.zip" --out "$tmpdir/out" --report "$tmpdir/report.jsonl" --nested-archive-policy copy --zip-max-members 10 --zip-max-member-bytes 1024 --zip-max-total-bytes 4096 --zip-max-compression-ratio 200` -> pass (`rc=0`, output ZIP entries include `docs/note.txt`, `nested/inner.zip`).
  - `.venv/bin/python -m file_sanitizer sanitize --input "$tmpdir/in" --out "$tmpdir/out" --report "$tmpdir/report.jsonl" --max-files 2 --report-summary` -> pass (report includes `report_version: 1`, `content_type_detected` warnings for renamed PDF/ZIP, and `action=truncated` when guardrails stop traversal).

## Insights
- Deterministic iteration improves CI reproducibility and reduces flaky report diffs.
- ZIP sanitization is only as safe as member policy; warning+skip for unsafe members is required even in metadata-focused tools.
- Fixture-backed binary tests catch parser/serialization regressions that synthetic-only tests may miss.
- ZIP safety controls are most useful when enforced pre-decompression (metadata checks) with deterministic warning output.
- Nested archive handling should be explicit policy, not implicit pass-through.
- Market scan notes (2026-02-09): MAT2 is a general-purpose metadata removal CLI; baseline expectation: multi-format support + automation-friendly usage. https://0xacab.org/jvoisin/mat2
- Market scan notes (2026-02-09): ExifTool is the de-facto standard for inspecting/removing metadata from many file types; baseline expectation: deterministic scripting and broad format support. https://exiftool.org/
- Market scan notes (2026-02-09): qpdf supports removing/clearing PDF metadata and deterministic output; baseline expectation: PDF metadata removal should be scriptable. https://qpdf.readthedocs.io/en/stable/cli.html
- Market scan notes (2026-02-09): Dangerzone uses render-to-safe-output for risky documents; baseline expectation: users want a "safer export" story beyond metadata removal for untrusted docs. https://dangerzone.rocks/
- Market scan notes (2026-02-09): OOXML macro signals are commonly detectable via `vbaProject.bin`; baseline expectation: macro-enabled formats should be surfaced as high-risk findings. https://arstdesign.com/articles/detecting-macros-in-ooxml-files.html
- Market scan notes (2026-02-09, Cycle 3): MAT (Metadata Anonymisation Toolkit) positions “wide format coverage” as table stakes and publishes an explicit supported-format list (includes TIFF and OOXML among others). https://mat.boum.org/
- Market scan notes (2026-02-09, Cycle 3): Dangerzone’s core value prop is “safe export” via sandboxed render-to-pixels then rebuild-to-PDF; this is a distinct category from metadata stripping and sets user expectations for handling untrusted documents. https://dangerzone.rocks/
- Market scan notes (2026-02-09, Cycle 3): qpdf documents deterministic/static ID flags for reproducible output in tests; “deterministic output” is a common expectation for automation pipelines. https://qpdf.readthedocs.io/
- Market scan notes (2026-02-09, Cycle 3): ExifTool’s official docs emphasize broad metadata read/write coverage; “strip metadata” workflows typically combine deterministic CLI flags with policy about what to retain. https://exiftool.org/exiftool_pod2.html

## Notes
- This file is maintained by the autonomous clone loop.
