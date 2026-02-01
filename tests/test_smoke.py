from __future__ import annotations

import subprocess
import sys


def test_help() -> None:
    proc = subprocess.run([sys.executable, "-m", "file_sanitizer", "--help"], check=False)
    assert proc.returncode == 0
