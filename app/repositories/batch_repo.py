# -*- coding: utf-8 -*-
"""
مستودع بيانات الرسائل والدفعات الأكاديمية (Research & Batch Repository):
- إنشاء وإدارة كيانات Research وResearchFile.
- إنشاء وإدارة ScanBatch وScanBatchItem.
- استرجاع حالة الدفعة الكاملة للعرض في الواجهة.
"""

import re
import uuid
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import desc

from app.repositories.base_repo import get_session
from app.models.research_schema import Research, ResearchFile, ScanBatch, ScanBatchItem
from app.workflow.statuses import (
    ScanStatus, ReviewStatus, SCAN_STATUS_LABELS_AR, REVIEW_STATUS_LABELS_AR,
    validate_scan_transition, validate_review_transition
)

logger = logging.getLogger(__name__)


# ─── Research ─────────────────────────────────────────────────────────────────

def create_research(
    title: str,
    author: str = '',
    specialization: str = '',
    degree_type: str = '',
    created_by: str = '',
    batch_id: Optional[str] = None,
    reference_number: Optional[str] = None,
    scan_status: str = 'queued',
    review_status: str = 'pending_review'
) -> int:
    """إنشاء كيان رسالة/بحث جديد وتعيين رقم مرجعي وحالتي الفحص والتحكيم. يُعيد research_id."""
    from app.services import reference_service
    with get_session() as session:
        if not reference_number:
            reference_number = reference_service.get_next_research_reference()

        res = Research(
            reference_number=reference_number,
            title=title,
            author=author,
            specialization=specialization,
            degree_type=degree_type,
            created_by=created_by,
            batch_id=batch_id,
            scan_status=scan_status,
            review_status=review_status
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
    file_hash: str = '',
    storage_status: str = 'finalized'
) -> int:
    """إضافة ملف لرسالة مع تحديد حالة التخزين (finalized / registry_only). يُعيد file_id."""
    with get_session() as session:
        rf = ResearchFile(
            research_id=research_id,
            original_filename=original_filename,
            stored_filename=stored_filename,
            file_path=file_path,
            file_type=file_type,
            file_size_bytes=file_size_bytes,
            file_order=file_order,
            file_hash=file_hash,
            storage_status=storage_status
        )
        session.add(rf)
        session.flush()
        return rf.id


def update_research_scan(research_id: int, scan_job_id: str, report_id: Optional[str] = None):
    """ربط الرسالة بمهمة الفحص وتحديث حالتها التقنية كـ completed."""
    with get_session() as session:
        res = session.query(Research).filter(Research.id == research_id).first()
        if res:
            res.scan_job_id = scan_job_id
            if report_id:
                res.report_id = report_id
                res.scan_status = ScanStatus.COMPLETED.value


def update_research_scan_status(research_id: int, new_status: str) -> bool:
    """تحديث الحالة التقنية للفحص مع التحقق من صحة الانتقال."""
    with get_session() as session:
        res = session.query(Research).filter(Research.id == research_id).first()
        if not res:
            return False
        if not validate_scan_transition(res.scan_status, new_status):
            logger.warning(f"انتقال تقني غير قانوني للبحث {research_id}: {res.scan_status} -> {new_status}")
            return False
        res.scan_status = new_status
        return True


def update_research_review_status(research_id: int, new_status: str) -> bool:
    """تحديث الحالة الإجرائية للتحكيم الأكاديمي مع التحقق من صحة الانتقال."""
    with get_session() as session:
        res = session.query(Research).filter(Research.id == research_id).first()
        if not res:
            return False
        if not validate_review_transition(res.review_status, new_status):
            logger.warning(f"انتقال تحكيمي غير قانوني للبحث {research_id}: {res.review_status} -> {new_status}")
            return False
        res.review_status = new_status
        return True


def get_research(research_id: int) -> Optional[dict]:
    """استرجاع بيانات رسالة مع ملفاتها ورقمها المرجعي وحالتي الفحص والتحكيم."""
    with get_session() as session:
        res = session.query(Research).filter(Research.id == research_id).first()
        if not res:
            return None
        s_stat = res.scan_status or 'queued'
        r_stat = res.review_status or 'pending_review'
        return {
            'id': res.id,
            'reference_number': res.reference_number or '',
            'title': res.title,
            'author': res.author,
            'specialization': res.specialization,
            'degree_type': res.degree_type,
            'created_by': res.created_by,
            'created_at': res.created_at.isoformat() if res.created_at else '',
            'batch_id': res.batch_id,
            'report_id': res.report_id,
            'scan_job_id': res.scan_job_id,
            'scan_status': s_stat,
            'review_status': r_stat,
            'scan_status_label': SCAN_STATUS_LABELS_AR.get(s_stat, s_stat),
            'review_status_label': REVIEW_STATUS_LABELS_AR.get(r_stat, r_stat),
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


def get_research_by_reference(reference_number: str) -> Optional[dict]:
    """استرجاع بيانات البحث عبر الرقم المرجعي الرسمي الفريد."""
    if not reference_number:
        return None
    clean_ref = reference_number.strip().upper()
    with get_session() as session:
        res = session.query(Research).filter(Research.reference_number == clean_ref).first()
        if not res:
            return None
        return get_research(res.id)


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


def get_research_by_file_hash(file_hash: str) -> Optional[dict]:
    """استرجاع أول بحث مطابق للبصمة الرقمية مع بيانات التقرير والرقم المرجعي."""
    if not file_hash:
        return None
    with get_session() as session:
        rf = (
            session.query(ResearchFile)
            .filter(ResearchFile.file_hash == file_hash)
            .order_by(ResearchFile.id.asc())
            .first()
        )
        if not rf:
            return None
        res = session.query(Research).filter(Research.id == rf.research_id).first()
        if not res:
            return None

        report_data = None
        if res.report_id:
            from app.repositories import report_repo
            rep = report_repo.get_report(res.report_id)
            if rep:
                report_data = {
                    'report_id': rep.get('id'),
                    'overall_pct': rep.get('overall_pct', 0.0),
                    'copied_pct': rep.get('copied_pct', 0.0),
                    'para_pct': rep.get('para_pct', 0.0),
                    'scan_date': str(rep.get('created_at', ''))[:19],
                    'title': rep.get('title', res.title),
                    'author': rep.get('author', res.author)
                }

        return {
            'research_id': res.id,
            'reference_number': res.reference_number,
            'title': res.title,
            'author': res.author,
            'created_by': res.created_by,
            'created_at': str(res.created_at)[:19] if res.created_at else '',
            'scan_status': res.scan_status,
            'review_status': res.review_status,
            'report_id': res.report_id,
            'report': report_data,
            'file_id': rf.id,
            'original_filename': rf.original_filename,
            'file_size_bytes': rf.file_size_bytes
        }


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
    """استرجاع كامل بيانات الدفعة مع عناصرها عبر استعلام واحد محسن يمنع مشكلة N+1."""
    with get_session() as session:
        batch = session.query(ScanBatch).filter(ScanBatch.id == batch_id).first()
        if not batch:
            return None

        # استعلام مدمج للعناصر مع الأبحاث المرتبطة
        items_with_res = (
            session.query(ScanBatchItem, Research)
            .outerjoin(Research, Research.id == ScanBatchItem.research_id)
            .filter(ScanBatchItem.batch_id == batch_id)
            .order_by(ScanBatchItem.item_order.asc())
            .all()
        )

        items = []
        for item, research in items_with_res:
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
                'research_reference_number': research.reference_number if (research and research.reference_number) else '',
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


# ─── Paginated Large Dataset Search & Filtering (Phase 10) ───────────────────

def search_researches(
    query: str = '',
    scan_status: Optional[str] = None,
    review_status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    sort_field: str = 'created_at',
    order_direction: str = 'desc',
    offset: int = 0,
    limit: int = 25,
    user_scope_username: Optional[str] = None,
    after_id: Optional[int] = None,
    before_id: Optional[int] = None
) -> tuple[list[dict], int]:
    """
    استعلام وبحث مقسم ومحسن للأبحاث والرسائل:
    - البحث الذكي: الرقم المرجعي الرسمي (أولوية قصوى)، العنوان، الباحث.
    - الفلترة المفهرسة: scan_status، review_status، النطاق الزمني.
    - تقييد نطاق البيانات الصارم بحسب المستخدم (Data Scoping).
    - دعم التصفح المفهرس بالمفاتيح (Keyset/Cursor Pagination: after_id / before_id) لمنع بطء OFFSET.
    - يرجع (قائمة_الأبحاث_الخفيفة, إجمالي_العدد).
    """
    from app.utils.search_normalizer import normalize_search_query, extract_reference_search_term
    from sqlalchemy import or_, and_, func

    with get_session() as session:
        q = session.query(Research)

        # 1. تقييد الصلاحيات ونطاق البيانات للمستخدم إن وجد
        if user_scope_username:
            q = q.filter(Research.created_by == user_scope_username)

        # 2. الفلترة بحالة الفحص وحالة التحكيم
        if scan_status and scan_status != 'all':
            q = q.filter(Research.scan_status == scan_status)
        if review_status and review_status != 'all':
            q = q.filter(Research.review_status == review_status)

        # 3. فلترة النطاق الزمني
        if date_from:
            try:
                dt_from = datetime.strptime(date_from[:10], '%Y-%m-%d')
                q = q.filter(Research.created_at >= dt_from)
            except ValueError:
                pass
        if date_to:
            try:
                dt_to = datetime.strptime(date_to[:10], '%Y-%m-%d')
                dt_to = dt_to.replace(hour=23, minute=59, second=59)
                q = q.filter(Research.created_at <= dt_to)
            except ValueError:
                pass

        # 4. معالجة نص البحث
        if query:
            clean_q = normalize_search_query(query)
            ref_term = extract_reference_search_term(clean_q)

            # إذا كان البحث يطابق رقم مرجعي مكتمل بصيغة رسمية (Exact Lookup First)
            if re.match(r'^RES-\d{4}-[A-Za-z0-9_]+$', ref_term):
                q_exact = q.filter(Research.reference_number == ref_term)
                if q_exact.order_by(None).count() > 0:
                    q = q_exact
                else:
                    q = q.filter(
                        or_(
                            Research.reference_number == ref_term,
                            Research.reference_number.ilike(f"%{clean_q}%"),
                            Research.title.ilike(f"%{clean_q}%")
                        )
                    )
            elif 'RES-' in ref_term or (len(ref_term) >= 4 and ref_term.replace('-', '').isdigit()):
                q = q.filter(
                    or_(
                        Research.reference_number == ref_term,
                        Research.reference_number.ilike(f"%{clean_q}%"),
                        Research.title.ilike(f"%{clean_q}%")
                    )
                )
            else:
                q = q.filter(
                    or_(
                        Research.title.ilike(f"%{clean_q}%"),
                        Research.author.ilike(f"%{clean_q}%"),
                        Research.reference_number.ilike(f"%{clean_q}%"),
                        Research.specialization.ilike(f"%{clean_q}%")
                    )
                )

        # حساب إجمالي النتائج بكفاءة دون جلب الكيانات
        total_count = q.order_by(None).count()

        # 5. تطبيق تصفية المفتاح المفهرس (Keyset / Cursor Navigation)
        if after_id is not None:
            if order_direction == 'desc':
                q = q.filter(Research.id < after_id)
            else:
                q = q.filter(Research.id > after_id)
        elif before_id is not None:
            if order_direction == 'desc':
                q = q.filter(Research.id > before_id)
            else:
                q = q.filter(Research.id < before_id)

        # 6. الترتيب الآمن
        sort_column_map = {
            'created_at': Research.created_at,
            'reference_number': Research.reference_number,
            'title': Research.title,
            'author': Research.author,
            'scan_status': Research.scan_status,
            'review_status': Research.review_status,
            'id': Research.id
        }
        sort_col = sort_column_map.get(sort_field, Research.created_at)
        if order_direction == 'asc':
            q = q.order_by(sort_col.asc(), Research.id.asc())
        else:
            q = q.order_by(sort_col.desc(), Research.id.desc())

        # 7. جلب الصفحة المحددة (إذا تم تمرير after_id/before_id نتفادى الـ offset الخطي)
        if after_id is not None or before_id is not None:
            rows = q.limit(limit).all()
        else:
            rows = q.offset(offset).limit(limit).all()

        items = []
        for r in rows:
            items.append({
                'id': r.id,
                'reference_number': r.reference_number or '',
                'title': r.title,
                'author': r.author or 'غير محدد',
                'specialization': r.specialization or '',
                'degree_type': r.degree_type or '',
                'created_by': r.created_by or '',
                'scan_status': r.scan_status or 'queued',
                'review_status': r.review_status or 'pending_review',
                'scan_status_label': SCAN_STATUS_LABELS_AR.get(r.scan_status, r.scan_status),
                'review_status_label': REVIEW_STATUS_LABELS_AR.get(r.review_status, r.review_status),
                'report_id': r.report_id,
                'scan_job_id': r.scan_job_id,
                'created_at': r.created_at.strftime('%Y-%m-%d %H:%M') if r.created_at else ''
            })

        return items, total_count



def search_batches(
    query: str = '',
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    sort_field: str = 'created_at',
    order_direction: str = 'desc',
    offset: int = 0,
    limit: int = 25
) -> tuple[list[dict], int]:
    """استعلام مقسم ومحسن لدفعات الفحص."""
    from app.utils.search_normalizer import normalize_search_query
    from sqlalchemy import or_, desc, asc

    with get_session() as session:
        q = session.query(ScanBatch)

        if status and status != 'all':
            q = q.filter(ScanBatch.status == status)

        if date_from:
            try:
                dt_from = datetime.strptime(date_from[:10], '%Y-%m-%d')
                q = q.filter(ScanBatch.created_at >= dt_from)
            except ValueError:
                pass
        if date_to:
            try:
                dt_to = datetime.strptime(date_to[:10], '%Y-%m-%d')
                dt_to = dt_to.replace(hour=23, minute=59, second=59)
                q = q.filter(ScanBatch.created_at <= dt_to)
            except ValueError:
                pass

        if query:
            clean_q = normalize_search_query(query)
            q = q.filter(or_(ScanBatch.id.ilike(f"%{clean_q}%"), ScanBatch.label.ilike(f"%{clean_q}%")))

        total_count = q.order_by(None).count()

        sort_col = ScanBatch.created_at
        if sort_field == 'label':
            sort_col = ScanBatch.label
        elif sort_field == 'status':
            sort_col = ScanBatch.status

        if order_direction == 'asc':
            q = q.order_by(sort_col.asc())
        else:
            q = q.order_by(sort_col.desc())

        rows = q.offset(offset).limit(limit).all()

        items = [
            {
                'id': b.id,
                'label': b.label,
                'status': b.status,
                'total_items': b.total_items,
                'completed_items': b.completed_items,
                'failed_items': b.failed_items,
                'created_by': b.created_by,
                'created_at': b.created_at.strftime('%Y-%m-%d %H:%M') if b.created_at else ''
            }
            for b in rows
        ]

        return items, total_count

