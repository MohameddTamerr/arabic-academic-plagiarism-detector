# -*- coding: utf-8 -*-
"""
مشغل عامل المعالجة الموزع المستقل (Standalone Distributed Worker Daemon CLI):
- يقوم بتسجيل هوية العامل في سجل العمال (WorkerRegistry).
- ينفذ حلقة المعالجة: سحب المهام الذري -> التنفيذ -> نبضات القلب -> الاعتماد.
- يدعم وضع التجفيف (Drain Mode) والإغلاق السلس (Graceful Shutdown) عند استلام إشارات الإيقاف.
- يدعم توجيه الإمكانيات المخصصة (SCAN, OCR, INDEX_BUILD, EXPORT).
"""

import os
import sys
import time
import uuid
import signal
import socket
import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.queue.db_queue import DatabaseJobQueue
from app.models.queue_schema import WorkerRegistry
from app.repositories import base_repo

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] [Worker] %(message)s'
)
logger = logging.getLogger("worker_daemon")


class WorkerProcess:
    """معالج تشغيل العامل الموزع المستقل."""

    def __init__(
        self,
        capabilities: List[str],
        heartbeat_interval: int = 10,
        lease_seconds: int = 60,
        worker_id: Optional[str] = None
    ):
        self.hostname = socket.gethostname()
        self.pid = os.getpid()
        self.boot_token = uuid.uuid4().hex[:8]
        self.worker_id = worker_id or f"{self.hostname}_{self.pid}_{self.boot_token}"
        self.capabilities = [c.strip().upper() for c in capabilities if c.strip()]
        self.heartbeat_interval = heartbeat_interval
        self.lease_seconds = lease_seconds
        
        self.queue = DatabaseJobQueue()
        self.is_running = False
        self.is_draining = False
        self.active_jobs = 0

    def register(self) -> None:
        """تسجيل العامل في قاعدة البيانات المشتركة."""
        now_dt = datetime.now(timezone.utc)
        cap_str = ",".join(self.capabilities)
        with base_repo.get_session() as session:
            existing = session.query(WorkerRegistry).filter(WorkerRegistry.id == self.worker_id).first()
            if existing:
                existing.status = 'ONLINE'
                existing.last_heartbeat_at = now_dt
                existing.active_jobs_count = 0
            else:
                w = WorkerRegistry(
                    id=self.worker_id,
                    hostname=self.hostname,
                    pid=self.pid,
                    capabilities=cap_str,
                    status='ONLINE',
                    active_jobs_count=0,
                    started_at=now_dt,
                    last_heartbeat_at=now_dt,
                    worker_version='1.3.0'
                )
                session.add(w)
            session.commit()
        logger.info(f"تم تسجيل العامل {self.worker_id} بنجاح (الإمكانيات: {cap_str}).")

    def heartbeat(self) -> None:
        """إرسال نبضة حياة لسجل العمال."""
        now_dt = datetime.now(timezone.utc)
        try:
            with base_repo.get_session() as session:
                w = session.query(WorkerRegistry).filter(WorkerRegistry.id == self.worker_id).first()
                if w:
                    w.last_heartbeat_at = now_dt
                    w.status = 'DRAINING' if self.is_draining else ('BUSY' if self.active_jobs > 0 else 'ONLINE')
                    w.active_jobs_count = self.active_jobs
                    session.commit()
        except Exception as e:
            logger.warning(f"تعذر إرسال نبضة حياة العامل: {e}")

    def deregister(self) -> None:
        """إلغاء تسجيل العامل عند الإغلاق."""
        try:
            with base_repo.get_session() as session:
                w = session.query(WorkerRegistry).filter(WorkerRegistry.id == self.worker_id).first()
                if w:
                    w.status = 'OFFLINE'
                    session.commit()
            logger.info(f"تم تسجيل خروج العامل {self.worker_id} بنجاح.")
        except Exception:
            pass

    def handle_signal(self, signum, frame):
        """التعامل مع إشارات الإيقاف وتفعيل وضع التجفيف."""
        logger.info(f"تم استلام إشارة إيقاف ({signum}). تفعيل وضع التجفيف (Draining)...")
        self.is_draining = True

    def process_job(self, job_dict: dict) -> None:
        """معالجة مهمة مستحوذ عليها."""
        job_id = job_dict['id']
        job_type = job_dict['job_type']
        token = job_dict['claim_token']
        self.active_jobs += 1
        logger.info(f"بدء تنفيذ المهمة {job_id} (نوع: {job_type})...")

        try:
            # محاكاة التنفيذ أو الربط مع محرك الفحص
            if job_type in ('SCAN_RESEARCH', 'SCAN'):
                # فحص البحث الأكاديمي
                time.sleep(0.05) # معالجة سريعة
            elif job_type in ('OCR_DOCUMENT', 'OCR'):
                time.sleep(0.05)
            elif job_type in ('INDEX_REBUILD', 'INDEX_INCREMENTAL'):
                time.sleep(0.05)
            else:
                time.sleep(0.02)

            self.queue.complete(job_id, token)
            logger.info(f"اكتملت المهمة {job_id} بنجاح.")
        except Exception as e:
            logger.error(f"فشلت المهمة {job_id}: {e}", exc_info=True)
            self.queue.fail(job_id, token, error_code="ERR_EXECUTION_FAILED", error_message=str(e), retryable=True)
        finally:
            self.active_jobs = max(0, self.active_jobs - 1)

    def run(self, max_iterations: Optional[int] = None, idle_timeout_seconds: Optional[float] = None) -> None:
        """حلقة العمل الرئيسية للعامل."""
        signal.signal(signal.SIGINT, self.handle_signal)
        signal.signal(signal.SIGTERM, self.handle_signal)

        self.register()
        self.is_running = True
        last_hb = time.time()
        last_active = time.time()
        iterations = 0

        try:
            while self.is_running:
                if max_iterations and iterations >= max_iterations:
                    break

                # نبضات القلب الدورية
                if time.time() - last_hb >= self.heartbeat_interval:
                    self.heartbeat()
                    last_hb = time.time()

                if self.is_draining and self.active_jobs == 0:
                    logger.info("اكتمل تجفيف المهام. إيقاف العامل بأمان.")
                    break

                if not self.is_draining:
                    claimed = self.queue.claim(
                        worker_id=self.worker_id,
                        capabilities=self.capabilities,
                        lease_seconds=self.lease_seconds,
                        max_jobs=1
                    )
                    if claimed:
                        last_active = time.time()
                        for job in claimed:
                            self.process_job(job)
                            iterations += 1
                    else:
                        if idle_timeout_seconds and (time.time() - last_active >= idle_timeout_seconds):
                            logger.info(f"انتهت مهلة الخمول ({idle_timeout_seconds}s). إيقاف العامل بأمان.")
                            break
                        time.sleep(0.02)
                else:
                    time.sleep(0.02)

        finally:
            self.deregister()


def main():
    parser = argparse.ArgumentParser(description="مشغل عامل المعالجة الموزع المستقل")
    parser.add_argument("--capabilities", type=str, default="SCAN,OCR,INDEX_BUILD,EXPORT,STORAGE_INTEGRITY_SCAN", help="الإمكانيات مفصولة بفاصلة")
    parser.add_argument("--heartbeat-interval", type=int, default=5, help="فترة نبضات القلب بالثواني")
    parser.add_argument("--lease-seconds", type=int, default=30, help="مدة عقد الإيجار بالثواني")
    parser.add_argument("--worker-id", type=str, default=None, help="معرف مخصص للعامل")
    args = parser.parse_args()

    caps = args.capabilities.split(",")
    worker = WorkerProcess(
        capabilities=caps,
        heartbeat_interval=args.heartbeat_interval,
        lease_seconds=args.lease_seconds,
        worker_id=args.worker_id
    )
    worker.run()


if __name__ == '__main__':
    main()
