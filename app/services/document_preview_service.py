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
import weakref
from contextlib import contextmanager
from pathlib import Path

import config


logger = logging.getLogger(__name__)


class DocumentPreviewError(RuntimeError):
    """Raised when a supported document cannot be converted for preview."""


_LOCKS = weakref.WeakValueDictionary()
_LOCKS_GUARD = threading.Lock()
_WORD_AUTOMATION_MUTEX = r"Local\ArabicAcademicPlagiarismSystem.WordPreview"
_WORD_AUTOMATION_TIMEOUT_MS = 300_000


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


@contextmanager
def _word_automation_lock():
    """Serialize Word COM automation across local application processes.

    Word exposes a shared out-of-process COM server. Starting concurrent
    ``DispatchEx``/export lifecycles from separate scan workers or processes
    can tear down that server while another caller is exporting, producing the
    Windows RPC error 0x800706be. A named Windows mutex covers the complete
    COM lifecycle; the ordinary in-process preview-cache lock remains in place
    for per-document deduplication.
    """
    if sys.platform != "win32":
        yield
        return

    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.ReleaseMutex.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel32.CreateMutexW(None, False, _WORD_AUTOMATION_MUTEX)
    if not handle:
        raise DocumentPreviewError("تعذر إنشاء قفل تحويل Microsoft Word")

    acquired = False
    try:
        result = kernel32.WaitForSingleObject(handle, _WORD_AUTOMATION_TIMEOUT_MS)
        if result not in (0, 0x80):  # WAIT_OBJECT_0 / WAIT_ABANDONED
            raise DocumentPreviewError("انتهت مهلة انتظار محول Microsoft Word")
        acquired = True
        yield
    finally:
        if acquired:
            kernel32.ReleaseMutex(handle)
        kernel32.CloseHandle(handle)


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
    owned_process = None
    with _word_automation_lock():
        pythoncom.CoInitialize()
        try:
            word = win32com.client.DispatchEx("Word.Application")
            try:
                import psutil
                import win32process
                _, process_id = win32process.GetWindowThreadProcessId(word.Hwnd)
                owned_process = psutil.Process(process_id)
            except Exception:
                logger.warning('Cannot observe owned Word shutdown', exc_info=True)
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
                    document.Close(SaveChanges=0)  # wdDoNotSaveChanges (integer enum)
                except Exception:
                    logger.warning("Failed to close Word preview document", exc_info=True)
            # Release the child COM proxy before asking its server to shut down.
            document = None
            if word is not None:
                try:
                    word.Quit(SaveChanges=0)  # avoid a VARIANT_BOOL for WdSaveOptions
                except Exception:
                    logger.warning("Failed to close Word preview process", exc_info=True)
            word = None
            pythoncom.CoUninitialize()
            if owned_process is not None:
                try:
                    owned_process.wait(timeout=5)
                except Exception:
                    # Do not kill a Word process: COM may share a server with a user.
                    logger.warning('Word process %s has not confirmed shutdown', owned_process.pid, exc_info=True)


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
                '-env:UserInstallation=' + (output_dir / 'profile').resolve().as_uri(),
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
    except subprocess.TimeoutExpired as exc:
        raise DocumentPreviewError('Local LibreOffice conversion timed out') from exc
    finally:
        try:
            shutil.rmtree(output_dir)
        except OSError:
            logger.warning('Failed to remove conversion directory %s', output_dir, exc_info=True)


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
