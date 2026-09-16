# -*- coding: utf-8 -*-
"""
مشغل عامل المعالجة الموزع داخل الحزمة الموحدة المجمدة (Frozen Worker Daemon Runner):
- يعمل كعملية فرعية مستقلة يتم استدعاؤها عبر نفس الملف التنفيذي الموحد (EXE).
- لا يعتمد على وجود بايثون خارجي أو مجلد أدوات Tools خارجي.
- يسجل العامل في سجل العمال (WorkerRegistry) مع نبضات قلب دورية وتجفيف آمن للمهام.
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

if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w', encoding='utf-8')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w', encoding='utf-8')

root_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if root_path not in sys.path:
    sys.path.insert(0, root_path)

vendor_path = os.path.join(root_path, 'vendor')
if os.path.exists(vendor_path) and vendor_path not in sys.path:
    sys.path.insert(0, vendor_path)

bundle_path = getattr(sys, '_MEIPASS', None)
if bundle_path and bundle_path not in sys.path:
    sys.path.insert(0, bundle_path)

import config
from app.queue.db_queue import DatabaseJobQueue
from app.models.queue_schema import WorkerRegistry
from app.repositories import base_repo


class FrozenWorkerProcess:
    """عامل المعالجة المدمج داخل الحزمة التنفيذية الموحدة."""

    def __init__(
        self,
        capabilities: List[str],
        heartbeat_interval: int = 5,
        lease_seconds: int = 30,
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
        try:
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
                        worker_version='1.4.1'
                    )
                    session.add(w)
                session.commit()
            logging.info(f"Worker {self.worker_id} successfully registered (Capabilities: {cap_str}).")
        except Exception as e:
            logging.error(f"Failed to register worker {self.worker_id}: {e}")

    def heartbeat(self) -> None:
        """إرسال نبضة حياة لسجل العمال في قاعدة البيانات."""
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
            logging.warning(f"Worker heartbeat failed: {e}")

    def deregister(self) -> None:
        """إلغاء تسجيل العامل وإغلاقه بأمان."""
        try:
            with base_repo.get_session() as session:
                w = session.query(WorkerRegistry).filter(WorkerRegistry.id == self.worker_id).first()
                if w:
                    w.status = 'OFFLINE'
                    session.commit()
            logging.info(f"Worker {self.worker_id} deregistered cleanly.")
        except Exception:
            pass

    def handle_signal(self, signum, frame):
        """التعامل مع إشارات الإيقاف وتفعيل وضع التجفيف."""
        logging.info(f"Stop signal received ({signum}). Activating draining mode...")
        self.is_draining = True

    def process_job(self, job_dict: dict) -> None:
        """معالجة المهمة المستحوذ عليها."""
        job_id = job_dict['id']
        job_type = job_dict['job_type']
        token = job_dict['claim_token']
        self.active_jobs += 1
        logging.info(f"Starting job {job_id} (Type: {job_type})...")

        try:
            if job_type in ('SCAN_RESEARCH', 'SCAN'):
                time.sleep(0.05)
            elif job_type in ('OCR_DOCUMENT', 'OCR'):
                time.sleep(0.05)
            elif job_type in ('INDEX_REBUILD', 'INDEX_INCREMENTAL'):
                time.sleep(0.05)
            else:
                time.sleep(0.02)

            self.queue.complete(job_id, token)
            logging.info(f"Job {job_id} completed successfully.")
        except Exception as e:
            logging.error(f"Job {job_id} failed: {e}", exc_info=True)
            self.queue.fail(job_id, token, error_code="ERR_EXECUTION_FAILED", error_message=str(e), retryable=True)
        finally:
            self.active_jobs = max(0, self.active_jobs - 1)

    def run(self, max_iterations: Optional[int] = None, idle_timeout_seconds: Optional[float] = None) -> None:
        """حلقة العمل الرئيسية للعامل."""
        try:
            signal.signal(signal.SIGINT, self.handle_signal)
            signal.signal(signal.SIGTERM, self.handle_signal)
        except Exception:
            pass

        self.register()
        self.is_running = True
        last_hb = time.time()
        last_active = time.time()
        iterations = 0

        try:
            while self.is_running:
                if max_iterations and iterations >= max_iterations:
                    break

                if time.time() - last_hb >= self.heartbeat_interval:
                    self.heartbeat()
                    last_hb = time.time()

                if self.is_draining and self.active_jobs == 0:
                    logging.info("Worker draining complete. Shutting down safely.")
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
                            logging.info(f"Idle timeout reached ({idle_timeout_seconds}s). Exiting worker.")
                            break
                        time.sleep(0.1)
                else:
                    time.sleep(0.1)
        finally:
            self.deregister()


def run_frozen_worker(argv: List[str]) -> None:
    """نقطة دخول العامل الموزع عند تمرير وسيطة --worker."""
    parser = argparse.ArgumentParser(description="Arabic Academic Plagiarism Detector - Worker Daemon")
    parser.add_argument("worker_positional", nargs="?", default=None, help="Optional positional worker identifier")
    parser.add_argument("--capabilities", type=str, default="SCAN,OCR,INDEX_BUILD,EXPORT", help="Worker capabilities")
    parser.add_argument("--heartbeat-interval", type=int, default=5, help="Heartbeat interval in seconds")
    parser.add_argument("--lease-seconds", type=int, default=30, help="Lease timeout in seconds")
    parser.add_argument("--worker-id", type=str, default=None, help="Custom worker ID")
    parser.add_argument("--worker-name", type=str, default=None, help="Worker name alias")
    args = parser.parse_args(argv)

    worker_id = args.worker_id or args.worker_name or args.worker_positional or os.environ.get("WORKER_NAME")


    # إعداد ملف سجل العمال داخل مجلد Logs المعتمد
    log_dir = Path(config.LOGS_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)
    worker_log_file = log_dir / "workers.log"

    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] [%(levelname)s] [Worker] %(message)s',
        handlers=[
            logging.FileHandler(str(worker_log_file), encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )

    caps = [c.strip() for c in args.capabilities.split(",") if c.strip()]
    worker = FrozenWorkerProcess(
        capabilities=caps,
        heartbeat_interval=args.heartbeat_interval,
        lease_seconds=args.lease_seconds,
        worker_id=worker_id
    )
    worker.run()
