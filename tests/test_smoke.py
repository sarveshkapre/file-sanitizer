from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_help() -> None:
    proc = subprocess.run([sys.executable, "-m", "file_sanitizer", "--help"], check=False)
    assert proc.returncode == 0


def test_cli_report_summary(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    (input_dir / "a.txt").write_text("hello", encoding="utf-8")

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "file_sanitizer",
            "sanitize",
            "--input",
            str(input_dir),
            "--out",
            str(out_dir),
            "--report",
            str(report),
            "--dry-run",
            "--report-summary",
        ],
        check=False,
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert report.exists()

    lines = report.read_text(encoding="utf-8").strip().splitlines()
    summary = json.loads(lines[-1])
    assert summary["type"] == "summary"
    assert summary["dry_run"] is True
