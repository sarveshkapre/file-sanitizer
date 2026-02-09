from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from PIL import Image
from pypdf import PdfReader

from file_sanitizer.sanitizer import sanitize_path


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_fixture_inputs_are_intentionally_risky() -> None:
    image_path = FIXTURES_DIR / "exif-photo.jpg"
    with Image.open(image_path) as img:
        assert len(img.getexif()) > 0

    pdf_path = FIXTURES_DIR / "risky.pdf"
    reader = PdfReader(str(pdf_path))
    assert reader.metadata is not None
    assert reader.metadata.get("/Author") == "fixture-author"
    root_ref = reader.trailer.get("/Root")
    assert root_ref is not None
    root = root_ref.get_object()
    assert "/OpenAction" in root


def test_fixture_zip_regression_flow(tmp_path: Path) -> None:
    input_zip = FIXTURES_DIR / "mixed-bundle.zip"
    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"

    rc = sanitize_path(input_zip, out_dir, report)
    assert rc == 0

    output_zip = out_dir / input_zip.name
    assert output_zip.exists()

    item = json.loads(report.read_text(encoding="utf-8").strip())
    warnings = item["warnings"]
    assert any("unsafe path" in warning for warning in warnings)
    assert any("symlink" in warning for warning in warnings)

    with zipfile.ZipFile(output_zip, "r") as zip_in:
        names = set(zip_in.namelist())
        assert "images/exif-photo.jpg" in names
        assert "pdfs/risky.pdf" in names
        assert "docs/readme.txt" in names
        assert "../escape.txt" not in names
        assert "docs/link" not in names

        with Image.open(io.BytesIO(zip_in.read("images/exif-photo.jpg"))) as image:
            assert len(image.getexif()) == 0

        reader = PdfReader(io.BytesIO(zip_in.read("pdfs/risky.pdf")))
        metadata = reader.metadata
        assert metadata is not None
        assert metadata.get("/Author") is None
