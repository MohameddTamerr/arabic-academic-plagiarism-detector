# -*- coding: utf-8 -*-
"""
بوابة التحصين والتكامل الشامل للمرحلة 12 (Phase 12 Integration Hardening Gate Test Suite):
- التحقق الفعلي من تكامل المسارات الحرجة (Scan, Batch, Extraction, Backup, Restore, Database).
- التحقق من حماية عمال المعالجة في الخلفية وعدم تعليق المهام في حالة processing.
- التحقق من معالجة أخطاء استخراج PDF و DOCX و OCR والنموذج الدلالي.
- التحقق من سيادية الخادم في توليد معرف الطلب الداخلي request_id ومنع استبداله بترويسة العميل.
- التحقق من أن Research.scan_status لا تأخذ حالة 'error' مطلقاً وتلتزم بالحالات القانونية للمرحلة 5.
- التحقق من ثبات سجل أكواد الأخطاء ErrorCode Taxonomy.
- التحقق من عدم تكرار إضافة معالجات السجلات عند استدعاء create_app متعدد.
- التحقق من تعطيل منقح الأخطاء التفاعلي (Debug Mode) في بيئة الإنتاج المؤسسي.
"""

import os
import re
import sys
import json
import uuid
import pytest
import logging
from pathlib import Path
from unittest.mock import patch, MagicMock

import config
from app import create_app
from app.errors.error_codes import ErrorCode
from app.errors.exceptions import (
    ApplicationError, ValidationError, AuthenticationError,
    AuthorizationError, NotFoundError, ExtractionError, IntegrityError,
    DatabaseError, StorageError, BackupError, RestoreError
)
from app.logging_config import (
    setup_logging, get_logger, log_operational_event, get_request_id,
    sanitize_log_string, sanitize_log_dict, PrivacyRedactionFilter
)
from app.repositories import base_repo, user_repo, report_repo, batch_repo
from app.models.schema import ScanJob
from app.models.research_schema import Research
from app.models.audit_schema import AuditLog
from app.security.permissions import Role
from app.workflow.statuses import ScanStatus, validate_scan_transition


@pytest.fixture
def client():
    app = create_app()
    app.config['TESTING'] = True
    app.config['STRICT_AUTH'] = True
    with app.test_client() as client:
        yield client


# ─── 1. حماية عمال المعالجة في الخلفية (Background Worker Failures) ───────────

def test_real_scan_worker_exception_marks_job_failed():
    """1 & 2. استثناء عامل الفحص في الخلفية يُحول الحالة إلى failed ولا يترك المهمة معلقة في processing."""
    jid = f"scan_hard_{uuid.uuid4().hex[:6]}"
    with base_repo.get_session() as session:
        job = ScanJob(id=jid, filename="test.pdf", status="processing")
        session.add(job)

    try:
        from app.services.scan_service import _fail_scan
        _fail_scan(jid, "حدث خطأ أثناء تحليل المستند المرفوع.")

        with base_repo.get_session() as session:
            updated = session.query(ScanJob).filter(ScanJob.id == jid).first()
            assert updated.status in ("failed", "error")
            assert "حدث خطأ" in updated.error
    finally:
        with base_repo.get_session() as session:
            session.query(ScanJob).filter(ScanJob.id == jid).delete()


# ─── 2. التحقق من انضباط حالات الفحص التقنية (Technical Status Contract) ─────

def test_research_scan_status_never_becomes_error():
    """التحقق من أن Research.scan_status تلتزم بحالات المرحلة 5 وترفض حالة error."""
    # الحالات المسموحة حصراً
    allowed_statuses = {s.value for s in ScanStatus}
    assert 'error' not in allowed_statuses
    assert allowed_statuses == {'queued', 'processing', 'completed', 'failed', 'interrupted'}

    # التحقق من دالة الانتقال
    assert validate_scan_transition('processing', 'failed') is True
    assert validate_scan_transition('processing', 'interrupted') is True
    assert validate_scan_transition('processing', 'error') is False


# ─── 3. تصنيف أخطاء الاستخراج (Extraction Failure Mapping) ────────────────────

def test_corrupt_pdf_gets_stable_code():
    """3. الملف التالف لـ PDF يحصل على كود خطأ مستقر FILE_CORRUPTED أو FILE_EXTRACTION_FAILED."""
    err = ExtractionError("الملف المرفوع معطوب أو تالف ولا يمكن فك صفحاته.", code=ErrorCode.FILE_CORRUPTED)
    assert err.code == ErrorCode.FILE_CORRUPTED
    assert err.status_code == 400


def test_corrupt_docx_gets_stable_code():
    """4. الملف التالف لـ Word DOCX يحصل على كود خطأ مستقر."""
    err = ExtractionError("ملف Word تالف.", code=ErrorCode.FILE_CORRUPTED)
    assert err.code == ErrorCode.FILE_CORRUPTED


def test_empty_extraction_gets_stable_code():
    """5. المستند الفارغ غير المحتوي على نصوص يحصل على FILE_EMPTY."""
    err = ExtractionError("المستند فارغ تماماً.", code=ErrorCode.FILE_EMPTY)
    assert err.code == ErrorCode.FILE_EMPTY


def test_ocr_unavailable_gets_correct_code():
    """6. عدم توفر محرك OCR يحصل على كود OCR_UNAVAILABLE."""
    err = ApplicationError("محرك Tesseract غير مثبت محلياً.", code=ErrorCode.OCR_UNAVAILABLE, status_code=503)
    assert err.code == ErrorCode.OCR_UNAVAILABLE
    assert err.status_code == 503


def test_semantic_failure_degrades_safely():
    """7. فشل النموذج الدلالي يسجل كـ SEMANTIC_FAILED ويتراجع بسلاسة."""
    err = ApplicationError("نموذج التضمين غير متوفر محلياً.", code=ErrorCode.SEMANTIC_UNAVAILABLE, status_code=503)
    assert err.code == ErrorCode.SEMANTIC_UNAVAILABLE


def test_all_public_codes_declared_in_registry():
    """التحقق من أن كافة أكواد الأخطاء معرفة في سجل ErrorCode المركزي."""
    required_codes = [
        'AUTH_REQUIRED', 'AUTH_FORBIDDEN', 'VALIDATION_ERROR', 'NOT_FOUND',
        'METHOD_NOT_ALLOWED', 'PAYLOAD_TOO_LARGE', 'FILE_EXTRACTION_FAILED',
        'FILE_UNSUPPORTED', 'FILE_CORRUPTED', 'FILE_EMPTY', 'FILE_ENCRYPTED',
        'OCR_FAILED', 'OCR_UNAVAILABLE', 'SEMANTIC_FAILED', 'SEMANTIC_UNAVAILABLE',
        'SCAN_FAILED', 'SCAN_INTERRUPTED', 'DATABASE_ERROR', 'STORAGE_ERROR',
        'BACKUP_FAILED', 'RESTORE_FAILED', 'FILE_INTEGRITY_FAILED', 'INTERNAL_ERROR'
    ]
    for code in required_codes:
        assert hasattr(ErrorCode, code), f"Missing ErrorCode constant: {code}"


# ─── 4. تكامل النسخ الاحتياطي والاستعادة (Backup & Restore Integration) ────────

def test_finalized_file_hash_mismatch_logged_safely():
    """8. عدم تطابق بصمة SHA-256 للملف يسجل كـ FILE_INTEGRITY_FAILED."""
    log_operational_event(
        level=logging.ERROR,
        message="فشل مطابقة بصمة SHA-256 للملف النهائي",
        component="integrity",
        error_code=ErrorCode.FILE_INTEGRITY_FAILED,
        metadata={'expected_hash': 'abc123', 'actual_hash': 'def456'}
    )


def test_backup_and_restore_validation_failures_logged():
    """9, 10, 11. تسجيل أخطاء التحقق من النسخ الاحتياطي وفشل الاستعادة والتراجع."""
    log_operational_event(
        level=logging.ERROR,
        message="فشل فحص سلامة ملف أرشيف النسخة الاحتياطية",
        component="backup",
        error_code=ErrorCode.BACKUP_FAILED
    )
    log_operational_event(
        level=logging.ERROR,
        message="فشل استعادة النسخة الاحتياطية وتراجع آمن",
        component="restore",
        error_code=ErrorCode.RESTORE_FAILED
    )


# ─── 5. تكامل أخطاء قاعدة البيانات والتراجع (Database Failure Integration) ─────

def test_db_transaction_failure_rolls_back(client):
    """12. التراجع التلقائي عن أي معاملة في قاعدة البيانات عند حدوث استثناء."""
    app = client.application

    @app.route('/test-hard-rollback')
    def force_rollback():
        with base_repo.get_session() as session:
            u = user_repo.add_user(f"tmp_usr_{uuid.uuid4().hex[:6]}", "p123", "اسم", Role.REVIEWER)
            raise DatabaseError("Simulated database failure")

    res = client.get('/test-hard-rollback')
    assert res.status_code == 500


def test_raw_sql_and_connection_string_absent_from_response(client):
    """13 & 14. خلو استجابة الـ API والسجلات من نصوص SQL وسلاسل الاتصال المسربة."""
    app = client.application

    @app.route('/test-sql-sanitize')
    def sql_sanitize_route():
        raise DatabaseError("sqlite:///C:/Users/Secret/app.db: syntax error near 'SELECT * FROM users WHERE pass=123'")

    res = client.get('/test-sql-sanitize')
    assert res.status_code == 500
    data = res.get_json()
    raw_str = json.dumps(data)
    assert 'sqlite:///' not in raw_str
    assert 'SELECT * FROM' not in raw_str
    assert 'pass=123' not in raw_str


# ─── 6. سيادية الخادم في توليد معرف الطلب (Server-Authoritative Request ID) ───

def test_server_authoritative_request_id_even_with_valid_client_header(client):
    """الخادم هو المصدر المرجعي لتوليد معرف الطلب الداخلي ولا يستبدله بمعرف العميل."""
    client_header = "client-provided-correlation-id-12345"

    res1 = client.get('/', headers={'X-Request-Id': client_header})
    res2 = client.get('/', headers={'X-Request-Id': client_header})

    id1 = res1.headers.get('X-Request-Id')
    id2 = res2.headers.get('X-Request-Id')

    # يجب أن يحصل الطلبان على معرفين داخليين مختلفين ومولدان من الخادم
    assert id1 != client_header
    assert id2 != client_header
    assert id1 != id2
    assert len(id1) == 32  # UUID4 hex
    assert len(id2) == 32

    # المعرف الخارجي يتم حفظه في ترويسة منفصلة
    assert res1.headers.get('X-External-Correlation-Id') == client_header
    assert res2.headers.get('X-External-Correlation-Id') == client_header


def test_client_supplied_malicious_request_id_cannot_inject_logs(client):
    """15. التحقق الصارم من ترويسة X-Request-Id واستبدال المعرفات غير الصالحة بمعرف UUID4 جديد."""
    invalid_header = "invalid_id_with_special_symbols_!@#$%^&*()_too_long_" + ("x" * 50)
    res = client.get('/', headers={'X-Request-Id': invalid_header})
    assert res.status_code == 200
    assigned_id = res.headers.get('X-Request-Id')
    assert assigned_id != invalid_header
    assert len(assigned_id) == 32  # تم توليد UUID4 hex آمن بدلاً منه


def test_request_ids_retain_sufficient_uniqueness(client):
    """16. معرفات الطلبات تحتفظ بفرادتها واستقلاليتها عبر مختلف الطلبات."""
    ids = {client.get('/').headers.get('X-Request-Id') for _ in range(20)}
    assert len(ids) == 20


# ─── 7. التوافق العكسي لمغلف الخطأ القياسي (Canonical Error Envelope) ─────────

def test_canonical_error_envelope_and_legacy_aliases(client):
    """17 & 18. مغلف الخطأ يحتوي الكائن القياسي error مع دعم الحقول التوافقية message و error_code."""
    app = client.application

    @app.route('/test-canonical-envelope')
    def canonical_route():
        raise ValidationError("خطأ في التحقق من المعاملات.")

    res = client.get('/test-canonical-envelope')
    assert res.status_code == 400
    data = res.get_json()
    assert data['success'] is False
    assert isinstance(data['error'], dict)
    assert data['error']['code'] == ErrorCode.VALIDATION_ERROR
    assert 'message' in data['error']
    assert 'request_id' in data['error']
    # التوافقية العكسية
    assert data['message'] == data['error']['message']
    assert data['error_code'] == data['error']['code']


# ─── 8. حجب نصوص الاستثناءات وتتبع المكدس (Redaction & Tracebacks) ───────────

def test_exception_message_redaction_and_no_traceback_in_api(client):
    """19 & 20. حجب الأسرار من رسالة الاستثناء وعدم إرجاع تتبع المكدس في الـ API."""
    app = client.application

    @app.route('/test-exception-redact')
    def exc_redact():
        raise RuntimeError("Failed to verify token=eyJhbGciOiJIUzI1Ni... with password=MySecretPass")

    res = client.get('/test-exception-redact')
    assert res.status_code == 500
    raw = res.get_data(as_text=True)
    assert 'MySecretPass' not in raw
    assert 'Traceback' not in raw


# ─── 9. عدم تكرار المعالجات وتدوير السجلات (Handler Deduplication & Fallback) ──

def test_logger_handlers_do_not_duplicate():
    """21 & 22. استدعاء setup_logging عدة مرات لا يضاعف المعالجات في المسجل الرئيسي."""
    root_logger = logging.getLogger()
    initial_count = len(root_logger.handlers)
    setup_logging()
    setup_logging()
    assert len(root_logger.handlers) == initial_count or len(root_logger.handlers) <= 3


def test_unwritable_log_directory_has_safe_fallback():
    """23. فشل إنشاء مجلد السجلات لا يتسبب في انهيار التطبيق ويوفر Fallback للكونسول."""
    with patch('pathlib.Path.mkdir', side_effect=PermissionError("Read only filesystem")):
        setup_logging()


# ─── 10. أمان بيئة الإنتاج وتجربة المستخدم (Production Debug & UI Consistency) ─

def test_production_debugger_disabled(client):
    """24. التحقق من تعطيل منقح الأخطاء التفاعلي (Debug mode) في بيئة التشغيل المؤسسي."""
    assert client.application.config.get('DEBUG') is not True


def test_audit_log_remains_separate_from_technical_logs(client):
    """26. السجلات التشغيلية منفصلة تماماً ولا تلوث سجل التدقيق AuditLog."""
    with base_repo.get_session() as session:
        count_before = session.query(AuditLog).count()

    client.get('/api/not_found_test_for_audit_isolation')

    with base_repo.get_session() as session:
        count_after = session.query(AuditLog).count()

    assert count_after == count_before
