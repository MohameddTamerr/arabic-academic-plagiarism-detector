# -*- coding: utf-8 -*-
"""
مسارات الفحص الأكاديمي ومهام المعالجة (Scan Routes):
- فحص غير متزامن في الخلفية لضمان عدم توقف المتصفح.
- فحص فوري متزامن للنصوص القصيرة.
- استعلام ومتابعة التقدم.
"""

import os
import uuid
from werkzeug.utils import secure_filename
from flask import Blueprint, request, jsonify

import config
from app.services.scan_service import start_async_scan, get_scan_status
from plagiarism_detector.extraction.page_extractor import extract_document_pages
from plagiarism_detector.reporting.report_builder import analyze_academic_document
from app.services.settings_service import get_current_settings
from app.repositories import report_repo

scan_bp = Blueprint('scan_bp', __name__)


@scan_bp.route('/api/analyze_async', methods=['POST'])
def analyze_async_route():
    """بدء فحص أكاديمي غير متزامن في الخلفية."""
    title = request.form.get('title', '').strip()
    author = request.form.get('author', '').strip()
    raw_text = request.form.get('text', '').strip()
    file_name = ''
    file_path = ''

    if 'file' in request.files and request.files['file'].filename:
        file = request.files['file']
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in config.ALLOWED_EXTENSIONS:
            return jsonify({'error': f"نوع الملف غير مدعوم ({ext}). الصيغ المسموح بها هي: PDF, DOCX, TXT"}), 400

        file_name = secure_filename(file.filename) or 'document.pdf'
        if not title:
            title = os.path.splitext(file_name)[0]

        save_path = config.TEMP_UPLOAD_DIR / f"{uuid.uuid4().hex[:6]}_{file_name}"
        file.save(save_path)
        file_path = str(save_path)

    task_id = start_async_scan(
        file_path=file_path,
        title=title,
        author=author,
        raw_text=raw_text,
        file_name=file_name
    )

    return jsonify({'task_id': task_id, 'status': 'queued'})


@scan_bp.route('/api/tasks/<task_id>', methods=['GET'])
def get_task_status_route(task_id):
    """استعلام عن تقدم مهمة الفحص."""
    res = get_scan_status(task_id)
    if 'error' in res and res['error'] == 'المهمة غير موجودة':
        return jsonify(res), 404
    return jsonify(res)


@scan_bp.route('/api/analyze', methods=['POST'])
def analyze_sync_route():
    """فحص متزامن سريع للنصوص المباشرة."""
    title = request.form.get('title', '').strip()
    author = request.form.get('author', '').strip()
    raw_text = request.form.get('text', '').strip()
    file_path = ''
    pages_data = []

    if 'file' in request.files and request.files['file'].filename:
        file = request.files['file']
        file_name = secure_filename(file.filename) or 'document.pdf'
        if not title:
            title = os.path.splitext(file_name)[0]

        save_path = config.TEMP_UPLOAD_DIR / f"{uuid.uuid4().hex[:6]}_{file_name}"
        file.save(save_path)
        file_path = str(save_path)
        pages_data = extract_document_pages(file_path, enable_ocr=True)
        if not raw_text:
            raw_text = '\n\n'.join(p['text'] for p in pages_data if p['text'])

    if not raw_text.strip():
        return jsonify({'error': 'لم يتم العثور على نص لتحليله'}), 400

    settings = get_current_settings()
    report = analyze_academic_document(
        raw_text=raw_text,
        pages_data=pages_data if pages_data else None,
        settings_override=settings
    )

    report_id = str(uuid.uuid4())[:8]
    now_str = os.getenv('CURRENT_DATE', '2026-09-02 14:00')

    report['id'] = report_id
    report['title'] = title or 'بحث جديد'
    report['author'] = author or 'غير محدد'
    report['date'] = now_str
    report['file_path'] = file_path
    report['status'] = 'مفحوص'

    report_repo.save_report(
        report_id=report_id,
        title=report['title'],
        overall_pct=report['overall_pct'],
        copied_pct=report['copied_pct'],
        para_pct=report['paraphrase_pct'],
        report_dict=report,
        status='مفحوص',
        author=report['author'],
        file_path=file_path
    )

    return jsonify(report)
