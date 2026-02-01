from __future__ import annotations

from pathlib import Path

from PIL import Image
from pypdf import PdfWriter

from file_sanitizer.sanitizer import sanitize_path


def test_sanitize_image(tmp_path: Path) -> None:
    img_path = tmp_path / "test.jpg"
    img = Image.new("RGB", (10, 10), color="red")
    img.save(img_path)

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"
    sanitize_path(img_path, out_dir, report)
    assert (out_dir / "test.jpg").exists()


def test_sanitize_pdf(tmp_path: Path) -> None:
    pdf_path = tmp_path / "test.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with pdf_path.open("wb") as fh:
        writer.write(fh)

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"
    sanitize_path(pdf_path, out_dir, report)
    assert (out_dir / "test.pdf").exists()
