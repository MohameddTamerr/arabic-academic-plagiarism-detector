# -*- coding: utf-8 -*-
"""
خدمة مراقبة وصحة قاعدة البيانات (Database Health & SQLite Hardening Service):
- توفير فحص تشخيصي خفيف ومستمر لحالة قاعدة البيانات ونمط WAL وحجم الملفات.
- توفير أدوات الصيانة المؤسسية: PRAGMA quick_check و PRAGMA integrity_check مع توثيق أحداث التدقيق.
- إدارة نقاط تفتيش WAL (Passive / Truncate Checkpoints) لضبط نمو سجل المعاملات.
- استعراض مقاييس الأداء والإصدارات بدون تسريب بيانات حساسة.
"""

import os
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy import text

import config
from app import versioning
from app.repositories import base_repo, backup_repo
from app.services import audit_service
from app.models.schema import ScanJob

logger = logging.getLogger(__name__)


def get_database_health() -> Dict[str, Any]:
    """
    استرجاع الفحص التشخيصي الخفيف لصحة قاعدة البيانات وبيئة SQLite:
    - فحص الاتصال وقراءة إعدادات الـ PRAGMA الحالية.
    - قياس حجم ملف قاعدة البيانات وملف الـ WAL بالبايت والميجابايت.
    - استرجاع إصدار مخطط قاعدة البيانات وعدد المهام الجارية وآخر نسخة احتياطية.
    """
    db_path = config.DEFAULT_SQLITE_PATH
    wal_path = Path(str(db_path) + '-wal')
    shm_path = Path(str(db_path) + '-shm')

    db_size = db_path.stat().st_size if db_path.exists() else 0
    wal_size = wal_path.stat().st_size if wal_path.exists() else 0
    shm_size = shm_path.stat().st_size if shm_path.exists() else 0

    pragmas = {}
    is_reachable = False

    try:
        with base_repo.engine.connect() as conn:
            is_reachable = True
            # استعلام الـ PRAGMAs
            res_fk = conn.execute(text("PRAGMA foreign_keys;")).scalar()
            res_jm = conn.execute(text("PRAGMA journal_mode;")).scalar()
            res_sync = conn.execute(text("PRAGMA synchronous;")).scalar()
            res_bt = conn.execute(text("PRAGMA busy_timeout;")).scalar()
            res_ts = conn.execute(text("PRAGMA temp_store;")).scalar()
            res_acp = conn.execute(text("PRAGMA wal_autocheckpoint;")).scalar()

            pragmas = {
                'foreign_keys': bool(res_fk),
                'journal_mode': str(res_jm).upper() if res_jm else 'UNKNOWN',
                'synchronous': _format_sync_mode(res_sync),
                'busy_timeout_ms': int(res_bt or 0),
                'temp_store': str(res_ts),
                'wal_autocheckpoint': int(res_acp or 0)
            }
    except Exception as e:
        logger.error(f"فشل الاتصال بقاعدة البيانات أثناء الفحص الصحي: {e}")
        pragmas = {'error': str(e)}

    # عدد مهام الفحص النشطة
    active_jobs = 0
    try:
        with base_repo.get_session() as session:
            active_jobs = session.query(ScanJob).filter(ScanJob.status.in_(['running', 'queued', 'processing'])).count()
    except Exception:
        pass

    # معلومات أحدث نسخة احتياطية
    latest_backup = None
    try:
        backups = backup_repo.list_backups()
        if backups:
            latest_backup = {
                'backup_id': backups[0]['backup_identifier'],
                'created_at': backups[0]['created_at'],
                'status': backups[0]['status'],
                'validation_status': backups[0]['validation_status']
            }
    except Exception:
        pass

    return {
        'status': 'healthy' if is_reachable and pragmas.get('journal_mode') == 'WAL' else 'degraded',
        'database_reachable': is_reachable,
        'database_type': 'SQLite (Offline WAL Mode)',
        'schema_version': getattr(versioning, 'DATABASE_SCHEMA_VERSION', '1.0.0'),
        'database_file_size_bytes': db_size,
        'database_file_size_mb': round(db_size / (1024 * 1024), 2),
        'wal_file_size_bytes': wal_size,
        'wal_file_size_mb': round(wal_size / (1024 * 1024), 2),
        'shm_file_size_bytes': shm_size,
        'pragmas': pragmas,
        'active_scan_jobs_count': active_jobs,
        'latest_backup': latest_backup,
        'checked_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
    }


def run_quick_check() -> Dict[str, Any]:
    """
    تشغيل فحص سريع لسلامة فهرس وهيكل SQLite (PRAGMA quick_check).
    أخف وزناً وأسرع من الفحص الشامل ولا يستهلك موارد الخادم.
    """
    start_t = datetime.utcnow()
    try:
        with base_repo.engine.connect() as conn:
            res = conn.execute(text("PRAGMA quick_check;")).fetchall()
            output = [r[0] for r in res]
            is_ok = len(output) == 1 and output[0] == 'ok'

            audit_service.record_event(
                action="database.quick_check_completed",
                category="database",
                object_type="database",
                object_id="papers.db",
                success=is_ok,
                metadata={"status": "ok" if is_ok else "errors_found", "details": output[:5]}
            )

            return {
                'success': is_ok,
                'result': 'ok' if is_ok else output,
                'is_clean': is_ok,
                'duration_ms': int((datetime.utcnow() - start_t).total_seconds() * 1000)
            }
    except Exception as e:
        logger.error(f"خطأ أثناء PRAGMA quick_check: {e}")
        return {'success': False, 'error': str(e), 'is_clean': False}


def run_deep_integrity_check() -> Dict[str, Any]:
    """
    تشغيل فحص شامل وعميق لسلامة قاعدة البيانات (PRAGMA integrity_check).
    إجراء صيانة إداري حصري يتطلب صلاحية system.maintenance.
    """
    start_t = datetime.utcnow()
    try:
        with base_repo.engine.connect() as conn:
            res = conn.execute(text("PRAGMA integrity_check;")).fetchall()
            output = [r[0] for r in res]
            is_ok = len(output) == 1 and output[0] == 'ok'

            action_name = "database.integrity_check_completed" if is_ok else "database.integrity_check_failed"
            audit_service.record_event(
                action=action_name,
                category="database",
                object_type="database",
                object_id="papers.db",
                success=is_ok,
                failure_reason_code=None if is_ok else "INTEGRITY_CHECK_ERRORS",
                metadata={"status": "ok" if is_ok else "corrupted", "errors": output if not is_ok else []}
            )

            return {
                'success': is_ok,
                'result': 'ok' if is_ok else output,
                'is_clean': is_ok,
                'duration_ms': int((datetime.utcnow() - start_t).total_seconds() * 1000)
            }
    except Exception as e:
        logger.error(f"خطأ أثناء PRAGMA integrity_check: {e}")
        audit_service.record_event(
            action="database.integrity_check_failed",
            category="database",
            object_type="database",
            object_id="papers.db",
            success=False,
            failure_reason_code="EXECUTION_ERROR",
            metadata={"error": str(e)}
        )
        return {'success': False, 'error': str(e), 'is_clean': False}


def run_wal_checkpoint(mode: str = 'PASSIVE') -> Dict[str, Any]:
    """
    تنفيذ نقطة تفتيش WAL (PRAGMA wal_checkpoint).
    الأنماط المدعومة:
    - PASSIVE: دمج الصفحات المتاحة دون حظر القراء أو الكتاب.
    - TRUNCATE: دمج كامل الصفحات وإعادة ضبط حجم ملف الـ WAL إلى الصفر بعد تحرير القراء.
    """
    clean_mode = mode.upper().strip()
    if clean_mode not in ('PASSIVE', 'FULL', 'RESTART', 'TRUNCATE'):
        clean_mode = 'PASSIVE'

    start_t = datetime.utcnow()
    try:
        with base_repo.engine.connect() as conn:
            # PRAGMA wal_checkpoint(MODE) returns (busy, log, checkpointed)
            res = conn.execute(text(f"PRAGMA wal_checkpoint({clean_mode});")).fetchone()
            busy, log_frames, checkpointed = (res[0], res[1], res[2]) if res else (0, 0, 0)
            is_success = (busy == 0)

            audit_service.record_event(
                action="database.checkpoint_completed",
                category="database",
                object_type="database",
                object_id="papers.db",
                success=is_success,
                metadata={
                    "mode": clean_mode,
                    "busy": busy,
                    "log_frames": log_frames,
                    "checkpointed_frames": checkpointed
                }
            )

            return {
                'success': is_success,
                'mode': clean_mode,
                'busy': bool(busy),
                'log_frames': log_frames,
                'checkpointed_frames': checkpointed,
                'duration_ms': int((datetime.utcnow() - start_t).total_seconds() * 1000)
            }
    except Exception as e:
        logger.error(f"خطأ أثناء PRAGMA wal_checkpoint: {e}")
        return {'success': False, 'error': str(e)}


def _format_sync_mode(code: Any) -> str:
    modes = {0: 'OFF', 1: 'NORMAL', 2: 'FULL', 3: 'EXTRA'}
    return modes.get(code, str(code))
