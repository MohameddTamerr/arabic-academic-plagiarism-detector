# -*- coding: utf-8 -*-
"""
مسارات الدفعات والرسائل متعددة الملفات (Batch & Thesis Routes):
- POST /api/batch/independent  → رفع عدة أبحاث مستقلة في دفعة واحدة
- POST /api/batch/thesis       → رفع رسالة واحدة من عدة ملفات مرتبة
- GET  /api/batch/<id>         → حالة الدفعة الكاملة
- GET  /api/batch/<id>/item/<research_id>/report  → تقرير عنصر محدد
- POST /api/batch/<id>/item/<research_id>/retry   → إعادة فحص عنصر فاشل
"""

import os
import uuid
import hashlib
import logging
from pathlib import Path
from werkzeug.utils import secure_filename
from flask import Blueprint, request, jsonify

import config
from app.repositories import report_repo
from app.repositories import batch_repo
from app.services.scan_service import start_async_scan, start_thesis_scan, start_batch_scan
from app.security.permissions import Permission
from app.security.authorization import require_permission

logger = logging.getLogger(__name__)
batch_bp = Blueprint('batch_bp', __name__)


from app.services import upload_validation_service
from app.errors.exceptions import ValidationError
from app.errors.error_codes import ErrorCode

def _safe_store(file, orig_name: str, max_bytes: int = config.MAX_UPLOAD_BYTES) -> tuple[str, str, str, int]:
    """
    تدقيق وحفظ ملف مرفوع بشكل آمن وذري باستخدام upload_validation_service.
    يتحقق من البصمة والبنية الرقمية، يكتب في staging، وينقل ذرياً للتخزين النهائي.
    """
    val_res = upload_validation_service.validate_and_stage_upload(
        file_stream=file,
        original_filename=orig_name,
        max_bytes=max_bytes,
        allowed_extensions=config.ALLOWED_EXTENSIONS
    )
    final_res = upload_validation_service.finalize_validated_upload(
        validation_result=val_res,
        target_dir=config.TEMP_UPLOAD_DIR
    )
    return final_res['stored_filename'], final_res['file_path'], final_res['file_hash'], final_res['file_size_bytes']


# ─── POST /api/batch/independent ─────────────────────────────────────────────

@batch_bp.route('/api/batch/independent', methods=['POST'])
@require_permission(Permission.RESEARCH_UPLOAD)
def start_independent_batch():
    """
    رفع عدة أبحاث مستقلة في دفعة واحدة (صلاحية research.upload).
    كل ملف = بحث مستقل بتقرير ونسبة خاصة به مع كشف التكرار الداخلي والخارجي.
    FormData:
      files[]          ← الملفات
      titles[]         ← عنوان كل ملف (نفس الترتيب)
      authors[]        ← اسم الباحث لكل ملف
      created_by       ← اسم المستخدم الرافع
      label            ← وصف اختياري للدفعة
    """
    files = request.files.getlist('files[]')
    titles = request.form.getlist('titles[]')
    authors = request.form.getlist('authors[]')
    created_by = request.form.get('created_by', '').strip()
    label = request.form.get('label', '').strip()

    if not files or not files[0].filename:
        return jsonify({'error': 'لم يتم رفع أي ملفات'}), 400

    if len(files) > config.MAX_FILES_PER_BATCH:
        raise ValidationError(
            f"عدد الملفات المرفوعة ({len(files)}) يتجاوز الحد الأقصى المسموح للدفعة الواحدة ({config.MAX_FILES_PER_BATCH} أبحاث).",
            code=ErrorCode.BATCH_LIMIT_EXCEEDED,
            status_code=400
        )

    if len(titles) < len(files) or len(authors) < len(files):
        return jsonify({'error': 'عدد العناوين وأسماء الباحثين يجب أن يتطابق مع عدد الملفات'}), 400

    # إنشاء الدفعة
    batch_id = batch_repo.create_batch(created_by=created_by, label=label or f'دفعة {len(files)} أبحاث')

    batch_items = []
    duplicates = []
    seen_batch_hashes = set()
    total_batch_bytes = 0

    for idx, (file, title, author) in enumerate(zip(files, titles, authors)):
        orig_name = file.filename
        title = title.strip() or os.path.splitext(orig_name)[0]
        author = author.strip() or 'غير محدد'

        stored_name, file_path, file_hash, file_size = _safe_store(file, orig_name)
        total_batch_bytes += file_size

        if total_batch_bytes > config.MAX_BATCH_TOTAL_BYTES:
            raise ValidationError(
                f"الحجم الإجمالي لملفات الدفعة يتجاوز الحد الأقصى المسموح ({config.MAX_BATCH_TOTAL_BYTES // (1024 * 1024)} ميجابايت).",
                code=ErrorCode.BATCH_LIMIT_EXCEEDED,
                status_code=413
            )

        is_internal_duplicate = file_hash in seen_batch_hashes
        is_db_duplicate = batch_repo.file_hash_exists(file_hash)

        if is_internal_duplicate or is_db_duplicate:
            duplicates.append(orig_name)

        seen_batch_hashes.add(file_hash)
        ext = os.path.splitext(orig_name)[1].lower().lstrip('.')

        # إنشاء Research + ResearchFile
        research_id = batch_repo.create_research(
            title=title,
            author=author,
            created_by=created_by,
            batch_id=batch_id
        )
        batch_repo.add_research_file(
            research_id=research_id,
            original_filename=orig_name,
            stored_filename=stored_name,
            file_path=file_path,
            file_type=ext,
            file_size_bytes=file_size,
            file_order=0,
            file_hash=file_hash
        )
        batch_repo.add_batch_item(batch_id=batch_id, research_id=research_id, item_order=idx)

        batch_items.append({
            'research_id': research_id,
            'file_path': file_path,
            'title': title,
            'author': author,
            'file_name': orig_name,
            'raw_text': '',
            'is_duplicate': is_internal_duplicate or is_db_duplicate
        })

    # تشغيل فحص الدفعة في الخلفية
    start_batch_scan(batch_id, batch_items)

    # توثيق حدث إنشاء الدفعة في سجل التدقيق
    from app.services import audit_service
    audit_service.record_event(
        action="batch.created",
        category="batch",
        object_type="batch",
        object_id=batch_id,
        batch_id=batch_id,
        success=True,
        metadata={"total_items": len(files), "label": label, "duplicates_count": len(duplicates)}
    )

    if duplicates:
        audit_service.record_event(
            action="batch.duplicate_detected",
            category="batch",
            object_type="batch",
            object_id=batch_id,
            batch_id=batch_id,
            success=True,
            metadata={"batch_id": batch_id, "duplicate_files": duplicates}
        )

    response = {'batch_id': batch_id, 'total': len(files), 'status': 'running'}
    if duplicates:
        response['duplicates_warning'] = duplicates
    return jsonify(response), 202


# ─── POST /api/batch/thesis ──────────────────────────────────────────────────

@batch_bp.route('/api/batch/thesis', methods=['POST'])
@require_permission(Permission.RESEARCH_UPLOAD)
def start_thesis_upload():
    """
    رفع رسالة واحدة تتكون من عدة ملفات مرتبة (صلاحية research.upload).
    الملفات تُفحص كوثيقة واحدة موحدة مع استبعاد الفصول المكررة تماماً.
    FormData:
      files[]          ← الملفات بترتيب الأبواب
      orders[]         ← ترتيب كل ملف (0-indexed integers)
      title            ← عنوان الرسالة
      author           ← اسم الباحث
      specialization   ← التخصص
      degree_type      ← الدرجة (ماجستير / دكتوراه)
      created_by       ← اسم المستخدم الرافع
    """
    files = request.files.getlist('files[]')
    orders_raw = request.form.getlist('orders[]')
    title = request.form.get('title', '').strip()
    author = request.form.get('author', '').strip()
    specialization = request.form.get('specialization', '').strip()
    degree_type = request.form.get('degree_type', '').strip()
    created_by = request.form.get('created_by', '').strip()

    if not files or not files[0].filename:
        return jsonify({'error': 'لم يتم رفع أي ملفات'}), 400
    if len(files) > config.MAX_FILES_PER_THESIS:
        raise ValidationError(
            f"عدد ملفات الرسالة المرفوعة ({len(files)}) يتجاوز الحد الأقصى المسموح ({config.MAX_FILES_PER_THESIS} ملفات/أبواب).",
            code=ErrorCode.BATCH_LIMIT_EXCEEDED,
            status_code=400
        )
    if not title:
        return jsonify({'error': 'عنوان الرسالة مطلوب'}), 400
    if not author:
        return jsonify({'error': 'اسم الباحث مطلوب'}), 400

    # تحليل الترتيب
    orders = []
    for i, o in enumerate(orders_raw):
        try:
            orders.append(int(o))
        except (ValueError, TypeError):
            orders.append(i)
    while len(orders) < len(files):
        orders.append(len(orders))

    # الترتيب النهائي: sort files by order
    file_order_pairs = sorted(zip(orders, files), key=lambda x: x[0])

    # إنشاء Research
    research_id = batch_repo.create_research(
        title=title,
        author=author,
        specialization=specialization,
        degree_type=degree_type,
        created_by=created_by
    )

    file_entries = []
    duplicates = []
    seen_thesis_hashes = set()
    total_thesis_bytes = 0

    for file_order_val, file in file_order_pairs:
        orig_name = file.filename
        ext = os.path.splitext(orig_name)[1].lower().lstrip('.')

        stored_name, file_path, file_hash, file_size = _safe_store(file, orig_name)
        total_thesis_bytes += file_size

        if total_thesis_bytes > config.MAX_THESIS_TOTAL_BYTES:
            raise ValidationError(
                f"الحجم الإجمالي لملفات الرسالة يتجاوز الحد الأقصى المسموح ({config.MAX_THESIS_TOTAL_BYTES // (1024 * 1024)} ميجابايت).",
                code=ErrorCode.BATCH_LIMIT_EXCEEDED,
                status_code=413
            )

        is_duplicate_chapter = file_hash in seen_thesis_hashes
        if is_duplicate_chapter or batch_repo.file_hash_exists(file_hash):
            duplicates.append(orig_name)

        batch_repo.add_research_file(
            research_id=research_id,
            original_filename=orig_name,
            stored_filename=stored_name,
            file_path=file_path,
            file_type=ext,
            file_size_bytes=file_size,
            file_order=file_order_val,
            file_hash=file_hash
        )

        # استبعاد الفصل المكرر تماماً من الدمج المنطقي للنص حتى لا يُحلل مرتين
        if not is_duplicate_chapter:
            seen_thesis_hashes.add(file_hash)
            file_entries.append({
                'path': file_path,
                'original_filename': orig_name,
                'file_type': ext,
                'file_order': file_order_val
            })

    # تشغيل فحص الرسالة في الخلفية
    task_id = start_thesis_scan(
        research_id=research_id,
        file_entries=file_entries,
        title=title,
        author=author
    )

    # توثيق رفع الرسالة في سجل التدقيق
    from app.services import audit_service
    res_obj = batch_repo.get_research(research_id)
    ref_num = res_obj.get('reference_number', '') if res_obj else ''

    audit_service.record_event(
        action="research.multi_file_created",
        category="research",
        object_type="research",
        object_id=str(research_id),
        research_id=research_id,
        research_reference_number=ref_num,
        success=True,
        metadata={
            "title": title,
            "author": author,
            "file_count": len(file_entries),
            "degree_type": degree_type,
            "specialization": specialization
        }
    )

    if duplicates:
        audit_service.record_event(
            action="thesis.duplicate_file_detected",
            category="research",
            object_type="research",
            object_id=str(research_id),
            research_id=research_id,
            research_reference_number=ref_num,
            success=True,
            metadata={"duplicate_files": duplicates}
        )

    response = {
        'research_id': research_id,
        'reference_number': ref_num,
        'task_id': task_id,
        'file_count': len(file_entries),
        'status': 'running'
    }
    if duplicates:
        response['duplicates_warning'] = duplicates
    return jsonify(response), 202


# ─── GET /api/batch/<batch_id> ───────────────────────────────────────────────

@batch_bp.route('/api/batch/<batch_id>', methods=['GET'])
@require_permission(Permission.BATCH_VIEW)
def get_batch_status(batch_id):
    """حالة الدفعة الكاملة مع حالة كل عنصر (صلاحية batch.view)."""
    data = batch_repo.get_batch(batch_id)
    if not data:
        return jsonify({'error': 'الدفعة غير موجودة'}), 404

    # إثراء بحالة المهام من _ACTIVE_SCANS لو لم تُكتمل بعد
    from app.services.scan_service import get_scan_status
    for item in data['items']:
        if item['status'] in ('queued', 'running') and item.get('scan_job_id'):
            live = get_scan_status(item['scan_job_id'])
            if live and 'status' in live:
                item['live_status'] = live.get('status')
                item['live_progress'] = live.get('progress', 0)
                item['live_stage'] = live.get('stage', '')

    return jsonify(data)


# ─── GET /api/batch/<batch_id>/item/<research_id>/report ─────────────────────

@batch_bp.route('/api/batch/<batch_id>/item/<int:research_id>/report', methods=['GET'])
@require_permission(Permission.REPORT_VIEW)
def get_batch_item_report(batch_id, research_id):
    """استرجاع تقرير عنصر محدد داخل الدفعة (صلاحية report.view)."""
    report_id = batch_repo.get_batch_item_report_id(batch_id, research_id)
    if not report_id:
        return jsonify({'error': 'التقرير غير متاح بعد أو لم يكتمل الفحص'}), 404

    report = report_repo.get_report(report_id)
    if not report:
        return jsonify({'error': 'التقرير غير موجود في قاعدة البيانات'}), 404

    return jsonify(report)


# ─── POST /api/batch/<batch_id>/item/<research_id>/retry ─────────────────────

@batch_bp.route('/api/batch/<batch_id>/item/<int:research_id>/retry', methods=['POST'])
@require_permission(Permission.BATCH_RETRY)
def retry_batch_item(batch_id, research_id):
    """إعادة فحص عنصر فاشل أو منقطع داخل الدفعة (صلاحية batch.retry)."""
    batch_data = batch_repo.get_batch(batch_id)
    if not batch_data:
        return jsonify({'error': 'الدفعة غير موجودة'}), 404

    # إيجاد العنصر
    target_item = None
    for item in batch_data['items']:
        if item['research_id'] == research_id:
            target_item = item
            break

    if not target_item:
        return jsonify({'error': 'العنصر غير موجود في هذه الدفعة'}), 404

    if target_item['status'] == 'completed':
        return jsonify({'error': 'العنصر مكتمل بالفعل — لا حاجة لإعادة الفحص'}), 400

    # جلب ملفات الرسالة
    research = batch_repo.get_research(research_id)
    if not research or not research.get('files'):
        return jsonify({'error': 'لم يتم العثور على ملفات الرسالة'}), 404

    files = research['files']

    # إعادة تعيين الحالة
    batch_repo.update_batch_item(
        batch_id=batch_id,
        research_id=research_id,
        status='queued',
        progress=0
    )

    # إعادة تشغيل الفحص
    start_batch_scan(batch_id, [{
        'research_id': research_id,
        'file_path': files[0]['file_path'] if files else '',
        'title': research['title'],
        'author': research['author'],
        'file_name': files[0]['original_filename'] if files else '',
        'raw_text': ''
    }])

    from app.services import audit_service
    audit_service.record_event(
        action="batch.item_retried",
        category="batch",
        object_type="research",
        object_id=str(research_id),
        batch_id=batch_id,
        research_id=research_id,
        research_reference_number=research.get('reference_number', ''),
        success=True,
        metadata={"title": research.get('title', '')}
    )

    return jsonify({'success': True, 'research_id': research_id, 'status': 'queued'})


# ─── GET /api/thesis/<research_id>/status ────────────────────────────────────

@batch_bp.route('/api/thesis/<int:research_id>/status', methods=['GET'])
@require_permission(Permission.RESEARCH_VIEW)
def get_thesis_status(research_id):
    """حالة فحص رسالة (ملفات متعددة) (صلاحية research.view)."""
    from app.services.scan_service import get_scan_status

    research = batch_repo.get_research(research_id)
    if not research:
        return jsonify({'error': 'الرسالة غير موجودة'}), 404

    result = {'research_id': research_id, 'report_id': research.get('report_id')}

    if research.get('scan_job_id'):
        job = get_scan_status(research['scan_job_id'])
        result['task_id'] = research['scan_job_id']
        result['status'] = job.get('status', 'unknown')
        result['progress'] = job.get('progress', 0)
        result['stage'] = job.get('stage', '')
        result['error'] = job.get('error', '')
        if job.get('result'):
            result['result'] = job['result']
    else:
        result['status'] = 'not_started'

    return jsonify(result)


# ─── Large Dataset Research & Batch Search Endpoints (Phase 10) ──────────────

@batch_bp.route('/api/researches', methods=['GET'])
@require_permission(Permission.RESEARCH_VIEW)
def list_researches_paginated():
    """
    استرجاع وبحث الأبحاث والرسائل مع التقسيم والفلترة المؤسسية (صلاحية research.view).
    يدعم:
    - ?q= نص البحث (رقم مرجعي، عنوان، مؤلف)
    - ?scan_status= (queued, running, completed, failed, interrupted)
    - ?review_status= (pending_review, preliminary_accepted, rejected, final_accepted)
    - ?date_from=YYYY-MM-DD & ?date_to=YYYY-MM-DD
    - ?sort= (created_at, reference_number, title, scan_status, review_status) & ?order= (asc, desc)
    - ?page=1 & ?page_size=25 (max 100)
    """
    from app.utils.pagination import get_pagination_params, format_paginated_response
    from app.security.authorization import get_authenticated_user
    from app.security.permissions import Role

    params = get_pagination_params(
        default_size=25,
        max_size=100,
        allowed_sort_fields=['created_at', 'reference_number', 'title', 'author', 'scan_status', 'review_status'],
        default_sort='created_at',
        default_order='desc'
    )

    # التحقق من نطاق صلاحيات المستخدم (Data Scoping)
    current_user = get_authenticated_user()
    user_scope = None
    if current_user and current_user.get('role') == Role.DATA_ENTRY:
        user_scope = current_user.get('username')

    scan_status = request.args.get('scan_status')
    review_status = request.args.get('review_status')

    items, total_count = batch_repo.search_researches(
        query=params['q'],
        scan_status=scan_status,
        review_status=review_status,
        date_from=params['date_from'],
        date_to=params['date_to'],
        sort_field=params['sort'],
        order_direction=params['order'],
        offset=params['offset'],
        limit=params['limit'],
        user_scope_username=user_scope,
        after_id=params.get('after_id'),
        before_id=params.get('before_id')
    )

    return jsonify(format_paginated_response(
        items=items,
        total_items=total_count,
        page=params['page'],
        page_size=params['page_size'],
        legacy_key='researches'
    ))



@batch_bp.route('/api/batches', methods=['GET'])
@require_permission(Permission.BATCH_VIEW)
def list_batches_paginated():
    """
    استرجاع سجل الدفعات مع التقسيم والبحث وفلترة الحالات (صلاحية batch.view).
    """
    from app.utils.pagination import get_pagination_params, format_paginated_response

    params = get_pagination_params(
        default_size=25,
        max_size=100,
        allowed_sort_fields=['created_at', 'label', 'status'],
        default_sort='created_at',
        default_order='desc'
    )

    status = request.args.get('status')

    items, total_count = batch_repo.search_batches(
        query=params['q'],
        status=status,
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
        legacy_key='batches'
    ))

