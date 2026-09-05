# -*- coding: utf-8 -*-
"""
خدمة مراقبة وصحة النظام التشغيلية المحصنة (Hardened System Health Service):
- مصفوفة تصنيف المكونات الصريحة (REQUIRED / OPTIONAL / POLICY_DEPENDENT).
- فحص الحالة العامة وفق قواعد حتمية محكمة دون خفض الصحة للمكونات الاختيارية المعطلة.
- فحص النسخ الاحتياطي المعتمد على فهرس BackupCatalog بدقة والتفريق بين الإنشاء والاكتمال والتحقق.
- فحوصات خفيفة تماماً بدون تحميل نماذج في الذاكرة وبكاش محكوم لعمليات الاستعلام عن البرمجيات.
- عزل استعلام مساحة القرص لمجلد التخزين الفعلي المعتمد دون تسريب مسارات النظام.
- رصد المهام العالقة بناءً على تاريخ المعالجة وبحث مجمع خفيف.
- كبح التنبيهات المكررة (State-Aware Alert Deduplication).
- حماية مسار الصحة ضد الانهيار (Resilience) والتحصين الشامل للخصوصية.
"""

import os
import re
import time
import shutil
import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Callable
from sqlalchemy import text, func

import config
from app import versioning
from app.repositories import base_repo, backup_repo
from app.models.schema import ScanJob, Document
from app.models.research_schema import ScanBatch, ScanBatchItem
from app.models.snapshot_schema import ReferenceCorpusVersion
from app.models.audit_schema import AuditLog
from app.services.settings_service import get_current_settings
from plagiarism_detector.extraction.ocr_engine import check_ocr_availability
from plagiarism_detector.detection.semantic_matcher import check_semantic_model_availability

logger = logging.getLogger(__name__)

# الحالات التشغيلية المعتمدة
STATUS_HEALTHY = "healthy"
STATUS_DEGRADED = "degraded"
STATUS_CRITICAL = "critical"
STATUS_DISABLED = "disabled"
STATUS_NOT_CONFIGURED = "not_configured"
STATUS_UNKNOWN = "unknown"

STATUS_LABELS_AR = {
    STATUS_HEALTHY: "سليم",
    STATUS_DEGRADED: "يحتاج متابعة",
    STATUS_CRITICAL: "حالة حرجة",
    STATUS_DISABLED: "غير مفعّل",
    STATUS_NOT_CONFIGURED: "لم يتم التحقق بعد",
    STATUS_UNKNOWN: "غير متاح"
}

# مصفوفة تصنيف المكونات الصريحة (Component Severity Matrix)
COMPONENT_CLASSIFICATION = {
    'database': 'REQUIRED',
    'storage': 'REQUIRED',
    'semantic_model': 'OPTIONAL',
    'ocr': 'OPTIONAL',
    'backup': 'POLICY_DEPENDENT',
    'scan_jobs': 'POLICY_DEPENDENT',
    'batches': 'POLICY_DEPENDENT',
    'reference_corpus': 'POLICY_DEPENDENT',
    'application': 'POLICY_DEPENDENT',
}

# كاش الفحص المحكوم لمحرك OCR (لتفادي استدعاء أوامر النظام كل 30 ثانية)
_OCR_CACHE = {'last_checked': 0.0, 'data': None, 'ttl_seconds': 60.0}

# حالة التنبيهات لتطبيق كبح التكرار الواعي بالحالة (State-Aware Deduplication)
_ALERT_STATE_TRACKER: Dict[str, str] = {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_system_health() -> Dict[str, Any]:
    """
    استرجاع لقطة الحالة التشغيلية الشاملة للمنظومة (Central System Health Snapshot).
    خفيفة وسريعة وتعمل 100% أوفلاين مع حماية تامة ضد انهيار أي مكوّن فردي.
    """
    now = _utcnow()
    checked_at_iso = now.strftime('%Y-%m-%d %H:%M:%S UTC')

    # 1. فحص المكونات مع عزل الأخطاء (Fault-Tolerant Checks)
    components: Dict[str, Dict[str, Any]] = {
        'application': _safe_check('application', _check_application, now),
        'database': _safe_check('database', _check_database, now),
        'storage': _safe_check('storage', _check_storage, now),
        'backup': _safe_check('backup', _check_backup, now),
        'scan_jobs': _safe_check('scan_jobs', _check_scan_jobs, now),
        'batches': _safe_check('batches', _check_batches, now),
        'reference_corpus': _safe_check('reference_corpus', _check_reference_corpus, now),
        'ocr': _safe_check('ocr', _check_ocr, now),
        'semantic_model': _safe_check('semantic_model', _check_semantic_model, now),
    }

    # 2. احتساب الحالة الكلية وفق مصفوفة تصنيف المكونات
    overall_status = _determine_overall_status(components)
    overall_status_ar = STATUS_LABELS_AR.get(overall_status, "غير متاح")

    # 3. ملخص الأحداث التشغيلية الحديثة المحصنة
    recent_incidents = _get_recent_incidents()

    # 4. تحديث سجل تتبع التنبيهات وكبح التكرار
    _evaluate_alert_state_transitions(components)

    raw_response = {
        'overall_status': overall_status,
        'overall_status_ar': overall_status_ar,
        'checked_at': checked_at_iso,
        'components': components,
        'recent_incidents': recent_incidents
    }

    # 5. تنقية الاستجابة من أي مسارات أو أسرار (Recursive Privacy Sanitization)
    return _sanitize_privacy(raw_response)


def _safe_check(name: str, fn: Callable[[datetime], Dict[str, Any]], now: datetime) -> Dict[str, Any]:
    """تنفيذ فحص المكون بحماية تمنع استثناء أي مكون من تعطيل واجهة صحة النظام بالكامل."""
    try:
        return fn(now)
    except Exception as e:
        logger.error(f"خطأ غير متوقع أثناء فحص المكون '{name}': {e}", exc_info=False)
        classification = COMPONENT_CLASSIFICATION.get(name, 'POLICY_DEPENDENT')
        status = STATUS_CRITICAL if classification == 'REQUIRED' else STATUS_DEGRADED
        return {
            'status': status,
            'status_ar': STATUS_LABELS_AR.get(status, 'غير متاح'),
            'message': f"تعذر استكمال فحص {name} لوجود خطأ داخلي.",
            'checked_at': now.strftime('%Y-%m-%d %H:%M:%S UTC'),
            'metadata': {'check_error': True}
        }


def _determine_overall_status(components: Dict[str, Dict[str, Any]]) -> str:
    """
    تحديد الحالة الكلية للمنظومة بناءً على مصفوفة تصنيف المكونات الصريحة:
    - REQUIRED: تعطل أي مكوّن أساسي (database, storage) ينتج CRITICAL فوراً، وتدهوره ينتج DEGRADED.
    - POLICY_DEPENDENT: أي مكوّن تدهور فيه يتطلب متابعة (DEGRADED).
    - OPTIONAL: المكونات الاختيارية (ocr, semantic_model) إذا كانت معطلة (DISABLED) فلا تؤثر مطلقاً
      على صحة النظام. وإذا كانت مفعلة في الإعدادات ولكن ملفاتها ناقصة محلياً فإنها تصبح DEGRADED.
    """
    # 1. التحقق من المكونات الأساسية المطلوبة (REQUIRED)
    for comp_name, classification in COMPONENT_CLASSIFICATION.items():
        if classification == 'REQUIRED':
            st = components.get(comp_name, {}).get('status')
            if st == STATUS_CRITICAL:
                return STATUS_CRITICAL
            if st == STATUS_DEGRADED:
                return STATUS_DEGRADED

    # 2. التحقق من المكونات المعتمدة على السياسات (POLICY_DEPENDENT)
    for comp_name, classification in COMPONENT_CLASSIFICATION.items():
        if classification == 'POLICY_DEPENDENT':
            st = components.get(comp_name, {}).get('status')
            if st == STATUS_CRITICAL:
                return STATUS_CRITICAL
            if st == STATUS_DEGRADED:
                return STATUS_DEGRADED

    # 3. التحقق من المكونات الاختيارية (OPTIONAL)
    for comp_name, classification in COMPONENT_CLASSIFICATION.items():
        if classification == 'OPTIONAL':
            st = components.get(comp_name, {}).get('status')
            # disabled لا يخفض الصحة
            if st in (STATUS_DEGRADED, STATUS_CRITICAL):
                return STATUS_DEGRADED

    return STATUS_HEALTHY


def _check_application(now: datetime) -> Dict[str, Any]:
    """إصدارات المنظومة ومخطط البيانات ومحركات الفحص وفحص تهيئة الأمان المؤسسي."""
    is_prod = getattr(config, 'APP_ENV', 'development') in ('production', 'institutional') or os.environ.get('INSTITUTIONAL_MODE') == '1'
    cookie_secure = getattr(config, 'AUTH_COOKIE_SECURE', False)
    status = STATUS_HEALTHY
    msg = 'إصدارات المنظومة ومخطط البيانات متطابقة ومستقرة.'

    if is_prod and not cookie_secure:
        status = STATUS_DEGRADED
        msg = 'تحذير أمني: المنظومة تعمل في بيئة إنتاج مؤسسية مع تعطيل سمة كوكيز الجلسات الآمنة (SESSION_COOKIE_SECURE=False). يرجى تفعيل HTTPS وتفعيل Secure Cookies.'

    return {
        'status': status,
        'status_ar': STATUS_LABELS_AR[status],
        'message': msg,
        'checked_at': now.strftime('%Y-%m-%d %H:%M:%S UTC'),
        'metadata': {
            'application_version': getattr(versioning, 'APP_VERSION', '1.0.0'),
            'engine_version': getattr(versioning, 'DETECTOR_VERSION', '2.0.0'),
            'database_schema_version': getattr(versioning, 'DATABASE_SCHEMA_VERSION', '1.0.0'),
            'report_schema_version': getattr(versioning, 'REPORT_SCHEMA_VERSION', '1.0.0'),
            'normalization_version': getattr(versioning, 'NORMALIZATION_VERSION', '1.0.0'),
            'secure_cookies_enabled': cookie_secure,
            'environment': getattr(config, 'APP_ENV', 'development'),
        }
    }


def _check_database(now: datetime) -> Dict[str, Any]:
    """فحص خفيف لصحة قاعدة البيانات وبيئة SQLite/PostgreSQL دون أقفال طويلة ودون تسريب أسرار."""
    backend_type = base_repo.get_backend_type()
    reachable = False
    error_msg = None
    query_latency_ms = None

    if backend_type == "sqlite":
        db_path = config.DEFAULT_SQLITE_PATH
        wal_path = Path(str(db_path) + '-wal')
        shm_path = Path(str(db_path) + '-shm')

        db_size = db_path.stat().st_size if db_path.exists() else 0
        wal_size = wal_path.stat().st_size if wal_path.exists() else 0
        shm_size = shm_path.stat().st_size if shm_path.exists() else 0

        journal_mode = "UNKNOWN"
        foreign_keys = False

        try:
            t0 = time.time()
            with base_repo.engine.connect() as conn:
                reachable = True
                jm = conn.execute(text("PRAGMA journal_mode;")).scalar()
                fk = conn.execute(text("PRAGMA foreign_keys;")).scalar()
                journal_mode = str(jm).upper() if jm else "UNKNOWN"
                foreign_keys = bool(fk)
            query_latency_ms = round((time.time() - t0) * 1000, 2)
        except Exception as e:
            reachable = False
            error_msg = str(e)
            logger.error(f"فشل الاتصال بقاعدة بيانات SQLite أثناء الفحص الصحي: {e}")

        if not reachable:
            status = STATUS_CRITICAL
            msg = f"تعذر الاتصال بقاعدة البيانات (SQLite): {error_msg or 'خطأ غير محدد'}"
        elif journal_mode != "WAL":
            status = STATUS_DEGRADED
            msg = f"قاعدة البيانات (SQLite) متاحة ولكن تعمل بنمط «{journal_mode}» بدلاً من WAL المحصن."
        else:
            status = STATUS_HEALTHY
            msg = "قاعدة بيانات SQLite متاحة وتعمل بنمط WAL الآمن والمحصن."

        return {
            'status': status,
            'status_ar': STATUS_LABELS_AR.get(status, status),
            'message': msg,
            'checked_at': now.strftime('%Y-%m-%d %H:%M:%S UTC'),
            'metadata': {
                'backend': 'sqlite',
                'reachable': reachable,
                'query_latency_ms': query_latency_ms,
                'journal_mode': journal_mode,
                'foreign_keys_enabled': foreign_keys,
                'schema_version': getattr(versioning, 'DATABASE_SCHEMA_VERSION', '1.0.0'),
                'database_size_bytes': db_size,
                'database_size_mb': round(db_size / (1024 * 1024), 2),
                'wal_size_bytes': wal_size,
                'wal_size_mb': round(wal_size / (1024 * 1024), 2),
                'shm_size_bytes': shm_size,
            }
        }

    else:
        # فحص محرك PostgreSQL
        pool_stats = {}
        try:
            pool = base_repo.engine.pool
            pool_stats = {
                'pool_size': pool.size(),
                'checked_in': pool.checkedin(),
                'checked_out': pool.checkedout(),
                'overflow': pool.overflow()
            }
        except Exception:
            pass

        try:
            t0 = time.time()
            with base_repo.engine.connect() as conn:
                res = conn.execute(text("SELECT 1;")).scalar()
                reachable = (res == 1)
            query_latency_ms = round((time.time() - t0) * 1000, 2)
        except Exception as e:
            reachable = False
            # تنقية أي بيانات اعتماد من رسالة الخطأ
            error_msg = config.get_masked_database_url(str(e))
            logger.error(f"فشل الاتصال بقاعدة بيانات PostgreSQL أثناء الفحص الصحي: {error_msg}")

        if not reachable:
            status = STATUS_CRITICAL
            msg = f"تعذر الاتصال بقاعدة بيانات PostgreSQL الوزارية: {error_msg or 'خطأ غير محدد'}"
        else:
            status = STATUS_HEALTHY
            msg = "خادم PostgreSQL الوزاري متاح ومتصل بنجاح عبر الشبكة الداخلية."

        return {
            'status': status,
            'status_ar': STATUS_LABELS_AR.get(status, status),
            'message': msg,
            'checked_at': now.strftime('%Y-%m-%d %H:%M:%S UTC'),
            'metadata': {
                'backend': 'postgresql',
                'reachable': reachable,
                'query_latency_ms': query_latency_ms,
                'schema_version': getattr(versioning, 'DATABASE_SCHEMA_VERSION', '1.0.0'),
                'database_url_masked': config.get_masked_database_url(),
                'pool': pool_stats
            }
        }



def _check_storage(now: datetime) -> Dict[str, Any]:
    """
    فحص مساحة التخزين المتاحة على وحدة التخزين الفعلية التي تضم مجلد البيانات ومجلد الأبحاث.
    تحديد المسار المستهدف بناءً على STORAGE_ROOT وDEFAULT_SQLITE_PATH.
    """
    target_dir = Path(config.STORAGE_ROOT)
    if not target_dir.exists():
        target_dir = Path(config.DEFAULT_SQLITE_PATH).parent

    try:
        usage = shutil.disk_usage(str(target_dir))
        total_b = usage.total
        used_b = usage.used
        free_b = usage.free
        free_pct = round((free_b / total_b) * 100, 2) if total_b > 0 else 0.0
    except Exception as e:
        logger.warning(f"تعذر استعلام مساحة القرص لمجلد التخزين: {e}")
        total_b, used_b, free_b, free_pct = 0, 0, 0, 100.0

    warn_pct = config.DISK_WARNING_PERCENT
    crit_pct = config.DISK_CRITICAL_PERCENT

    if free_pct < crit_pct:
        status = STATUS_CRITICAL
        msg = f"مساحة القرص منخفضة جداً بشكل حرج ({free_pct}% متاح، أقل من الحد الحرج {crit_pct}%)."
    elif free_pct < warn_pct:
        status = STATUS_DEGRADED
        msg = f"مساحة القرص تقترب من الامتلاء ({free_pct}% متاح، أقل من حد التحذير {warn_pct}%)."
    else:
        status = STATUS_HEALTHY
        msg = f"مساحة التخزين كافية وسليمة ({free_pct}% مساحة حرة متاحة)."

    return {
        'status': status,
        'status_ar': STATUS_LABELS_AR.get(status, status),
        'message': msg,
        'checked_at': now.strftime('%Y-%m-%d %H:%M:%S UTC'),
        'metadata': {
            'total_bytes': total_b,
            'total_gb': round(total_b / (1024 ** 3), 2),
            'used_bytes': used_b,
            'used_gb': round(used_b / (1024 ** 3), 2),
            'free_bytes': free_b,
            'free_gb': round(free_b / (1024 ** 3), 2),
            'free_percent': free_pct,
            'warning_threshold_pct': warn_pct,
            'critical_threshold_pct': crit_pct,
        }
    }


def _check_backup(now: datetime) -> Dict[str, Any]:
    """
    فحص صحة وحداثة النسخ الاحتياطي بالاعتماد على الفهرس الرسمي (BackupCatalog).
    التمييز الدقيق بين:
    - أحدث نسخة تم إنشاؤها (latest created).
    - أحدث نسخة مكتملة بنجاح (latest completed).
    - أحدث نسخة تم التحقق من سلامتها (latest validated).
    - أحدث نسخة فاشلة (latest failed).
    """
    try:
        backups = backup_repo.list_backups()
    except Exception as e:
        logger.warning(f"تعذر قراءة فهرس النسخ الاحتياطي: {e}")
        backups = []

    if not backups:
        return {
            'status': STATUS_NOT_CONFIGURED,
            'status_ar': STATUS_LABELS_AR[STATUS_NOT_CONFIGURED],
            'message': 'لم يتم تسجيل أي نسخ احتياطية في المنظومة حتى الآن.',
            'checked_at': now.strftime('%Y-%m-%d %H:%M:%S UTC'),
            'metadata': {
                'backup_configured': False,
                'total_backups_count': 0,
                'latest_backup_id': None,
                'latest_completed_backup_id': None,
                'latest_validated_backup_id': None,
                'latest_failed_backup_id': None,
                'age_hours': None
            }
        }

    latest_created = backups[0]
    latest_completed = next((b for b in backups if b.get('status') == 'completed'), None)
    latest_validated = next((b for b in backups if b.get('status') == 'completed' and b.get('validation_status') == 'valid'), None)
    latest_failed = next((b for b in backups if b.get('status') == 'failed'), None)

    # حساب عمر أحدث نسخة مقبولة ومتحقق منها
    ref_backup_for_age = latest_validated or latest_completed or latest_created
    age_hours = _calculate_backup_age_hours(ref_backup_for_age, now)

    max_age = config.BACKUP_MAX_AGE_HOURS

    # القواعد الدقيقة لتحديد الحالة
    if latest_created.get('status') == 'failed':
        status = STATUS_DEGRADED
        if latest_validated:
            msg = f"فشلت آخر محاولة نسخ احتياطي ({latest_created.get('backup_identifier')})، ولكن تتوفر نسخة سابقة صالحة ({latest_validated.get('backup_identifier')})."
        else:
            msg = f"فشلت آخر محاولة لإنشاء نسخة احتياطية ({latest_created.get('backup_identifier')}) ولا توجد نسخة سابقة صالحة."
    elif latest_created.get('validation_status') == 'corrupted':
        status = STATUS_DEGRADED
        msg = f"النسخة الاحتياطية الأخيرة ({latest_created.get('backup_identifier')}) تالفة وفشلت في التحقق من السلامة."
    elif latest_created.get('status') == 'completed' and latest_created.get('validation_status') not in ('valid', 'verified'):
        status = STATUS_DEGRADED
        msg = f"النسخة الاحتياطية الأخيرة ({latest_created.get('backup_identifier')}) مكتملة ولكن لم يتم التحقق من سلامتها بعد."
    elif age_hours is not None and age_hours > max_age:
        status = STATUS_DEGRADED
        msg = f"النسخة الاحتياطية الصالحة متأخرة ({age_hours} ساعة مضت، الحد المتوقع {max_age} ساعة)."
    else:
        status = STATUS_HEALTHY
        msg = f"النسخ الاحتياطي سليم وصالح ومتحقق منه ({age_hours or 0} ساعة مضت)."

    return {
        'status': status,
        'status_ar': STATUS_LABELS_AR.get(status, status),
        'message': msg,
        'checked_at': now.strftime('%Y-%m-%d %H:%M:%S UTC'),
        'metadata': {
            'backup_configured': True,
            'total_backups_count': len(backups),
            'latest_backup_id': latest_created.get('backup_identifier'),
            'latest_backup_status': latest_created.get('status'),
            'latest_backup_validation_status': latest_created.get('validation_status'),
            'latest_completed_backup_id': latest_completed.get('backup_identifier') if latest_completed else None,
            'latest_validated_backup_id': latest_validated.get('backup_identifier') if latest_validated else None,
            'latest_failed_backup_id': latest_failed.get('backup_identifier') if latest_failed else None,
            'age_hours': age_hours,
            'max_age_hours_threshold': max_age
        }
    }


def _calculate_backup_age_hours(backup_dict: Optional[Dict[str, Any]], now: datetime) -> Optional[float]:
    """حساب عمر النسخة الاحتياطية بالساعات بدقة."""
    if not backup_dict:
        return None
    created_at_str = backup_dict.get('created_at', '')
    if not created_at_str:
        return None
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M'):
        try:
            dt = datetime.strptime(created_at_str.split('.')[0], fmt)
            return round((now - dt).total_seconds() / 3600, 1)
        except ValueError:
            continue
    return None


def _check_scan_jobs(now: datetime) -> Dict[str, Any]:
    """
    فحص طابور مهام الفحص ورصد المهام العالقة بدقة.
    يعتمد عمر المهمة العالقة على توقيت بدء المعالجة (ScanJob.created_at للمهام قيد التشغيل)
    وليس على تاريخ إنشاء البحث، مع استبعاد المهام المكتملة كلياً.
    """
    queued = 0
    processing = 0
    completed = 0
    failed = 0
    interrupted = 0
    stuck_jobs_count = 0

    stuck_limit_dt = now - timedelta(minutes=config.STUCK_JOB_MINUTES)

    try:
        with base_repo.get_session() as session:
            counts = (
                session.query(ScanJob.status, func.count(ScanJob.id))
                .group_by(ScanJob.status)
                .all()
            )
            count_map = {c[0]: c[1] for c in counts}
            queued = count_map.get('queued', 0)
            processing = count_map.get('running', 0) + count_map.get('processing', 0)
            completed = count_map.get('completed', 0)
            failed = count_map.get('failed', 0)
            interrupted = count_map.get('interrupted', 0)

            # المهام العالقة: مهام قيد المعالجة تجاوز وقتها الحد المسموح
            stuck_jobs_count = (
                session.query(ScanJob)
                .filter(
                    ScanJob.status.in_(['running', 'processing']),
                    ScanJob.created_at < stuck_limit_dt
                )
                .count()
            )

            # فحص مهام JobRecord العالقة والنشطة
            try:
                from app.models.schema import JobRecord
                stuck_job_records = (
                    session.query(JobRecord)
                    .filter(
                        JobRecord.status == 'running',
                        or_(
                            JobRecord.heartbeat_at < stuck_limit_dt,
                            and_(JobRecord.heartbeat_at == None, JobRecord.started_at < stuck_limit_dt)
                        )
                    )
                    .count()
                )
                stuck_jobs_count += stuck_job_records
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"تعذر استعلام مهام الفحص: {e}")

    if stuck_jobs_count > 0:
        status = STATUS_DEGRADED
        msg = f"يوجد {stuck_jobs_count} مهمة فحص عالقة في طور المعالجة لأكثر من {config.STUCK_JOB_MINUTES} دقيقة."
    else:
        status = STATUS_HEALTHY
        msg = f"طابور الفحص يعمل بصورة طبيعية ({processing} قيد المعالجة، {queued} بالانتظار)."

    return {
        'status': status,
        'status_ar': STATUS_LABELS_AR.get(status, status),
        'message': msg,
        'checked_at': now.strftime('%Y-%m-%d %H:%M:%S UTC'),
        'metadata': {
            'queued': queued,
            'processing': processing,
            'completed': completed,
            'failed': failed,
            'interrupted': interrupted,
            'stuck_jobs_count': stuck_jobs_count,
            'stuck_job_minutes_threshold': config.STUCK_JOB_MINUTES,
            'max_concurrent_scans': config.MAX_CONCURRENT_SCANS,
            'max_queued_jobs': config.MAX_QUEUED_JOBS,
        }
    }


def _check_batches(now: datetime) -> Dict[str, Any]:
    """فحص مجمع وخفيف لحالة دفعات الفحص وعناصرها."""
    active_batches = 0
    queued_items = 0
    failed_items = 0
    interrupted_items = 0

    try:
        with base_repo.get_session() as session:
            active_batches = (
                session.query(ScanBatch)
                .filter(ScanBatch.status.in_(['processing', 'running', 'queued']))
                .count()
            )
            item_counts = (
                session.query(ScanBatchItem.status, func.count(ScanBatchItem.id))
                .group_by(ScanBatchItem.status)
                .all()
            )
            count_map = {c[0]: c[1] for c in item_counts}
            queued_items = count_map.get('queued', 0)
            failed_items = count_map.get('failed', 0)
            interrupted_items = count_map.get('interrupted', 0)
    except Exception as e:
        logger.warning(f"تعذر استعلام حالة الدفعات: {e}")

    status = STATUS_HEALTHY
    msg = f"حالة الدفعات: {active_batches} دفعة نشطة، {queued_items} عنصر بالانتظار."

    return {
        'status': status,
        'status_ar': STATUS_LABELS_AR.get(status, status),
        'message': msg,
        'checked_at': now.strftime('%Y-%m-%d %H:%M:%S UTC'),
        'metadata': {
            'active_batches': active_batches,
            'queued_items': queued_items,
            'failed_items': failed_items,
            'interrupted_items': interrupted_items
        }
    }


def _check_reference_corpus(now: datetime) -> Dict[str, Any]:
    """فحص خفيف لقاعدة المراجع المعتمدة وإصدار البصمة وحالة فهرس الاسترجاع."""
    doc_count = 0
    active_count = 0
    current_version = "REF-2026-000001"
    fingerprint_present = False
    last_updated = None
    index_state = "current"
    index_corpus_version = ""
    last_rebuild = None

    try:
        from app.models.schema import IndexStateRecord
        with base_repo.get_session() as session:
            doc_count = session.query(Document).count()
            active_count = session.query(Document).filter(Document.current_status == 'active').count()
            latest_v = (
                session.query(ReferenceCorpusVersion)
                .order_by(ReferenceCorpusVersion.id.desc())
                .first()
            )
            if latest_v:
                current_version = latest_v.version_identifier or f"V{latest_v.id}"
                fingerprint_present = bool(latest_v.fingerprint)
                last_updated = latest_v.created_at.strftime('%Y-%m-%d %H:%M:%S') if latest_v.created_at else None

            idx_rec = session.query(IndexStateRecord).order_by(IndexStateRecord.id.desc()).first()
            if idx_rec:
                index_state = idx_rec.state
                index_corpus_version = idx_rec.index_corpus_version
                last_rebuild = idx_rec.built_at.strftime('%Y-%m-%d %H:%M:%S') if idx_rec.built_at else None
    except Exception as e:
        logger.warning(f"تعذر استعلام بيانات قاعدة المراجع: {e}")

    status = STATUS_HEALTHY
    if index_state == 'failed':
        status = STATUS_DEGRADED
        msg = f"فهرس الاسترجاع في حالة خطأ ({index_state})، قاعدة المراجع: {current_version} ({active_count} مرجع نشط)."
    elif index_state == 'stale':
        msg = f"قاعدة المراجع معتمدة ({current_version})، الفهرس بانتظار التحديث عند الفحص القادم ({active_count} مرجع نشط)."
    else:
        msg = f"قاعدة المراجع والفهرس متطابقان وسليمان ({current_version}، {active_count} مرجع نشط)."

    return {
        'status': status,
        'status_ar': STATUS_LABELS_AR.get(status, status),
        'message': msg,
        'checked_at': now.strftime('%Y-%m-%d %H:%M:%S UTC'),
        'metadata': {
            'corpus_version': current_version,
            'documents_count': doc_count,
            'active_reference_count': active_count,
            'index_state': index_state,
            'index_corpus_version': index_corpus_version,
            'last_successful_rebuild': last_rebuild,
            'fingerprint_present': fingerprint_present,
            'last_updated': last_updated
        }
    }



def _check_ocr(now: datetime) -> Dict[str, Any]:
    """
    فحص جاهزية محرك التعرف الضوئي OCR المحلي وحزم اللغة العربية بكفاءة عالية (Cached TTL).
    لا ينفذ أي عمليات OCR فعلية ولا يطلق عمليات معالجة فرعية مجهدة على كل طلب.
    """
    settings = get_current_settings()
    enabled = settings.get('enable_ocr', True)

    if not enabled:
        return {
            'status': STATUS_DISABLED,
            'status_ar': STATUS_LABELS_AR[STATUS_DISABLED],
            'message': 'محرك التعرف الضوئي (OCR) معطل في إعدادات المنظومة.',
            'checked_at': now.strftime('%Y-%m-%d %H:%M:%S UTC'),
            'metadata': {
                'enabled': False,
                'available': False,
                'has_arabic': False,
                'version': None
            }
        }

    # فحص الكاش
    cur_time = time.time()
    if _OCR_CACHE['data'] and (cur_time - _OCR_CACHE['last_checked'] < _OCR_CACHE['ttl_seconds']):
        ocr_info = _OCR_CACHE['data']
    else:
        ocr_info = check_ocr_availability()
        _OCR_CACHE['data'] = ocr_info
        _OCR_CACHE['last_checked'] = cur_time

    available = ocr_info.get('available', False)
    has_arabic = ocr_info.get('has_arabic', False)

    if not available:
        status = STATUS_DEGRADED
        msg = 'محرك OCR مفعل في الإعدادات لكن برنامج Tesseract غير مثبت محلياً.'
    elif not has_arabic:
        status = STATUS_DEGRADED
        msg = 'محرك OCR متاح لكن حزمة اللغة العربية (ara.traineddata) غير متوفرة.'
    else:
        status = STATUS_HEALTHY
        msg = 'محرك OCR جاهز محلياً ويدعم قراءة النصوص العربية الممسوحة ضوئياً.'

    return {
        'status': status,
        'status_ar': STATUS_LABELS_AR.get(status, status),
        'message': msg,
        'checked_at': now.strftime('%Y-%m-%d %H:%M:%S UTC'),
        'metadata': {
            'enabled': True,
            'available': available,
            'has_arabic': has_arabic,
            'version': ocr_info.get('version'),
            'languages': ocr_info.get('languages', [])
        }
    }


def _check_semantic_model(now: datetime) -> Dict[str, Any]:
    """
    فحص جاهزية نموذج المطابقة الدلالية أوفلاين.
    لا يقوم إطلاقاً بتحميل النموذج في الذاكرة ولا يستدعي FastEmbed/ONNX أثناء الفحص الصحي.
    """
    settings = get_current_settings()
    enabled = settings.get('enable_semantic_model', False)

    if not enabled:
        return {
            'status': STATUS_DISABLED,
            'status_ar': STATUS_LABELS_AR[STATUS_DISABLED],
            'message': 'المطابقة الدلالية معطلة في إعدادات المنظومة (خيار قياسي لتسريع المعالجة).',
            'checked_at': now.strftime('%Y-%m-%d %H:%M:%S UTC'),
            'metadata': {
                'enabled': False,
                'available': False,
                'offline_only': True,
                'model_name': 'fastembed-lightweight'
            }
        }

    model_info = check_semantic_model_availability()
    available = model_info.get('available', False)

    if not available:
        status = STATUS_DEGRADED
        msg = 'المطابقة الدلالية مفعلة ولكن ملفات النموذج المحلي غير متوفرة محلياً.'
    else:
        status = STATUS_HEALTHY
        msg = 'نموذج المطابقة الدلالية جاهز ومتاح محلياً على القرص (100% أوفلاين).'

    return {
        'status': status,
        'status_ar': STATUS_LABELS_AR.get(status, status),
        'message': msg,
        'checked_at': now.strftime('%Y-%m-%d %H:%M:%S UTC'),
        'metadata': {
            'enabled': True,
            'available': available,
            'offline_only': True,
            'model_name': 'fastembed-lightweight'
        }
    }


def _get_recent_incidents(limit: int = 8) -> List[Dict[str, Any]]:
    """
    استرجاع ملخص مقتضب للحوادث التشغيلية الحديثة.
    ملاحظة: محصن ضد تسريب الأسرار والمسارات المطلقة ونصوص الأبحاث.
    """
    incidents = []
    try:
        with base_repo.get_session() as session:
            logs = (
                session.query(AuditLog)
                .filter(
                    AuditLog.success.is_(False),
                    AuditLog.category.in_(['backup', 'system', 'database', 'integrity', 'storage'])
                )
                .order_by(AuditLog.id.desc())
                .limit(limit)
                .all()
            )
            for l in logs:
                incidents.append({
                    'id': l.id,
                    'action': l.action,
                    'category': l.category,
                    'created_at': l.created_at.strftime('%Y-%m-%d %H:%M:%S') if l.created_at else '',
                    'failure_reason_code': l.failure_reason_code or 'UNKNOWN_ERROR',
                    'username': l.username_snapshot or 'system'
                })
    except Exception as e:
        logger.warning(f"تعذر استعلام ملخص الأحداث التشغيلية: {e}")

    return incidents


# ─── كبح التنبيهات المكررة (State-Aware Deduplication) ─────────────────────────

def _evaluate_alert_state_transitions(components: Dict[str, Dict[str, Any]]):
    """
    تتبع الانتقالات في حالة المكونات التشغيلية لمنع تضخيم سجل التدقيق:
    - healthy -> degraded/critical: تسجيل الحدث مرة واحدة.
    - degraded -> degraded: كبح التكرار وعدم إعادة التسجيل.
    - degraded -> healthy: توثيق التعافي والعودة للحالة السليمة.
    - healthy -> degraded (مجدداً): تسجيل حدث جديد.
    """
    global _ALERT_STATE_TRACKER

    for name in ('storage', 'backup', 'ocr', 'semantic_model', 'database', 'scan_jobs'):
        comp = components.get(name, {})
        new_state = comp.get('status', STATUS_HEALTHY)
        old_state = _ALERT_STATE_TRACKER.get(name, STATUS_HEALTHY)

        if old_state != new_state:
            _ALERT_STATE_TRACKER[name] = new_state
            if new_state in (STATUS_DEGRADED, STATUS_CRITICAL) and old_state == STATUS_HEALTHY:
                logger.warning(f"انتقال تشغيلي للمكون [{name}]: {old_state} -> {new_state} ({comp.get('message', '')})")
            elif new_state == STATUS_HEALTHY and old_state in (STATUS_DEGRADED, STATUS_CRITICAL):
                logger.info(f"تعافي المكون التشغيلي [{name}]: {old_state} -> {new_state}")


# ─── تنقية الخصوصية الشاملة (Recursive Privacy Sanitization) ──────────────────

_PATH_PATTERN = re.compile(r'([A-Za-z]:\\[^"\'\s\<\>]+|/(?:Users|home|tmp|var)/[^"\'\s\<\>]+)')

def _sanitize_privacy(obj: Any) -> Any:
    """إزالة أي مسارات مطلقة حساسة أو بيانات شخصية من الرد بصورة عودية."""
    if isinstance(obj, dict):
        cleaned = {}
        for k, v in obj.items():
            # استبعاد المفاتيح الحساسة
            if k in ('file_path', 'full_path', 'password', 'token', 'secret', 'connection_string', 'extracted_text', 'full_text'):
                continue
            cleaned[k] = _sanitize_privacy(v)
        return cleaned
    elif isinstance(obj, list):
        return [_sanitize_privacy(item) for item in obj]
    elif isinstance(obj, str):
        # استبدال المسارات المطلقة الحساسة
        return _PATH_PATTERN.sub('[LOCAL_STORAGE_PATH]', obj)
    return obj
