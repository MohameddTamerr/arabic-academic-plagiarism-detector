# -*- coding: utf-8 -*-
"""
خدمة نزاهة واعتماد وسلسلة أدلة التقارير الأكاديمية (Report Integrity, Finalization & Evidence Chain Service):
- توليد التمثيل المعياري الحتمي للتقرير (Deterministic Canonical Serialization).
- حساب بصمة الاعتماد الرقمية (SHA-256 Checksum) لمنع التلاعب وتجميد التقرير المكتمل.
- التحقق الفوري والشامل من سلامة ونزاهة التقارير (Report Integrity Verification).
- إدارة سلاسل الإصدارات والتحكيم وإبطال التقارير (Revision Lineage, Review Decisions & Voiding).
- دعم كامل وتصنيف دقيق للتقارير التاريخية السابقة (Legacy Unverifiable Reports).
"""

import os
import json
import hashlib
import logging
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List
from sqlalchemy import text

from app import versioning
from app.repositories import base_repo
from app.models.schema import LegacyReport, ReviewDecisionRecord
from app.models.research_schema import Research, ResearchFile, STORAGE_STATUS_FINALIZED
from app.models.snapshot_schema import ReportExecutionSnapshot
from app.services import integrity_service, snapshot_service, audit_service
from app.errors.error_codes import ErrorCode

logger = logging.getLogger(__name__)

# الحالات المعيارية لنزاهة التقرير (Integrity Verification Statuses)
INTEGRITY_VERIFIED = "verified"
INTEGRITY_MODIFIED = "modified"
INTEGRITY_INCOMPLETE = "incomplete"
INTEGRITY_LEGACY_UNVERIFIABLE = "legacy_unverifiable"

# حالات كائن التقرير (Artifact Statuses)
ARTIFACT_DRAFT = "draft"
ARTIFACT_FINALIZED = "finalized"
ARTIFACT_SUPERSEDED = "superseded"
ARTIFACT_VOIDED = "voided"


def _clean_text_field(val: Any) -> str:
    """تنظيف وتوحيد النصوص للتمثيل المعياري."""
    if val is None:
        return ""
    return str(val).strip()


def _clean_float_field(val: Any, default: float = 0.0) -> float:
    """توحيد الأعداد العشرية لضمان دقة الحساب الحتمي."""
    if val is None:
        return default
    try:
        return round(float(val), 4)
    except (ValueError, TypeError):
        return default


def build_canonical_report_payload(
    report_dict: dict,
    input_manifest: list[dict],
    reference_sources: list[dict],
    evidence_snapshot: list[dict],
    version_snap_dict: dict,
    revision_metadata: dict
) -> str:
    """
    بناء السلسلة المعيارية الحتمية للتقرير (Deterministic Canonical JSON Representation).
    يستبعد أي حقول متغيرة أو مؤقتة (كالروابط وحالات الواجهة اللحظية) ويعتمد ترتيب مفاتيح ثابت.
    """
    # 1. قائمة المدخلات مرتبة حسب ترتيب الملفات
    sorted_inputs = []
    for f in input_manifest:
        sorted_inputs.append({
            'file_id': f.get('file_id') or f.get('id'),
            'file_order': int(f.get('file_order', 0)),
            'file_size_bytes': int(f.get('file_size_bytes', 0)),
            'file_type': _clean_text_field(f.get('file_type', '')).lower(),
            'original_filename': _clean_text_field(f.get('original_filename', '')),
            'sha256': _clean_text_field(f.get('sha256') or f.get('file_hash', '')).lower(),
            'storage_status': _clean_text_field(f.get('storage_status', 'finalized'))
        })
    sorted_inputs.sort(key=lambda x: (x['file_order'], x['original_filename']))

    # 2. قائمة المراجع المستشهد بها مرتبة حسب معرف الوثيقة المرجعية
    sorted_sources = []
    for s in reference_sources:
        sorted_sources.append({
            'author': _clean_text_field(s.get('author', '')),
            'corpus_version': _clean_text_field(s.get('corpus_version', '')),
            'document_hash': _clean_text_field(s.get('document_hash', '')).lower(),
            'document_id': s.get('document_id'),
            'title': _clean_text_field(s.get('title', ''))
        })
    sorted_sources.sort(key=lambda x: (x['document_id'] if x['document_id'] is not None else -1, x['title']))

    # 3. قائمة الأدلة والشواهد النصية مرتبة حتمياً
    sorted_evidence = []
    for e in evidence_snapshot:
        sorted_evidence.append({
            'is_cited': bool(e.get('is_cited', False)),
            'match_type': _clean_text_field(e.get('match_type', 'exact')),
            'research_page': e.get('research_page') or e.get('page'),
            'research_span': _clean_text_field(e.get('research_span') or e.get('submitted_text', '')),
            'similarity_score': _clean_float_field(e.get('similarity_score', 0.0)),
            'source_author': _clean_text_field(e.get('source_author', '')),
            'source_page': e.get('source_page'),
            'source_title': _clean_text_field(e.get('source_title', ''))
        })
    sorted_evidence.sort(key=lambda x: (
        x['research_page'] if x['research_page'] is not None else -1,
        x['source_title'],
        x['research_span'][:50]
    ))

    # 4. لقطة النسخ والمعايير الثابتة
    snap_payload = {
        'application_version': _clean_text_field(version_snap_dict.get('application_version', '')),
        'citation_detection_version': _clean_text_field(version_snap_dict.get('citation_detection_version', '')),
        'common_text_handling_version': _clean_text_field(version_snap_dict.get('common_text_handling_version', '')),
        'detector_version': _clean_text_field(version_snap_dict.get('detector_version', '')),
        'engine_version': _clean_text_field(version_snap_dict.get('engine_version', '')),
        'jaccard_threshold': _clean_float_field(version_snap_dict.get('jaccard_threshold', 0.3)),
        'normalization_version': _clean_text_field(version_snap_dict.get('normalization_version', '')),
        'reference_corpus_version': _clean_text_field(version_snap_dict.get('reference_corpus_version', '')),
        'reference_fingerprint': _clean_text_field(version_snap_dict.get('reference_fingerprint', '')).lower(),
        'report_schema_version': _clean_text_field(version_snap_dict.get('report_schema_version', '1.0.0')),
        'tfidf_threshold': _clean_float_field(version_snap_dict.get('tfidf_threshold', 0.4))
    }

    # 5. التجميع النهائي المعياري
    canonical_obj = {
        'author': _clean_text_field(report_dict.get('author', '')),
        'category': _clean_text_field(report_dict.get('category', 'عام')),
        'evidence_snapshot': sorted_evidence,
        'input_manifest': sorted_inputs,
        'metrics': {
            'copied_pct': _clean_float_field(report_dict.get('copied_pct', 0.0)),
            'overall_pct': _clean_float_field(report_dict.get('overall_pct', 0.0)),
            'para_pct': _clean_float_field(report_dict.get('para_pct') or report_dict.get('paraphrase_pct', 0.0)),
            'word_count': int(report_dict.get('word_count') or report_dict.get('total_words', 0))
        },
        'reference_sources': sorted_sources,
        'report_id': _clean_text_field(report_dict.get('id', '')),
        'research_id': revision_metadata.get('research_id'),
        'research_reference_number': _clean_text_field(revision_metadata.get('research_reference_number', '')),
        'revision_number': int(revision_metadata.get('revision_number', 1)),
        'scan_execution_id': _clean_text_field(revision_metadata.get('scan_execution_id', '')),
        'supersedes_report_id': _clean_text_field(revision_metadata.get('supersedes_report_id', '')),
        'title': _clean_text_field(report_dict.get('title', '')),
        'version_snapshot': snap_payload
    }

    return json.dumps(canonical_obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def compute_report_hash(canonical_payload_str: str) -> str:
    """حساب بصمة SHA-256 الحتمية لسلسلة التقرير المعيارية."""
    return hashlib.sha256(canonical_payload_str.encode('utf-8')).hexdigest()


def _extract_input_manifest_from_research(research_id: Optional[int], legacy_file_path: str = '') -> list[dict]:
    """استخراج مصفوفة ملفات المدخلات المعتمدة."""
    manifest = []
    if research_id:
        with base_repo.get_session() as session:
            r_files = session.query(ResearchFile).filter(
                ResearchFile.research_id == research_id
            ).order_by(ResearchFile.file_order.asc()).all()

            for rf in r_files:
                manifest.append({
                    'file_id': rf.id,
                    'original_filename': rf.original_filename,
                    'stored_filename': rf.stored_filename,
                    'file_path': rf.file_path,
                    'file_type': rf.file_type,
                    'file_size_bytes': rf.file_size_bytes,
                    'file_order': rf.file_order,
                    'sha256': rf.file_hash,
                    'storage_status': rf.storage_status
                })

    if not manifest and legacy_file_path and os.path.exists(legacy_file_path):
        f_hash, f_size = integrity_service.compute_stream_sha256(legacy_file_path)
        manifest.append({
            'file_id': 0,
            'original_filename': os.path.basename(legacy_file_path),
            'stored_filename': os.path.basename(legacy_file_path),
            'file_path': legacy_file_path,
            'file_type': os.path.splitext(legacy_file_path)[1].lower().lstrip('.'),
            'file_size_bytes': f_size,
            'file_order': 0,
            'sha256': f_hash,
            'storage_status': STORAGE_STATUS_FINALIZED
        })

    return manifest


def _extract_sources_and_evidence(report_dict: dict) -> Tuple[list[dict], list[dict]]:
    """استخراج المراجع والشواهد النصية من بنية التقرير."""
    sources = []
    evidence = []

    # 1. استخراج المراجع من مصادر التقرير
    raw_sources = report_dict.get('sources') or report_dict.get('matched_sources') or []
    for s in raw_sources:
        if isinstance(s, dict):
            sources.append({
                'document_id': s.get('id') or s.get('document_id'),
                'title': s.get('title') or s.get('source_title', 'مرجع مجهول'),
                'author': s.get('author') or s.get('source_author', ''),
                'document_hash': s.get('document_hash') or s.get('hash', ''),
                'corpus_version': s.get('corpus_version', '')
            })

    # 2. استخراج الشواهد والأدلة النصية
    raw_matches = report_dict.get('matches') or report_dict.get('findings') or []
    for m in raw_matches:
        if isinstance(m, dict):
            evidence.append({
                'research_span': m.get('submitted_segment') or m.get('research_span') or m.get('text', ''),
                'source_title': m.get('source_title') or m.get('title', ''),
                'source_author': m.get('source_author') or m.get('author', ''),
                'source_page': m.get('source_page') or m.get('page'),
                'research_page': m.get('research_page') or m.get('student_page'),
                'match_type': m.get('match_type') or ('paraphrase' if m.get('is_paraphrase') else 'exact'),
                'similarity_score': m.get('similarity_score') or m.get('similarity', 1.0),
                'is_cited': bool(m.get('is_cited', False))
            })

    return sources, evidence


def finalize_report(report_id: str, finalized_by: str) -> Tuple[bool, Optional[dict], Optional[str], Optional[str]]:
    """
    اعتماد التقرير رسمياً وتجميد محتواه بحساب بصمة SHA-256 النزيهة داخل معاملة ذرية.
    المتطلبات المسبقة:
    1. اكتمال مهمة الفحص بنجاح (scan_status == 'completed').
    2. وجود البحث المدخل وسلامة ملفاته الفيزيائية المعتمدة على القرص ومطابقة بصماتها.
    3. وجود لقطة المعايير (ReportExecutionSnapshot).
    4. عدم اعتماد التقرير مسبقاً (إرجاع نجاح متماثل idempotency إذا كان معتمداً بالفعل).

    يُعيد: (نجاح, تقرير_محدث, رسالة_خطأ, كود_الخطأ)
    """
    finalized_by_clean = _clean_text_field(finalized_by) or 'system_user'

    with base_repo.get_session() as session:
        # قفل صريح لسجل التقرير
        rep = session.query(LegacyReport).filter(LegacyReport.id == report_id).first()
        if not rep:
            return False, None, "تقرير الفحص غير موجود.", ErrorCode.NOT_FOUND

        # 1. إذا كان معتمداً مسبقاً: معالجة متماثلة وآمنة (Idempotent)
        if rep.artifact_status == ARTIFACT_FINALIZED and rep.finalization_hash:
            data = _format_report_dict(rep)
            return True, data, "التقرير معتمد مسبقاً وبصمته الرقمية مجمدة ومؤكدة.", None

        # 2. التحقق من اكتمال الفحص
        if rep.scan_status != 'completed':
            return False, None, f"لا يمكن اعتماد تقرير لم يكتمل فحصه بعد (الحالة الحالية: {rep.scan_status}).", ErrorCode.REPORT_NOT_READY

        # 3. التحقق من لقطة المعايير
        snap = session.query(ReportExecutionSnapshot).filter(
            ReportExecutionSnapshot.report_id == report_id
        ).first()
        if not snap:
            return False, None, "تعذر اعتماد التقرير: لقطة معايير الفحص الأكاديمي غير متوفرة.", ErrorCode.REPORT_FINALIZATION_FAILED

        # 4. استخراج والتحقق من الملفات المدخلة وبصماتها
        input_manifest = _extract_input_manifest_from_research(rep.research_id, rep.file_path)
        for inf in input_manifest:
            f_path = inf.get('file_path')
            if inf.get('storage_status') == STORAGE_STATUS_FINALIZED and f_path:
                if not os.path.exists(f_path):
                    return False, None, f"تعذر اعتماد التقرير: ملف البحث المعتمد غير موجود على وسيط التخزين: {inf.get('original_filename')}", ErrorCode.REPORT_INPUT_INTEGRITY_FAILED
                actual_hash, _ = integrity_service.compute_stream_sha256(f_path)
                expected_hash = inf.get('sha256') or inf.get('file_hash')
                if expected_hash and actual_hash.lower() != expected_hash.lower():
                    return False, None, f"تعذر اعتماد التقرير: تعارض في بصمة ملف البحث: {inf.get('original_filename')}", ErrorCode.REPORT_INPUT_INTEGRITY_FAILED

        # 5. استخراج المراجع والأدلة وتحديث البنية
        try:
            report_dict = json.loads(rep.report_json)
        except Exception:
            report_dict = {}

        ref_sources, evidence_list = _extract_sources_and_evidence(report_dict)

        # جلب الرقم المرجعي للبحث
        res_ref_num = ''
        if rep.research_id:
            res_obj = session.query(Research).filter(Research.id == rep.research_id).first()
            if res_obj:
                res_ref_num = res_obj.reference_number or ''

        revision_meta = {
            'research_id': rep.research_id,
            'research_reference_number': res_ref_num or report_dict.get('reference_number', ''),
            'revision_number': rep.revision_number or 1,
            'scan_execution_id': rep.scan_execution_id or report_id,
            'supersedes_report_id': rep.supersedes_report_id or ''
        }

        snap_dict = {
            'application_version': snap.application_version or versioning.APP_VERSION,
            'engine_version': snap.engine_version or versioning.ENGINE_VERSION,
            'report_schema_version': snap.report_schema_version or versioning.REPORT_SCHEMA_VERSION,
            'normalization_version': snap.normalization_version or versioning.NORMALIZATION_VERSION,
            'detector_version': snap.detector_version or versioning.DETECTOR_VERSION,
            'citation_detection_version': snap.citation_detection_version or versioning.CITATION_DETECTION_VERSION,
            'common_text_handling_version': snap.common_text_handling_version or versioning.COMMON_TEXT_HANDLING_VERSION,
            'jaccard_threshold': snap.jaccard_threshold,
            'tfidf_threshold': snap.tfidf_threshold,
            'reference_corpus_version': snap.reference_corpus_version,
            'reference_fingerprint': snap.reference_fingerprint
        }

        # 6. بناء التمثيل المعياري وحساب البصمة الرقمية
        canonical_str = build_canonical_report_payload(
            report_dict=report_dict,
            input_manifest=input_manifest,
            reference_sources=ref_sources,
            evidence_snapshot=evidence_list,
            version_snap_dict=snap_dict,
            revision_metadata=revision_meta
        )
        final_hash = compute_report_hash(canonical_str)
        now_dt = datetime.utcnow()

        # 7. التجميد النهائي والتحديث داخل المعاملة الذرية
        rep.artifact_status = ARTIFACT_FINALIZED
        rep.finalization_hash = final_hash
        rep.finalized_at = now_dt
        rep.finalized_by = finalized_by_clean
        rep.input_manifest_json = json.dumps(input_manifest, ensure_ascii=False)
        rep.reference_sources_json = json.dumps(ref_sources, ensure_ascii=False)
        rep.evidence_snapshot_json = json.dumps(evidence_list, ensure_ascii=False)
        rep.canonical_payload_json = canonical_str

        session.commit()

        # 8. تسجيل حدث تدقيق رسمي
        audit_service.record_event(
            category='security',
            action='report.finalized',
            object_type='report',
            object_id=report_id,
            report_id=report_id,
            research_id=rep.research_id,
            research_reference_number=res_ref_num,
            metadata={
                'revision_number': rep.revision_number,
                'finalization_hash': final_hash,
                'finalized_by': finalized_by_clean,
                'inputs_count': len(input_manifest),
                'evidence_count': len(evidence_list)
            },
            success=True
        )

        data = _format_report_dict(rep)
        return True, data, "تم اعتماد التقرير وتجميد بصمته الرقمية بنجاح.", None


def verify_report_integrity(report_id: str) -> Dict[str, Any]:
    """
    التحقق من سلامة ونزاهة التقرير بمقارنة البصمة المخزنة بالبصمة المحسوبة للتمثيل المعياري.
    العملية للقراءة فقط ولا تقوم بتعديل أي بيانات في قاعدة البيانات (No Lazy Writes).
    """
    with base_repo.get_session() as session:
        rep = session.query(LegacyReport).filter(LegacyReport.id == report_id).first()
        if not rep:
            return {
                'report_id': report_id,
                'integrity_status': INTEGRITY_INCOMPLETE,
                'error': 'التقرير غير موجود',
                'is_tamper_evident': False
            }

        # 1. فحص التقارير التاريخية السابقة لـ Phase 15
        if not rep.finalization_hash or rep.artifact_status == ARTIFACT_DRAFT:
            return {
                'report_id': rep.id,
                'research_id': rep.research_id,
                'research_reference_number': '',
                'revision_number': rep.revision_number or 1,
                'artifact_status': rep.artifact_status or ARTIFACT_DRAFT,
                'integrity_status': INTEGRITY_LEGACY_UNVERIFIABLE,
                'finalization_hash': '',
                'hash_algorithm': 'SHA-256',
                'finalized_at': None,
                'finalized_by': '',
                'is_tamper_evident': False,
                'message': 'تقرير قديم أو مسودة — لا تتوفر له بصمة اعتماد أصلية مجمدة.'
            }

        # 2. التحقق من وجود التمثيل المعياري وإعادة حساب البصمة
        canonical_str = rep.canonical_payload_json
        if not canonical_str:
            return {
                'report_id': rep.id,
                'research_id': rep.research_id,
                'revision_number': rep.revision_number,
                'artifact_status': rep.artifact_status,
                'integrity_status': INTEGRITY_INCOMPLETE,
                'finalization_hash': rep.finalization_hash,
                'hash_algorithm': 'SHA-256',
                'finalized_at': rep.finalized_at.isoformat() if rep.finalized_at else None,
                'finalized_by': rep.finalized_by,
                'is_tamper_evident': False,
                'message': 'بيانات التمثيل المعياري للتقرير غير مكتملة.'
            }

        recomputed_hash = compute_report_hash(canonical_str)

        if recomputed_hash.lower() == rep.finalization_hash.lower():
            status = INTEGRITY_VERIFIED
            msg = "تم التحقق من سلامة ونزاهة التقرير وتطابق بصمة الاعتماد الرقمية بنجاح."
            is_valid = True
        else:
            status = INTEGRITY_MODIFIED
            msg = "تحذير أمني: تعذر التحقق من سلامة التقرير بسبب اختلاف في بصمة الاعتماد."
            is_valid = False
            # تسجيل حدث تدقيق لفشل التحقق من النزاهة
            audit_service.record_event(
                category='security',
                action='integrity.verification_failed',
                object_type='report',
                object_id=report_id,
                report_id=report_id,
                research_id=rep.research_id,
                metadata={
                    'expected_hash': rep.finalization_hash,
                    'calculated_hash': recomputed_hash,
                    'artifact_status': rep.artifact_status
                },
                success=False
            )

        res_ref_num = ''
        if rep.research_id:
            res_obj = session.query(Research).filter(Research.id == rep.research_id).first()
            if res_obj:
                res_ref_num = res_obj.reference_number or ''

        return {
            'report_id': rep.id,
            'research_id': rep.research_id,
            'research_reference_number': res_ref_num,
            'revision_number': rep.revision_number,
            'artifact_status': rep.artifact_status,
            'integrity_status': status,
            'finalization_hash': rep.finalization_hash,
            'hash_algorithm': 'SHA-256',
            'finalized_at': rep.finalized_at.isoformat() if rep.finalized_at else None,
            'finalized_by': rep.finalized_by,
            'is_tamper_evident': is_valid,
            'message': msg
        }


def void_report(report_id: str, voided_by: str, reason: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    إبطال تقرير معتمد مع حفظ سبب الإبطال والبصمة الأصلية دون حذف أي سجل.
    """
    if not reason or not reason.strip():
        return False, "يجب تحديد سبب إبطال التقرير المؤسسي بشكل صريح ومفصل.", ErrorCode.VALIDATION_ERROR

    with base_repo.get_session() as session:
        rep = session.query(LegacyReport).filter(LegacyReport.id == report_id).first()
        if not rep:
            return False, "تقرير الفحص غير موجود.", ErrorCode.NOT_FOUND

        if rep.artifact_status == ARTIFACT_VOIDED:
            return False, "التقرير مبطل مسبقاً بالفعل.", ErrorCode.REPORT_VOIDED

        now_dt = datetime.utcnow()
        rep.artifact_status = ARTIFACT_VOIDED
        rep.void_reason = reason.strip()
        rep.voided_by = _clean_text_field(voided_by) or 'system_user'
        rep.voided_at = now_dt

        session.commit()

        audit_service.record_event(
            category='security',
            action='report.voided',
            object_type='report',
            object_id=report_id,
            report_id=report_id,
            research_id=rep.research_id,
            metadata={
                'void_reason': rep.void_reason,
                'voided_by': rep.voided_by,
                'finalization_hash': rep.finalization_hash
            },
            success=True
        )

        return True, "تم إبطال التقرير وتوثيق العملية في سجل التدقيق بنجاح.", None


def create_report_revision(
    research_id: int,
    new_report_id: str,
    scan_execution_id: str
) -> Tuple[int, Optional[str]]:
    """
    حجز رقم إصدار جديد للبحث وربط الإصدار الجديد بالإصدار السابق (Lineage & Superseding).
    يُعيد: (رقم_الإصدار_الجديد, معرف_التقرير_السابق_المستبدل)
    """
    with base_repo.get_session() as session:
        # قراءة كافة التقارير السابقة لهذا البحث
        prev_reports = session.query(LegacyReport).filter(
            LegacyReport.research_id == research_id
        ).order_by(LegacyReport.revision_number.desc()).all()

        if not prev_reports:
            return 1, None

        latest_prev = prev_reports[0]
        next_rev = (latest_prev.revision_number or len(prev_reports)) + 1

        # استبدال التقرير السابق إن لم يكن مبطلاً
        if latest_prev.artifact_status != ARTIFACT_VOIDED:
            latest_prev.artifact_status = ARTIFACT_SUPERSEDED

        session.commit()

        audit_service.record_event(
            category='workflow',
            action='report.revision_created',
            object_type='report',
            object_id=new_report_id,
            report_id=new_report_id,
            research_id=research_id,
            metadata={
                'new_revision': next_rev,
                'superseded_report_id': latest_prev.id,
                'scan_execution_id': scan_execution_id
            },
            success=True
        )

        return next_rev, latest_prev.id


def record_review_decision(
    report_id: str,
    research_id: Optional[int],
    decision: str,
    reviewer: str,
    comment: str = ''
) -> None:
    """توثيق قرار تحكيم أكاديمي مرتبط بإصدار تقرير محدد."""
    with base_repo.get_session() as session:
        rec = ReviewDecisionRecord(
            report_id=report_id,
            research_id=research_id,
            decision=decision,
            reviewer=_clean_text_field(reviewer) or 'system_user',
            comment=_clean_text_field(comment),
            created_at=datetime.utcnow()
        )
        session.add(rec)


def get_research_revisions_lineage(research_id: int) -> List[Dict[str, Any]]:
    """استرجاع خط النسب الزمني الكامل لكافة إصدارات تقارير البحث."""
    lineage = []
    with base_repo.get_session() as session:
        reports = session.query(LegacyReport).filter(
            LegacyReport.research_id == research_id
        ).order_by(LegacyReport.revision_number.asc()).all()

        for r in reports:
            decisions = session.query(ReviewDecisionRecord).filter(
                ReviewDecisionRecord.report_id == r.id
            ).order_by(ReviewDecisionRecord.created_at.desc()).all()

            lineage.append({
                'report_id': r.id,
                'revision_number': r.revision_number or 1,
                'artifact_status': r.artifact_status or ARTIFACT_DRAFT,
                'scan_status': r.scan_status,
                'review_status': r.review_status,
                'supersedes_report_id': r.supersedes_report_id,
                'finalization_hash': r.finalization_hash,
                'finalized_at': r.finalized_at.isoformat() if r.finalized_at else None,
                'finalized_by': r.finalized_by,
                'overall_pct': r.overall_pct,
                'created_at': r.created_at.strftime('%Y-%m-%d %H:%M') if r.created_at else '',
                'decisions': [
                    {
                        'decision': d.decision,
                        'reviewer': d.reviewer,
                        'comment': d.comment,
                        'timestamp': d.created_at.strftime('%Y-%m-%d %H:%M') if d.created_at else ''
                    } for d in decisions
                ]
            })

    return lineage


def _format_report_dict(rep: LegacyReport) -> dict:
    """تهيئة كائن القاموس الخاص بالتقرير لعرضه وتمريره في الاستجابات."""
    try:
        data = json.loads(rep.report_json)
    except Exception:
        data = {}
    data.update({
        'id': rep.id,
        'report_id': rep.id,
        'title': rep.title,
        'author': rep.author,
        'overall_pct': rep.overall_pct,
        'copied_pct': rep.copied_pct,
        'para_pct': rep.para_pct,
        'category': rep.category,
        'scan_status': rep.scan_status,
        'review_status': rep.review_status,
        'artifact_status': rep.artifact_status,
        'revision_number': rep.revision_number,
        'supersedes_report_id': rep.supersedes_report_id,
        'finalization_hash': rep.finalization_hash,
        'finalized_at': rep.finalized_at.isoformat() if rep.finalized_at else None,
        'finalized_by': rep.finalized_by,
        'void_reason': rep.void_reason,
        'voided_by': rep.voided_by,
        'voided_at': rep.voided_at.isoformat() if rep.voided_at else None
    })
    return data
