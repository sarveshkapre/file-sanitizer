from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
PDF_EXTS = {".pdf"}


@dataclass(frozen=True)
class SanitizeOptions:
    flat_output: bool = False
    overwrite: bool = True
    copy_unsupported: bool = True
    skip_symlinks: bool = True
    dry_run: bool = False


@dataclass(frozen=True)
class ReportItem:
    input_path: str
    output_path: str | None
    action: str
    warnings: list[str]
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_path": self.input_path,
            "output_path": self.output_path,
            "action": self.action,
            "warnings": self.warnings,
            "error": self.error,
        }


def sanitize_path(
    input_path: Path,
    out_dir: Path,
    report_path: Path,
    *,
    options: SanitizeOptions | None = None,
    on_item: Callable[[ReportItem], None] | None = None,
) -> int:
    opts = options or SanitizeOptions()

    report_path.parent.mkdir(parents=True, exist_ok=True)

    error_count = 0

    input_root = input_path if input_path.is_dir() else input_path.parent
    input_root_resolved = input_root.resolve(strict=False)
    out_dir_resolved = out_dir.resolve(strict=False)
    report_path_resolved = report_path.resolve(strict=False)

    with report_path.open("w", encoding="utf-8") as out:
        for file in _iter_files(input_path):
            item = _sanitize_one(
                file=file,
                input_root=input_root,
                input_root_resolved=input_root_resolved,
                out_dir=out_dir,
                out_dir_resolved=out_dir_resolved,
                report_path_resolved=report_path_resolved,
                options=opts,
            )
            if item is None:
                continue

            if item.action == "error":
                error_count += 1

            out.write(json.dumps(item.to_dict()) + "\n")
            if on_item is not None:
                on_item(item)

    return 0 if error_count == 0 else 2


def _iter_files(input_path: Path) -> Iterator[Path]:
    if input_path.is_dir():
        yield from (p for p in input_path.rglob("*") if p.is_file())
        return
    yield input_path


def _sanitize_one(
    *,
    file: Path,
    input_root: Path,
    input_root_resolved: Path,
    out_dir: Path,
    out_dir_resolved: Path,
    report_path_resolved: Path,
    options: SanitizeOptions,
) -> ReportItem | None:
    if options.skip_symlinks and file.is_symlink():
        return ReportItem(
            input_path=str(file),
            output_path=None,
            action="skipped",
            warnings=["symlink skipped"],
        )

    if file.resolve() == report_path_resolved:
        return None

    if out_dir_resolved.is_relative_to(input_root_resolved) and file.resolve().is_relative_to(
        out_dir_resolved
    ):
        return None

    output_path = _compute_output_path(
        file=file,
        input_root=input_root,
        out_dir=out_dir,
        flat_output=options.flat_output,
    )
    return _sanitize_file(file, output_path, options=options)


def _compute_output_path(*, file: Path, input_root: Path, out_dir: Path, flat_output: bool) -> Path:
    if not flat_output:
        return out_dir / file.relative_to(input_root)

    out_path = out_dir / file.name
    if not out_path.exists():
        return out_path

    stem = out_path.stem
    suffix = out_path.suffix
    for i in range(1, 10_000):
        candidate = out_dir / f"{stem}-{i}{suffix}"
        if not candidate.exists():
            return candidate

    raise RuntimeError(f"unable to find available output path for {file}")


def _sanitize_file(input_path: Path, output_path: Path, *, options: SanitizeOptions) -> ReportItem:
    if not options.dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists() and not options.overwrite:
        return ReportItem(
            str(input_path),
            str(output_path),
            "skipped",
            ["output exists; use --overwrite to replace"],
        )

    suffix = input_path.suffix.lower()
    warnings: list[str] = []
    try:
        if suffix in IMAGE_EXTS:
            if options.dry_run:
                _validate_image_readable(input_path)
                return ReportItem(
                    str(input_path), str(output_path), "would_image_sanitize", warnings
                )
            _sanitize_image(input_path, output_path)
            return ReportItem(str(input_path), str(output_path), "image_sanitized", warnings)
        if suffix in PDF_EXTS:
            if options.dry_run:
                warnings.extend(_scan_pdf_warnings(input_path))
                return ReportItem(str(input_path), str(output_path), "would_pdf_sanitize", warnings)
            warnings.extend(_sanitize_pdf(input_path, output_path))
            return ReportItem(str(input_path), str(output_path), "pdf_sanitized", warnings)

        if options.copy_unsupported:
            if options.dry_run:
                warnings.append("unsupported file type; would copy as-is")
                return ReportItem(str(input_path), str(output_path), "would_copy", warnings)
            _copy_atomic(input_path, output_path)
            warnings.append("unsupported file type; copied as-is")
            return ReportItem(str(input_path), str(output_path), "copied", warnings)

        warnings.append("unsupported file type; skipped")
        return ReportItem(
            str(input_path),
            None,
            "would_skip" if options.dry_run else "skipped",
            warnings,
        )
    except Exception as exc:  # noqa: BLE001
        return ReportItem(str(input_path), str(output_path), "error", warnings, error=str(exc))


def _sanitize_image(input_path: Path, output_path: Path) -> None:
    out_ext = output_path.suffix.lower()
    out_format = {
        ".jpg": "JPEG",
        ".jpeg": "JPEG",
        ".png": "PNG",
        ".webp": "WEBP",
    }[out_ext]

    with Image.open(input_path) as img:
        data = img.copy()
        data.info.clear()
        data.load()

        tmp = _temp_path_for(output_path)
        try:
            if out_format == "JPEG":
                data = data.convert("RGB")
                data.save(
                    tmp,
                    format=out_format,
                    exif=b"",
                    icc_profile=None,
                    optimize=True,
                    progressive=True,
                    quality=95,
                )
            elif out_format == "PNG":
                data.save(tmp, format=out_format, optimize=True)
            else:
                data.save(tmp, format=out_format, exif=b"", icc_profile=None, quality=90, method=6)

            os.replace(tmp, output_path)
        finally:
            if tmp.exists():
                tmp.unlink(missing_ok=True)


def _sanitize_pdf(input_path: Path, output_path: Path) -> list[str]:
    reader = PdfReader(str(input_path))
    warnings = _scan_pdf_risks(reader)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.add_metadata({})

    tmp = _temp_path_for(output_path)
    try:
        with tmp.open("wb") as fh:
            writer.write(fh)
        os.replace(tmp, output_path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
    return warnings


def _scan_pdf_warnings(input_path: Path) -> list[str]:
    reader = PdfReader(str(input_path))
    return _scan_pdf_risks(reader)


def _scan_pdf_risks(reader: PdfReader) -> list[str]:
    warnings: set[str] = set()
    try:
        root = _pdf_deref(reader.trailer.get("/Root"))
        if isinstance(root, DictionaryObject):
            _scan_pdf_catalog(root, warnings)

        for page in reader.pages:
            page_obj = _pdf_deref(page)
            if isinstance(page_obj, DictionaryObject):
                _scan_pdf_page(page_obj, warnings)
    except Exception as exc:  # noqa: BLE001
        warnings.add(f"pdf scan failed: {exc}")

    return sorted(warnings)


def _scan_pdf_catalog(root: DictionaryObject, warnings: set[str]) -> None:
    if "/OpenAction" in root:
        warnings.add("pdf has /OpenAction (auto-exec on open) — not removed")
        warnings.update(_scan_pdf_action(root.get("/OpenAction"), context="/OpenAction"))

    if "/AA" in root:
        warnings.add("pdf has /AA (additional actions) — not removed")
        aa = _pdf_deref(root.get("/AA"))
        if isinstance(aa, DictionaryObject):
            for k, v in aa.items():
                warnings.update(_scan_pdf_action(v, context=f"/AA {k}"))

    if "/AcroForm" in root:
        warnings.add("pdf has forms (/AcroForm) — not removed")
        acro = _pdf_deref(root.get("/AcroForm"))
        if isinstance(acro, DictionaryObject) and "/XFA" in acro:
            warnings.add("pdf has XFA forms (/XFA) — not removed")

    names = _pdf_deref(root.get("/Names"))
    if isinstance(names, DictionaryObject):
        if "/JavaScript" in names:
            warnings.add("pdf has JavaScript name tree (/Names/JavaScript) — not removed")
        if "/EmbeddedFiles" in names:
            warnings.add("pdf has embedded files (/Names/EmbeddedFiles) — not removed")


def _scan_pdf_page(page: DictionaryObject, warnings: set[str]) -> None:
    if "/AA" in page:
        warnings.add("pdf page has /AA (additional actions) — not removed")
        aa = _pdf_deref(page.get("/AA"))
        if isinstance(aa, DictionaryObject):
            for k, v in aa.items():
                warnings.update(_scan_pdf_action(v, context=f"page /AA {k}"))

    annots = _pdf_deref(page.get("/Annots"))
    if isinstance(annots, ArrayObject):
        for annot_ref in annots:
            annot = _pdf_deref(annot_ref)
            if not isinstance(annot, DictionaryObject):
                continue
            if str(annot.get("/Subtype")) == "/FileAttachment":
                warnings.add(
                    "pdf has file attachment annotation (/Subtype /FileAttachment) — not removed"
                )
            if "/A" in annot:
                warnings.update(_scan_pdf_action(annot.get("/A"), context="annotation /A"))
            if "/AA" in annot:
                warnings.add("pdf annotation has /AA (additional actions) — not removed")
                aa = _pdf_deref(annot.get("/AA"))
                if isinstance(aa, DictionaryObject):
                    for k, v in aa.items():
                        warnings.update(_scan_pdf_action(v, context=f"annotation /AA {k}"))


def _scan_pdf_action(action_obj: object, *, context: str) -> set[str]:
    action = _pdf_deref(action_obj)
    warnings: set[str] = set()

    if isinstance(action, ArrayObject):
        warnings.add(f"pdf {context} sets destination — not removed")
        return warnings

    if not isinstance(action, DictionaryObject):
        warnings.add(f"pdf {context} has action — not removed")
        return warnings

    subtype = str(action.get("/S") or "")
    if subtype:
        warnings.add(f"pdf {context} action subtype {subtype} — not removed")
    else:
        warnings.add(f"pdf {context} has action without /S — not removed")

    if "/Next" in action:
        warnings.add(f"pdf {context} action has /Next chain — not removed")

    return warnings


def _pdf_deref(obj: object) -> object:
    if isinstance(obj, IndirectObject):
        return obj.get_object()
    return obj


def _temp_path_for(output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fh = tempfile.NamedTemporaryFile(
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        dir=str(output_path.parent),
        delete=False,
    )
    fh.close()
    return Path(fh.name)


def _copy_atomic(input_path: Path, output_path: Path) -> None:
    tmp = _temp_path_for(output_path)
    try:
        shutil.copy2(input_path, tmp)
        os.replace(tmp, output_path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def _validate_image_readable(input_path: Path) -> None:
    with Image.open(input_path) as img:
        img.verify()
