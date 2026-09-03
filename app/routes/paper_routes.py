# -*- coding: utf-8 -*-
"""
مسارات إدارة الأبحاث المرجعية ولوحة الإحصائيات (Paper Routes):
- تصفح وإضافة الأبحاث مع منع التكرار عبر SHA-256 Hash.
- تحديث وحذف الأبحاث وإعادة بناء الفهرس.
"""

import os
import uuid
from pathlib import Path
from werkzeug.utils import secure_filename
from flask import Blueprint, request, jsonify

import config
from app.repositories import document_repo, report_repo
from app.services.paper_service import import_reference_paper
from plagiarism_detector.reporting.report_builder import invalidate_pipeline_index, build_pipeline_index

paper_bp = Blueprint('paper_bp', __name__)


@paper_bp.route('/api/stats', methods=['GET'])
def get_stats():
    """استرجاع إحصائيات لوحة التحكم الحقيقية من قاعدة البيانات."""
    paper_count = document_repo.get_document_count()
    stats = report_repo.get_reports_stats()
    recent = report_repo.get_recent_reports(limit=10)

    recent_reports = [
        {
            'id': r['id'],
            'title': r['title'],
            'author': r.get('author', 'غير محدد'),
            'date': str(r['created_at'])[:16],
            'pct': r['overall_pct'],
            'status': r.get('status', 'مفحوص')
        }
        for r in recent
    ]

    return jsonify({
        'total_papers': paper_count,
        'total_scans': stats['total_scans'],
        'avg_plagiarism': stats['avg_plagiarism'],
        'preliminary_count': stats.get('preliminary_count', 0),
        'final_count': stats.get('final_count', 0),
        'pending_initial_count': stats.get('pending_initial_count', 0),
        'recent_reports': recent_reports
    })


@paper_bp.route('/api/papers', methods=['GET'])
def list_papers():
    """عرض قائمة الأبحاث في قاعدة البيانات مع دعم البحث وترقيم الصفحات."""
    query = request.args.get('q', '').strip()
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 10))

    result = document_repo.get_all_documents(page=page, per_page=per_page, query=query)
    for p in result['papers']:
        ext = os.path.splitext(p.get('file_path', ''))[1].upper().replace('.', '')
        p['file_type'] = ext if ext else 'TXT'

    return jsonify(result)


@paper_bp.route('/api/papers', methods=['POST'])
def add_paper():
    """إضافة بحث جديد إلى قاعدة البيانات مع فحص التكرار (SHA-256)."""
    title = request.form.get('title', '').strip()
    author = request.form.get('author', '').strip()
    category = request.form.get('category', '').strip()
    raw_text = request.form.get('text', '').strip()
    file_path = ''

    if 'file' in request.files and request.files['file'].filename:
        file = request.files['file']
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in config.ALLOWED_EXTENSIONS:
            return jsonify({'error': f"نوع الملف غير مدعوم ({ext}). الصيغ المسموح بها هي: PDF, DOCX, TXT"}), 400

        orig_name = secure_filename(file.filename) or f"upload_{uuid.uuid4().hex[:6]}.pdf"
        if not title:
            title = os.path.splitext(orig_name)[0]

        save_path = config.TEMP_UPLOAD_DIR / f"{uuid.uuid4().hex[:6]}_{orig_name}"
        file.save(save_path)
        file_path = str(save_path)

    if not title:
        return jsonify({'error': 'عنوان البحث مطلوب'}), 400

    res = import_reference_paper(
        title=title,
        author=author,
        category=category,
        file_path=file_path,
        raw_text=raw_text
    )

    if not res['success']:
        status_code = 409 if res.get('is_duplicate') else 400
        return jsonify({'error': res['error'], 'is_duplicate': res.get('is_duplicate', False)}), status_code

    return jsonify(res)


@paper_bp.route('/api/papers/<int:paper_id>', methods=['DELETE'])
def delete_paper(paper_id):
    """حذف بحث مرجعي وتحديث الفهرس."""
    document_repo.delete_document(paper_id)
    invalidate_pipeline_index()
    build_pipeline_index()
    return jsonify({'success': True})


@paper_bp.route('/api/papers/<int:paper_id>/update', methods=['POST', 'PUT'])
def update_paper(paper_id):
    """تعديل بيانات بحث مرجعي."""
    title = request.form.get('title')
    author = request.form.get('author')
    category = request.form.get('category')
    year = request.form.get('year')

    document_repo.update_document(paper_id, title=title, author=author, category=category, year=year)
    invalidate_pipeline_index()
    build_pipeline_index()
    return jsonify({'success': True})


@paper_bp.route('/api/clear-db', methods=['POST', 'DELETE'])
def clear_db():
    """حذف كافة المراجع والبيانات."""
    document_repo.clear_all_documents()
    invalidate_pipeline_index()
    build_pipeline_index()
    return jsonify({'success': True, 'message': 'تم تفريغ كافة المراجع بنجاح'})
