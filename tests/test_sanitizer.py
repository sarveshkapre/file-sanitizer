from __future__ import annotations

import io
import json
import stat
import zipfile
from pathlib import Path

import pytest
from PIL import Image, TiffImagePlugin
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject, TextStringObject

from file_sanitizer.sanitizer import REPORT_VERSION, SanitizeOptions, sanitize_path


def _warning_messages(warnings: list[dict[str, object]]) -> list[str]:
    return [str(w.get("message", "")) for w in warnings]


def test_sanitize_image(tmp_path: Path) -> None:
    img_path = tmp_path / "test.jpg"
    img = Image.new("RGB", (10, 10), color="red")
    img.save(img_path)

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"
    sanitize_path(img_path, out_dir, report)
    assert (out_dir / "test.jpg").exists()

    item = json.loads(report.read_text(encoding="utf-8").strip())
    assert item["report_version"] == REPORT_VERSION


def test_sanitize_tiff_strips_common_tags(tmp_path: Path) -> None:
    img_path = tmp_path / "test.tiff"
    img = Image.new("RGB", (10, 10), color="red")
    info = TiffImagePlugin.ImageFileDirectory_v2()
    info[270] = "secret-desc"
    img.save(img_path, format="TIFF", tiffinfo=info)

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"
    sanitize_path(img_path, out_dir, report)
    out_path = out_dir / "test.tiff"
    assert out_path.exists()

    with Image.open(out_path) as out_img:
        assert out_img.tag_v2.get(270) is None


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


def test_risky_policy_block_blocks_risky_pdf_output(tmp_path: Path) -> None:
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
    rc = sanitize_path(
        pdf_path,
        out_dir,
        report,
        options=SanitizeOptions(risky_policy="block"),
    )
    assert rc == 2
    assert not (out_dir / "test.pdf").exists()

    item = json.loads(report.read_text(encoding="utf-8").strip())
    assert item["action"] == "blocked"
    codes = {w["code"] for w in item["warnings"]}
    assert "policy_blocked" in codes
    assert "pdf_risk_open_action" in codes


def test_directory_input_preserves_structure(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    (input_dir / "nested").mkdir(parents=True)
    img_path = input_dir / "nested" / "x.png"
    Image.new("RGB", (4, 4), color="blue").save(img_path)

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"
    sanitize_path(input_dir, out_dir, report)

    assert (out_dir / "nested" / "x.png").exists()


def test_directory_max_files_truncates(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    (input_dir / "a.txt").write_text("a", encoding="utf-8")
    (input_dir / "b.txt").write_text("b", encoding="utf-8")
    (input_dir / "c.txt").write_text("c", encoding="utf-8")

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"
    rc = sanitize_path(
        input_dir,
        out_dir,
        report,
        options=SanitizeOptions(max_files=2),
    )
    assert rc == 0

    lines = report.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    last = json.loads(lines[-1])
    assert last["action"] == "truncated"
    codes = {w["code"] for w in last["warnings"]}
    assert "traversal_limit_reached" in codes

    assert (out_dir / "a.txt").exists()
    assert (out_dir / "b.txt").exists()
    assert not (out_dir / "c.txt").exists()


def test_directory_max_bytes_truncates(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    (input_dir / "a.txt").write_text("a" * 10, encoding="utf-8")
    (input_dir / "b.txt").write_text("b" * 10, encoding="utf-8")

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"
    rc = sanitize_path(
        input_dir,
        out_dir,
        report,
        options=SanitizeOptions(max_bytes=15),
    )
    assert rc == 0

    lines = report.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    last = json.loads(lines[-1])
    assert last["action"] == "truncated"

    assert (out_dir / "a.txt").exists()
    assert not (out_dir / "b.txt").exists()


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


def _make_ooxml_like_zip(path: Path, *, with_vba_project: bool) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("word/document.xml", "<w:document/>")
        if with_vba_project:
            zf.writestr("word/vbaProject.bin", b"not-a-real-vba")


def test_office_macro_enabled_extension_warns(tmp_path: Path) -> None:
    docm = tmp_path / "macro.docm"
    _make_ooxml_like_zip(docm, with_vba_project=True)

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"
    rc = sanitize_path(docm, out_dir, report)
    assert rc == 0

    assert (out_dir / "macro.docm").exists()
    item = json.loads(report.read_text(encoding="utf-8").strip())
    codes = {w["code"] for w in item["warnings"]}
    assert "office_macro_enabled" in codes
    assert "office_macro_indicator_vbaproject" in codes


def test_office_docx_with_vbaproject_warns(tmp_path: Path) -> None:
    docx = tmp_path / "has-macro.docx"
    _make_ooxml_like_zip(docx, with_vba_project=True)

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"
    rc = sanitize_path(docx, out_dir, report)
    assert rc == 0

    assert (out_dir / "has-macro.docx").exists()
    item = json.loads(report.read_text(encoding="utf-8").strip())
    codes = {w["code"] for w in item["warnings"]}
    assert "office_macro_indicator_vbaproject" in codes


def test_content_type_sniffing_sanitizes_pdf_even_with_wrong_extension(tmp_path: Path) -> None:
    pdf_path = tmp_path / "not-a-pdf-extension.txt"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with pdf_path.open("wb") as fh:
        writer.write(fh)

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"
    rc = sanitize_path(pdf_path, out_dir, report)
    assert rc == 0
    assert (out_dir / "not-a-pdf-extension.txt").exists()

    item = json.loads(report.read_text(encoding="utf-8").strip())
    assert item["action"] == "pdf_sanitized"
    codes = {w["code"] for w in item["warnings"]}
    assert "content_type_detected" in codes


def test_content_type_sniffing_avoids_parsing_non_pdf_with_pdf_extension(tmp_path: Path) -> None:
    fake_pdf = tmp_path / "fake.pdf"
    fake_pdf.write_text("not really a pdf", encoding="utf-8")

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"
    rc = sanitize_path(fake_pdf, out_dir, report)
    assert rc == 0
    assert (out_dir / "fake.pdf").exists()

    item = json.loads(report.read_text(encoding="utf-8").strip())
    assert item["action"] == "copied"
    codes = {w["code"] for w in item["warnings"]}
    assert "content_type_mismatch" in codes


def test_content_type_sniffing_sanitizes_zip_even_with_wrong_extension(tmp_path: Path) -> None:
    disguised = tmp_path / "bundle.dat"
    with zipfile.ZipFile(disguised, "w") as zf:
        zf.writestr("docs/note.txt", "hello")

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"
    rc = sanitize_path(disguised, out_dir, report)
    assert rc == 0
    assert (out_dir / "bundle.dat").exists()

    item = json.loads(report.read_text(encoding="utf-8").strip())
    assert item["action"] == "zip_sanitized"
    codes = {w["code"] for w in item["warnings"]}
    assert "content_type_detected" in codes


def test_content_type_sniffing_detects_ooxml_inside_zip_container(tmp_path: Path) -> None:
    disguised = tmp_path / "macro.bin"
    _make_ooxml_like_zip(disguised, with_vba_project=True)

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"
    rc = sanitize_path(disguised, out_dir, report)
    assert rc == 0
    assert (out_dir / "macro.bin").exists()

    item = json.loads(report.read_text(encoding="utf-8").strip())
    assert item["action"] == "copied"
    codes = {w["code"] for w in item["warnings"]}
    assert "content_type_detected_ooxml" in codes
    assert "office_macro_indicator_vbaproject" in codes


def test_zip_member_office_macro_enabled_warns(tmp_path: Path) -> None:
    office_payload = io.BytesIO()
    with zipfile.ZipFile(office_payload, "w") as zf:
        zf.writestr("word/document.xml", "<w:document/>")

    outer = tmp_path / "outer.zip"
    with zipfile.ZipFile(outer, "w") as zip_out:
        zip_out.writestr("docs/macro.docm", office_payload.getvalue())

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"
    rc = sanitize_path(outer, out_dir, report)
    assert rc == 0

    item = json.loads(report.read_text(encoding="utf-8").strip())
    warnings = item["warnings"]
    assert any(w["code"] == "office_macro_enabled" for w in warnings)
    assert any("zip entry 'docs/macro.docm'" in str(w["message"]) for w in warnings)


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


def test_exclude_prunes_directory_children_from_traversal(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    (input_dir / "skip").mkdir(parents=True)
    (input_dir / "keep").mkdir(parents=True)
    (input_dir / "skip" / "a.txt").write_text("nope", encoding="utf-8")
    (input_dir / "skip" / "b.txt").write_text("nope2", encoding="utf-8")
    (input_dir / "keep" / "c.txt").write_text("ok", encoding="utf-8")

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"
    rc = sanitize_path(
        input_dir,
        out_dir,
        report,
        options=SanitizeOptions(copy_unsupported=True, exclude_globs=["skip"]),
    )
    assert rc == 0

    rels = [
        Path(json.loads(line)["input_path"]).relative_to(input_dir).as_posix()
        for line in report.read_text(encoding="utf-8").splitlines()
    ]
    assert "skip" in rels
    assert "skip/a.txt" not in rels
    assert "skip/b.txt" not in rels


def test_allow_ext_skips_non_allowlisted_files(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    input_dir.mkdir(parents=True)
    (input_dir / "a.txt").write_text("nope", encoding="utf-8")

    img = Image.new("RGB", (10, 10), color="red")
    (input_dir / "b.jpg").parent.mkdir(parents=True, exist_ok=True)
    img.save(input_dir / "b.jpg", format="JPEG")

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"
    rc = sanitize_path(
        input_dir,
        out_dir,
        report,
        options=SanitizeOptions(copy_unsupported=True, allow_exts=[".jpg"]),
    )
    assert rc == 0
    assert not (out_dir / "a.txt").exists()
    assert (out_dir / "b.jpg").exists()

    items = [json.loads(line) for line in report.read_text(encoding="utf-8").splitlines()]
    skipped = [i for i in items if i["input_path"].endswith("a.txt")][0]
    assert skipped["action"] == "skipped"
    assert [w["code"] for w in skipped["warnings"]] == ["allowlist_skipped"]


def test_allow_ext_allows_unsupported_copy_when_allowlisted(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    input_dir.mkdir(parents=True)
    (input_dir / "a.txt").write_text("ok", encoding="utf-8")

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"
    rc = sanitize_path(
        input_dir,
        out_dir,
        report,
        options=SanitizeOptions(copy_unsupported=True, allow_exts=[".txt"]),
    )
    assert rc == 0
    assert (out_dir / "a.txt").exists()


def test_allow_ext_applies_to_zip_members(tmp_path: Path) -> None:
    zip_path = tmp_path / "bundle.zip"

    img = Image.new("RGB", (10, 10), color="red")
    img_buf = io.BytesIO()
    img.save(img_buf, format="JPEG")

    with zipfile.ZipFile(zip_path, "w") as zip_out:
        zip_out.writestr("docs/note.txt", "hello")
        zip_out.writestr("images/photo.jpg", img_buf.getvalue())

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"
    rc = sanitize_path(
        zip_path,
        out_dir,
        report,
        options=SanitizeOptions(copy_unsupported=True, allow_exts=[".jpg"]),
    )
    assert rc == 0

    out_zip = out_dir / "bundle.zip"
    assert out_zip.exists()
    with zipfile.ZipFile(out_zip, "r") as zip_in:
        names = set(zip_in.namelist())
    assert "images/photo.jpg" in names
    assert "docs/note.txt" not in names

    zip_item = [json.loads(line) for line in report.read_text(encoding="utf-8").splitlines()][0]
    codes = [w["code"] for w in zip_item["warnings"]]
    assert "allowlist_skipped" in codes


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
    messages = _warning_messages(line["warnings"])
    assert any("unsafe path" in message for message in messages)
    assert any("symlink" in message for message in messages)
    assert any("unsupported; copied as-is" in message for message in messages)
    assert any("/OpenAction" in message for message in messages)

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
    assert any("unsupported; skipped" in message for message in _warning_messages(warnings))


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


def test_risky_policy_block_blocks_risky_zip_output(tmp_path: Path) -> None:
    zip_path = tmp_path / "bundle.zip"
    with zipfile.ZipFile(zip_path, "w") as zip_out:
        zip_out.writestr("docs/note.txt", "hello")

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"
    rc = sanitize_path(
        zip_path,
        out_dir,
        report,
        options=SanitizeOptions(risky_policy="block"),
    )
    assert rc == 2
    assert not (out_dir / "bundle.zip").exists()

    item = json.loads(report.read_text(encoding="utf-8").strip())
    assert item["action"] == "blocked"
    codes = {w["code"] for w in item["warnings"]}
    assert "policy_blocked" in codes
    assert "zip_entry_unsupported_copied" in codes


def test_zip_guardrail_limits_member_count(tmp_path: Path) -> None:
    zip_path = tmp_path / "bundle.zip"
    with zipfile.ZipFile(zip_path, "w") as zip_out:
        zip_out.writestr("a.txt", "a")
        zip_out.writestr("b.txt", "b")
        zip_out.writestr("c.txt", "c")

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"
    rc = sanitize_path(
        zip_path,
        out_dir,
        report,
        options=SanitizeOptions(zip_max_members=2),
    )
    assert rc == 0

    output_zip = out_dir / "bundle.zip"
    with zipfile.ZipFile(output_zip, "r") as zip_in:
        assert set(zip_in.namelist()) == {"a.txt", "b.txt"}

    warnings = json.loads(report.read_text(encoding="utf-8").strip())["warnings"]
    assert any(
        "processing limited to 2 by policy" in message for message in _warning_messages(warnings)
    )


def test_zip_guardrail_skips_large_member(tmp_path: Path) -> None:
    zip_path = tmp_path / "bundle.zip"
    with zipfile.ZipFile(zip_path, "w") as zip_out:
        zip_out.writestr("big.txt", "0123456789")

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"
    rc = sanitize_path(
        zip_path,
        out_dir,
        report,
        options=SanitizeOptions(zip_max_member_uncompressed_bytes=5),
    )
    assert rc == 0

    output_zip = out_dir / "bundle.zip"
    with zipfile.ZipFile(output_zip, "r") as zip_in:
        assert zip_in.namelist() == []

    warnings = json.loads(report.read_text(encoding="utf-8").strip())["warnings"]
    assert any(
        "expanded size 10 exceeds limit 5; skipped" in message
        for message in _warning_messages(warnings)
    )


def test_zip_guardrail_limits_total_expanded_bytes(tmp_path: Path) -> None:
    zip_path = tmp_path / "bundle.zip"
    with zipfile.ZipFile(zip_path, "w") as zip_out:
        zip_out.writestr("a.txt", "123456")
        zip_out.writestr("b.txt", "abcdef")

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"
    rc = sanitize_path(
        zip_path,
        out_dir,
        report,
        options=SanitizeOptions(zip_max_total_uncompressed_bytes=10),
    )
    assert rc == 0

    output_zip = out_dir / "bundle.zip"
    with zipfile.ZipFile(output_zip, "r") as zip_in:
        assert zip_in.namelist() == ["a.txt"]

    warnings = json.loads(report.read_text(encoding="utf-8").strip())["warnings"]
    assert any(
        "zip expanded size limit exceeded (10 bytes)" in message
        for message in _warning_messages(warnings)
    )


def test_zip_guardrail_skips_high_compression_ratio(tmp_path: Path) -> None:
    zip_path = tmp_path / "bundle.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zip_out:
        zip_out.writestr("bomb.txt", b"0" * 50_000)

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"
    rc = sanitize_path(
        zip_path,
        out_dir,
        report,
        options=SanitizeOptions(zip_max_compression_ratio=2.0),
    )
    assert rc == 0

    output_zip = out_dir / "bundle.zip"
    with zipfile.ZipFile(output_zip, "r") as zip_in:
        assert zip_in.namelist() == []

    warnings = json.loads(report.read_text(encoding="utf-8").strip())["warnings"]
    assert any(
        "compression ratio" in message and "exceeds limit 2.0" in message
        for message in _warning_messages(warnings)
    )


def test_zip_nested_archive_default_policy_skips_member(tmp_path: Path) -> None:
    inner_buf = io.BytesIO()
    with zipfile.ZipFile(inner_buf, "w") as nested_zip:
        nested_zip.writestr("nested.txt", "hello")

    outer_path = tmp_path / "outer.zip"
    with zipfile.ZipFile(outer_path, "w") as zip_out:
        zip_out.writestr("nested/inner.zip", inner_buf.getvalue())
        zip_out.writestr("docs/note.txt", "ok")

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"
    rc = sanitize_path(outer_path, out_dir, report)
    assert rc == 0

    with zipfile.ZipFile(out_dir / "outer.zip", "r") as zip_in:
        names = set(zip_in.namelist())
        assert "docs/note.txt" in names
        assert "nested/inner.zip" not in names

    warnings = json.loads(report.read_text(encoding="utf-8").strip())["warnings"]
    assert any(
        "nested archive; skipped by policy" in message for message in _warning_messages(warnings)
    )


def test_zip_nested_archive_copy_policy_keeps_member(tmp_path: Path) -> None:
    inner_buf = io.BytesIO()
    with zipfile.ZipFile(inner_buf, "w") as nested_zip:
        nested_zip.writestr("nested.txt", "hello")

    outer_path = tmp_path / "outer.zip"
    with zipfile.ZipFile(outer_path, "w") as zip_out:
        zip_out.writestr("nested/inner.zip", inner_buf.getvalue())
        zip_out.writestr("docs/note.txt", "ok")

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"
    rc = sanitize_path(
        outer_path,
        out_dir,
        report,
        options=SanitizeOptions(nested_archive_policy="copy"),
    )
    assert rc == 0

    with zipfile.ZipFile(out_dir / "outer.zip", "r") as zip_in:
        names = set(zip_in.namelist())
        assert "docs/note.txt" in names
        assert "nested/inner.zip" in names

    warnings = json.loads(report.read_text(encoding="utf-8").strip())["warnings"]
    assert any(
        "nested archive; copied by policy" in message for message in _warning_messages(warnings)
    )


def test_zip_guardrails_apply_in_dry_run(tmp_path: Path) -> None:
    inner_buf = io.BytesIO()
    with zipfile.ZipFile(inner_buf, "w") as nested_zip:
        nested_zip.writestr("nested.txt", "hello")

    zip_path = tmp_path / "bundle.zip"
    with zipfile.ZipFile(zip_path, "w") as zip_out:
        zip_out.writestr("nested/inner.zip", inner_buf.getvalue())

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"
    rc = sanitize_path(zip_path, out_dir, report, options=SanitizeOptions(dry_run=True))
    assert rc == 0
    assert not (out_dir / "bundle.zip").exists()

    warnings = json.loads(report.read_text(encoding="utf-8").strip())["warnings"]
    assert any(
        "nested archive; skipped by policy" in message for message in _warning_messages(warnings)
    )


def test_invalid_zip_options_raise_value_error(tmp_path: Path) -> None:
    zip_path = tmp_path / "bundle.zip"
    with zipfile.ZipFile(zip_path, "w") as zip_out:
        zip_out.writestr("a.txt", "a")

    out_dir = tmp_path / "out"
    report = tmp_path / "report.jsonl"
    with pytest.raises(ValueError, match="zip_max_members must be >= 1"):
        sanitize_path(
            zip_path,
            out_dir,
            report,
            options=SanitizeOptions(zip_max_members=0),
        )
