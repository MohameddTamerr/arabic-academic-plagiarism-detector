# -*- coding: utf-8 -*-
"""
خدمة إدارة وفحص الرسائل العلمية والتقرير المجمع (Thesis Management & Combined Report Service):
- إدارة دورة حياة الرسالة العلمية متعددة الأجزاء.
- جدولة وفحص الأجزاء المستقلة عبر طابور المهام المنضبط.
- التجميع الرياضي الموزون بدقة للتقرير المجمع (Weighted Similarity Aggregation).
- منع التقدير الحسابي البسيط غير الموزون (No Simple Unweighted Averages).
- ضمان إدارة المراجعات (Revisions) والنزاهة الرقمية وعدم المساس بالتقارير المعتمدة.
"""

import os
import uuid
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from collections import defaultdict

import config
from app.repositories import thesis_repo, report_repo, base_repo
from app.models.schema import LegacyReport, Document
from app.services import audit_service, job_queue_service, report_integrity_service
from app.services.job_queue_service import JobType
from plagiarism_detector.reporting.report_builder import analyze_academic_document
from app.services.self_match_service import reference_ids_for_work
from plagiarism_detector.extraction.page_extractor import extract_document_pages
from plagiarism_detector.reporting.page_allowance import compute_source_allowance
from app.services.settings_service import get_current_settings
from app import versioning

logger = logging.getLogger(__name__)


# ─── 1. تشغيل فحص جزء محدد ──────────────────────────────────────────────────

def scan_thesis_part(part_id: int, requested_by: str = '') -> str:
    """
    إطلاق فحص لجزء محدد من الرسالة عبر الطابور والتزامن المنضبط.
    يُعيد task_id.
    """
    part = thesis_repo.get_thesis_part(part_id)
    if not part:
        raise ValueError("الجزء المطلوب غير موجود")

    task_id = str(uuid.uuid4())[:10]

    thesis_repo.update_thesis_part_scan_result(
        part_id=part_id,
        scan_status='queued',
        scan_job_id=task_id
    )

    report_repo.create_scan_job(
        job_id=task_id,
        filename=part['original_filename'],
        title=part['part_title'],
        author=f"رسالة {part['thesis_id']}"
    )

    job_queue_service.enqueue_job(
        job_type=JobType.SCAN,
        payload={'part_id': part_id, 'file_path': part['file_path'], 'part_title': part['part_title']},
        requested_by=requested_by,
        custom_job_id=task_id,
        scan_execution_id=task_id
    )

    from app.services.scan_service import _EXECUTOR
    _EXECUTOR.submit(_execute_part_scan, task_id, part_id)

    return task_id


def _execute_part_scan(task_id: str, part_id: int):
    """تنفيذ عملية الفحص لجزء الرسالة في الخلفية."""
    try:
        if job_queue_service.is_cancellation_requested(task_id):
            job_queue_service.finalize_cancellation(task_id)
            thesis_repo.update_thesis_part_scan_result(part_id=part_id, scan_status='interrupted')
            return

        part = thesis_repo.get_thesis_part(part_id)
        if not part or not os.path.exists(part['file_path']):
            err = "ملف الجزء غير موجود على القرص"
            report_repo.update_scan_job(task_id, status='error', error=err)
            thesis_repo.update_thesis_part_scan_result(part_id=part_id, scan_status='failed', error_message=err)
            return

        settings = get_current_settings()
        report_repo.update_scan_job(task_id, status='running', progress=15, stage='جاري استخراج نصوص وصفحات الجزء...')

        from app.services.scan_service import _find_exact_reference_match, _pdf_progress_callback
        exact_reference_match = _find_exact_reference_match(part['file_path'])
        if exact_reference_match:
            report_repo.update_scan_job(
                task_id,
                status='running',
                progress=50,
                stage='تم اكتشاف ملف مطابق تماماً لمرجع نشط — تم تجاوز OCR',
            )
            pages_data = [dict(page) for page in exact_reference_match.get('pages', [])]
        else:
            pages_data = extract_document_pages(
                part['file_path'],
                enable_ocr=settings.get('enable_ocr', True),
                progress_callback=_pdf_progress_callback(task_id, 15, 50, 'جاري قراءة صفحات الجزء'),
            )
        for pg in pages_data:
            pg['source_file'] = part['original_filename']
            pg['part_title'] = part['part_title']

        if not pages_data:
            err = 'لم يتم العثور على صفحات أو نصوص قابلة للقراءة في هذا الجزء.'
            report_repo.update_scan_job(task_id, status='error', error=err)
            thesis_repo.update_thesis_part_scan_result(part_id=part_id, scan_status='failed', error_message=err)
            return

        raw_text = '\n\n'.join(p.get('text', '') for p in pages_data if p.get('text'))
        if not raw_text.strip():
            err = 'لم يتم العثور على نصوص قابلة للقراءة في هذا الجزء.'
            report_repo.update_scan_job(task_id, status='error', error=err)
            thesis_repo.update_thesis_part_scan_result(part_id=part_id, scan_status='failed', error_message=err)
            return

        report_repo.update_scan_job(task_id, status='running', progress=60, stage='جاري مطابقة النصوص واكتشاف الشواهد...')

        report = analyze_academic_document(
            raw_text=raw_text,
            pages_data=pages_data,
            settings_override=settings,
            exact_reference_match=exact_reference_match,
            excluded_doc_ids=reference_ids_for_work(thesis_id=part['thesis_id']),
        )

        report_repo.update_scan_job(task_id, status='running', progress=90, stage='جاري حفظ نتائج التقرير الفردي...')

        report_id = str(uuid.uuid4())[:8]
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M')

        th = thesis_repo.get_thesis(part['thesis_id'])
        th_title = th['title'] if th else 'رسالة علمية'
        th_author = th['author'] if th else 'غير محدد'
        th_ref = th['reference_number'] if th else ''

        report['id'] = report_id
        report['title'] = f"{th_title} — {part['part_title']}"
        report['author'] = th_author
        report['date'] = now_str
        report['file_path'] = part['file_path']
        report['status'] = 'مفحوص'
        report['thesis_id'] = part['thesis_id']
        report['thesis_part_id'] = part_id
        report['reference_number'] = th_ref

        report_repo.save_report(
            report_id=report_id,
            title=report['title'],
            overall_pct=report['overall_pct'],
            copied_pct=report['copied_pct'],
            para_pct=report['paraphrase_pct'],
            report_dict=report,
            status='مفحوص',
            author=th_author,
            file_path=part['file_path']
        )

        # تحديث نتائج الجزء في DB
        thesis_repo.update_thesis_part_scan_result(
            part_id=part_id,
            scan_status='completed',
            scan_job_id=task_id,
            report_id=report_id,
            similarity_pct=report.get('overall_pct', 0.0),
            problematic_pct=report.get('problematic_pct', 0.0),
            copied_pct=report.get('copied_pct', 0.0),
            para_pct=report.get('paraphrase_pct', 0.0),
            cited_pct=report.get('cited_pct', 0.0),
            total_words=report.get('total_words', 0),
            problematic_words=report.get('problematic_words', 0),
            copied_words=report.get('copied_words', 0),
            para_words=report.get('paraphrased_words', 0),
            cited_words=report.get('cited_words', 0),
            error_message=''
        )

        report_repo.update_scan_job(
            task_id,
            status='completed',
            progress=100,
            stage='اكتمل فحص الجزء بنجاح',
            result_dict={'report_id': report_id, 'overall_pct': report['overall_pct']}
        )

        audit_service.record_event(
            action="THESIS_PART_SCANNED",
            category="thesis",
            object_type="thesis_part",
            object_id=str(part_id),
            success=True,
            metadata={
                'thesis_id': part['thesis_id'],
                'part_title': part['part_title'],
                'report_id': report_id,
                'overall_pct': report['overall_pct'],
                'problematic_pct': report['problematic_pct']
            }
        )

    except Exception as e:
        logger.error(f"خطأ أثناء فحص جزء الرسالة {part_id}: {e}", exc_info=True)
        report_repo.update_scan_job(task_id, status='error', error=str(e))
        thesis_repo.update_thesis_part_scan_result(part_id=part_id, scan_status='failed', error_message=str(e))


# ─── 2. التجميع الرياضي الموزون للتقرير المجمع ────────────────────────────────

def generate_combined_thesis_report(
    thesis_id: int,
    actor_user: Optional[dict] = None
) -> Tuple[bool, Optional[dict], str]:
    """
    إنشاء أو تحديث التقرير المجمع للرسالة العلمية (Combined Thesis Report):
    - يجمع كافة الأجزاء المكتملة رياضياً بالحساب الموزون الدقيق على أساس الكلمات القابلة للفحص.
    - يستبعد المتوسطات الحسابية البسيطة غير الموزونة.
    - يحذر بوضوح إذا كانت هناك أجزاء غير مكتملة أو فاشلة.
    - يدير الإصدارات الرقمية (Revisions) وحفظ البصمة الرقمية للنزاهة.
    """
    thesis = thesis_repo.get_thesis(thesis_id)
    if not thesis:
        return False, None, "الرسالة العلمية غير موجودة"

    parts = thesis.get('parts', [])
    if not parts:
        return False, None, "لا توجد أجزاء مضافة للرسالة"

    completed_parts = [p for p in parts if p['scan_status'] == 'completed' and p.get('report_id')]
    incomplete_parts = [p for p in parts if p['scan_status'] != 'completed' or not p.get('report_id')]

    if not completed_parts:
        return False, None, "لم يكتمل فحص أي جزء من أجزاء الرسالة حتى الآن"

    # ── أ. التجميع الرياضي الموزون الصارم ─────────────────────────────────────
    total_clean_words = 0
    total_copied_words = 0
    total_para_words = 0
    total_cited_words = 0
    total_problematic_words = 0
    total_raw_words = 0

    combined_segments = []
    sources_dict: dict[int, dict] = {}
    words_by_source: dict[int, int] = defaultdict(int)
    pages_by_source: dict[int, set] = defaultdict(set)

    part_summaries = []
    input_manifest = []

    for idx, p in enumerate(completed_parts):
        rep = report_repo.get_report(p['report_id'])
        if not rep:
            continue

        p_total = rep.get('total_words', 0)
        p_copied = rep.get('copied_words', 0)
        p_para = rep.get('paraphrased_words', 0)
        p_cited = rep.get('cited_words', 0)
        p_prob = rep.get('problematic_words', (p_copied + p_para))

        total_clean_words += p_total
        total_raw_words += p_total
        total_copied_words += p_copied
        total_para_words += p_para
        total_cited_words += p_cited
        total_problematic_words += p_prob

        part_summaries.append({
            'part_id': p['id'],
            'part_title': p['part_title'],
            'sort_order': p['sort_order'],
            'original_filename': p['original_filename'],
            'file_hash': p['file_hash'],
            'scan_status': 'completed',
            'report_id': p['report_id'],
            'total_words': p_total,
            'copied_words': p_copied,
            'paraphrased_words': p_para,
            'cited_words': p_cited,
            'problematic_words': p_prob,
            'overall_pct': rep.get('overall_pct', 0.0),
            'problematic_pct': rep.get('problematic_pct', 0.0),
            'settings_used': rep.get('settings_snapshot', {})
        })

        input_manifest.append({
            'file_id': p['id'],
            'part_title': p['part_title'],
            'file_order': p['sort_order'],
            'original_filename': p['original_filename'],
            'sha256': p['file_hash'],
            'file_size_bytes': p['file_size_bytes'],
            'file_type': p['file_type'],
            'storage_status': 'finalized'
        })

        # دمج المقاطع مع عزو الجزء
        for seg in rep.get('segments', []):
            seg_copy = dict(seg)
            seg_copy['part_id'] = p['id']
            seg_copy['part_title'] = p['part_title']
            combined_segments.append(seg_copy)

        # دمج المصادر
        for s in rep.get('sources', []):
            s_id = s.get('source_id')
            if s_id is not None:
                s_words = s.get('matched_words', 0)
                words_by_source[s_id] += s_words
                for pg in s.get('matched_pages', []):
                    pages_by_source[s_id].add(pg)
                if s_id not in sources_dict:
                    sources_dict[s_id] = {
                        'source_id': s_id,
                        'title': s.get('source_title', ''),
                        'author': s.get('source_author', '')
                    }

    total_safe_words = max(total_clean_words, 1)
    total_matched_words = total_copied_words + total_para_words + total_cited_words

    # الحساب الرياضي الموزون الحقيقي:
    combined_overall_pct = min(round((total_matched_words / total_safe_words) * 100, 1), 100.0)
    combined_problematic_pct = min(round((total_problematic_words / total_safe_words) * 100, 1), combined_overall_pct)
    combined_copied_pct = min(round((total_copied_words / total_safe_words) * 100, 1), 100.0)
    combined_para_pct = min(round((total_para_words / total_safe_words) * 100, 1), 100.0)
    combined_cited_pct = min(round((total_cited_words / total_safe_words) * 100, 1), 100.0)

    # إعادة حساب المصادر المجمعة مع حدود الصفحات
    settings = get_current_settings()
    sources_list = []
    exceeded_sources = []

    for s_id, s_words in words_by_source.items():
        s_meta = sources_dict.get(s_id, {})
        s_title = s_meta.get('title', '')
        s_author = s_meta.get('author', '')
        s_pages_set = pages_by_source[s_id]

        allowance = compute_source_allowance(
            source_id=s_id,
            source_title=s_title,
            source_author=s_author,
            matched_words=s_words,
            matched_pages_set=s_pages_set,
            words_per_page=settings.get('words_per_page', 250),
            max_allowed_pages=settings.get('max_allowed_pages_per_source', 3.0)
        )
        allowance['pct'] = round((s_words / total_safe_words) * 100, 1)
        sources_list.append(allowance)
        if allowance['is_limit_exceeded']:
            exceeded_sources.append(allowance)

    sources_list.sort(key=lambda x: x['matched_words'], reverse=True)

    # ── ب. إدارة الإصدارات والتقرير المجمع ─────────────────────────────────────
    new_report_id = str(uuid.uuid4())[:8]
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')

    # جلب الإصدار السابق للتقرير المجمع إن وجد
    prev_report_id = thesis.get('combined_report_id')
    prev_rev = 1
    if prev_report_id:
        prev_rep = report_repo.get_report(prev_report_id)
        if prev_rep:
            prev_rev = prev_rep.get('revision_number', 1)
            # إذا كان التقرير السابق معتمداً أو موجوداً، التقرير الجديد يأخذ الإصدار التالي
            new_rev = prev_rev + 1
        else:
            new_rev = 1
    else:
        new_rev = 1

    is_complete_thesis = (len(incomplete_parts) == 0)

    combined_report_dict = {
        'id': new_report_id,
        'title': f"التقرير المجمع — {thesis['title']}",
        'author': thesis['author'],
        'date': now_str,
        'overall_pct': combined_overall_pct,
        'problematic_pct': combined_problematic_pct,
        'copied_pct': combined_copied_pct,
        'paraphrase_pct': combined_para_pct,
        'cited_pct': combined_cited_pct,
        'total_words': total_clean_words,
        'copied_words': total_copied_words,
        'paraphrased_words': total_para_words,
        'cited_words': total_cited_words,
        'problematic_words': total_problematic_words,
        'sources': sources_list,
        'segments': combined_segments,
        'part_summaries': part_summaries,
        'incomplete_parts': [
            {
                'part_id': ip['id'],
                'part_title': ip['part_title'],
                'sort_order': ip['sort_order'],
                'original_filename': ip['original_filename'],
                'scan_status': ip['scan_status'],
                'error_message': ip.get('error_message', '')
            }
            for ip in incomplete_parts
        ],
        'is_complete_thesis': is_complete_thesis,
        'completion_status_label_ar': 'مكتملة الفحص لكافة الأجزاء' if is_complete_thesis else f'غير مكتملة الفحص ({len(incomplete_parts)} أجزاء غير مكتملة)',
        'thesis_id': thesis_id,
        'reference_number': thesis['reference_number'],
        'degree_type': thesis.get('degree_type', 'ماجستير'),
        'department': thesis.get('department', ''),
        'academic_year': thesis.get('academic_year', ''),
        'is_combined_thesis': True,
        'revision_number': new_rev,
        'supersedes_report_id': prev_report_id,
        'artifact_status': 'draft',
        'application_version': versioning.APPLICATION_VERSION,
        'engine_version': versioning.ENGINE_VERSION,
        'detector_version': versioning.DETECTOR_VERSION,
        'settings_snapshot': dict(settings),
        'part_settings_snapshots': [{'part_id': p['part_id'], 'report_id': p['report_id'], 'settings_used': p['settings_used']} for p in part_summaries],
        'combined_settings_scope': 'page_allowance_aggregation_only'
    }

    # حفظ التقرير المجمع
    report_repo.save_report(
        report_id=new_report_id,
        title=combined_report_dict['title'],
        overall_pct=combined_overall_pct,
        copied_pct=combined_copied_pct,
        para_pct=combined_para_pct,
        report_dict=combined_report_dict,
        status='مفحوص',
        author=thesis['author']
    )

    # ربط التقرير بـ LegacyReport
    with base_repo.get_session() as session:
        rep_row = session.query(LegacyReport).filter(LegacyReport.id == new_report_id).first()
        if rep_row:
            rep_row.thesis_id = thesis_id
            rep_row.is_combined_thesis = 1
            rep_row.revision_number = new_rev
            rep_row.supersedes_report_id = prev_report_id
            rep_row.artifact_status = 'draft'
            if actor_user:
                rep_row.submitted_by_user_id = actor_user.get('id')
                rep_row.submitted_by = actor_user.get('username', '')

    # تحديث كائن الرسالة
    thesis_repo.update_thesis_status(
        thesis_id=thesis_id,
        status='completed' if is_complete_thesis else 'incomplete',
        combined_report_id=new_report_id,
        is_stale=0
    )

    audit_service.record_event(
        action="THESIS_COMBINED_REPORT_CREATED",
        category="thesis",
        user=actor_user,
        object_type="thesis",
        object_id=str(thesis_id),
        success=True,
        metadata={
            'thesis_id': thesis_id,
            'report_id': new_report_id,
            'revision_number': new_rev,
            'combined_overall_pct': combined_overall_pct,
            'combined_problematic_pct': combined_problematic_pct,
            'completed_parts_count': len(completed_parts),
            'incomplete_parts_count': len(incomplete_parts),
            'is_complete': is_complete_thesis
        }
    )

    return True, combined_report_dict, "تم إنشاء التقرير المجمع للرسالة العلمية بنجاح"
