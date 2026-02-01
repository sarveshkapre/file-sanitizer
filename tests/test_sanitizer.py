from __future__ import annotations

import json
from pathlib import Path

from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, TextStringObject

from file_sanitizer.sanitizer import SanitizeOptions, sanitize_path


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


def test_pdf_risk_scan_warns_on_openaction_javascript(tmp_path: Path) -> None:
    pdf_path = tmp_path / "test.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer._root_object.update(  # noqa: SLF001
        {
            NameObject("/OpenAction"): DictionaryObject(
                {
                    NameObject("/S"): NameObject("/JavaScript"),
                    NameObject("/JS"): TextStringObject("app.alert('hi')"),
                }
            )
        }
    )
    with pdf_path.open("wb") as fh:
        writer.write(fh)

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"
    sanitize_path(pdf_path, out_dir, report)

    report_text = report.read_text(encoding="utf-8")
    assert "/OpenAction" in report_text
    assert "/JavaScript" in report_text


def test_directory_input_preserves_structure(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    (input_dir / "nested").mkdir(parents=True)
    img_path = input_dir / "nested" / "x.png"
    Image.new("RGB", (4, 4), color="blue").save(img_path)

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"
    sanitize_path(input_dir, out_dir, report)

    assert (out_dir / "nested" / "x.png").exists()


def test_flat_output_dedupes_names(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    (input_dir / "a").mkdir(parents=True)
    (input_dir / "b").mkdir(parents=True)

    (input_dir / "a" / "dup.txt").write_text("one", encoding="utf-8")
    (input_dir / "b" / "dup.txt").write_text("two", encoding="utf-8")

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"
    sanitize_path(
        input_dir,
        out_dir,
        report,
        options=SanitizeOptions(flat_output=True, copy_unsupported=True),
    )

    outputs = sorted(p.name for p in out_dir.glob("dup*.txt"))
    assert len(outputs) == 2
    assert "dup.txt" in outputs
    assert any(name.startswith("dup-") for name in outputs)


def test_skip_unsupported_when_configured(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    (input_dir / "note.txt").write_text("hello", encoding="utf-8")

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"
    sanitize_path(
        input_dir,
        out_dir,
        report,
        options=SanitizeOptions(copy_unsupported=False),
    )

    assert not (out_dir / "note.txt").exists()
    assert report.read_text(encoding="utf-8").strip() != ""


def test_dry_run_does_not_write_outputs(tmp_path: Path) -> None:
    img_path = tmp_path / "test.jpg"
    Image.new("RGB", (10, 10), color="red").save(img_path)

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"
    rc = sanitize_path(
        img_path,
        out_dir,
        report,
        options=SanitizeOptions(dry_run=True),
    )
    assert rc == 0
    assert not (out_dir / "test.jpg").exists()

    report_text = report.read_text(encoding="utf-8")
    assert "would_image_sanitize" in report_text


def test_dry_run_does_not_create_out_dir_when_report_elsewhere(tmp_path: Path) -> None:
    img_path = tmp_path / "test.jpg"
    Image.new("RGB", (10, 10), color="red").save(img_path)

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"
    rc = sanitize_path(
        img_path,
        out_dir,
        report,
        options=SanitizeOptions(dry_run=True),
    )
    assert rc == 0
    assert not out_dir.exists()


def test_flat_output_dry_run_dedupes_names(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    (input_dir / "a").mkdir(parents=True)
    (input_dir / "b").mkdir(parents=True)
    (input_dir / "a" / "dup.txt").write_text("one", encoding="utf-8")
    (input_dir / "b" / "dup.txt").write_text("two", encoding="utf-8")

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"
    rc = sanitize_path(
        input_dir,
        out_dir,
        report,
        options=SanitizeOptions(flat_output=True, copy_unsupported=True, dry_run=True),
    )
    assert rc == 0

    output_paths = []
    for line in report.read_text(encoding="utf-8").splitlines():
        obj = json.loads(line)
        if obj.get("output_path"):
            output_paths.append(obj["output_path"])
    assert len(output_paths) == 2
    assert len(set(output_paths)) == 2
