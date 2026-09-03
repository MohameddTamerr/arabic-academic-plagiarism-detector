# -*- coding: utf-8 -*-
"""
نماذج قاعدة البيانات المتطورة (SQLAlchemy ORM Models):
- تخزين المراجع على مستوى الصفحات والفقرات (Page & Segment Attribution).
- دعم منع التكرار عبر البصمة الرقمية (SHA-256 File Hash).
- جاهزة للنقل السلس مستقبلاً إلى PostgreSQL دون تغيير كود الاستعلامات.
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Float, DateTime, ForeignKey, Index
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Document(Base):
    """جدول الأبحاث والوثائق المرجعية الأساسية."""
    __tablename__ = 'documents'

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False, index=True)
    author = Column(String(255), default='', index=True)
    year = Column(String(50), default='')
    category = Column(String(100), default='عام', index=True)
    file_path = Column(Text, default='')
    file_hash = Column(String(64), unique=True, index=True)  # SHA-256 لمنع التكرار
    created_at = Column(DateTime, default=datetime.utcnow)

    pages = relationship("DocumentPage", back_populates="document", cascade="all, delete-orphan")
    segments = relationship("DocumentSegment", back_populates="document", cascade="all, delete-orphan")


class DocumentPage(Base):
    """جدول نصوص صفحات المرجع المستقلة لحفظ أرقام الصفحات بدقة."""
    __tablename__ = 'document_pages'

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey('documents.id', ondelete='CASCADE'), nullable=False, index=True)
    page_number = Column(Integer, nullable=True)  # رقم الصفحة الفعلي من PDF أو None إذا غير متاح
    raw_text = Column(Text, nullable=False)
    normalized_text = Column(Text, default='')

    document = relationship("Document", back_populates="pages")

    __table_args__ = (
        Index('idx_doc_page_lookup', 'document_id', 'page_number'),
    )


class DocumentSegment(Base):
    """جدول فقرات وجمل المرجع لإجراء المطابقة الدقيقة واسترجاع المرشحين."""
    __tablename__ = 'document_segments'

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey('documents.id', ondelete='CASCADE'), nullable=False, index=True)
    page_number = Column(Integer, nullable=True)
    segment_number = Column(Integer, nullable=False)
    raw_text = Column(Text, nullable=False)
    normalized_text = Column(Text, default='')
    word_count = Column(Integer, default=0)

    document = relationship("Document", back_populates="segments")

    __table_args__ = (
        Index('idx_doc_seg_lookup', 'document_id', 'segment_number'),
    )


class ScanJob(Base):
    """جدول مهام الفحص في الخلفية لمتابعة التقدم والنتائج."""
    __tablename__ = 'scan_jobs'

    id = Column(String(64), primary_key=True)
    filename = Column(String(500), default='')
    title = Column(String(500), default='')
    author = Column(String(255), default='')
    status = Column(String(50), default='queued')  # queued, running, completed, error
    progress = Column(Integer, default=0)
    stage = Column(String(255), default='')
    result_json = Column(Text, default='')
    error = Column(Text, default='')
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


class Match(Base):
    """جدول تسجيل كل تطابق مكتشف مع عزو الصفحة المصدرية الحقيقية."""
    __tablename__ = 'matches'

    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_id = Column(String(64), index=True, nullable=False)
    source_document_id = Column(Integer, ForeignKey('documents.id', ondelete='SET NULL'), nullable=True)
    source_page = Column(Integer, nullable=True)
    submitted_segment = Column(Text, nullable=False)
    source_segment = Column(Text, nullable=False)
    match_type = Column(String(50), default='exact')  # exact, paraphrase, semantic, cited
    similarity_score = Column(Float, default=0.0)


# الجداول الحالية لضمان التوافق التام (Backward Compatibility)
class LegacyReport(Base):
    """جدول التقارير وأرشيف الفحوصات المتوافق مع المنظومة السابقة."""
    __tablename__ = 'reports'

    id = Column(String(64), primary_key=True)
    title = Column(String(500), nullable=False)
    author = Column(String(255), default='')
    overall_pct = Column(Float, nullable=False)
    copied_pct = Column(Float, nullable=False)
    para_pct = Column(Float, nullable=False)
    category = Column(String(100), default='عام')
    status = Column(String(50), default='محفوظ')
    file_path = Column(Text, default='')
    submitted_by = Column(String(255), default='')
    submitted_notes = Column(Text, default='')
    report_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class User(Base):
    """جدول حسابات الموظفين ومديري النظام."""
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    role = Column(String(50), default='employee')  # admin, employee
    reset_allowed = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class PasswordResetRequest(Base):
    """جدول طلبات استعادة وتعيين كلمات المرور."""
    __tablename__ = 'password_reset_requests'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    username = Column(String(100), nullable=False)
    full_name = Column(String(255), nullable=False)
    new_password_hash = Column(String(255), default='')
    status = Column(String(50), default='pending')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
