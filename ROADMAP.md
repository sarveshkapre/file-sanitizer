# ROADMAP

## v0.1.0

- Image EXIF removal + PDF metadata stripping.

## v0.1.1 (Unreleased)

- Office OOXML metadata stripping for `.docx/.xlsx/.pptx` (and macro-enabled variants).
- Recursive nested ZIP sanitization option with depth and aggregate-byte guardrails.
- ZIP member content-type sniffing parity (detected PDF/image/OOXML inside archives).

## Next

- CI-friendly benchmark/regression coverage for very large directory and ZIP inputs.
- Optional run-level metadata record at the start of the JSONL report (distinct from summary).
- Optional HEIC image support behind an extra dependency.
