# -*- coding: utf-8 -*-
"""
مسارات الفحص الأكاديمي والتحليل (Scan Routes)
"""

import os
import uuid
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename

import config
from app.services.scan_service import (
    start_async_scan,
    get_scan_status,
    _find_exact_reference_match,
)
from app.repositories import report_repo
from app.security.authorization import require_permission, get_authenticated_user
from app.security.permissions import Permission
from app.services import integrity_service, audit_service, upload_validation_service
from plagiarism_detector.reporting.report_builder import analyze_academic_document
from plagiarism_detector.extraction.page_extractor import extract_document_pages
from app.services.settings_service import get_current_settings

scan_bp = Blueprint('scan_bp', __name__)


@scan_bp.route('/api/scan', methods=['POST'])
@scan_bp.route('/api/analyze_async', methods=['POST'])
@require_permission(Permission.SCAN_START)
def start_scan_route():
    """بدء فحص أكاديمي غير متزامن (صلاحية scan.start)."""
    title = request.form.get('title', '').strip()
    author = request.form.get('author', '').strip()
    raw_text = request.form.get('text', '').strip()
    allow_rescan = request.form.get('allow_rescan', '0') in ('1', 'true', 'True')
    file_path = ''
    file_name = ''
    safe_stored_name = ''

    current_user = get_authenticated_user()

    if 'file' in request.files and request.files['file'].filename:
        file = request.files['file']
        orig_name = file.filename

        # تدقيق وتحصين الملف المرفوع في بيئة Staging
        val_res = upload_validation_service.validate_and_stage_upload(
            file_stream=file,
            original_filename=orig_name,
            max_bytes=config.MAX_UPLOAD_BYTES,
            allowed_extensions=config.ALLOWED_EXTENSIONS
        )

        file_hash = val_res['sha256']
        file_name = val_res['original_filename']
        if not title:
            title = os.path.splitext(file_name)[0]

        # فحص التكرار الدقيق قبل إطلاق الفحص المكلف
        if not allow_rescan and file_hash:
            dup_info = integrity_service.check_file_duplicate_in_repository(file_hash, current_user=current_user)
            if dup_info:
                upload_validation_service.cleanup_staging_file(val_res['staging_path'])
                audit_service.record_event(
                    action="research.duplicate_detected",
                    category="research",
                    object_type="research",
                    object_id=str(dup_info.get('existing_research_id', '')),
                    research_reference_number=dup_info.get('existing_research_reference', ''),
                    success=True,
                    metadata={
                        "filename": file_name,
                        "hash_prefix": file_hash[:16],
                        "scope": "existing_research"
                    }
                )
                return jsonify(dup_info), 200

        # النقل الذري من Staging إلى التخزين المعتمد
        final_res = upload_validation_service.finalize_validated_upload(
            val_res,
            target_dir=config.TEMP_UPLOAD_DIR
        )
        safe_stored_name = final_res['stored_filename']
        file_path = final_res['file_path']

        if allow_rescan and file_hash:
            audit_service.record_event(
                action="research.duplicate_rescan_requested",
                category="research",
                object_type="research",
                success=True,
                metadata={
                    "filename": file_name,
                    "hash_prefix": file_hash[:16],
                    "title": title
                }
            )

    task_id = start_async_scan(
        file_path=file_path,
        title=title,
        author=author,
        raw_text=raw_text,
        file_name=file_name
    )

    return jsonify({'task_id': task_id, 'status': 'queued'})


@scan_bp.route('/api/tasks/<task_id>', methods=['GET'])
@require_permission(Permission.RESEARCH_VIEW)
def get_task_status_route(task_id):
    """استعلام عن تقدم مهمة الفحص (صلاحية research.view)."""
    res = get_scan_status(task_id)
    if 'error' in res and res['error'] == 'المهمة غير موجودة':
        return jsonify(res), 404
    return jsonify(res)


@scan_bp.route('/api/analyze', methods=['POST'])
@require_permission(Permission.SCAN_START)
def analyze_sync_route():
    """فحص متزامن سريع للنصوص المباشرة (صلاحية scan.start)."""
    title = request.form.get('title', '').strip()
    author = request.form.get('author', '').strip()
    raw_text = request.form.get('text', '').strip()
    file_path = ''
    pages_data = []
    exact_reference_match = None

    if 'file' in request.files and request.files['file'].filename:
        file = request.files['file']
        orig_name = file.filename

        val_res = upload_validation_service.validate_and_stage_upload(
            file_stream=file,
            original_filename=orig_name,
            max_bytes=config.MAX_UPLOAD_BYTES,
            allowed_extensions=config.ALLOWED_EXTENSIONS
        )
        final_res = upload_validation_service.finalize_validated_upload(
            val_res,
            target_dir=config.TEMP_UPLOAD_DIR
        )
        file_path = final_res['file_path']
        file_name = final_res['original_filename']
        if not title:
            title = os.path.splitext(file_name)[0]

        exact_reference_match = _find_exact_reference_match(file_path)
        if exact_reference_match:
            pages_data = [dict(page) for page in exact_reference_match.get('pages', [])]
        else:
            pages_data = extract_document_pages(file_path, enable_ocr=True)
        if not raw_text:
            raw_text = '\n\n'.join(p['text'] for p in pages_data if p['text'])

    if not raw_text.strip():
        return jsonify({'error': 'لم يتم العثور على نص لتحليله'}), 400

    settings = get_current_settings()
    report = analyze_academic_document(
        raw_text=raw_text,
        pages_data=pages_data if pages_data else None,
        settings_override=settings,
        exact_reference_match=exact_reference_match,
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
