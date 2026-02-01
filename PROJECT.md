# PROJECT.md

Exact commands for working in this repo.

## Setup

```bash
make setup
```

## Quality gate

```bash
make check
```

## Run

```bash
python -m file_sanitizer --help
```

## Example

```bash
python -m file_sanitizer sanitize --input ./files --out ./sanitized --report sanitize-report.jsonl
```
