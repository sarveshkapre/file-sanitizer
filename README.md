# File Sanitizer

Local file sanitizer that removes common metadata from images and PDFs.

## Scope (v0.1.0)

- Strip EXIF from images.
- Remove PDF metadata.
- Strip common Office OOXML metadata (`docProps/*`) and drop `docProps/thumbnail.*` for `.docx/.xlsx/.pptx` (and macro-enabled variants).
- Sanitize ZIP archives by sanitizing supported members and filtering unsafe members.
- JSONL report output.
- Preserve directory structure by default (avoids filename collisions).
- Deterministic traversal/report ordering for reproducible runs.

## Quickstart

```bash
make setup
make check
```

## Usage

```bash
file-sanitizer sanitize --input ./files --out ./sanitized
```

`--input` can be either a directory/file or a `.zip` archive.

Optional flags:

```bash
# Skip unknown file types instead of copying them as-is
file-sanitizer sanitize --input ./files --out ./sanitized --no-copy-unsupported

# Exclude paths (repeatable; evaluated relative to input directory)
file-sanitizer sanitize --input ./files --out ./sanitized --exclude .git --exclude node_modules

# Only export selected extensions (repeatable; everything else is skipped)
file-sanitizer sanitize --input ./files --out ./sanitized --allow-ext .pdf --allow-ext .jpg

# Flatten outputs into a single directory (may rename to avoid collisions)
file-sanitizer sanitize --input ./files --out ./sanitized --flat

# Preview sanitized outputs (report only; no sanitized files written)
file-sanitizer sanitize --input ./files --out ./sanitized --dry-run

# Append a summary record to the report JSONL (useful for ingestion)
file-sanitizer sanitize --input ./files --out ./sanitized --report-summary

# Write the JSONL report to stdout (useful for piping)
file-sanitizer sanitize --input ./files --out ./sanitized --report - --dry-run --report-summary

# Suppress human-readable stderr summary output (useful when piping in strict environments)
file-sanitizer sanitize --input ./files --out ./sanitized --report - --dry-run --quiet

# Exit non-zero if any warnings are emitted (useful for CI policy)
file-sanitizer sanitize --input ./files --out ./sanitized --dry-run --fail-on-warnings

# Guardrails for huge directory inputs
file-sanitizer sanitize --input ./files --out ./sanitized --max-files 50000 --max-bytes 1073741824

# Block writing outputs if risky findings are detected (PDF active content indicators, risky ZIP findings, Office macro signals)
file-sanitizer sanitize --input ./files --out ./sanitized --risky-policy block

# Sanitize a ZIP archive in place (supported members are re-written)
file-sanitizer sanitize --input ./drop/batch.zip --out ./sanitized

# Tighten ZIP bomb guardrails for untrusted drops
file-sanitizer sanitize --input ./drop/batch.zip --out ./sanitized \
  --zip-max-members 2000 \
  --zip-max-member-bytes 33554432 \
  --zip-max-total-bytes 268435456 \
  --zip-max-compression-ratio 80

# Keep nested ZIP members instead of skipping them (default is skip)
file-sanitizer sanitize --input ./drop/batch.zip --out ./sanitized --nested-archive-policy copy
```

Notes:
- ZIP handling skips unsafe members (for example path traversal paths or symlinks) and reports warnings.
- ZIP guardrails skip entries that exceed configured limits (entry count, per-entry size, total expanded bytes, compression ratio).
- Nested ZIP members are skipped by default (use `--nested-archive-policy copy` to preserve them as-is).
- When `--allow-ext` is set, non-allowlisted files are skipped; for `.zip` inputs, the allowlist is applied to ZIP members.
- Unsupported ZIP members are copied as-is by default (use `--no-copy-unsupported` to skip them).
- Report warnings are structured objects with `code` and `message` for machine-actionable ingestion.
- Office macro-enabled OOXML files (`.docm/.xlsm/.pptm` and templates) and OOXML macro indicators (ex: `vbaProject.bin`) are surfaced as warnings (macros are not removed).

Report contract:
- Schema documentation: `docs/report.md`
- Optional JSON Schema (per JSONL line): `docs/report.schema.json`

## Benchmark (Local)

```bash
.venv/bin/python scripts/bench_sanitize.py --kind dir --count 20000
.venv/bin/python scripts/bench_sanitize.py --kind zip --count 20000
```
