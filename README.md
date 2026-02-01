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

# Flatten outputs into a single directory (may rename to avoid collisions)
file-sanitizer sanitize --input ./files --out ./sanitized --flat

# Preview the report without writing outputs
file-sanitizer sanitize --input ./files --out ./sanitized --dry-run

# Append a summary record to the report JSONL (useful for ingestion)
file-sanitizer sanitize --input ./files --out ./sanitized --report-summary
```
