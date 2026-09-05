# -*- coding: utf-8 -*-
"""
نماذج قاعدة البيانات لطابور المهام وسجل العمال والأقفال الموزعة (Queue & Worker ORM Schema):
- QueueJob: جدول المهام الدائم الموزع.
- WorkerRegistry: سجل العمال الموزعين وحالاتهم ونبضات قلوبهم.
- DistributedLockRecord: سجل الأقفال الموزعة لمنع تضارب العمليات الأحادية (مثل إعادة بناء الفهرس).
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Float, DateTime, Index, Boolean
)
from app.models.schema import Base


class QueueJob(Base):
    """جدول المهام الموزع الدائم."""
    __tablename__ = 'queue_jobs'

    id = Column(String(64), primary_key=True)
    job_type = Column(String(50), nullable=False, index=True) # SCAN_RESEARCH, OCR_DOCUMENT, INDEX_INCREMENTAL, INDEX_REBUILD, STORAGE_INTEGRITY_SCAN, REPORT_EXPORT
    status = Column(String(50), nullable=False, default='queued', index=True) # queued, processing, retry_waiting, completed, failed, cancelled
    priority = Column(Integer, nullable=False, default=3, index=True) # 1: CRITICAL, 2: INTERACTIVE, 3: NORMAL, 4: BATCH, 5: MAINTENANCE
    department_id = Column(String(64), nullable=True, index=True)
    research_id = Column(Integer, nullable=True, index=True)
    batch_id = Column(String(64), nullable=True, index=True)
    payload_json = Column(Text, nullable=True) # المعايير والبيانات الوصفية
    attempt_count = Column(Integer, default=0)
    max_attempts = Column(Integer, default=3)
    claimed_by = Column(String(128), nullable=True, index=True) # worker_id
    claim_token = Column(String(64), nullable=True)
    lease_expires_at = Column(DateTime, nullable=True, index=True)
    last_heartbeat_at = Column(DateTime, nullable=True)
    available_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_code = Column(String(100), nullable=True)
    error_message_redacted = Column(String(500), nullable=True)
    worker_protocol_version = Column(String(20), default='1.0.0')

    __table_args__ = (
        Index('idx_qjob_status_prio_avail', 'status', 'priority', 'available_at'),
        Index('idx_qjob_claimed_lease', 'claimed_by', 'lease_expires_at'),
        Index('idx_qjob_dept_status', 'department_id', 'status'),
    )


class WorkerRegistry(Base):
    """سجل العمال الموزعين النشطين ونبضات حياتهم وإمكانياتهم."""
    __tablename__ = 'worker_registry'

    id = Column(String(128), primary_key=True) # worker_id
    hostname = Column(String(255), nullable=False)
    pid = Column(Integer, nullable=False)
    capabilities = Column(String(255), nullable=False) # SCAN,OCR,INDEX_BUILD,EXPORT
    status = Column(String(50), nullable=False, default='ONLINE') # ONLINE, BUSY, DRAINING, OFFLINE
    active_jobs_count = Column(Integer, default=0)
    started_at = Column(DateTime, default=datetime.utcnow)
    last_heartbeat_at = Column(DateTime, default=datetime.utcnow, index=True)
    worker_version = Column(String(50), default='1.3.0')


class DistributedLockRecord(Base):
    """سجل الأقفال الموزعة للعمليات الأحادية (مثل إعادة بناء الفهرس)."""
    __tablename__ = 'distributed_locks'

    lock_name = Column(String(128), primary_key=True)
    owner_token = Column(String(128), nullable=False)
    acquired_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False, index=True)
