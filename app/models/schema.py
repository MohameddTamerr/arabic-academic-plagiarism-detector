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
    """جدول الأبحاث والوثائق المرجعية الأساسية وحوكمتها المؤسسية (Reference Document Governance & Lifecycle)."""
    __tablename__ = 'documents'

    id = Column(Integer, primary_key=True, autoincrement=True)
    reference_id = Column(String(64), unique=True, index=True)  # المعرف الثابت المستقر للمرجع (UUID v4)
    title = Column(String(500), nullable=False, index=True)
    author = Column(String(255), default='', index=True)
    year = Column(String(50), default='')
    publisher = Column(String(255), default='')
    edition = Column(String(100), default='')
    document_type = Column(String(100), default='paper')
    source_category = Column(String(100), default='academic')
    category = Column(String(100), default='عام', index=True)
    file_path = Column(Text, default='')
    original_filename = Column(String(500), default='')
    size_bytes = Column(Integer, default=0)
    file_hash = Column(String(64), unique=True, index=True)  # SHA-256 لمنع التكرار
    current_status = Column(String(50), default='active', index=True)  # active, superseded, retired, invalid
    
    # التتبع المؤسسي والنسب وسلسلة الإصدارات
    added_by = Column(String(255), default='')
    notes = Column(Text, default='')
    ownership_note = Column(Text, default='')
    supersedes_reference_id = Column(String(64), nullable=True, index=True)
    superseded_by_reference_id = Column(String(64), nullable=True, index=True)
    active_from_version = Column(String(50), default='', index=True)
    inactive_from_version = Column(String(50), nullable=True, index=True)
    
    # النزاهة والتحقق
    integrity_status = Column(String(50), default='verified', index=True)
    last_integrity_check = Column(DateTime, nullable=True)
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
    """جدول التقارير وأرشيف الفحوصات المتوافق مع المنظومة وسلسلة النزاهة المؤسسية (Report Integrity & Lineage)."""
    __tablename__ = 'reports'

    id = Column(String(64), primary_key=True)
    title = Column(String(500), nullable=False)
    author = Column(String(255), default='')
    overall_pct = Column(Float, nullable=False)
    copied_pct = Column(Float, nullable=False)
    para_pct = Column(Float, nullable=False)
    category = Column(String(100), default='عام')
    status = Column(String(50), default='محفوظ') # للتوافق القديم
    scan_status = Column(String(50), default='completed', index=True)
    review_status = Column(String(50), default='pending_review', index=True)
    file_path = Column(Text, default='')
    submitted_by = Column(String(255), default='')
    submitted_notes = Column(Text, default='')
    report_json = Column(Text, nullable=False)

    # Phase 15: الهوية المستقرة وإدارة المراجعات وسلسلة النزاهة (Revision Model & Tamper-Evidence)
    research_id = Column(Integer, nullable=True, index=True)
    thesis_id = Column(Integer, nullable=True, index=True)
    is_combined_thesis = Column(Integer, default=0, index=True)
    submitted_by_user_id = Column(Integer, nullable=True, index=True)
    scan_execution_id = Column(String(64), nullable=True, index=True)
    revision_number = Column(Integer, default=1, nullable=False)
    supersedes_report_id = Column(String(64), nullable=True, index=True)
    artifact_status = Column(String(50), default='draft', nullable=False, index=True) # draft, finalized, superseded, voided
    finalization_hash = Column(String(64), default='', index=True) # SHA-256
    finalized_at = Column(DateTime, nullable=True)
    finalized_by = Column(String(255), default='')
    void_reason = Column(Text, default='')
    voided_by = Column(String(255), default='')
    voided_at = Column(DateTime, nullable=True)

    # اللقطات المجمدة الموثوقة للمدخلات والمراجع والأدلة والتمثيل المعياري
    input_manifest_json = Column(Text, default='[]')
    reference_sources_json = Column(Text, default='[]')
    evidence_snapshot_json = Column(Text, default='[]')
    canonical_payload_json = Column(Text, default='')

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_rep_research_rev', 'research_id', 'revision_number'),
        Index('idx_rep_thesis_rev', 'thesis_id', 'revision_number'),
        Index('idx_rep_artifact_status', 'artifact_status'),
    )


class ReviewDecisionRecord(Base):
    """
    سجل تتبع قرارات التحكيم الأكاديمي المرتبطة بالإصدارات المحددة للتقارير (Review Decision Audit Trail).
    """
    __tablename__ = 'review_decision_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(String(64), nullable=False, index=True)
    research_id = Column(Integer, nullable=True, index=True)
    thesis_id = Column(Integer, nullable=True, index=True)
    report_revision = Column(Integer, default=1)
    previous_review_status = Column(String(50), default='')
    new_review_status = Column(String(50), default='')
    decision = Column(String(50), nullable=False) # pending_review, preliminary_accepted, rejected, final_accepted
    reviewer = Column(String(255), nullable=False)
    reviewer_user_id = Column(Integer, nullable=True, index=True)
    reviewer_role_snapshot = Column(String(50), default='')
    rejection_reason = Column(Text, default='')
    comment = Column(Text, default='')
    request_id = Column(String(64), default='')
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_rev_hist_report', 'report_id'),
        Index('idx_rev_hist_research', 'research_id'),
        Index('idx_rev_hist_thesis', 'thesis_id'),
    )


class User(Base):
    """جدول حسابات الموظفين ومديري النظام مع دعم أمان الجلسات والإلغاء الفوري."""
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    role = Column(String(50), default='employee')  # system_admin, reviewer, employee, etc.
    department = Column(String(255), default='')   # الإدارة / الوحدة
    phone_number = Column(String(50), default='')  # رقم الهاتف (اختياري)
    reset_allowed = Column(Integer, default=0)
    is_active = Column(Integer, default=1)         # 1 = نشط، 0 = معطل
    must_change_password = Column(Integer, default=0) # 1 = إجبار تغيير كلمة المرور عند أول تسجيل دخول
    must_enroll_recovery = Column(Integer, default=0) # 1 = إجبار إعداد استرداد الحساب
    session_version = Column(Integer, default=1)   # ختم أمان الجلسة لإلغاء الجلسات النشطة
    created_at = Column(DateTime, default=datetime.utcnow)


class AuthLockout(Base):
    """جدول استمرار حالة القفل ومحاولات الدخول الخاطئة عبر العمليات المتعددة."""
    __tablename__ = 'auth_lockouts'

    id = Column(Integer, primary_key=True, autoincrement=True)
    identifier = Column(String(255), unique=True, nullable=False, index=True)  # اسم المستخدم المطبع أو IP
    failed_count = Column(Integer, default=0)
    last_failed_at = Column(DateTime, default=datetime.utcnow)
    locked_until = Column(DateTime, nullable=True)
    lockout_count = Column(Integer, default=0)
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


class SystemSecurityState(Base):
    """جدول الحالة الأمنية للمنظومة واستكمال التهيئة الأولية (Persistent Installation Security State)."""
    __tablename__ = 'system_security_state'

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow)


class AccountRecoveryCredential(Base):
    """
    جدول اعتمادات استرداد الحسابات بدون اتصال (Offline QR/Code Account Recovery Credentials):
    - يخزن فقط مدققات التجزئة القوية (Argon2id Verifiers) للسر ولرمز PIN.
    - لا يخزن السر الخام أو رمز الاسترداد أو رقم PIN نهائياً.
    """
    __tablename__ = 'account_recovery_credentials'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    credential_public_id = Column(String(64), unique=True, nullable=False, index=True)
    secret_verifier = Column(String(255), nullable=False)
    pin_verifier = Column(String(255), nullable=False)
    version = Column(Integer, default=1)
    status = Column(String(20), default='active', index=True)  # active, revoked, superseded
    created_at = Column(DateTime, default=datetime.utcnow)
    revoked_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)
    failure_count = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)


class RecoveryTransaction(Base):
    """
    جدول معاملات الاسترداد المؤقتة ذات الاستخدام لمرة واحدة (Short-Lived Reset Authorization Tokens):
    - صلاحية محدودة (5-10 دقائق).
    - غير صالحة للاستخدام المزدوج، وتبطل فور إعادة تعيين كلمة المرور أو انتهاء الوقت.
    """
    __tablename__ = 'recovery_transactions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    credential_id = Column(Integer, ForeignKey('account_recovery_credentials.id', ondelete='CASCADE'), nullable=False)
    token_hash = Column(String(255), unique=True, nullable=False, index=True)
    state = Column(String(20), default='pending', index=True)  # pending, completed, expired, revoked
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    request_id = Column(String(64), default='')
    client_ip = Column(String(64), default='')
    created_at = Column(DateTime, default=datetime.utcnow)


class ReferenceMetadataHistory(Base):
    """
    سجل تتبع التعديلات والبيانات الوصفية للمراجع (Reference Metadata Revision History).
    يحفظ القيم السابقة والجديدة مع توثيق الفاعل وسبب التعديل.
    """
    __tablename__ = 'reference_metadata_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey('documents.id', ondelete='CASCADE'), nullable=False, index=True)
    reference_id = Column(String(64), nullable=False, index=True)
    field_name = Column(String(100), nullable=False)
    old_value = Column(Text, default='')
    new_value = Column(Text, default='')
    changed_by = Column(String(255), default='')
    reason = Column(Text, default='')
    changed_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_ref_meta_hist_refid', 'reference_id'),
        Index('idx_ref_meta_hist_docid', 'document_id'),
    )


class CorpusChangeset(Base):
    """
    سجل التغييرات المدمجة لإصدارات قاعدة المراجع (Reference Corpus Monotonic Changeset).
    يوثق كل حركة تؤثر على عضوية أو حالة المرجع في قاعدة الفحص.
    """
    __tablename__ = 'corpus_changesets'

    id = Column(Integer, primary_key=True, autoincrement=True)
    corpus_version = Column(String(50), nullable=False, index=True)  # e.g. REF-2026-000001
    event_id = Column(String(64), unique=True, nullable=False, index=True)
    change_type = Column(String(50), nullable=False)  # add, retire, supersede, reactivate, invalidate
    reference_id = Column(String(64), nullable=False, index=True)
    previous_reference_id = Column(String(64), nullable=True, index=True)
    actor = Column(String(255), default='')
    reason = Column(Text, default='')
    resulting_status = Column(String(50), default='active')
    timestamp = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_corpus_chg_ver', 'corpus_version'),
        Index('idx_corpus_chg_ref', 'reference_id'),
    )


class IndexStateRecord(Base):
    """
    سجل متابعة حالة فهرس الاسترجاع ومطابقته لإصدار قاعدة المراجع (Index State & Lifecycle Registry).
    الحالات المعتمدة: current, stale, building, failed
    """
    __tablename__ = 'index_state_records'

    id = Column(Integer, primary_key=True, autoincrement=True)
    index_corpus_version = Column(String(50), default='', index=True)
    index_fingerprint = Column(String(64), default='')
    state = Column(String(50), default='stale', nullable=False, index=True)  # current, stale, building, failed
    built_at = Column(DateTime, nullable=True)
    built_by = Column(String(255), default='system')
    total_segments = Column(Integer, default=0)
    error_message = Column(Text, default='')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class JobRecord(Base):
    """
    سجل مهام التشغيل الخلفية وإدارة الطابور والتزامن المحصن (Persistent Background Job Record & Lifecycle).
    الحالات المعتمدة: queued, running, completed, failed, cancel_requested, cancelled, interrupted
    أنواع المهام: scan, batch_scan, thesis_scan, reference_index_rebuild, integrity_check, backup, report_export
    """
    __tablename__ = 'job_records'

    id = Column(String(64), primary_key=True)                 # job-uuid
    job_type = Column(String(50), nullable=False, index=True) # scan, batch_scan, thesis_scan, reference_index_rebuild, etc.
    status = Column(String(50), default='queued', nullable=False, index=True) # queued, running, completed, failed, cancel_requested, cancelled, interrupted
    priority = Column(Integer, default=0, nullable=False, index=True) # أولوية التشغيل (الأعلى أولاً)

    # التوقيت والجدولة
    queued_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    heartbeat_at = Column(DateTime, nullable=True, index=True)
    retry_at = Column(DateTime, nullable=True, index=True)

    # ملكية المهمة وعقد العملية
    requested_by = Column(String(255), default='', index=True)
    worker_pid = Column(Integer, nullable=True)
    lease_token = Column(String(64), nullable=True)

    # التقدم والمراحل والإلغاء التعاوني
    progress = Column(Integer, default=0)
    stage = Column(String(255), default='')
    cancel_requested = Column(Integer, default=0)             # 0 = لا، 1 = نعم

    # المحاولات وإعادة التشغيل المنضبط
    attempt_count = Column(Integer, default=0, nullable=False)
    max_attempts = Column(Integer, default=3, nullable=False)
    error_code = Column(String(100), default='')
    safe_error_message = Column(Text, default='')

    # العلاقات مع الكيانات الأكاديمية والمؤسسية
    research_id = Column(Integer, nullable=True, index=True)
    batch_id = Column(String(64), nullable=True, index=True)
    batch_item_id = Column(Integer, nullable=True)
    report_id = Column(String(64), nullable=True, index=True)
    scan_execution_id = Column(String(64), nullable=True, index=True)
    target_corpus_version = Column(String(50), nullable=True, index=True)

    # الحمولات والنتائج
    payload_json = Column(Text, default='{}')
    result_json = Column(Text, default='{}')
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_job_dequeue', 'status', 'retry_at', 'priority', 'queued_at'),
        Index('idx_job_heartbeat', 'status', 'heartbeat_at'),
        Index('idx_job_dedup_index', 'job_type', 'target_corpus_version', 'status'),
        Index('idx_job_scan_exec', 'scan_execution_id'),
        Index('idx_job_research', 'research_id'),
        Index('idx_job_batch', 'batch_id'),
    )

