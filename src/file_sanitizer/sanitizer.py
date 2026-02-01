from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image
from pypdf import PdfReader, PdfWriter


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
PDF_EXTS = {".pdf"}


@dataclass(frozen=True)
class ReportItem:
    input_path: str
    output_path: str
    action: str
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_path": self.input_path,
            "output_path": self.output_path,
            "action": self.action,
            "warnings": self.warnings,
        }


def sanitize_path(input_path: Path, out_dir: Path, report_path: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    items: list[ReportItem] = []
    if input_path.is_dir():
        for file in input_path.rglob("*"):
            if file.is_file():
                items.append(_sanitize_file(file, out_dir / file.name))
    else:
        items.append(_sanitize_file(input_path, out_dir / input_path.name))

    with report_path.open("w", encoding="utf-8") as out:
        for item in items:
            out.write(json.dumps(item.to_dict()) + "\n")
    print(f"wrote {report_path}")
    return 0


def _sanitize_file(input_path: Path, output_path: Path) -> ReportItem:
    suffix = input_path.suffix.lower()
    warnings: list[str] = []
    if suffix in IMAGE_EXTS:
        _sanitize_image(input_path, output_path)
        return ReportItem(str(input_path), str(output_path), "image_sanitized", warnings)
    if suffix in PDF_EXTS:
        _sanitize_pdf(input_path, output_path)
        return ReportItem(str(input_path), str(output_path), "pdf_sanitized", warnings)

    shutil.copy2(input_path, output_path)
    warnings.append("unsupported file type; copied as-is")
    return ReportItem(str(input_path), str(output_path), "copied", warnings)


def _sanitize_image(input_path: Path, output_path: Path) -> None:
    with Image.open(input_path) as img:
        data = img.copy()
        data.save(output_path, exif=b"", icc_profile=None)


def _sanitize_pdf(input_path: Path, output_path: Path) -> None:
    reader = PdfReader(str(input_path))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.add_metadata({})
    with output_path.open("wb") as fh:
        writer.write(fh)
