# -*- coding: utf-8 -*-
"""
مستودع بيانات الرسائل العلمية متعددة الأجزاء (Thesis & Thesis Part Repository):
- إدارة كيان الرسالة وتوليد الأرقام المرجعية الذرية (THS-YYYY-XXXXXX).
- إدارة أجزاء الرسالة (إضافة، ترتيب، تعديل التسمية، الفصل/الاستبعاد).
- منع التكرار داخل الرسالة الواحدة مع تقديم تحذيرات دقيقة.
- حفظ وتتبع نتائج الفحص الفردية لكل جزء ومزامنة حالة الرسالة.
"""

import logging
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy import or_

from app.repositories.base_repo import get_session
from app.models.research_schema import Thesis, ThesisPart, generate_thesis_reference
from app.models.schema import LegacyReport

logger = logging.getLogger(__name__)


def create_thesis(
    title: str,
    author: str,
    degree_type: str = 'ماجستير',
    department: str = '',
    academic_year: str = '',
    notes: str = '',
    created_by: str = '',
    created_by_user_id: Optional[int] = None
) -> Tuple[int, str]:
    """إنشاء كيان رسالة علمية جديد مع توليد الرقم المرجعي الذري."""
    with get_session() as session:
        ref_num = generate_thesis_reference(session)
        thesis = Thesis(
            reference_number=ref_num,
            title=title.strip(),
            author=author.strip(),
            degree_type=degree_type.strip() or 'ماجستير',
            department=department.strip(),
            academic_year=academic_year.strip(),
            notes=notes.strip(),
            status='draft',
            review_status='pending_review',
            created_by=created_by.strip(),
            created_by_user_id=created_by_user_id,
            is_stale=0
        )
        session.add(thesis)
        session.flush()
        return thesis.id, ref_num


def get_thesis(thesis_id: int) -> Optional[dict]:
    """استرجاع بيانات الرسالة الكاملة مع كافة أجزائها النشطة وإحصائياتها."""
    with get_session() as session:
        th = session.query(Thesis).filter(Thesis.id == thesis_id).first()
        if not th:
            return None

        parts = (
            session.query(ThesisPart)
            .filter(ThesisPart.thesis_id == thesis_id, ThesisPart.is_detached == 0)
            .order_by(ThesisPart.sort_order.asc(), ThesisPart.id.asc())
            .all()
        )

        parts_list = []
        total_analyzable_words = 0
        total_problematic_words = 0
        completed_count = 0
        failed_count = 0
        pending_count = 0

        for p in parts:
            if p.scan_status == 'completed':
                completed_count += 1
                total_analyzable_words += getattr(p, 'total_words', 0) or 0
                total_problematic_words += getattr(p, 'problematic_words', 0) or 0
            elif p.scan_status in ('failed', 'error'):
                failed_count += 1
            else:
                pending_count += 1

            parts_list.append({
                'id': p.id,
                'thesis_id': p.thesis_id,
                'part_title': p.part_title,
                'sort_order': p.sort_order,
                'original_filename': p.original_filename,
                'stored_filename': p.stored_filename,
                'file_type': p.file_type,
                'file_size_bytes': p.file_size_bytes,
                'file_hash': p.file_hash,
                'scan_status': p.scan_status,
                'scan_job_id': p.scan_job_id,
                'report_id': p.report_id,
                'similarity_pct': p.similarity_pct,
                'problematic_pct': p.problematic_pct,
                'copied_pct': p.copied_pct,
                'para_pct': p.para_pct,
                'cited_pct': p.cited_pct,
                'total_words': p.total_words,
                'problematic_words': p.problematic_words,
                'error_message': p.error_message,
                'created_at': p.created_at.strftime('%Y-%m-%d %H:%M') if p.created_at else ''
            })

        # حساب النسبة المجمعة التقديرية الحالية
        calc_combined_pct = None
        if total_analyzable_words > 0:
            calc_combined_pct = min(round((total_problematic_words / total_analyzable_words) * 100, 1), 100.0)

        # جلب معلومات التقرير المجمع
        combined_report_data = None
        if th.combined_report_id:
            rep = session.query(LegacyReport).filter(LegacyReport.id == th.combined_report_id).first()
            if rep:
                combined_report_data = {
                    'id': rep.id,
                    'revision_number': rep.revision_number,
                    'artifact_status': rep.artifact_status,
                    'overall_pct': rep.overall_pct,
                    'copied_pct': rep.copied_pct,
                    'para_pct': rep.para_pct,
                    'created_at': rep.created_at.strftime('%Y-%m-%d %H:%M') if rep.created_at else ''
                }

        return {
            'id': th.id,
            'reference_number': th.reference_number,
            'title': th.title,
            'author': th.author,
            'degree_type': th.degree_type,
            'department': th.department,
            'academic_year': th.academic_year,
            'notes': th.notes,
            'status': th.status,
            'review_status': th.review_status,
            'combined_report_id': th.combined_report_id,
            'combined_report': combined_report_data,
            'is_stale': bool(th.is_stale),
            'created_by': th.created_by,
            'created_by_user_id': th.created_by_user_id,
            'total_parts': len(parts),
            'completed_parts_count': completed_count,
            'failed_parts_count': failed_count,
            'pending_parts_count': pending_count,
            'is_all_completed': (len(parts) > 0 and completed_count == len(parts)),
            'total_analyzable_words': total_analyzable_words,
            'combined_problematic_pct': calc_combined_pct,
            'parts': parts_list,
            'created_at': th.created_at.strftime('%Y-%m-%d %H:%M') if th.created_at else ''
        }


def get_thesis_by_reference(reference_number: str) -> Optional[dict]:
    """استرجاع الرسالة عبر رقمها المرجعي."""
    with get_session() as session:
        th = session.query(Thesis).filter(Thesis.reference_number == reference_number.strip()).first()
        if not th:
            return None
        return get_thesis(th.id)


def search_theses(
    query: Optional[str] = None,
    degree_type: Optional[str] = None,
    department: Optional[str] = None,
    status: Optional[str] = None,
    review_status: Optional[str] = None,
    page: int = 1,
    per_page: int = 25
) -> Tuple[List[dict], int]:
    """بحث واسترجاع قائمة الرسائل العلمية مع دعم الترقيم والفلترة ونطاق الوحدة."""
    with get_session() as session:
        q = session.query(Thesis)

        if query and query.strip():
            clean_q = f"%{query.strip()}%"
            q = q.filter(
                or_(
                    Thesis.title.ilike(clean_q),
                    Thesis.author.ilike(clean_q),
                    Thesis.reference_number.ilike(clean_q),
                    Thesis.department.ilike(clean_q)
                )
            )

        if degree_type and degree_type.strip():
            q = q.filter(Thesis.degree_type == degree_type.strip())

        if department and department.strip():
            q = q.filter(Thesis.department.ilike(f"%{department.strip()}%"))

        if status and status.strip():
            q = q.filter(Thesis.status == status.strip())

        if review_status and review_status.strip():
            q = q.filter(Thesis.review_status == review_status.strip())

        total_count = q.count()
        offset_val = max(0, (page - 1) * per_page)
        theses = q.order_by(Thesis.id.desc()).offset(offset_val).limit(per_page).all()

        results = []
        for th in theses:
            # إحصائيات سريعة للأجزاء
            p_stats = (
                session.query(ThesisPart.scan_status)
                .filter(ThesisPart.thesis_id == th.id, ThesisPart.is_detached == 0)
                .all()
            )
            total_p = len(p_stats)
            completed_p = sum(1 for p in p_stats if p[0] == 'completed')
            failed_p = sum(1 for p in p_stats if p[0] in ('failed', 'error'))

            results.append({
                'id': th.id,
                'reference_number': th.reference_number,
                'title': th.title,
                'author': th.author,
                'degree_type': th.degree_type,
                'department': th.department,
                'status': th.status,
                'review_status': th.review_status,
                'total_parts': total_p,
                'completed_parts': completed_p,
                'failed_parts': failed_p,
                'combined_report_id': th.combined_report_id,
                'is_stale': bool(th.is_stale),
                'created_by': th.created_by,
                'created_at': th.created_at.strftime('%Y-%m-%d %H:%M') if th.created_at else ''
            })

        return results, total_count


def file_hash_exists_in_thesis(thesis_id: int, file_hash: str) -> bool:
    """التحقق مما إذا كان هناك ملف بنفس الهاش موجود مسبقاً داخل نفس الرسالة."""
    if not file_hash:
        return False
    with get_session() as session:
        count = (
            session.query(ThesisPart)
            .filter(
                ThesisPart.thesis_id == thesis_id,
                ThesisPart.file_hash == file_hash,
                ThesisPart.is_detached == 0
            )
            .count()
        )
        return count > 0


def add_thesis_part(
    thesis_id: int,
    part_title: str,
    original_filename: str,
    stored_filename: str,
    file_path: str,
    file_type: str,
    file_size_bytes: int,
    file_hash: str,
    sort_order: Optional[int] = None
) -> Tuple[int, bool]:
    """
    إضافة جزء جديد إلى الرسالة.
    تُعيد (part_id, is_duplicate_in_thesis)
    """
    is_dup = file_hash_exists_in_thesis(thesis_id, file_hash)

    with get_session() as session:
        if sort_order is None:
            max_order = (
                session.query(ThesisPart.sort_order)
                .filter(ThesisPart.thesis_id == thesis_id)
                .order_by(ThesisPart.sort_order.desc())
                .first()
            )
            sort_order = (max_order[0] + 1) if max_order else 0

        part = ThesisPart(
            thesis_id=thesis_id,
            part_title=part_title.strip() or original_filename,
            sort_order=sort_order,
            original_filename=original_filename,
            stored_filename=stored_filename,
            file_path=file_path,
            file_type=file_type,
            file_size_bytes=file_size_bytes,
            file_hash=file_hash,
            scan_status='queued',
            is_detached=0
        )
        session.add(part)

        # وسم الرسالة كـ stale لإعادة توليد التقرير المجمع
        th = session.query(Thesis).filter(Thesis.id == thesis_id).first()
        if th:
            th.is_stale = 1
            if th.status == 'completed':
                th.status = 'incomplete'

        session.flush()
        return part.id, is_dup


def get_thesis_part(part_id: int) -> Optional[dict]:
    """استرجاع بيانات جزء محدد من الرسالة."""
    with get_session() as session:
        p = session.query(ThesisPart).filter(ThesisPart.id == part_id).first()
        if not p:
            return None
        return {
            'id': p.id,
            'thesis_id': p.thesis_id,
            'part_title': p.part_title,
            'sort_order': p.sort_order,
            'original_filename': p.original_filename,
            'stored_filename': p.stored_filename,
            'file_path': p.file_path,
            'file_type': p.file_type,
            'file_size_bytes': p.file_size_bytes,
            'file_hash': p.file_hash,
            'scan_status': p.scan_status,
            'scan_job_id': p.scan_job_id,
            'report_id': p.report_id,
            'similarity_pct': p.similarity_pct,
            'problematic_pct': p.problematic_pct,
            'copied_pct': p.copied_pct,
            'para_pct': p.para_pct,
            'cited_pct': p.cited_pct,
            'total_words': p.total_words,
            'problematic_words': p.problematic_words,
            'copied_words': p.copied_words,
            'para_words': p.para_words,
            'cited_words': p.cited_words,
            'error_message': p.error_message,
            'is_detached': p.is_detached,
            'created_at': p.created_at.strftime('%Y-%m-%d %H:%M') if p.created_at else ''
        }


def update_thesis_part_meta(
    part_id: int,
    part_title: Optional[str] = None,
    sort_order: Optional[int] = None
) -> Tuple[bool, str]:
    """تعديل التسمية المعروضة أو ترتيب الجزء."""
    with get_session() as session:
        p = session.query(ThesisPart).filter(ThesisPart.id == part_id).first()
        if not p:
            return False, "الجزء غير موجود"

        if part_title and part_title.strip():
            p.part_title = part_title.strip()

        if sort_order is not None:
            p.sort_order = sort_order

        return True, "تم تحديث بيانات الجزء بنجاح"


def detach_thesis_part(part_id: int, detached_by: str = '', reason: str = '') -> Tuple[bool, str]:
    """فصل أو استبعاد جزء من الرسالة دون حذف الملف الفعلي من سجل التخزين التاريخي."""
    with get_session() as session:
        p = session.query(ThesisPart).filter(ThesisPart.id == part_id).first()
        if not p:
            return False, "الجزء غير موجود"

        p.is_detached = 1
        p.detached_by = detached_by
        p.detach_reason = reason

        th = session.query(Thesis).filter(Thesis.id == p.thesis_id).first()
        if th:
            th.is_stale = 1

        return True, "تم استبعاد الجزء من الرسالة بنجاح"


def update_thesis_part_scan_result(
    part_id: int,
    scan_status: str,
    scan_job_id: Optional[str] = None,
    report_id: Optional[str] = None,
    similarity_pct: Optional[float] = None,
    problematic_pct: Optional[float] = None,
    copied_pct: Optional[float] = None,
    para_pct: Optional[float] = None,
    cited_pct: Optional[float] = None,
    total_words: int = 0,
    problematic_words: int = 0,
    copied_words: int = 0,
    para_words: int = 0,
    cited_words: int = 0,
    error_message: str = ''
) -> bool:
    """تحديث نتائج فحص الجزء المنفرد في قاعدة البيانات."""
    with get_session() as session:
        p = session.query(ThesisPart).filter(ThesisPart.id == part_id).first()
        if not p:
            return False

        p.scan_status = scan_status
        if scan_job_id:
            p.scan_job_id = scan_job_id
        if report_id:
            p.report_id = report_id
        if similarity_pct is not None:
            p.similarity_pct = similarity_pct
        if problematic_pct is not None:
            p.problematic_pct = problematic_pct
        if copied_pct is not None:
            p.copied_pct = copied_pct
        if para_pct is not None:
            p.para_pct = para_pct
        if cited_pct is not None:
            p.cited_pct = cited_pct

        p.total_words = total_words
        p.problematic_words = problematic_words
        p.copied_words = copied_words
        p.para_words = para_words
        p.cited_words = cited_words
        p.error_message = error_message

        # وسم الرسالة كـ stale
        th = session.query(Thesis).filter(Thesis.id == p.thesis_id).first()
        if th:
            th.is_stale = 1
            # فحص حالة سائر أجزاء الرسالة
            all_parts = session.query(ThesisPart).filter(ThesisPart.thesis_id == th.id, ThesisPart.is_detached == 0).all()
            if all(pt.scan_status == 'completed' for pt in all_parts):
                th.status = 'completed'
            elif any(pt.scan_status in ('failed', 'error') for pt in all_parts):
                th.status = 'incomplete'
            elif any(pt.scan_status in ('queued', 'processing', 'running') for pt in all_parts):
                th.status = 'processing'

        return True


def update_thesis_status(
    thesis_id: int,
    status: Optional[str] = None,
    review_status: Optional[str] = None,
    combined_report_id: Optional[str] = None,
    is_stale: Optional[int] = None
) -> bool:
    """تحديث الحالة العامة للرسالة والتقرير المجمع."""
    with get_session() as session:
        th = session.query(Thesis).filter(Thesis.id == thesis_id).first()
        if not th:
            return False

        if status:
            th.status = status
        if review_status:
            th.review_status = review_status
        if combined_report_id is not None:
            th.combined_report_id = combined_report_id
        if is_stale is not None:
            th.is_stale = is_stale

        return True
