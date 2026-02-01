from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from .sanitizer import SanitizeOptions, sanitize_path
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
        if str(getattr(item, "action")) == "error":
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
