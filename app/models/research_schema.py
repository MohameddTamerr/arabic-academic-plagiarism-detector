# -*- coding: utf-8 -*-
"""
نماذج قاعدة البيانات للرسائل متعددة الملفات والدفعات الأكاديمية (Research & Batch ORM Models):
- Research: كيان منطقي للرسالة/البحث (قد يضم عدة ملفات).
- ResearchFile: ملف واحد منتمٍ لرسالة (PDF, DOCX, TXT).
- ScanBatch: دفعة فحص تضم أبحاثاً مستقلة.
- ScanBatchItem: عنصر واحد داخل الدفعة.
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Float, DateTime, ForeignKey, Index, BigInteger
)
from sqlalchemy.orm import relationship

from app.models.schema import Base


class Research(Base):
    """
    كيان منطقي للرسالة أو البحث الأكاديمي.
    يمكن أن يحتوي ملفاً واحداً أو عدة ملفات (أبواب/فصول).
    """
    __tablename__ = 'research'

    id = Column(Integer, primary_key=True, autoincrement=True)
    reference_number = Column(String(50), unique=True, nullable=True, index=True) # الرقم المرجعي الرسمي الفريد
    title = Column(String(500), nullable=False, index=True)
    author = Column(String(255), default='', index=True)
    specialization = Column(String(255), default='')     # التخصص
    degree_type = Column(String(100), default='')        # الدرجة / النوع (ماجستير, دكتوراه...)
    created_by = Column(String(255), default='')
    created_at = Column(DateTime, default=datetime.utcnow)

    # ربط اختياري بدفعة فحص (Null = رفع فردي)
    batch_id = Column(String(64), ForeignKey('scan_batches.id', ondelete='SET NULL'), nullable=True, index=True)

    # ربط بتقرير الفحص المنجز (Null = لم يُفحص بعد)
    report_id = Column(String(64), nullable=True, index=True)
    scan_job_id = Column(String(64), nullable=True, index=True)

    # الحالات الصريحة للفحص والتحكيم (Phase 5 Workflow Statuses)
    scan_status = Column(String(50), default='queued', index=True)          # queued, processing, completed, failed, interrupted
    review_status = Column(String(50), default='pending_review', index=True) # pending_review, preliminary_accepted, rejected, final_accepted

    files = relationship('ResearchFile', back_populates='research',
                         cascade='all, delete-orphan', order_by='ResearchFile.file_order')
    batch = relationship('ScanBatch', back_populates='research_items')

    __table_args__ = (
        Index('idx_research_batch', 'batch_id'),
        Index('idx_research_ref_num', 'reference_number'),
        Index('idx_research_scan_status', 'scan_status'),
        Index('idx_research_review_status', 'review_status'),
    )


STORAGE_STATUS_FINALIZED = 'finalized'
STORAGE_STATUS_REGISTRY_ONLY = 'registry_only'
STORAGE_STATUS_STAGING = 'staging'


class ResearchFile(Base):
    """
    ملف واحد منتمٍ لرسالة (باب أو فصل أو ملحق).
    يحتفظ بالاسم الأصلي للعرض واسم التخزين الآمن للنظام وحالة التخزين الصريحة.
    """
    __tablename__ = 'research_files'

    id = Column(Integer, primary_key=True, autoincrement=True)
    research_id = Column(Integer, ForeignKey('research.id', ondelete='CASCADE'), nullable=False, index=True)
    original_filename = Column(String(500), nullable=False)   # اسم الملف الأصلي كما رفعه المستخدم
    stored_filename = Column(String(500), nullable=False)     # اسم مولَّد آمن للتخزين الفعلي
    file_path = Column(Text, default='')                      # المسار الكامل
    file_type = Column(String(10), default='pdf')             # pdf / docx / txt
    file_size_bytes = Column(BigInteger, default=0)
    file_order = Column(Integer, nullable=False, default=0)   # ترتيب الملف داخل الرسالة (0-indexed)
    file_hash = Column(String(64), default='', index=True)    # SHA-256 لكشف التكرار
    storage_status = Column(String(50), default='finalized', nullable=False, index=True) # finalized, registry_only, staging

    research = relationship('Research', back_populates='files')

    __table_args__ = (
        Index('idx_rf_research_order', 'research_id', 'file_order'),
        Index('idx_rf_storage_status', 'storage_status'),
    )


class ScanBatch(Base):
    """
    دفعة فحص تجمع عدة أبحاث مستقلة في عملية رفع واحدة.
    الحالة محفوظة في DB لاستعادتها بعد إغلاق المتصفح.
    """
    __tablename__ = 'scan_batches'

    id = Column(String(64), primary_key=True)               # UUID
    label = Column(String(500), default='')                 # وصف اختياري
    created_by = Column(String(255), default='')
    created_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(50), default='pending')          # pending / running / partial / completed / error
    total_items = Column(Integer, default=0)
    completed_items = Column(Integer, default=0)
    failed_items = Column(Integer, default=0)

    research_items = relationship('Research', back_populates='batch',
                                  foreign_keys='Research.batch_id')
    items = relationship('ScanBatchItem', back_populates='batch',
                         cascade='all, delete-orphan', order_by='ScanBatchItem.item_order')


class ScanBatchItem(Base):
    """
    عنصر واحد داخل دفعة الفحص — يُربط بـ Research واحد ومهمة فحص واحدة.
    """
    __tablename__ = 'scan_batch_items'

    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(String(64), ForeignKey('scan_batches.id', ondelete='CASCADE'), nullable=False, index=True)
    research_id = Column(Integer, ForeignKey('research.id', ondelete='CASCADE'), nullable=False, index=True)
    scan_job_id = Column(String(64), nullable=True)         # مرتبط بـ ScanJob الحالي
    report_id = Column(String(64), nullable=True)           # يُملأ عند الاكتمال
    item_order = Column(Integer, default=0)                 # ترتيب العنصر في الدفعة
    status = Column(String(50), default='queued')           # queued / running / completed / error / interrupted
    progress = Column(Integer, default=0)                   # 0-100
    error_message = Column(Text, default='')
    similarity_pct = Column(Float, nullable=True)           # نسبة التشابه — تُملأ عند الاكتمال
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    batch = relationship('ScanBatch', back_populates='items')
    research = relationship('Research')

    __table_args__ = (
        Index('idx_sbi_batch_research', 'batch_id', 'research_id'),
    )


class ReferenceSequence(Base):
    """
    جدول إدارة السلاسل التراكمية لتوليد الأرقام المرجعية بأمان تام تحت التزامن.
    - namespace: نوع السجل (مثال: 'research')
    - year: السنة الميلادية (مثال: 2026)
    - last_value: آخر قيمة تسلسلية تم حجزها
    """
    __tablename__ = 'reference_sequences'

    id = Column(Integer, primary_key=True, autoincrement=True)
    namespace = Column(String(50), nullable=False, default='research', index=True)
    year = Column(Integer, nullable=False, index=True)
    last_value = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('idx_ref_seq_ns_year', 'namespace', 'year', unique=True),
    )
