# -*- coding: utf-8 -*-
"""
مستودع بيانات التقارير والفحوصات (Report & Scan Repository):
- إدارة حفظ واسترجاع التقارير المفصلة وحالاتها.
- متابعة طابور الفحص الأولي والأبحاث المقبولة/المرفوضة.
- تخزين التطابقات المصدرية (Matches).
"""

import json
from datetime import datetime
from typing import Optional
from sqlalchemy import desc, func

from app.repositories.base_repo import get_session
from app.models.schema import LegacyReport, ScanJob, Match


def save_report(
    report_id: str,
    title: str,
    overall_pct: float,
    copied_pct: float,
    para_pct: float,
    report_dict: dict,
    category: str = 'عام',
    status: str = 'مفحوص',
    author: str = '',
    file_path: str = '',
    submitted_by: str = '',
    submitted_notes: str = ''
):
    """حفظ أو تحديث تقرير فحص كامل."""
    report_json_str = json.dumps(report_dict, ensure_ascii=False)
    with get_session() as session:
        rep = session.query(LegacyReport).filter(LegacyReport.id == report_id).first()
        if rep:
            rep.title = title
            rep.author = author
            rep.overall_pct = overall_pct
            rep.copied_pct = copied_pct
            rep.para_pct = para_pct
            rep.category = category
            rep.status = status
            rep.file_path = file_path
            rep.submitted_by = submitted_by
            rep.submitted_notes = submitted_notes
            rep.report_json = report_json_str
        else:
            rep = LegacyReport(
                id=report_id,
                title=title,
                author=author,
                overall_pct=overall_pct,
                copied_pct=copied_pct,
                para_pct=para_pct,
                category=category,
                status=status,
                file_path=file_path,
                submitted_by=submitted_by,
                submitted_notes=submitted_notes,
                report_json=report_json_str
            )
            session.add(rep)


def get_report(report_id: str) -> Optional[dict]:
    """استرجاع تقرير محدد بمعرفه."""
    with get_session() as session:
        rep = session.query(LegacyReport).filter(LegacyReport.id == report_id).first()
        if not rep:
            return None
        try:
            data = json.loads(rep.report_json)
        except Exception:
            data = {}
        data['id'] = rep.id
        data['title'] = rep.title
        data['author'] = rep.author or 'غير محدد'
        data['category'] = rep.category or 'عام'
        data['status'] = rep.status
        data['file_path'] = rep.file_path
        data['submitted_by'] = rep.submitted_by
        data['submitted_notes'] = rep.submitted_notes
        data['created_at'] = rep.created_at.strftime('%Y-%m-%d %H:%M') if rep.created_at else ''
        return data


def delete_report(report_id: str) -> bool:
    """حذف تقرير من الأرشيف."""
    with get_session() as session:
        rep = session.query(LegacyReport).filter(LegacyReport.id == report_id).first()
        if rep:
            session.delete(rep)
            return True
    return False


def set_report_status(report_id: str, status: str) -> bool:
    """تحديث حالة التقرير (مقبول مبدئياً، مرفوض، قبول نهائي...)."""
    with get_session() as session:
        rep = session.query(LegacyReport).filter(LegacyReport.id == report_id).first()
        if rep:
            rep.status = status
            try:
                data = json.loads(rep.report_json)
                data['status'] = status
                rep.report_json = json.dumps(data, ensure_ascii=False)
            except Exception:
                pass
            return True
    return False


def get_reports_stats() -> dict:
    """حساب إحصائيات لوحة التحكم."""
    with get_session() as session:
        total_scans = session.query(LegacyReport).count()
        avg_plagiarism = session.query(func.avg(LegacyReport.overall_pct)).scalar() or 0.0
        preliminary_count = session.query(LegacyReport).filter(LegacyReport.status == 'قبول مبدئي').count()
        final_count = session.query(LegacyReport).filter(LegacyReport.status == 'قبول نهائي').count()
        pending_count = session.query(LegacyReport).filter(LegacyReport.status == 'بانتظار الفحص الأولي').count()

        return {
            'total_scans': total_scans,
            'avg_plagiarism': round(float(avg_plagiarism), 1),
            'preliminary_count': preliminary_count,
            'final_count': final_count,
            'pending_initial_count': pending_count
        }


def get_recent_reports(limit: int = 10) -> list[dict]:
    """استرجاع أحدث التقارير المفحوصة."""
    with get_session() as session:
        rows = session.query(LegacyReport).order_by(desc(LegacyReport.created_at)).limit(limit).all()
        return [
            {
                'id': r.id,
                'title': r.title,
                'author': r.author or 'غير محدد',
                'created_at': r.created_at.strftime('%Y-%m-%d %H:%M') if r.created_at else '',
                'overall_pct': r.overall_pct,
                'status': r.status
            }
            for r in rows
        ]


def get_preliminary_reports() -> list[dict]:
    """الأبحاث المقبولة مبدئياً."""
    with get_session() as session:
        rows = session.query(LegacyReport).filter(LegacyReport.status == 'قبول مبدئي').order_by(desc(LegacyReport.created_at)).all()
        return [
            {
                'id': r.id,
                'title': r.title,
                'author': r.author,
                'category': r.category,
                'date': r.created_at.strftime('%Y-%m-%d %H:%M') if r.created_at else '',
                'overall_pct': r.overall_pct
            }
            for r in rows
        ]


def get_rejected_reports() -> list[dict]:
    """الأبحاث المرفوضة."""
    with get_session() as session:
        rows = session.query(LegacyReport).filter(LegacyReport.status == 'مرفوض').order_by(desc(LegacyReport.created_at)).all()
        return [
            {
                'id': r.id,
                'title': r.title,
                'author': r.author,
                'category': r.category,
                'date': r.created_at.strftime('%Y-%m-%d %H:%M') if r.created_at else '',
                'overall_pct': r.overall_pct
            }
            for r in rows
        ]


def get_pending_initial_reviews(query: str = '') -> list[dict]:
    """طابور الأبحاث المنتظرة للفحص الأولي."""
    with get_session() as session:
        q = session.query(LegacyReport).filter(LegacyReport.status == 'بانتظار الفحص الأولي')
        if query:
            q = q.filter(LegacyReport.title.ilike(f"%{query.strip()}%"))
        rows = q.order_by(desc(LegacyReport.created_at)).all()
        return [
            {
                'id': r.id,
                'title': r.title,
                'author': r.author,
                'date': r.created_at.strftime('%Y-%m-%d %H:%M') if r.created_at else '',
                'overall_pct': r.overall_pct,
                'submitted_by': r.submitted_by,
                'notes': r.submitted_notes
            }
            for r in rows
        ]


def get_pending_initial_reviews_count() -> int:
    with get_session() as session:
        return session.query(LegacyReport).filter(LegacyReport.status == 'بانتظار الفحص الأولي').count()


def submit_report_to_admin(report_id: str, employee_name: str, notes: str):
    """إرسال بحث من موظف لمدير النظام للاعتماد."""
    with get_session() as session:
        rep = session.query(LegacyReport).filter(LegacyReport.id == report_id).first()
        if rep:
            rep.status = 'بانتظار الفحص الأولي'
            rep.submitted_by = employee_name
            rep.submitted_notes = notes


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
