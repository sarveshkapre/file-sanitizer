# Report Schema (JSONL)

`file-sanitizer` writes an audit report as newline-delimited JSON (JSONL): one JSON object per line.

You can write the report to stdout by passing `--report -` (useful for piping into other tools).

## Record Types

### File records (always present)

Each processed file produces one record with these fields:

- `report_version` (int): report schema version.
- `input_path` (string): input path as seen by the sanitizer.
- `output_path` (string | null): output path written (or planned in `--dry-run`), or `null` if no output is written.
- `action` (string): what the sanitizer did.
- `warnings` (array): zero or more warning objects.
- `error` (string | null): error message if `action == "error"`.

Warning objects:

- `code` (string): stable machine-readable code.
- `message` (string): human-readable detail.

#### `action` values

Non-dry-run actions:

- `image_sanitized`
- `pdf_sanitized`
- `zip_sanitized`
- `office_sanitized`
- `copied`
- `skipped`
- `excluded`
- `blocked`
- `error`
- `truncated` (run-level record indicating traversal stopped early due to guardrails)

Dry-run actions:

- `would_image_sanitize`
- `would_pdf_sanitize`
- `would_zip_sanitize`
- `would_office_sanitize`
- `would_copy`
- `would_skip`
- `would_block`

### Summary record (optional)

If you pass `--report-summary`, the CLI appends one final record:

- `type`: `"summary"`
- `report_version` (int)
- `dry_run` (bool)
- `exit_code` (int)
- `files` (int)
- `warnings` (int)
- `errors` (int)
- `counts` (object): action counts (string -> int)

Additional run-context fields may be present for ingestion/debugging:

- `tool_version` (string)
- `started_at` / `ended_at` (string, ISO 8601)
- `duration_ms` (int)
- `input` / `out` / `report` (string)
- `options` (object): CLI option snapshot

## Warning Codes

Warning codes are intended to be stable; new codes may be added over time.

### Recommended Policy Actions (Consumer Guidance)

This tool is primarily a metadata sanitizer; it also surfaces "risky" signals so downstream systems can
make trust decisions. Suggested handling by category:

- `pdf_risk_*`, `pdf_scan_failed`: treat as risky; consider `--risky-policy block` and/or a safer export workflow.
- `office_macro_*`, `office_ooxml_scan_failed`: treat as risky; macros are not removed, so consider blocking or quarantining.
- `zip_*`: treat as risky; indicates unsafe members, guardrail skips, nested-archive findings, or read/sanitize failures.
- `content_type_mismatch`, `content_type_detected_ooxml`: treat as suspicious on untrusted drops (extension spoofing).
- `allowlist_skipped`, `excluded_by_pattern`, `unsupported_*`, `symlink_skipped`, `output_exists`, `traversal_limit_reached`:
  informational; usually not security-critical, but may be policy-relevant depending on your pipeline.

Implementation note: `--risky-policy block` blocks output writes when any "risky" findings are present.

Common categories:

- `content_type_*`: content-type sniffing and mismatch findings.
  - `content_type_detected`: magic-bytes detection caused sanitizer selection to differ from extension.
  - `content_type_detected_ooxml`: ZIP container looks like an Office OOXML document.
  - `content_type_mismatch`: extension implies a supported type but magic bytes do not match.
- `allowlist_*`: allowlist mode findings.
  - `allowlist_skipped`: file (or ZIP member) was skipped because its extension was not in `--allow-ext`.
- `excluded_*`: exclusion behavior.
  - `excluded_by_pattern`
- `unsupported_*`: unsupported file handling.
  - `unsupported_copied`, `unsupported_skipped`, `unsupported_would_copy`
- `pdf_risk_*` and `pdf_scan_failed`: PDF active-content indicators (not removed).
- `office_*`: Office macro signals (macros are not removed).
- `zip_*`: ZIP hardening warnings and guardrail findings.
- `symlink_skipped`, `output_exists`, `traversal_limit_reached`

## Exit Codes (CLI)

- `0`: success (no `error` / `blocked` actions; warnings may be present).
- `2`: at least one `error` or `blocked` action occurred.
- `3`: `--fail-on-warnings` was set and at least one warning was emitted.
