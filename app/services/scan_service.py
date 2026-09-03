# -*- coding: utf-8 -*-
"""
خدمة فحص الأبحاث وإدارة المهام في الخلفية (Scan Service):
- تشغيل عمليات الفحص غير المتزامن في مسارات مستقلة لضمان استجابة وسلاسة الواجهة.
- تحديث مراحل التقدم لحظياً (استخراج، كشف تحايل، مطابقة متواليات، استشهادات، بناء التقرير).
- تسجيل النتائج في قاعدة البيانات وربطها بالتقارير السابقة.
- دعم فحص الرسائل متعددة الملفات (thesis scan) مع حفظ عزو المصدر.
- دعم فحص الدفعات مع تحديد MAX_CONCURRENT_SCANS لحماية الأجهزة المتواضعة.
"""

import os
import uuid
import logging
import datetime
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import config
from app.repositories import report_repo
from app.services.settings_service import get_current_settings
from plagiarism_detector.extraction.page_extractor import extract_document_pages
from plagiarism_detector.reporting.report_builder import analyze_academic_document
from plagiarism_detector.core.categorizer import categorize_text

logger = logging.getLogger(__name__)

_EXECUTOR = ThreadPoolExecutor(max_workers=max(4, config.MAX_CONCURRENT_SCANS + 2))
_ACTIVE_SCANS = {}

# Semaphore لتحديد التزامن الحقيقي لمهام الدفعة
_BATCH_SEMAPHORE = threading.Semaphore(config.MAX_CONCURRENT_SCANS)


# ─── فحص بحث واحد (API الحالي — بدون تغيير) ─────────────────────────────────

def start_async_scan(
    file_path: str,
    title: str,
    author: str,
    raw_text: str = '',
    file_name: str = ''
) -> str:
    """بدء مهمة فحص في الخلفية وإرجاع task_id للمتابعة."""
    task_id = str(uuid.uuid4())[:10]

    _ACTIVE_SCANS[task_id] = {
        'task_id': task_id,
        'status': 'running',
        'progress': 10,
        'stage': 'جاري استلام الملف وبدء الفحص...',
        'file_name': file_name or title or 'بحث جديد',
        'result': None,
        'error': None
    }

    report_repo.create_scan_job(
        job_id=task_id,
        filename=file_name or title or 'نص مدخل',
        title=title,
        author=author
    )

    _EXECUTOR.submit(_execute_scan_pipeline, task_id, file_path, title, author, raw_text, file_name)
    return task_id


def get_scan_status(task_id: str) -> dict:
    """استعلام عن تقدم مهمة الفحص."""
    if task_id in _ACTIVE_SCANS:
        return _ACTIVE_SCANS[task_id]
    job = report_repo.get_scan_job(task_id)
    if job:
        return job
    return {'error': 'المهمة غير موجودة'}


# ─── فحص رسالة متعددة الملفات (Thesis Scan) ─────────────────────────────────

def start_thesis_scan(
    research_id: int,
    file_entries: list[dict],   # [{'path': str, 'original_filename': str, 'file_type': str}, ...]
    title: str,
    author: str
) -> str:
    """
    فحص رسالة تتكون من عدة ملفات مرتبة.
    يُدمج نصوص الملفات منطقياً ويفحصها كوثيقة واحدة،
    مع حفظ عزو المصدر (اسم الملف + رقم الصفحة) في التقرير.
    يُعيد task_id.
    """
    task_id = str(uuid.uuid4())[:10]

    _ACTIVE_SCANS[task_id] = {
        'task_id': task_id,
        'status': 'running',
        'progress': 5,
        'stage': 'جاري استقبال ملفات الرسالة...',
        'file_name': title or 'رسالة جديدة',
        'result': None,
        'error': None
    }

    report_repo.create_scan_job(
        job_id=task_id,
        filename=title or 'رسالة جديدة',
        title=title,
        author=author
    )

    _EXECUTOR.submit(
        _execute_thesis_pipeline,
        task_id, research_id, file_entries, title, author
    )
    return task_id


def _execute_thesis_pipeline(
    task_id: str,
    research_id: int,
    file_entries: list[dict],
    title: str,
    author: str
):
    """
    خط أنابيب فحص الرسالة متعددة الملفات.
    يستخرج كل ملف على حدة، ينسب كل صفحة لملفها الأصلي،
    ثم يُشغّل المحرك الأكاديمي على النص الموحد.
    """
    try:
        settings = get_current_settings()
        all_pages_data = []    # قائمة موحدة بجميع الصفحات من جميع الملفات
        total_files = len(file_entries)

        for f_idx, entry in enumerate(file_entries):
            prog = 10 + int((f_idx / total_files) * 40)
            _update_progress(
                task_id, prog,
                f'جاري استخراج الملف {f_idx + 1} من {total_files}: {entry["original_filename"]}'
            )

            file_path = entry['path']
            orig_name = entry['original_filename']

            if not os.path.exists(file_path):
                logger.warning(f"ملف الرسالة غير موجود: {file_path}")
                continue

            pages = extract_document_pages(file_path, enable_ocr=settings.get('enable_ocr', True))

            # إضافة معرف الملف الأصلي لكل صفحة (للعزو في التقرير)
            for pg in pages:
                pg['source_file'] = orig_name   # اسم الملف الأصلي
                pg['file_index'] = f_idx

            all_pages_data.extend(pages)

        if not all_pages_data:
            _fail_scan(task_id, 'لم يتم العثور على نصوص قابلة للقراءة في ملفات الرسالة.')
            return

        raw_text = '\n\n'.join(p['text'] for p in all_pages_data if p.get('text'))
        if not raw_text.strip():
            _fail_scan(task_id, 'لم يتم العثور على نصوص قابلة للقراءة في ملفات الرسالة.')
            return

        _update_progress(task_id, 55, 'جاري تحليل الرسالة واكتشاف التطابقات...')

        report = analyze_academic_document(
            raw_text=raw_text,
            pages_data=all_pages_data,
            settings_override=settings
        )

        _update_progress(task_id, 88, 'جاري بناء التقرير النهائي وعزو المصادر...')

        # إثراء بيانات المطابقات بعزو الملف الأصلي
        _enrich_matches_with_file_provenance(report, all_pages_data)

        category = categorize_text(raw_text)
        report_id = str(uuid.uuid4())[:8]
        now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')

        report['id'] = report_id
        report['title'] = title or 'رسالة جديدة'
        report['author'] = author or 'غير محدد'
        report['date'] = now_str
        report['category'] = category
        report['status'] = 'مفحوص'
        report['research_id'] = research_id
        report['file_count'] = len(file_entries)
        report['file_names'] = [e['original_filename'] for e in file_entries]

        report_repo.save_report(
            report_id=report_id,
            title=report['title'],
            overall_pct=report['overall_pct'],
            copied_pct=report['copied_pct'],
            para_pct=report['paraphrase_pct'],
            report_dict=report,
            category=category,
            status='مفحوص',
            author=report['author']
        )

        # تحديث Research بمعرف التقرير
        from app.repositories.batch_repo import update_research_scan
        update_research_scan(research_id, task_id, report_id)

        if task_id in _ACTIVE_SCANS:
            _ACTIVE_SCANS[task_id].update({
                'stage': 'اكتمل تحليل الرسالة بنجاح!',
                'progress': 100,
                'status': 'completed',
                'result': report
            })

        report_repo.update_scan_job(
            job_id=task_id,
            status='completed',
            progress=100,
            stage='اكتمل تحليل الرسالة بنجاح!',
            result_dict=report
        )

    except Exception as e:
        logger.error(f"خطأ أثناء فحص الرسالة {task_id}: {e}", exc_info=True)
        _fail_scan(task_id, f"حدث خطأ أثناء تحليل الرسالة: {str(e)}")


def _enrich_matches_with_file_provenance(report: dict, all_pages_data: list[dict]):
    """
    إثراء المطابقات في التقرير بمعلومات عزو المصدر:
    اسم الملف الأصلي + رقم الصفحة الحقيقي.
    يعمل على المطابقات التي تحتوي page_number مرتبطاً بـ all_pages_data.
    """
    # بناء خريطة: page_number/file_index → source_file
    page_map = {}
    for pg in all_pages_data:
        key = (pg.get('file_index', 0), pg.get('page_number'))
        page_map[key] = pg.get('source_file', '')

    for match in report.get('matches', []):
        submitted_page = match.get('submitted_page')
        # نحاول إيجاد اسم الملف من submitted_page
        for pg in all_pages_data:
            if pg.get('page_number') == submitted_page:
                match['source_file'] = pg.get('source_file', '')
                break


# ─── فحص دفعة أبحاث مستقلة (Batch Scan) ─────────────────────────────────────

def start_batch_scan(batch_id: str, batch_items: list[dict]):
    """
    جدولة فحص دفعة أبحاث مستقلة في الخلفية.
    batch_items: [{'research_id': int, 'file_path': str, 'title': str, 'author': str, 'file_name': str}, ...]
    يُشغَّل بحد أقصى MAX_CONCURRENT_SCANS متزامن.
    فشل عنصر واحد لا يوقف البقية.
    """
    from app.repositories import batch_repo

    def run_batch():
        batch_repo.start_batch(batch_id)
        futures = {}

        with ThreadPoolExecutor(max_workers=config.MAX_CONCURRENT_SCANS) as batch_executor:
            for item in batch_items:
                future = batch_executor.submit(
                    _execute_batch_item,
                    batch_id,
                    item['research_id'],
                    item.get('file_path', ''),
                    item['title'],
                    item['author'],
                    item.get('file_name', ''),
                    item.get('raw_text', '')
                )
                futures[future] = item['research_id']

            for future in as_completed(futures):
                research_id = futures[future]
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"فشل عنصر batch research_id={research_id}: {e}", exc_info=True)
                    batch_repo.update_batch_item(
                        batch_id=batch_id,
                        research_id=research_id,
                        status='error',
                        progress=0,
                        error_message=str(e)
                    )

    _EXECUTOR.submit(run_batch)


def _execute_batch_item(
    batch_id: str,
    research_id: int,
    file_path: str,
    title: str,
    author: str,
    file_name: str,
    raw_text: str
):
    """تنفيذ فحص عنصر واحد داخل الدفعة."""
    from app.repositories import batch_repo

    task_id = str(uuid.uuid4())[:10]

    try:
        batch_repo.update_batch_item(
            batch_id=batch_id,
            research_id=research_id,
            status='running',
            progress=10,
            scan_job_id=task_id
        )

        _ACTIVE_SCANS[task_id] = {
            'task_id': task_id,
            'status': 'running',
            'progress': 10,
            'stage': 'جاري البدء...',
            'file_name': file_name or title,
            'result': None,
            'error': None
        }

        report_repo.create_scan_job(
            job_id=task_id,
            filename=file_name or title or 'نص مدخل',
            title=title,
            author=author
        )

        # تنفيذ الفحص الفعلي مع Semaphore
        with _BATCH_SEMAPHORE:
            _execute_scan_pipeline(task_id, file_path, title, author, raw_text, file_name)

        # جلب النتيجة وتحديث الدفعة
        result = _ACTIVE_SCANS.get(task_id, {})
        status = result.get('status', 'error')
        report = result.get('result')
        similarity_pct = report.get('overall_pct') if report else None
        report_id = report.get('id') if report else None

        batch_repo.update_batch_item(
            batch_id=batch_id,
            research_id=research_id,
            status='completed' if status == 'completed' else 'error',
            progress=100,
            report_id=report_id,
            error_message=result.get('error') or '',
            similarity_pct=similarity_pct
        )

        # تحديث Research بمعرف التقرير
        if report_id:
            batch_repo.update_research_scan(research_id, task_id, report_id)

    except Exception as e:
        logger.error(f"خطأ في _execute_batch_item research_id={research_id}: {e}", exc_info=True)
        from app.repositories import batch_repo as br
        br.update_batch_item(
            batch_id=batch_id,
            research_id=research_id,
            status='error',
            progress=0,
            error_message=f"خطأ داخلي: {str(e)}"
        )


# ─── خط الأنابيب الأصلي (بدون تغيير جوهري) ──────────────────────────────────

def _execute_scan_pipeline(
    task_id: str,
    file_path: str,
    title: str,
    author: str,
    raw_text: str,
    file_name: str
):
    """تنفيذ خط أنابيب الفحص الأكاديمي الشامل في مسار الخلفية."""
    try:
        # المرحلة 1: استخراج الصفحات والنصوص
        _update_progress(task_id, 20, 'جاري استخراج وقراءة النصوص والصفحات من المستند...')
        pages_data = []

        if file_path and os.path.exists(file_path):
            settings = get_current_settings()
            pages_data = extract_document_pages(file_path, enable_ocr=settings.get('enable_ocr', True))
            if not raw_text:
                raw_text = '\n\n'.join(p['text'] for p in pages_data if p['text'])

        if not raw_text.strip():
            _fail_scan(task_id, 'لم يتم العثور على نصوص قابلة للقراءة في هذا الملف.')
            return

        # المرحلة 2: كشف التلاعب وتحليل الاستشهاد
        _update_progress(task_id, 45, 'جاري فحص المسافات المخفية وعلامات التنصيص والتوثيق...')

        # المرحلة 3: المطابقة متعددة المراحل واسترجاع المرشحين
        _update_progress(task_id, 70, 'جاري مطابقة المتواليات واسترجاع المرشحين من المراجع...')
        settings = get_current_settings()
        report = analyze_academic_document(
            raw_text=raw_text,
            pages_data=pages_data if pages_data else None,
            settings_override=settings
        )

        # المرحلة 4: تصنيف التخصص واللمسات النهائية
        _update_progress(task_id, 90, 'جاري حساب أرقام الصفحات المصدرية والصفحات المسموحة...')
        category = categorize_text(raw_text)

        report_id = str(uuid.uuid4())[:8]
        now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')

        report['id'] = report_id
        report['title'] = title if title else (file_name if file_name else 'بحث جديد')
        report['author'] = author if author else 'غير محدد'
        report['date'] = now_str
        report['category'] = category
        report['file_path'] = file_path
        report['status'] = 'مفحوص'

        # حفظ التقرير في قاعدة البيانات
        report_repo.save_report(
            report_id=report_id,
            title=report['title'],
            overall_pct=report['overall_pct'],
            copied_pct=report['copied_pct'],
            para_pct=report['paraphrase_pct'],
            report_dict=report,
            category=category,
            status='مفحوص',
            author=report['author'],
            file_path=file_path
        )

        # اكتمال المهمة
        if task_id in _ACTIVE_SCANS:
            _ACTIVE_SCANS[task_id]['stage'] = 'اكتمل التحليل بنجاح!'
            _ACTIVE_SCANS[task_id]['progress'] = 100
            _ACTIVE_SCANS[task_id]['status'] = 'completed'
            _ACTIVE_SCANS[task_id]['result'] = report

        report_repo.update_scan_job(
            job_id=task_id,
            status='completed',
            progress=100,
            stage='اكتمل التحليل بنجاح!',
            result_dict=report
        )

    except Exception as e:
        logger.error(f"خطأ أثناء فحص المهمة {task_id}: {e}", exc_info=True)
        _fail_scan(task_id, f"حدث خطأ أثناء المعالجة: {str(e)}")


def _update_progress(task_id: str, progress: int, stage: str):
    if task_id in _ACTIVE_SCANS:
        _ACTIVE_SCANS[task_id]['progress'] = progress
        _ACTIVE_SCANS[task_id]['stage'] = stage
    report_repo.update_scan_job(job_id=task_id, status='running', progress=progress, stage=stage)


def _fail_scan(task_id: str, error_msg: str):
    if task_id in _ACTIVE_SCANS:
        _ACTIVE_SCANS[task_id]['status'] = 'error'
        _ACTIVE_SCANS[task_id]['error'] = error_msg
    report_repo.update_scan_job(job_id=task_id, status='error', progress=0, stage='حدث خطأ', error=error_msg)
