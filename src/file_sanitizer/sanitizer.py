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
OFFICE_OOXML_EXTS = {
    ".docx",
    ".xlsx",
    ".pptx",
    ".docm",
    ".xlsm",
    ".pptm",
    ".dotm",
    ".xltm",
    ".potm",
}
OFFICE_MACRO_ENABLED_EXTS = {".docm", ".xlsm", ".pptm", ".dotm", ".xltm", ".potm"}

DEFAULT_ZIP_MAX_MEMBERS = 10_000
DEFAULT_ZIP_MAX_MEMBER_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
DEFAULT_ZIP_MAX_TOTAL_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
DEFAULT_ZIP_MAX_COMPRESSION_RATIO = 100.0
NESTED_ARCHIVE_POLICIES = {"skip", "copy"}
RISKY_POLICIES = {"warn", "block"}


@dataclass(frozen=True)
class SanitizeOptions:
    flat_output: bool = False
    overwrite: bool = True
    copy_unsupported: bool = True
    skip_symlinks: bool = True
    dry_run: bool = False
    exclude_globs: list[str] = field(default_factory=list)
    zip_max_members: int = DEFAULT_ZIP_MAX_MEMBERS
    zip_max_member_uncompressed_bytes: int = DEFAULT_ZIP_MAX_MEMBER_UNCOMPRESSED_BYTES
    zip_max_total_uncompressed_bytes: int = DEFAULT_ZIP_MAX_TOTAL_UNCOMPRESSED_BYTES
    zip_max_compression_ratio: float = DEFAULT_ZIP_MAX_COMPRESSION_RATIO
    nested_archive_policy: str = "skip"
    risky_policy: str = "warn"


class BlockedByPolicy(Exception):
    def __init__(self, *, warnings: list[WarningItem]) -> None:
        super().__init__("blocked by policy")
        self.warnings = warnings


@dataclass(frozen=True)
class WarningItem:
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True)
class ReportItem:
    input_path: str
    output_path: str | None
    action: str
    warnings: list[WarningItem]
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_path": self.input_path,
            "output_path": self.output_path,
            "action": self.action,
            "warnings": [w.to_dict() for w in self.warnings],
            "error": self.error,
        }


def _is_risky_warning(w: WarningItem) -> bool:
    if w.code.startswith("pdf_risk_") or w.code == "pdf_scan_failed":
        return True
    if w.code in {
        "office_macro_enabled",
        "office_macro_indicator_vbaproject",
        "office_ooxml_scan_failed",
    }:
        return True
    if w.code.startswith("zip_"):
        return True
    return False


def _has_risky_findings(warnings: list[WarningItem]) -> bool:
    return any(_is_risky_warning(w) for w in warnings)


def _policy_blocked_warning() -> WarningItem:
    return WarningItem(code="policy_blocked", message="blocked by risky_policy=block")


def sanitize_path(
    input_path: Path,
    out_dir: Path,
    report_path: Path,
    *,
    options: SanitizeOptions | None = None,
    on_item: Callable[[ReportItem], None] | None = None,
) -> int:
    opts = options or SanitizeOptions()
    _validate_options(opts)
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

            if item.action in {"error", "blocked"}:
                error_count += 1

            out.write(json.dumps(item.to_dict()) + "\n")
            if on_item is not None:
                on_item(item)

    return 0 if error_count == 0 else 2


def _validate_options(options: SanitizeOptions) -> None:
    if options.zip_max_members < 1:
        raise ValueError("zip_max_members must be >= 1")
    if options.zip_max_member_uncompressed_bytes < 1:
        raise ValueError("zip_max_member_uncompressed_bytes must be >= 1")
    if options.zip_max_total_uncompressed_bytes < 1:
        raise ValueError("zip_max_total_uncompressed_bytes must be >= 1")
    if options.zip_max_compression_ratio <= 0:
        raise ValueError("zip_max_compression_ratio must be > 0")
    if options.nested_archive_policy not in NESTED_ARCHIVE_POLICIES:
        allowed = ", ".join(sorted(NESTED_ARCHIVE_POLICIES))
        raise ValueError(f"nested_archive_policy must be one of: {allowed}")
    if options.risky_policy not in RISKY_POLICIES:
        allowed = ", ".join(sorted(RISKY_POLICIES))
        raise ValueError(f"risky_policy must be one of: {allowed}")


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
            warnings=[
                WarningItem(code="excluded_by_pattern", message=f"excluded by pattern: {matched}")
            ],
        )

    if options.skip_symlinks and file.is_symlink():
        return ReportItem(
            input_path=str(file),
            output_path=None,
            action="skipped",
            warnings=[WarningItem(code="symlink_skipped", message="symlink skipped")],
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


def _scan_office_macro_indicators_path(path: Path) -> list[WarningItem]:
    suffix = path.suffix.lower()
    warnings: list[WarningItem] = []

    if suffix in OFFICE_MACRO_ENABLED_EXTS:
        warnings.append(
            WarningItem(
                code="office_macro_enabled",
                message=f"office macro-enabled file type ({suffix}); macros are not removed",
            )
        )

    if suffix in OFFICE_OOXML_EXTS:
        try:
            with zipfile.ZipFile(path, "r") as zf:
                names = zf.namelist()
        except Exception as exc:  # noqa: BLE001
            warnings.append(
                WarningItem(
                    code="office_ooxml_scan_failed",
                    message=f"office OOXML scan failed: {exc}",
                )
            )
            return warnings

        if any(name.lower().endswith("vbaproject.bin") for name in names):
            warnings.append(
                WarningItem(
                    code="office_macro_indicator_vbaproject",
                    message="office OOXML contains vbaProject.bin (macro indicator); not removed",
                )
            )

    return warnings


def _scan_office_macro_indicators_bytes(payload: bytes) -> list[WarningItem]:
    try:
        with zipfile.ZipFile(io.BytesIO(payload), "r") as zf:
            names = zf.namelist()
    except Exception as exc:  # noqa: BLE001
        return [
            WarningItem(code="office_ooxml_scan_failed", message=f"office OOXML scan failed: {exc}")
        ]

    if any(name.lower().endswith("vbaproject.bin") for name in names):
        return [
            WarningItem(
                code="office_macro_indicator_vbaproject",
                message="office OOXML contains vbaProject.bin (macro indicator); not removed",
            )
        ]
    return []


def _sanitize_file(input_path: Path, output_path: Path, *, options: SanitizeOptions) -> ReportItem:
    if not options.dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists() and not options.overwrite:
        return ReportItem(
            str(input_path),
            str(output_path),
            "skipped",
            [
                WarningItem(
                    code="output_exists",
                    message="output exists; use --overwrite to replace",
                )
            ],
        )

    suffix = input_path.suffix.lower()
    warnings: list[WarningItem] = []
    try:
        if suffix in OFFICE_OOXML_EXTS:
            warnings.extend(_scan_office_macro_indicators_path(input_path))
            if options.risky_policy == "block" and _has_risky_findings(warnings):
                warnings.append(_policy_blocked_warning())
                return ReportItem(
                    str(input_path),
                    None,
                    "would_block" if options.dry_run else "blocked",
                    warnings,
                )

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
                if options.risky_policy == "block" and _has_risky_findings(warnings):
                    warnings.append(_policy_blocked_warning())
                    return ReportItem(str(input_path), None, "would_block", warnings)
                return ReportItem(str(input_path), str(output_path), "would_pdf_sanitize", warnings)
            warnings.extend(_sanitize_pdf(input_path, output_path, options=options))
            return ReportItem(str(input_path), str(output_path), "pdf_sanitized", warnings)
        if suffix in ZIP_EXTS:
            if options.dry_run:
                warnings.extend(_scan_zip_warnings(input_path, options=options))
                if options.risky_policy == "block" and _has_risky_findings(warnings):
                    warnings.append(_policy_blocked_warning())
                    return ReportItem(str(input_path), None, "would_block", warnings)
                return ReportItem(str(input_path), str(output_path), "would_zip_sanitize", warnings)
            warnings.extend(_sanitize_zip(input_path, output_path, options=options))
            return ReportItem(str(input_path), str(output_path), "zip_sanitized", warnings)

        if options.copy_unsupported:
            if options.dry_run:
                warnings.append(
                    WarningItem(
                        code="unsupported_would_copy",
                        message="unsupported file type; would copy as-is",
                    )
                )
                return ReportItem(str(input_path), str(output_path), "would_copy", warnings)
            _copy_atomic(input_path, output_path)
            warnings.append(
                WarningItem(
                    code="unsupported_copied",
                    message="unsupported file type; copied as-is",
                )
            )
            return ReportItem(str(input_path), str(output_path), "copied", warnings)

        warnings.append(
            WarningItem(code="unsupported_skipped", message="unsupported file type; skipped")
        )
        return ReportItem(
            str(input_path),
            None,
            "would_skip" if options.dry_run else "skipped",
            warnings,
        )
    except BlockedByPolicy as exc:
        blocked_warnings = list(exc.warnings)
        blocked_warnings.append(_policy_blocked_warning())
        return ReportItem(str(input_path), None, "blocked", blocked_warnings)
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


def _sanitize_pdf(
    input_path: Path, output_path: Path, *, options: SanitizeOptions
) -> list[WarningItem]:
    input_bytes = input_path.read_bytes()
    sanitized, warnings = _sanitize_pdf_bytes(input_bytes)
    if options.risky_policy == "block" and _has_risky_findings(warnings):
        raise BlockedByPolicy(warnings=warnings)

    tmp = _temp_path_for(output_path)
    try:
        tmp.write_bytes(sanitized)
        os.replace(tmp, output_path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
    return warnings


def _scan_pdf_warnings(input_path: Path) -> list[WarningItem]:
    reader = PdfReader(str(input_path))
    return _scan_pdf_risks(reader)


def _scan_zip_warnings(input_path: Path, *, options: SanitizeOptions) -> list[WarningItem]:
    with zipfile.ZipFile(input_path, "r") as zip_in:
        return _sanitize_zip_members(
            zip_in,
            zip_out=None,
            options=options,
        )


def _sanitize_zip(
    input_path: Path, output_path: Path, *, options: SanitizeOptions
) -> list[WarningItem]:
    tmp = _temp_path_for(output_path)
    try:
        with zipfile.ZipFile(input_path, "r") as zip_in, zipfile.ZipFile(tmp, "w") as zip_out:
            warnings = _sanitize_zip_members(
                zip_in,
                zip_out=zip_out,
                options=options,
            )
        if options.risky_policy == "block" and _has_risky_findings(warnings):
            raise BlockedByPolicy(warnings=warnings)
        os.replace(tmp, output_path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
    return warnings


def _sanitize_zip_members(
    zip_in: zipfile.ZipFile,
    *,
    zip_out: zipfile.ZipFile | None,
    options: SanitizeOptions,
) -> list[WarningItem]:
    warnings: set[WarningItem] = set()
    seen_names: set[str] = set()
    total_expanded_bytes = 0

    infos = sorted(zip_in.infolist(), key=lambda info: _normalized_zip_name(info.filename))
    if len(infos) > options.zip_max_members:
        warnings.add(
            WarningItem(
                code="zip_entries_truncated",
                message=(
                    f"zip has {len(infos)} entries; processing limited to "
                    f"{options.zip_max_members} by policy"
                ),
            )
        )
        infos = infos[: options.zip_max_members]

    for info in infos:
        output_name = _normalized_zip_name(info.filename)
        if not output_name:
            warnings.add(
                WarningItem(
                    code="zip_entry_empty_name", message="zip has an empty entry name; skipped"
                )
            )
            continue

        if _is_unsafe_zip_name(output_name):
            warnings.add(
                WarningItem(
                    code="zip_entry_unsafe_path",
                    message=f"zip entry '{info.filename}' has unsafe path; skipped",
                )
            )
            continue

        if output_name in seen_names:
            warnings.add(
                WarningItem(
                    code="zip_entry_duplicate",
                    message=f"zip entry '{info.filename}' is duplicated; skipped",
                )
            )
            continue
        seen_names.add(output_name)

        if _zipinfo_is_symlink(info):
            warnings.add(
                WarningItem(
                    code="zip_entry_symlink",
                    message=f"zip entry '{info.filename}' is a symlink; skipped",
                )
            )
            continue

        if info.is_dir():
            if zip_out is not None:
                _write_zip_member(zip_out, info, output_name, b"")
            continue

        if info.flag_bits & 0x1:
            warnings.add(
                WarningItem(
                    code="zip_entry_encrypted",
                    message=f"zip entry '{info.filename}' is encrypted; skipped",
                )
            )
            continue

        suffix = Path(output_name).suffix.lower()
        expanded_size = max(int(info.file_size), 0)
        if expanded_size > options.zip_max_member_uncompressed_bytes:
            warnings.add(
                WarningItem(
                    code="zip_entry_oversize",
                    message=(
                        f"zip entry '{info.filename}' expanded size {expanded_size} exceeds "
                        f"limit {options.zip_max_member_uncompressed_bytes}; skipped"
                    ),
                )
            )
            continue

        compressed_size = max(int(info.compress_size), 0)
        ratio = _zip_compression_ratio(expanded_size, compressed_size)
        if ratio > options.zip_max_compression_ratio:
            warnings.add(
                WarningItem(
                    code="zip_entry_compression_ratio_exceeded",
                    message=(
                        f"zip entry '{info.filename}' compression ratio {_format_ratio(ratio)} exceeds "
                        f"limit {_format_ratio(options.zip_max_compression_ratio)}; skipped"
                    ),
                )
            )
            continue

        if suffix in ZIP_EXTS:
            if options.nested_archive_policy == "copy":
                try:
                    data = zip_in.read(info)
                except Exception as exc:  # noqa: BLE001
                    warnings.add(
                        WarningItem(
                            code="zip_nested_archive_read_failed",
                            message=(
                                f"zip entry '{info.filename}' failed to read nested archive: {exc}; skipped"
                            ),
                        )
                    )
                    continue
                if total_expanded_bytes + len(data) > options.zip_max_total_uncompressed_bytes:
                    warnings.add(
                        WarningItem(
                            code="zip_total_expanded_limit_exceeded",
                            message=(
                                "zip expanded size limit exceeded "
                                f"({options.zip_max_total_uncompressed_bytes} bytes); "
                                f"nested archive '{info.filename}' skipped"
                            ),
                        )
                    )
                    continue
                total_expanded_bytes += len(data)
                warnings.add(
                    WarningItem(
                        code="zip_nested_archive_copied",
                        message=f"zip entry '{info.filename}' is nested archive; copied by policy",
                    )
                )
                if zip_out is not None:
                    _write_zip_member(zip_out, info, output_name, data)
            else:
                warnings.add(
                    WarningItem(
                        code="zip_nested_archive_skipped",
                        message=f"zip entry '{info.filename}' is nested archive; skipped by policy",
                    )
                )
            continue

        if total_expanded_bytes + expanded_size > options.zip_max_total_uncompressed_bytes:
            warnings.add(
                WarningItem(
                    code="zip_total_expanded_limit_exceeded",
                    message=(
                        "zip expanded size limit exceeded "
                        f"({options.zip_max_total_uncompressed_bytes} bytes); "
                        f"entry '{info.filename}' and remaining data may be skipped"
                    ),
                )
            )
            continue

        data = zip_in.read(info)
        total_expanded_bytes += len(data)

        try:
            if suffix in IMAGE_EXTS:
                payload = _sanitize_image_bytes(data, suffix=suffix)
            elif suffix in PDF_EXTS:
                payload, pdf_warnings = _sanitize_pdf_bytes(data)
                for warning in pdf_warnings:
                    warnings.add(
                        WarningItem(
                            code=warning.code,
                            message=f"zip entry '{info.filename}': {warning.message}",
                        )
                    )
            elif options.copy_unsupported:
                payload = data
                if suffix in OFFICE_OOXML_EXTS:
                    if suffix in OFFICE_MACRO_ENABLED_EXTS:
                        warnings.add(
                            WarningItem(
                                code="office_macro_enabled",
                                message=(
                                    f"zip entry '{info.filename}': "
                                    f"office macro-enabled file type ({suffix}); macros are not removed"
                                ),
                            )
                        )
                    for w in _scan_office_macro_indicators_bytes(data):
                        warnings.add(
                            WarningItem(
                                code=w.code,
                                message=f"zip entry '{info.filename}': {w.message}",
                            )
                        )
                warnings.add(
                    WarningItem(
                        code="zip_entry_unsupported_copied",
                        message=f"zip entry '{info.filename}' unsupported; copied as-is",
                    )
                )
            else:
                if suffix in OFFICE_MACRO_ENABLED_EXTS:
                    warnings.add(
                        WarningItem(
                            code="office_macro_enabled",
                            message=(
                                f"zip entry '{info.filename}': "
                                f"office macro-enabled file type ({suffix}); macros are not removed"
                            ),
                        )
                    )
                warnings.add(
                    WarningItem(
                        code="zip_entry_unsupported_skipped",
                        message=f"zip entry '{info.filename}' unsupported; skipped",
                    )
                )
                continue
        except Exception as exc:  # noqa: BLE001
            warnings.add(
                WarningItem(
                    code="zip_entry_sanitize_failed",
                    message=f"zip entry '{info.filename}' failed to sanitize: {exc}; skipped",
                )
            )
            continue

        if zip_out is not None:
            _write_zip_member(zip_out, info, output_name, payload)

    return sorted(warnings, key=lambda w: (w.code, w.message))


def _zip_compression_ratio(expanded_size: int, compressed_size: int) -> float:
    if expanded_size <= 0:
        return 1.0
    if compressed_size <= 0:
        return float("inf")
    return expanded_size / compressed_size


def _format_ratio(value: float) -> str:
    if value == float("inf"):
        return "inf"
    return f"{value:.1f}"


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


def _sanitize_pdf_bytes(input_bytes: bytes) -> tuple[bytes, list[WarningItem]]:
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


def _scan_pdf_risks(reader: PdfReader) -> list[WarningItem]:
    warnings: set[WarningItem] = set()
    try:
        root = _pdf_deref(reader.trailer.get("/Root"))
        if isinstance(root, DictionaryObject):
            _scan_pdf_catalog(root, warnings)

        for page in reader.pages:
            page_obj = _pdf_deref(page)
            if isinstance(page_obj, DictionaryObject):
                _scan_pdf_page(page_obj, warnings)
    except Exception as exc:  # noqa: BLE001
        warnings.add(WarningItem(code="pdf_scan_failed", message=f"pdf scan failed: {exc}"))

    return sorted(warnings, key=lambda w: (w.code, w.message))


def _scan_pdf_catalog(root: DictionaryObject, warnings: set[WarningItem]) -> None:
    if "/OpenAction" in root:
        warnings.add(
            WarningItem(
                code="pdf_risk_open_action",
                message="pdf has /OpenAction (auto-exec on open) -- not removed",
            )
        )
        warnings.update(_scan_pdf_action(root.get("/OpenAction"), context="/OpenAction"))

    if "/AA" in root:
        warnings.add(
            WarningItem(
                code="pdf_risk_additional_actions",
                message="pdf has /AA (additional actions) -- not removed",
            )
        )
        aa = _pdf_deref(root.get("/AA"))
        if isinstance(aa, DictionaryObject):
            for k, v in aa.items():
                warnings.update(_scan_pdf_action(v, context=f"/AA {k}"))

    if "/AcroForm" in root:
        warnings.add(
            WarningItem(
                code="pdf_risk_forms",
                message="pdf has forms (/AcroForm) -- not removed",
            )
        )
        acro = _pdf_deref(root.get("/AcroForm"))
        if isinstance(acro, DictionaryObject) and "/XFA" in acro:
            warnings.add(
                WarningItem(
                    code="pdf_risk_xfa_forms",
                    message="pdf has XFA forms (/XFA) -- not removed",
                )
            )

    names = _pdf_deref(root.get("/Names"))
    if isinstance(names, DictionaryObject):
        if "/JavaScript" in names:
            warnings.add(
                WarningItem(
                    code="pdf_risk_javascript_tree",
                    message="pdf has JavaScript name tree (/Names/JavaScript) -- not removed",
                )
            )
        if "/EmbeddedFiles" in names:
            warnings.add(
                WarningItem(
                    code="pdf_risk_embedded_files",
                    message="pdf has embedded files (/Names/EmbeddedFiles) -- not removed",
                )
            )


def _scan_pdf_page(page: DictionaryObject, warnings: set[WarningItem]) -> None:
    if "/AA" in page:
        warnings.add(
            WarningItem(
                code="pdf_risk_page_additional_actions",
                message="pdf page has /AA (additional actions) -- not removed",
            )
        )
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
                    WarningItem(
                        code="pdf_risk_file_attachment_annotation",
                        message=(
                            "pdf has file attachment annotation "
                            "(/Subtype /FileAttachment) -- not removed"
                        ),
                    )
                )
            if "/A" in annot:
                warnings.update(_scan_pdf_action(annot.get("/A"), context="annotation /A"))
            if "/AA" in annot:
                warnings.add(
                    WarningItem(
                        code="pdf_risk_annotation_additional_actions",
                        message="pdf annotation has /AA (additional actions) -- not removed",
                    )
                )
                aa = _pdf_deref(annot.get("/AA"))
                if isinstance(aa, DictionaryObject):
                    for k, v in aa.items():
                        warnings.update(_scan_pdf_action(v, context=f"annotation /AA {k}"))


def _scan_pdf_action(action_obj: object, *, context: str) -> set[WarningItem]:
    action = _pdf_deref(action_obj)
    warnings: set[WarningItem] = set()

    if isinstance(action, ArrayObject):
        warnings.add(
            WarningItem(
                code="pdf_risk_destination",
                message=f"pdf {context} sets destination -- not removed",
            )
        )
        return warnings

    if not isinstance(action, DictionaryObject):
        warnings.add(
            WarningItem(
                code="pdf_risk_action_unknown", message=f"pdf {context} has action -- not removed"
            )
        )
        return warnings

    subtype = str(action.get("/S") or "")
    if subtype:
        warnings.add(
            WarningItem(
                code="pdf_risk_action_subtype",
                message=f"pdf {context} action subtype {subtype} -- not removed",
            )
        )
    else:
        warnings.add(
            WarningItem(
                code="pdf_risk_action_no_subtype",
                message=f"pdf {context} has action without /S -- not removed",
            )
        )

    if "/Next" in action:
        warnings.add(
            WarningItem(
                code="pdf_risk_action_next_chain",
                message=f"pdf {context} action has /Next chain -- not removed",
            )
        )

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
