# PLAN.md

One-line pitch: A fast, local CLI to sanitize files by stripping common metadata and exporting safer copies with an audit log.

## Shipped

- Image metadata stripping (JPEG/PNG/WebP) and PDF document metadata removal.
- Directory sanitization that preserves folder structure (avoids filename collisions).
- Atomic writes (avoid partially-written outputs on failure).
- JSONL report output with per-file actions/warnings/errors.
- PDF risk scanning warnings (OpenAction/actions/forms/attachments) included in the report.
- ZIP archive sanitization (sanitize image/PDF members, handle unsupported members via policy).
- ZIP member hardening warnings (unsafe paths, symlinks, encrypted/duplicate entries are skipped).
- ZIP bomb guardrails (entry count, per-entry size, total expanded bytes, compression ratio) with configurable limits.
- Nested ZIP member policy (`skip` default, optional `copy`) to reduce nested archive propagation risk.
- CLI flags for safer runs: `--flat`, `--[no-]overwrite`, `--[no-]copy-unsupported`, `--dry-run`.
- ZIP safety tuning flags: `--zip-max-members`, `--zip-max-member-bytes`, `--zip-max-total-bytes`, `--zip-max-compression-ratio`, `--nested-archive-policy`.
- Summary stats printed to stderr (counts by action).
- Optional report summary record appended to JSONL via `--report-summary`.
- CI-friendly strict mode: `--fail-on-warnings`.
- `--dry-run` avoids creating output directories unless required for the report path.
- Safe traversal when `--out` is inside input (prevents re-processing outputs).
- Path exclusions via `--exclude` (repeatable).
- Deterministic traversal/member ordering for reproducible reports.
- Golden fixture corpus under `tests/fixtures/` for EXIF image, risky PDF, and mixed ZIP regression tests.

## Next

- Office document macro detection with clear warning taxonomy.
- Trust policy mode (`warn` vs `block`) for risky PDF/ZIP findings.
- Performance benchmark coverage for large directory and ZIP workloads.

## Top Risks / Unknowns

- “Sanitized” does not mean “safe”: PDFs can contain scripts, embedded files, links, and other active content.
- Image sanitization is format- and encoder-dependent; verify edge cases (animated WebP, palette PNGs).
- Large archives/directories still require tuning guardrail thresholds for deployment-specific workloads.

## Commands

See `PROJECT.md` for the canonical commands:

```bash
make setup
make check
make test
make lint
make typecheck
```
