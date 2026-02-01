# CHANGELOG

## Unreleased

- Preserve directory structure on directory inputs (avoids collisions).
- Atomic output writes (reduces partial-file risk on failure).
- Add PDF risk scanning warnings (OpenAction/JavaScript/actions/forms/attachments).
- Add CLI flags: `--flat`, `--[no-]overwrite`, `--[no-]copy-unsupported`, `--dry-run`.
- Print summary stats (counts by action) to stderr.
- Add optional report summary record (`--report-summary`).

## v0.1.0 - 2026-01-31

- Image EXIF stripping and PDF metadata removal.
- JSONL report output.
