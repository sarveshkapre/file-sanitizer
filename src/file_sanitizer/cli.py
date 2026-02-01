from __future__ import annotations

import argparse
from pathlib import Path

from .sanitizer import sanitize_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="file-sanitizer")
    parser.add_argument("--version", action="version", version="0.1.0")

    sub = parser.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("sanitize", help="Sanitize a file or directory")
    p_run.add_argument("--input", required=True, help="File or directory to sanitize")
    p_run.add_argument("--out", required=True, help="Output directory")
    p_run.add_argument("--report", default="sanitize-report.jsonl")
    p_run.set_defaults(func=_run)

    args = parser.parse_args(argv)
    return int(args.func(args))


def _run(args: argparse.Namespace) -> int:
    return sanitize_path(Path(args.input), Path(args.out), Path(args.report))


if __name__ == "__main__":
    raise SystemExit(main())
