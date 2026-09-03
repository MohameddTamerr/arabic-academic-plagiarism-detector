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

logger = logging.getLogger(__name__)
batch_bp = Blueprint('batch_bp', __name__)


def _safe_store(file, orig_name: str) -> tuple[str, str, str, int]:
    """
    حفظ ملف مرفوع بشكل آمن. يُعيد (stored_filename, file_path, file_hash, size).
    يمنع path traversal ويُولّد اسم تخزين فريد.
    """
    ext = os.path.splitext(orig_name)[1].lower()
    safe_base = secure_filename(os.path.splitext(orig_name)[0]) or 'file'
    stored_name = f"{uuid.uuid4().hex[:8]}_{safe_base}{ext}"
    save_path = config.TEMP_UPLOAD_DIR / stored_name

    file.save(str(save_path))

    # حساب SHA-256 لمنع التكرار
    sha = hashlib.sha256()
    with open(save_path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            sha.update(chunk)
    file_hash = sha.hexdigest()
    file_size = save_path.stat().st_size

    return stored_name, str(save_path), file_hash, file_size


# ─── POST /api/batch/independent ─────────────────────────────────────────────

@batch_bp.route('/api/batch/independent', methods=['POST'])
def start_independent_batch():
    """
    رفع عدة أبحاث مستقلة في دفعة واحدة.
    كل ملف = بحث مستقل بتقرير ونسبة خاصة به.
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

    if len(titles) < len(files) or len(authors) < len(files):
        return jsonify({'error': 'عدد العناوين وأسماء الباحثين يجب أن يتطابق مع عدد الملفات'}), 400

    # التحقق من صيغ الملفات
    for f in files:
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in config.ALLOWED_EXTENSIONS:
            return jsonify({'error': f"صيغة الملف غير مدعومة: {f.filename}"}), 400

    # إنشاء الدفعة
    batch_id = batch_repo.create_batch(created_by=created_by, label=label or f'دفعة {len(files)} أبحاث')

    batch_items = []
    duplicates = []

    for idx, (file, title, author) in enumerate(zip(files, titles, authors)):
        orig_name = file.filename
        title = title.strip() or os.path.splitext(orig_name)[0]
        author = author.strip() or 'غير محدد'

        try:
            stored_name, file_path, file_hash, file_size = _safe_store(file, orig_name)
        except Exception as e:
            logger.error(f"فشل حفظ الملف {orig_name}: {e}")
            return jsonify({'error': f"فشل حفظ الملف: {orig_name}"}), 500

        # فحص التكرار
        if batch_repo.file_hash_exists(file_hash):
            duplicates.append(orig_name)

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
            'raw_text': ''
        })

    # تشغيل فحص الدفعة في الخلفية
    start_batch_scan(batch_id, batch_items)

    response = {'batch_id': batch_id, 'total': len(files), 'status': 'running'}
    if duplicates:
        response['duplicates_warning'] = duplicates
    return jsonify(response), 202


# ─── POST /api/batch/thesis ──────────────────────────────────────────────────

@batch_bp.route('/api/batch/thesis', methods=['POST'])
def start_thesis_upload():
    """
    رفع رسالة واحدة تتكون من عدة ملفات مرتبة.
    الملفات تُفحص كوثيقة واحدة موحدة.
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

    # التحقق من صيغ الملفات
    for _, f in file_order_pairs:
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in config.ALLOWED_EXTENSIONS:
            return jsonify({'error': f"صيغة الملف غير مدعومة: {f.filename}"}), 400

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

    for file_order_val, file in file_order_pairs:
        orig_name = file.filename
        ext = os.path.splitext(orig_name)[1].lower().lstrip('.')

        try:
            stored_name, file_path, file_hash, file_size = _safe_store(file, orig_name)
        except Exception as e:
            logger.error(f"فشل حفظ الملف {orig_name}: {e}")
            return jsonify({'error': f"فشل حفظ الملف: {orig_name}"}), 500

        if batch_repo.file_hash_exists(file_hash):
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

    response = {
        'research_id': research_id,
        'task_id': task_id,
        'file_count': len(file_entries),
        'status': 'running'
    }
    if duplicates:
        response['duplicates_warning'] = duplicates
    return jsonify(response), 202


# ─── GET /api/batch/<batch_id> ───────────────────────────────────────────────

@batch_bp.route('/api/batch/<batch_id>', methods=['GET'])
def get_batch_status(batch_id):
    """حالة الدفعة الكاملة مع حالة كل عنصر."""
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
def get_batch_item_report(batch_id, research_id):
    """استرجاع تقرير عنصر محدد داخل الدفعة."""
    report_id = batch_repo.get_batch_item_report_id(batch_id, research_id)
    if not report_id:
        return jsonify({'error': 'التقرير غير متاح بعد أو لم يكتمل الفحص'}), 404

    report = report_repo.get_report(report_id)
    if not report:
        return jsonify({'error': 'التقرير غير موجود في قاعدة البيانات'}), 404

    return jsonify(report)


# ─── POST /api/batch/<batch_id>/item/<research_id>/retry ─────────────────────

@batch_bp.route('/api/batch/<batch_id>/item/<int:research_id>/retry', methods=['POST'])
def retry_batch_item(batch_id, research_id):
    """إعادة فحص عنصر فاشل أو منقطع داخل الدفعة."""
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

    return jsonify({'success': True, 'research_id': research_id, 'status': 'queued'})


# ─── GET /api/thesis/<research_id>/status ────────────────────────────────────

@batch_bp.route('/api/thesis/<int:research_id>/status', methods=['GET'])
def get_thesis_status(research_id):
    """حالة فحص رسالة (ملفات متعددة)."""
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
