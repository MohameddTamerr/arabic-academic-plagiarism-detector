# -*- coding: utf-8 -*-
"""
نماذج استنساخ التقارير ونسخ قاعدة المراجع (Report Reproducibility & Corpus Versioning Models):
- ReportExecutionSnapshot: لقطة تشغيل ثابتة لتقرير الفحص تحفظ العتبات والنسخ المستخدمة فعلياً لحظة الفحص.
- ReferenceCorpusVersion: تتبع نسخ وبصمات قاعدة الأبحاث المرجعية لحفظ تاريخ تغير المراجع.
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean, DateTime, Index
)
from app.models.schema import Base


class ReportExecutionSnapshot(Base):
    """
    لقطة تشغيل ومعايير فحص التقرير (Immutable Report Execution Snapshot).
    تحفظ كافة المتغيرات والنسخ والعتبات المستخدمة في الفحص لضمان استنساخ النتائج ومراجعتها تاريخياً.
    """
    __tablename__ = 'report_snapshots'

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(String(64), unique=True, nullable=False, index=True)
    research_id = Column(Integer, nullable=True, index=True)
    research_reference_number = Column(String(50), default='', index=True)

    # النسخ المعتمدة للمكونات
    application_version = Column(String(50), nullable=False)
    engine_version = Column(String(50), nullable=False)
    report_schema_version = Column(String(50), nullable=False)
    normalization_version = Column(String(50), nullable=False)
    detector_version = Column(String(50), nullable=False)
    citation_detection_version = Column(String(50), nullable=False)
    common_text_handling_version = Column(String(50), nullable=False)

    # التوقيت
    scan_started_at = Column(DateTime, nullable=True)
    scan_completed_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # العتبات الفعلية المستخدمة أثناء هذا الفحص
    jaccard_threshold = Column(Float, nullable=False)
    tfidf_threshold = Column(Float, nullable=False)
    cosine_threshold = Column(Float, nullable=True)
    shingle_size = Column(Integer, default=5)
    max_pages_per_source = Column(Float, default=5.0)
    words_per_page = Column(Integer, default=250)

    # النموذج الدلالي
    semantic_enabled = Column(Boolean, default=False)
    semantic_model_identifier = Column(String(100), nullable=True)
    semantic_model_version = Column(String(100), nullable=True)

    # قاعدة المراجع والفهرس المستخدم
    reference_index_version = Column(String(50), default='')
    reference_corpus_version = Column(String(50), default='')
    reference_fingerprint = Column(String(64), default='')  # SHA-256 over active doc set

    # لقطة الإعدادات الكاملة غير الحساسة
    configuration_snapshot_json = Column(Text, default='{}')

    # علامة التقارير القديمة
    is_legacy = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_snap_report_id', 'report_id'),
        Index('idx_snap_research_ref', 'research_reference_number'),
    )


class ReferenceCorpusVersion(Base):
    """
    سجل تتبع نسخ وبصمات قاعدة المراجع الأساسية (Reference Corpus Version History).
    """
    __tablename__ = 'reference_corpus_versions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    version_identifier = Column(String(50), unique=True, nullable=False, index=True)  # e.g., REF-2026-000001
    fingerprint = Column(String(64), nullable=False)  # SHA-256
    document_count = Column(Integer, default=0)
    change_reason = Column(String(255), default='initial')
    created_at = Column(DateTime, default=datetime.utcnow)
