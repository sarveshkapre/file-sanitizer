from __future__ import annotations

import io
import json
import stat
import zipfile
from pathlib import Path

from PIL import Image
from pypdf import PdfReader, PdfWriter
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


def test_out_dir_inside_input_does_not_reprocess_outputs(tmp_path: Path) -> None:
    root = tmp_path / "root"
    input_dir = root / "in"
    input_dir.mkdir(parents=True)
    (input_dir / "a.txt").write_text("hello", encoding="utf-8")

    out_dir = input_dir / "out"
    report = root / "report.jsonl"
    rc = sanitize_path(
        input_dir,
        out_dir,
        report,
        options=SanitizeOptions(copy_unsupported=True, dry_run=False),
    )
    assert rc == 0

    # If outputs were re-processed during traversal, we'd likely see nested out/out/...
    assert not (out_dir / "out").exists()


def test_exclude_by_segment_skips_matching_dir(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    (input_dir / "skip").mkdir(parents=True)
    (input_dir / "keep").mkdir(parents=True)
    (input_dir / "skip" / "a.txt").write_text("nope", encoding="utf-8")
    (input_dir / "keep" / "b.txt").write_text("ok", encoding="utf-8")

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"
    rc = sanitize_path(
        input_dir,
        out_dir,
        report,
        options=SanitizeOptions(copy_unsupported=True, exclude_globs=["skip"]),
    )
    assert rc == 0
    assert not (out_dir / "skip" / "a.txt").exists()
    assert (out_dir / "keep" / "b.txt").exists()

    report_text = report.read_text(encoding="utf-8")
    assert '"action": "excluded"' in report_text


def test_exclude_by_path_glob_skips_matching_files(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    (input_dir / "docs").mkdir(parents=True)
    (input_dir / "docs" / "a.txt").write_text("nope", encoding="utf-8")
    (input_dir / "docs" / "b.md").write_text("ok", encoding="utf-8")

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"
    rc = sanitize_path(
        input_dir,
        out_dir,
        report,
        options=SanitizeOptions(copy_unsupported=True, exclude_globs=["docs/*.txt"]),
    )
    assert rc == 0
    assert not (out_dir / "docs" / "a.txt").exists()
    assert (out_dir / "docs" / "b.md").exists()


def test_directory_report_order_is_deterministic(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    (input_dir / "b").mkdir(parents=True)
    (input_dir / "a").mkdir(parents=True)
    (input_dir / "b" / "z.txt").write_text("z", encoding="utf-8")
    (input_dir / "a" / "y.txt").write_text("y", encoding="utf-8")
    (input_dir / "a" / "x.txt").write_text("x", encoding="utf-8")

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"
    rc = sanitize_path(input_dir, out_dir, report)
    assert rc == 0

    rel_paths = [
        Path(json.loads(line)["input_path"]).relative_to(input_dir).as_posix()
        for line in report.read_text(encoding="utf-8").splitlines()
    ]
    assert rel_paths == sorted(rel_paths)


def test_zip_sanitize_sanitizes_members_and_skips_unsafe_entries(tmp_path: Path) -> None:
    zip_path = tmp_path / "bundle.zip"

    img = Image.new("RGB", (10, 10), color="red")
    img_buf = io.BytesIO()
    img.save(img_buf, format="JPEG")

    pdf_writer = PdfWriter()
    pdf_writer.add_blank_page(width=72, height=72)
    pdf_writer.add_metadata({"/Author": "alice"})
    pdf_writer._root_object.update(  # noqa: SLF001
        {
            NameObject("/OpenAction"): DictionaryObject(
                {
                    NameObject("/S"): NameObject("/JavaScript"),
                    NameObject("/JS"): TextStringObject("app.alert('hi')"),
                }
            )
        }
    )
    pdf_buf = io.BytesIO()
    pdf_writer.write(pdf_buf)

    with zipfile.ZipFile(zip_path, "w") as zip_out:
        zip_out.writestr("docs/note.txt", "hello")
        zip_out.writestr("images/photo.jpg", img_buf.getvalue())
        zip_out.writestr("pdfs/doc.pdf", pdf_buf.getvalue())
        zip_out.writestr("../escape.txt", "nope")

        symlink = zipfile.ZipInfo("docs/link")
        symlink.create_system = 3
        symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
        zip_out.writestr(symlink, "note.txt")

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"
    rc = sanitize_path(zip_path, out_dir, report)
    assert rc == 0

    out_zip = out_dir / "bundle.zip"
    assert out_zip.exists()

    line = json.loads(report.read_text(encoding="utf-8").strip())
    warnings = line["warnings"]
    assert any("unsafe path" in warning for warning in warnings)
    assert any("symlink" in warning for warning in warnings)
    assert any("unsupported; copied as-is" in warning for warning in warnings)
    assert any("/OpenAction" in warning for warning in warnings)

    with zipfile.ZipFile(out_zip, "r") as zip_in:
        names = set(zip_in.namelist())
        assert "images/photo.jpg" in names
        assert "pdfs/doc.pdf" in names
        assert "docs/note.txt" in names
        assert "../escape.txt" not in names
        assert "docs/link" not in names

        with Image.open(io.BytesIO(zip_in.read("images/photo.jpg"))) as sanitized_img:
            assert len(sanitized_img.getexif()) == 0

        reader = PdfReader(io.BytesIO(zip_in.read("pdfs/doc.pdf")))
        metadata = reader.metadata
        assert metadata is not None
        assert metadata.get("/Author") is None
        root_ref = reader.trailer.get("/Root")
        assert root_ref is not None
        root = root_ref.get_object()
        assert "/OpenAction" not in root


def test_zip_respects_copy_unsupported_false(tmp_path: Path) -> None:
    zip_path = tmp_path / "bundle.zip"
    with zipfile.ZipFile(zip_path, "w") as zip_out:
        zip_out.writestr("docs/note.txt", "hello")

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"
    rc = sanitize_path(
        zip_path,
        out_dir,
        report,
        options=SanitizeOptions(copy_unsupported=False),
    )
    assert rc == 0

    out_zip = out_dir / "bundle.zip"
    assert out_zip.exists()
    with zipfile.ZipFile(out_zip, "r") as zip_in:
        assert zip_in.namelist() == []

    warnings = json.loads(report.read_text(encoding="utf-8").strip())["warnings"]
    assert any("unsupported; skipped" in warning for warning in warnings)


def test_zip_dry_run_does_not_write_outputs(tmp_path: Path) -> None:
    zip_path = tmp_path / "bundle.zip"
    with zipfile.ZipFile(zip_path, "w") as zip_out:
        zip_out.writestr("docs/note.txt", "hello")

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"
    rc = sanitize_path(
        zip_path,
        out_dir,
        report,
        options=SanitizeOptions(dry_run=True),
    )
    assert rc == 0
    assert not (out_dir / "bundle.zip").exists()
    assert "would_zip_sanitize" in report.read_text(encoding="utf-8")
