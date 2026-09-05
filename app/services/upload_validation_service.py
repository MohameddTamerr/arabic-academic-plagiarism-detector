# -*- coding: utf-8 -*-
"""
خدمة تدقيق وتحصين الملفات المرفوعة (Centralized Upload & Input Validation Service):
- تدقيق امتداد وبصمة وتوقيع المحتوى (Magic Bytes / File Signatures) لكافة صيغ الأبحاث (PDF, DOCX, TXT).
- فرض حدود الأحجام عبر الدفق المباشر (Streaming Size Enforcement) دون حجز الذاكرة.
- فحص عميق وآمن لملفات PDF (كشف التشفير، حد الصفحات، بنية الملف).
- فحص وقائي لحزم Word DOCX (كشف القنابل الانضغاطية Zip-Bombs، Zip-Slip، معايير OpenXML).
- تنقية أسماء الملفات ومنع هجمات التخطي المساري (Path Traversal) مع الحفاظ على الأسماء العربية.
- إدارة عزل الرفع المؤقت (Staging Lifecycle) والنقل الذري بعد تمام التحقق.
"""

import os
import re
import sys
import io
import uuid
import time
import zipfile
import logging
import unicodedata
from pathlib import Path
from typing import Optional, Dict, Any, Union, BinaryIO, Set

import config
from app.errors.error_codes import ErrorCode
from app.errors.exceptions import ValidationError
from app.services import integrity_service, storage_service
from app.logging_config import log_operational_event

logger = logging.getLogger(__name__)

# الأسماء المحجوزة في أنظمة Windows
_WINDOWS_RESERVED_NAMES = {
    'CON', 'PRN', 'AUX', 'NUL',
    'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
    'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
}

# محارف التحكم والرموز المحظورة في أسماء الملفات
_INVALID_FILENAME_CHARS = re.compile(r'[\x00-\x1f\x7f-\x9f\\/\:\*\?\"\<\>\|]')


def sanitize_upload_filename(filename: str) -> tuple[str, str]:
    """
    تنقية اسم الملف المرفوع وحمايته من التخطي المساري والرموز غير الآمنة
    مع الحفاظ الكامل على الأسماء الأكاديمية باللغة العربية.
    يُعيد: (safe_display_name, safe_extension)
    """
    if not filename or not isinstance(filename, str):
        filename = "document"

    # 1. إزالة مسارات المجلدات واستخراج اسم الملف فقط
    raw_name = Path(filename).name.strip()
    raw_name = unicodedata.normalize('NFKC', raw_name)

    # 2. استخراج الامتداد وتحويله لأحرف صغيرة
    ext = Path(raw_name).suffix.lower()
    base = Path(raw_name).stem

    # 3. إزالة محارف التحكم والمسارات والرموز المحظورة
    clean_base = _INVALID_FILENAME_CHARS.sub('_', base)
    clean_base = clean_base.replace('..', '_').strip('. ')

    # 4. معالجة الأسماء المحجوزة في Windows
    if clean_base.upper() in _WINDOWS_RESERVED_NAMES:
        clean_base = f"doc_{clean_base}"

    # 5. إذا أصبح الاسم فارغاً
    if not clean_base:
        clean_base = "academic_document"

    # 6. تقليص الطول إلى 150 محرفاً لتفادي تجاوز مسارات نظام التشغيل
    if len(clean_base) > 150:
        clean_base = clean_base[:150]

    safe_display_name = f"{clean_base}{ext}" if ext else clean_base
    return safe_display_name, ext


def validate_and_stage_upload(
    file_stream: Union[BinaryIO, bytes, io.BytesIO],
    original_filename: str,
    max_bytes: Optional[int] = None,
    allowed_extensions: Optional[Set[str]] = None
) -> Dict[str, Any]:
    """
    تدقيق دفق الملف وحفظه مؤقتاً في Staging مع التحقق من البصمة وبنية المحتوى:
    1. تنقية اسم الملف وفحص الامتداد في القائمة المسموحة.
    2. الكتابة عبر دفق مقيد بالحجم الأقصى (Streaming Size Enforcement).
    3. حساب البصمة الرقمية SHA-256 أثناء الدفق.
    4. الفحص الهيكلي لتوقيع وبنية الملف (PDF, DOCX, TXT).
    5. إرجاع بيانات التدقيق المهيكلة ومسار Staging.
    """
    safe_display_name, ext = sanitize_upload_filename(original_filename)
    allowed_exts = allowed_extensions or config.ALLOWED_EXTENSIONS

    # 1. التحقق من الامتداد
    if not ext or ext not in allowed_exts:
        log_operational_event(
            level=logging.WARNING,
            message=f"محاولة رفع ملف بامتداد غير مدعوم: {ext}",
            component="upload",
            error_code=ErrorCode.FILE_UNSUPPORTED
        )
        raise ValidationError(
            f"نوع الملف «{ext or 'غير معروف'}» غير مدعوم. الأنواع المقبولة هي: {', '.join(sorted(allowed_exts))}",
            code=ErrorCode.FILE_UNSUPPORTED,
            status_code=400
        )

    max_allowed = max_bytes or config.MAX_UPLOAD_BYTES
    staging_dir = storage_service.get_staging_upload_dir()
    staging_token = uuid.uuid4().hex
    staging_filename = f".stage_{staging_token}_{safe_display_name}"
    staging_path = staging_dir / staging_filename

    total_bytes = 0
    import hashlib
    hasher = hashlib.sha256()

    try:
        # 2. الكتابة المباشرة في كتل 64KB مع مراقبة الحجم والبصمة
        with open(staging_path, 'wb') as f:
            if isinstance(file_stream, bytes):
                total_bytes = len(file_stream)
                if total_bytes > max_allowed:
                    raise ValidationError(
                        f"حجم الملف يتجاوز الحد الأقصى المسموح به ({max_allowed // (1024 * 1024)} ميجابايت).",
                        code=ErrorCode.FILE_TOO_LARGE,
                        status_code=413
                    )
                f.write(file_stream)
                hasher.update(file_stream)
            elif hasattr(file_stream, 'read'):
                while True:
                    chunk = file_stream.read(65536)
                    if not chunk:
                        break
                    total_bytes += len(chunk)
                    if total_bytes > max_allowed:
                        raise ValidationError(
                            f"حجم الملف يتجاوز الحد الأقصى المسموح به ({max_allowed // (1024 * 1024)} ميجابايت).",
                            code=ErrorCode.FILE_TOO_LARGE,
                            status_code=413
                        )
                    f.write(chunk)
                    hasher.update(chunk)
            f.flush()
            os.fsync(f.fileno())

        if total_bytes == 0:
            raise ValidationError(
                "الملف المرفوع فارغ تماماً (0 بايت).",
                code=ErrorCode.FILE_EMPTY,
                status_code=400
            )

        file_hash = hasher.hexdigest()

        # 3. التحقق الهيكلي من توقيع وبنية الملف (File Signature & Structure Inspection)
        detected_type = _inspect_file_structure(staging_path, ext)

        return {
            'success': True,
            'original_filename': safe_display_name,
            'safe_extension': ext,
            'detected_type': detected_type,
            'size_bytes': total_bytes,
            'sha256': file_hash,
            'staging_path': str(staging_path),
            'validation_status': 'validated'
        }

    except Exception as e:
        # تنظيف ملف Staging فوراً عند فشل التحقق
        cleanup_staging_file(staging_path)
        if isinstance(e, ValidationError):
            raise
        logger.error(f"فشل التحقق من الملف المرفوع {original_filename}: {e}", exc_info=True)
        raise ValidationError(
            f"تعذر التحقق من سلامة الملف المرفوع: {str(e)}",
            code=ErrorCode.FILE_CORRUPTED,
            status_code=400
        )


def _inspect_file_structure(staging_path: Path, ext: str) -> str:
    """
    فحص توقيع وبنية الملف بحسب نوعه للتأكد من أمانه ومطابقته للمواصفات الأكاديمية.
    """
    if ext == '.pdf':
        return _inspect_pdf(staging_path)
    elif ext == '.docx':
        return _inspect_docx(staging_path)
    elif ext == '.txt':
        return _inspect_txt(staging_path)
    else:
        raise ValidationError("نوع الملف غير مدعوم.", code=ErrorCode.FILE_UNSUPPORTED, status_code=400)


def _inspect_pdf(path: Path) -> str:
    """فحص سلامة وتوقيع ملف PDF وتوافق عدد الصفحات والتشفير."""
    # 1. فحص البايتات السحرية (%PDF-)
    with open(path, 'rb') as f:
        header = f.read(1024)
        if b'%PDF-' not in header:
            raise ValidationError(
                "الملف المرفوع لا يطابق البنية الرقمية لملفات PDF (توقيع غير صالح).",
                code=ErrorCode.FILE_SIGNATURE_MISMATCH,
                status_code=400
            )

    # 2. فحص بنيوي دفاعي باستخدام fitz
    try:
        import fitz
        doc = fitz.open(str(path))
        if doc.is_encrypted:
            raise ValidationError(
                "ملف PDF محمي بكلمة مرور أو مشفر ويتعذر فحصه.",
                code=ErrorCode.FILE_ENCRYPTED,
                status_code=400
            )
        page_count = len(doc)
        if page_count == 0:
            raise ValidationError(
                "ملف PDF لا يحتوي على أي صفحات صالحة.",
                code=ErrorCode.FILE_EMPTY,
                status_code=400
            )
        if page_count > config.MAX_PDF_PAGES:
            raise ValidationError(
                f"عدد صفحات ملف PDF ({page_count}) يتجاوز الحد الأقصى المسموح ({config.MAX_PDF_PAGES} صفحة).",
                code=ErrorCode.PDF_PAGE_LIMIT,
                status_code=400
            )
        doc.close()
        return 'pdf'
    except ValidationError:
        raise
    except Exception as e:
        logger.warning(f"فحص PyMuPDF للملف {path.name} أظهر خللاً: {e}")
        # محاولة بديلة عبر pdfplumber
        try:
            import pdfplumber
            with pdfplumber.open(str(path)) as pdf:
                if len(pdf.pages) == 0:
                    raise ValidationError("ملف PDF فارغ تماماً.", code=ErrorCode.FILE_EMPTY, status_code=400)
                if len(pdf.pages) > config.MAX_PDF_PAGES:
                    raise ValidationError(
                        f"عدد صفحات ملف PDF ({len(pdf.pages)}) يتجاوز الحد الأقصى المسموح.",
                        code=ErrorCode.PDF_PAGE_LIMIT,
                        status_code=400
                    )
            return 'pdf'
        except ValidationError:
            raise
        except Exception as e2:
            raise ValidationError(
                "بنية ملف PDF معطوبة أو تالفة ولا يمكن قراءتها بأمان.",
                code=ErrorCode.FILE_CORRUPTED,
                status_code=400
            )


def _inspect_docx(path: Path) -> str:
    """فحص سلامة حزمة Word DOCX ومقاومة Zip-Bomb و Zip-Slip."""
    # 1. فحص البايتات السحرية للأرشيف (PK\x03\x04)
    with open(path, 'rb') as f:
        magic = f.read(4)
        if magic != b'PK\x03\x04':
            raise ValidationError(
                "الملف المرفوع لا يطابق البنية الرقمية لمستندات Word DOCX.",
                code=ErrorCode.FILE_SIGNATURE_MISMATCH,
                status_code=400
            )

    # 2. فحص دليل الأرشيف المركزي بدون فك الضغط على القرص
    try:
        with zipfile.ZipFile(str(path), 'r') as z:
            members = z.infolist()
            if len(members) > config.MAX_DOCX_ENTRIES:
                raise ValidationError(
                    f"حزمة ملف Word تحتوي على عدد عناصر كبير جداً ({len(members)}) يتجاوز الحد المسموح ({config.MAX_DOCX_ENTRIES}).",
                    code=ErrorCode.DOCX_RESOURCE_LIMIT,
                    status_code=400
                )

            total_uncompressed = 0
            total_compressed = 0
            names = set()

            for member in members:
                # أمان المسارات: منع Zip-Slip والمسارات المطلقة
                m_name = member.filename
                names.add(m_name)

                if m_name.startswith('/') or m_name.startswith('\\') or '..' in m_name or re.match(r'^[a-zA-Z]:', m_name):
                    raise ValidationError(
                        "حزمة الأرشيف تحتوي على مسارات ملفات غير آمنة (Zip Traversal).",
                        code=ErrorCode.DOCX_ARCHIVE_UNSAFE,
                        status_code=400
                    )

                if member.file_size > config.MAX_DOCX_SINGLE_ENTRY_BYTES:
                    raise ValidationError(
                        f"أحد ملفات حزمة Word يتجاوز الحد الأقصى المسموح ({member.file_size // (1024 * 1024)} ميجابايت).",
                        code=ErrorCode.DOCX_RESOURCE_LIMIT,
                        status_code=400
                    )

                total_uncompressed += member.file_size
                total_compressed += member.compress_size

            # فحص إجمالي الحجم بعد فك الضغط
            if total_uncompressed > config.MAX_DOCX_UNCOMPRESSED_BYTES:
                raise ValidationError(
                    f"الحجم الإجمالي لمحتويات ملف Word بعد فك الضغط ({total_uncompressed // (1024 * 1024)} ميجابايت) يتجاوز الحد المسموح.",
                    code=ErrorCode.DOCX_RESOURCE_LIMIT,
                    status_code=400
                )

            # فحص نسبة الضغط (مقاومة Zip-Bomb)
            if total_compressed > 0:
                ratio = total_uncompressed / max(total_compressed, 1)
                if ratio > config.MAX_DOCX_COMPRESSION_RATIO:
                    raise ValidationError(
                        f"نسبة ضغط ملف Word مرتفعة جداً ومريبة ({ratio:.1f}x) وتتجاوز معايير الأمان.",
                        code=ErrorCode.DOCX_RESOURCE_LIMIT,
                        status_code=400
                    )

            # التحقق من وجود المكونات البنيوية الأساسية لـ DOCX OpenXML
            if '[Content_Types].xml' not in names or 'word/document.xml' not in names:
                raise ValidationError(
                    "ملف الأرشيف لا يحتوي على البنية القياسية لمستندات Word OpenXML.",
                    code=ErrorCode.FILE_CORRUPTED,
                    status_code=400
                )

        return 'docx'
    except ValidationError:
        raise
    except zipfile.BadZipFile:
        raise ValidationError(
            "ملف Word تالف أو ليس أرشيفاً صالحاً.",
            code=ErrorCode.FILE_CORRUPTED,
            status_code=400
        )
    except Exception as e:
        raise ValidationError(
            f"فشل التحقق من بنية ملف Word: {str(e)}",
            code=ErrorCode.FILE_CORRUPTED,
            status_code=400
        )


def _inspect_txt(path: Path) -> str:
    """فحص سلامة وترميز الملف النصي وخلوه من البيانات الثنائية غير الصالحة."""
    file_size = path.stat().st_size
    if file_size > config.MAX_TXT_BYTES:
        raise ValidationError(
            f"حجم الملف النصي يتجاوز الحد الأقصى المسموح ({config.MAX_TXT_BYTES // (1024 * 1024)} ميجابايت).",
            code=ErrorCode.FILE_TOO_LARGE,
            status_code=413
        )

    # قراءة عينة لاكتشاف البايتات الثنائية
    with open(path, 'rb') as f:
        sample = f.read(8192)
        if b'\x00' in sample:
            raise ValidationError(
                "الملف النصي يحتوي على بايتات ثنائية فارغة (NUL bytes) غير صالحة كنص.",
                code=ErrorCode.FILE_CORRUPTED,
                status_code=400
            )

    # محاولة فك الترميز بترميزات النصوص المقبولة (UTF-8 و Windows-1256 العربي)
    text_content = None
    for enc in ('utf-8', 'utf-8-sig', 'windows-1256'):
        try:
            with open(path, 'r', encoding=enc) as f:
                text_content = f.read(1000)
            break
        except UnicodeDecodeError:
            continue

    if text_content is None:
        raise ValidationError(
            "تعذر فك ترميز الملف النصي بترميز صالح ومقروء.",
            code=ErrorCode.FILE_CORRUPTED,
            status_code=400
        )

    return 'txt'


def finalize_validated_upload(
    validation_result: Dict[str, Any],
    target_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """
    نقل الملف المدقق ذرياً من Staging إلى مجلد التخزين النهائي وتوليد السجل المعتمد.
    """
    target_dir = target_dir or storage_service.get_finalized_upload_dir()
    staging_path = Path(validation_result['staging_path'])

    if not staging_path.exists():
        raise ValidationError(
            "ملف الرفع المؤقت غير موجود لإتمام التثبيت.",
            code=ErrorCode.STORAGE_ERROR,
            status_code=500
        )

    safe_orig = validation_result['original_filename']
    ext = validation_result['safe_extension']
    unique_token = uuid.uuid4().hex[:12]
    stored_filename = f"{unique_token}_{safe_orig}"
    final_path = target_dir / stored_filename

    try:
        # النقل الذري
        os.replace(str(staging_path), str(final_path))

        return {
            'success': True,
            'original_filename': safe_orig,
            'stored_filename': stored_filename,
            'file_path': str(final_path),
            'file_size_bytes': validation_result['size_bytes'],
            'file_hash': validation_result['sha256'],
            'file_type': ext.lstrip('.')
        }
    except Exception as e:
        logger.error(f"فشل النقل الذري للملف المدقق {safe_orig}: {e}", exc_info=True)
        cleanup_staging_file(staging_path)
        raise ValidationError(
            f"فشل تثبيت الملف المدقق في وسيط التخزين النهائي: {str(e)}",
            code=ErrorCode.STORAGE_ERROR,
            status_code=500
        )


def cleanup_staging_file(staging_path: Union[str, Path]) -> None:
    """حذف ملف Staging المؤقت بأمان عند فشل التحقق."""
    try:
        p = Path(staging_path)
        if p.exists():
            p.unlink()
    except Exception as e:
        logger.debug(f"تعذر حذف ملف Staging {staging_path}: {e}")


def clean_stale_staging(max_age_seconds: int = 3600) -> int:
    """
    وظيفة صيانة دورية لحذف الملفات المؤقتة في مجلد .staging_uploads
    التي تجاوز عمرها الحد المحدد (افتراضياً ساعة واحدة).
    """
    staging_dir = storage_service.get_staging_upload_dir()
    if not staging_dir.exists():
        return 0

    now = time.time()
    deleted_count = 0

    try:
        for item in staging_dir.iterdir():
            if item.is_file():
                try:
                    age = now - item.stat().st_mtime
                    if age > max_age_seconds:
                        item.unlink()
                        deleted_count += 1
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"خطأ أثناء تنظيف مجلد Staging: {e}")

    return deleted_count
