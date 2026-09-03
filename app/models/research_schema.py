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

    files = relationship('ResearchFile', back_populates='research',
                         cascade='all, delete-orphan', order_by='ResearchFile.file_order')
    batch = relationship('ScanBatch', back_populates='research_items')

    __table_args__ = (
        Index('idx_research_batch', 'batch_id'),
    )


class ResearchFile(Base):
    """
    ملف واحد منتمٍ لرسالة (باب أو فصل أو ملحق).
    يحتفظ بالاسم الأصلي للعرض واسم التخزين الآمن للنظام.
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

    research = relationship('Research', back_populates='files')

    __table_args__ = (
        Index('idx_rf_research_order', 'research_id', 'file_order'),
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
