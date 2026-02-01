# File Sanitizer

Local file sanitizer that removes common metadata from images and PDFs.

## Scope (v0.1.0)

- Strip EXIF from images.
- Remove PDF metadata.
- JSONL report output.

## Quickstart

```bash
make setup
make check
```

## Usage

```bash
python -m file_sanitizer sanitize --input ./files --out ./sanitized --report sanitize-report.jsonl
```
