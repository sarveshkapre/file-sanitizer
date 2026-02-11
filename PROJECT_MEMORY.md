# PROJECT_MEMORY

## Recent Decisions

- 2026-02-11 | Add recursive nested ZIP sanitization mode (`--nested-archive-policy sanitize`) with explicit depth (`--nested-archive-max-depth`) and aggregate-byte (`--nested-archive-max-total-bytes`) guardrails. | Why: nested archives are common in real drops and skip/copy-only handling leaves sanitizer coverage gaps. | Evidence: `src/file_sanitizer/sanitizer.py`, `src/file_sanitizer/cli.py`, `tests/test_sanitizer.py`, `tests/test_smoke.py`, `README.md`, `make check`, smoke run with `RC1=0` and nested output entry `docs/secret.bin`. | Commit: `dd058cb5036408f9c72615ef7385991898cfaa7b` | Confidence: High | Trust label: trusted (verified-local)
- 2026-02-11 | Add ZIP-member magic-byte sniffing parity (detected PDF/image/OOXML in `.zip` members) and allowlist-by-detected-type behavior. | Why: extension-only routing missed disguised supported payloads and could under-sanitize untrusted archives. | Evidence: `src/file_sanitizer/sanitizer.py`, `tests/test_sanitizer.py` (`test_zip_member_magic_sniffing_*`, `test_zip_member_allowlist_uses_detected_type`), smoke run with `RC2=0` and output entry `docs/secret.bin`. | Commit: `dd058cb5036408f9c72615ef7385991898cfaa7b` | Confidence: High | Trust label: trusted (verified-local)

## Mistakes And Fixes

- 2026-02-11 | Root cause: initial allowlist parity implementation still rejected disguised ZIP members because `_allowlist_allows` short-circuited on non-allowlisted suffix before considering detected content type. | Fix: changed allowlist evaluation to allow detected-type matches even when suffix is present/mismatched; added regression test `test_zip_member_allowlist_uses_detected_type`. | Prevention rule: for every “detected content type” feature, add a mismatch test where extension and detected type disagree.

## Verification Evidence

- `make check` | pass (`58 passed`, mypy/ruff/build clean)
- `.venv/bin/python -m file_sanitizer sanitize --input "$tmpdir/outer.zip" --out "$tmpdir/out1" --report "$tmpdir/report1.jsonl" --nested-archive-policy sanitize --nested-archive-max-depth 3 --nested-archive-max-total-bytes 1048576 --quiet` | pass (`RC1=0`, nested output retained `docs/secret.bin`, warnings include `zip_nested_archive_sanitized`)
- `.venv/bin/python -m file_sanitizer sanitize --input "$tmpdir/allow.zip" --out "$tmpdir/out2" --report "$tmpdir/report2.jsonl" --allow-ext .pdf --no-copy-unsupported --quiet` | pass (`RC2=0`, allowlist accepted disguised PDF member by detected type)
- `gh run list --limit 10 --json databaseId,headSha,status,conclusion,workflowName,createdAt` | pass (`dd058cb5036408f9c72615ef7385991898cfaa7b` and `b51801ea7507d8972819c9ff6fc814302a42b5bb` completed with `conclusion=success`)

## Decision Log

### 2026-02-10 - Stdout report mode should not skip a real input file named `-`
- Decision: When `report_path` is `"-"` (stdout mode), do not apply report-file skipping logic against a resolved `Path("-")`; only skip the report file when writing to an on-disk report path.
- Why: In stdout mode there is no report file on disk, so skipping an input path named `-` is incorrect and surprising; this also removes an unnecessary `Path.resolve()` in stdout mode.
- Evidence:
  - Code: `src/file_sanitizer/sanitizer.py`
  - Tests: `tests/test_sanitizer.py` (regression for `input=.` containing a file named `-` with `report_path="-"`)
  - Verification: `make check` (pass, `51 passed`)
- Commit: `a9d7b90a84ee097a75d83c64760c1ff73e499573`
- Confidence: High
- Trust label: verified-local

### 2026-02-10 - Office OOXML metadata stripping (docProps) and embedded OOXML sanitization inside ZIP inputs
- Decision: Treat OOXML Office documents (`.docx/.xlsx/.pptx` and macro-enabled variants) as supported inputs and sanitize their `docProps/*.xml` metadata parts (core/app/custom) while dropping `docProps/thumbnail.*`; extend ZIP sanitization to sanitize embedded OOXML members using the same logic.
- Why: Office files commonly include user-identifying metadata (author/tool/timestamps) and thumbnails that can leak document content; stripping these parts improves privacy and matches user expectations for a "metadata sanitizer" without requiring a full render-to-pixels workflow.
- Evidence:
  - Code: `src/file_sanitizer/sanitizer.py`
  - Docs: `README.md`, `docs/report.md`, `CHANGELOG.md`
  - Tests: `tests/test_sanitizer.py` (OOXML docProps/thumbnail regression; embedded `.docx` inside `.zip`)
  - Verification: `make check` (pass, `50 passed`)
  - Smoke:
    - `.venv/bin/python -m file_sanitizer sanitize --input tests/fixtures/mixed-bundle.zip --out "$tmpdir/out" --report "$tmpdir/report.jsonl" --report-summary --quiet` (pass, `rc=0`)
    - `.venv/bin/python -m file_sanitizer sanitize --input "$tmpdir/meta.docx" --out "$tmpdir/out" --report "$tmpdir/report.jsonl" --quiet` (pass, `action=office_sanitized`; output `.docx` contains no `docProps/thumbnail.*`)
- Commits:
  - Feature + tests: `df8ac571ad21df2afce11cb93ba3cb04107e3806`
  - Docs: `0db2cb6923b04b5adba8147ef044e9235f2f3fbd`
- Confidence: High
- Trust label: verified-local

### 2026-02-09 - Bound ZIP member reads to enforce uncompressed-byte limits during streaming read
- Decision: Read ZIP members via a bounded streaming reader (hard cap) instead of `ZipFile.read()` to ensure uncompressed-byte guardrails hold even if ZIP headers lie about sizes.
- Why: ZIP safety controls based only on declared metadata can be bypassed with malformed entries; bounding the actual read reduces zip-bomb/DoS risk on untrusted drops.
- Evidence:
  - Code: `src/file_sanitizer/sanitizer.py`
  - Verification: `make check` (pass, `48 passed`)
  - Smoke: `.venv/bin/python -m file_sanitizer sanitize --input tests/fixtures/mixed-bundle.zip --out "$tmpdir/out" --report "$tmpdir/report.jsonl" --report-summary` (pass, `rc=0`)
- Commit: `3e2c6c1a50b0333c763a05f1141e69399b4dc647`
- Confidence: High
- Trust label: verified-local

### 2026-02-09 - Quiet CLI mode and richer report summary run context
- Decision: Add `--quiet` to suppress human-readable stderr summaries; extend the optional JSONL summary record with run context (timestamps, duration, tool version, and options snapshot).
- Why: Many ingestion/pipeline environments require clean stdout/stderr separation; run metadata in the summary reduces troubleshooting and improves auditability without changing the required report fields.
- Evidence:
  - Code: `src/file_sanitizer/cli.py`
  - Docs: `README.md`, `docs/report.md`, `CHANGELOG.md`
  - Tests: `tests/test_smoke.py`
  - Verification: `make check` (pass, `48 passed`)
  - Smoke: `.venv/bin/python -m file_sanitizer sanitize --input tests/fixtures/mixed-bundle.zip --out "$tmpdir/out" --report - --dry-run --quiet` (pass, `rc=0`, `stderr_len=0`)
- Commit: `a5750d1bddc0947a5a7a3d24d3c7b4b53534d75f`
- Confidence: High
- Trust label: verified-local

### 2026-02-09 - Stdout JSONL reports (`--report -`) and report-summary to stdout
- Decision: Support writing the JSONL report to stdout via `--report -` and ensure `--report-summary` appends the summary record to stdout in this mode (stderr summary remains for humans/CI logs).
- Why: Enables piping into jq/ingestion systems without managing a report file path and prevents accidental creation of a literal `./-` file.
- Evidence:
  - Code: `src/file_sanitizer/sanitizer.py`, `src/file_sanitizer/cli.py`
  - Docs: `README.md`, `docs/report.md`, `CHANGELOG.md`
  - Tests: `tests/test_smoke.py`
  - Verification: `make check` (pass, `47 passed`)
  - Smoke: `.venv/bin/python -m file_sanitizer sanitize --input "$tmpdir/in" --out "$tmpdir/out" --report - --dry-run --report-summary` (pass; JSONL file records + summary emitted on stdout)
- Commit: `9cd15aa990a31ed7a6afcd71a5e6c3f27ad409e4`
- Confidence: High
- Trust label: verified-local

### 2026-02-09 - TIFF image sanitization support (`.tif/.tiff`)
- Decision: Add TIFF to supported image inputs and sanitize by re-encoding through Pillow with a metadata-dropping conversion step (convert to RGB, then write TIFF with deflate compression).
- Why: TIFF is a common “scanned doc” container and often carries metadata in tags/IFDs; broadening image support improves real-world usefulness without adding dependencies.
- Evidence:
  - Code: `src/file_sanitizer/sanitizer.py`
  - Tests: `tests/test_sanitizer.py` (writes TIFF with ImageDescription tag and asserts tag is absent post-sanitize)
  - Verification: `make check` (pass, `47 passed`)
  - Smoke: `.venv/bin/python -m file_sanitizer sanitize --input "$tmpdir/secret.tiff" --out "$tmpdir/out" --report "$tmpdir/report.jsonl"` (pass; output TIFF tag 270 absent)
- Commit: `1bc6b03b1c49f1438e369a4fc5c73b57f9ff7c34`
- Confidence: Medium-High
- Trust label: verified-local

### 2026-02-09 - Lightweight benchmark harness (local-only)
- Decision: Add a simple benchmark script to generate synthetic directory/ZIP fixtures and time sanitizer runs (default dry-run) without adding CI runtime risk.
- Why: Provides a low-friction way to catch obvious performance regressions during development and when tuning guardrails.
- Evidence:
  - Code: `scripts/bench_sanitize.py`
  - Docs: `README.md`
  - Verification: `make check` (pass, `47 passed`)
  - Smoke: `.venv/bin/python scripts/bench_sanitize.py --kind dir --count 2000 --bytes 64` and `--kind zip ...` (pass; prints JSON timings)
- Commit: `74ffe48a5c2f76d1105ef7393117c88d503d9b3b`
- Confidence: Medium
- Trust label: verified-local

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
