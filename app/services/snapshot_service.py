# -*- coding: utf-8 -*-
"""
خدمة لقطات واستنساخ التقارير وإصدارات قاعدة المراجع (Report Reproducibility Service):
- تسجيل لقطة المعايير والعتبات والنسخ المستخدمة فعلياً في الفحص لحظة إنشائه.
- إدارة وتوليد نسخ وبصمات قاعدة المراجع (Reference Corpus Versioning & Fingerprint).
- توفير بيانات الاستنساخ الكاملة للواجهة وتصدير الـ HTML مع دعم التقارير التاريخية (Legacy).
"""

import json
import hashlib
import logging
from datetime import datetime
from typing import Optional, Tuple

import config
from app import versioning
from app.models.schema import Document
from app.models.snapshot_schema import ReportExecutionSnapshot, ReferenceCorpusVersion
from app.repositories.base_repo import get_session
from app.services import audit_service

logger = logging.getLogger(__name__)


def compute_corpus_fingerprint() -> Tuple[str, int]:
    """
    حساب بصمة رقمية حتمية ومستقرة عبر الهجرات لكافة الأبحاث المرجعية النشطة.
    """
    from app.services import corpus_governance_service
    return corpus_governance_service.compute_deterministic_corpus_fingerprint()


def get_current_reference_corpus_info() -> Tuple[str, str]:
    """
    استرجاع الإصدار الحالي لقاعدة المراجع وبصمتها الرقمية المعتمدة.
    """
    from app.services import corpus_governance_service
    info = corpus_governance_service.get_current_corpus_info()
    return info['corpus_version'], info['fingerprint']



def create_report_snapshot(
    report_id: str,
    research_id: Optional[int],
    research_reference_number: str,
    settings_used: dict,
    scan_started_at: Optional[datetime] = None,
    scan_completed_at: Optional[datetime] = None
) -> ReportExecutionSnapshot:
    """
    إنشاء وحفظ لقطة تشغيل ثابتة لتقرير الفحص (Immutable Report Execution Snapshot).
    تحفظ العتبات والنسخ المستخدمة فعلياً أثناء هذا الفحص فقط.
    """
    ref_corpus_ver, ref_fingerprint = get_current_reference_corpus_info()

    j_thresh = float(settings_used.get('jaccard_threshold', 0.40))
    t_thresh = float(settings_used.get('tfidf_threshold', settings_used.get('cosine_threshold', 0.40)))
    c_thresh = float(settings_used.get('cosine_threshold', t_thresh))
    shingle = int(settings_used.get('shingle_size', 5))
    max_pages = float(settings_used.get('max_allowed_pages_per_source', 5.0))
    words_page = int(settings_used.get('words_per_page', 250))

    sem_enabled = bool(settings_used.get('enable_semantic_model', False))
    sem_id = settings_used.get('semantic_model_identifier', None) if sem_enabled else None
    sem_ver = settings_used.get('semantic_model_version', None) if sem_enabled else None

    # بناء لقطة الإعدادات الآمنة (Allowlisted Config Snapshot)
    clean_config = {
        'jaccard_threshold': j_thresh,
        'tfidf_threshold': t_thresh,
        'cosine_threshold': c_thresh,
        'shingle_size': shingle,
        'max_allowed_pages_per_source': max_pages,
        'words_per_page': words_page,
        'enable_semantic_model': sem_enabled,
        'semantic_model_identifier': sem_id,
        'semantic_model_version': sem_ver,
        'enable_ocr': bool(settings_used.get('enable_ocr', True))
    }

    started = scan_started_at or datetime.utcnow()
    completed = scan_completed_at or datetime.utcnow()

    with get_session() as session:
        # حذف لقطة سابقة لهذا التقرير إذا كانت موجودة لمنع الخطأ عند إعادة الفحص
        session.query(ReportExecutionSnapshot).filter(ReportExecutionSnapshot.report_id == report_id).delete()

        snapshot = ReportExecutionSnapshot(
            report_id=report_id,
            research_id=research_id,
            research_reference_number=research_reference_number or '',
            application_version=versioning.APPLICATION_VERSION,
            engine_version=versioning.ENGINE_VERSION,
            report_schema_version=versioning.REPORT_SCHEMA_VERSION,
            normalization_version=versioning.NORMALIZATION_VERSION,
            detector_version=versioning.DETECTOR_VERSION,
            citation_detection_version=versioning.CITATION_ENGINE_VERSION,
            common_text_handling_version=versioning.COMMON_TEXT_HANDLING_VERSION,
            scan_started_at=started,
            scan_completed_at=completed,
            jaccard_threshold=j_thresh,
            tfidf_threshold=t_thresh,
            cosine_threshold=c_thresh,
            shingle_size=shingle,
            max_pages_per_source=max_pages,
            words_per_page=words_page,
            semantic_enabled=sem_enabled,
            semantic_model_identifier=sem_id,
            semantic_model_version=sem_ver,
            reference_index_version=ref_corpus_ver,
            reference_corpus_version=ref_corpus_ver,
            reference_fingerprint=ref_fingerprint,
            configuration_snapshot_json=json.dumps(clean_config, ensure_ascii=False),
            is_legacy=False,
            created_at=datetime.utcnow()
        )
        session.add(snapshot)
        session.flush()

    audit_service.record_event(
        action="report.snapshot_created",
        category="report",
        object_type="report_snapshot",
        object_id=report_id,
        report_id=report_id,
        research_id=research_id,
        research_reference_number=research_reference_number or '',
        success=True,
        metadata={
            'engine_version': versioning.ENGINE_VERSION,
            'corpus_version': ref_corpus_ver,
            'jaccard_threshold': j_thresh,
            'tfidf_threshold': t_thresh
        }
    )

    return snapshot


def get_report_snapshot(report_id: str) -> dict:
    """
    استرجاع لقطة تشغيل الفحص للتقرير.
    للتقارير القديمة (Legacy Reports) التي لا تملك لقطة مسجلة، يتم إرجاع علامة legacy صريحة دون اختلاق بيانات غير مسجلة.
    """
    with get_session() as session:
        snap = (
            session.query(ReportExecutionSnapshot)
            .filter(ReportExecutionSnapshot.report_id == report_id)
            .first()
        )

        if snap:
            try:
                cfg = json.loads(snap.configuration_snapshot_json) if snap.configuration_snapshot_json else {}
            except Exception:
                cfg = {}

            return {
                'report_id': snap.report_id,
                'research_id': snap.research_id,
                'research_reference_number': snap.research_reference_number,
                'application_version': snap.application_version,
                'engine_version': snap.engine_version,
                'report_schema_version': snap.report_schema_version,
                'normalization_version': snap.normalization_version,
                'detector_version': snap.detector_version,
                'citation_detection_version': snap.citation_detection_version,
                'common_text_handling_version': snap.common_text_handling_version,
                'scan_started_at': snap.scan_started_at.strftime('%Y-%m-%d %H:%M:%S') if snap.scan_started_at else '',
                'scan_completed_at': snap.scan_completed_at.strftime('%Y-%m-%d %H:%M:%S') if snap.scan_completed_at else '',
                'jaccard_threshold': snap.jaccard_threshold,
                'tfidf_threshold': snap.tfidf_threshold,
                'cosine_threshold': snap.cosine_threshold,
                'shingle_size': snap.shingle_size,
                'max_pages_per_source': snap.max_pages_per_source,
                'words_per_page': snap.words_per_page,
                'semantic_enabled': snap.semantic_enabled,
                'semantic_model_identifier': snap.semantic_model_identifier,
                'semantic_model_version': snap.semantic_model_version,
                'reference_index_version': snap.reference_index_version,
                'reference_corpus_version': snap.reference_corpus_version,
                'reference_fingerprint': snap.reference_fingerprint,
                'configuration_snapshot': cfg,
                'is_legacy': False
            }

        # تقرير قديم لا يملك لقطة سابقة
        return {
            'report_id': report_id,
            'is_legacy': True,
            'engine_version': 'إصدار سابق — غير مسجل تفصيلياً',
            'normalization_version': 'إصدار سابق',
            'report_schema_version': 'legacy',
            'reference_corpus_version': 'إصدار سابق',
            'semantic_enabled': False,
            'semantic_model_identifier': None,
            'configuration_snapshot': {}
        }
