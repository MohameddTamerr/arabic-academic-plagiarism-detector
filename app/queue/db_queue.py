# -*- coding: utf-8 -*-
"""
تطبيق طابور المهام الموزع الدائم في قاعدة البيانات (Database-Backed Persistent Job Queue):
- استحواذ ذري آمن على المهام بنظام بطاقات الأمان claim_token وعقود الإيجار.
- جدولة منضبطة بالأولوية وعدالة الأقسام لمنع احتكار الطابور.
- استعادة تلقائية للمهام المنقطعة نتيجة انهيار العمال.
- تنقية وإخفاء البيانات الحساسة وكلمات المرور من رسائل الأخطاء.
"""

import os
import json
import uuid
import re
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List, Set

from sqlalchemy import or_, and_, text
from app.queue.base import JobQueueBackend
from app.models.queue_schema import QueueJob, WorkerRegistry
from app.repositories import base_repo
import config

logger = logging.getLogger(__name__)

# حقول وكلمات حساسة للتنقية
_SENSITIVE_PATTERNS = [
    re.compile(r'password=([^\s;]+)', re.IGNORECASE),
    re.compile(r'postgresql://([^:]+):([^@]+)@', re.IGNORECASE),
    re.compile(r'[a-zA-Z]:\\[^\s"\']+', re.IGNORECASE), # مسارات ويندوز المطلقة
]


def redact_error_message(msg: str) -> str:
    """تنقية رسالة الخطأ من أي بيانات اعتماد أو مسارات حساسة."""
    if not msg:
        return ""
    cleaned = str(msg)
    for p in _SENSITIVE_PATTERNS:
        cleaned = p.sub('[REDACTED]', cleaned)
    return cleaned[:500]


class DatabaseJobQueue(JobQueueBackend):
    """طابور مهام دائم يعتمد على طبقة قاعدة البيانات المعاملاتية."""

    def __init__(self):
        self._claims_paused = False
        base_repo.init_db()

    def is_paused(self) -> bool:
        return self._claims_paused

    def pause_claims(self) -> None:
        self._claims_paused = True
        logger.info("تم تفعيل إيقاف سحب المهام مؤقتاً (Queue Claims Paused).")

    def resume_claims(self) -> None:
        self._claims_paused = False
        logger.info("تم استئناف سحب المهام بنجاح (Queue Claims Resumed).")

    def enqueue(
        self,
        job_type: str,
        payload: Optional[Dict[str, Any]] = None,
        priority: int = 3,
        research_id: Optional[int] = None,
        batch_id: Optional[str] = None,
        department_id: Optional[str] = None,
        delay_seconds: int = 0
    ) -> str:
        """إدراج مهمة جديدة في الطابور الدائم."""
        job_id = f"job_{uuid.uuid4().hex[:16]}"
        now_dt = datetime.now(timezone.utc)
        avail_dt = now_dt + timedelta(seconds=max(0, delay_seconds))

        payload_str = json.dumps(payload or {}, ensure_ascii=False)

        with base_repo.get_session() as session:
            job = QueueJob(
                id=job_id,
                job_type=job_type,
                status='queued',
                priority=max(1, min(5, priority)),
                department_id=str(department_id) if department_id else None,
                research_id=research_id,
                batch_id=str(batch_id) if batch_id else None,
                payload_json=payload_str,
                attempt_count=0,
                max_attempts=getattr(config, 'QUEUE_MAX_ATTEMPTS', 3),
                created_at=now_dt,
                available_at=avail_dt,
                worker_protocol_version='1.3.0'
            )
            session.add(job)
            session.commit()

        logger.debug(f"تم إدراج المهمة {job_id} في الطابور بنجاح (نوع: {job_type}، أولوية: {priority}).")
        return job_id

    def claim(
        self,
        worker_id: str,
        capabilities: List[str],
        lease_seconds: int = 60,
        max_jobs: int = 1
    ) -> List[Dict[str, Any]]:
        """الاستحواذ الذري المعاملاتي على المهام الجاهزة."""
        if self._claims_paused:
            return []

        now_dt = datetime.now(timezone.utc)
        claimed_jobs = []

        with base_repo.get_session() as session:
            # استعلام المهام المتاحة وفق الأولوية والتاريخ
            query = session.query(QueueJob).filter(
                QueueJob.status == 'queued',
                QueueJob.available_at <= now_dt,
                QueueJob.job_type.in_(capabilities)
            ).order_by(QueueJob.priority.asc(), QueueJob.created_at.asc())

            # فحص عدالة الأقسام: حصر الأقسام النشطة
            active_dept_counts = {}
            active_jobs = session.query(QueueJob.department_id).filter(
                QueueJob.status == 'processing',
                QueueJob.department_id.isnot(None)
            ).all()
            for row in active_jobs:
                d = row[0]
                active_dept_counts[d] = active_dept_counts.get(d, 0) + 1

            candidates = query.limit(max_jobs * 10).all()
            
            # ضمان عدالة الأقسام: إذا كانت كل العينات الأولية من قسم واحد، جلب عينات من الأقسام الأخرى
            candidate_depts = {c.department_id for c in candidates if c.department_id}
            if len(candidate_depts) == 1:
                other_candidates = session.query(QueueJob).filter(
                    QueueJob.status == 'queued',
                    QueueJob.available_at <= now_dt,
                    QueueJob.job_type.in_(capabilities),
                    ~QueueJob.department_id.in_(candidate_depts)
                ).order_by(QueueJob.priority.asc(), QueueJob.created_at.asc()).limit(max_jobs * 5).all()
                if other_candidates:
                    candidates.extend(other_candidates)
                    
            # توزيع عادل متناوب بين الأقسام (Round-Robin Interleaving)
            dept_buckets = {}
            for j in candidates:
                dept_buckets.setdefault(j.department_id or "default", []).append(j)
            
            interleaved = []
            max_len = max(len(b) for b in dept_buckets.values()) if dept_buckets else 0
            for i in range(max_len):
                for d, bucket in dept_buckets.items():
                    if i < len(bucket):
                        interleaved.append(bucket[i])
            candidates = interleaved

            for job in candidates:
                # التحقق من سقف القسم (إن وجد وكانت هناك مهام لأقسام أخرى)
                if job.department_id and active_dept_counts.get(job.department_id, 0) >= 5 and len(candidates) > 1:
                    continue

                token = uuid.uuid4().hex
                lease_end = now_dt + timedelta(seconds=lease_seconds)

                # تحديث ذري شرطي يضمن استحواذاً حصرياً آمناً
                updated_rows = session.query(QueueJob).filter(
                    QueueJob.id == job.id,
                    QueueJob.status == 'queued'
                ).update({
                    QueueJob.status: 'processing',
                    QueueJob.claimed_by: worker_id,
                    QueueJob.claim_token: token,
                    QueueJob.started_at: now_dt,
                    QueueJob.last_heartbeat_at: now_dt,
                    QueueJob.lease_expires_at: lease_end,
                    QueueJob.attempt_count: QueueJob.attempt_count + 1
                }, synchronize_session=False)

                if updated_rows > 0:
                    claimed_jobs.append({
                        'id': job.id,
                        'job_type': job.job_type,
                        'priority': job.priority,
                        'research_id': job.research_id,
                        'batch_id': job.batch_id,
                        'department_id': job.department_id,
                        'payload': json.loads(job.payload_json or '{}'),
                        'attempt_count': (job.attempt_count or 0) + 1,
                        'claim_token': token,
                        'lease_expires_at': lease_end.isoformat()
                    })

                if len(claimed_jobs) >= max_jobs:
                    break

            if claimed_jobs:
                session.commit()

        return claimed_jobs

    def heartbeat(self, job_id: str, claim_token: str, extend_seconds: int = 60) -> bool:
        """تمديد عقد إيجار المهمة عبر نبضات القلب الدورية."""
        now_dt = datetime.now(timezone.utc)
        new_lease = now_dt + timedelta(seconds=extend_seconds)

        with base_repo.get_session() as session:
            job = session.query(QueueJob).filter(
                QueueJob.id == job_id,
                QueueJob.claim_token == claim_token,
                QueueJob.status == 'processing'
            ).first()

            if not job:
                return False

            job.last_heartbeat_at = now_dt
            job.lease_expires_at = new_lease
            session.commit()
            return True

    def complete(self, job_id: str, claim_token: str, result_metadata: Optional[Dict[str, Any]] = None) -> bool:
        """اعتماد اكتمال المهمة بنجاح."""
        now_dt = datetime.now(timezone.utc)
        with base_repo.get_session() as session:
            job = session.query(QueueJob).filter(
                QueueJob.id == job_id,
                QueueJob.claim_token == claim_token,
                QueueJob.status == 'processing'
            ).first()

            if not job:
                return False

            job.status = 'completed'
            job.completed_at = now_dt
            job.lease_expires_at = None
            session.commit()
            return True

    def fail(
        self,
        job_id: str,
        claim_token: str,
        error_code: str,
        error_message: str,
        retryable: bool = False,
        backoff_seconds: int = 10
    ) -> bool:
        """تسجيل فشل المهمة وتحديد إمكانية إعادة المحاولة."""
        now_dt = datetime.now(timezone.utc)
        clean_msg = redact_error_message(error_message)

        with base_repo.get_session() as session:
            job = session.query(QueueJob).filter(
                QueueJob.id == job_id,
                QueueJob.claim_token == claim_token,
                QueueJob.status == 'processing'
            ).first()

            if not job:
                return False

            job.error_code = error_code[:100]
            job.error_message_redacted = clean_msg
            job.lease_expires_at = None

            if retryable and job.attempt_count < job.max_attempts:
                job.status = 'retry_waiting'
                job.available_at = now_dt + timedelta(seconds=backoff_seconds * job.attempt_count)
                # إعادة المهمة للحالة الجاهزة بعد انقضاء المهلة
                job.status = 'queued'
            else:
                job.status = 'failed'
                job.completed_at = now_dt

            session.commit()
            return True

    def cancel(self, job_id: str, reason: str = "Admin requested") -> bool:
        """إلغاء مهمة محددة بأمر إداري معتمد."""
        now_dt = datetime.now(timezone.utc)
        with base_repo.get_session() as session:
            job = session.query(QueueJob).filter(QueueJob.id == job_id).first()
            if not job:
                return False

            if job.status in ('completed', 'failed', 'cancelled'):
                return False

            job.status = 'cancelled'
            job.completed_at = now_dt
            job.lease_expires_at = None
            job.error_code = 'ERR_JOB_CANCELLED'
            job.error_message_redacted = redact_error_message(reason)
            session.commit()
            return True

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """استرجاع تفاصيل مهمة محددة."""
        with base_repo.get_session() as session:
            job = session.query(QueueJob).filter(QueueJob.id == job_id).first()
            if not job:
                return None
            return {
                'id': job.id,
                'job_type': job.job_type,
                'status': job.status,
                'priority': job.priority,
                'department_id': job.department_id,
                'research_id': job.research_id,
                'batch_id': job.batch_id,
                'payload': json.loads(job.payload_json or '{}'),
                'attempt_count': job.attempt_count,
                'max_attempts': job.max_attempts,
                'claimed_by': job.claimed_by,
                'created_at': job.created_at.isoformat() if job.created_at else None,
                'started_at': job.started_at.isoformat() if job.started_at else None,
                'completed_at': job.completed_at.isoformat() if job.completed_at else None,
                'error_code': job.error_code,
                'error_message': job.error_message_redacted
            }

    def get_stats(self) -> Dict[str, Any]:
        """استرجاع إحصائيات عمق الطابور وحالات المهام."""
        with base_repo.get_session() as session:
            total = session.query(QueueJob).count()
            queued = session.query(QueueJob).filter(QueueJob.status == 'queued').count()
            processing = session.query(QueueJob).filter(QueueJob.status == 'processing').count()
            completed = session.query(QueueJob).filter(QueueJob.status == 'completed').count()
            failed = session.query(QueueJob).filter(QueueJob.status == 'failed').count()
            cancelled = session.query(QueueJob).filter(QueueJob.status == 'cancelled').count()

            # أقدم مهمة في الانتظار
            oldest_queued = session.query(QueueJob.created_at).filter(
                QueueJob.status == 'queued'
            ).order_by(QueueJob.created_at.asc()).first()

            oldest_age_sec = 0
            if oldest_queued and oldest_queued[0]:
                created_dt = oldest_queued[0]
                if created_dt.tzinfo is None:
                    created_dt = created_dt.replace(tzinfo=timezone.utc)
                oldest_age_sec = int((datetime.now(timezone.utc) - created_dt).total_seconds())

            return {
                'total_jobs': total,
                'queued_count': queued,
                'processing_count': processing,
                'completed_count': completed,
                'failed_count': failed,
                'cancelled_count': cancelled,
                'oldest_queued_age_seconds': max(0, oldest_age_sec),
                'is_paused': self._claims_paused
            }

    def recover_stale_jobs(self, timeout_seconds: int = 60) -> int:
        """استعادة المهام المنتهية عقود إيجارها بسبب انهيار أو انقطاع العمال."""
        now_dt = datetime.now(timezone.utc)
        recovered_count = 0

        with base_repo.get_session() as session:
            stale_jobs = session.query(QueueJob).filter(
                QueueJob.status == 'processing',
                QueueJob.lease_expires_at < now_dt
            ).all()

            for job in stale_jobs:
                recovered_count += 1
                if job.attempt_count < job.max_attempts:
                    job.status = 'queued'
                    job.claimed_by = None
                    job.claim_token = None
                    job.lease_expires_at = None
                    job.available_at = now_dt + timedelta(seconds=5)
                    logger.warning(f"تمت استعادة المهمة المنقطعة {job.id} وإعادتها للطابور (محاولة {job.attempt_count}/{job.max_attempts}).")
                else:
                    job.status = 'failed'
                    job.completed_at = now_dt
                    job.error_code = 'ERR_WORKER_TIMEOUT_EXCEEDED'
                    job.error_message_redacted = 'تجاوزت المهمة الحد الأقصى لمحاولات الاستعادة بعد انقطاع العمال'
                    logger.error(f"فشلت المهمة المنقطعة {job.id} نهائياً لتجاوز عدد المحاولات.")

            if recovered_count > 0:
                session.commit()

        return recovered_count
