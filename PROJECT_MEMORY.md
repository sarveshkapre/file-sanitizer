# PROJECT_MEMORY

## Decision Log

### 2026-02-09 - Exclude traversal pruning and allowlist mode (`--allow-ext`)
- Decision: When an `--exclude` glob matches a directory during traversal, prune it (do not walk into it) and emit a single `action=excluded` record for that directory.
- Decision: Add allowlist mode via `--allow-ext` (repeatable); when set, non-allowlisted files are skipped, and for `.zip` inputs the allowlist is applied to ZIP members.
- Why: Exclude pruning avoids wasting time walking large ignored trees (ex: `.git`, `node_modules`) and reduces report noise; allowlist mode lets users enforce “only export these types” policies for untrusted drops.
- Evidence:
  - Code: `src/file_sanitizer/sanitizer.py`, `src/file_sanitizer/cli.py`
  - Docs: `README.md`, `docs/report.md`, `UPDATE.md`
  - Tests: `tests/test_sanitizer.py`
  - Verification: `make check` (pass, `45 passed`)
  - Smoke: `.venv/bin/python -m file_sanitizer sanitize --input tests/fixtures/mixed-bundle.zip --out "$tmpdir/out" --report "$tmpdir/report.jsonl" --allow-ext .jpg --report-summary` (pass; output ZIP contains only allowlisted members; report includes `allowlist_skipped` warnings for dropped members)
- Commits:
  - Exclude traversal pruning: `acd69e79c46ab9c6779bc883eb992c0739b16643`
  - Allowlist mode (`--allow-ext`): `a28783f63d8e34bf3364a565b770db05e68f78fd`
- Confidence: High
- Trust label: verified-local

### 2026-02-09 - Report contract v1, content-type sniffing, and traversal guardrails
- Decision: Add `report_version` to every JSONL record and the optional CLI summary record; publish a stable report contract doc and an optional JSON Schema (per JSONL line).
- Decision: Add magic-bytes content-type sniffing to reduce extension spoofing (sanitize PDFs/ZIPs even when renamed) and avoid hard parser failures for invalid `.pdf` inputs (warn + treat as unsupported).
- Decision: Add directory traversal guardrails (`--max-files`, `--max-bytes`) and switch directory walking to a streaming deterministic iterator (avoid materializing the full file list).
- Why: Improves reliability and security posture on untrusted drops, makes downstream ingestion safer, and reduces memory risk on large traversals.
- Evidence:
  - Code: `src/file_sanitizer/sanitizer.py`, `src/file_sanitizer/cli.py`
  - Docs: `docs/report.md`, `docs/report.schema.json`, `README.md`
  - Tests: `tests/test_sanitizer.py`
  - Verification: `make check` (pass, `41 passed`)
  - Smoke: `.venv/bin/python -m file_sanitizer sanitize --input "$tmpdir/in" --out "$tmpdir/out" --report "$tmpdir/report.jsonl" --max-files 2 --report-summary` (pass; report shows `report_version: 1`, `content_type_detected` warnings, and `action=truncated` when limits are hit)
- Commits:
  - Traversal guardrails + streaming deterministic walk: `88325740bc350f84249f7f930d8596b92f7cb4d7`
  - Content-type sniffing + OOXML heuristics: `9760c86a121953dc4f45065b0d6716f02f10254b`
  - Report contract docs + schema v1: `2cf257e12ed41a0fd3cdbd053b58768768933c2c`
- Confidence: High
- Trust label: verified-local
- Follow-ups:
  - Prune excluded directories during traversal for performance (avoid walking into `.git`, `node_modules`, etc).
  - Add benchmark/regression coverage for large directory and ZIP inputs.

### 2026-02-09 - ZIP guardrails and nested-archive policy
- Decision: Enforce ZIP safety guardrails during archive processing using configurable limits for member count, per-member expanded bytes, total expanded bytes, and compression ratio.
- Decision: Treat nested ZIP members as risky by default (`nested_archive_policy=skip`) with an explicit opt-in to copy (`copy`).
- Why: Current ZIP processing previously allowed fully compressed/high-expansion payloads and nested bundles to pass through when unsupported-copy mode was enabled.
- Evidence:
  - Code: `src/file_sanitizer/sanitizer.py`, `src/file_sanitizer/cli.py`
  - Tests: `tests/test_sanitizer.py` (`test_zip_guardrail_*`, nested policy tests, dry-run parity, option validation)
  - Verification: `make check` (pass, `29 passed`)
  - Smoke: CLI run with fixture ZIP (`rc=0` normal, `rc=3` strict dry-run), CLI nested-copy policy run (`rc=0`)
- Commit: `91bee26b2077497ae508602ab755069c2fe4d3d3`
- Confidence: High
- Trust label: verified-local
- Follow-ups:
  - Add macro detection for Office docs and OOXML macro indicators.
  - Add warning taxonomy (`code` + `message`) for policy automation.
  - Add optional recursive nested sanitization with depth budget.

### 2026-02-09 - Structured warning codes, Office macro signals, and risky-policy block mode
- Decision: Switch JSONL report warnings from free-form strings to structured objects with `code` and `message`.
- Decision: Add Office macro warnings for macro-enabled OOXML extensions and `vbaProject.bin` indicators, including within ZIP members.
- Decision: Add `--risky-policy {warn,block}`; when set to `block`, skip writing outputs for risky PDFs and ZIPs (report action `blocked`).
- Why: Makes findings machine-actionable, improves auditability, and lets users enforce trust gates without relying on brittle string matching.
- Evidence:
  - Code: `src/file_sanitizer/sanitizer.py`, `src/file_sanitizer/cli.py`
  - Tests: `tests/test_sanitizer.py`, `tests/test_fixtures.py`, `tests/test_smoke.py`
  - Verification: `make check` (pass, `35 passed`)
  - Smoke: `.venv/bin/python -m file_sanitizer sanitize --input tests/fixtures/mixed-bundle.zip --out "$tmpdir/out" --report "$tmpdir/report.jsonl" --report-summary` (pass, `rc=0`, warnings are structured as `code` + `message`)
  - Smoke: `.venv/bin/python -m file_sanitizer sanitize --input tests/fixtures/mixed-bundle.zip --out "$tmpdir/out" --report "$tmpdir/report.jsonl" --risky-policy block` (expected block, `rc=2`, `action=blocked`)
- Commits:
  - Structured warning objects: `75c50a4dcd1a8de77b5bf0eb84b6678404c6ae92`
  - Office macro warnings: `2b81c82e5c1c8a3429c8cfe2ac0db85c746d1cc5`
  - Risky-policy block mode: `dc6734107354418dba5955b4384a0d9793db59a3`
- Confidence: High
- Trust label: verified-local
- Follow-ups:
  - Document the report schema/warning codes as a stable contract (and optionally ship a JSON Schema).
  - Add content-type sniffing to reduce extension-based misclassification.

## Open Follow-ups
- Add performance benchmark coverage for large ZIP and directory workloads.
- Add optional recursive nested-archive sanitization with a depth budget.
