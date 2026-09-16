# -*- coding: utf-8 -*-
"""
مسارات الرسائل العلمية والتقرير المجمع (Thesis & Multi-Part Routes):
- إنشاء رسالة علمية جديدة مع رفع ملفاتها الأولية دفعة واحدة.
- استعراض وبحث قائمة الرسائل العلمية وتفاصيلها وأجزائها.
- إضافة أجزاء جديدة إلى رسالة موجودة مع فحص التكرار.
- تعديل ترتيب وتسمية الأجزاء، وفصل الأجزاء غير المرغوبة.
- إعادة فحص جزء منفرد وتوليد واستعراض التقرير المجمع للرسالة.
"""

import os
from flask import Blueprint, request, jsonify

import config
from app.security.permissions import Permission
from app.security.authorization import require_permission, get_authenticated_user, check_unit_access
from app.security.permissions import Role, normalize_role
from app.repositories import thesis_repo, report_repo, base_repo
from app.services import thesis_service, audit_service, upload_validation_service
from app.errors.error_codes import ErrorCode
from app.utils.pagination import get_pagination_params, format_paginated_response
from app.models.schema import LegacyReport

thesis_bp = Blueprint('thesis_bp', __name__)


def _safe_store_thesis_file(file, orig_name: str) -> tuple[str, str, str, int, str]:
    """تحصين وتخزين ملف جزء الرسالة بأمان في مجلد التخزين."""
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
    ext = os.path.splitext(orig_name)[1].lower().lstrip('.')
    return final_res['stored_filename'], final_res['file_path'], final_res['file_hash'], final_res['file_size_bytes'], ext


@thesis_bp.route('/api/thesis', methods=['GET'])
@thesis_bp.route('/api/theses', methods=['GET'])
@require_permission(Permission.THESIS_VIEW)
def list_theses():
    """استرجاع وبحث قائمة الرسائل العلمية مع الترقيم والفلترة."""
    params = get_pagination_params(
        default_size=25,
        max_size=100,
        allowed_sort_fields=['id', 'reference_number', 'title', 'author', 'created_at']
    )

    actor = get_authenticated_user()
    actor_role = normalize_role(actor.get('role') if actor else 'employee')

    degree_filter = request.args.get('degree_type')
    status_filter = request.args.get('status')
    review_status_filter = request.args.get('review_status')
    dept_filter = request.args.get('department')

    if actor_role == Role.UNIT_MANAGER and actor and actor.get('department'):
        dept_filter = actor.get('department')

    items, total_count = thesis_repo.search_theses(
        query=params['q'],
        degree_type=degree_filter,
        department=dept_filter,
        status=status_filter,
        review_status=review_status_filter,
        page=params['page'],
        per_page=params['page_size']
    )

    return jsonify(format_paginated_response(
        items=items,
        total_items=total_count,
        page=params['page'],
        page_size=params['page_size'],
        legacy_key='theses'
    ))


@thesis_bp.route('/api/thesis/<int:thesis_id>', methods=['GET'])
@thesis_bp.route('/api/theses/<int:thesis_id>', methods=['GET'])
@require_permission(Permission.THESIS_VIEW)
def get_thesis_detail(thesis_id):
    """استرجاع بيانات وتفاصيل الرسالة وأجزائها وإحصائياتها مع فحص نطاق الوحدة."""
    th = thesis_repo.get_thesis(thesis_id)
    if not th:
        return jsonify({'error': 'الرسالة العلمية غير موجودة', 'code': ErrorCode.NOT_FOUND}), 404

    actor = get_authenticated_user()
    if not check_unit_access(actor, th.get('department')):
        return jsonify({'error': 'غير مصرح: لا تملك صلاحية الوصول إلى رسائل هذا القسم/الوحدة', 'code': ErrorCode.AUTH_FORBIDDEN}), 403

    return jsonify(th)


@thesis_bp.route('/api/thesis', methods=['POST'])
@thesis_bp.route('/api/theses', methods=['POST'])
@require_permission(Permission.THESIS_CREATE)
def create_new_thesis():
    """
    إنشاء رسالة علمية جديدة مع رفع ملفات أجزائها دفعة واحدة (صلاحية thesis.create).
    FormData:
      title            ← عنوان الرسالة
      author           ← اسم الباحث
      degree_type      ← الدرجة (ماجستير / دكتوراه)
      department       ← الوحدة / الإدارة
      academic_year    ← السنة الأكاديمية
      notes            ← ملاحظات
      files[]          ← ملفات الأجزاء
      labels[]         ← تسمية كل جزء (الباب الأول, الفصل الأول...)
      orders[]         ← ترتيب الأجزاء (اختياري)
      auto_scan        ← بدء الفحص التلقائي للأجزاء (0 أو 1)
    """
    title = (request.form.get('title') or '').strip()
    author = (request.form.get('author') or '').strip()
    degree_type = (request.form.get('degree_type') or 'ماجستير').strip()
    department = (request.form.get('department') or '').strip()
    academic_year = (request.form.get('academic_year') or '').strip()
    notes = (request.form.get('notes') or '').strip()
    auto_scan = request.form.get('auto_scan', '1') in ('1', 'true', 'True')

    if not title:
        return jsonify({'error': 'عنوان الرسالة مطلوب', 'code': ErrorCode.VALIDATION_ERROR}), 400
    if not author:
        return jsonify({'error': 'اسم الباحث مطلوب', 'code': ErrorCode.VALIDATION_ERROR}), 400

    files = request.files.getlist('files[]')
    labels = request.form.getlist('labels[]')
    orders_raw = request.form.getlist('orders[]')

    actor = get_authenticated_user()
    actor_username = actor.get('username') if actor else ''
    actor_id = actor.get('id') if actor else None

    # 1. إنشاء كيان الرسالة
    thesis_id, ref_num = thesis_repo.create_thesis(
        title=title,
        author=author,
        degree_type=degree_type,
        department=department,
        academic_year=academic_year,
        notes=notes,
        created_by=actor_username,
        created_by_user_id=actor_id
    )

    added_parts = []
    duplicate_warnings = []
    seen_hashes_in_request = set()

    # 2. معالجة وحفظ الأجزاء المرفوعة
    if files and files[0].filename:
        for idx, file in enumerate(files):
            orig_name = file.filename
            if not orig_name:
                continue

            # استخراج التسمية المعروضة والترتيب
            label = labels[idx].strip() if idx < len(labels) and labels[idx].strip() else os.path.splitext(orig_name)[0]
            try:
                order_val = int(orders_raw[idx]) if idx < len(orders_raw) else idx
            except (ValueError, TypeError):
                order_val = idx

            stored_name, file_path, file_hash, file_size, file_type = _safe_store_thesis_file(file, orig_name)

            if file_hash in seen_hashes_in_request:
                duplicate_warnings.append(f"{label} ({orig_name}): هذا الملف مضاف بالفعل إلى الرسالة.")
            seen_hashes_in_request.add(file_hash)

            part_id, is_dup = thesis_repo.add_thesis_part(
                thesis_id=thesis_id,
                part_title=label,
                original_filename=orig_name,
                stored_filename=stored_name,
                file_path=file_path,
                file_type=file_type,
                file_size_bytes=file_size,
                file_hash=file_hash,
                sort_order=order_val
            )

            if is_dup:
                duplicate_warnings.append(f"{label} ({orig_name}): هذا الملف مضاف بالفعل إلى الرسالة.")

            added_parts.append({
                'part_id': part_id,
                'part_title': label,
                'original_filename': orig_name,
                'sort_order': order_val
            })

            # بدء الفحص إذا طُلب
            if auto_scan:
                thesis_service.scan_thesis_part(part_id, requested_by=actor_username)

    audit_service.record_event(
        action="THESIS_CREATED",
        category="thesis",
        user=actor,
        object_type="thesis",
        object_id=str(thesis_id),
        success=True,
        metadata={
            'thesis_id': thesis_id,
            'reference_number': ref_num,
            'title': title,
            'author': author,
            'parts_count': len(added_parts),
            'duplicate_warnings': duplicate_warnings
        }
    )

    resp_data = {
        'success': True,
        'message': f'تم إنشاء الرسالة العلمية بنجاح بالرقم المرجعي {ref_num}',
        'thesis_id': thesis_id,
        'reference_number': ref_num,
        'parts_count': len(added_parts),
        'parts': added_parts
    }
    if duplicate_warnings:
        resp_data['duplicate_warnings'] = duplicate_warnings

    return jsonify(resp_data), 201


@thesis_bp.route('/api/thesis/<int:thesis_id>/parts', methods=['POST'])
@thesis_bp.route('/api/theses/<int:thesis_id>/parts', methods=['POST'])
@require_permission(Permission.THESIS_ADD_PART)
def add_parts_to_thesis(thesis_id):
    """إضافة جزء أو عدة أجزاء إلى رسالة علمية موجودة مسبقاً مع فحص نطاق الوحدة."""
    th = thesis_repo.get_thesis(thesis_id)
    if not th:
        return jsonify({'error': 'الرسالة العلمية غير موجودة', 'code': ErrorCode.NOT_FOUND}), 404

    actor = get_authenticated_user()
    if not check_unit_access(actor, th.get('department')):
        return jsonify({'error': 'غير مصرح: لا تملك صلاحية تعديل رسائل هذا القسم/الوحدة', 'code': ErrorCode.AUTH_FORBIDDEN}), 403

    files = request.files.getlist('files[]') or request.files.getlist('files')
    if not files and 'file' in request.files:
        files = [request.files['file']]

    labels = request.form.getlist('labels[]') or request.form.getlist('labels')
    if not labels and 'part_label' in request.form:
        labels = [request.form['part_label']]

    orders_raw = request.form.getlist('orders[]') or request.form.getlist('orders')
    if not orders_raw and 'order_index' in request.form:
        orders_raw = [request.form['order_index']]

    auto_scan = request.form.get('auto_scan', '1') in ('1', 'true', 'True')

    if not files or not files[0].filename:
        return jsonify({'error': 'لم يتم اختيار أي ملفات للإضافة', 'code': ErrorCode.VALIDATION_ERROR}), 400

    actor = get_authenticated_user()
    actor_username = actor.get('username') if actor else ''

    added_parts = []
    duplicate_warnings = []

    for idx, file in enumerate(files):
        orig_name = file.filename
        if not orig_name:
            continue

        label = labels[idx].strip() if idx < len(labels) and labels[idx].strip() else os.path.splitext(orig_name)[0]
        try:
            order_val = int(orders_raw[idx]) if idx < len(orders_raw) else None
        except (ValueError, TypeError):
            order_val = None

        stored_name, file_path, file_hash, file_size, file_type = _safe_store_thesis_file(file, orig_name)

        part_id, is_dup = thesis_repo.add_thesis_part(
            thesis_id=thesis_id,
            part_title=label,
            original_filename=orig_name,
            stored_filename=stored_name,
            file_path=file_path,
            file_type=file_type,
            file_size_bytes=file_size,
            file_hash=file_hash,
            sort_order=order_val
        )

        if is_dup:
            duplicate_warnings.append(f"{label} ({orig_name}): هذا الملف مضاف بالفعل إلى الرسالة.")

        added_parts.append({
            'part_id': part_id,
            'part_title': label,
            'original_filename': orig_name
        })

        if auto_scan:
            thesis_service.scan_thesis_part(part_id, requested_by=actor_username)

    audit_service.record_event(
        action="THESIS_PART_ADDED",
        category="thesis",
        user=actor,
        object_type="thesis",
        object_id=str(thesis_id),
        success=True,
        metadata={
            'thesis_id': thesis_id,
            'added_parts_count': len(added_parts),
            'duplicate_warnings': duplicate_warnings
        }
    )

    part_id = added_parts[0]['part_id'] if added_parts else None
    resp_data = {
        'success': True,
        'message': f'تمت إضافة {len(added_parts)} أجزاء إلى الرسالة بنجاح',
        'part_id': part_id,
        'part': added_parts[0] if added_parts else None,
        'added_parts': added_parts
    }
    if duplicate_warnings:
        resp_data['duplicate_warnings'] = duplicate_warnings
        if len(duplicate_warnings) == len(files):
            resp_data['error'] = 'الملف مضاف بالفعل إلى هذه الرسالة'
            return jsonify(resp_data), 409

    return jsonify(resp_data), 201


@thesis_bp.route('/api/thesis/<int:thesis_id>/parts/<int:part_id>', methods=['PUT', 'POST'])
@require_permission(Permission.THESIS_EDIT)
def update_thesis_part(thesis_id, part_id):
    """تعديل التسمية المعروضة أو ترتيب جزء من الرسالة مع فحص نطاق الوحدة."""
    part = thesis_repo.get_thesis_part(part_id)
    if not part or part['thesis_id'] != thesis_id:
        return jsonify({'error': 'الجزء غير موجود في هذه الرسالة', 'code': ErrorCode.NOT_FOUND}), 404

    th = thesis_repo.get_thesis(thesis_id)
    actor = get_authenticated_user()
    if th and not check_unit_access(actor, th.get('department')):
        return jsonify({'error': 'غير مصرح: لا تملك صلاحية تعديل رسائل هذا القسم/الوحدة', 'code': ErrorCode.AUTH_FORBIDDEN}), 403

    data = request.get_json(silent=True) or request.form or {}
    part_title = data.get('part_title') or data.get('title')
    sort_order = data.get('sort_order')
    if sort_order is not None:
        try:
            sort_order = int(sort_order)
        except (ValueError, TypeError):
            sort_order = None

    success, msg = thesis_repo.update_thesis_part_meta(part_id, part_title=part_title, sort_order=sort_order)
    if not success:
        return jsonify({'error': msg, 'code': ErrorCode.VALIDATION_ERROR}), 400

    actor = get_authenticated_user()
    audit_service.record_event(
        action="THESIS_PART_REORDERED" if sort_order is not None else "THESIS_UPDATED",
        category="thesis",
        user=actor,
        object_type="thesis_part",
        object_id=str(part_id),
        success=True,
        metadata={'thesis_id': thesis_id, 'part_title': part_title, 'sort_order': sort_order}
    )

    return jsonify({'success': True, 'message': msg})


@thesis_bp.route('/api/thesis/<int:thesis_id>/parts/reorder', methods=['POST'])
@thesis_bp.route('/api/theses/<int:thesis_id>/parts/reorder', methods=['POST'])
@require_permission(Permission.THESIS_EDIT)
def reorder_thesis_parts(thesis_id):
    """إعادة ترتيب وتسمية مجموعة أجزاء في الرسالة دفعة واحدة مع فحص نطاق الوحدة."""
    th = thesis_repo.get_thesis(thesis_id)
    if not th:
        return jsonify({'error': 'الرسالة العلمية غير موجودة', 'code': ErrorCode.NOT_FOUND}), 404

    actor = get_authenticated_user()
    if not check_unit_access(actor, th.get('department')):
        return jsonify({'error': 'غير مصرح: لا تملك صلاحية تعديل رسائل هذا القسم/الوحدة', 'code': ErrorCode.AUTH_FORBIDDEN}), 403

    data = request.get_json(silent=True) or {}
    part_orders = data.get('part_orders', [])
    if not part_orders:
        return jsonify({'error': 'قائمة ترتيب الأجزاء مطلوبة', 'code': ErrorCode.VALIDATION_ERROR}), 400

    for item in part_orders:
        p_id = item.get('id') or item.get('part_id')
        p_label = item.get('part_label') or item.get('part_title')
        p_order = item.get('order_index') or item.get('sort_order')
        if p_id is not None:
            thesis_repo.update_thesis_part_meta(p_id, part_title=p_label, sort_order=p_order)

    actor = get_authenticated_user()
    audit_service.record_event(
        action="THESIS_PARTS_REORDERED",
        category="thesis",
        user=actor,
        object_type="thesis",
        object_id=str(thesis_id),
        success=True,
        metadata={'thesis_id': thesis_id, 'reordered_count': len(part_orders)}
    )

    return jsonify({'success': True, 'message': 'تم تحديث ترتيب الأجزاء بنجاح'})


@thesis_bp.route('/api/thesis/<int:thesis_id>/parts/<int:part_id>', methods=['DELETE'])
@thesis_bp.route('/api/theses/<int:thesis_id>/parts/<int:part_id>', methods=['DELETE'])
@require_permission(Permission.THESIS_REMOVE_PART)
def detach_part_from_thesis(thesis_id, part_id):
    """استبعاد/فصل جزء من الرسالة العلمية مع الحفاظ على الأثر التاريخي ونطاق الوحدة."""
    part = thesis_repo.get_thesis_part(part_id)
    if not part or part['thesis_id'] != thesis_id:
        return jsonify({'error': 'الجزء غير موجود في هذه الرسالة', 'code': ErrorCode.NOT_FOUND}), 404

    th = thesis_repo.get_thesis(thesis_id)
    actor = get_authenticated_user()
    if th and not check_unit_access(actor, th.get('department')):
        return jsonify({'error': 'غير مصرح: لا تملك صلاحية تعديل رسائل هذا القسم/الوحدة', 'code': ErrorCode.AUTH_FORBIDDEN}), 403

    actor = get_authenticated_user()
    actor_name = actor.get('username') if actor else 'system'
    reason = request.args.get('reason') or (request.get_json(silent=True) or {}).get('reason') or 'استبعاد بطلب المستخدم'

    success, msg = thesis_repo.detach_thesis_part(part_id, detached_by=actor_name, reason=reason)
    if not success:
        return jsonify({'error': msg, 'code': ErrorCode.VALIDATION_ERROR}), 400

    audit_service.record_event(
        action="THESIS_PART_REMOVED",
        category="thesis",
        user=actor,
        object_type="thesis_part",
        object_id=str(part_id),
        success=True,
        metadata={'thesis_id': thesis_id, 'part_title': part['part_title'], 'reason': reason}
    )

    return jsonify({'success': True, 'message': msg})


@thesis_bp.route('/api/thesis/<int:thesis_id>/parts/<int:part_id>/scan', methods=['POST'])
@require_permission(Permission.THESIS_SCAN)
def rescan_single_part(thesis_id, part_id):
    """إعادة فحص جزء منفرد من الرسالة مع فحص نطاق الوحدة."""
    part = thesis_repo.get_thesis_part(part_id)
    if not part or part['thesis_id'] != thesis_id:
        return jsonify({'error': 'الجزء غير موجود في هذه الرسالة', 'code': ErrorCode.NOT_FOUND}), 404

    th = thesis_repo.get_thesis(thesis_id)
    actor = get_authenticated_user()
    if th and not check_unit_access(actor, th.get('department')):
        return jsonify({'error': 'غير مصرح: لا تملك صلاحية فحص رسائل هذا القسم/الوحدة', 'code': ErrorCode.AUTH_FORBIDDEN}), 403

    actor = get_authenticated_user()
    actor_name = actor.get('username') if actor else ''

    task_id = thesis_service.scan_thesis_part(part_id, requested_by=actor_name)

    audit_service.record_event(
        action="THESIS_PART_RESCANNED",
        category="thesis",
        user=actor,
        object_type="thesis_part",
        object_id=str(part_id),
        success=True,
        metadata={'thesis_id': thesis_id, 'part_title': part['part_title'], 'task_id': task_id}
    )

    return jsonify({'success': True, 'task_id': task_id, 'message': f'تم إطلاق إعادة فحص الجزء: {part["part_title"]}'})


@thesis_bp.route('/api/thesis/<int:thesis_id>/combined_report', methods=['POST'])
@thesis_bp.route('/api/theses/<int:thesis_id>/combined-report', methods=['POST'])
@require_permission(Permission.THESIS_REPORT_VIEW)
def generate_combined_report_endpoint(thesis_id):
    """إنشاء أو تحديث التقرير المجمع للرسالة العلمية بالحساب الموزون مع فحص نطاق الوحدة."""
    th = thesis_repo.get_thesis(thesis_id)
    if not th:
        return jsonify({'error': 'الرسالة غير موجودة', 'code': ErrorCode.NOT_FOUND}), 404

    actor = get_authenticated_user()
    if not check_unit_access(actor, th.get('department')):
        return jsonify({'error': 'غير مصرح: لا تملك صلاحية توليد تقرير لرسائل هذا القسم/الوحدة', 'code': ErrorCode.AUTH_FORBIDDEN}), 403

    success, report_dict, msg = thesis_service.generate_combined_thesis_report(thesis_id, actor_user=actor)
    if not success:
        return jsonify({'error': msg, 'code': ErrorCode.VALIDATION_ERROR}), 400

    return jsonify({
        'success': True,
        'message': msg,
        'report': report_dict
    })


@thesis_bp.route('/api/thesis/<int:thesis_id>/combined_report', methods=['GET'])
@thesis_bp.route('/api/theses/<int:thesis_id>/combined-report', methods=['GET'])
@require_permission(Permission.THESIS_REPORT_VIEW)
def get_combined_report_endpoint(thesis_id):
    """استرجاع التقرير المجمع الحالي للرسالة مع فحص نطاق الوحدة."""
    th = thesis_repo.get_thesis(thesis_id)
    if not th:
        return jsonify({'error': 'الرسالة غير موجودة', 'code': ErrorCode.NOT_FOUND}), 404

    actor = get_authenticated_user()
    if not check_unit_access(actor, th.get('department')):
        return jsonify({'error': 'غير مصرح: لا تملك صلاحية استعراض تقرير لرسائل هذا القسم/الوحدة', 'code': ErrorCode.AUTH_FORBIDDEN}), 403

    if not th.get('combined_report_id'):
        return jsonify({'error': 'لم يتم إنشاء التقرير المجمع لهذه الرسالة بعد', 'code': ErrorCode.NOT_FOUND}), 404

    rep = report_repo.get_report(th['combined_report_id'])
    if not rep:
        return jsonify({'error': 'ملف التقرير المجمع غير موجود في قاعدة البيانات', 'code': ErrorCode.NOT_FOUND}), 404

    return jsonify(rep)


@thesis_bp.route('/api/thesis/<int:thesis_id>/revisions', methods=['GET'])
@require_permission(Permission.THESIS_REPORT_VIEW)
def get_thesis_revisions(thesis_id):
    """استرجاع سجل مراجعات وإصدارات التقارير المجمعة للرسالة."""
    th = thesis_repo.get_thesis(thesis_id)
    if not th:
        return jsonify({'error': 'الرسالة غير موجودة', 'code': ErrorCode.NOT_FOUND}), 404

    if not check_unit_access(get_authenticated_user(), th.get('department')):
        return jsonify({'error': 'غير مصرح', 'code': ErrorCode.AUTH_FORBIDDEN}), 403

    with base_repo.get_session() as session:
        reps = (
            session.query(LegacyReport)
            .filter(LegacyReport.thesis_id == thesis_id, LegacyReport.is_combined_thesis == 1)
            .order_by(LegacyReport.revision_number.desc())
            .all()
        )

        revisions = [
            {
                'report_id': r.id,
                'revision_number': r.revision_number,
                'artifact_status': r.artifact_status,
                'overall_pct': r.overall_pct,
                'copied_pct': r.copied_pct,
                'para_pct': r.para_pct,
                'finalized_at': r.finalized_at.strftime('%Y-%m-%d %H:%M') if r.finalized_at else '',
                'finalized_by': r.finalized_by,
                'created_at': r.created_at.strftime('%Y-%m-%d %H:%M') if r.created_at else ''
            }
            for r in reps
        ]

        return jsonify({'thesis_id': thesis_id, 'revisions': revisions})
