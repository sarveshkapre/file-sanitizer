#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
import zipfile
from pathlib import Path

from file_sanitizer.sanitizer import SanitizeOptions, sanitize_path


def _write_bytes(path: Path, nbytes: int) -> None:
    # Fast enough for small fixtures without pulling in extra deps.
    path.write_bytes(b"a" * nbytes)


def _make_dir_fixture(root: Path, *, files: int, bytes_per_file: int, fanout: int) -> Path:
    in_dir = root / "in"
    in_dir.mkdir(parents=True, exist_ok=True)
    for i in range(files):
        sub = in_dir / f"d{i % fanout:02d}"
        sub.mkdir(parents=True, exist_ok=True)
        _write_bytes(sub / f"f{i:06d}.txt", bytes_per_file)
    return in_dir


def _make_zip_fixture(root: Path, *, members: int, bytes_per_member: int, fanout: int) -> Path:
    zip_path = root / "in.zip"
    payload = b"a" * bytes_per_member
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for i in range(members):
            zf.writestr(f"d{i % fanout:02d}/m{i:06d}.txt", payload)
    return zip_path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="bench_sanitize.py")
    p.add_argument("--kind", choices=["dir", "zip"], required=True)
    p.add_argument("--count", type=int, default=10_000, help="files (dir) or members (zip)")
    p.add_argument("--bytes", type=int, default=256, dest="bytes_per", help="bytes per file/member")
    p.add_argument("--fanout", type=int, default=32, help="number of subdirs used for the fixture")
    p.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="avoid writing sanitized outputs (default: true)",
    )
    args = p.parse_args(argv)

    root = Path(os.environ.get("TMPDIR", "/tmp")) / f"file-sanitizer-bench-{os.getpid()}"
    root.mkdir(parents=True, exist_ok=True)

    if args.kind == "dir":
        input_path = _make_dir_fixture(
            root, files=int(args.count), bytes_per_file=int(args.bytes_per), fanout=int(args.fanout)
        )
    else:
        input_path = _make_zip_fixture(
            root,
            members=int(args.count),
            bytes_per_member=int(args.bytes_per),
            fanout=int(args.fanout),
        )

    out_dir = root / "out"
    report = root / "report.jsonl"

    t0 = time.perf_counter()
    rc = sanitize_path(
        input_path,
        out_dir,
        report,
        options=SanitizeOptions(dry_run=bool(args.dry_run)),
    )
    dt = time.perf_counter() - t0

    result = {
        "kind": str(args.kind),
        "count": int(args.count),
        "bytes_per": int(args.bytes_per),
        "dry_run": bool(args.dry_run),
        "exit_code": int(rc),
        "seconds": float(dt),
        "report_bytes": int(report.stat().st_size) if report.exists() else 0,
    }
    print(json.dumps(result, sort_keys=True))
    return int(rc)


if __name__ == "__main__":
    raise SystemExit(main())
