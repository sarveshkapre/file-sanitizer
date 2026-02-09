from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from .sanitizer import (
    DEFAULT_ZIP_MAX_COMPRESSION_RATIO,
    DEFAULT_ZIP_MAX_MEMBER_UNCOMPRESSED_BYTES,
    DEFAULT_ZIP_MAX_MEMBERS,
    DEFAULT_ZIP_MAX_TOTAL_UNCOMPRESSED_BYTES,
    NESTED_ARCHIVE_POLICIES,
    REPORT_VERSION,
    RISKY_POLICIES,
    SanitizeOptions,
    sanitize_path,
)
from .version import get_version


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="file-sanitizer")
    parser.add_argument("--version", action="version", version=get_version())

    sub = parser.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("sanitize", help="Sanitize a file or directory")
    p_run.add_argument("--input", required=True, help="File or directory to sanitize")
    p_run.add_argument("--out", required=True, help="Output directory")
    p_run.add_argument(
        "--report",
        default=None,
        help="Path to JSONL report (default: <out>/sanitize-report.jsonl)",
    )
    p_run.add_argument(
        "--flat",
        action="store_true",
        help="Write all outputs directly into --out (may rename to avoid collisions)",
    )
    p_run.add_argument(
        "--overwrite",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Overwrite existing outputs (default: true)",
    )
    p_run.add_argument(
        "--copy-unsupported",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Copy unsupported file types as-is (default: true)",
    )
    p_run.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute outputs and write the report without writing sanitized outputs",
    )
    p_run.add_argument(
        "--report-summary",
        action="store_true",
        help="Append a final JSONL summary record to the report",
    )
    p_run.add_argument(
        "--fail-on-warnings",
        action="store_true",
        help="Exit non-zero if any warnings are emitted (useful for CI)",
    )
    p_run.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="GLOB",
        help="Exclude paths matching this glob (repeatable, evaluated relative to input dir when input is a directory)",
    )
    p_run.add_argument(
        "--allow-ext",
        action="append",
        default=[],
        metavar="EXT",
        help=(
            "Only export files with these extensions (repeatable). "
            "When set, all other files are skipped even if --copy-unsupported is enabled."
        ),
    )
    p_run.add_argument(
        "--max-files",
        type=int,
        default=None,
        metavar="N",
        help="Stop traversal after processing N files (directory inputs only; default: unlimited)",
    )
    p_run.add_argument(
        "--max-bytes",
        type=int,
        default=None,
        metavar="BYTES",
        help="Stop traversal after processing BYTES of file sizes (directory inputs only; default: unlimited)",
    )
    p_run.add_argument(
        "--zip-max-members",
        type=int,
        default=DEFAULT_ZIP_MAX_MEMBERS,
        metavar="N",
        help=f"Maximum ZIP entries processed (default: {DEFAULT_ZIP_MAX_MEMBERS})",
    )
    p_run.add_argument(
        "--zip-max-member-bytes",
        type=int,
        default=DEFAULT_ZIP_MAX_MEMBER_UNCOMPRESSED_BYTES,
        metavar="BYTES",
        help=(
            "Maximum uncompressed size allowed for a single ZIP member "
            f"(default: {DEFAULT_ZIP_MAX_MEMBER_UNCOMPRESSED_BYTES})"
        ),
    )
    p_run.add_argument(
        "--zip-max-total-bytes",
        type=int,
        default=DEFAULT_ZIP_MAX_TOTAL_UNCOMPRESSED_BYTES,
        metavar="BYTES",
        help=(
            "Maximum cumulative uncompressed bytes processed from ZIP members "
            f"(default: {DEFAULT_ZIP_MAX_TOTAL_UNCOMPRESSED_BYTES})"
        ),
    )
    p_run.add_argument(
        "--zip-max-compression-ratio",
        type=float,
        default=DEFAULT_ZIP_MAX_COMPRESSION_RATIO,
        metavar="RATIO",
        help=(
            "Maximum allowed ZIP member compression ratio "
            f"(uncompressed/compressed, default: {DEFAULT_ZIP_MAX_COMPRESSION_RATIO})"
        ),
    )
    p_run.add_argument(
        "--nested-archive-policy",
        choices=sorted(NESTED_ARCHIVE_POLICIES),
        default="skip",
        help="How nested ZIP members are handled (default: skip)",
    )
    p_run.add_argument(
        "--risky-policy",
        choices=sorted(RISKY_POLICIES),
        default="warn",
        help="How risky findings are handled (default: warn; use block to skip writing risky outputs)",
    )
    p_run.set_defaults(func=_run)

    args = parser.parse_args(argv)
    return int(args.func(args))


def _run(args: argparse.Namespace) -> int:
    out_dir = Path(args.out)
    report = Path(args.report) if args.report is not None else (out_dir / "sanitize-report.jsonl")

    counts: Counter[str] = Counter()
    warning_count = 0
    error_count = 0

    def _on_item(item: object) -> None:
        nonlocal warning_count, error_count
        # Keep callback typing loose so `sanitize_path` remains the source of truth.
        counts.update([str(getattr(item, "action"))])
        if str(getattr(item, "action")) != "excluded":
            warning_count += len(getattr(item, "warnings"))
        if str(getattr(item, "action")) in {"error", "blocked"}:
            error_count += 1

    rc = sanitize_path(
        Path(args.input),
        out_dir,
        report,
        options=SanitizeOptions(
            flat_output=bool(args.flat),
            overwrite=bool(args.overwrite),
            copy_unsupported=bool(args.copy_unsupported),
            dry_run=bool(args.dry_run),
            exclude_globs=list(args.exclude),
            allow_exts=list(args.allow_ext),
            max_files=None if args.max_files is None else int(args.max_files),
            max_bytes=None if args.max_bytes is None else int(args.max_bytes),
            zip_max_members=int(args.zip_max_members),
            zip_max_member_uncompressed_bytes=int(args.zip_max_member_bytes),
            zip_max_total_uncompressed_bytes=int(args.zip_max_total_bytes),
            zip_max_compression_ratio=float(args.zip_max_compression_ratio),
            nested_archive_policy=str(args.nested_archive_policy),
            risky_policy=str(args.risky_policy),
        ),
        on_item=_on_item,
    )

    if rc == 0 and args.fail_on_warnings and warning_count > 0:
        rc = 3

    total = sum(counts.values())
    if args.dry_run:
        print("dry-run complete", file=sys.stderr)
    print(f"wrote {report}", file=sys.stderr)
    print(f"files: {total}", file=sys.stderr)
    print(f"warnings: {warning_count}", file=sys.stderr)
    print(f"errors: {error_count}", file=sys.stderr)
    for action, n in sorted(counts.items()):
        print(f"  {action}: {n}", file=sys.stderr)

    if args.report_summary:
        summary = {
            "type": "summary",
            "report_version": REPORT_VERSION,
            "dry_run": bool(args.dry_run),
            "exit_code": int(rc),
            "files": int(total),
            "warnings": int(warning_count),
            "errors": int(error_count),
            "counts": dict(sorted(counts.items())),
        }
        with report.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(summary) + "\n")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
