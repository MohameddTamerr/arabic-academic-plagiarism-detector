# -*- coding: utf-8 -*-
"""Create cached PDF previews for locally stored Word documents."""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
import sys
import threading
import uuid
from pathlib import Path

import config


logger = logging.getLogger(__name__)


class DocumentPreviewError(RuntimeError):
    """Raised when a supported document cannot be converted for preview."""


_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def _preview_cache_dir() -> Path:
    path = Path(config.STORAGE_ROOT) / "document_previews"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cache_key(source: Path) -> str:
    stat = source.stat()
    identity = f"{source.resolve()}|{stat.st_size}|{stat.st_mtime_ns}"
    return hashlib.sha256(identity.encode("utf-8", errors="surrogatepass")).hexdigest()


def _lock_for(key: str) -> threading.Lock:
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.Lock())


def _convert_with_word(source: Path, destination: Path) -> None:
    if sys.platform != "win32":
        raise DocumentPreviewError("Microsoft Word conversion is only available on Windows")

    try:
        import pythoncom
        import win32com.client
    except ImportError as exc:
        raise DocumentPreviewError("Microsoft Word integration is unavailable") from exc

    word = None
    document = None
    pythoncom.CoInitialize()
    try:
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        try:
            # Disable macros while opening documents through Office automation.
            word.AutomationSecurity = 3
        except Exception:
            pass
        document = word.Documents.Open(
            str(source.resolve()),
            ConfirmConversions=False,
            ReadOnly=True,
            AddToRecentFiles=False,
            Visible=False,
            OpenAndRepair=True,
            NoEncodingDialog=True,
        )
        document.ExportAsFixedFormat(
            OutputFileName=str(destination.resolve()),
            ExportFormat=17,  # wdExportFormatPDF
            OpenAfterExport=False,
            OptimizeFor=0,
            Range=0,
            Item=0,
            IncludeDocProps=True,
            KeepIRM=True,
            CreateBookmarks=1,
            DocStructureTags=True,
            BitmapMissingFonts=True,
            UseISO19005_1=False,
        )
    except Exception as exc:
        raise DocumentPreviewError("تعذر تحويل ملف Word إلى PDF للعرض") from exc
    finally:
        if document is not None:
            try:
                document.Close(SaveChanges=False)
            except Exception:
                logger.debug("Failed to close Word preview document", exc_info=True)
        if word is not None:
            try:
                word.Quit(SaveChanges=False)
            except Exception:
                logger.debug("Failed to close Word preview process", exc_info=True)
        pythoncom.CoUninitialize()


def _convert_with_libreoffice(source: Path, destination: Path) -> None:
    executable = shutil.which("soffice") or shutil.which("libreoffice")
    if not executable:
        raise DocumentPreviewError("No local Word-to-PDF converter is installed")

    output_dir = destination.parent / f"lo-{uuid.uuid4().hex}"
    output_dir.mkdir(parents=True, exist_ok=False)
    try:
        completed = subprocess.run(
            [
                executable,
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(output_dir),
                str(source.resolve()),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        converted = output_dir / f"{source.stem}.pdf"
        if completed.returncode != 0 or not converted.is_file():
            raise DocumentPreviewError("LibreOffice could not create the PDF preview")
        os.replace(converted, destination)
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)


def ensure_pdf_preview(source_path: str | Path) -> Path:
    """Return the PDF itself or a cached PDF preview for a DOCX document."""
    source = Path(source_path)
    if not source.is_file():
        raise DocumentPreviewError("المستند الأصلي غير متاح")
    if source.suffix.lower() == ".pdf":
        return source
    if source.suffix.lower() != ".docx":
        raise DocumentPreviewError("صيغة المستند غير مدعومة للعرض")

    key = _cache_key(source)
    destination = _preview_cache_dir() / f"{key}.pdf"
    if destination.is_file() and destination.stat().st_size > 0:
        return destination

    with _lock_for(key):
        if destination.is_file() and destination.stat().st_size > 0:
            return destination

        temporary = destination.with_name(f".{destination.stem}-{uuid.uuid4().hex}.pdf")
        try:
            try:
                _convert_with_word(source, temporary)
            except DocumentPreviewError as word_error:
                logger.info("Microsoft Word preview conversion failed; trying LibreOffice: %s", word_error)
                _convert_with_libreoffice(source, temporary)
            if not temporary.is_file() or temporary.stat().st_size == 0:
                raise DocumentPreviewError("تم إنشاء معاينة فارغة للمستند")
            os.replace(temporary, destination)
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                logger.debug("Failed to remove temporary preview", exc_info=True)
        return destination
