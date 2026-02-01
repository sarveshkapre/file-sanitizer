from __future__ import annotations

import argparse
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
        help="Compute outputs and report without writing any files",
    )
    p_run.set_defaults(func=_run)

    args = parser.parse_args(argv)
    return int(args.func(args))


def _run(args: argparse.Namespace) -> int:
    out_dir = Path(args.out)
    report = Path(args.report) if args.report is not None else (out_dir / "sanitize-report.jsonl")

    counts: Counter[str] = Counter()

    rc = sanitize_path(
        Path(args.input),
        out_dir,
        report,
        options=SanitizeOptions(
            flat_output=bool(args.flat),
            overwrite=bool(args.overwrite),
            copy_unsupported=bool(args.copy_unsupported),
            dry_run=bool(args.dry_run),
        ),
        on_item=lambda item: counts.update([item.action]),
    )

    total = sum(counts.values())
    if args.dry_run:
        print("dry-run complete", file=sys.stderr)
    print(f"wrote {report}", file=sys.stderr)
    print(f"files: {total}", file=sys.stderr)
    for action, n in sorted(counts.items()):
        print(f"  {action}: {n}", file=sys.stderr)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
