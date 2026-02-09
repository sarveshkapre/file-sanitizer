from __future__ import annotations

import io
import json
import os
import shutil
import stat
import tempfile
import zipfile
from collections.abc import Callable, Iterator
from dataclasses import field
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath
from typing import Any

from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
PDF_EXTS = {".pdf"}
ZIP_EXTS = {".zip"}


@dataclass(frozen=True)
class SanitizeOptions:
    flat_output: bool = False
    overwrite: bool = True
    copy_unsupported: bool = True
    skip_symlinks: bool = True
    dry_run: bool = False
    exclude_globs: list[str] = field(default_factory=list)


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
    exclude_globs = opts.exclude_globs or []

    report_path.parent.mkdir(parents=True, exist_ok=True)

    error_count = 0
    reserved_outputs: set[Path] = set()

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
                reserved_outputs=reserved_outputs,
                options=opts,
                exclude_globs=exclude_globs,
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
        files = sorted(
            (p for p in input_path.rglob("*") if p.is_file()),
            key=lambda path: path.relative_to(input_path).as_posix(),
        )
        yield from files
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
    reserved_outputs: set[Path],
    options: SanitizeOptions,
    exclude_globs: list[str],
) -> ReportItem | None:
    matched = _match_exclude_glob(file=file, input_root=input_root, globs=exclude_globs)
    if matched is not None:
        return ReportItem(
            input_path=str(file),
            output_path=None,
            action="excluded",
            warnings=[f"excluded by pattern: {matched}"],
        )

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
        reserved_outputs=reserved_outputs,
    )
    reserved_outputs.add(output_path.resolve(strict=False))
    return _sanitize_file(file, output_path, options=options)


def _compute_output_path(
    *,
    file: Path,
    input_root: Path,
    out_dir: Path,
    flat_output: bool,
    reserved_outputs: set[Path],
) -> Path:
    if not flat_output:
        return out_dir / file.relative_to(input_root)

    out_path = out_dir / file.name
    if not out_path.exists() and out_path.resolve(strict=False) not in reserved_outputs:
        return out_path

    stem = out_path.stem
    suffix = out_path.suffix
    for i in range(1, 10_000):
        candidate = out_dir / f"{stem}-{i}{suffix}"
        if not candidate.exists() and candidate.resolve(strict=False) not in reserved_outputs:
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
        if suffix in ZIP_EXTS:
            if options.dry_run:
                warnings.extend(_scan_zip_warnings(input_path, options=options))
                return ReportItem(str(input_path), str(output_path), "would_zip_sanitize", warnings)
            warnings.extend(_sanitize_zip(input_path, output_path, options=options))
            return ReportItem(str(input_path), str(output_path), "zip_sanitized", warnings)

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
    input_bytes = input_path.read_bytes()
    sanitized = _sanitize_image_bytes(input_bytes, suffix=output_path.suffix.lower())

    tmp = _temp_path_for(output_path)
    try:
        tmp.write_bytes(sanitized)
        os.replace(tmp, output_path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def _sanitize_pdf(input_path: Path, output_path: Path) -> list[str]:
    input_bytes = input_path.read_bytes()
    sanitized, warnings = _sanitize_pdf_bytes(input_bytes)

    tmp = _temp_path_for(output_path)
    try:
        tmp.write_bytes(sanitized)
        os.replace(tmp, output_path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
    return warnings


def _scan_pdf_warnings(input_path: Path) -> list[str]:
    reader = PdfReader(str(input_path))
    return _scan_pdf_risks(reader)


def _scan_zip_warnings(input_path: Path, *, options: SanitizeOptions) -> list[str]:
    with zipfile.ZipFile(input_path, "r") as zip_in:
        return _sanitize_zip_members(
            zip_in,
            zip_out=None,
            copy_unsupported=options.copy_unsupported,
        )


def _sanitize_zip(input_path: Path, output_path: Path, *, options: SanitizeOptions) -> list[str]:
    tmp = _temp_path_for(output_path)
    try:
        with zipfile.ZipFile(input_path, "r") as zip_in, zipfile.ZipFile(tmp, "w") as zip_out:
            warnings = _sanitize_zip_members(
                zip_in,
                zip_out=zip_out,
                copy_unsupported=options.copy_unsupported,
            )
        os.replace(tmp, output_path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
    return warnings


def _sanitize_zip_members(
    zip_in: zipfile.ZipFile,
    *,
    zip_out: zipfile.ZipFile | None,
    copy_unsupported: bool,
) -> list[str]:
    warnings: set[str] = set()
    seen_names: set[str] = set()

    infos = sorted(zip_in.infolist(), key=lambda info: _normalized_zip_name(info.filename))
    for info in infos:
        output_name = _normalized_zip_name(info.filename)
        if not output_name:
            warnings.add("zip has an empty entry name; skipped")
            continue

        if _is_unsafe_zip_name(output_name):
            warnings.add(f"zip entry '{info.filename}' has unsafe path; skipped")
            continue

        if output_name in seen_names:
            warnings.add(f"zip entry '{info.filename}' is duplicated; skipped")
            continue
        seen_names.add(output_name)

        if _zipinfo_is_symlink(info):
            warnings.add(f"zip entry '{info.filename}' is a symlink; skipped")
            continue

        if info.is_dir():
            if zip_out is not None:
                _write_zip_member(zip_out, info, output_name, b"")
            continue

        if info.flag_bits & 0x1:
            warnings.add(f"zip entry '{info.filename}' is encrypted; skipped")
            continue

        data = zip_in.read(info)
        suffix = Path(output_name).suffix.lower()

        try:
            if suffix in IMAGE_EXTS:
                payload = _sanitize_image_bytes(data, suffix=suffix)
            elif suffix in PDF_EXTS:
                payload, pdf_warnings = _sanitize_pdf_bytes(data)
                for warning in pdf_warnings:
                    warnings.add(f"zip entry '{info.filename}': {warning}")
            elif copy_unsupported:
                payload = data
                warnings.add(f"zip entry '{info.filename}' unsupported; copied as-is")
            else:
                warnings.add(f"zip entry '{info.filename}' unsupported; skipped")
                continue
        except Exception as exc:  # noqa: BLE001
            warnings.add(f"zip entry '{info.filename}' failed to sanitize: {exc}; skipped")
            continue

        if zip_out is not None:
            _write_zip_member(zip_out, info, output_name, payload)

    return sorted(warnings)


def _write_zip_member(
    zip_out: zipfile.ZipFile, source_info: zipfile.ZipInfo, output_name: str, payload: bytes
) -> None:
    out_info = zipfile.ZipInfo(filename=output_name, date_time=source_info.date_time)
    out_info.compress_type = source_info.compress_type
    out_info.create_system = source_info.create_system
    out_info.external_attr = source_info.external_attr
    out_info.comment = source_info.comment
    out_info.extra = source_info.extra
    out_info.internal_attr = source_info.internal_attr
    out_info.flag_bits = source_info.flag_bits & ~0x1
    zip_out.writestr(out_info, payload)


def _normalized_zip_name(name: str) -> str:
    return name.replace("\\", "/")


def _is_unsafe_zip_name(name: str) -> bool:
    if name.startswith("/"):
        return True
    path = PurePosixPath(name)
    if path.is_absolute():
        return True
    if path.parts and path.parts[0].endswith(":"):
        return True
    return ".." in path.parts


def _zipinfo_is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0o177777
    return stat.S_ISLNK(mode)


def _sanitize_image_bytes(input_bytes: bytes, *, suffix: str) -> bytes:
    out_format = _image_format_for_suffix(suffix)
    with Image.open(io.BytesIO(input_bytes)) as img:
        data = img.copy()
        data.info.clear()
        data.load()

    out = io.BytesIO()
    if out_format == "JPEG":
        data = data.convert("RGB")
        data.save(
            out,
            format=out_format,
            exif=b"",
            icc_profile=None,
            optimize=True,
            progressive=True,
            quality=95,
        )
    elif out_format == "PNG":
        data.save(out, format=out_format, optimize=True)
    else:
        data.save(out, format=out_format, exif=b"", icc_profile=None, quality=90, method=6)
    return out.getvalue()


def _sanitize_pdf_bytes(input_bytes: bytes) -> tuple[bytes, list[str]]:
    reader = PdfReader(io.BytesIO(input_bytes))
    warnings = _scan_pdf_risks(reader)

    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.add_metadata({})

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue(), warnings


def _image_format_for_suffix(suffix: str) -> str:
    return {
        ".jpg": "JPEG",
        ".jpeg": "JPEG",
        ".png": "PNG",
        ".webp": "WEBP",
    }[suffix]


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
    input_bytes = input_path.read_bytes()
    with Image.open(io.BytesIO(input_bytes)) as img:
        img.verify()


def _match_exclude_glob(*, file: Path, input_root: Path, globs: list[str]) -> str | None:
    if not globs:
        return None

    try:
        rel = file.relative_to(input_root)
        rel_posix = rel.as_posix()
        rel_parts = rel_posix.split("/")
    except Exception:
        rel_posix = file.name
        rel_parts = [file.name]

    for raw in globs:
        pat = raw.replace("\\", "/")
        if "/" in pat or pat.startswith("**"):
            if PurePosixPath(rel_posix).match(pat):
                return raw
            continue

        # Segment-style matching (e.g., ".git", "node_modules", "*.tmp")
        if any(fnmatchcase(part, pat) for part in rel_parts):
            return raw

    return None
