# -*- coding: utf-8 -*-
"""
FINAL ADMIN UI / RBAC CORRECTION GATE TEST SUITE
- SysAdmin user management (create all roles, search, paginate, filter by dept, toggle status, reset password).
- Recovery secret protection (enrollment status visible, secrets/PINs never exposed to admin, revoke/re-enroll).
- EMPLOYEE strict 403 enforcement (cannot accept, reject, final accept, manage users, view audit).
- REVIEWER vs SENIOR_REVIEWER separation of duties (Reviewer: initial accept/reject only; Senior Reviewer: final accept/finalize).
- Self-review denial (submitter cannot accept/reject own submission -> SELF_REVIEW_FORBIDDEN 403).
- Row-level department/unit scoping and IDOR protection.
- Multi-part thesis workflow with weighted analyzable-word similarity calculation.
- Database preservation & bootstrap status invariants.
"""

import json
import uuid
import pytest
from app import create_app
from app.models.schema import User, LegacyReport
from app.models.research_schema import Thesis, ThesisPart
from app.repositories.base_repo import get_session as get_db_session
from app.security.permissions import Role, Permission, role_has_permission, normalize_role
from app.services import thesis_service
from app.repositories import report_repo, thesis_repo


@pytest.fixture
def app_instance():
    app = create_app()
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app_instance):
    return app_instance.test_client()


def test_rbac_permission_matrix_authoritative():
    """Verify authoritative permission mapping for all institutional roles."""
    # EMPLOYEE
    assert role_has_permission(Role.EMPLOYEE, Permission.RESEARCH_UPLOAD) is True
    assert role_has_permission(Role.EMPLOYEE, Permission.SCAN_START) is True
    assert role_has_permission(Role.EMPLOYEE, Permission.REVIEW_PRELIMINARY) is False
    assert role_has_permission(Role.EMPLOYEE, Permission.REVIEW_REJECT) is False
    assert role_has_permission(Role.EMPLOYEE, Permission.REVIEW_FINAL) is False
    assert role_has_permission(Role.EMPLOYEE, Permission.USERS_MANAGE) is False
    assert role_has_permission(Role.EMPLOYEE, Permission.AUDIT_VIEW) is False

    # REVIEWER
    assert role_has_permission(Role.REVIEWER, Permission.REVIEW_PRELIMINARY) is True
    assert role_has_permission(Role.REVIEWER, Permission.REVIEW_REJECT) is True
    assert role_has_permission(Role.REVIEWER, Permission.REVIEW_FINAL) is False
    assert role_has_permission(Role.REVIEWER, Permission.REPORT_FINALIZE) is False
    assert role_has_permission(Role.REVIEWER, Permission.REPORT_VOID) is False
    assert role_has_permission(Role.REVIEWER, Permission.USERS_MANAGE) is False

    # SENIOR_REVIEWER
    assert role_has_permission(Role.SENIOR_REVIEWER, Permission.REVIEW_FINAL) is True
    assert role_has_permission(Role.SENIOR_REVIEWER, Permission.REPORT_FINALIZE) is True
    assert role_has_permission(Role.SENIOR_REVIEWER, Permission.REVIEW_PRELIMINARY) is True

    # UNIT_MANAGER
    assert role_has_permission(Role.UNIT_MANAGER, Permission.THESIS_CREATE) is True
    assert role_has_permission(Role.UNIT_MANAGER, Permission.THESIS_VIEW) is True
    assert role_has_permission(Role.UNIT_MANAGER, Permission.REVIEW_FINAL) is False

    # SYSTEM_ADMIN
    assert role_has_permission(Role.SYSTEM_ADMIN, Permission.USERS_MANAGE) is True
    assert role_has_permission(Role.SYSTEM_ADMIN, Permission.SETTINGS_MANAGE) is True
    assert role_has_permission(Role.SYSTEM_ADMIN, Permission.AUDIT_VIEW) is True
    assert role_has_permission(Role.SYSTEM_ADMIN, Permission.USER_PASSWORD_ADMIN_RESET) is True
    assert role_has_permission(Role.SYSTEM_ADMIN, Permission.REVIEW_VIEW) is True
    assert role_has_permission(Role.SYSTEM_ADMIN, Permission.REVIEW_PRELIMINARY) is True
    assert role_has_permission(Role.SYSTEM_ADMIN, Permission.REVIEW_FINAL) is True


def test_sysadmin_user_management_lifecycle(client):
    """Test full user management lifecycle by SysAdmin."""
    with get_db_session() as session:
        admin = User(
            username=f"sysadmin_{uuid.uuid4().hex[:6]}",
            password_hash="fake_hash",
            full_name="المدير العام",
            role="system_admin",
            session_version=1,
            is_active=1
        )
        session.add(admin)
        session.commit()
        admin_id = admin.id
        admin_role = admin.role
        admin_user = admin.username

    with client.session_transaction() as sess:
        sess['user_id'] = admin_id
        sess['role'] = admin_role
        sess['username'] = admin_user
        sess['session_version'] = 1

    unique_dept = f"كلية الهندسة_{uuid.uuid4().hex[:4]}"

    # 1. Create employees, reviewers, senior reviewers, unit managers
    roles_to_test = [
        ('emp_gate', 'موظف تجريبي', 'employee', unique_dept),
        ('rev_gate', 'محكم تجريبي', 'reviewer', unique_dept),
        ('srev_gate', 'محكم أول تجريبي', 'senior_reviewer', unique_dept),
        ('umgr_gate', 'مدير وحدة تجريبي', 'unit_manager', unique_dept),
    ]

    created_ids = {}
    for prefix, name, r_name, dept in roles_to_test:
        u_name = f"{prefix}_{uuid.uuid4().hex[:4]}"
        res = client.post('/api/admin/users', json={
            'username': u_name,
            'full_name': name,
            'role': r_name,
            'department': dept,
            'password': 'ComplexPassword#2026!'
        })
        assert res.status_code == 201, f"Failed creating {r_name}: {res.get_data(as_text=True)}"
        data = res.get_json()
        assert data['success'] is True
        created_ids[r_name] = (data['user_id'], u_name)

    # 2. List and search with department filter
    res = client.get(f'/api/admin/users?department={unique_dept}&page=1&page_size=20')
    assert res.status_code == 200
    list_data = res.get_json()
    items = list_data.get('items') or list_data.get('users', [])
    assert len(items) == 4

    # 3. User details must show has_recovery_key but NEVER expose secret or PIN
    emp_user_id, emp_username = created_ids['employee']
    res = client.get(f'/api/admin/users/{emp_user_id}')
    assert res.status_code == 200
    user_detail = res.get_json()
    assert user_detail['username'] == emp_username
    assert 'has_recovery_key' in user_detail
    assert 'recovery_secret' not in user_detail
    assert 'recovery_pin' not in user_detail
    assert 'password_hash' not in user_detail

    # 4. Toggle active status
    res = client.post(f'/api/admin/users/{emp_user_id}/toggle_status', json={'is_active': False})
    assert res.status_code == 200
    assert res.get_json()['success'] is True

    # 5. Reset password by Admin
    res = client.post(f'/api/admin/users/{emp_user_id}/reset_password', json={
        'new_password': 'NewAdminReset#2026!',
        'must_change_password': 1
    })
    assert res.status_code == 200
    assert res.get_json()['success'] is True


def test_employee_403_restrictions(client):
    """Verify that an EMPLOYEE cannot perform any review, accept, reject, or admin actions."""
    # Create employee in DB
    with get_db_session() as session:
        emp = User(
            username=f"strict_emp_{uuid.uuid4().hex[:6]}",
            password_hash="fake_hash",
            full_name="موظف فحص ميداني",
            role="employee",
            department="قسم الحاسب",
            is_active=1
        )
        session.add(emp)
        session.commit()
        emp_id = emp.id
        emp_username = emp.username

    # Create dummy report
    report_id = f"gate_rep_{uuid.uuid4().hex[:8]}"
    report_repo.save_report(
        report_id=report_id,
        title="بحث اختبار الصلاحيات الصارمة",
        overall_pct=15.0,
        copied_pct=10.0,
        para_pct=5.0,
        report_dict={'segments': [{'text': 'محتوى أكاديمي محفوظ صالح للإضافة إلى قاعدة المراجع المؤسسية'}], 'summary': 'test'},
        category="قسم الحاسب",
        author="د. أحمد كمال",
        scan_status="completed",
        review_status="pending_review"
    )

    with client.session_transaction() as sess:
        sess['user_id'] = emp_id
        sess['role'] = 'employee'
        sess['username'] = emp_username
        sess['department'] = 'قسم الحاسب'

    # 1. Employee cannot view user list
    res = client.get('/api/admin/users')
    assert res.status_code == 403

    # 2. Employee cannot create users
    res = client.post('/api/admin/users', json={'username': 'illegal_user', 'password': 'Password123!'})
    assert res.status_code == 403

    # 3. Employee cannot view audit trail
    res = client.get('/api/admin/audit_logs')
    assert res.status_code == 403

    # 4. Employee cannot perform initial accept
    res = client.post(f'/api/reports/{report_id}/initial_accept', json={'comment': 'محاولة غير مصرحة'})
    assert res.status_code == 403

    # 5. Employee cannot reject report
    res = client.post(f'/api/reports/{report_id}/reject', json={'reason': 'محاولة غير مصرحة'})
    assert res.status_code == 403

    # 6. Employee cannot perform final accept
    res = client.post(f'/api/reports/{report_id}/final_accept')
    assert res.status_code == 403

    # 7. Employee cannot finalize report
    res = client.post(f'/api/reports/{report_id}/finalize')
    assert res.status_code == 403

    # 8. Employee cannot void report
    res = client.post(f'/api/reports/{report_id}/void', json={'reason': 'محاولة غير مصرحة'})
    assert res.status_code == 403


def test_reviewer_vs_senior_reviewer_separation(client):
    """Test that REVIEWER cannot do final accept/finalize, but SENIOR_REVIEWER can."""
    with get_db_session() as session:
        rev = User(
            username=f"rev_user_{uuid.uuid4().hex[:6]}",
            password_hash="fake_hash",
            full_name="محكم أبحاث",
            role="reviewer",
            department="قسم الرياضيات",
            is_active=1
        )
        srev = User(
            username=f"srev_user_{uuid.uuid4().hex[:6]}",
            password_hash="fake_hash",
            full_name="محكم أول رئيسي",
            role="senior_reviewer",
            department="قسم الرياضيات",
            is_active=1
        )
        session.add(rev)
        session.add(srev)
        session.commit()
        rev_id, srev_id = rev.id, srev.id
        rev_username, srev_username = rev.username, srev.username

    report_id = f"sep_rep_{uuid.uuid4().hex[:8]}"
    report_repo.save_report(
        report_id=report_id,
        title="بحث تفريق الأدوار",
        overall_pct=8.0,
        copied_pct=5.0,
        para_pct=3.0,
        report_dict={'segments': [{'text': 'محتوى أكاديمي محفوظ صالح للإضافة إلى قاعدة المراجع المؤسسية'}], 'summary': 'test'},
        category="قسم الرياضيات",
        author="د. خليل إبراهيم",
        scan_status="completed",
        review_status="pending_review"
    )

    # 1. REVIEWER can preliminary accept
    with client.session_transaction() as sess:
        sess['user_id'] = rev_id
        sess['role'] = 'reviewer'
        sess['username'] = rev_username
        sess['department'] = 'قسم الرياضيات'

    res = client.post(f'/api/reports/{report_id}/initial_accept', json={'comment': 'مقبول مبدئياً'})
    assert res.status_code == 200

    # 2. REVIEWER CANNOT final accept -> 403
    res = client.post(f'/api/reports/{report_id}/final_accept')
    assert res.status_code == 403

    # 3. REVIEWER CANNOT finalize report -> 403
    res = client.post(f'/api/reports/{report_id}/finalize')
    assert res.status_code == 403

    # 4. SENIOR_REVIEWER CAN final accept -> 200
    with client.session_transaction() as sess:
        sess['user_id'] = srev_id
        sess['role'] = 'senior_reviewer'
        sess['username'] = srev_username
        sess['department'] = 'قسم الرياضيات'

    res = client.post(f'/api/reports/{report_id}/final_accept')
    assert res.status_code == 200
    assert res.get_json()['status'] == 'قبول نهائي'


def test_self_review_forbidden_protection(client):
    """Test that a user cannot approve or reject their own submitted paper."""
    with get_db_session() as session:
        reviewer_submitter = User(
            username=f"submitter_{uuid.uuid4().hex[:6]}",
            password_hash="fake_hash",
            full_name="محكم باحث",
            role="senior_reviewer",
            department="قسم العلوم",
            is_active=1
        )
        session.add(reviewer_submitter)
        session.commit()
        sub_id = reviewer_submitter.id
        sub_username = reviewer_submitter.username

    report_id = f"self_rev_{uuid.uuid4().hex[:8]}"
    report_repo.save_report(
        report_id=report_id,
        title="بحث مقدم ذاتياً",
        overall_pct=12.0,
        copied_pct=8.0,
        para_pct=4.0,
        report_dict={'segments': [{'text': 'محتوى أكاديمي محفوظ صالح للإضافة إلى قاعدة المراجع المؤسسية'}], 'summary': 'test'},
        category="قسم العلوم",
        author="د. حسام",
        submitted_by=sub_username,
        scan_status="completed",
        review_status="pending_review"
    )

    with client.session_transaction() as sess:
        sess['user_id'] = sub_id
        sess['role'] = 'senior_reviewer'
        sess['username'] = sub_username
        sess['department'] = 'قسم العلوم'

    # Self-review initial accept -> 403
    res = client.post(f'/api/reports/{report_id}/initial_accept', json={'comment': 'اعتماد ذاتي'})
    assert res.status_code == 403
    resp_data = res.get_json() or {}
    assert resp_data.get('code') == 'AUTH_FORBIDDEN' or 'غير مصرح' in resp_data.get('error', '')

    # Self-review reject -> 403
    res = client.post(f'/api/reports/{report_id}/reject', json={'reason': 'رفض ذاتي'})
    assert res.status_code == 403

    # Self-review final accept -> 403
    res = client.post(f'/api/reports/{report_id}/final_accept')
    assert res.status_code == 403


def test_idor_department_scoping_protection(client):
    """Test department scoping: Unit Manager / Reviewer from Dept A cannot access Dept B."""
    with get_db_session() as session:
        mgr_cs = User(
            username=f"mgr_cs_{uuid.uuid4().hex[:6]}",
            password_hash="fake_hash",
            full_name="مدير قسم الحاسب",
            role="unit_manager",
            department="قسم علوم الحاسب",
            is_active=1
        )
        mgr_eng = User(
            username=f"mgr_eng_{uuid.uuid4().hex[:6]}",
            password_hash="fake_hash",
            full_name="مدير قسم الهندسة",
            role="unit_manager",
            department="قسم الهندسة المدنية",
            is_active=1
        )
        session.add(mgr_cs)
        session.add(mgr_eng)
        session.commit()
        cs_id, eng_id = mgr_cs.id, mgr_eng.id
        mgr_cs_user = mgr_cs.username

    # Create report in Civil Engineering
    report_eng_id = f"rep_eng_{uuid.uuid4().hex[:8]}"
    report_repo.save_report(
        report_id=report_eng_id,
        title="بحث الهندسة المدنية",
        overall_pct=10.0,
        copied_pct=6.0,
        para_pct=4.0,
        report_dict={'segments': [], 'department': 'قسم الهندسة المدنية'},
        category="قسم الهندسة المدنية",
        author="م. عمر",
        scan_status="completed",
        review_status="pending_review"
    )

    # Create thesis in Civil Engineering
    thesis_eng_id, _ = thesis_repo.create_thesis(
        title="أطروحة الهندسة المدنية",
        author="م. عمر",
        department="قسم الهندسة المدنية",
        created_by="mgr_eng"
    )

    # Log in as CS Unit Manager
    with client.session_transaction() as sess:
        sess['user_id'] = cs_id
        sess['role'] = 'unit_manager'
        sess['username'] = mgr_cs_user
        sess['department'] = 'قسم علوم الحاسب'

    # CS Manager cannot view Civil Eng Report -> 403
    res = client.get(f'/api/reports/{report_eng_id}')
    assert res.status_code == 403

    # CS Manager cannot view Civil Eng Thesis -> 403
    res = client.get(f'/api/theses/{thesis_eng_id}')
    assert res.status_code == 403

    # CS Manager cannot view users of Civil Eng when querying user details
    res = client.get(f'/api/admin/users/{eng_id}')
    assert res.status_code == 403


def test_thesis_weighted_aggregation_math():
    """Verify that multi-part thesis overall plagiarism uses weighted analyzable words, not arithmetic average."""
    # Part 1: 1000 words, 500 copied (50%)
    # Part 2: 9000 words, 100 copied (1.11%)
    # Arithmetic average: (50 + 1.11) / 2 = 25.55%
    # Weighted average: (500 + 100) / (1000 + 9000) = 600 / 10000 = 6.0%

    thesis_id, _ = thesis_repo.create_thesis(
        title="أطروحة حساب النسبة الموزونة",
        author="الباحث التجريبي",
        department="قسم الإحصاء"
    )

    rep1_id = f"p1_rep_{uuid.uuid4().hex[:6]}"
    rep2_id = f"p2_rep_{uuid.uuid4().hex[:6]}"

    report_repo.save_report(
        report_id=rep1_id,
        title="الفصل الأول",
        overall_pct=50.0,
        copied_pct=50.0,
        para_pct=0.0,
        report_dict={'total_words': 1000, 'copied_words': 500, 'paraphrased_words': 0, 'cited_words': 0, 'problematic_words': 500, 'segments': []},
        category="قسم الإحصاء",
        author="الباحث التجريبي"
    )

    report_repo.save_report(
        report_id=rep2_id,
        title="الفصل الثاني",
        overall_pct=1.11,
        copied_pct=1.11,
        para_pct=0.0,
        report_dict={'total_words': 9000, 'copied_words': 100, 'paraphrased_words': 0, 'cited_words': 0, 'problematic_words': 100, 'segments': []},
        category="قسم الإحصاء",
        author="الباحث التجريبي"
    )

    with get_db_session() as session:
        # Part 1
        p1 = ThesisPart(
            thesis_id=thesis_id,
            part_title="الفصل الأول",
            sort_order=1,
            original_filename="p1.docx",
            stored_filename="stored_p1.docx",
            file_path="p1.docx",
            scan_status="completed",
            report_id=rep1_id,
            total_words=1000,
            copied_words=500,
            para_words=0,
            cited_words=0,
            problematic_words=500,
            similarity_pct=50.0,
            copied_pct=50.0,
            para_pct=0.0
        )
        # Part 2
        p2 = ThesisPart(
            thesis_id=thesis_id,
            part_title="الفصل الثاني",
            sort_order=2,
            original_filename="p2.docx",
            stored_filename="stored_p2.docx",
            file_path="p2.docx",
            scan_status="completed",
            report_id=rep2_id,
            total_words=9000,
            copied_words=100,
            para_words=0,
            cited_words=0,
            problematic_words=100,
            similarity_pct=1.11,
            copied_pct=1.11,
            para_pct=0.0
        )
        session.add(p1)
        session.add(p2)
        session.commit()

    ok, combined_report, msg = thesis_service.generate_combined_thesis_report(thesis_id)
    assert ok is True
    assert combined_report is not None

    # Total words = 10,000, matched = 600 -> overall_pct = 6.0% (NOT 25.55%)
    assert combined_report['total_words'] == 10000
    assert combined_report['copied_words'] == 600
    assert abs(combined_report['overall_pct'] - 6.0) < 0.1
    assert abs(combined_report['overall_pct'] - 25.55) > 10.0
