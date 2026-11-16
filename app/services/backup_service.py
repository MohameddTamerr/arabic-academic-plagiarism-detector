# -*- coding: utf-8 -*-
"""
خدمة النسخ الاحتياطي والتعافي من الكوارث (Institutional Backup & Disaster Recovery Service):
- إنشاء نسخ احتياطية شاملة ومتسقة ومتحقق من سلامتها بتجزئة SHA-256 (SHA-256 Checksum Verification).
- استخدام SQLite Online Backup API لضمان اتساق البيانات مع نمط WAL ومنع النسخ غير الآمن.
- بناء حزم نسخ ذاتية التوصيف (Self-Describing Packages) مع بيان تفصيلي (manifest.json).
- فحص سلامة وتحقق متعدد المراحل (Validation) مع اختبار الجداول وPRAGMA integrity_check.
- استعادة آمنة محصنة (Safe Restore) مع نسخة طوارئ مسبقة (Pre-Restore Snapshot) وإمكانية التراجع التلقائي (Rollback).
- إدارة مدة الحفظ (Retention Management) دون المساس بأحدث نسخة صالحة.
"""

import os
import sys
import time
import json
import uuid
import zipfile
import sqlite3
import shutil
import logging
import re
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, Dict, Any, List


import config
from app import versioning
from app.repositories import backup_repo, base_repo
from app.services import audit_service, reference_service, integrity_service, snapshot_service
from app.services import backup_persistent_files

logger = logging.getLogger(__name__)

# قفل لمنع استعادة نسختين في نفس اللحظة عبر مسارات متزامنة في نفس العملية
_RESTORE_MUTEX = threading.Lock()
_BACKUP_IN_PROGRESS = False
_BACKUP_LOCK = threading.Lock()

# الإصدار الحالي لبيان النسخ
MANIFEST_SCHEMA_VERSION = "1.0"


def get_backup_dir() -> Path:
    """استرجاع والتأكد من وجود مجلد النسخ الاحتياطية."""
    b_dir = getattr(config, 'BACKUP_DIR', config.STORAGE_ROOT / 'backups')
    b_dir.mkdir(parents=True, exist_ok=True)
    return b_dir


def _remove_owned_directory(path: Path, parent: Path) -> None:
    """Remove only the directory created by this operation inside its trusted parent."""
    try:
        trusted=parent.resolve()
        target=path.resolve()
        if path.is_symlink() or target.parent != trusted:
            raise ValueError('Cleanup target escaped its trusted parent')
        shutil.rmtree(path)
    except FileNotFoundError:
        pass
    except Exception:
        logger.warning('Unable to safely remove operation directory %s',path,exc_info=True)


def _locate_backup_path(backup_identifier: str, entry=None) -> Optional[Path]:
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', backup_identifier or ''):
        raise ValueError('Invalid backup identifier')
    root=get_backup_dir().resolve()
    if entry and entry.get('file_path'):
        candidate=Path(entry['file_path']).resolve()
        if candidate.is_relative_to(root) and candidate.is_file():return candidate
    for candidate in sorted(root.glob(f'{backup_identifier}_*.zip')):
        resolved=candidate.resolve()
        if resolved.is_relative_to(root) and resolved.is_file():return resolved
    return None


class CrossProcessRestoreLock:
    """
    قفل استعادة موثوق وحاكم عبر العمليات المتعددة (Cross-Process Authoritative Restore Lock):
    - يعتمد على ملف قفل ذري (.restore.lock) مدعوم برقم العملية (PID) وطابع زمني وهوية فريدة.
    - يمنع تماماً تنفيذ عمليتي استعادة في نفس الوقت عبر عمليات نظام التشغيل المختلفة.
    - يدعم كشف واسترداد الأقفال الميتة (Stale Locks) إذا توقفت العملية السابقة دون تحرير القفل.
    - يضمن التحرير الحتمي للقفل في كتلة finally أو عند خروج مدير السياق.
    """
    def __init__(self, owner: str = 'system', timeout_seconds: int = 300, lock_file_path: Optional[Path] = None):
        self.owner = owner
        self.timeout_seconds = timeout_seconds
        self.lock_file = lock_file_path or (get_backup_dir() / '.restore.lock')
        self.token = str(uuid.uuid4())
        self._fd = None
        self._acquired = False

    def acquire(self, blocking: bool = False, poll_interval: float = 0.1) -> bool:
        start_time = time.time()
        while True:
            # 1. فحص القفل الحالي إذا كان موجوداً
            if self.lock_file.exists():
                is_stale = self._check_and_clean_stale_lock()
                if not is_stale:
                    if not blocking:
                        return False
                    if time.time() - start_time > self.timeout_seconds:
                        return False
                    time.sleep(poll_interval)
                    continue

            # 2. محاولة إنشاء ملف القفل ذرياً على مستوى نظام التشغيل
            try:
                flags = os.O_CREAT | os.O_EXCL | os.O_RDWR
                self._fd = os.open(str(self.lock_file), flags, 0o600)
                payload = {
                    'token': self.token,
                    'owner': self.owner,
                    'pid': os.getpid(),
                    'acquired_at': datetime.utcnow().isoformat(),
                    'expires_at': time.time() + self.timeout_seconds
                }
                os.write(self._fd, json.dumps(payload).encode('utf-8'))
                self._acquired = True
                return True
            except (FileExistsError, OSError):
                if not blocking:
                    return False
                if time.time() - start_time > self.timeout_seconds:
                    return False
                time.sleep(poll_interval)

    def _check_and_clean_stale_lock(self) -> bool:
        try:
            if not self.lock_file.exists():
                return True
            with open(self.lock_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:
                    self._force_remove_lock_file()
                    return True
                data = json.loads(content)

            expires_at = data.get('expires_at', 0)
            pid = data.get('pid')

            # فحص انتهاء مدة التأجير
            if time.time() > expires_at:
                logger.warning(f"تم اكتشاف قفل استعادة منتهي الصلاحية (Stale Lock) لمالكه {data.get('owner')} (PID {pid}). جاري الاسترداد...")
                self._force_remove_lock_file()
                return True

            # فحص ما إذا كانت العملية ميتة
            if pid and not self._is_process_alive(pid):
                logger.warning(f"تم اكتشاف قفل استعادة لعملية غير موجودة (Dead PID {pid}). جاري الاسترداد...")
                self._force_remove_lock_file()
                return True

            return False
        except Exception as e:
            logger.warning(f"تعذر فحص ملف القفل: {e}. جاري تجاوزه...")
            self._force_remove_lock_file()
            return True

    @staticmethod
    def _is_process_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            if os.name == 'nt':
                import ctypes
                kernel32 = ctypes.windll.kernel32
                SYNCHRONIZE = 0x00100000
                process = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
                if process:
                    wait_res = kernel32.WaitForSingleObject(process, 0)
                    kernel32.CloseHandle(process)
                    # 0x00000102 (WAIT_TIMEOUT) means the process is still running (unsignaled)
                    return wait_res == 0x00000102
                return False
            else:
                os.kill(pid, 0)
                return True
        except Exception:
            return False

    def _force_remove_lock_file(self):
        try:
            if self._fd is not None:
                try:
                    os.close(self._fd)
                except Exception:
                    pass
                self._fd = None
            if self.lock_file.exists():
                os.unlink(str(self.lock_file))
        except Exception as e:
            logger.error(f"خطأ أثناء إزالة ملف القفل القديم: {e}")

    def release(self):
        if not self._acquired:
            return
        try:
            if self._fd is not None:
                try:
                    os.close(self._fd)
                except Exception:
                    pass
                self._fd = None

            if self.lock_file.exists():
                try:
                    with open(self.lock_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    if data.get('token') == self.token or data.get('pid') == os.getpid():
                        os.unlink(str(self.lock_file))
                except Exception:
                    if self.lock_file.exists():
                        os.unlink(str(self.lock_file))
        finally:
            self._acquired = False

    def __enter__(self):
        if not self.acquire(blocking=False):
            raise RuntimeError("توجد عملية استعادة أخرى قيد التنفيذ حالياً على مستوى النظام (Cross-Process Lock). يرجى الانتظار.")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


class CrossProcessBackupLock(CrossProcessRestoreLock):
    """
    قفل نسخ احتياطي موثوق وحاكم عبر العمليات المتعددة (Cross-Process Authoritative Backup Lock):
    - يعتمد على ملف قفل ذري (.backup.lock) مدعوم برقم العملية (PID) وطابع زمني وهوية فريدة.
    - يمنع تماماً تنفيذ أكثر من عملية نسخ احتياطي واحدة في نفس اللحظة عبر كافة عمليات نظام التشغيل.
    """
    def __init__(self, owner: str = 'system', timeout_seconds: int = 300, lock_file_path: Optional[Path] = None):
        super().__init__(
            owner=owner,
            timeout_seconds=timeout_seconds,
            lock_file_path=lock_file_path or (get_backup_dir() / '.backup.lock')
        )


# ─── 1. النسخ المتسق لقاعدة بيانات SQLite ─────────────────────────────────────

def backup_sqlite_consistently(src_db_path: Path, dst_db_path: Path) -> None:
    """
    نسخ متسق وآمن لقاعدة بيانات SQLite متوافق مع نمط WAL والمعاملات النشطة.
    يستخدم SQLite Online Backup API الرسمي بدلاً من النسخ العشوائي للملفات.
    """
    if not src_db_path.exists():
        raise FileNotFoundError(f"قاعدة البيانات الأصلية غير موجودة: {src_db_path}")

    dst_db_path.parent.mkdir(parents=True, exist_ok=True)

    src_conn = sqlite3.connect(str(src_db_path), timeout=30.0)
    dst_conn = sqlite3.connect(str(dst_db_path), timeout=30.0)
    try:
        # تنفيذ النسخ عبر واجهة backup_api مع معالجة WAL frames
        src_conn.backup(dst_conn, pages=250, sleep=0.01)
        # The portable snapshot must be self-contained; do not archive unchecked
        # WAL frames that could change the database after integrity validation.
        dst_conn.execute('PRAGMA journal_mode=DELETE')
    finally:
        dst_conn.close()
        src_conn.close()


# ─── 2. إنشاء حزمة النسخ الاحتياطي ────────────────────────────────────────────

def create_institutional_backup(
    created_by: str = 'system',
    backup_type: str = 'full',
    label: str = ''
) -> Dict[str, Any]:
    """
    إنشاء حزمة نسخ احتياطي مؤسسية متكاملة ومتحقق من سلامتها.
    تشمل:
    - قاعدة بيانات SQLite المنسوخة بشكل متسق عبر backup API.
    - ملفات الأبحاث المرفوعة (Research Files).
    - وثائق المراجع (Reference Files).
    - إعدادات المنظومة (Configuration).
    - البيانات الوصفية والإصدارات (Metadata).
    - بيان الحزمة الرقمي (manifest.json) المتحقق من سلامته بتجزئة SHA-256.
    """
    global _BACKUP_IN_PROGRESS

    cross_lock = CrossProcessBackupLock(owner=created_by)
    if not cross_lock.acquire(blocking=False):
        raise RuntimeError("توجد عملية نسخ احتياطي أخرى قيد التنفيذ حالياً على مستوى النظام (Cross-Process Lock). يرجى الانتظار.")

    backup_id = None
    staging_dir = None
    staging_created = False
    partial_zip = None
    try:
        with _BACKUP_LOCK:
            _BACKUP_IN_PROGRESS = True
            start_time = datetime.utcnow()
            backup_dir = get_backup_dir()
            # Imported archives may not yet be in this database's sequence.
            # Never replace any existing backup while making a safety snapshot.
            while True:
                backup_id = reference_service.get_next_backup_reference(prefix='BKP')
                zip_filename = f"{backup_id}_{backup_type}.zip"
                zip_filepath = backup_dir / zip_filename
                if not list(backup_dir.glob(f'{backup_id}_*.zip')):
                    break
            staging_dir = backup_dir / f"_staging_{backup_id}_{uuid.uuid4().hex}"

            # تسجيل مبدئي في الفهرس
            backup_repo.create_backup_entry(
                backup_identifier=backup_id,
                file_name=zip_filename,
                file_path=str(zip_filepath),
                created_by=created_by,
                backup_type=backup_type,
                status='creating',
                application_version=getattr(versioning, 'APP_VERSION', '1.0.0'),
                engine_version=getattr(versioning, 'ENGINE_VERSION', '1.0.0'),
                manifest_version=MANIFEST_SCHEMA_VERSION
            )

            staging_dir.mkdir(parents=False, exist_ok=False)
            staging_created = True
            db_staging_dir = staging_dir / 'database'
            research_staging_dir = staging_dir / 'research_files'
            ref_staging_dir = staging_dir / 'reference_files'
            config_staging_dir = staging_dir / 'configuration'
            meta_staging_dir = staging_dir / 'metadata'

            for d in (db_staging_dir, research_staging_dir, ref_staging_dir, config_staging_dir, meta_staging_dir):
                d.mkdir(parents=True, exist_ok=True)

            included_components = []
            total_files_count = 0

            # 1. نسخ قاعدة البيانات
            live_db_path = config.DEFAULT_SQLITE_PATH
            staged_db_path = db_staging_dir / 'papers.db'
            if live_db_path.exists():
                backup_sqlite_consistently(live_db_path, staged_db_path)
                db_hash, db_size = integrity_service.compute_stream_sha256(staged_db_path)
                included_components.append({
                    'name': 'database',
                    'file_name': 'database/papers.db',
                    'file_count': 1,
                    'size_bytes': db_size,
                    'sha256': db_hash
                })
                total_files_count += 1
            else:
                db_hash, db_size = '', 0

            # 2. نسخ والتحقق من ملفات الأبحاث المعتمدة المرجعية (Database-Authoritative File Enumeration & Verification)
            research_files_manifest = []
            research_files_size = 0

            # قراءة سجلات الملفات من لقطة قاعدة البيانات المؤكدة حصراً
            snap_conn = sqlite3.connect(f"file:{staged_db_path.as_posix()}?mode=ro", uri=True)
            try:
                snap_cur = snap_conn.cursor()
                snap_cur.execute("PRAGMA table_info(research_files);")
                cols = [c[1] for c in snap_cur.fetchall()]
                has_storage_status = 'storage_status' in cols

                if has_storage_status:
                    snap_cur.execute("""
                        SELECT id, research_id, stored_filename, file_path, file_size_bytes, file_hash, storage_status
                        FROM research_files;
                    """)
                    db_research_files = snap_cur.fetchall()
                else:
                    snap_cur.execute("""
                        SELECT id, research_id, stored_filename, file_path, file_size_bytes, file_hash
                        FROM research_files;
                    """)
                    db_research_files = [(r[0], r[1], r[2], r[3], r[4], r[5], 'finalized') for r in snap_cur.fetchall()]
            finally:
                snap_conn.close()

            uploaded_dir = getattr(config, 'TEMP_UPLOAD_DIR', None)

            for item in db_research_files:
                rf_id, r_id, stored_name, f_path, expected_size, expected_hash = item[0], item[1], item[2], item[3], item[4], item[5]
                st_status = item[6] if len(item) > 6 else 'finalized'

                # 1. السجلات المخصصة صراحة للبصمة الرقمية فقط (Registry-Only) يتم استبعادها نظامياً
                if st_status == 'registry_only':
                    continue

                # 2. السجلات المعتمدة (Finalized Persistent Files) - التحقق الصارم من المسار والوجود
                if not f_path or not str(f_path).strip():
                    raise FileNotFoundError(
                        f"ملف البحث المعتمد «{stored_name or 'سجل ' + str(rf_id)}» (سجل رقم {rf_id}) مسار التخزين الخاص به فارغ في قاعدة البيانات."
                    )

                # تحديد موقع الملف على القرص
                candidate_path = None
                if Path(f_path).exists() and Path(f_path).is_file():
                    candidate_path = Path(f_path)
                elif uploaded_dir and stored_name and (uploaded_dir / stored_name).exists() and (uploaded_dir / stored_name).is_file():
                    candidate_path = uploaded_dir / stored_name

                if candidate_path is None or not candidate_path.exists():
                    raise FileNotFoundError(
                        f"ملف البحث المعتمد «{stored_name or f_path}» (سجل رقم {rf_id}) مفقود من وسيط التخزين أثناء النسخ الاحتياطي."
                    )

                actual_size = candidate_path.stat().st_size
                actual_hash, _ = integrity_service.compute_stream_sha256(candidate_path)

                # 3. التحقق الصارم من البصمة الرقمية
                if expected_hash and actual_hash.lower() != expected_hash.lower():
                    raise ValueError(
                        f"بصمة ملف البحث «{stored_name}» غير مطابقة لسجل قاعدة البيانات (محسوبة: {actual_hash[:12]}، متوقعة: {expected_hash[:12]})."
                    )

                # 4. التحقق الصارم من الحجم
                if expected_size and expected_size > 0 and actual_size != expected_size:
                    raise ValueError(
                        f"حجم ملف البحث «{stored_name}» غير مطابق لسجل قاعدة البيانات (فعلي: {actual_size}، متوقع: {expected_size})."
                    )

                dest = research_staging_dir / stored_name
                shutil.copy2(candidate_path, dest)
                research_files_size += actual_size
                research_files_manifest.append({
                    'logical_type': 'research_file',
                    'stored_filename': stored_name,
                    'file_name': f"research_files/{stored_name}",
                    'size_bytes': actual_size,
                    'sha256': actual_hash
                })

            included_components.append({
                'name': 'research_files',
                'file_count': len(research_files_manifest),
                'size_bytes': research_files_size,
                'files': research_files_manifest
            })
            total_files_count += len(research_files_manifest)

            # Preserve database-referenced originals, including report sources and
            # reference/thesis documents, independently of regenerable caches.
            persistent_component = backup_persistent_files.stage(staged_db_path, staging_dir / 'persistent_files')
            included_components.append(persistent_component)
            total_files_count += persistent_component['file_count']

            # 3. نسخ إعدادات المنظومة
            from app.services.settings_service import get_current_settings
            current_settings = get_current_settings()
            staged_settings_path = config_staging_dir / 'settings.json'
            with open(staged_settings_path, 'w', encoding='utf-8') as f:
                json.dump(current_settings, f, ensure_ascii=False, indent=2)
            cfg_size = staged_settings_path.stat().st_size
            cfg_hash, _ = integrity_service.compute_stream_sha256(staged_settings_path)
            included_components.append({
                'name': 'configuration',
                'file_name': 'configuration/settings.json',
                'file_count': 1,
                'size_bytes': cfg_size,
                'sha256': cfg_hash
            })
            total_files_count += 1

            # 4. نسخ البيانات الوصفية وإصدار الفهرس المرجعي
            corpus_version, corpus_fp = snapshot_service.get_current_reference_corpus_info()
            version_meta = {
                'application_version': getattr(versioning, 'APP_VERSION', '1.0.0'),
                'engine_version': getattr(versioning, 'ENGINE_VERSION', '1.0.0'),
                'normalization_version': getattr(versioning, 'NORMALIZATION_VERSION', '1.0.0'),
                'report_schema_version': getattr(versioning, 'REPORT_SCHEMA_VERSION', '1.0.0'),
                'reference_corpus_version': corpus_version,
                'reference_corpus_fingerprint': corpus_fp,
                'created_at': start_time.isoformat() + 'Z'
            }
            staged_meta_path = meta_staging_dir / 'version_info.json'
            with open(staged_meta_path, 'w', encoding='utf-8') as f:
                json.dump(version_meta, f, ensure_ascii=False, indent=2)
            meta_size = staged_meta_path.stat().st_size
            meta_hash, _ = integrity_service.compute_stream_sha256(staged_meta_path)
            included_components.append({
                'name': 'metadata',
                'file_name': 'metadata/version_info.json',
                'file_count': 1,
                'size_bytes': meta_size,
                'sha256': meta_hash
            })
            total_files_count += 1

            # 5. بناء وتضمين البيان التفصيلي (manifest.json)
            manifest_data = {
                'manifest_version': MANIFEST_SCHEMA_VERSION,
                'backup_id': backup_id,
                'created_at': start_time.isoformat() + 'Z',
                'created_by': created_by,
                'backup_type': backup_type,
                'label': label,
                'application_version': getattr(versioning, 'APP_VERSION', '1.0.0'),
                'engine_version': getattr(versioning, 'ENGINE_VERSION', '1.0.0'),
                'normalization_version': getattr(versioning, 'NORMALIZATION_VERSION', '1.0.0'),
                'report_schema_version': getattr(versioning, 'REPORT_SCHEMA_VERSION', '1.0.0'),
                'reference_corpus_version': corpus_version,
                'database': {
                    'file_name': 'database/papers.db',
                    'sha256': db_hash,
                    'size_bytes': db_size
                },
                'components': included_components,
                'total_files': total_files_count,
                'exclusions': [
                    'runtime_logs',
                    'temp_cache',
                    'python_virtualenv',
                    'auth_secrets'
                ]
            }

            staged_manifest_path = staging_dir / 'manifest.json'
            with open(staged_manifest_path, 'w', encoding='utf-8') as f:
                json.dump(manifest_data, f, ensure_ascii=False, indent=2)

            # 6. ضغط الحزمة إلى ملف ZIP
            partial_zip = backup_dir / f'.{backup_id}_{uuid.uuid4().hex}.partial'
            with zipfile.ZipFile(partial_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
                for root, _, files in os.walk(staging_dir):
                    for file in files:
                        full_p = Path(root) / file
                        rel_p = full_p.relative_to(staging_dir)
                        zf.write(full_p, arcname=rel_p.as_posix())

            # 7. حساب البصمة الرقمية للحزمة وفحص سلامتها
            package_checksum, package_size = integrity_service.compute_stream_sha256(partial_zip)

            # 8. التحقق التلقائي الصارم من سلامة الحزمة قبل اعتمادها
            val_result = validate_backup_package_file(partial_zip, expected_db_hash=db_hash, allow_partial=True)
            if not val_result['valid']:
                raise ValueError(f"فشل التحقق الذاتي من النسخة الاحتياطية: {val_result.get('error')}")
            # Publish without ever replacing an archive created by another actor.
            if os.name == 'nt':
                os.rename(partial_zip, zip_filepath)
            else:
                os.link(partial_zip, zip_filepath)
                partial_zip.unlink()

            # 9. تحديث السجل في الفهرس
            backup_repo.update_backup_status(
                backup_identifier=backup_id,
                status='completed',
                size_bytes=package_size,
                checksum=package_checksum
            )
            backup_repo.update_backup_validation(
                backup_identifier=backup_id,
                validation_status='valid',
                validation_details=val_result
            )

            # 10. توثيق الحدث في سجل التدقيق المؤسسي
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            audit_service.record_event(
                action="backup.created",
                category="backup",
                object_type="backup",
                object_id=backup_id,
                success=True,
                metadata={
                    "backup_id": backup_id,
                    "backup_type": backup_type,
                    "size_bytes": package_size,
                    "duration_ms": duration_ms,
                    "total_files": total_files_count,
                    "checksum_prefix": package_checksum[:16]
                }
            )

            # 11. تطبيق سياسة مدة الحفظ (Retention)
            enforce_backup_retention()

            return backup_repo.get_backup_entry(backup_id) or {
                'backup_identifier': backup_id,
                'status': 'completed',
                'size_bytes': package_size,
                'checksum': package_checksum
            }

    except Exception as e:
        logger.error(f"فشل إنشاء النسخة الاحتياطية {backup_id}: {e}", exc_info=True)
        if backup_id:
            backup_repo.update_backup_status(backup_id, status='failed')
        audit_service.record_event(
            action="backup.failed",
            category="backup",
            object_type="backup",
            object_id=backup_id,
            success=False,
            failure_reason_code="BACKUP_CREATION_FAILED",
            metadata={"backup_id": backup_id, "error": str(e)}
        )
        raise e

    finally:
        _BACKUP_IN_PROGRESS = False
        if staging_created and staging_dir is not None and staging_dir.exists():
            _remove_owned_directory(staging_dir,backup_dir)
        if partial_zip is not None:
            try:
                partial_zip.unlink(missing_ok=True)
            except OSError:
                logger.warning('Unable to remove incomplete backup %s', partial_zip, exc_info=True)
        cross_lock.release()


# ─── 3. التحقق من سلامة وصلاحية النسخة (Validation) ───────────────────────────

def validate_backup(backup_identifier: str) -> Dict[str, Any]:
    """
    التحقق من سلامة وصحة حزمة النسخة الاحتياطية المحددة:
    - التأكد من وجود ملف الحزمة والبيان manifest.json.
    - مطابقة بصمات SHA-256 للبيان وقاعدة البيانات.
    - فتح قاعدة البيانات كـ read-only وفحص الجداول الأساسية وسلامة SQLite.
    """
    entry = backup_repo.get_backup_entry(backup_identifier)
    backup_dir = get_backup_dir()
    if entry and entry.get('status') in ('creating','failed'):
        return {'backup_id':backup_identifier,'valid':False,'error':'Backup creation was not completed'}
    try:
        zip_path = _locate_backup_path(backup_identifier,entry)
    except ValueError as exc:
        return {'backup_id':backup_identifier,'valid':False,'error':str(exc)}
    if zip_path is None:
        return {'backup_id':backup_identifier,'valid':False,'validation_status':'invalid',
                'error':'ملف النسخة الاحتياطية غير موجود على القرص'}

    if entry and entry.get('checksum'):
        current_pkg_hash, _ = integrity_service.compute_stream_sha256(zip_path)
        if current_pkg_hash.lower() != entry['checksum'].lower():
            return {
                'valid': False,
                'backup_id': backup_identifier,
                'error': f"بصمة الحزمة غير متطابقة مع المسجل في الفهرس (محسوبة: {current_pkg_hash[:12]}، مسجلة: {entry['checksum'][:12]})"
            }

    result = validate_backup_package_file(zip_path)

    # تحديث الفهرس
    backup_repo.update_backup_validation(
        backup_identifier=backup_identifier,
        validation_status='valid' if result['valid'] else 'invalid',
        validation_details=result
    )

    if not result['valid']:
        audit_service.record_event(
            action="backup.validation_failed",
            category="backup",
            object_type="backup",
            object_id=backup_identifier,
            success=False,
            failure_reason_code="INTEGRITY_MISMATCH",
            metadata={"backup_id": backup_identifier, "error": result.get('error')}
        )

    return result


def validate_backup_package_file(zip_path: Path, expected_db_hash: Optional[str] = None, *, allow_partial: bool = False) -> Dict[str, Any]:
    """فحص داخلي متقدم لبنية محتويات ملف الـ ZIP."""
    if zip_path.suffix == '.partial' and not allow_partial:
        return {'valid': False, 'error': 'Incomplete backup archive'}
    if not zip_path.exists():
        return {'valid': False, 'error': 'ملف الحزمة غير موجود'}

    temp_inspect_dir = get_backup_dir() / f"_inspect_{uuid.uuid4().hex}"
    inspect_created = False
    try:
        if not zipfile.is_zipfile(zip_path):
            return {'valid': False, 'error': 'الملف ليس حزمة ZIP صالحة'}

        with zipfile.ZipFile(zip_path, 'r') as zf:
            backup_persistent_files.safe_members(zf)
            namelist = zf.namelist()
            if 'database/papers.db-wal' in namelist and zf.getinfo('database/papers.db-wal').file_size:
                return {'valid': False, 'error': 'Unverified database WAL is not permitted in a backup'}
            if 'manifest.json' not in namelist:
                return {'valid': False, 'error': 'البيان الوصفي manifest.json مفقود من الحزمة'}

            if 'database/papers.db' not in namelist:
                return {'valid': False, 'error': 'ملف قاعدة البيانات database/papers.db مفقود'}

            # قراءة البيان
            manifest_bytes = zf.read('manifest.json')
            try:
                manifest = json.loads(manifest_bytes.decode('utf-8'))
            except Exception as e:
                return {'valid': False, 'error': f"فشل قراءة وفك ترميز manifest.json: {e}"}
            allowed={'manifest.json','database/papers.db','database/papers.db-wal','database/papers.db-shm'}
            for component in manifest.get('components',[]):
                if component.get('file_name'):allowed.add(component['file_name'].replace('\\','/'))
                for item in component.get('files',[]):
                    if item.get('file_name'):allowed.add(item['file_name'].replace('\\','/'))
            for entry in zf.infolist():
                if not entry.is_dir() and entry.filename.replace('\\','/') not in allowed:
                    return {'valid':False,'error':'Backup contains an unlisted file'}

            # فحص قاعدة البيانات في مجلد مؤقت للقراءة فقط
            temp_inspect_dir.mkdir(parents=False, exist_ok=False)
            inspect_created = True
            extracted_db_path = temp_inspect_dir / 'papers.db'
            with zf.open('database/papers.db') as source, open(extracted_db_path, 'wb') as f:
                shutil.copyfileobj(source, f, length=1024*1024)

            # مطابقة الهاش
            computed_db_hash, db_size = integrity_service.compute_stream_sha256(extracted_db_path)
            manifest_db_hash = manifest.get('database', {}).get('sha256', '')
            if manifest_db_hash and computed_db_hash.lower() != manifest_db_hash.lower():
                return {
                    'valid': False,
                    'error': f"بصمة قاعدة البيانات غير متطابقة (محسوبة: {computed_db_hash[:12]}، مسجلة: {manifest_db_hash[:12]})"
                }

            if expected_db_hash and computed_db_hash.lower() != expected_db_hash.lower():
                return {
                    'valid': False,
                    'error': 'بصمة قاعدة البيانات لا تطابق الهاش المتوقع'
                }

            # فتح قاعدة البيانات وفحص الجداول وسلامة SQLite
            db_conn = sqlite3.connect(f"file:{extracted_db_path.as_posix()}?mode=ro", uri=True)
            try:
                cursor = db_conn.cursor()
                cursor.execute("PRAGMA integrity_check;")
                integrity_row = cursor.fetchone()
                if not integrity_row or integrity_row[0] != 'ok':
                    return {'valid': False, 'error': f"فشل فحص سلامة SQLite: {integrity_row}"}

                # التحقق من وجود الجداول الهيكلية الأساسية
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = {row[0] for row in cursor.fetchall()}
                required_tables = {'research', 'research_files', 'reports', 'audit_logs', 'users'}
                missing_tables = required_tables - tables
                if missing_tables:
                    return {'valid': False, 'error': f"جداول أساسية مفقودة من قاعدة البيانات: {missing_tables}"}
            finally:
                db_conn.close()
            backup_persistent_files.validate_references(extracted_db_path, manifest)

            # فحص ومطابقة سلامة ملفات الأبحاث والمراجع المرفقة داخل الحزمة مقابل البيان
            import hashlib
            norm_namelist = {n.replace('\\', '/'): n for n in namelist}
            for comp in manifest.get('components', []):
                component_name=comp.get('file_name','').replace('\\','/')
                if component_name and comp.get('sha256'):
                    if component_name not in norm_namelist:
                        return {'valid':False,'error':f'Missing component: {component_name}'}
                    component_hash=hashlib.sha256();component_size=0
                    with zf.open(norm_namelist[component_name]) as source:
                        for block in iter(lambda:source.read(1024*1024),b''):
                            component_hash.update(block);component_size+=len(block)
                    if component_hash.hexdigest().lower()!=comp['sha256'].lower() or component_size!=comp.get('size_bytes'):
                        return {'valid':False,'error':f'Component integrity mismatch: {component_name}'}
                for file_meta in comp.get('files', []):
                    f_name = file_meta.get('file_name', '')
                    f_name = f_name.replace('\\', '/') if f_name else ''
                    expected_hash = file_meta.get('sha256')
                    expected_size = file_meta.get('size_bytes')

                    if not f_name or f_name not in norm_namelist:
                        return {
                            'valid': False,
                            'error': f"الملف المرفق «{f_name}» مفقود من حزمة النسخة الاحتياطية"
                        }

                    actual_zip_entry = norm_namelist[f_name]
                    actual_hash_obj = hashlib.sha256()
                    actual_size = 0
                    with zf.open(actual_zip_entry) as source:
                        for block in iter(lambda: source.read(1024*1024), b''):
                            actual_hash_obj.update(block); actual_size += len(block)
                    if expected_size is not None and actual_size != expected_size:
                        return {
                            'valid': False,
                            'error': f"حجم الملف المرفق «{f_name}» غير مطابق للبيان (فعلي: {actual_size}، متوقع: {expected_size})"
                        }

                    if expected_hash:
                        actual_hash = actual_hash_obj.hexdigest()
                        if actual_hash.lower() != expected_hash.lower():
                            return {
                                'valid': False,
                                'error': f"بصمة الملف المرفق «{f_name}» غير مطابقة للبيان (محسوبة: {actual_hash[:12]}، مسجلة: {expected_hash[:12]})"
                            }

            return {
                'valid': True,
                'backup_id': manifest.get('backup_id'),
                'created_at': manifest.get('created_at'),
                'created_by': manifest.get('created_by'),
                'manifest_version': manifest.get('manifest_version'),
                'application_version': manifest.get('application_version'),
                'engine_version': manifest.get('engine_version'),
                'database_sha256': computed_db_hash,
                'total_files': manifest.get('total_files'),
                'error': None
            }

    except Exception as e:
        return {'valid': False, 'error': f"خطأ أثناء التحقق: {str(e)}"}
    finally:
        if inspect_created and temp_inspect_dir.exists():
            _remove_owned_directory(temp_inspect_dir,get_backup_dir())


# ─── 4. الاستعادة والتعافي الآمن (Safe Restore & Rollback) ─────────────────────

def restore_institutional_backup(
    backup_identifier: str,
    confirmation: str,
    current_user: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    استعادة نسخة احتياطية بشكل آمن ومحصن بالكامل:
    1. التحقق من التأكيد الصريح confirmation == backup_identifier.
    2. قفل المعالجة _RESTORE_MUTEX لمنع أي استعادة متزامنة.
    3. التحقق المسبق من سلامة النسخة وصحة قواعد بياناتها.
    4. إنشاء نسخة طوارئ مسبقة للوضع الحالي للنظام (Emergency Pre-Restore Snapshot).
    5. استخراج المحتويات إلى مجلد عزل مؤقت (Staging).
    6. التبديل الذري للملفات وقاعدة البيانات بعد إغلاق اتصالات المحرك.
    7. فحص ما بعد الاستعادة والتراجع التلقائي (Rollback) في حالة حدوث أي خطأ.
    8. مصالحة المهام المتوقفة وتوثيق أحداث التدقيق.
    """
    clean_id = (backup_identifier or '').strip()
    clean_conf = (confirmation or '').strip()

    if clean_id != clean_conf:
        raise ValueError(f"رمز التأكيد غير مطابق. المطلوب: «{clean_id}»، المدخل: «{clean_conf}»")

    username = current_user.get('username') if current_user else 'system_admin'
    cross_lock = CrossProcessRestoreLock(owner=username, timeout_seconds=300)

    if not _RESTORE_MUTEX.acquire(blocking=False):
        raise RuntimeError("توجد عملية استعادة أخرى قيد التنفيذ حالياً. يرجى الانتظار.")

    if not cross_lock.acquire(blocking=False):
        _RESTORE_MUTEX.release()
        raise RuntimeError("توجد عملية استعادة أخرى قيد التنفيذ حالياً على مستوى النظام (Cross-Process Lock). يرجى الانتظار.")

    safety_backup_id = None
    staging_restore_dir = get_backup_dir() / f"_staging_restore_{uuid.uuid4().hex}"
    restore_staging_created = False
    restored_sources_dir = None
    created_restore_paths = []
    database_touched = False

    try:
        # 1. التحقق المسبق من سلامة النسخة
        val_result = validate_backup(clean_id)
        if not val_result.get('valid'):
            raise ValueError(f"لا يمكن استعادة النسخة لأنها غير صالحة أو تالفة: {val_result.get('error')}")

        # 2. إنشاء نسخة طوارئ للوضع الحالي للنظام قبل البدء
        logger.info(f"بدء إنشاء نسخة الطوارئ المسبقة قبل استعادة {clean_id}...")
        safety_backup = create_institutional_backup(
            created_by=f"pre_restore_{username}",
            backup_type='pre_restore',
            label=f"نسخة أمان طارئة تلقائية قبل استعادة {clean_id}"
        )
        safety_backup_id = safety_backup.get('backup_identifier')
        logger.info(f"تم إنشاء نسخة الطوارئ بنجاح: {safety_backup_id}")

        # 3. توثيق بدء الاستعادة في سجل التدقيق
        audit_service.record_event(
            action="backup.restore_started",
            category="backup",
            object_type="backup",
            object_id=clean_id,
            user=current_user,
            success=True,
            metadata={
                "target_backup_id": clean_id,
                "safety_backup_id": safety_backup_id,
                "initiated_by": username
            }
        )

        # 4. فك الحزمة إلى مجلد عزل مؤقت
        entry = backup_repo.get_backup_entry(clean_id)
        zip_path = _locate_backup_path(clean_id,entry)
        if zip_path is None:raise FileNotFoundError('Backup archive is unavailable in the configured backup directory')

        staging_restore_dir.mkdir(parents=False, exist_ok=False)
        restore_staging_created = True
        with zipfile.ZipFile(zip_path, 'r') as zf:
            backup_persistent_files.safe_members(zf)
            zf.extractall(staging_restore_dir)
        # Empty legacy WAL/SHM files are not part of the verified DB snapshot.
        for suffix in ('-wal','-shm'):
            (staging_restore_dir/'database'/('papers.db'+suffix)).unlink(missing_ok=True)

        staged_db = staging_restore_dir / 'database' / 'papers.db'
        if not staged_db.exists():
            raise FileNotFoundError("ملف database/papers.db مفقود داخل حزمة الاستعادة")

        restored_sources_dir = Path(config.STORAGE_ROOT) / 'restored_backup_files' / uuid.uuid4().hex
        backup_persistent_files.rebase_staged_database(staged_db, staging_restore_dir, restored_sources_dir, created_restore_paths)

        # 5. إغلاق اتصالات SQLAlchemy المحرك الحالي
        base_repo.engine.dispose()

        # 6. استبدال محتويات قاعدة البيانات الحية عبر SQLite Backup API
        live_db = config.DEFAULT_SQLITE_PATH
        src_conn = sqlite3.connect(str(staged_db), timeout=30.0)
        dst_conn = sqlite3.connect(str(live_db), timeout=30.0)
        try:
            database_touched = True
            src_conn.backup(dst_conn)
        finally:
            src_conn.close()
            dst_conn.close()

        base_repo.engine.dispose()

        # 7. استبدال ملفات الأبحاث
        # All referenced originals were copied into a unique destination above;
        # never overwrite existing uploads while restoring.

        # 8. التحقق بعد الاستعادة
        post_conn = sqlite3.connect(str(live_db), timeout=10.0)
        try:
            cur = post_conn.cursor()
            cur.execute("PRAGMA integrity_check;")
            res = cur.fetchone()
            if not res or res[0] != 'ok':
                raise RuntimeError(f"فشل التحقق من سلامة قاعدة البيانات بعد الاستبدال: {res}")
            # مصالحة مهام الفحص التي كانت قيد التشغيل وقت النسخة وجعلها 'interrupted'
            cur.execute("UPDATE research SET scan_status = 'interrupted' WHERE scan_status IN ('running', 'queued', 'processing');")
            cur.execute("UPDATE scan_jobs SET status = 'interrupted' WHERE status IN ('running', 'queued', 'processing');")
            post_conn.commit()
        finally:
            post_conn.close()

        # إعادة تطبيق سمة الإخفاء في نظام ويندوز بعد الاستعادة
        if sys.platform == "win32":
            try:
                from app.utils.windows_security import apply_windows_hidden_attribute
                apply_windows_hidden_attribute(live_db)
                apply_windows_hidden_attribute(live_db.parent)
            except Exception:
                pass

        base_repo.engine.dispose()

        # 9. توثيق النجاح في سجل الفهرس والتدقيق
        if safety_backup and safety_backup_id:
            safety_entry = backup_repo.get_backup_entry(safety_backup_id)
            if not safety_entry:
                backup_repo.create_backup_entry(
                    backup_identifier=safety_backup_id,
                    file_name=safety_backup.get('file_name', f"{safety_backup_id}_pre_restore.zip"),
                    file_path=safety_backup.get('file_path', str(get_backup_dir() / f"{safety_backup_id}_pre_restore.zip")),
                    created_by=safety_backup.get('created_by', f"pre_restore_{username}"),
                    backup_type='pre_restore',
                    status='completed',
                    size_bytes=safety_backup.get('size_bytes', 0),
                    checksum=safety_backup.get('checksum', '')
                )

        # The restored snapshot may contain the old machine's catalog path and
        # a 'creating' record captured before publication; relocate this entry.
        from app.models.backup_schema import BackupCatalog
        with base_repo.get_session() as session:
            record=session.query(BackupCatalog).filter_by(backup_identifier=clean_id).first()
            if record:
                record.file_path=str(zip_path);record.file_name=zip_path.name
                record.checksum,record.size_bytes=integrity_service.compute_stream_sha256(zip_path)
        backup_repo.mark_backup_restored(clean_id)
        audit_service.record_event(
            action="backup.restore_completed",
            category="backup",
            object_type="backup",
            object_id=clean_id,
            user=current_user,
            success=True,
            metadata={
                "restored_backup_id": clean_id,
                "safety_backup_id": safety_backup_id
            }
        )

        base_repo.engine.dispose()

        return {
            'success': True,
            'message': f"تمت استعادة النسخة الاحتياطية «{clean_id}» بنجاح تام.",
            'restored_backup_id': clean_id,
            'safety_backup_id': safety_backup_id
        }

    except Exception as e:
        logger.error(f"خطأ حرج أثناء استعادة النسخة {clean_id}: {e}", exc_info=True)
        # تنفيذ التراجع التلقائي إلى نسخة الأمان (Rollback)
        rollback_success = not database_touched
        if safety_backup_id and database_touched:
            logger.warning(f"جاري التراجع التلقائي (Rollback) إلى نسخة الأمان: {safety_backup_id}...")
            try:
                _rollback_to_safety_backup(safety_backup_id)
                rollback_success = True
                logger.info(f"اكتمل التراجع التلقائي إلى {safety_backup_id} بنجاح.")
            except Exception as rb_err:
                logger.critical(f"فشل التراجع التلقائي: {rb_err}", exc_info=True)
        if restored_sources_dir in created_restore_paths and restored_sources_dir.exists() and (not database_touched or rollback_success):
            safe_root = (Path(config.STORAGE_ROOT) / 'restored_backup_files').resolve()
            target = restored_sources_dir.resolve()
            if target.parent == safe_root:
                _remove_owned_directory(restored_sources_dir,safe_root)

        audit_service.record_event(
            action="backup.restore_failed",
            category="backup",
            object_type="backup",
            object_id=clean_id,
            user=current_user,
            success=False,
            failure_reason_code="RESTORE_EXECUTION_FAILED",
            metadata={
                "target_backup_id": clean_id,
                "safety_backup_id": safety_backup_id,
                "rollback_performed": rollback_success,
                "error": str(e)
            }
        )
        raise RuntimeError(f"فشلت الاستعادة: {str(e)} (حالة التراجع التلقائي: {'تم بنجاح' if rollback_success else 'فشل'})")

    finally:
        if restore_staging_created and staging_restore_dir.exists():
            _remove_owned_directory(staging_restore_dir,get_backup_dir())
        cross_lock.release()
        _RESTORE_MUTEX.release()


def _rollback_to_safety_backup(safety_backup_id: str) -> None:
    """استرجاع اضطراري فوري لنسخة الأمان عند تعثر الاستعادة."""
    entry = backup_repo.get_backup_entry(safety_backup_id)
    zip_path = Path(entry['file_path']) if entry and entry.get('file_path') else get_backup_dir() / f"{safety_backup_id}_pre_restore.zip"
    if not zip_path.exists():
        candidates = list(get_backup_dir().glob(f"{safety_backup_id}*.zip"))
        if candidates:
            zip_path = candidates[0]
        else:
            raise FileNotFoundError(f"ملف نسخة الأمان مفقود: {zip_path}")

    temp_rb = get_backup_dir() / f"_rb_{uuid.uuid4().hex}"
    temp_rb.mkdir(parents=False, exist_ok=False)
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            backup_persistent_files.safe_members(zf)
            zf.extractall(temp_rb)

        staged_db = temp_rb / 'database' / 'papers.db'
        if staged_db.exists():
            base_repo.engine.dispose()
            live_db = config.DEFAULT_SQLITE_PATH
            src_conn = sqlite3.connect(str(staged_db), timeout=30.0)
            dst_conn = sqlite3.connect(str(live_db), timeout=30.0)
            try:
                src_conn.backup(dst_conn)
            finally:
                src_conn.close()
                dst_conn.close()
            if sys.platform == "win32":
                try:
                    from app.utils.windows_security import apply_windows_hidden_attribute
                    apply_windows_hidden_attribute(live_db)
                    apply_windows_hidden_attribute(live_db.parent)
                except Exception:
                    pass
            base_repo.engine.dispose()
    finally:
        if temp_rb.exists():
            _remove_owned_directory(temp_rb,get_backup_dir())


# ─── 5. سياسة مدة الحفظ (Retention Management) ───────────────────────────────

def enforce_backup_retention(max_count: Optional[int] = None) -> int:
    """
    تطبيق سياسة الحفظ المحلية:
    - الإبقاء على أحدث max_count نسخة صالحة.
    - عدم حذف أحدث نسخة صالحة إطلاقاً تحت أي ظرف.
    - توثيق حذف النسخ القديمة في سجل التدقيق المؤسسي.
    """
    if max_count is None:
        max_count = getattr(config, 'BACKUP_RETENTION_COUNT', 30)

    all_backups = backup_repo.list_backups()
    if len(all_backups) <= max_count:
        return 0

    # الحفاظ على أحدث نسخة صالحة
    newest_valid_id = None
    for b in all_backups:
        if b.get('status') == 'completed' and b.get('validation_status') == 'valid':
            newest_valid_id = b['backup_identifier']
            break

    candidates_to_delete = all_backups[max_count:]
    deleted_count = 0

    for b in candidates_to_delete:
        b_id = b['backup_identifier']
        # حظر حذف أحدث نسخة صالحة
        if b_id == newest_valid_id:
            continue

        file_p = Path(b.get('file_path', ''))
        size = b.get('size_bytes', 0)

        # حذف الملف الفعلي من القرص
        if file_p.exists():
            try:
                file_p.unlink()
            except Exception as e:
                logger.warning(f"تعذر حذف ملف النسخة القديمة {file_p}: {e}")

        # حذف السجل من الفهرس
        backup_repo.delete_backup_entry(b_id)
        deleted_count += 1

        # توثيق حدث التدقيق
        audit_service.record_event(
            action="backup.retention_deleted",
            category="backup",
            object_type="backup",
            object_id=b_id,
            success=True,
            metadata={"backup_id": b_id, "size_bytes": size, "reason": "retention_policy"}
        )

    return deleted_count
