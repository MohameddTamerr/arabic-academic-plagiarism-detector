# -*- coding: utf-8 -*-
"""
خدمة إدارة دورة حياة وتخزين الملفات الآمن (Atomic Storage & File Lifecycle Service):
- دورة حياة منضبطة: staging/temp -> كتابة كاملة -> fsync/إغلاق -> حساب SHA-256 والحجم -> نقل ذري (atomic rename) -> تثبيت DB.
- ضمان عدم قراءة أو نسخ أي ملف قبل اكتمال كتابته وتثبيته.
- تنظيف الملفات غير المكتملة أو اليتيمة عند فشل أي خطوة.
"""

import os
import io
import uuid
import shutil
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Union, BinaryIO

import config
from app.services import integrity_service

logger = logging.getLogger(__name__)


def get_staging_upload_dir() -> Path:
    """مجلد العزل المؤقت للرفع أثناء مرحلة الكتابة."""
    temp_up = getattr(config, 'TEMP_UPLOAD_DIR', None) or (Path(config.STORAGE_ROOT) / 'temp_uploads')
    staging_dir = Path(temp_up) / '.staging_uploads'
    staging_dir.mkdir(parents=True, exist_ok=True)
    return staging_dir


def get_finalized_upload_dir() -> Path:
    """مجلد التخزين النهائي للملفات المعتمدة."""
    temp_up = getattr(config, 'TEMP_UPLOAD_DIR', None) or (Path(config.STORAGE_ROOT) / 'temp_uploads')
    final_dir = Path(temp_up)
    final_dir.mkdir(parents=True, exist_ok=True)
    return final_dir


def save_stream_atomically(
    file_stream: Union[BinaryIO, bytes, io.BytesIO],
    original_filename: str,
    target_dir: Optional[Path] = None,
    expected_hash: Optional[str] = None
) -> Dict[str, Any]:
    """
    حفظ دفق الملف عبر دورة حياة ذرية وآمنة:
    1. الكتابة إلى ملف مؤقت في مجلد staging.
    2. تطبيق flush و fsync لضمان ثبات البايتات على القرص.
    3. حساب البصمة الرقمية SHA-256 وحجم البايتات.
    4. النقل الذري (Atomic rename / replace) إلى المجلد النهائي.
    5. التحقق من تطابق البصمة مع المتوقع إن وجد.
    """
    target_dir = target_dir or get_finalized_upload_dir()
    staging_dir = get_staging_upload_dir()

    # تنظيف اسم الملف الأصلي وتوليد اسم تخزين آمن وفريد
    safe_orig = Path(original_filename).name.replace('..', '').strip()
    ext = Path(safe_orig).suffix.lower()
    if not ext:
        ext = '.bin'
    
    unique_token = uuid.uuid4().hex[:12]
    stored_filename = f"{unique_token}_{safe_orig}"
    staging_filename = f".staging_{unique_token}_{safe_orig}"

    staging_path = staging_dir / staging_filename
    final_path = target_dir / stored_filename

    try:
        # 1. كتابة البايتات في staging
        with open(staging_path, 'wb') as f:
            if isinstance(file_stream, bytes):
                f.write(file_stream)
            elif hasattr(file_stream, 'read'):
                # قراءة وكتابة في كتل 64KB
                while True:
                    chunk = file_stream.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
            f.flush()
            os.fsync(f.fileno())

        # 2. فحص الحجم والبصمة الرقمية
        file_size = staging_path.stat().st_size
        file_hash, _ = integrity_service.compute_stream_sha256(staging_path)

        if expected_hash and file_hash.lower() != expected_hash.lower():
            raise ValueError(f"البصمة الرقمية للملف المحفوظ لا تطابق المتوقع (محسوبة: {file_hash[:12]}، متوقعة: {expected_hash[:12]})")

        # 3. النقل الذري إلى المجلد النهائي
        os.replace(str(staging_path), str(final_path))

        return {
            'success': True,
            'original_filename': safe_orig,
            'stored_filename': stored_filename,
            'file_path': str(final_path),
            'file_size_bytes': file_size,
            'file_hash': file_hash,
            'file_type': ext.lstrip('.')
        }

    except Exception as e:
        logger.error(f"فشل حفظ الملف ذرياً {original_filename}: {e}")
        if staging_path.exists():
            try:
                os.unlink(str(staging_path))
            except Exception:
                pass
        if final_path.exists():
            try:
                os.unlink(str(final_path))
            except Exception:
                pass
        raise


# ─── Enterprise Storage Abstraction & Content-Addressed Interface ─────────────

_GLOBAL_STORAGE_BACKEND = None


def get_storage_backend():
    """استرجاع محرك التخزين النشط وفق الإعدادات مع حظر أي سقوط صامت."""
    global _GLOBAL_STORAGE_BACKEND
    if _GLOBAL_STORAGE_BACKEND is None:
        backend_type = getattr(config, 'STORAGE_BACKEND', 'filesystem').lower()
        if backend_type == 's3_compatible_local':
            from app.storage.s3_local_backend import S3CompatibleLocalStorageBackend
            endpoint = getattr(config, 'S3_LOCAL_ENDPOINT', 'http://127.0.0.1:9000')
            bucket = getattr(config, 'S3_LOCAL_BUCKET', 'plagiarism-documents')
            backend = S3CompatibleLocalStorageBackend(endpoint_url=endpoint, bucket_name=bucket)
            if not backend.is_available():
                raise RuntimeError(
                    "LOCAL OBJECT STORAGE RUNTIME ERROR: S3-compatible local storage is configured "
                    "(STORAGE_BACKEND=s3_compatible_local) but the local object server is unavailable. "
                    "Silent fallback to filesystem is strictly prohibited."
                )
            _GLOBAL_STORAGE_BACKEND = backend
        elif backend_type in ('filesystem', 'filesystem_cas', 'local'):
            from app.storage.filesystem_backend import FileSystemStorageBackend
            _GLOBAL_STORAGE_BACKEND = FileSystemStorageBackend(config.STORAGE_ROOT)
        else:
            raise ValueError(f"Unknown storage backend configured: {backend_type}")
    return _GLOBAL_STORAGE_BACKEND


def store_document_cas(
    stream_or_bytes: Union[BinaryIO, bytes],
    content_hash: str,
    ext: str = '.bin',
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """تخزين دفق الوثيقة في هيكل التخزين المؤسسي الموجه بالمحتوى (CAS)."""
    backend = get_storage_backend()
    return backend.put(stream_or_bytes, content_hash, ext=ext, metadata=metadata)


def count_content_references(content_hash: str) -> int:
    """احتساب عدد السجلات التي تشير إلى نفس البصمة في قاعدة البيانات."""
    from app.repositories import base_repo
    from app.models.research_schema import ResearchFile, Research
    from app.models.schema import Document

    h = content_hash.strip().lower()
    total_refs = 0
    with base_repo.get_session() as session:
        # 1. ملفات الأبحاث
        total_refs += session.query(ResearchFile).filter(ResearchFile.file_hash == h).count()
        # 2. مستندات قاعدة المراجع
        total_refs += session.query(Document).filter(Document.file_hash == h).count()
    return total_refs


def delete_content_reference(content_hash: str) -> bool:
    """
    حذف محكوم بالارتباط (Reference-Aware Deletion):
    - لا يُحذف الملف الفيزيائي من CAS إلا إذا وصل عدد الإشارات المرجعية له إلى 0.
    """
    ref_count = count_content_references(content_hash)
    if ref_count > 0:
        logger.info(f"المحتوى {content_hash[:12]} لا يزال مستخدماً في {ref_count} سجل. لن يتم حذفه فيزيائياً.")
        return False

    backend = get_storage_backend()
    deleted = backend.delete(content_hash)
    logger.info(f"تم حذف الملف الفيزيائي {content_hash[:12]} من التخزين بنجاح (عدد الإشارات: 0).")
    return deleted


def verify_storage_integrity(sample_limit: Optional[int] = None) -> Dict[str, Any]:
    """
    فحص وتدقيق سلامة التخزين المؤسسي (Storage Integrity Audit):
    - التحقق من وجود الملفات المسجلة ومطابقة بصمات SHA-256 وأحجام البايتات.
    - تصنيف الحالات: OK, MISSING, HASH_MISMATCH, ORPHANED, UNREGISTERED.
    """
    from app.repositories import base_repo
    from app.models.research_schema import ResearchFile
    from app.models.schema import Document

    backend = get_storage_backend()
    results = {
        'total_checked': 0,
        'ok_count': 0,
        'missing_count': 0,
        'mismatch_count': 0,
        'details': []
    }

    with base_repo.get_session() as session:
        files = session.query(ResearchFile).all()
        if sample_limit:
            files = files[:sample_limit]

        for rf in files:
            results['total_checked'] += 1
            f_hash = rf.file_hash
            f_path = Path(rf.file_path) if rf.file_path else None

            # فحص إما عبر المسار المباشر أو عبر CAS
            exists_on_disk = (f_path and f_path.exists()) or (f_hash and backend.exists(f_hash))
            if not exists_on_disk:
                results['missing_count'] += 1
                results['details'].append({
                    'id': rf.id,
                    'file_name': rf.original_filename,
                    'hash': f_hash,
                    'status': 'MISSING'
                })
                continue

            # التحقق من الهاش
            target_file = f_path if (f_path and f_path.exists()) else backend.get_physical_path(f_hash)
            if target_file:
                computed_hash, _ = integrity_service.compute_stream_sha256(target_file)
                if f_hash and computed_hash.lower() != f_hash.lower():
                    results['mismatch_count'] += 1
                    results['details'].append({
                        'id': rf.id,
                        'file_name': rf.original_filename,
                        'expected_hash': f_hash,
                        'computed_hash': computed_hash,
                        'status': 'HASH_MISMATCH'
                    })
                else:
                    results['ok_count'] += 1

    return results


# ─── Storage Invariant & Orphan Maintenance ───────────────────────────────────

def detect_orphan_storage_files(storage_dir: Optional[Path] = None) -> list[Path]:
    """
    اكتشاف الملفات الفيزيائية على القرص غير المسجلة في قاعدة البيانات المعتمدة.
    """
    from app.repositories import base_repo
    from app.models.research_schema import ResearchFile

    storage_dir = storage_dir or get_finalized_upload_dir()
    if not storage_dir.exists():
        return []

    with base_repo.get_session() as session:
        registered_filenames = {
            r.stored_filename for r in session.query(ResearchFile.stored_filename).all() if r.stored_filename
        }

    orphans = []
    for item in storage_dir.iterdir():
        if item.is_file() and not item.name.startswith('.'):
            if item.name not in registered_filenames:
                orphans.append(item)
    return orphans


def cleanup_orphan_storage_files(storage_dir: Optional[Path] = None) -> int:
    """
    تنظيف صريح للملفات اليتيمة غير المسجلة (للاستخدام في الصيانة اليدوية فقط).
    """
    orphans = detect_orphan_storage_files(storage_dir)
    deleted_count = 0
    for orphan in orphans:
        try:
            orphan.unlink()
            deleted_count += 1
        except Exception as e:
            logger.warning(f"تعذر حذف الملف اليتيم {orphan}: {e}")
    return deleted_count

