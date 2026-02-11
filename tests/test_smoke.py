from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import zipfile
from datetime import datetime
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
    assert "warnings" in summary
    assert "errors" in summary
    assert "tool_version" in summary
    assert "options" in summary
    assert "started_at" in summary
    assert "ended_at" in summary
    datetime.fromisoformat(summary["started_at"])
    datetime.fromisoformat(summary["ended_at"])


def test_cli_report_stdout_dash_writes_to_stdout_and_does_not_create_dash_file(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    (input_dir / "a.txt").write_text("hello", encoding="utf-8")

    out_dir = tmp_path / "out"

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
            "-",
            "--dry-run",
            "--report-summary",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert proc.returncode == 0
    assert not (tmp_path / "-").exists()

    lines = proc.stdout.strip().splitlines()
    assert len(lines) >= 2
    summary = json.loads(lines[-1])
    assert summary["type"] == "summary"
    assert summary["dry_run"] is True
    assert "wrote report to stdout" in proc.stderr
    assert "tool_version" in summary


def test_cli_quiet_suppresses_stderr_summary(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    (input_dir / "a.txt").write_text("hello", encoding="utf-8")

    out_dir = tmp_path / "out"
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
            "-",
            "--dry-run",
            "--quiet",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert proc.returncode == 0
    assert proc.stderr.strip() == ""
    assert proc.stdout.strip() != ""


def test_cli_fail_on_warnings_sets_nonzero_exit(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    (input_dir / "a.txt").write_text("hello", encoding="utf-8")

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"

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
            "--fail-on-warnings",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 3


def test_cli_risky_policy_block_blocks_outputs(tmp_path: Path) -> None:
    input_zip = tmp_path / "bundle.zip"

    with zipfile.ZipFile(input_zip, "w") as zf:
        zf.writestr("docs/note.txt", "hello")

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "file_sanitizer",
            "sanitize",
            "--input",
            str(input_zip),
            "--out",
            str(out_dir),
            "--report",
            str(report),
            "--risky-policy",
            "block",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 2
    item = json.loads(report.read_text(encoding="utf-8").strip().splitlines()[0])
    assert item["action"] == "blocked"


def test_cli_nested_archive_sanitize_policy_flags(tmp_path: Path) -> None:
    input_zip = tmp_path / "bundle.zip"

    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as inner_zip:
        inner_zip.writestr("nested.txt", "ok")

    with zipfile.ZipFile(input_zip, "w") as zf:
        zf.writestr("nested/inner.zip", inner.getvalue())

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "file_sanitizer",
            "sanitize",
            "--input",
            str(input_zip),
            "--out",
            str(out_dir),
            "--report",
            str(report),
            "--nested-archive-policy",
            "sanitize",
            "--nested-archive-max-depth",
            "2",
            "--nested-archive-max-total-bytes",
            "4096",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0
    with zipfile.ZipFile(out_dir / "bundle.zip", "r") as zf:
        assert "nested/inner.zip" in set(zf.namelist())
