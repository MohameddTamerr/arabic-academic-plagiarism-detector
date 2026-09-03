# -*- coding: utf-8 -*-
"""
مسارات التقارير ودورة اعتماد الأبحاث الأكاديمية (Report Routes):
- عرض التقارير وتصديرها بصيغة HTML جاهزة للطباعة.
- إدارة طابور الفحص الأولي للمدير، والقبول المبدئي، والرفض، والقبول النهائي.
"""

import os
from flask import Blueprint, request, jsonify, Response
from werkzeug.utils import secure_filename

import config
from app.repositories import report_repo, document_repo
from app.services.paper_service import import_reference_paper
from plagiarism_detector.extraction.page_extractor import extract_text, extract_document_pages
from plagiarism_detector.preprocessing.cheating_detector import clean_cheating_text
from plagiarism_detector.reporting.html_exporter import export_report_to_html

report_bp = Blueprint('report_bp', __name__)


@report_bp.route('/api/reports/<report_id>', methods=['GET'])
def get_report_route(report_id):
    """استرجاع تقرير فحص سابق."""
    report = report_repo.get_report(report_id)
    if not report:
        return jsonify({'error': 'التقرير غير موجود'}), 404
    return jsonify(report)


@report_bp.route('/api/reports/<report_id>', methods=['DELETE'])
def delete_report_route(report_id):
    """حذف تقرير من الأرشيف."""
    report_repo.delete_report(report_id)
    return jsonify({'success': True})


@report_bp.route('/api/reports/<report_id>/submit_to_admin', methods=['POST'])
def submit_to_admin(report_id):
    """إرسال بحث من موظف لمدير النظام للاعتماد والفحص الأولي."""
    data = request.get_json(silent=True) or request.form or {}
    emp_name = data.get('employee_name', 'موظف الفحص').strip()
    notes = data.get('notes', '').strip()

    report = report_repo.get_report(report_id)
    if not report:
        return jsonify({'error': 'التقرير غير موجود'}), 404

    report_repo.submit_report_to_admin(report_id, emp_name, notes)
    return jsonify({
        'success': True,
        'id': report_id,
        'status': 'بانتظار الفحص الأولي',
        'message': 'تم إرسال البحث بنجاح إلى مدير النظام للفحص الأولي واتخاذ القرار.'
    })


@report_bp.route('/api/initial_reviews', methods=['GET'])
def get_initial_reviews():
    """استرجاع قائمة الأبحاث المنتظرة في طابور الفحص الأولي."""
    q = request.args.get('q', '').strip()
    papers = report_repo.get_pending_initial_reviews(q)
    return jsonify({'papers': papers, 'count': len(papers)})


@report_bp.route('/api/initial_reviews/count', methods=['GET'])
def get_initial_reviews_count():
    """عدد الأبحاث المعلقة لتحديث شارة الإشعارات."""
    return jsonify({'count': report_repo.get_pending_initial_reviews_count()})


@report_bp.route('/api/reports/<report_id>/initial_accept', methods=['POST'])
def initial_accept(report_id):
    """قبول مبدئي للبحث."""
    report = report_repo.get_report(report_id)
    if not report:
        return jsonify({'error': 'التقرير غير موجود'}), 404
    report_repo.set_report_status(report_id, 'قبول مبدئي')
    return jsonify({'success': True, 'id': report_id, 'status': 'قبول مبدئي'})


@report_bp.route('/api/reports/<report_id>/reject', methods=['POST'])
def reject_report(report_id):
    """رفض البحث."""
    report = report_repo.get_report(report_id)
    if not report:
        return jsonify({'error': 'التقرير غير موجود'}), 404
    report_repo.set_report_status(report_id, 'مرفوض')
    return jsonify({'success': True, 'id': report_id, 'status': 'مرفوض'})


@report_bp.route('/api/preliminary_papers', methods=['GET'])
def get_preliminary():
    return jsonify({'papers': report_repo.get_preliminary_reports()})


@report_bp.route('/api/rejected_papers', methods=['GET'])
def get_rejected():
    return jsonify({'papers': report_repo.get_rejected_reports()})


@report_bp.route('/api/reports/<report_id>/upload_latest_pdf', methods=['POST'])
def upload_latest_pdf(report_id):
    """رفع أحدث نسخة معدلة لبحث مقبول مبدئياً."""
    report = report_repo.get_report(report_id)
    if not report:
        return jsonify({'error': 'التقرير غير موجود'}), 404

    if 'file' not in request.files or not request.files['file'].filename:
        return jsonify({'error': 'لم يتم اختيار ملف PDF جديد'}), 400

    file = request.files['file']
    filename = secure_filename(file.filename) or 'document.pdf'
    save_path = config.TEMP_UPLOAD_DIR / f"latest_{report_id}_{filename}"
    file.save(save_path)

    extracted_text = extract_text(str(save_path))
    cleaned = clean_cheating_text(extracted_text) if extracted_text else ''

    report_repo.update_report_latest_pdf(report_id, str(save_path), cleaned)
    return jsonify({'success': True, 'file_path': str(save_path), 'text_length': len(cleaned)})


@report_bp.route('/api/reports/<report_id>/final_accept', methods=['POST'])
@report_bp.route('/api/accept_paper/<report_id>', methods=['POST'])
def final_accept(report_id):
    """القبول النهائي للبحث وإدراجه رسمياً في قاعدة المراجع المعتمدة."""
    report = report_repo.get_report(report_id)
    if not report:
        return jsonify({'error': 'التقرير غير موجود'}), 404

    title = report.get('title', 'بحث بدون عنوان')
    author = report.get('author', 'غير محدد')
    category = report.get('category', 'عام')
    final_file = report.get('final_file_path') or report.get('file_path', '')
    final_text = report.get('final_full_text', '')

    if not final_text and 'segments' in report and report['segments']:
        final_text = ' '.join(s.get('text', '') for s in report['segments'])

    res = import_reference_paper(
        title=f"{title} (معتمد نهائي)",
        author=author,
        category=category,
        file_path=final_file,
        raw_text=final_text
    )

    report_repo.set_report_status(report_id, 'قبول نهائي')
    return jsonify({'success': True, 'paper_id': res.get('id'), 'title': title, 'author': author})


@report_bp.route('/api/export_html/<report_id>', methods=['GET'])
def export_html(report_id):
    """تصدير التقرير كملف HTML ملون ومناسب للطباعة الرسمية."""
    report = report_repo.get_report(report_id)
    if not report:
        return jsonify({'error': 'التقرير غير موجود'}), 404

    html_content = export_report_to_html(report)
    response = Response(html_content, mimetype='text/html; charset=utf-8')
    response.headers['Content-Disposition'] = f'attachment; filename="academic_report_{report_id}.html"'
    return response
