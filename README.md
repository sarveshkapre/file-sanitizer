# File Sanitizer

Local file sanitizer that removes common metadata from images and PDFs.

## Scope (v0.1.0)

- Strip EXIF from images.
- Remove PDF metadata.
- JSONL report output.
- Preserve directory structure by default (avoids filename collisions).

## Quickstart

```bash
make setup
make check
```

## Usage

```bash
file-sanitizer sanitize --input ./files --out ./sanitized
```

Optional flags:

```bash
# Skip unknown file types instead of copying them as-is
file-sanitizer sanitize --input ./files --out ./sanitized --no-copy-unsupported

# Exclude paths (repeatable; evaluated relative to input directory)
file-sanitizer sanitize --input ./files --out ./sanitized --exclude .git --exclude node_modules

# Flatten outputs into a single directory (may rename to avoid collisions)
file-sanitizer sanitize --input ./files --out ./sanitized --flat

# Preview sanitized outputs (report only; no sanitized files written)
file-sanitizer sanitize --input ./files --out ./sanitized --dry-run

# Append a summary record to the report JSONL (useful for ingestion)
file-sanitizer sanitize --input ./files --out ./sanitized --report-summary

# Exit non-zero if any warnings are emitted (useful for CI policy)
file-sanitizer sanitize --input ./files --out ./sanitized --dry-run --fail-on-warnings
```
