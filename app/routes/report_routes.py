# -*- coding: utf-8 -*-
"""
مسارات التقارير ودورة اعتماد الأبحاث الأكاديمية (Report Routes):
- عرض التقارير وتصديرها بصيغة HTML جاهزة للطباعة مع توثيق التدقيق.
- إدارة طابور الفحص الأولي للمدير، والقبول المبدئي، والرفض، والقبول النهائي.
"""

import os
from flask import Blueprint, request, jsonify, Response
from werkzeug.utils import secure_filename

import config
from app.repositories import report_repo, document_repo, batch_repo
from app.services import audit_service
from app.services.paper_service import import_reference_paper
from plagiarism_detector.extraction.page_extractor import extract_text
from plagiarism_detector.preprocessing.cheating_detector import clean_cheating_text
from plagiarism_detector.reporting.html_exporter import export_report_to_html
from app.security.permissions import Permission
from app.security.authorization import require_permission

report_bp = Blueprint('report_bp', __name__)


@report_bp.route('/api/reports/<report_id>', methods=['GET'])
@require_permission(Permission.REPORT_VIEW)
def get_report_route(report_id):
    """استرجاع تقرير فحص سابق وتوثيق استعراض التقرير (صلاحية report.view)."""
    report = report_repo.get_report(report_id)
    if not report:
        return jsonify({'error': 'التقرير غير موجود'}), 404

    # تسجيل حدث فتح التقرير إذا كان الطلب من مستخدم وليس استعلاماً خلفياً متكرراً
    if request.headers.get('X-Track-Open', '').lower() == 'true' or request.args.get('track', '').lower() == '1':
        audit_service.record_event(
            action="report.opened",
            category="report",
            object_type="report",
            object_id=report_id,
            report_id=report_id,
            research_id=report.get('research_id'),
            research_reference_number=report.get('reference_number', ''),
            success=True,
            metadata={'title': report.get('title', '')}
        )

    return jsonify(report)


@report_bp.route('/api/reports/<report_id>', methods=['DELETE'])
@require_permission(Permission.USERS_MANAGE)
def delete_report_route(report_id):
    """حذف تقرير من الأرشيف وتوثيق الحدث (صلاحية users.manage)."""
    report = report_repo.get_report(report_id)
    if not report:
        return jsonify({'error': 'التقرير غير موجود'}), 404

    from app.errors.error_codes import ErrorCode
    if report.get('artifact_status') == 'finalized' and request.args.get('force_maintenance', '').lower() != 'true':
        return jsonify({
            'success': False,
            'error': 'لا يمكن حذف تقرير معتمد رسمياً. يجب إبطال التقرير أولاً للحفاظ على سلسلة التدقيق المؤسسية.',
            'code': ErrorCode.VALIDATION_ERROR
        }), 400

    ref_num = report.get('reference_number', '') if report else ''
    res_id = report.get('research_id') if report else None

    report_repo.delete_report(report_id, allow_finalized=True)

    audit_service.record_event(
        action="report.deleted",
        category="report",
        object_type="report",
        object_id=report_id,
        report_id=report_id,
        research_id=res_id,
        research_reference_number=ref_num,
        success=True
    )
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

    audit_service.record_event(
        action="review.submitted_to_admin",
        category="review",
        object_type="report",
        object_id=report_id,
        report_id=report_id,
        research_id=report.get('research_id'),
        research_reference_number=report.get('reference_number', ''),
        success=True,
        metadata={'employee_name': emp_name, 'notes': notes, 'previous_status': report.get('status')}
    )

    return jsonify({
        'success': True,
        'id': report_id,
        'status': 'بانتظار الفحص الأولي',
        'message': 'تم إرسال البحث بنجاح إلى مدير النظام للفحص الأولي واتخاذ القرار.'
    })


@report_bp.route('/api/initial_reviews', methods=['GET'])
@require_permission(Permission.REVIEW_PRELIMINARY)
def get_initial_reviews():
    """استرجاع قائمة الأبحاث المنتظرة في طابور الفحص الأولي مع دعم التقسيم والبحث وفلترة التواريخ."""
    from app.utils.pagination import get_pagination_params, format_paginated_response
    params = get_pagination_params(default_size=25, max_size=100)
    
    # إذا لم يُحدد العميل معيار page_size صراحة وكان طلباً موروثاً
    has_page_param = 'page' in request.args or 'page_size' in request.args or 'per_page' in request.args
    limit_val = params['limit'] if has_page_param else None
    offset_val = params['offset'] if has_page_param else 0

    papers, total_count = report_repo.get_pending_initial_reviews(
        query=params['q'],
        date_from=params['date_from'],
        date_to=params['date_to'],
        offset=offset_val,
        limit=limit_val,
        as_tuple=True
    )

    resp = format_paginated_response(
        items=papers,
        total_items=total_count,
        page=params['page'],
        page_size=params['page_size'] if has_page_param else total_count or 1,
        legacy_key='papers'
    )
    resp['count'] = total_count
    return jsonify(resp)


@report_bp.route('/api/initial_reviews/count', methods=['GET'])
def get_initial_reviews_count():
    """عدد الأبحاث المعلقة لتحديث شارة الإشعارات."""
    return jsonify({'count': report_repo.get_pending_initial_reviews_count()})


@report_bp.route('/api/reports', methods=['GET'])
@require_permission(Permission.REPORT_VIEW)
def list_reports_paginated():
    """استرجاع وبحث قائمة التقارير الأكاديمية المفحوصة مع التقسيم والفلترة (صلاحية report.view)."""
    from app.utils.pagination import get_pagination_params, format_paginated_response
    params = get_pagination_params(
        default_size=25,
        max_size=100,
        allowed_sort_fields=['created_at', 'title', 'overall_pct', 'review_status'],
        default_sort='created_at',
        default_order='desc'
    )

    review_status = request.args.get('review_status')
    scan_status = request.args.get('scan_status')

    items, total_count = report_repo.search_reports(
        query=params['q'],
        review_status=review_status,
        scan_status=scan_status,
        date_from=params['date_from'],
        date_to=params['date_to'],
        sort_field=params['sort'],
        order_direction=params['order'],
        offset=params['offset'],
        limit=params['limit']
    )

    return jsonify(format_paginated_response(
        items=items,
        total_items=total_count,
        page=params['page'],
        page_size=params['page_size'],
        legacy_key='reports'
    ))


@report_bp.route('/api/reports/<report_id>/initial_accept', methods=['POST'])
@require_permission(Permission.REVIEW_PRELIMINARY)
def initial_accept(report_id):
    """قبول مبدئي للبحث مع التحقق من صحة الانتقال (صلاحية review.preliminary)."""
    report = report_repo.get_report(report_id)
    if not report:
        return jsonify({'error': 'التقرير غير موجود'}), 404

    prev_review_status = report.get('review_status', 'pending_review')
    prev_status = report.get('status', 'مفحوص')

    success, err_msg = report_repo.update_report_review_status(report_id, 'preliminary_accepted')
    if not success:
        return jsonify({'error': err_msg or 'انتقال تحكيمي غير قانوني'}), 400

    audit_service.record_event(
        action="review.preliminary_accepted",
        category="review",
        object_type="report",
        object_id=report_id,
        report_id=report_id,
        research_id=report.get('research_id'),
        research_reference_number=report.get('reference_number', ''),
        success=True,
        metadata={
            'previous_review_status': prev_review_status,
            'new_review_status': 'preliminary_accepted',
            'previous_status': prev_status,
            'new_status': 'قبول مبدئي'
        }
    )

    return jsonify({
        'success': True,
        'id': report_id,
        'scan_status': report.get('scan_status', 'completed'),
        'review_status': 'preliminary_accepted',
        'status': 'قبول مبدئي'
    })


@report_bp.route('/api/reports/<report_id>/reject', methods=['POST'])
@require_permission(Permission.REVIEW_REJECT)
def reject_report(report_id):
    """رفض البحث أكاديمياً مع التحقق من صحة الانتقال (صلاحية review.reject)."""
    report = report_repo.get_report(report_id)
    if not report:
        return jsonify({'error': 'التقرير غير موجود'}), 404

    prev_review_status = report.get('review_status', 'pending_review')
    prev_status = report.get('status', 'مفحوص')

    success, err_msg = report_repo.update_report_review_status(report_id, 'rejected')
    if not success:
        return jsonify({'error': err_msg or 'انتقال تحكيمي غير قانوني'}), 400

    audit_service.record_event(
        action="review.rejected",
        category="review",
        object_type="report",
        object_id=report_id,
        report_id=report_id,
        research_id=report.get('research_id'),
        research_reference_number=report.get('reference_number', ''),
        success=True,
        metadata={
            'previous_review_status': prev_review_status,
            'new_review_status': 'rejected',
            'previous_status': prev_status,
            'new_status': 'مرفوض'
        }
    )

    return jsonify({
        'success': True,
        'id': report_id,
        'scan_status': report.get('scan_status', 'completed'),
        'review_status': 'rejected',
        'status': 'مرفوض'
    })


@report_bp.route('/api/preliminary_papers', methods=['GET'])
@require_permission(Permission.REPORT_VIEW)
def get_preliminary():
    """استرجاع الأبحاث المقبولة مبدئياً مع دعم التقسيم والبحث والفلترة."""
    from app.utils.pagination import get_pagination_params, format_paginated_response
    params = get_pagination_params(default_size=25, max_size=100)

    has_page_param = 'page' in request.args or 'page_size' in request.args or 'per_page' in request.args
    limit_val = params['limit'] if has_page_param else None
    offset_val = params['offset'] if has_page_param else 0

    papers, total_count = report_repo.get_preliminary_reports(
        query=params['q'],
        date_from=params['date_from'],
        date_to=params['date_to'],
        offset=offset_val,
        limit=limit_val,
        as_tuple=True
    )

    resp = format_paginated_response(
        items=papers,
        total_items=total_count,
        page=params['page'],
        page_size=params['page_size'] if has_page_param else total_count or 1,
        legacy_key='papers'
    )
    resp['count'] = total_count
    return jsonify(resp)


@report_bp.route('/api/rejected_papers', methods=['GET'])
@require_permission(Permission.REPORT_VIEW)
def get_rejected():
    """استرجاع الأبحاث المرفوضة مع دعم التقسيم والبحث والفلترة."""
    from app.utils.pagination import get_pagination_params, format_paginated_response
    params = get_pagination_params(default_size=25, max_size=100)

    has_page_param = 'page' in request.args or 'page_size' in request.args or 'per_page' in request.args
    limit_val = params['limit'] if has_page_param else None
    offset_val = params['offset'] if has_page_param else 0

    papers, total_count = report_repo.get_rejected_reports(
        query=params['q'],
        date_from=params['date_from'],
        date_to=params['date_to'],
        offset=offset_val,
        limit=limit_val,
        as_tuple=True
    )

    resp = format_paginated_response(
        items=papers,
        total_items=total_count,
        page=params['page'],
        page_size=params['page_size'] if has_page_param else total_count or 1,
        legacy_key='papers'
    )
    resp['count'] = total_count
    return jsonify(resp)


@report_bp.route('/api/reports/<report_id>/upload_latest_pdf', methods=['POST'])
@require_permission(Permission.RESEARCH_UPLOAD)
def upload_latest_pdf(report_id):
    """رفع أحدث نسخة معدلة لبحث مقبول مبدئياً (صلاحية research.upload)."""
    report = report_repo.get_report(report_id)
    if not report:
        return jsonify({'error': 'التقرير غير موجود'}), 404

    if 'file' not in request.files or not request.files['file'].filename:
        return jsonify({'error': 'لم يتم اختيار ملف PDF جديد'}), 400

    file = request.files['file']
    orig_name = file.filename

    from app.services import upload_validation_service
    val_res = upload_validation_service.validate_and_stage_upload(
        file_stream=file,
        original_filename=orig_name,
        max_bytes=config.MAX_UPLOAD_BYTES,
        allowed_extensions=config.ALLOWED_EXTENSIONS
    )
    final_res = upload_validation_service.finalize_validated_upload(
        validation_result=val_res,
        target_dir=config.TEMP_UPLOAD_DIR
    )
    save_path = final_res['file_path']
    filename = final_res['original_filename']

    extracted_text = extract_text(str(save_path))
    cleaned = clean_cheating_text(extracted_text) if extracted_text else ''

    report_repo.update_report_latest_pdf(report_id, str(save_path), cleaned)

    audit_service.record_event(
        action="research.latest_pdf_uploaded",
        category="research",
        object_type="report",
        object_id=report_id,
        report_id=report_id,
        research_id=report.get('research_id'),
        research_reference_number=report.get('reference_number', ''),
        success=True,
        metadata={'filename': filename}
    )

    return jsonify({'success': True, 'file_path': str(save_path), 'text_length': len(cleaned)})


@report_bp.route('/api/reports/<report_id>/final_accept', methods=['POST'])
@report_bp.route('/api/accept_paper/<report_id>', methods=['POST'])
@require_permission(Permission.REVIEW_FINAL)
def final_accept(report_id):
    """القبول النهائي للبحث وإدراجه رسمياً في قاعدة المراجع المعتمدة (صلاحية review.final)."""
    report = report_repo.get_report(report_id)
    if not report:
        return jsonify({'error': 'التقرير غير موجود'}), 404

    prev_review_status = report.get('review_status', 'pending_review')
    prev_status = report.get('status', 'مفحوص')

    success, err_msg = report_repo.update_report_review_status(report_id, 'final_accepted')
    if not success:
        return jsonify({'error': err_msg or 'انتقال تحكيمي غير قانوني'}), 400

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

    audit_service.record_event(
        action="review.final_accepted",
        category="review",
        object_type="report",
        object_id=report_id,
        report_id=report_id,
        research_id=report.get('research_id'),
        research_reference_number=report.get('reference_number', ''),
        success=True,
        metadata={
            'title': title,
            'author': author,
            'previous_review_status': prev_review_status,
            'new_review_status': 'final_accepted',
            'previous_status': prev_status,
            'new_status': 'قبول نهائي',
            'indexed_doc_id': res.get('id')
        }
    )

    return jsonify({
        'success': True,
        'paper_id': res.get('id'),
        'title': title,
        'author': author,
        'scan_status': report.get('scan_status', 'completed'),
        'review_status': 'final_accepted',
        'status': 'قبول نهائي'
    })


@report_bp.route('/api/export_html/<report_id>', methods=['GET'])
@require_permission(Permission.REPORT_EXPORT)
def export_html(report_id):
    """تصدير التقرير كملف HTML ملون ومناسب للطباعة الرسمية (صلاحية report.export)."""
    report = report_repo.get_report(report_id)
    if not report:
        return jsonify({'error': 'التقرير غير موجود'}), 404

    audit_service.record_event(
        action="report.exported",
        category="report",
        object_type="report",
        object_id=report_id,
        report_id=report_id,
        research_id=report.get('research_id'),
        research_reference_number=report.get('reference_number', ''),
        success=True,
        metadata={'format': 'html'}
    )

    html_content = export_report_to_html(report)
    response = Response(html_content, mimetype='text/html; charset=utf-8')
    response.headers['Content-Disposition'] = f'attachment; filename="academic_report_{report_id}.html"'
    return response


# ─── مسارات نزاهة التقارير والاعتماد وإدارة المراجعات (Phase 15 Endpoints) ──────

@report_bp.route('/api/reports/<report_id>/finalize', methods=['POST'])
@require_permission(Permission.REPORT_FINALIZE)
def finalize_report_route(report_id):
    """اعتماد التقرير رسمياً وتجميد محتواه وبصمته الرقمية (صلاحية report.finalize)."""
    from flask import session as flask_session
    from app.services import report_integrity_service
    user_name = flask_session.get('user', {}).get('username') or 'senior_reviewer'

    ok, rep_data, msg, err_code = report_integrity_service.finalize_report(report_id, finalized_by=user_name)
    if not ok:
        status_code = 400
        if err_code == ErrorCode.NOT_FOUND:
            status_code = 404
        return jsonify({'success': False, 'error': msg, 'code': err_code}), status_code

    return jsonify({
        'success': True,
        'message': msg,
        'report': rep_data
    })


@report_bp.route('/api/reports/<report_id>/integrity', methods=['GET'])
@require_permission(Permission.REPORT_VIEW)
def get_report_integrity_route(report_id):
    """التحقق من سلامة ونزاهة وبصمة التقرير (صلاحية report.view)."""
    from app.services import report_integrity_service
    res = report_integrity_service.verify_report_integrity(report_id)
    if res.get('error'):
        return jsonify({'success': False, 'error': res['error']}), 404
    return jsonify(res)


@report_bp.route('/api/reports/<report_id>/void', methods=['POST'])
@require_permission(Permission.REPORT_VOID)
def void_report_route(report_id):
    """إبطال تقرير معتمد مع توثيق السبب والفاعل (صلاحية report.void)."""
    from flask import session as flask_session
    from app.services import report_integrity_service
    user_name = flask_session.get('user', {}).get('username') or 'system_admin'
    data = request.get_json(silent=True) or request.form or {}
    reason = data.get('reason', '').strip()

    ok, msg, err_code = report_integrity_service.void_report(report_id, voided_by=user_name, reason=reason)
    if not ok:
        status_code = 400
        if err_code == ErrorCode.NOT_FOUND:
            status_code = 404
        return jsonify({'success': False, 'error': msg, 'code': err_code}), status_code

    return jsonify({'success': True, 'message': msg})


@report_bp.route('/api/reports/<report_id>/revisions', methods=['GET'])
@require_permission(Permission.REPORT_VIEW)
def get_report_revisions_route(report_id):
    """استرجاع خط النسب الزمني وتاريخ مراجعات البحث للتقرير (صلاحية report.view)."""
    from app.services import report_integrity_service
    report = report_repo.get_report(report_id)
    if not report:
        return jsonify({'error': 'التقرير غير موجود'}), 404

    research_id = report.get('research_id')
    if not research_id:
        return jsonify({'research_id': None, 'revisions': []})

    revisions = report_integrity_service.get_research_revisions_lineage(research_id)
    return jsonify({
        'research_id': research_id,
        'research_reference_number': report.get('reference_number', ''),
        'revisions': revisions
    })

