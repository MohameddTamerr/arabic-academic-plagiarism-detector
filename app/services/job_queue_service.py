# -*- coding: utf-8 -*-
"""
محرك إدارة طابور المهام الخلفية والتزامن المحصن (Job Queue & Execution Service):
- إدارة دورة حياة المهام القياسية (queued, running, completed, failed, cancel_requested, cancelled, interrupted).
- سحب المهام الذري الآمن للعمليات المتعددة (Atomic Process-Safe Claiming via SQLite).
- فرض حدود التزامن الصارمة ومنع استنزاف الموارد (Bounded Concurrency & Backpressure).
- جدولة عادلة بين الأبحاث الفردية والدفعات الكبيرة لمنع التجويع (Batch Fairness).
- فحص دوري لنبض الحياة (Heartbeat) ورصد المهام العالقة بدقة.
- إلغاء تعاوني آمن (Cooperative Cancellation) عند نقاط التفتيش الآمنة.
- إعادة المحاولة المنضبطة مع التراجع الزمني للأخطاء العابرة (Bounded Exponential Backoff).
- استعادة واستدراك المهام المنقطعة عند إعادة تشغيل الخادم (Restart Recovery).
- تنظيف دوري لسجلات المهام القديمة للتحكم في نمو قاعدة البيانات.
"""

import os
import time
import uuid
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple, Callable

from sqlalchemy import text, desc, func, and_, or_

import config
from app.repositories import base_repo
from app.models.schema import JobRecord
from app.errors.error_codes import ErrorCode

logger = logging.getLogger(__name__)


# ─── ثوابت أنواع وحالات المهام ───────────────────────────────────────────────

class JobType:
    SCAN = "scan"
    BATCH_SCAN = "batch_scan"
    THESIS_SCAN = "thesis_scan"
    REFERENCE_INDEX_REBUILD = "reference_index_rebuild"
    INTEGRITY_CHECK = "integrity_check"
    BACKUP = "backup"
    REPORT_EXPORT = "report_export"


class JobStatus:
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


JOB_STATUS_LABELS_AR = {
    JobStatus.QUEUED: "قيد الانتظار",
    JobStatus.RUNNING: "قيد التنفيذ",
    JobStatus.COMPLETED: "مكتمل",
    JobStatus.FAILED: "فشل",
    JobStatus.CANCEL_REQUESTED: "جاري الإلغاء",
    JobStatus.CANCELLED: "ملغى",
    JobStatus.INTERRUPTED: "منقطع",
}

JOB_TYPE_LABELS_AR = {
    JobType.SCAN: "فحص بحث",
    JobType.BATCH_SCAN: "فحص دفعة",
    JobType.THESIS_SCAN: "فحص رسالة متعددة الملفات",
    JobType.REFERENCE_INDEX_REBUILD: "إعادة بناء فهرس المراجع",
    JobType.INTEGRITY_CHECK: "فحص النزاهة الشامل",
    JobType.BACKUP: "نسخ احتياطي",
    JobType.REPORT_EXPORT: "تصدير تقارير",
}

# قائمة الأخطاء العابرة القابلة لإعادة المحاولة التلقائية
TRANSIENT_ERROR_SUBSTRINGS = (
    "database is locked",
    "locked",
    "busy",
    "resource temporarily unavailable",
    "temporary failure",
    "connection reset",
    "worker interrupted",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ─── إضافة مهمة جديدة إلى الطابور (Enqueue) ───────────────────────────────────

def enqueue_job(
    job_type: str,
    payload: Optional[Dict[str, Any]] = None,
    requested_by: str = '',
    priority: int = 0,
    research_id: Optional[int] = None,
    batch_id: Optional[str] = None,
    batch_item_id: Optional[int] = None,
    scan_execution_id: Optional[str] = None,
    target_corpus_version: Optional[str] = None,
    max_attempts: int = 3,
    custom_job_id: Optional[str] = None
) -> Tuple[Optional[str], Optional[str]]:
    """
    إدراج مهمة جديدة في طابور SQLite المحصن مع التحقق من حدود الضغط والتكرار.
    يُعيد: (job_id, error_code)
    - إذا نجح: (job_id, None)
    - إذا فشل: (None, error_code)
    """
    now = _utcnow()
    payload_str = json.dumps(payload or {}, ensure_ascii=False)

    with base_repo.get_session() as session:
        # 1. التحقق من سقف ضغط العمل الخلفي (Backpressure)
        queued_count = session.query(func.count(JobRecord.id)).filter(
            JobRecord.status == JobStatus.QUEUED
        ).scalar() or 0

        if queued_count >= config.MAX_QUEUED_JOBS:
            logger.warning(f"تم رفض إدراج المهمة: طابور المهام ممتلئ ({queued_count} >= {config.MAX_QUEUED_JOBS})")
            return None, ErrorCode.JOB_QUEUE_FULL

        # 2. منع تكرار مهام إعادة بناء الفهرس لنفس الإصدار ذرياً عبر العمليات (DB-Atomic Index Rebuild Deduplication)
        if job_type == JobType.REFERENCE_INDEX_REBUILD and target_corpus_version:
            try:
                session.execute(text("BEGIN IMMEDIATE;"))
            except Exception:
                pass
            existing = session.query(JobRecord).filter(
                JobRecord.job_type == JobType.REFERENCE_INDEX_REBUILD,
                JobRecord.target_corpus_version == target_corpus_version,
                JobRecord.status.in_([JobStatus.QUEUED, JobStatus.RUNNING])
            ).first()
            if existing:
                logger.info(f"تم العثور على مهمة بناء فهرس نشطة مسبقاً للإصدار {target_corpus_version}: {existing.id}")
                return existing.id, None

        # 3. إنشاء سجل المهمة
        job_id = custom_job_id or f"job-{uuid.uuid4().hex[:12]}"
        exec_id = scan_execution_id or f"exec-{uuid.uuid4().hex[:12]}"

        job = JobRecord(
            id=job_id,
            job_type=job_type,
            status=JobStatus.QUEUED,
            priority=priority,
            queued_at=now,
            requested_by=requested_by,
            attempt_count=0,
            max_attempts=max_attempts,
            research_id=research_id,
            batch_id=batch_id,
            batch_item_id=batch_item_id,
            scan_execution_id=exec_id,
            target_corpus_version=target_corpus_version,
            payload_json=payload_str,
            result_json='{}',
            created_at=now
        )
        session.add(job)
        session.commit()

        logger.info(f"تم إدراج المهمة بنجاح: {job_id} ({job_type}) بواسطة: {requested_by}")
        return job_id, None


# ─── سحب المهام الذري المحصن (Atomic Multi-Process Claiming) ───────────────────

def claim_next_job(worker_pid: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """
    سحب المهمة المؤهلة التالية ذرياً عبر معاملة SQLite مع تطبيق حدود التزامن وعدالة الدفعات.
    يُعيد قاموس بيانات المهمة المسحوبة أو None إذا لم توجد مهمة مؤهلة حالياً.
    """
    pid = worker_pid or os.getpid()
    now = _utcnow()
    lease_token = uuid.uuid4().hex

    with base_repo.get_session() as session:
        # 1. حساب المهام الجارية حالياً لكل نوع لضبط التزامن
        running_counts = dict(
            session.query(JobRecord.job_type, func.count(JobRecord.id))
            .filter(JobRecord.status == JobStatus.RUNNING)
            .group_by(JobRecord.job_type)
            .all()
        )

        running_scans = (
            running_counts.get(JobType.SCAN, 0) +
            running_counts.get(JobType.BATCH_SCAN, 0) +
            running_counts.get(JobType.THESIS_SCAN, 0)
        )
        running_index_builds = running_counts.get(JobType.REFERENCE_INDEX_REBUILD, 0)
        running_backups = running_counts.get(JobType.BACKUP, 0)

        # 2. تحديد الأنواع المسموح بسحبها بناءً على السعة الشاغرة
        disallowed_types = set()
        if running_scans >= config.MAX_CONCURRENT_SCANS:
            disallowed_types.update([JobType.SCAN, JobType.BATCH_SCAN, JobType.THESIS_SCAN])
        if running_index_builds >= config.MAX_CONCURRENT_INDEX_BUILDS:
            disallowed_types.add(JobType.REFERENCE_INDEX_REBUILD)
        if running_backups >= config.MAX_CONCURRENT_BACKUPS:
            disallowed_types.add(JobType.BACKUP)

        # 3. استعلام المهام الجاهزة للتنفيذ
        query = session.query(JobRecord).filter(
            JobRecord.status == JobStatus.QUEUED,
            or_(JobRecord.retry_at == None, JobRecord.retry_at <= now)
        )
        if disallowed_types:
            query = query.filter(~JobRecord.job_type.in_(disallowed_types))

        # ترتيب حسب الأولوية تنازلياً ثم تاريخ الإدراج تصاعدياً (FIFO)
        candidate_jobs = query.order_by(
            JobRecord.priority.desc(),
            JobRecord.queued_at.asc()
        ).limit(10).all()

        if not candidate_jobs:
            return None

        # 4. تطبيق عدالة الجدولة ومنع تجويع الأبحاث المستقلة (Batch Fairness)
        active_batch_ids = {
            r[0] for r in session.query(JobRecord.batch_id).filter(
                JobRecord.status == JobStatus.RUNNING,
                JobRecord.batch_id != None
            ).all() if r[0]
        }

        selected_job: Optional[JobRecord] = None
        for job in candidate_jobs:
            if job.batch_id and job.batch_id in active_batch_ids and len(candidate_jobs) > 1:
                # محاولة إيجاد بحث مستقل في المرشحين
                continue
            selected_job = job
            break

        if not selected_job:
            selected_job = candidate_jobs[0]

        # 5. التحديث الذري لحالة المهمة إلى running عبر شرط التحقق من حالة الطابور (Atomic Conditional Update)
        claimed_id = None
        candidates_to_try = [selected_job] + [j for j in candidate_jobs if j.id != selected_job.id]

        for candidate in candidates_to_try:
            res = session.execute(
                text("""
                    UPDATE job_records
                    SET status = :running_status,
                        started_at = :started_at,
                        heartbeat_at = :heartbeat_at,
                        worker_pid = :worker_pid,
                        lease_token = :lease_token,
                        attempt_count = attempt_count + 1,
                        stage = :stage
                    WHERE id = :job_id AND status = :queued_status
                """),
                {
                    'running_status': JobStatus.RUNNING,
                    'started_at': now,
                    'heartbeat_at': now,
                    'worker_pid': pid,
                    'lease_token': lease_token,
                    'stage': "بدء التنفيذ",
                    'job_id': candidate.id,
                    'queued_status': JobStatus.QUEUED,
                }
            )
            if res.rowcount > 0:
                claimed_id = candidate.id
                break

        if not claimed_id:
            session.rollback()
            return None

        session.commit()

        updated_job = session.query(JobRecord).filter(JobRecord.id == claimed_id).first()
        if not updated_job:
            return None

        job_dict = _job_to_dict(updated_job)
        logger.info(f"تم سحب المهمة {job_dict['id']} بنجاح بواسطة العملية {pid} (المحاولة: {job_dict['attempt_count']})")
        return job_dict


# ─── نبض الحياة وتحديث التقدم (Heartbeat & Progress) ─────────────────────────

def heartbeat_job(
    job_id: str,
    progress: Optional[int] = None,
    stage: Optional[str] = None,
    min_interval_seconds: int = 5,
    lease_token: Optional[str] = None
) -> bool:
    """
    تحديث نبض الحياة وسجل التقدم مع كبح الكتابة المفرطة في قاعدة البيانات وحماية ملكية الإيجار (Lease Ownership).
    يُعيد True إذا تم التحديث بنجاح.
    """
    now = _utcnow()
    with base_repo.get_session() as session:
        job = session.query(JobRecord).filter(JobRecord.id == job_id).first()
        if not job or job.status != JobStatus.RUNNING:
            return False

        # التحقق من ملكية الإيجار (Lease Token Check)
        if lease_token and job.lease_token and job.lease_token != lease_token:
            logger.warning(f"رفض تحديث نبض الحياة للمهمة {job_id}: عدم تطابق رمز الإيجار ({lease_token} != {job.lease_token})")
            return False

        if job.heartbeat_at and progress is None and stage is None:
            elapsed = (now - job.heartbeat_at).total_seconds()
            if elapsed < min_interval_seconds:
                return True

        job.heartbeat_at = now
        if progress is not None:
            job.progress = max(0, min(100, progress))
        if stage:
            job.stage = stage

        session.commit()
        return True


def update_job_progress(job_id: str, progress: int, stage: Optional[str] = None, lease_token: Optional[str] = None) -> bool:
    """تحديث نسبة ومرحلة تقدم المهمة."""
    return heartbeat_job(job_id, progress=progress, stage=stage, min_interval_seconds=0, lease_token=lease_token)


# ─── الإلغاء التعاوني المنضبط (Cooperative Cancellation) ──────────────────────

def request_job_cancellation(
    job_id: str,
    actor: str = 'user',
    reason: str = ''
) -> Tuple[bool, str, Optional[str]]:
    """
    طلب إلغاء مهمة تعاونياً.
    - إذا كانت queued: تُلغى فوراً دون أن يسحبها أي عامل.
    - إذا كانت running: يُسجل cancel_requested وتتحول إلى cancelled عند أقرب نقطة تفتيش آمنة.
    - إذا كانت completed: يُرفض الإلغاء بكود JOB_CANCEL_NOT_ALLOWED.
    يُعيد: (success, message, error_code)
    """
    now = _utcnow()
    with base_repo.get_session() as session:
        job = session.query(JobRecord).filter(JobRecord.id == job_id).first()
        if not job:
            return False, "المهمة غير موجودة.", ErrorCode.JOB_NOT_FOUND

        if job.status == JobStatus.COMPLETED:
            return False, "لا يمكن إلغاء مهمة مكتملة بنجاح.", ErrorCode.JOB_CANCEL_NOT_ALLOWED

        if job.status == JobStatus.CANCELLED:
            return True, "المهمة ملغاة مسبقاً.", None

        if job.status == JobStatus.QUEUED:
            job.status = JobStatus.CANCELLED
            job.finished_at = now
            job.safe_error_message = f"تم الإلغاء قبل البدء بواسطة {actor}: {reason}".strip()
            session.commit()
            logger.info(f"تم إلغاء المهمة في الطابور مباشرة: {job_id}")
            return True, "تم إلغاء المهمة بنجاح.", None

        if job.status == JobStatus.RUNNING:
            job.cancel_requested = 1
            job.status = JobStatus.CANCEL_REQUESTED
            job.safe_error_message = f"طلب إلغاء بواسطة {actor}: {reason}".strip()
            session.commit()
            logger.info(f"تم تسجيل طلب إلغاء للمهمة قيد التشغيل: {job_id}")
            return True, "تم تسجيل طلب الإلغاء وسيتم التوقف عند أقرب نقطة آمنة.", None

        return False, f"حالة المهمة الحالية ({job.status}) لا تقبل الإلغاء.", ErrorCode.JOB_CANCEL_NOT_ALLOWED


def is_cancellation_requested(job_id: str) -> bool:
    """فحص سريع لمعرفة ما إذا كان قد طُلب إلغاء المهمة."""
    with base_repo.get_session() as session:
        job = session.query(JobRecord).filter(JobRecord.id == job_id).first()
        if not job:
            return False
        return bool(job.cancel_requested or job.status in (JobStatus.CANCEL_REQUESTED, JobStatus.CANCELLED))


def finalize_cancellation(
    job_id: str,
    cleanup_fn: Optional[Callable[[], None]] = None,
    lease_token: Optional[str] = None
) -> bool:
    """تأكيد إلغاء المهمة نهائياً عند نقطة التفتيش الآمنة وتنظيف المخلفات المؤقتة مع التحقق من ملكية الإيجار."""
    now = _utcnow()
    with base_repo.get_session() as session:
        job = session.query(JobRecord).filter(JobRecord.id == job_id).first()
        if not job:
            return False

        if lease_token and job.lease_token and job.lease_token != lease_token:
            logger.warning(f"رفض تأكيد إلغاء المهمة {job_id}: عدم تطابق رمز الإيجار ({lease_token} != {job.lease_token})")
            return False

        if cleanup_fn:
            try:
                cleanup_fn()
            except Exception as e:
                logger.warning(f"تحذير أثناء تنظيف مخلفات المهمة الملغاة {job_id}: {e}")

        job.status = JobStatus.CANCELLED
        job.finished_at = now
        job.stage = "تم الإلغاء بنجاح"
        session.commit()
        logger.info(f"تم إنهاء وتأكيد إلغاء المهمة بنجاح: {job_id}")
        return True


# ─── إنهاء وفشل المهام وإعادة المحاولة (Completion, Failure & Retries) ────────

def complete_job(
    job_id: str,
    result: Optional[Dict[str, Any]] = None,
    report_id: Optional[str] = None,
    lease_token: Optional[str] = None
) -> bool:
    """
    تسجيل اكتمال المهمة بنجاح وحفظ النتائج بشكل نهائي مع التحقق من ملكية الإيجار.
    يُعيد True إذا تم الاكتمال بنجاح، أو False في حال عدم العثور عليها أو عدم تطابق الإيجار.
    """
    now = _utcnow()
    result_str = json.dumps(result or {}, ensure_ascii=False)

    with base_repo.get_session() as session:
        job = session.query(JobRecord).filter(JobRecord.id == job_id).first()
        if not job:
            return False

        if lease_token and job.lease_token and job.lease_token != lease_token:
            logger.warning(f"رفض إكمال المهمة {job_id}: عدم تطابق رمز الإيجار ({lease_token} != {job.lease_token})")
            return False

        job.status = JobStatus.COMPLETED
        job.progress = 100
        job.stage = "اكتمل بنجاح"
        job.finished_at = now
        job.result_json = result_str
        if report_id:
            job.report_id = report_id
        session.commit()
        logger.info(f"اكتملت المهمة {job_id} بنجاح.")
        return True


def fail_job(
    job_id: str,
    error_code: str,
    error_message: str,
    is_transient: bool = False,
    lease_token: Optional[str] = None
) -> bool:
    """
    تسجيل فشل المهمة مع دعم إعادة المحاولة المنضبطة بالأخطاء العابرة (Bounded Backoff) وحماية الإيجار.
    """
    now = _utcnow()
    clean_error_msg = str(error_message).strip()

    with base_repo.get_session() as session:
        job = session.query(JobRecord).filter(JobRecord.id == job_id).first()
        if not job:
            return False

        if lease_token and job.lease_token and job.lease_token != lease_token:
            logger.warning(f"رفض تسجيل فشل المهمة {job_id}: عدم تطابق رمز الإيجار ({lease_token} != {job.lease_token})")
            return False

        can_retry = is_transient and (job.attempt_count < job.max_attempts)
        if not can_retry and any(ts in clean_error_msg.lower() for ts in TRANSIENT_ERROR_SUBSTRINGS):
            can_retry = job.attempt_count < job.max_attempts

        if can_retry:
            backoff_seconds = [5, 30, 120][min(job.attempt_count - 1, 2)]
            job.status = JobStatus.QUEUED
            job.retry_at = now + timedelta(seconds=backoff_seconds)
            job.error_code = error_code
            job.safe_error_message = f"محاولة {job.attempt_count} فشلت ({error_code})، جاري إعادة المحاولة بعد {backoff_seconds} ثانية..."
            job.stage = "في انتظار إعادة المحاولة"
            session.commit()
            logger.warning(f"تمت جدولة إعادة محاولة للمهمة {job_id} بعد {backoff_seconds} ثوانٍ (محاولة {job.attempt_count}/{job.max_attempts})")
        else:
            final_err_code = ErrorCode.JOB_RETRY_LIMIT_REACHED if (job.attempt_count >= job.max_attempts and is_transient) else error_code
            job.status = JobStatus.FAILED
            job.finished_at = now
            job.error_code = final_err_code
            job.safe_error_message = clean_error_msg
            job.stage = "فشلت المهمة"
            session.commit()
            logger.error(f"فشلت المهمة {job_id} نهائياً ({final_err_code}): {clean_error_msg}")
        return True


# ─── إعادة المحاولة اليدوية الذرية (Atomic Manual Retry) ──────────────────────

def retry_job_manually(job_id: str, actor: str = 'admin') -> Tuple[bool, str, Optional[str]]:
    """
    إعادة تشغيل مهمة فاشلة أو منقطعة يدوياً ذرياً لمنع تكرار الجدولة بين العمليات المتزامنة.
    يُعيد: (success, message, error_code)
    """
    now = _utcnow()
    with base_repo.get_session() as session:
        res = session.execute(
            text("""
                UPDATE job_records
                SET status = :queued_status,
                    retry_at = :now,
                    attempt_count = 0,
                    progress = 0,
                    stage = :stage,
                    safe_error_message = '',
                    error_code = '',
                    cancel_requested = 0,
                    started_at = NULL,
                    finished_at = NULL,
                    lease_token = NULL,
                    worker_pid = NULL
                WHERE id = :job_id AND status IN (:failed, :interrupted, :cancelled)
            """),
            {
                'queued_status': JobStatus.QUEUED,
                'now': now,
                'stage': "تمت إعادة الجدولة يدوياً",
                'job_id': job_id,
                'failed': JobStatus.FAILED,
                'interrupted': JobStatus.INTERRUPTED,
                'cancelled': JobStatus.CANCELLED
            }
        )
        if res.rowcount == 0:
            job = session.query(JobRecord).filter(JobRecord.id == job_id).first()
            if not job:
                return False, "المهمة غير موجودة.", ErrorCode.JOB_NOT_FOUND
            return False, f"لا يمكن إعادة تشغيل مهمة في حالة {job.status}.", ErrorCode.JOB_ALREADY_RUNNING

        session.commit()
        logger.info(f"تمت إعادة جدولة المهمة {job_id} يدوياً بواسطة {actor}")
        return True, "تمت إعادة جدولة المهمة بنجاح.", None


# ─── التعافي عند إعادة التشغيل والمهام العالقة (Recovery & Stuck Detection) ───

def recover_interrupted_jobs() -> int:
    """
    فحص المهام التي تُركت في حالة running أو cancel_requested من جلسات سابقة وتحويلها إلى interrupted.
    يتم استدعاؤها حتمياً عند بدء تشغيل التطبيق.
    يُعيد عدد المهام التي تم استدراكها.
    """
    now = _utcnow()
    recovered_count = 0

    with base_repo.get_session() as session:
        orphans = session.query(JobRecord).filter(
            JobRecord.status.in_([JobStatus.RUNNING, JobStatus.CANCEL_REQUESTED])
        ).all()

        for job in orphans:
            job.status = JobStatus.INTERRUPTED
            job.finished_at = now
            job.error_code = ErrorCode.JOB_INTERRUPTED
            job.safe_error_message = "انقطعت المهمة نتيجة إغلاق أو إعادة تشغيل الخادم."
            job.stage = "منقطع"
            recovered_count += 1

        if recovered_count > 0:
            session.commit()
            logger.info(f"تم استدراك {recovered_count} مهمة منقطعة من التشغيل السابق.")

    return recovered_count


def get_stuck_jobs(stuck_minutes: Optional[int] = None) -> List[Dict[str, Any]]:
    """استرجاع قائمة بالمهام التي يبدو أنها عالقة بناءً على عمر نبض الحياة."""
    mins = stuck_minutes or config.JOB_STUCK_HEARTBEAT_MINUTES
    cutoff = _utcnow() - timedelta(minutes=mins)

    with base_repo.get_session() as session:
        stuck_records = session.query(JobRecord).filter(
            JobRecord.status == JobStatus.RUNNING,
            or_(
                JobRecord.heartbeat_at < cutoff,
                and_(JobRecord.heartbeat_at == None, JobRecord.started_at < cutoff)
            )
        ).all()
        return [_job_to_dict(j) for j in stuck_records]


# ─── استعلام وإحصائيات الطابور (Querying & Monitoring) ─────────────────────────

def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """استرجاع بيانات مهمة واحدة."""
    with base_repo.get_session() as session:
        job = session.query(JobRecord).filter(JobRecord.id == job_id).first()
        if not job:
            return None
        return _job_to_dict(job)


def list_jobs(
    status: Optional[str] = None,
    job_type: Optional[str] = None,
    requested_by: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> Tuple[List[Dict[str, Any]], int]:
    """
    استرجاع قائمة المهام مع الفرز والتصفية والترقيم لدعم شاشات الإدارة والمراقبة.
    يُعيد: (items, total_count)
    """
    with base_repo.get_session() as session:
        query = session.query(JobRecord)

        if status:
            query = query.filter(JobRecord.status == status)
        if job_type:
            query = query.filter(JobRecord.job_type == job_type)
        if requested_by:
            query = query.filter(JobRecord.requested_by == requested_by)

        total_count = query.count()
        records = query.order_by(JobRecord.queued_at.desc()).offset(offset).limit(limit).all()

        return [_job_to_dict(r) for r in records], total_count


def get_queue_stats() -> Dict[str, Any]:
    """
    استرجاع إحصائيات مجمعة وسريعة لطابور المهام وسعة المعالجة للوحة الصحة والتشغيل.
    """
    now = _utcnow()
    cutoff_recent = now - timedelta(hours=24)
    stuck_cutoff = now - timedelta(minutes=config.JOB_STUCK_HEARTBEAT_MINUTES)

    with base_repo.get_session() as session:
        counts = dict(
            session.query(JobRecord.status, func.count(JobRecord.id))
            .group_by(JobRecord.status)
            .all()
        )

        oldest_queued = session.query(func.min(JobRecord.queued_at)).filter(
            JobRecord.status == JobStatus.QUEUED
        ).scalar()

        oldest_queued_seconds = (now - oldest_queued).total_seconds() if oldest_queued else 0

        stuck_count = session.query(func.count(JobRecord.id)).filter(
            JobRecord.status == JobStatus.RUNNING,
            or_(
                JobRecord.heartbeat_at < stuck_cutoff,
                and_(JobRecord.heartbeat_at == None, JobRecord.started_at < stuck_cutoff)
            )
        ).scalar() or 0

        recent_failed = session.query(func.count(JobRecord.id)).filter(
            JobRecord.status == JobStatus.FAILED,
            JobRecord.finished_at >= cutoff_recent
        ).scalar() or 0

        return {
            'queued_count': counts.get(JobStatus.QUEUED, 0),
            'running_count': counts.get(JobStatus.RUNNING, 0),
            'completed_count': counts.get(JobStatus.COMPLETED, 0),
            'failed_count': counts.get(JobStatus.FAILED, 0),
            'cancelled_count': counts.get(JobStatus.CANCELLED, 0),
            'interrupted_count': counts.get(JobStatus.INTERRUPTED, 0),
            'stuck_count': stuck_count,
            'recent_failed_24h': recent_failed,
            'oldest_queued_seconds': round(oldest_queued_seconds, 1),
            'max_concurrent_scans': config.MAX_CONCURRENT_SCANS,
            'max_queued_jobs': config.MAX_QUEUED_JOBS,
        }


# ─── تنظيف السجلات القديمة (Retention Cleanup) ───────────────────────────────

def cleanup_completed_jobs(retention_days: Optional[int] = None) -> int:
    """
    حذف سجلات المهام المكتملة أو الملغاة أو الفاشلة القديمة لإدارة نمو قاعدة البيانات.
    يُعيد عدد السجلات المحذوفة.
    """
    days = retention_days or config.JOB_RETENTION_DAYS
    cutoff = _utcnow() - timedelta(days=days)

    with base_repo.get_session() as session:
        deleted = session.query(JobRecord).filter(
            JobRecord.status.in_([JobStatus.COMPLETED, JobStatus.CANCELLED, JobStatus.FAILED]),
            JobRecord.finished_at < cutoff
        ).delete(synchronize_session=False)

        if deleted > 0:
            session.commit()
            logger.info(f"تم تنظيف {deleted} سجل مهام قديم تجاوزت {days} يوماً.")
        return deleted


# ─── دوال مساعدة داخلية ──────────────────────────────────────────────────────

def _job_to_dict(job: JobRecord) -> Dict[str, Any]:
    """تحويل سجل المهمة إلى قاموس معقم للعرض."""
    payload = {}
    result = {}
    try:
        if job.payload_json:
            payload = json.loads(job.payload_json)
    except Exception:
        pass
    try:
        if job.result_json:
            result = json.loads(job.result_json)
    except Exception:
        pass

    return {
        'id': job.id,
        'job_type': job.job_type,
        'job_type_label': JOB_TYPE_LABELS_AR.get(job.job_type, job.job_type),
        'status': job.status,
        'status_label': JOB_STATUS_LABELS_AR.get(job.status, job.status),
        'priority': job.priority,
        'queued_at': job.queued_at.isoformat() if job.queued_at else None,
        'started_at': job.started_at.isoformat() if job.started_at else None,
        'finished_at': job.finished_at.isoformat() if job.finished_at else None,
        'heartbeat_at': job.heartbeat_at.isoformat() if job.heartbeat_at else None,
        'retry_at': job.retry_at.isoformat() if job.retry_at else None,
        'requested_by': job.requested_by,
        'worker_pid': job.worker_pid,
        'lease_token': job.lease_token,
        'progress': job.progress,
        'stage': job.stage,
        'cancel_requested': bool(job.cancel_requested),
        'attempt_count': job.attempt_count,
        'max_attempts': job.max_attempts,
        'error_code': job.error_code,
        'safe_error_message': job.safe_error_message,
        'research_id': job.research_id,
        'batch_id': job.batch_id,
        'batch_item_id': job.batch_item_id,
        'report_id': job.report_id,
        'scan_execution_id': job.scan_execution_id,
        'target_corpus_version': job.target_corpus_version,
        'payload': payload,
        'result': result,
    }
