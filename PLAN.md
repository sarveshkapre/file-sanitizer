# PLAN.md

One-line pitch: A fast, local CLI to sanitize files by stripping common metadata and exporting safer copies with an audit log.

## Shipped

- Image metadata stripping (JPEG/PNG/WebP) and PDF document metadata removal.
- Directory sanitization that preserves folder structure (avoids filename collisions).
- Atomic writes (avoid partially-written outputs on failure).
- JSONL report output with per-file actions/warnings/errors.
- PDF risk scanning warnings (OpenAction/actions/forms/attachments) included in the report.
- CLI flags for safer runs: `--flat`, `--[no-]overwrite`, `--[no-]copy-unsupported`, `--dry-run`.
- Summary stats printed to stderr (counts by action).
- Optional report summary record appended to JSONL via `--report-summary`.
- CI-friendly strict mode: `--fail-on-warnings`.
- `--dry-run` avoids creating output directories unless required for the report path.

## Next

- Add a small golden test corpus under `tests/fixtures/` (EXIF’d JPEG, metadata’d PDF).

## Top Risks / Unknowns

- “Sanitized” does not mean “safe”: PDFs can contain scripts, embedded files, links, and other active content.
- Image sanitization is format- and encoder-dependent; verify edge cases (animated WebP, palette PNGs).
- Large directories: performance characteristics and failure modes on very large inputs.

## Commands

See `PROJECT.md` for the canonical commands:

```bash
make setup
make check
make test
make lint
make typecheck
```
