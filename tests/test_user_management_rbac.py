"""
Tests for Admin User Management & RBAC Protection.
100% Offline & Local Operation.
"""
import uuid
import pytest
from app import create_app
from app.models.schema import User
from app.repositories.base_repo import get_session as get_db_session
from app.security.permissions import Role, Permission, role_has_permission


@pytest.fixture
def app_instance():
    app = create_app()
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app_instance):
    return app_instance.test_client()


def test_rbac_matrix_definitions():
    """Verify role permissions hierarchy and separation."""
    # Employee has operational upload and scan, but NO review permissions
    assert role_has_permission(Role.EMPLOYEE, Permission.RESEARCH_UPLOAD) is True
    assert role_has_permission(Role.EMPLOYEE, Permission.SCAN_START) is True
    assert role_has_permission(Role.EMPLOYEE, Permission.REVIEW_PRELIMINARY) is False
    assert role_has_permission(Role.EMPLOYEE, Permission.REVIEW_REJECT) is False
    assert role_has_permission(Role.EMPLOYEE, Permission.REVIEW_FINAL) is False
    assert role_has_permission(Role.EMPLOYEE, Permission.USERS_MANAGE) is False

    # Reviewer has preliminary review and reject, but NO final review or user mgmt
    assert role_has_permission(Role.REVIEWER, Permission.REVIEW_PRELIMINARY) is True
    assert role_has_permission(Role.REVIEWER, Permission.REVIEW_REJECT) is True
    assert role_has_permission(Role.REVIEWER, Permission.REVIEW_FINAL) is False
    assert role_has_permission(Role.REVIEWER, Permission.USERS_MANAGE) is False

    # Senior Reviewer has final review
    assert role_has_permission(Role.SENIOR_REVIEWER, Permission.REVIEW_FINAL) is True
    assert role_has_permission(Role.SENIOR_REVIEWER, Permission.REVIEW_PRELIMINARY) is True

    # System Admin has user management & system settings
    assert role_has_permission(Role.SYSTEM_ADMIN, Permission.USERS_MANAGE) is True
    assert role_has_permission(Role.SYSTEM_ADMIN, Permission.USER_PASSWORD_ADMIN_RESET) is True
    assert role_has_permission(Role.SYSTEM_ADMIN, Permission.SETTINGS_MANAGE) is True


def test_user_management_stats_and_listing(client):
    """Test fetching user management statistics and paginated user list."""
    with get_db_session() as session:
        admin = session.query(User).filter(User.role.in_(['admin', 'system_admin'])).first()
        if not admin:
            admin = User(
                username=f"admin_{uuid.uuid4().hex[:6]}",
                password_hash="fake_hash",
                full_name="Test Admin",
                role="system_admin",
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

    # Stats
    res = client.get('/api/admin/users/stats')
    assert res.status_code == 200
    data = res.get_json()
    assert 'total_users' in data
    assert data['total_users'] >= 1

    # List
    res = client.get('/api/admin/users?page=1&page_size=10')
    assert res.status_code == 200
    data = res.get_json()
    assert 'items' in data or 'users' in data
    users_list = data.get('items') or data.get('users')
    assert isinstance(users_list, list)
    assert len(users_list) >= 1


def test_user_creation_and_escalation_guard(client):
    """Test user creation by admin and privilege escalation block for non-admin."""
    unique_user = f"emp_test_{uuid.uuid4().hex[:6]}"

    with get_db_session() as session:
        admin = session.query(User).filter(User.role.in_(['admin', 'system_admin'])).first()
        if not admin:
            admin = User(
                username=f"admin_{uuid.uuid4().hex[:6]}",
                password_hash="fake_hash",
                full_name="المشرف العام",
                role="system_admin",
                is_active=1
            )
            session.add(admin)
            session.commit()
        admin_id = admin.id
        admin_role = admin.role
        admin_user = admin.username

        # Create a test employee user
        emp = User(
            username=f"emp_actor_{uuid.uuid4().hex[:4]}",
            password_hash="fake_hash",
            full_name="موظف تجريبي",
            role="employee",
            is_active=1
        )
        session.add(emp)
        session.commit()
        emp_id = emp.id

    # 1. Non-admin attempt -> 403 Forbidden
    with client.session_transaction() as sess:
        sess['user_id'] = emp_id
        sess['role'] = 'employee'
        sess['username'] = 'actor_employee'

    res = client.post('/api/admin/users', json={
        'username': unique_user,
        'full_name': 'سالم راشد',
        'role': 'employee',
        'password': 'StrongAcademic#2026!'
    })
    assert res.status_code == 403

    # 2. Admin creation -> 201 Success
    with client.session_transaction() as sess:
        sess['user_id'] = admin_id
        sess['role'] = admin_role
        sess['username'] = admin_user

    res = client.post('/api/admin/users', json={
        'username': unique_user,
        'full_name': 'سالم راشد',
        'role': 'employee',
        'department': 'قسم الفحص الأكاديمي',
        'password': 'StrongAcademic#2026!'
    })
    assert res.status_code == 201
    data = res.get_json()
    assert data['success'] is True
    created_id = data['user_id']

    # 3. Fetch created user
    res = client.get(f'/api/admin/users/{created_id}')
    assert res.status_code == 200
    u_data = res.get_json()
    assert u_data['username'] == unique_user
    assert u_data['role'] == 'employee'

    # 4. Toggle active status
    res = client.post(f'/api/admin/users/{created_id}/toggle_status', json={'is_active': False})
    assert res.status_code == 200
    assert res.get_json()['success'] is True

    # 5. Reset password
    res = client.post(f'/api/admin/users/{created_id}/reset_password', json={
        'new_password': 'NewSecurePassword456!',
        'must_change_password': 1
    })
    assert res.status_code == 200
    assert res.get_json()['success'] is True
