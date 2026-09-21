# -*- coding: utf-8 -*-
"""
حزمة اختبارات سجل التدقيق والمراجعة المؤسسي (Institutional Audit Trail Tests):
- التحقق من تسجيل أحداث المصادقة، الإدارة، التحكيم، والرفع.
- التحقق من حجب كلمات المرور والبيانات الحساسة تماماً (Sanitization).
- التحقق من الصلاحيات ومنع الموظف من الوصول لسجل التدقيق.
- التحقق من البحث بالرقم المرجعي والتقسيم المكتبي (Pagination).
- التحقق من الحصانة ضد التعديل أو الحذف (Append-Only Immutability).
"""

import json
import pytest
from app import create_app
from app.models.audit_schema import AuditLog
from app.services import audit_service
from app.repositories import user_repo
from app.repositories.base_repo import get_session


@pytest.fixture
def client():
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


def _login_as(client, role, username):
    with client.session_transaction() as session:
        session['user_id'] = 876543
        session['username'] = username
        session['role'] = role


def test_successful_login_creates_audit_event(client):
    """تسجيل الدخول الناجح ينشئ حدث تدقيق auth.login.success."""
    user_repo.add_user('audit_test_user', 'secure_pass123', 'مدير الاختبار', 'admin')
    res = client.post('/api/auth/login', json={'username': 'audit_test_user', 'password': 'secure_pass123'})
    assert res.status_code == 200

    with get_session() as session:
        ev = (
            session.query(AuditLog)
            .filter(AuditLog.action == 'auth.login.success', AuditLog.username_snapshot == 'audit_test_user')
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert ev is not None
        assert ev.success is True
        assert ev.category == 'auth'


def test_failed_login_creates_audit_event_without_password_leakage(client):
    """تسجيل الدخول الفاشل يسجل محاولة الدخول دون تسريب كلمة المرور المدخلة نهائياً."""
    secret_pass = "SuperSecretPlainText12345!"
    res = client.post('/api/auth/login', json={'username': 'non_existent_user_xyz', 'password': secret_pass})
    assert res.status_code == 401

    with get_session() as session:
        ev = (
            session.query(AuditLog)
            .filter(AuditLog.action == 'auth.login.failure')
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert ev is not None
        assert ev.success is False
        assert ev.failure_reason_code == "INVALID_CREDENTIALS"
        # التأكد التام من عدم وجود كلمة المرور في أي حقل
        assert secret_pass not in (ev.metadata_json or '')
        assert 'non_existent_user_xyz' in (ev.metadata_json or '')


def test_logout_creates_audit_event(client):
    """تسجيل الخروج ينشئ حدث auth.logout."""
    res = client.post('/api/auth/logout', json={'username': 'audit_test_user'})
    assert res.status_code == 200

    with get_session() as session:
        ev = (
            session.query(AuditLog)
            .filter(AuditLog.action == 'auth.logout')
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert ev is not None
        assert ev.success is True


def _make_valid_test_pdf(text: str = "Sample") -> bytes:
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>\nendobj\n"
        b"4 0 obj\n<< /Length 44 >>\nstream\nBT /F1 12 Tf 100 700 Td (Hello World) Tj ET\nendstream\nendobj\n"
        b"xref\n0 5\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000214 00000 n \n"
        b"trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n308\n%%EOF"
    )


def test_batch_creation_creates_audit_event(client):
    """إنشاء دفعة أبحاث يسجل حدث batch.created في سجل التدقيق."""
    import io
    data = {
        'files[]': [
            (io.BytesIO(_make_valid_test_pdf("1")), "res1.pdf"),
            (io.BytesIO(_make_valid_test_pdf("2")), "res2.pdf")
        ],
        'titles[]': ['بحث التدقيق 1', 'بحث التدقيق 2'],
        'authors[]': ['باحث 1', 'باحث 2'],
        'label': 'دفعة تجريبية للتدقيق'
    }
    res = client.post('/api/batch/independent', data=data, content_type='multipart/form-data')
    assert res.status_code == 202
    resp_json = res.get_json()
    batch_id = resp_json['batch_id']

    with get_session() as session:
        ev = (
            session.query(AuditLog)
            .filter(AuditLog.action == 'batch.created', AuditLog.batch_id == batch_id)
            .first()
        )
        assert ev is not None
        assert ev.category == 'batch'
        assert ev.success is True


def test_multi_file_thesis_creation_creates_audit_event(client):
    """رفع رسالة متعددة الملفات يسجل حدث research.multi_file_created متضمناً الرقم المرجعي."""
    import io
    data = {
        'files[]': [
            (io.BytesIO(_make_valid_test_pdf("ch1")), "ch1.pdf"),
            (io.BytesIO(_make_valid_test_pdf("ch2")), "ch2.pdf")
        ],
        'orders[]': ['0', '1'],
        'title': 'رسالة دكتوراه عن التحكيم المؤسسي',
        'author': 'د. سامح عبد الله'
    }
    res = client.post('/api/batch/thesis', data=data, content_type='multipart/form-data')
    assert res.status_code == 202
    resp_json = res.get_json()
    res_id = resp_json['research_id']
    ref_num = resp_json['reference_number']

    with get_session() as session:
        ev = (
            session.query(AuditLog)
            .filter(AuditLog.action == 'research.multi_file_created', AuditLog.research_id == res_id)
            .first()
        )
        assert ev is not None
        assert ev.research_reference_number == ref_num
        assert ev.success is True


def test_academic_review_workflow_events(client):
    """قرارات التحكيم (الفحص الأولي، القبول المبدئي، الرفض، والقبول النهائي) توثق بدقة في سجل التدقيق."""
    from app.repositories import report_repo
    
    # مسار 1: إرسال -> قبول مبدئي -> قبول نهائي
    rep_id = "test_audit_rep_100"
    report_repo.save_report(
        report_id=rep_id,
        title="بحث قيد التحكيم للتدقيق",
        overall_pct=12.0,
        copied_pct=8.0,
        para_pct=4.0,
        report_dict={'title': 'بحث قيد التحكيم للتدقيق', 'segments': [{'text': 'محتوى أكاديمي تجريبي محفوظ لاختبار سجل القبول النهائي'}]},
        author='باحث تجريبي'
    )
    _login_as(client, 'employee', 'employee_audit_1')
    client.post(f'/api/reports/{rep_id}/submit_to_admin', json={'employee_name': 'فاحص 1', 'notes': 'ملاحظات'})
    _login_as(client, 'reviewer', 'reviewer_audit_1')
    client.post(f'/api/reports/{rep_id}/initial_accept')
    _login_as(client, 'senior_reviewer', 'senior_audit_1')
    client.post(f'/api/reports/{rep_id}/final_accept')

    # مسار 2: إرسال -> رفض
    rep_id_rej = "test_audit_rep_101"
    report_repo.save_report(
        report_id=rep_id_rej,
        title="بحث قيد التحكيم للرفض",
        overall_pct=60.0,
        copied_pct=50.0,
        para_pct=10.0,
        report_dict={'title': 'بحث قيد التحكيم للرفض'},
        author='باحث تجريبي'
    )
    _login_as(client, 'employee', 'employee_audit_2')
    client.post(f'/api/reports/{rep_id_rej}/submit_to_admin', json={'employee_name': 'فاحص 2', 'notes': 'ملاحظات الرفض'})
    _login_as(client, 'reviewer', 'reviewer_audit_2')
    client.post(f'/api/reports/{rep_id_rej}/reject')

    with get_session() as session:
        ev_sub = session.query(AuditLog).filter(AuditLog.action == 'review.submitted_to_admin', AuditLog.report_id == rep_id).first()
        ev_init = session.query(AuditLog).filter(AuditLog.action == 'review.preliminary_accepted', AuditLog.report_id == rep_id).first()
        ev_fin = session.query(AuditLog).filter(AuditLog.action == 'review.final_accepted', AuditLog.report_id == rep_id).first()
        ev_rej = session.query(AuditLog).filter(AuditLog.action == 'review.rejected', AuditLog.report_id == rep_id_rej).first()

        assert ev_sub is not None
        assert ev_init is not None
        assert ev_fin is not None
        assert ev_rej is not None


def test_settings_update_creates_audit_event_without_secret_leak(client):
    """تعديل الإعدادات يسجل أسماء الحقول المعدلة فقط دون كشف أي قيم سرية."""
    res = client.post('/api/settings', json={
        'jaccard_threshold': 0.35,
        'max_allowed_pages_per_source': 6.0
    })
    assert res.status_code == 200

    with get_session() as session:
        ev = (
            session.query(AuditLog)
            .filter(AuditLog.action == 'settings.updated')
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert ev is not None
        meta = json.loads(ev.metadata_json)
        assert 'changed_fields' in meta
        assert 'jaccard_threshold' in meta['changed_fields']


def test_employee_cannot_access_audit_endpoints(client):
    """الموظف العادي يُمنع تماماً من الوصول لسجل التدقيق (HTTP 403 Forbidden)."""
    headers = {'X-User-Role': 'employee', 'X-User-Name': 'emp_user'}
    res = client.get('/api/admin/audit_logs', headers=headers)
    assert res.status_code == 403
    assert 'غير مصرح' in str(res.get_json().get('error', ''))


def test_admin_can_access_audit_endpoints(client):
    """مدير النظام مصرح له باسترجاع وتصفية سجلات التدقيق (HTTP 200 OK)."""
    headers = {'X-User-Role': 'admin', 'X-User-Name': 'admin'}
    res = client.get('/api/admin/audit_logs', headers=headers)
    assert res.status_code == 200
    data = res.get_json()
    assert 'events' in data
    assert 'total' in data
    assert 'page' in data


def test_search_and_filter_by_reference_number(client):
    """البحث والتصفية بالرقم المرجعي الرسمي يسترجع الأحداث المرتبطة بدقة."""
    ref_num = "RES-2026-999888"
    audit_service.record_event(
        action="research.special_audit_test",
        category="research",
        research_reference_number=ref_num,
        success=True
    )

    headers = {'X-User-Role': 'admin'}
    res = client.get(f'/api/admin/audit_logs?reference_number={ref_num}', headers=headers)
    assert res.status_code == 200
    data = res.get_json()
    assert len(data['events']) >= 1
    assert data['events'][0]['research_reference_number'] == ref_num


def test_audit_pagination_works(client):
    """التقسيم المكتبي (Pagination) يعمل بسلاسة عبر المعاملات page و per_page."""
    headers = {'X-User-Role': 'admin'}
    res1 = client.get('/api/admin/audit_logs?page=1&per_page=5', headers=headers)
    data1 = res1.get_json()
    assert data1['page'] == 1
    assert data1['per_page'] == 5
    assert len(data1['events']) <= 5


def test_audit_sanitization_filters_sensitive_keys():
    """خدمة التدقيق تطهر تلقائياً كلمات المرور والرموز والنصوص الطويلة من البيانات الوصفية."""
    dirty_meta = {
        'password': 'PlainPassword123',
        'old_password': 'OldPassword456',
        'csrf_token': 'secret-token-abc',
        'full_text': 'A' * 2000,
        'safe_title': 'عنوان آمن تماماً'
    }
    sanitized = audit_service.sanitize_metadata(dirty_meta)
    assert sanitized['password'] == '[REDACTED]'
    assert sanitized['old_password'] == '[REDACTED]'
    assert sanitized['csrf_token'] == '[REDACTED]'
    assert sanitized['full_text'] == '[REDACTED]'
    assert sanitized['safe_title'] == 'عنوان آمن تماماً'


def test_immutability_no_edit_or_delete_routes(client):
    """لا توجد أي مسارات برمجية تسمح بتعديل أو حذف سجلات التدقيق."""
    headers = {'X-User-Role': 'admin'}
    res_put = client.put('/api/admin/audit_logs/1', headers=headers, json={'action': 'hacked'})
    res_del = client.delete('/api/admin/audit_logs/1', headers=headers)

    assert res_put.status_code in (404, 405)
    assert res_del.status_code in (404, 405)
