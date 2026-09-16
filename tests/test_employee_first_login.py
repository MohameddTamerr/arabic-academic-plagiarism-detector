import uuid

import pytest

from app import create_app
from app.models.schema import User
from app.repositories import user_repo
from app.repositories.base_repo import get_session


@pytest.fixture
def client():
    app = create_app()
    app.config.update(TESTING=True, STRICT_AUTH=True)
    return app.test_client()


def _admin_session(client):
    username = f"onboard_admin_{uuid.uuid4().hex[:8]}"
    with get_session() as session:
        admin = User(
            username=username,
            password_hash=user_repo.hash_password('Admin#Password2026Secure'),
            full_name='Onboarding Admin',
            role='system_admin',
            is_active=1,
            session_version=1,
        )
        session.add(admin)
        session.flush()
        admin_id = admin.id
    with client.session_transaction() as flask_session:
        flask_session.update(
            user_id=admin_id,
            username=username,
            role='system_admin',
            session_version=1,
        )


def test_employee_temporary_password_forces_password_and_qr_setup(client):
    _admin_session(client)
    username = f"temp_employee_{uuid.uuid4().hex[:8]}"
    temporary_password = '2468'

    created = client.post('/api/admin/users', json={
        'username': username,
        'full_name': 'Temporary Employee',
        'role': 'employee',
        'password': temporary_password,
    })
    assert created.status_code == 201, created.get_json()

    created_user = user_repo.get_user_by_username(username)
    assert created_user['must_change_password'] == 1
    assert created_user['must_enroll_recovery'] == 1
    assert created_user['recovery_configured'] is False

    with client.session_transaction() as flask_session:
        flask_session.clear()

    login = client.post('/api/auth/login', json={
        'username': username,
        'password': temporary_password,
    })
    assert login.status_code == 200
    login_user = login.get_json()['user']
    assert login_user['must_change_password'] == 1
    assert login_user['must_enroll_recovery'] == 1

    blocked = client.get('/api/users')
    assert blocked.status_code == 428
    assert blocked.get_json()['error']['code'] == 'ACCOUNT_SETUP_REQUIRED'

    permanent_password = 'Falcon#Archive2026Secure'
    completed = client.post('/api/auth/complete_first_login', json={
        'new_password': permanent_password,
        'confirm_password': permanent_password,
        'recovery_pin': '741852',
    })
    assert completed.status_code == 200, completed.get_json()
    completed_data = completed.get_json()
    assert completed_data['recovery_card']['qr_image_data_url'].startswith('data:image/png;base64,')
    assert completed_data['recovery_card']['manual_recovery_code']

    # The normal application remains locked until the employee confirms that
    # the one-time recovery card was saved.
    assert client.get('/api/users').status_code == 428

    acknowledged = client.post('/api/auth/acknowledge_recovery_card', json={'acknowledged': True})
    assert acknowledged.status_code == 200
    final_user = acknowledged.get_json()['user']
    assert final_user['must_change_password'] == 0
    assert final_user['must_enroll_recovery'] == 0
    assert final_user['recovery_configured'] is True

    client.post('/api/auth/logout', json={'username': username})
    assert client.post('/api/auth/login', json={
        'username': username,
        'password': temporary_password,
    }).status_code == 401
    relogin = client.post('/api/auth/login', json={
        'username': username,
        'password': permanent_password,
    })
    assert relogin.status_code == 200
    assert relogin.get_json()['user']['must_change_password'] == 0
    assert relogin.get_json()['user']['must_enroll_recovery'] == 0


def test_temporary_password_still_has_a_minimum_length(client):
    _admin_session(client)
    response = client.post('/api/admin/users', json={
        'username': f"short_temp_{uuid.uuid4().hex[:8]}",
        'full_name': 'Short Password Employee',
        'role': 'employee',
        'password': '123',
    })
    assert response.status_code == 400
    assert '4' in response.get_json()['error']
