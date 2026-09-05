# -*- coding: utf-8 -*-
"""
مستودع بيانات التقارير والفحوصات (Report & Scan Repository):
- إدارة حفظ واسترجاع التقارير المفصلة وحالاتها.
- متابعة طابور الفحص الأولي والأبحاث المقبولة/المرفوضة.
- تخزين التطابقات المصدرية (Matches).
"""

import json
import logging
from datetime import datetime
from typing import Optional, Tuple
from sqlalchemy import desc, func

from app.repositories.base_repo import get_session
from app.models.schema import LegacyReport, ScanJob, Match
from app.workflow.statuses import (
    ScanStatus, ReviewStatus, SCAN_STATUS_LABELS_AR, REVIEW_STATUS_LABELS_AR,
    derive_legacy_status, map_legacy_status
)

logger = logging.getLogger(__name__)


def save_report(
    report_id: str,
    title: str,
    overall_pct: float,
    copied_pct: float,
    para_pct: float,
    report_dict: dict,
    category: str = 'عام',
    status: str = '',
    author: str = '',
    file_path: str = '',
    submitted_by: str = '',
    submitted_notes: str = '',
    scan_status: str = 'completed',
    review_status: str = 'pending_review',
    research_id: Optional[int] = None,
    scan_execution_id: str = '',
    revision_number: int = 1,
    supersedes_report_id: Optional[str] = None
):
    """حفظ أو تحديث تقرير فحص كامل مع حالتي الفحص والمراجعة وبيانات خط النسب."""
    if status and not (scan_status != 'completed' or review_status != 'pending_review'):
        mapped_scan, mapped_rev = map_legacy_status(status)
        scan_status = mapped_scan
        review_status = mapped_rev

    legacy_status_val = status or derive_legacy_status(scan_status, review_status)
    report_json_str = json.dumps(report_dict, ensure_ascii=False)

    with get_session() as session:
        rep = session.query(LegacyReport).filter(LegacyReport.id == report_id).first()
        if rep:
            # حماية التقرير المعتمد من التعديل الصامت للمقاييس
            if rep.artifact_status == 'finalized':
                logger.warning(f"محاولة تحديث تقرير معتمد مسبقاً تم تجاهلها للحفاظ على النزاهة: {report_id}")
                return

            rep.title = title
            rep.author = author
            rep.overall_pct = overall_pct
            rep.copied_pct = copied_pct
            rep.para_pct = para_pct
            rep.category = category
            rep.status = legacy_status_val
            rep.scan_status = scan_status
            rep.review_status = review_status
            rep.file_path = file_path
            rep.submitted_by = submitted_by
            rep.submitted_notes = submitted_notes
            rep.report_json = report_json_str
            if research_id is not None:
                rep.research_id = research_id
            if scan_execution_id:
                rep.scan_execution_id = scan_execution_id
            if revision_number:
                rep.revision_number = revision_number
            if supersedes_report_id:
                rep.supersedes_report_id = supersedes_report_id
        else:
            rep = LegacyReport(
                id=report_id,
                title=title,
                author=author,
                overall_pct=overall_pct,
                copied_pct=copied_pct,
                para_pct=para_pct,
                category=category,
                status=legacy_status_val,
                scan_status=scan_status,
                review_status=review_status,
                file_path=file_path,
                submitted_by=submitted_by,
                submitted_notes=submitted_notes,
                report_json=report_json_str,
                research_id=research_id,
                scan_execution_id=scan_execution_id or report_id,
                revision_number=revision_number,
                supersedes_report_id=supersedes_report_id,
                artifact_status='draft'
            )
            session.add(rep)


def get_report(report_id: str) -> Optional[dict]:
    """استرجاع تقرير محدد بمعرفه مع الرقم المرجعي الرسمي وحالتي الفحص والتحكيم وحالة النزاهة."""
    with get_session() as session:
        rep = session.query(LegacyReport).filter(LegacyReport.id == report_id).first()
        if not rep:
            return None
        try:
            data = json.loads(rep.report_json)
        except Exception:
            data = {}
        data['overall_pct'] = rep.overall_pct if rep.overall_pct is not None else data.get('overall_pct', 0.0)
        data['copied_pct'] = rep.copied_pct if rep.copied_pct is not None else data.get('copied_pct', 0.0)
        data['para_pct'] = rep.para_pct if rep.para_pct is not None else data.get('para_pct', 0.0)
        data['id'] = rep.id
        data['report_id'] = rep.id
        data['title'] = rep.title
        data['author'] = rep.author or 'غير محدد'
        data['category'] = rep.category or 'عام'
        data['status'] = rep.status or derive_legacy_status(rep.scan_status, rep.review_status)
        data['scan_status'] = rep.scan_status or 'completed'
        data['review_status'] = rep.review_status or 'pending_review'
        data['scan_status_label'] = SCAN_STATUS_LABELS_AR.get(data['scan_status'], data['scan_status'])
        data['review_status_label'] = REVIEW_STATUS_LABELS_AR.get(data['review_status'], data['review_status'])
        data['file_path'] = rep.file_path
        data['submitted_by'] = rep.submitted_by
        data['submitted_notes'] = rep.submitted_notes
        data['created_at'] = rep.created_at.strftime('%Y-%m-%d %H:%M') if rep.created_at else ''

        # بيانات النزاهة وإدارة المراجعات (Phase 15 Integrity & Lineage)
        data['research_id'] = rep.research_id
        data['scan_execution_id'] = rep.scan_execution_id or rep.id
        data['revision_number'] = rep.revision_number or 1
        data['supersedes_report_id'] = rep.supersedes_report_id
        data['artifact_status'] = rep.artifact_status or 'draft'
        data['finalization_hash'] = rep.finalization_hash or ''
        data['finalized_at'] = rep.finalized_at.strftime('%Y-%m-%d %H:%M') if rep.finalized_at else None
        data['finalized_by'] = rep.finalized_by or ''
        data['void_reason'] = rep.void_reason or ''
        data['voided_by'] = rep.voided_by or ''
        data['voided_at'] = rep.voided_at.strftime('%Y-%m-%d %H:%M') if rep.voided_at else None

        # جلب الرقم المرجعي للبحث المرتبط
        from app.models.research_schema import Research
        res = None
        if rep.research_id:
            res = session.query(Research).filter(Research.id == rep.research_id).first()
        if not res:
            res = session.query(Research).filter(Research.report_id == report_id).first()

        if res and res.reference_number:
            data['reference_number'] = res.reference_number
            data['research_reference_number'] = res.reference_number
            data['research_id'] = res.id
        elif not data.get('reference_number'):
            data['reference_number'] = data.get('research_reference_number', '')

        # جلب لقطة تشغيل ومعايير الفحص الأكاديمي (Snapshot)
        from app.services import snapshot_service
        data['snapshot'] = snapshot_service.get_report_snapshot(report_id)

        return data


def delete_report(report_id: str, allow_finalized: bool = False) -> bool:
    """حذف تقرير من الأرشيف (التقارير المعتمدة محمية من الحذف العادي للحفاظ على النزاهة)."""
    with get_session() as session:
        rep = session.query(LegacyReport).filter(LegacyReport.id == report_id).first()
        if rep:
            if rep.artifact_status == 'finalized' and not allow_finalized:
                logger.warning(f"محاولة حذف تقرير معتمد محظورة: report_id={report_id}")
                return False
            session.delete(rep)
            return True
    return False


def update_report_review_status(
    report_id: str,
    new_review_status: str,
    reviewer: str = 'system_user',
    comment: str = ''
) -> Tuple[bool, Optional[str]]:
    """
    تحديث حالة التحكيم الأكاديمي للتقرير والبحث المرتبط به مع توثيق قرار التحكيم في سجل الإصدار.
    يُعيد (نجاح, رسالة_خطأ_إن_وجدت).
    """
    with get_session() as session:
        rep = session.query(LegacyReport).filter(LegacyReport.id == report_id).first()
        if not rep:
            return False, "التقرير غير موجود"

        current_review = rep.review_status or 'pending_review'
        from app.workflow.statuses import validate_review_transition, derive_legacy_status, REVIEW_STATUS_LABELS_AR
        if not validate_review_transition(current_review, new_review_status):
            curr_label = REVIEW_STATUS_LABELS_AR.get(current_review, current_review)
            target_label = REVIEW_STATUS_LABELS_AR.get(new_review_status, new_review_status)
            return False, f"انتقال إجرائي غير مسموح به من «{curr_label}» إلى «{target_label}»"

        rep.review_status = new_review_status
        rep.status = derive_legacy_status(rep.scan_status or 'completed', new_review_status)
        try:
            data = json.loads(rep.report_json)
            data['review_status'] = new_review_status
            data['status'] = rep.status
            rep.report_json = json.dumps(data, ensure_ascii=False)
        except Exception:
            pass

        # مزامنة الحالة مع سجل البحث Research
        from app.models.research_schema import Research
        res = session.query(Research).filter(Research.report_id == report_id).first()
        if res:
            res.review_status = new_review_status

        # توثيق القرار مرتبطاً بهذا التقرير تحديداً
        from app.services import report_integrity_service
        report_integrity_service.record_review_decision(
            report_id=report_id,
            research_id=rep.research_id or (res.id if res else None),
            decision=new_review_status,
            reviewer=reviewer,
            comment=comment
        )

        return True, None


def set_report_status(report_id: str, status: str) -> bool:
    """تحديث حالة التقرير (مقبول مبدئياً، مرفوض، قبول نهائي...)."""
    mapped_scan, mapped_rev = map_legacy_status(status)
    success, _ = update_report_review_status(report_id, mapped_rev)
    return success


def get_reports_stats() -> dict:
    """حساب إحصائيات لوحة التحكم بناءً على حالات المراجعة الصريحة (Review Status)."""
    with get_session() as session:
        total_scans = session.query(LegacyReport).count()
        avg_plagiarism = session.query(func.avg(LegacyReport.overall_pct)).scalar() or 0.0
        preliminary_count = session.query(LegacyReport).filter(LegacyReport.review_status == ReviewStatus.PRELIMINARY_ACCEPTED.value).count()
        final_count = session.query(LegacyReport).filter(LegacyReport.review_status == ReviewStatus.FINAL_ACCEPTED.value).count()
        rejected_count = session.query(LegacyReport).filter(LegacyReport.review_status == ReviewStatus.REJECTED.value).count()
        pending_count = session.query(LegacyReport).filter(LegacyReport.review_status == ReviewStatus.PENDING_REVIEW.value).count()

        return {
            'total_scans': total_scans,
            'avg_plagiarism': round(float(avg_plagiarism), 1),
            'preliminary_count': preliminary_count,
            'final_count': final_count,
            'rejected_count': rejected_count,
            'pending_initial_count': pending_count
        }


def get_recent_reports(limit: int = 10) -> list[dict]:
    """استرجاع أحدث التقارير المفحوصة متضمنة الرقم المرجعي وحالتي الفحص والتحكيم باستعلام واحد مدمج."""
    from app.models.research_schema import Research
    with get_session() as session:
        rows = (
            session.query(LegacyReport, Research.reference_number)
            .outerjoin(Research, Research.report_id == LegacyReport.id)
            .order_by(desc(LegacyReport.created_at))
            .limit(limit)
            .all()
        )
        result = []
        for r, ref_no in rows:
            scan_st = r.scan_status or 'completed'
            rev_st = r.review_status or 'pending_review'
            result.append({
                'id': r.id,
                'reference_number': ref_no or '',
                'title': r.title,
                'author': r.author or 'غير محدد',
                'created_at': r.created_at.strftime('%Y-%m-%d %H:%M') if r.created_at else '',
                'overall_pct': r.overall_pct,
                'status': r.status or derive_legacy_status(scan_st, rev_st),
                'scan_status': scan_st,
                'review_status': rev_st,
                'scan_status_label': SCAN_STATUS_LABELS_AR.get(scan_st, scan_st),
                'review_status_label': REVIEW_STATUS_LABELS_AR.get(rev_st, rev_st)
            })
        return result


def get_preliminary_reports(
    query: str = '',
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    offset: int = 0,
    limit: Optional[int] = None,
    as_tuple: bool = False
):
    """الأبحاث المقبولة مبدئياً مع دعم البحث وفلترة التواريخ وترقيم الصفحات الموحد."""
    from app.models.research_schema import Research
    from app.utils.search_normalizer import normalize_search_query
    from sqlalchemy import or_

    with get_session() as session:
        q = (
            session.query(LegacyReport, Research.reference_number)
            .outerjoin(Research, Research.report_id == LegacyReport.id)
            .filter(LegacyReport.review_status == ReviewStatus.PRELIMINARY_ACCEPTED.value)
        )

        if date_from:
            try:
                dt_from = datetime.strptime(date_from[:10], '%Y-%m-%d')
                q = q.filter(LegacyReport.created_at >= dt_from)
            except ValueError:
                pass
        if date_to:
            try:
                dt_to = datetime.strptime(date_to[:10], '%Y-%m-%d')
                dt_to = dt_to.replace(hour=23, minute=59, second=59)
                q = q.filter(LegacyReport.created_at <= dt_to)
            except ValueError:
                pass

        if query:
            clean_q = normalize_search_query(query)
            q = q.filter(
                or_(
                    LegacyReport.title.ilike(f"%{clean_q}%"),
                    LegacyReport.author.ilike(f"%{clean_q}%"),
                    Research.reference_number.ilike(f"%{clean_q}%"),
                    LegacyReport.id.ilike(f"%{clean_q}%")
                )
            )

        total_count = q.order_by(None).count()
        q = q.order_by(desc(LegacyReport.created_at))

        if limit is not None:
            rows = q.offset(offset).limit(limit).all()
        else:
            rows = q.all()

        result = []
        for r, ref_no in rows:
            result.append({
                'id': r.id,
                'reference_number': ref_no or '',
                'title': r.title,
                'author': r.author,
                'category': r.category,
                'created_at': r.created_at.strftime('%Y-%m-%d %H:%M') if r.created_at else '',
                'date': r.created_at.strftime('%Y-%m-%d %H:%M') if r.created_at else '',
                'overall_pct': r.overall_pct,
                'scan_status': r.scan_status or 'completed',
                'review_status': r.review_status or ReviewStatus.PRELIMINARY_ACCEPTED.value,
                'review_status_label': REVIEW_STATUS_LABELS_AR.get(r.review_status, 'قبول مبدئي')
            })

        if as_tuple:
            return result, total_count
        return result


def get_rejected_reports(
    query: str = '',
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    offset: int = 0,
    limit: Optional[int] = None,
    as_tuple: bool = False
):
    """الأبحاث المرفوضة أكاديمياً مع دعم البحث وفلترة التواريخ وترقيم الصفحات الموحد."""
    from app.models.research_schema import Research
    from app.utils.search_normalizer import normalize_search_query
    from sqlalchemy import or_

    with get_session() as session:
        q = (
            session.query(LegacyReport, Research.reference_number)
            .outerjoin(Research, Research.report_id == LegacyReport.id)
            .filter(LegacyReport.review_status == ReviewStatus.REJECTED.value)
        )

        if date_from:
            try:
                dt_from = datetime.strptime(date_from[:10], '%Y-%m-%d')
                q = q.filter(LegacyReport.created_at >= dt_from)
            except ValueError:
                pass
        if date_to:
            try:
                dt_to = datetime.strptime(date_to[:10], '%Y-%m-%d')
                dt_to = dt_to.replace(hour=23, minute=59, second=59)
                q = q.filter(LegacyReport.created_at <= dt_to)
            except ValueError:
                pass

        if query:
            clean_q = normalize_search_query(query)
            q = q.filter(
                or_(
                    LegacyReport.title.ilike(f"%{clean_q}%"),
                    LegacyReport.author.ilike(f"%{clean_q}%"),
                    Research.reference_number.ilike(f"%{clean_q}%"),
                    LegacyReport.id.ilike(f"%{clean_q}%")
                )
            )

        total_count = q.order_by(None).count()
        q = q.order_by(desc(LegacyReport.created_at))

        if limit is not None:
            rows = q.offset(offset).limit(limit).all()
        else:
            rows = q.all()

        result = []
        for r, ref_no in rows:
            result.append({
                'id': r.id,
                'reference_number': ref_no or '',
                'title': r.title,
                'author': r.author,
                'category': r.category,
                'created_at': r.created_at.strftime('%Y-%m-%d %H:%M') if r.created_at else '',
                'date': r.created_at.strftime('%Y-%m-%d %H:%M') if r.created_at else '',
                'overall_pct': r.overall_pct,
                'scan_status': r.scan_status or 'completed',
                'review_status': r.review_status or ReviewStatus.REJECTED.value,
                'review_status_label': REVIEW_STATUS_LABELS_AR.get(r.review_status, 'مرفوض')
            })

        if as_tuple:
            return result, total_count
        return result


def get_pending_initial_reviews(
    query: str = '',
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    offset: int = 0,
    limit: Optional[int] = None,
    as_tuple: bool = False
):
    """طابور الأبحاث المنتظرة للفحص الأولي مع دعم البحث وفلترة التواريخ والتقسيم المكتبي."""
    from app.models.research_schema import Research
    from app.utils.search_normalizer import normalize_search_query
    from sqlalchemy import or_

    with get_session() as session:
        q = (
            session.query(LegacyReport, Research.reference_number)
            .outerjoin(Research, Research.report_id == LegacyReport.id)
            .filter(LegacyReport.review_status == ReviewStatus.PENDING_REVIEW.value)
        )

        if date_from:
            try:
                dt_from = datetime.strptime(date_from[:10], '%Y-%m-%d')
                q = q.filter(LegacyReport.created_at >= dt_from)
            except ValueError:
                pass
        if date_to:
            try:
                dt_to = datetime.strptime(date_to[:10], '%Y-%m-%d')
                dt_to = dt_to.replace(hour=23, minute=59, second=59)
                q = q.filter(LegacyReport.created_at <= dt_to)
            except ValueError:
                pass

        if query:
            clean_q = normalize_search_query(query)
            q = q.filter(
                or_(
                    LegacyReport.title.ilike(f"%{clean_q}%"),
                    LegacyReport.author.ilike(f"%{clean_q}%"),
                    Research.reference_number.ilike(f"%{clean_q}%"),
                    LegacyReport.id.ilike(f"%{clean_q}%")
                )
            )

        total_count = q.order_by(None).count()
        q = q.order_by(desc(LegacyReport.created_at))

        if limit is not None:
            rows = q.offset(offset).limit(limit).all()
        else:
            rows = q.all()

        result = []
        for r, ref_no in rows:
            result.append({
                'id': r.id,
                'reference_number': ref_no or '',
                'title': r.title,
                'author': r.author,
                'created_at': r.created_at.strftime('%Y-%m-%d %H:%M') if r.created_at else '',
                'date': r.created_at.strftime('%Y-%m-%d %H:%M') if r.created_at else '',
                'overall_pct': r.overall_pct,
                'scan_status': r.scan_status or 'completed',
                'review_status': r.review_status or ReviewStatus.PENDING_REVIEW.value,
                'review_status_label': REVIEW_STATUS_LABELS_AR.get(r.review_status, 'قيد المراجعة'),
                'submitted_by': r.submitted_by,
                'submitted_notes': r.submitted_notes,
                'notes': r.submitted_notes
            })

        if as_tuple:
            return result, total_count
        return result


def search_reports(
    query: str = '',
    review_status: Optional[str] = None,
    scan_status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    sort_field: str = 'created_at',
    order_direction: str = 'desc',
    offset: int = 0,
    limit: int = 25
) -> tuple[list[dict], int]:
    """استعلام مقسم ومحسن للتقارير الأكاديمية المفحوصة مع بيانات المرجع."""
    from app.models.research_schema import Research
    from app.utils.search_normalizer import normalize_search_query
    from sqlalchemy import or_

    with get_session() as session:
        q = (
            session.query(LegacyReport, Research.reference_number)
            .outerjoin(Research, Research.report_id == LegacyReport.id)
        )

        if review_status and review_status != 'all':
            q = q.filter(LegacyReport.review_status == review_status)
        if scan_status and scan_status != 'all':
            q = q.filter(LegacyReport.scan_status == scan_status)

        if date_from:
            try:
                dt_from = datetime.strptime(date_from[:10], '%Y-%m-%d')
                q = q.filter(LegacyReport.created_at >= dt_from)
            except ValueError:
                pass
        if date_to:
            try:
                dt_to = datetime.strptime(date_to[:10], '%Y-%m-%d')
                dt_to = dt_to.replace(hour=23, minute=59, second=59)
                q = q.filter(LegacyReport.created_at <= dt_to)
            except ValueError:
                pass

        if query:
            clean_q = normalize_search_query(query)
            q = q.filter(
                or_(
                    LegacyReport.title.ilike(f"%{clean_q}%"),
                    LegacyReport.author.ilike(f"%{clean_q}%"),
                    Research.reference_number.ilike(f"%{clean_q}%"),
                    LegacyReport.id.ilike(f"%{clean_q}%")
                )
            )

        total_count = q.order_by(None).count()

        sort_map = {
            'created_at': LegacyReport.created_at,
            'title': LegacyReport.title,
            'overall_pct': LegacyReport.overall_pct,
            'review_status': LegacyReport.review_status
        }
        sort_col = sort_map.get(sort_field, LegacyReport.created_at)
        if order_direction == 'asc':
            q = q.order_by(sort_col.asc())
        else:
            q = q.order_by(sort_col.desc())

        rows = q.offset(offset).limit(limit).all()

        items = []
        for r, ref_no in rows:
            scan_st = r.scan_status or 'completed'
            rev_st = r.review_status or 'pending_review'
            items.append({
                'id': r.id,
                'reference_number': ref_no or '',
                'title': r.title,
                'author': r.author or 'غير محدد',
                'created_at': r.created_at.strftime('%Y-%m-%d %H:%M') if r.created_at else '',
                'date': r.created_at.strftime('%Y-%m-%d %H:%M') if r.created_at else '',
                'overall_pct': r.overall_pct,
                'status': r.status or derive_legacy_status(scan_st, rev_st),
                'scan_status': scan_st,
                'review_status': rev_st,
                'scan_status_label': SCAN_STATUS_LABELS_AR.get(scan_st, scan_st),
                'review_status_label': REVIEW_STATUS_LABELS_AR.get(rev_st, rev_st)
            })

        return items, total_count


def get_pending_initial_reviews_count() -> int:
    with get_session() as session:
        return session.query(LegacyReport).filter(LegacyReport.review_status == ReviewStatus.PENDING_REVIEW.value).count()


def submit_report_to_admin(report_id: str, employee_name: str, notes: str):
    """إرسال بحث من موظف لمدير النظام للاعتماد."""
    with get_session() as session:
        rep = session.query(LegacyReport).filter(LegacyReport.id == report_id).first()
        if rep:
            rep.review_status = ReviewStatus.PENDING_REVIEW.value
            rep.status = 'بانتظار الفحص الأولي'
            rep.submitted_by = employee_name
            rep.submitted_notes = notes

            from app.models.research_schema import Research
            res = session.query(Research).filter(Research.report_id == report_id).first()
            if res:
                res.review_status = ReviewStatus.PENDING_REVIEW.value


def update_report_latest_pdf(report_id: str, file_path: str, full_text: str):
    """تحديث ملف الـ PDF النهائي للبحث المقبول مبدئياً."""
    with get_session() as session:
        rep = session.query(LegacyReport).filter(LegacyReport.id == report_id).first()
        if rep:
            rep.file_path = file_path
            try:
                data = json.loads(rep.report_json)
                data['final_file_path'] = file_path
                data['final_full_text'] = full_text
                rep.report_json = json.dumps(data, ensure_ascii=False)
            except Exception:
                pass


# إدارة مهام الفحص في الخلفية
def create_scan_job(job_id: str, filename: str, title: str = '', author: str = ''):
    with get_session() as session:
        job = ScanJob(
            id=job_id,
            filename=filename,
            title=title,
            author=author,
            status='running',
            progress=10,
            stage='جاري استلام الملف وبدء الفحص...'
        )
        session.add(job)


def update_scan_job(job_id: str, status: str, progress: int, stage: str, result_dict: dict = None, error: str = ''):
    with get_session() as session:
        job = session.query(ScanJob).filter(ScanJob.id == job_id).first()
        if job:
            job.status = status
            job.progress = progress
            job.stage = stage
            if error:
                job.error = error
            if result_dict:
                job.result_json = json.dumps(result_dict, ensure_ascii=False)
                job.completed_at = datetime.utcnow()


def get_scan_job(job_id: str) -> Optional[dict]:
    with get_session() as session:
        job = session.query(ScanJob).filter(ScanJob.id == job_id).first()
        if not job:
            return None
        res = None
        if job.result_json:
            try:
                res = json.loads(job.result_json)
            except Exception:
                res = None
        return {
            'task_id': job.id,
            'status': job.status,
            'progress': job.progress,
            'stage': job.stage,
            'error': job.error,
            'result': res,
            'created_at': job.created_at.isoformat() if job.created_at else ''
        }
