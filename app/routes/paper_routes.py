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

from app.security.permissions import Permission
from app.security.authorization import require_permission, require_any_permission

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
            'reference_number': r.get('reference_number', ''),
            'title': r['title'],
            'author': r.get('author', 'غير محدد'),
            'date': str(r['created_at'])[:16],
            'pct': r['overall_pct'],
            'status': r.get('status', 'مفحوص'),
            'scan_status': r.get('scan_status', 'completed'),
            'review_status': r.get('review_status', 'pending_review'),
            'scan_status_label': r.get('scan_status_label', 'مكتمل الفحص'),
            'review_status_label': r.get('review_status_label', 'قيد المراجعة')
        }
        for r in recent
    ]

    return jsonify({
        'total_papers': paper_count,
        'total_scans': stats['total_scans'],
        'avg_plagiarism': stats['avg_plagiarism'],
        'pending_initial_count': stats.get('pending_initial_count', 0),
        'pending_review_count': stats.get('pending_initial_count', 0),
        'preliminary_count': stats.get('preliminary_count', 0),
        'rejected_count': stats.get('rejected_count', 0),
        'final_count': stats.get('final_count', 0),
        'recent_reports': recent_reports
    })


@paper_bp.route('/api/papers', methods=['GET'])
@require_permission(Permission.REFERENCE_VIEW)
def list_papers():
    """عرض قائمة الأبحاث في قاعدة البيانات مع دعم البحث وترقيم الصفحات وتصفية الحالات (صلاحية reference.view)."""
    from app.utils.pagination import get_pagination_params
    params = get_pagination_params(
        default_size=25,
        max_size=100,
        allowed_sort_fields=['created_at', 'title', 'author', 'id', 'reference_id'],
        default_sort='id',
        default_order='desc'
    )

    status = request.args.get('status')
    pub_year = request.args.get('year')
    file_hash = request.args.get('file_hash')
    ref_id = request.args.get('reference_id')

    result = document_repo.get_all_documents(
        page=params['page'],
        per_page=params['page_size'],
        query=params['q'],
        status=status,
        publication_year=pub_year,
        file_hash=file_hash,
        reference_id=ref_id,
        date_from=params['date_from'],
        date_to=params['date_to'],
        sort_field=params['sort'],
        order_direction=params['order']
    )
    for p in result.get('items', []):
        ext = os.path.splitext(p.get('file_path', ''))[1].upper().replace('.', '')
        p['file_type'] = ext if ext else 'TXT'

    return jsonify(result)


@paper_bp.route('/api/papers', methods=['POST'])
@require_any_permission(Permission.REFERENCE_ADD, Permission.REFERENCE_MANAGE)
def add_paper():
    """إضافة مرجع جديد إلى قاعدة المراجع مع فحص التكرار وحجز النسخة الذرية (صلاحية reference.add / reference.manage)."""
    title = request.form.get('title', '').strip()
    author = request.form.get('author', '').strip()
    year = request.form.get('year', '').strip()
    publisher = request.form.get('publisher', '').strip()
    edition = request.form.get('edition', '').strip()
    document_type = request.form.get('document_type', 'paper').strip()
    source_category = request.form.get('source_category', 'academic').strip()
    category = request.form.get('category', '').strip()
    notes = request.form.get('notes', '').strip()
    ownership_note = request.form.get('ownership_note', '').strip()
    raw_text = request.form.get('text', '').strip()
    file_path = ''
    orig_name = ''

    if 'file' in request.files and request.files['file'].filename:
        file = request.files['file']
        orig_name = file.filename

        from app.services import upload_validation_service
        val_res = upload_validation_service.validate_and_stage_upload(
            file_stream=file,
            original_filename=orig_name,
            max_bytes=config.MAX_REFERENCE_UPLOAD_BYTES,
            allowed_extensions=config.ALLOWED_EXTENSIONS
        )
        final_res = upload_validation_service.finalize_validated_upload(
            validation_result=val_res,
            target_dir=config.TEMP_UPLOAD_DIR
        )
        file_path = final_res['file_path']
        if not title:
            title = os.path.splitext(final_res['original_filename'])[0]

    if not title:
        return jsonify({'error': 'عنوان البحث مطلوب', 'error_code': 'VALIDATION_ERROR'}), 400

    from app.services import corpus_governance_service
    res = corpus_governance_service.add_reference_document(
        title=title,
        author=author,
        year=year,
        publisher=publisher,
        edition=edition,
        document_type=document_type,
        source_category=source_category,
        category=category,
        file_path=file_path,
        raw_text=raw_text,
        original_filename=orig_name,
        added_by=getattr(request, 'current_user', {}).get('username', 'system') if hasattr(request, 'current_user') else 'system',
        notes=notes,
        ownership_note=ownership_note
    )

    if not res['success']:
        status_code = 409 if res.get('is_duplicate') else 400
        return jsonify({
            'error': res['error'],
            'error_code': res.get('error_code', 'VALIDATION_ERROR'),
            'is_duplicate': res.get('is_duplicate', False)
        }), status_code

    return jsonify(res)


@paper_bp.route('/api/papers/supersede', methods=['POST'])
@require_any_permission(Permission.REFERENCE_SUPERSEDE, Permission.REFERENCE_MANAGE)
def supersede_paper():
    """استبدال مرجع سابق بإصدار أحدث مع الحفاظ على المرجع السابق وأدلته التاريخية (صلاحية reference.supersede)."""
    old_ref_id = request.form.get('old_reference_id') or request.form.get('paper_id')
    if not old_ref_id:
        return jsonify({'error': 'معرف المرجع السابق مطلوب', 'error_code': 'VALIDATION_ERROR'}), 400

    title = request.form.get('title', '').strip()
    author = request.form.get('author', '').strip()
    year = request.form.get('year', '').strip()
    publisher = request.form.get('publisher', '').strip()
    edition = request.form.get('edition', '').strip()
    reason = request.form.get('reason', '').strip()
    raw_text = request.form.get('text', '').strip()
    file_path = ''
    orig_name = ''

    if 'file' in request.files and request.files['file'].filename:
        file = request.files['file']
        orig_name = file.filename
        from app.services import upload_validation_service
        val_res = upload_validation_service.validate_and_stage_upload(
            file_stream=file,
            original_filename=orig_name,
            max_bytes=config.MAX_REFERENCE_UPLOAD_BYTES,
            allowed_extensions=config.ALLOWED_EXTENSIONS
        )
        final_res = upload_validation_service.finalize_validated_upload(
            validation_result=val_res,
            target_dir=config.TEMP_UPLOAD_DIR
        )
        file_path = final_res['file_path']

    from app.services import corpus_governance_service
    res = corpus_governance_service.supersede_reference_document(
        old_reference_id_or_id=old_ref_id,
        new_file_path=file_path,
        new_raw_text=raw_text,
        new_title=title,
        new_author=author,
        new_year=year,
        new_publisher=publisher,
        new_edition=edition,
        original_filename=orig_name,
        actor=getattr(request, 'current_user', {}).get('username', 'system') if hasattr(request, 'current_user') else 'system',
        reason=reason
    )

    if not res['success']:
        status_code = 404 if res.get('error_code') == 'REFERENCE_NOT_FOUND' else 400
        return jsonify(res), status_code

    return jsonify(res)


@paper_bp.route('/api/papers/<paper_id>/retire', methods=['POST'])
@require_any_permission(Permission.REFERENCE_RETIRE, Permission.REFERENCE_MANAGE)
def retire_paper(paper_id):
    """إيقاف مرجع عن الفحوصات المستقبلية مع الحفاظ على ملفه وأدلته (صلاحية reference.retire)."""
    reason = request.form.get('reason', '') or (request.json.get('reason', '') if request.is_json else '')
    from app.services import corpus_governance_service
    actor = getattr(request, 'current_user', {}).get('username', 'system') if hasattr(request, 'current_user') else 'system'
    res = corpus_governance_service.retire_reference_document(
        reference_id_or_id=paper_id,
        actor=actor,
        reason=reason
    )
    if not res['success']:
        status_code = 404 if res.get('error_code') == 'REFERENCE_NOT_FOUND' else 400
        return jsonify(res), status_code
    return jsonify(res)


@paper_bp.route('/api/papers/<paper_id>/reactivate', methods=['POST'])
@require_any_permission(Permission.REFERENCE_REACTIVATE, Permission.REFERENCE_MANAGE)
def reactivate_paper(paper_id):
    """إعادة تفعيل مرجع موقوف بعد التحقق من نزاهة ملفه (صلاحية reference.reactivate)."""
    reason = request.form.get('reason', '') or (request.json.get('reason', '') if request.is_json else '')
    from app.services import corpus_governance_service
    actor = getattr(request, 'current_user', {}).get('username', 'system') if hasattr(request, 'current_user') else 'system'
    res = corpus_governance_service.reactivate_reference_document(
        reference_id_or_id=paper_id,
        actor=actor,
        reason=reason
    )
    if not res['success']:
        status_code = 404 if res.get('error_code') == 'REFERENCE_NOT_FOUND' else 400
        return jsonify(res), status_code
    return jsonify(res)


@paper_bp.route('/api/papers/<paper_id>/verify-integrity', methods=['POST', 'GET'])
@require_any_permission(Permission.REFERENCE_INTEGRITY_VERIFY, Permission.REFERENCE_MANAGE)
def verify_paper_integrity(paper_id):
    """التحقق الصارم من نزاهة ملف المرجع ووجوده ومطابقة الهاش (صلاحية reference.integrity.verify)."""
    from app.services import corpus_governance_service
    res = corpus_governance_service.verify_reference_integrity(reference_id_or_id=paper_id)
    if not res['success']:
        status_code = 404 if res.get('error_code') == 'REFERENCE_NOT_FOUND' else 422
        return jsonify(res), status_code
    return jsonify(res)


@paper_bp.route('/api/papers/<paper_id>/history', methods=['GET'])
@require_permission(Permission.REFERENCE_VIEW)
def get_paper_history(paper_id):
    """استرجاع سجل التعديلات الوصفية والحركات المؤسسية لمرجع محدد (صلاحية reference.view)."""
    from app.services import corpus_governance_service
    res = corpus_governance_service.get_reference_history(paper_id)
    if not res['success']:
        return jsonify(res), 404
    return jsonify(res)


@paper_bp.route('/api/corpus/status', methods=['GET'])
@require_permission(Permission.REFERENCE_VIEW)
def get_corpus_status():
    """استرجاع إصدار قاعدة المراجع، البصمة الرقمية، وحالة فهرس الاسترجاع (صلاحية reference.view)."""
    from app.services import corpus_governance_service
    info = corpus_governance_service.get_current_corpus_info()
    return jsonify(info)


@paper_bp.route('/api/corpus/reindex', methods=['POST'])
@require_any_permission(Permission.REFERENCE_CORPUS_MANAGE, Permission.REFERENCE_MANAGE)
def rebuild_corpus_index():
    """إعادة بناء فهرس الاسترجاع لقاعدة المراجع النشطة يدوياً (صلاحية reference.corpus.manage)."""
    try:
        from plagiarism_detector.reporting.report_builder import build_pipeline_index
        idx_data = build_pipeline_index()
        return jsonify({
            'success': True,
            'message': 'تمت إعادة بناء وتحديث فهرس الاسترجاع بنجاح',
            'total_segments': idx_data.get('total_segments', 0),
            'index_corpus_version': idx_data.get('index_corpus_version', ''),
            'index_fingerprint': idx_data.get('index_fingerprint', '')
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'فشلت إعادة بناء الفهرس: {e}',
            'error_code': 'CORPUS_INDEX_BUILD_FAILED'
        }), 500


@paper_bp.route('/api/papers/<paper_id>', methods=['DELETE'])
@require_any_permission(Permission.REFERENCE_RETIRE, Permission.REFERENCE_MANAGE)
def delete_paper(paper_id):
    """إيقاف بحث مرجعي وتحديث الفهرس (صلاحية reference.retire / reference.manage)."""
    from app.services import corpus_governance_service
    actor = getattr(request, 'current_user', {}).get('username', 'system') if hasattr(request, 'current_user') else 'system'
    res = corpus_governance_service.retire_reference_document(
        reference_id_or_id=paper_id,
        actor=actor,
        reason="طلب إيقاف عبر مسار الحذف"
    )
    if not res.get('success'):
        return jsonify(res), 404
    return jsonify({'success': True, 'message': 'تم إيقاف المرجع بنجاح وحفظ أدلته التاريخية'})


@paper_bp.route('/api/papers/<paper_id>/update', methods=['POST', 'PUT'])
@require_any_permission(Permission.REFERENCE_METADATA_EDIT, Permission.REFERENCE_MANAGE)
def update_paper(paper_id):
    """تعديل بيانات بحث مرجعي وتوثيق التعديل في سجل التاريخ (صلاحية reference.metadata.edit)."""
    data = request.form if request.form else (request.get_json(silent=True) or {})
    title = data.get('title')
    author = data.get('author')
    category = data.get('category')
    year = data.get('year')
    publisher = data.get('publisher')
    edition = data.get('edition')
    notes = data.get('notes')
    reason = data.get('reason', 'تحديث عبر واجهة إدارة المراجع')

    from app.services import corpus_governance_service
    actor = getattr(request, 'current_user', {}).get('username', 'system') if hasattr(request, 'current_user') else 'system'
    updates = {}
    if title is not None:
        updates['title'] = title
    if author is not None:
        updates['author'] = author
    if category is not None:
        updates['category'] = category
    if year is not None:
        updates['year'] = year
    if publisher is not None:
        updates['publisher'] = publisher
    if edition is not None:
        updates['edition'] = edition
    if notes is not None:
        updates['notes'] = notes

    res = corpus_governance_service.edit_reference_metadata(
        reference_id_or_id=paper_id,
        updates=updates,
        actor=actor,
        reason=reason
    )
    if not res.get('success'):
        return jsonify(res), 404
    return jsonify(res)


@paper_bp.route('/api/clear-db', methods=['POST', 'DELETE'])
@require_permission(Permission.SYSTEM_MAINTENANCE)
def clear_db():
    """حذف كافة المراجع والبيانات (صلاحية system.maintenance)."""
    document_repo.clear_all_documents()
    invalidate_pipeline_index()
    build_pipeline_index()
    return jsonify({'success': True, 'message': 'تم تفريغ كافة المراجع بنجاح'})

