# Update (2026-02-01)

## Shipped

- Directory sanitization now preserves relative paths by default (avoids filename collisions).
- Outputs are written atomically (reduces risk of partial/corrupt outputs).
- PDF risk scanning adds report warnings for common active-content indicators (OpenAction/actions/forms/attachments).
- CLI adds safer knobs: `--flat`, `--[no-]overwrite`, `--[no-]copy-unsupported`, `--dry-run`.
- CLI prints a per-run summary to stderr (counts by action).
- Optional report summary record appended to JSONL via `--report-summary`.
- Optional strict mode for CI: `--fail-on-warnings` exits non-zero if any warnings are present.
- `--dry-run` avoids creating output directories unless required for the report path.
- When `--out` is under the input directory, the run now snapshots the file list up-front to avoid re-processing newly created outputs.

## Notes

- This tool primarily strips metadata. If the report warns about PDF actions/forms/attachments, treat the file as potentially unsafe.

## Verification

```bash
make setup
make check
```

## No PRs

Per instruction, changes are made directly on `main` and should be pushed as-is.
