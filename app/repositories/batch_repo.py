# -*- coding: utf-8 -*-
"""
مستودع بيانات الرسائل والدفعات الأكاديمية (Research & Batch Repository):
- إنشاء وإدارة كيانات Research وResearchFile.
- إنشاء وإدارة ScanBatch وScanBatchItem.
- استرجاع حالة الدفعة الكاملة للعرض في الواجهة.
"""

import uuid
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import desc

from app.repositories.base_repo import get_session
from app.models.research_schema import Research, ResearchFile, ScanBatch, ScanBatchItem

logger = logging.getLogger(__name__)


# ─── Research ─────────────────────────────────────────────────────────────────

def create_research(
    title: str,
    author: str = '',
    specialization: str = '',
    degree_type: str = '',
    created_by: str = '',
    batch_id: Optional[str] = None
) -> int:
    """إنشاء كيان رسالة/بحث جديد. يُعيد research_id."""
    with get_session() as session:
        res = Research(
            title=title,
            author=author,
            specialization=specialization,
            degree_type=degree_type,
            created_by=created_by,
            batch_id=batch_id
        )
        session.add(res)
        session.flush()
        return res.id


def add_research_file(
    research_id: int,
    original_filename: str,
    stored_filename: str,
    file_path: str,
    file_type: str,
    file_size_bytes: int,
    file_order: int,
    file_hash: str = ''
) -> int:
    """إضافة ملف لرسالة. يُعيد file_id."""
    with get_session() as session:
        rf = ResearchFile(
            research_id=research_id,
            original_filename=original_filename,
            stored_filename=stored_filename,
            file_path=file_path,
            file_type=file_type,
            file_size_bytes=file_size_bytes,
            file_order=file_order,
            file_hash=file_hash
        )
        session.add(rf)
        session.flush()
        return rf.id


def update_research_scan(research_id: int, scan_job_id: str, report_id: Optional[str] = None):
    """ربط الرسالة بمهمة الفحص والتقرير."""
    with get_session() as session:
        res = session.query(Research).filter(Research.id == research_id).first()
        if res:
            res.scan_job_id = scan_job_id
            if report_id:
                res.report_id = report_id


def get_research(research_id: int) -> Optional[dict]:
    """استرجاع بيانات رسالة مع ملفاتها."""
    with get_session() as session:
        res = session.query(Research).filter(Research.id == research_id).first()
        if not res:
            return None
        return {
            'id': res.id,
            'title': res.title,
            'author': res.author,
            'specialization': res.specialization,
            'degree_type': res.degree_type,
            'created_by': res.created_by,
            'created_at': res.created_at.isoformat() if res.created_at else '',
            'batch_id': res.batch_id,
            'report_id': res.report_id,
            'scan_job_id': res.scan_job_id,
            'files': [
                {
                    'id': f.id,
                    'original_filename': f.original_filename,
                    'file_type': f.file_type,
                    'file_size_bytes': f.file_size_bytes,
                    'file_order': f.file_order,
                    'file_path': f.file_path
                }
                for f in res.files
            ]
        }


def get_research_files_ordered(research_id: int) -> list[dict]:
    """استرجاع ملفات الرسالة مرتبةً حسب file_order."""
    with get_session() as session:
        files = (
            session.query(ResearchFile)
            .filter(ResearchFile.research_id == research_id)
            .order_by(ResearchFile.file_order)
            .all()
        )
        return [
            {
                'id': f.id,
                'original_filename': f.original_filename,
                'stored_filename': f.stored_filename,
                'file_path': f.file_path,
                'file_type': f.file_type,
                'file_size_bytes': f.file_size_bytes,
                'file_order': f.file_order,
                'file_hash': f.file_hash
            }
            for f in files
        ]


def file_hash_exists(file_hash: str) -> bool:
    """التحقق من وجود ملف مكرر بنفس البصمة الرقمية."""
    with get_session() as session:
        return session.query(ResearchFile).filter(ResearchFile.file_hash == file_hash).first() is not None


# ─── ScanBatch ────────────────────────────────────────────────────────────────

def create_batch(created_by: str = '', label: str = '') -> str:
    """إنشاء دفعة فحص جديدة. يُعيد batch_id (UUID)."""
    batch_id = str(uuid.uuid4())[:16]
    with get_session() as session:
        batch = ScanBatch(
            id=batch_id,
            label=label,
            created_by=created_by,
            status='pending',
            total_items=0,
            completed_items=0,
            failed_items=0
        )
        session.add(batch)
    return batch_id


def add_batch_item(batch_id: str, research_id: int, item_order: int = 0) -> int:
    """إضافة عنصر إلى دفعة فحص. يُعيد item_id."""
    with get_session() as session:
        item = ScanBatchItem(
            batch_id=batch_id,
            research_id=research_id,
            item_order=item_order,
            status='queued',
            progress=0
        )
        session.add(item)
        session.flush()

        # تحديث عداد الدفعة
        batch = session.query(ScanBatch).filter(ScanBatch.id == batch_id).first()
        if batch:
            batch.total_items = (batch.total_items or 0) + 1
        return item.id


def update_batch_item(
    batch_id: str,
    research_id: int,
    status: str,
    progress: int = 0,
    scan_job_id: Optional[str] = None,
    report_id: Optional[str] = None,
    error_message: str = '',
    similarity_pct: Optional[float] = None
):
    """تحديث حالة عنصر في الدفعة وتحديث عدادات الدفعة تلقائياً."""
    with get_session() as session:
        item = session.query(ScanBatchItem).filter(
            ScanBatchItem.batch_id == batch_id,
            ScanBatchItem.research_id == research_id
        ).first()
        if not item:
            return

        old_status = item.status
        item.status = status
        item.progress = progress
        if scan_job_id:
            item.scan_job_id = scan_job_id
        if report_id:
            item.report_id = report_id
        if error_message:
            item.error_message = error_message
        if similarity_pct is not None:
            item.similarity_pct = similarity_pct
        if status in ('completed', 'error'):
            item.completed_at = datetime.utcnow()

        # تحديث عدادات الدفعة
        batch = session.query(ScanBatch).filter(ScanBatch.id == batch_id).first()
        if batch:
            if status == 'completed' and old_status != 'completed':
                batch.completed_items = (batch.completed_items or 0) + 1
            if status == 'error' and old_status != 'error':
                batch.failed_items = (batch.failed_items or 0) + 1

            # تحديد الحالة الإجمالية للدفعة
            total = batch.total_items or 0
            done = (batch.completed_items or 0) + (batch.failed_items or 0)
            if done >= total > 0:
                if (batch.failed_items or 0) > 0 and (batch.completed_items or 0) > 0:
                    batch.status = 'partial'
                elif (batch.failed_items or 0) >= total:
                    batch.status = 'error'
                else:
                    batch.status = 'completed'
            elif status == 'running':
                batch.status = 'running'


def start_batch(batch_id: str):
    """تحديث حالة الدفعة إلى running."""
    with get_session() as session:
        batch = session.query(ScanBatch).filter(ScanBatch.id == batch_id).first()
        if batch:
            batch.status = 'running'


def get_batch(batch_id: str) -> Optional[dict]:
    """استرجاع كامل بيانات الدفعة مع عناصرها."""
    with get_session() as session:
        batch = session.query(ScanBatch).filter(ScanBatch.id == batch_id).first()
        if not batch:
            return None

        items = []
        for item in batch.items:
            research = session.query(Research).filter(Research.id == item.research_id).first()
            
            # Use actual stored Research.title, or original filename without extension as fallback
            res_title = ''
            if research and research.title and research.title.strip():
                res_title = research.title.strip()
            elif research and research.files:
                import os
                res_title = os.path.splitext(research.files[0].original_filename)[0]

            res_author = research.author if (research and research.author) else ''

            items.append({
                'id': item.id,
                'research_id': item.research_id,
                'research_title': res_title,
                'research_author': res_author,
                'scan_job_id': item.scan_job_id,
                'report_id': item.report_id,
                'item_order': item.item_order,
                'status': item.status,
                'progress': item.progress,
                'error_message': item.error_message,
                'similarity_pct': item.similarity_pct,
                'completed_at': item.completed_at.isoformat() if item.completed_at else None
            })

        return {
            'id': batch.id,
            'label': batch.label,
            'created_by': batch.created_by,
            'created_at': batch.created_at.isoformat() if batch.created_at else '',
            'status': batch.status,
            'total_items': batch.total_items,
            'completed_items': batch.completed_items,
            'failed_items': batch.failed_items,
            'items': items
        }


def get_batch_item_report_id(batch_id: str, research_id: int) -> Optional[str]:
    """استرجاع report_id لعنصر محدد في الدفعة."""
    with get_session() as session:
        item = session.query(ScanBatchItem).filter(
            ScanBatchItem.batch_id == batch_id,
            ScanBatchItem.research_id == research_id
        ).first()
        return item.report_id if item else None


def get_recent_batches(limit: int = 10) -> list[dict]:
    """استرجاع أحدث الدفعات للعرض في لوحة التحكم."""
    with get_session() as session:
        batches = (
            session.query(ScanBatch)
            .order_by(desc(ScanBatch.created_at))
            .limit(limit)
            .all()
        )
        return [
            {
                'id': b.id,
                'label': b.label,
                'status': b.status,
                'total_items': b.total_items,
                'completed_items': b.completed_items,
                'failed_items': b.failed_items,
                'created_at': b.created_at.isoformat() if b.created_at else ''
            }
            for b in batches
        ]
