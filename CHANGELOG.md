# CHANGELOG

## Unreleased

- Preserve directory structure on directory inputs (avoids collisions).
- Atomic output writes (reduces partial-file risk on failure).
- Add PDF risk scanning warnings (OpenAction/JavaScript/actions/forms/attachments).
- Add TIFF image sanitization support (`.tif/.tiff`).
- Add CLI flags: `--flat`, `--[no-]overwrite`, `--[no-]copy-unsupported`, `--dry-run`.
- Print summary stats (counts by action) to stderr.
- Add optional report summary record (`--report-summary`).
- Support writing the JSONL report to stdout (`--report -`) for piping/automation.
- Add `--fail-on-warnings` (CI-friendly non-zero exit on warnings).
- Add `--quiet` to suppress human-readable stderr summary output.
- Add warning taxonomy (`code` + `message`) in JSONL report warnings for machine-actionable policy decisions.
- Add Office macro detection warnings for OOXML macro-enabled documents and `vbaProject.bin` indicators.
- Add `--risky-policy` (`warn` vs `block`) to optionally block writing outputs for risky PDF/ZIP/Office findings.
- `--dry-run` no longer creates output directories unless needed for the report path.
- Avoid re-processing newly written outputs when `--out` is inside the input tree.
- Add `--exclude` (repeatable) to skip matching paths during traversal.
- Add `--allow-ext` (repeatable) allowlist mode to skip non-allowlisted extensions by default.
- Add ZIP archive sanitization with secure member filtering (unsafe/symlink/encrypted/duplicate entries skipped).
- Sanitize supported ZIP members (image/PDF) and preserve unsupported members by policy.
- Make directory and ZIP member processing deterministic for stable reports.
- Add ZIP bomb guardrails with configurable limits (`--zip-max-members`, `--zip-max-member-bytes`, `--zip-max-total-bytes`, `--zip-max-compression-ratio`).
- Add nested ZIP handling policy (`--nested-archive-policy` with secure default `skip`).
- Add committed regression fixtures under `tests/fixtures/` for EXIF image, risky PDF, and mixed ZIP.
- Add directory traversal guardrails for large inputs (`--max-files`, `--max-bytes`) and streaming deterministic directory walking.
- Add magic-bytes content-type sniffing to reduce extension spoofing (with OOXML heuristics to avoid treating Office docs as raw ZIPs).
- Add `report_version` field to report records and publish report schema documentation under `docs/report.md`.

## v0.1.0 - 2026-01-31

- Image EXIF stripping and PDF metadata removal.
- JSONL report output.
