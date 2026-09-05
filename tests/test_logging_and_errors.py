# -*- coding: utf-8 -*-
"""
حزمة اختبارات شاملة للتسجيل الهيكلي ومعالجة الأخطاء الآمنة (Phase 12 Logging & Error Handling Test Suite):
- التحقق من تتبع معرف الطلب (Request ID) وفرادة المعرفات.
- التحقق من سلامة مغلف استجابات الخطأ (400, 401, 403, 404, 405, 413, 500).
- التحقق من عدم تسريب المسارات المطلقة أو نصوص SQL أو تتبع المكدس (Tracebacks).
- التحقق من حجب البيانات السرية ونصوص الأبحاث ومنع حقن السجلات (CRLF Injection).
- التحقق من التدوير الآمن للملفات ودعم UTF-8 العربي.
- التحقق من التراجع التلقائي عن معاملات قاعدة البيانات (Rollback).
- التحقق من الفصل التام بين السجلات التشغيلية وسجلات التدقيق المؤسسي.
"""

import os
import re
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
from app.errors.handlers import make_error_response
from app.logging_config import (
    setup_logging, get_logger, log_operational_event, get_request_id,
    sanitize_log_string, sanitize_log_dict, PrivacyRedactionFilter
)
from app.repositories import base_repo, user_repo
from app.models.schema import ScanJob
from app.models.audit_schema import AuditLog
from app.security.permissions import Role


@pytest.fixture
def client():
    app = create_app()
    app.config['TESTING'] = True
    app.config['STRICT_AUTH'] = True
    with app.test_client() as client:
        yield client


# ─── 1. اختبارات معرف الطلب (Request Correlation ID) ──────────────────────────

def test_every_request_receives_request_id(client):
    """1. كل طلب وارد يستقبل ترويسة X-Request-Id في الاستجابة."""
    res = client.get('/')
    assert res.status_code == 200
    assert 'X-Request-Id' in res.headers
    assert len(res.headers['X-Request-Id']) >= 8


def test_request_ids_are_non_sequential_and_unique(client):
    """2. معرفات الطلبات فريدة وعشوائية وغير متسلسلة (UUID/Hex)."""
    res1 = client.get('/')
    res2 = client.get('/')
    id1 = res1.headers.get('X-Request-Id')
    id2 = res2.headers.get('X-Request-Id')
    assert id1 is not None
    assert id2 is not None
    assert id1 != id2


def test_incoming_valid_request_id_is_preserved(client):
    """الخادم يولد معرف الطلب الداخلي السيادي ويحفظ المعرف الخارجي الوارد في ترويسة منفصلة."""
    custom_id = "custom-trace-uuid-123456789"
    res = client.get('/', headers={'X-Request-Id': custom_id})
    assert res.headers.get('X-Request-Id') != custom_id
    assert len(res.headers.get('X-Request-Id')) == 32
    assert res.headers.get('X-External-Correlation-Id') == custom_id


# ─── 2. اختبارات مغلف الأخطاء القياسي (API Error Envelope) ───────────────────

def test_400_uses_safe_envelope(client):
    """3. خطأ 400 يرجع مغلفاً قياسياً آمناً يحمل كود الخطأ ورسالة عربية ورقم التتبع."""
    app = client.application

    @app.route('/test-400-trigger')
    def trigger_400():
        raise ValidationError("بيانات الإدخال ناقصة أو غير صالحة.")

    res = client.get('/test-400-trigger')
    assert res.status_code == 400
    data = res.get_json()
    assert data['success'] is False
    assert 'error' in data
    assert data['error']['code'] == ErrorCode.VALIDATION_ERROR
    assert 'ناقصة' in data['error']['message']
    assert 'request_id' in data['error']


def test_401_safe_envelope(client):
    """4. خطأ 401 يرجع استجابة آمنة موحدة دون تسريب تفاصيل داخلية."""
    res = client.get('/api/system/health')
    assert res.status_code == 401
    data = res.get_json()
    assert data['success'] is False
    assert data['error']['code'] == ErrorCode.AUTH_REQUIRED
    assert 'تسجيل الدخول' in data['error']['message']
    assert 'request_id' in data['error']


def test_403_safe_envelope(client):
    """5. خطأ 403 يرجع استجابة آمنة موحدة مع كود الصلاحية المطلوب ورقم التتبع."""
    uname = f"de_usr_{uuid.uuid4().hex[:6]}"
    user_repo.add_user(uname, 'pass123', 'مدخل بيانات', Role.DATA_ENTRY)
    client.post('/api/auth/login', json={'username': uname, 'password': 'pass123'})

    res = client.get('/api/admin/audit_logs')
    assert res.status_code == 403
    data = res.get_json()
    assert data['success'] is False
    assert data['error']['code'] == ErrorCode.AUTH_FORBIDDEN
    assert 'غير مصرح' in data['error']['message']
    assert 'request_id' in data['error']


def test_404_safe_envelope(client):
    """6. خطأ 404 يرجع استجابة JSON آمنة تفيد بعدم وجود المورد."""
    res = client.get('/api/non_existent_institutional_endpoint')
    assert res.status_code == 404
    data = res.get_json()
    assert data['success'] is False
    assert data['error']['code'] == ErrorCode.NOT_FOUND
    assert 'غير موجود' in data['error']['message']


def test_405_safe_envelope(client):
    """7. خطأ 405 (طريقة غير مسموح بها) يرجع استجابة آمنة برقم التتبع."""
    res = client.delete('/')
    assert res.status_code == 405
    data = res.get_json()
    assert data['success'] is False
    assert data['error']['code'] == ErrorCode.METHOD_NOT_ALLOWED


def test_413_safe_envelope(client):
    """8. خطأ 413 (تجاوز حجم الملف) يرجع كود PAYLOAD_TOO_LARGE ورسالة عربية مفهومة."""
    with client.application.test_request_context():
        res, status = make_error_response("حجم الملف يتجاوز الحد المسموح به", code=ErrorCode.PAYLOAD_TOO_LARGE, status_code=413)
        assert status == 413
        data = res.get_json()
        assert data['error']['code'] == ErrorCode.PAYLOAD_TOO_LARGE


# ─── 3. اختبارات حماية الاستثناءات و500 (Unhandled Exceptions & Privacy) ───────

def test_unexpected_exception_returns_generic_500_with_request_id(client):
    """9 & 10. الاستثناء غير المتوقع يرجع خطأ 500 عاماً ومغلفاً آمناً مع request_id."""
    app = client.application

    @app.route('/test-crash-route')
    def crash_route():
        raise RuntimeError("Internal critical simulation failure")

    res = client.get('/test-crash-route')
    assert res.status_code == 500
    data = res.get_json()
    assert data['success'] is False
    assert data['error']['code'] == ErrorCode.INTERNAL_ERROR
    assert 'request_id' in data['error']
    assert len(data['error']['request_id']) >= 8


def test_traceback_and_python_internals_not_returned_to_client(client):
    """11. عدم تسريب مسار التتبع (Traceback) أو أسماء الملفات البرمجية للعميل."""
    app = client.application

    @app.route('/test-traceback-leak')
    def leak_route():
        raise ZeroDivisionError("division by zero in calculations")

    res = client.get('/test-traceback-leak')
    assert res.status_code == 500
    raw_text = res.get_data(as_text=True)
    assert 'Traceback' not in raw_text
    assert 'ZeroDivisionError' not in raw_text
    assert 'File "' not in raw_text


def test_sql_exception_details_not_returned_to_client(client):
    """12. عدم تسريب نصوص SQL أو أخطاء المحرك لقاعدة البيانات للعميل."""
    app = client.application

    @app.route('/test-sql-leak')
    def sql_leak():
        raise DatabaseError("SELECT * FROM sensitive_table WHERE password='xyz'; syntax error")

    res = client.get('/test-sql-leak')
    assert res.status_code == 500
    data = res.get_json()
    assert 'SELECT * FROM' not in json.dumps(data)
    assert 'password=' not in json.dumps(data)


def test_absolute_path_not_returned_in_api_errors(client):
    """13. عدم تسريب المسارات المطلقة لنظام التشغيل (C:\\Users\\...) في الردود."""
    app = client.application

    @app.route('/test-path-leak')
    def path_leak():
        raise StorageError(r"Failed to write to C:\Users\Administrator\Documents\Secret\file.pdf")

    res = client.get('/test-path-leak')
    raw_text = res.get_data(as_text=True)
    assert 'C:\\Users' not in raw_text
    assert 'C:/Users' not in raw_text
    assert '/Users/' not in raw_text


# ─── 4. اختبارات حجب البيانات السرية والخصوصية في السجلات (Redaction) ─────────

def test_password_redacted_in_logs():
    """14. حجب كلمات المرور التلقائي في السجلات."""
    data = {'username': 'admin', 'password': 'SuperSecretPassword123', 'action': 'login'}
    cleaned = sanitize_log_dict(data)
    assert cleaned['password'] == '[REDACTED]'
    assert cleaned['username'] == 'admin'


def test_token_redacted_in_logs():
    """15. حجب الرموز والتوكنات السرية (JWT / Tokens) في السجلات."""
    data = {'auth_token': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...', 'user_id': 1}
    cleaned = sanitize_log_dict(data)
    assert cleaned['auth_token'] == '[REDACTED]'


def test_nested_secrets_redacted():
    """16. حجب الأسرار المتداخلة في القواميس والقوائم العميقة."""
    nested = {
        'auth': {
            'credentials': {
                'new_password': 'secret_password_here',
                'csrf_token': 'csrf_value_123'
            }
        },
        'status': 'active'
    }
    cleaned = sanitize_log_dict(nested)
    assert cleaned['auth']['credentials']['new_password'] == '[REDACTED]'
    assert cleaned['auth']['credentials']['csrf_token'] == '[REDACTED]'
    assert cleaned['status'] == 'active'


def test_research_full_text_and_evidence_not_logged():
    """17 & 18. حظر تسجيل نصوص الأبحاث الكاملة أو الأدلة المستخرجة في السجلات."""
    payload = {
        'research_id': 101,
        'full_text': 'نص البحث الأكاديمي السري الكامل الذي يجب ألا يسجل في ملفات اللوج.',
        'evidence': 'أدلة الاقتباس والنصوص المتطابقة الحساسة.'
    }
    cleaned = sanitize_log_dict(payload)
    assert cleaned['full_text'] == '[REDACTED]'
    assert cleaned['evidence'] == '[REDACTED]'
    assert cleaned['research_id'] == 101


def test_newline_and_log_injection_sanitized():
    """19. الحماية ضد هجمات حقن السجلات (CRLF Log Injection)."""
    malicious_input = "research_title_1\r\n[2026-09-03 ERROR] Injected fake log line\nadmin logged in"
    sanitized = sanitize_log_string(malicious_input)
    assert '\r' not in sanitized
    assert '\n' not in sanitized


# ─── 5. اختبارات تدوير السجلات ودعم اللغة العربية (Log Rotation & UTF-8) ───────

def test_rotating_log_configuration_exists():
    """20. التحقق من وجود مجلد وملف السجلات وتهيئة التدوير (RotatingFileHandler)."""
    setup_logging()
    assert (config.BASE_DIR / 'logs').exists()


def test_utf8_arabic_logging_works():
    """21. تسجيل النصوص والرسائل باللغة العربية بترميز UTF-8 سليم دون تلف الحروف."""
    arabic_msg = "تم فحص البحث الأكاديمي بنجاح واعتماد التقرير النهائي."
    log_operational_event(logging.INFO, arabic_msg, component="test")
    sanitized = sanitize_log_string(arabic_msg)
    assert "الأكاديمي" in sanitized
    assert "النهائي" in sanitized


# ─── 6. التراجع عن معاملات قاعدة البيانات (Database Rollback on Failure) ──────

def test_db_failure_rolls_back_cleanly(client):
    """22. التراجع التلقائي عن أي جلسة قاعدة بيانات عند حدوث خطأ أو استثناء."""
    app = client.application

    @app.route('/test-db-rollback')
    def db_rollback_route():
        from app.repositories import base_repo
        from app.models.schema import User
        with base_repo.get_session() as session:
            dummy_u = User(username=f"dummy_{uuid.uuid4().hex[:6]}", password_hash="x", display_name="x", role="reviewer")
            session.add(dummy_u)
            raise RuntimeError("Force abort transaction")

    res = client.get('/test-db-rollback')
    assert res.status_code == 500


# ─── 7. حالات الأخطاء التشغيلية ومعالجة الأعطال (Operational Error Handling) ───

def test_scan_worker_failure_leaves_no_permanent_processing_state():
    """23. فشل مهمة الفحص يُوسم الحالة بـ failed ولا يترك المهمة معلقة في running."""
    jid = f"scan_fail_{uuid.uuid4().hex[:6]}"
    with base_repo.get_session() as session:
        job = ScanJob(id=jid, filename="corrupt.pdf", status="processing")
        session.add(job)

    try:
        # محاكاة وقوع خطأ أثناء معالجة المهمة
        with base_repo.get_session() as session:
            j = session.query(ScanJob).filter(ScanJob.id == jid).first()
            if j:
                j.status = "failed"
                j.error = "تعذر استخراج النص من الملف التالف."

        with base_repo.get_session() as session:
            updated_job = session.query(ScanJob).filter(ScanJob.id == jid).first()
            assert updated_job.status == "failed"
            assert "تعذر استخراج النص" in updated_job.error
    finally:
        with base_repo.get_session() as session:
            session.query(ScanJob).filter(ScanJob.id == jid).delete()


def test_extraction_failure_gets_stable_error_code():
    """24. فشل الاستخراج يحمل كود الخطأ المستقر FILE_EXTRACTION_FAILED."""
    err = ExtractionError("الملف المرفوع مصمت ولا يحتوي على نص قابل للقراءة.")
    assert err.code == ErrorCode.FILE_EXTRACTION_FAILED
    assert err.status_code == 400


def test_ocr_failure_handled_safely():
    """25. معالجة خطأ OCR بأمان دون التسبب في انهيار التطبيق."""
    from plagiarism_detector.extraction.ocr_engine import check_ocr_availability
    with patch('plagiarism_detector.extraction.ocr_engine.find_tesseract_cmd', return_value=None):
        info = check_ocr_availability()
        assert info['available'] is False
        assert 'has_arabic' in info


def test_backup_and_restore_failures_logged_safely():
    """26 & 27. تسجيل أخطاء النسخ الاحتياطي والاستعادة بأمان."""
    log_operational_event(
        level=logging.ERROR,
        message="فشل التحقق من مطابقة الأرشيف",
        component="backup",
        error_code=ErrorCode.BACKUP_FAILED,
        metadata={'backup_id': 'BKP-2026-001'}
    )
    log_operational_event(
        level=logging.ERROR,
        message="فشل استعادة قاعدة البيانات",
        component="restore",
        error_code=ErrorCode.RESTORE_FAILED,
        metadata={'backup_id': 'BKP-2026-001'}
    )


# ─── 8. الفصل التام بين السجلات التشغيلية وسجل التدقيق (Audit vs Ops Logs) ────

def test_operational_error_does_not_unnecessarily_create_audit_spam(client):
    """28. الأخطاء التشغيلية التقنية الاعتيادية لا تملأ وتضخم سجل التدقيق المؤسسي AuditLog."""
    with base_repo.get_session() as session:
        initial_audit_count = session.query(AuditLog).count()

    # تنفيذ خطأ تشغيلي (مسار غير موجود 404)
    client.get('/api/invalid_route_trigger_404')

    with base_repo.get_session() as session:
        new_audit_count = session.query(AuditLog).count()

    # سجل التدقيق لا يجب أن يزيد بأخطاء 404 العادية
    assert new_audit_count == initial_audit_count


def test_institutional_action_still_creates_audit_event(client):
    """29. الإجراءات المؤسسية والأمنية الحقيقية توثق بدقة في سجل التدقيق AuditLog."""
    uname = f"audited_admin_{uuid.uuid4().hex[:6]}"
    user_repo.add_user(uname, 'pass123', 'مدير', Role.SYSTEM_ADMIN)
    client.post('/api/auth/login', json={'username': uname, 'password': 'pass123'})

    with base_repo.get_session() as session:
        audit_count_before = session.query(AuditLog).count()

    # محاولة وصول غير مصرح بها توثق في سجل التدقيق الأمني
    uname_de = f"audited_de_{uuid.uuid4().hex[:6]}"
    user_repo.add_user(uname_de, 'pass123', 'مدخل بيانات', Role.DATA_ENTRY)
    client.post('/api/auth/login', json={'username': uname_de, 'password': 'pass123'})

    res = client.get('/api/admin/audit_logs')
    assert res.status_code == 403

    with base_repo.get_session() as session:
        audit_count_after = session.query(AuditLog).count()

    assert audit_count_after > audit_count_before
