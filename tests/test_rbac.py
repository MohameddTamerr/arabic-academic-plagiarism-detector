# -*- coding: utf-8 -*-
"""
حزمة اختبارات نموذج التحكم في الوصول المبني على الأدوار المؤسسية (Institutional RBAC Tests):
1. التحقق من حظر وصول المستخدم غير المسجل (401 أو 403).
2. التحقق من صلاحيات مدخل البيانات (data_entry) في الرفع والحظر من التحكيم.
3. التحقق من صلاحيات المراجع (reviewer) في القبول المبدئي والحظر من الاعتماد النهائي.
4. التحقق من صلاحيات المراجع الأول (senior_reviewer) في الاعتماد النهائي.
5. التحقق من حظر المراجعين العاديين من سجل التدقيق والإعدادات وإتاحتها لمدير النظام (system_admin).
6. التحقق الصارم من أن ترويسة X-User-Role المزورة لا تمنح أي صلاحيات إضافية (Trust Boundary).
7. التحقق من مواءمة الأدوار القديمة (admin, employee) دون قفل الحسابات أو تقليص الصلاحيات.
8. توثيق أحداث authorization.access_denied و user.role_changed في سجل التدقيق.
"""

import json
import pytest
from flask import g, session as flask_session
from app import create_app
from app.repositories import user_repo, report_repo, base_repo
from app.models.schema import User
from app.models.audit_schema import AuditLog
from app.security.permissions import (
    Permission, Role, get_role_permissions, get_user_permissions, normalize_role
)


@pytest.fixture
def app_instance():
    app = create_app()
    app.config['TESTING'] = True
    app.config['STRICT_AUTH'] = True
    app.config['SECRET_KEY'] = 'test-rbac-secret-key-2026'
    return app


@pytest.fixture
def client(app_instance):
    with app_instance.test_client() as client:
        yield client


def _setup_test_user(username, role, password="Password123!"):
    """مساعد لإنشاء أو استرجاع مستخدم تجريبي بدور محدد."""
    with base_repo.get_session() as session:
        user = session.query(User).filter(User.username == username).first()
        if not user:
            user = User(
                username=username,
                password_hash=user_repo.hash_password(password),
                full_name=f"مستخدم تجريبي {username}",
                role=role
            )
            session.add(user)
            session.flush()
        else:
            user.role = role
        return user.id, user.username, user.role


def test_permission_matrix_integrity():
    """التحقق من صحة مصفوفة الصلاحيات الافتراضية لكل دور مؤسسي."""
    entry_perms = get_role_permissions(Role.DATA_ENTRY)
    assert Permission.RESEARCH_UPLOAD in entry_perms
    assert Permission.REVIEW_PRELIMINARY not in entry_perms
    assert Permission.REVIEW_FINAL not in entry_perms
    assert Permission.AUDIT_VIEW not in entry_perms

    rev_perms = get_role_permissions(Role.REVIEWER)
    assert Permission.RESEARCH_UPLOAD in rev_perms
    assert Permission.REVIEW_PRELIMINARY in rev_perms
    assert Permission.REVIEW_FINAL not in rev_perms
    assert Permission.AUDIT_VIEW not in rev_perms

    senior_perms = get_role_permissions(Role.SENIOR_REVIEWER)
    assert Permission.REVIEW_PRELIMINARY in senior_perms
    assert Permission.REVIEW_FINAL in senior_perms
    assert Permission.AUDIT_VIEW not in senior_perms

    admin_perms = get_role_permissions(Role.SYSTEM_ADMIN)
    assert Permission.USERS_MANAGE in admin_perms
    assert Permission.SETTINGS_MANAGE in admin_perms
    assert Permission.AUDIT_VIEW in admin_perms
    assert Permission.BACKUP_CREATE in admin_perms


def test_unauthenticated_user_cannot_access_protected_apis(client):
    """المستخدم غير المسجل لا يمكنه الوصول لنقاط النهاية المحمية."""
    res_audit = client.get('/api/admin/audit_logs')
    assert res_audit.status_code in (401, 403)

    res_settings = client.post('/api/settings', json={'threshold': 20})
    assert res_settings.status_code in (401, 403)


def test_forged_x_user_role_header_does_not_elevate_privileges(client):
    """ترويسة X-User-Role المزورة من العميل لا تمنح أي صلاحيات لمدير النظام (Zero Trust)."""
    # محاولة الوصول لسجلات التدقيق بترويسة مزورة دون تسجيل دخول حقيقي
    res = client.get('/api/admin/audit_logs', headers={'X-User-Role': 'admin', 'X-Admin': 'true'})
    assert res.status_code in (401, 403)

    # محاولة تغيير الإعدادات بترويسة مزورة
    res_set = client.post('/api/settings', json={'threshold': 25}, headers={'X-User-Role': 'system_admin'})
    assert res_set.status_code in (401, 403)


def test_data_entry_role_capabilities_and_restrictions(client, app_instance):
    """مدخل البيانات يملك صلاحية الرفع ولا يملك صلاحية التحكيم الأكاديمي."""
    uid, uname, urole = _setup_test_user('data_entry_user_1', Role.DATA_ENTRY)

    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = uname
        sess['role'] = urole

    # 1. إنشاء تقرير لاختبار محاولة الاعتماد
    rep_id = "test_rbac_rep_data_entry"
    report_repo.save_report(
        report_id=rep_id,
        title="بحث مدخل البيانات",
        overall_pct=10.0,
        copied_pct=5.0,
        para_pct=5.0,
        report_dict={'title': 'بحث مدخل البيانات'},
        review_status='pending_review'
    )

    # محاولة قبول مبدئي من مدخل بيانات -> يجب أن ترفض (403 Forbidden)
    res_accept = client.post(f'/api/reports/{rep_id}/initial_accept')
    assert res_accept.status_code == 403
    assert 'غير مصرح' in str(res_accept.get_json().get('error', ''))

    # محاولة الوصول لسجلات التدقيق -> 403 Forbidden
    res_audit = client.get('/api/admin/audit_logs')
    assert res_audit.status_code == 403


def test_reviewer_role_capabilities_and_restrictions(client, app_instance):
    """المراجع يملك صلاحية القبول المبدئي والرفض ولكن ليس الاعتماد النهائي أو إدارة النظام."""
    uid, uname, urole = _setup_test_user('reviewer_user_1', Role.REVIEWER)

    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = uname
        sess['role'] = urole

    rep_id = "test_rbac_rep_reviewer"
    report_repo.save_report(
        report_id=rep_id,
        title="بحث قيد المراجعة الأكاديمية",
        overall_pct=15.0,
        copied_pct=10.0,
        para_pct=5.0,
        report_dict={'title': 'بحث قيد المراجعة الأكاديمية'},
        review_status='pending_review'
    )

    # 1. قبول مبدئي -> مسموح (200 OK)
    res_init = client.post(f'/api/reports/{rep_id}/initial_accept')
    assert res_init.status_code == 200
    assert res_init.get_json()['review_status'] == 'preliminary_accepted'

    # 2. اعتماد نهائي من مراجع عادي -> مرفوض (403 Forbidden)
    res_final = client.post(f'/api/reports/{rep_id}/final_accept')
    assert res_final.status_code == 403

    # 3. محاولة تعديل الإعدادات -> مرفوض (403 Forbidden)
    res_set = client.post('/api/settings', json={'threshold': 15})
    assert res_set.status_code == 403


def test_senior_reviewer_can_perform_final_approval(client, app_instance):
    """المراجع الأول / المراجع النهائي يملك صلاحية الاعتماد النهائي."""
    uid, uname, urole = _setup_test_user('senior_user_1', Role.SENIOR_REVIEWER)

    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = uname
        sess['role'] = urole

    rep_id = "test_rbac_rep_senior"
    report_repo.save_report(
        report_id=rep_id,
        title="بحث المراجع النهائي",
        overall_pct=8.0,
        copied_pct=4.0,
        para_pct=4.0,
        report_dict={'title': 'بحث المراجع النهائي'},
        review_status='preliminary_accepted'
    )

    res_final = client.post(f'/api/reports/{rep_id}/final_accept')
    assert res_final.status_code == 200
    assert res_final.get_json()['review_status'] == 'final_accepted'


def test_system_admin_capabilities(client, app_instance):
    """مدير النظام يملك صلاحيات التدقيق، الإعدادات، وإدارة المستخدمين."""
    uid, uname, urole = _setup_test_user('admin_user_rbac', Role.SYSTEM_ADMIN)

    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = uname
        sess['role'] = urole

    # 1. استعراض سجلات التدقيق
    res_audit = client.get('/api/admin/audit_logs')
    assert res_audit.status_code == 200
    assert 'events' in res_audit.get_json()

    # 2. استرجاع وتحديث الإعدادات
    res_set_get = client.get('/api/settings')
    assert res_set_get.status_code == 200

    # 3. استعراض المستخدمين
    res_users = client.get('/api/admin/users')
    assert res_users.status_code == 200
    assert 'users' in res_users.get_json()


def test_legacy_role_mappings_and_compatibility():
    """الأدوار القديمة admin و employee تحافظ على التوافق الكامل دون قفل الحسابات."""
    assert normalize_role('admin') == Role.LEGACY_ADMIN
    assert normalize_role('employee') == Role.LEGACY_EMPLOYEE

    admin_perms = get_role_permissions(Role.LEGACY_ADMIN)
    assert Permission.AUDIT_VIEW in admin_perms
    assert Permission.USERS_MANAGE in admin_perms

    emp_perms = get_role_permissions(Role.LEGACY_EMPLOYEE)
    assert Permission.RESEARCH_UPLOAD in emp_perms
    assert Permission.REVIEW_PRELIMINARY in emp_perms


def test_audit_event_recorded_on_access_denied(client, app_instance):
    """محاولات الوصول الممنوعة توثق حدث authorization.access_denied في سجل التدقيق."""
    uid, uname, urole = _setup_test_user('unauth_actor', Role.DATA_ENTRY)

    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = uname
        sess['role'] = urole

    # محاولة غير مصرح بها للوصول إلى سجل التدقيق
    res = client.get('/api/admin/audit_logs')
    assert res.status_code == 403

    with base_repo.get_session() as session:
        denied_ev = (
            session.query(AuditLog)
            .filter(AuditLog.action == 'authorization.access_denied', AuditLog.username_snapshot == uname)
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert denied_ev is not None
        meta = json.loads(denied_ev.metadata_json)
        assert meta['required_permission'] == Permission.AUDIT_VIEW


def test_user_role_changed_audit_event(client, app_instance):
    """تعديل دور مستخدم يوثق حدث user.role_changed في سجل التدقيق."""
    admin_id, admin_name, admin_role = _setup_test_user('super_admin_role_change', Role.SYSTEM_ADMIN)
    target_id, target_name, _ = _setup_test_user('role_change_target', Role.DATA_ENTRY)

    with client.session_transaction() as sess:
        sess['user_id'] = admin_id
        sess['username'] = admin_name
        sess['role'] = admin_role

    res = client.post(f'/api/admin/users/{target_id}/role', json={'role': 'reviewer'})
    assert res.status_code == 200

    with base_repo.get_session() as session:
        ev = (
            session.query(AuditLog)
            .filter(AuditLog.action == 'user.role_changed', AuditLog.object_id == str(target_id))
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert ev is not None
        meta = json.loads(ev.metadata_json)
        assert meta['previous_role'] == Role.DATA_ENTRY
        assert meta['new_role'] == Role.REVIEWER


def test_unit_manager_capabilities(client, app_instance):
    """مسؤول الوحدة يملك صلاحيات المراجع الأول بالإضافة إلى إدارة المراجع وفحص الجاهزية."""
    uid, uname, urole = _setup_test_user('unit_mgr_1', Role.UNIT_MANAGER)

    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = uname
        sess['role'] = urole

    # 1. فحص تشخيص النظام -> مسموح (200 OK)
    res_diag = client.get('/api/system/diagnostics')
    assert res_diag.status_code == 200

    # 2. عرض المراجع -> مسموح (200 OK)
    res_papers = client.get('/api/papers')
    assert res_papers.status_code == 200


def test_unit_manager_cannot_manage_users_or_settings(client, app_instance):
    """مسؤول الوحدة محظور من إدارة مستخدمي النظام أو تعديل إعدادات النظام الحساسة."""
    uid, uname, urole = _setup_test_user('unit_mgr_restricted', Role.UNIT_MANAGER)

    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = uname
        sess['role'] = urole

    # محاولة تعديل الإعدادات -> 403
    res_set = client.post('/api/settings', json={'threshold': 20})
    assert res_set.status_code == 403

    # محاولة استعراض سجل التدقيق -> 403
    res_audit = client.get('/api/admin/audit_logs')
    assert res_audit.status_code == 403


def test_reviewer_can_reject_report(client, app_instance):
    """المراجع يملك صلاحية رفض الأبحاث المخالفة لمعايير الأمانة العلمية."""
    uid, uname, urole = _setup_test_user('reviewer_rejector', Role.REVIEWER)

    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = uname
        sess['role'] = urole

    rep_id = "test_rbac_rep_reject"
    report_repo.save_report(
        report_id=rep_id,
        title="بحث مخالف",
        overall_pct=50.0,
        copied_pct=40.0,
        para_pct=10.0,
        report_dict={'title': 'بحث مخالف'},
        review_status='pending_review'
    )

    res_rej = client.post(f'/api/reports/{rep_id}/reject')
    assert res_rej.status_code == 200
    assert res_rej.get_json()['review_status'] == 'rejected'


def test_non_admin_cannot_trigger_backup(client, app_instance):
    """المستخدمون غير الإداريين محظورون من إنشاء النسخ الاحتياطية (403 Forbidden)."""
    uid, uname, urole = _setup_test_user('reviewer_no_backup', Role.REVIEWER)

    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = uname
        sess['role'] = urole

    res = client.post('/api/admin/backup')
    assert res.status_code == 403


def test_system_admin_can_trigger_backup(client, app_instance):
    """مدير النظام يملك صلاحية إنشاء النسخ الاحتياطية لقاعدة البيانات."""
    uid, uname, urole = _setup_test_user('admin_backup_actor', Role.SYSTEM_ADMIN)

    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = uname
        sess['role'] = urole

    res = client.post('/api/admin/backup')
    assert res.status_code == 200
    assert res.get_json()['success'] is True


def test_reviewer_cannot_clear_database(client, app_instance):
    """المراجع العادي محظور من حذف قاعدة المراجع بالكامل (403 Forbidden)."""
    uid, uname, urole = _setup_test_user('reviewer_no_clear', Role.REVIEWER)

    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = uname
        sess['role'] = urole

    res = client.delete('/api/clear-db')
    assert res.status_code == 403


def test_auth_me_returns_profile_permissions_and_arabic_label(client, app_instance):
    """نقطة /api/auth/me تعيد بيانات المستخدم وصلاحياته والتسمية العربية المؤسسية."""
    uid, uname, urole = _setup_test_user('senior_me_test', Role.SENIOR_REVIEWER)

    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = uname
        sess['role'] = urole

    res = client.get('/api/auth/me')
    assert res.status_code == 200
    data = res.get_json()
    assert data['authenticated'] is True
    assert data['user']['role'] == Role.SENIOR_REVIEWER
    assert 'مراجع أول' in data['user']['role_label_ar']
    assert Permission.REVIEW_FINAL in data['user']['permissions']


def test_report_delete_requires_proper_permissions(client, app_instance):
    """حذف التقارير من الأرشيف مقصور على الصلاحيات الإدارية."""
    uid, uname, urole = _setup_test_user('entry_no_delete', Role.DATA_ENTRY)

    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = uname
        sess['role'] = urole

    res = client.delete('/api/reports/non_existent_rep')
    assert res.status_code == 403


def test_unauthenticated_auth_me_returns_anonymous(client, app_instance):
    """نقطة /api/auth/me لمستخدم غير مسجل تعيد authenticated = false."""
    res = client.get('/api/auth/me')
    assert res.status_code == 200
    data = res.get_json()
    assert data['authenticated'] is False
    assert data['user'] is None


def test_data_entry_can_view_reports_and_stats(client, app_instance):
    """مدخل البيانات مصرح له باستعراض التقارير وإحصائيات المنظومة."""
    uid, uname, urole = _setup_test_user('entry_viewer_test', Role.DATA_ENTRY)

    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = uname
        sess['role'] = urole

    res_stats = client.get('/api/stats')
    assert res_stats.status_code == 200
    assert 'total_scans' in res_stats.get_json()

