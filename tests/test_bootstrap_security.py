# -*- coding: utf-8 -*-
"""
حزمة اختبارات الأمان الشاملة للتهيئة الأولى لمدير النظام (Bootstrap Security & Offline QR Recovery Tests):
1. قاعدة بيانات نظيفة + اتصال محلي (Localhost: 127.0.0.1, ::1) -> الإعداد مسموح.
2. قاعدة بيانات نظيفة + اتصال شبكة محلية عن بعد (Remote LAN: 192.168.x.x, 10.x.x.x) -> الإعداد محظور ويعرض رسالة الانتظار.
3. محاولة انتحال العنوان عبر الترويسات (X-Forwarded-For: 127.0.0.1) من عميل شبكة -> الرفض الصارم (Denied).
4. إنشاء حساب مدير النظام الأول بنجاح مع تطبيق سياسة كلمات المرور وتوليد بطاقة الاسترداد.
5. محاولة ثانية لإجراء التهيئة الأولى -> الرفض الصارم (Denied).
6. محاولات متزامنة في نفس اللحظة (Concurrent Submissions) -> حساب واحد فقط يُنشأ بأمان.
7. إعادة تشغيل التطبيق / استمرارية القفل في قاعدة البيانات -> التهيئة مغلقة دائماً.
8. مسح كوكيز المتصفح / تغيير المتصفح بعد الإعداد -> التهيئة تظل مغلقة دائماً وتظهر شاشة الدخول العادية.
9. وصول عميل الشبكة LAN بعد اكتمال الإعداد -> ظهور شاشة تسجيل الدخول العادية دون أي بيانات إعداد.
10. مسار التهيئة لا يقبل أي أدوار مخصصة أو مدخلة من المستخدم (الدور إلزامي system_admin).
11. التحقق الكامل من دورة الاسترداد: إنشاء المدير الأول -> استخراج QR -> نسيان كلمة المرور -> استرداد الحساب وتعيين كلمة مرور جديدة بنجاح.
"""

import os
import io
import json
import base64
import threading
import pytest
from unittest.mock import patch

from app import create_app
from app.repositories.base_repo import get_session, init_database
from app.models.schema import User, SystemSecurityState, AccountRecoveryCredential
from app.repositories import user_repo
from app.services import recovery_service
from app.errors.error_codes import ErrorCode


@pytest.fixture(autouse=True)
def clean_db_state():
    """تفريغ الجداول لضمان بيئة نظيفة تماماً قبل كل اختبار."""
    with get_session() as session:
        session.query(AccountRecoveryCredential).delete()
        session.query(SystemSecurityState).delete()
        session.query(User).delete()
    user_repo.reopen_bootstrap_for_recovery()
    yield
    with get_session() as session:
        session.query(AccountRecoveryCredential).delete()
        session.query(SystemSecurityState).delete()
        session.query(User).delete()


@pytest.fixture
def app_instance():
    app = create_app()
    app.config['TESTING'] = True
    app.config['ENFORCE_CSRF_IN_TESTS'] = False
    with app.app_context():
        init_database()
        yield app


@pytest.fixture
def client(app_instance):
    return app_instance.test_client()


# ─── 1. Clean DB + Localhost -> Setup Allowed ─────────────────────────────
def test_clean_db_localhost_allowed(client):
    """التحقق من أن الخادم المحلي في قاعدة بيانات نظيفة يحصل على إذن التهيئة."""
    resp = client.get('/api/auth/status', environ_base={'REMOTE_ADDR': '127.0.0.1'})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['needs_first_time_setup'] is True
    assert data['setup_required'] is True
    assert data['is_localhost'] is True
    assert data['setup_pending'] is False
    assert data['bootstrap_allowed'] is True

    # IPv6 localhost check
    resp_v6 = client.get('/api/auth/status', environ_base={'REMOTE_ADDR': '::1'})
    assert resp_v6.status_code == 200
    assert resp_v6.get_json()['needs_first_time_setup'] is True


# ─── 2. Clean DB + Remote LAN -> Setup Denied (Pending State) ──────────────
def test_clean_db_remote_lan_denied(client):
    """التحقق من أن عملاء الشبكة عن بعد يُحظر وصولهم لنموذج الإعداد ويستلمون رسالة الانتظار."""
    resp = client.get('/api/auth/status', environ_base={'REMOTE_ADDR': '192.168.1.100'})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['needs_first_time_setup'] is False
    assert data['setup_required'] is True
    assert data['is_localhost'] is False
    assert data['setup_pending'] is True
    assert data['bootstrap_allowed'] is False
    assert 'لم يتم الانتهاء من إعداد النظام' in data['pending_message']

    # محاولة إرسال استمارة الإعداد من IP الشبكة مباشرة
    setup_resp = client.post(
        '/api/auth/setup_first_admin',
        json={
            'full_name': 'مدير متسلل',
            'username': 'remote_admin',
            'password': 'Secure#Password2026',
            'recovery_pin': '654321'
        },
        environ_base={'REMOTE_ADDR': '192.168.1.100'}
    )
    assert setup_resp.status_code == 403
    setup_data = setup_resp.get_json()
    assert setup_data['success'] is False
    assert setup_data['error_code'] == ErrorCode.FORBIDDEN_ORIGIN
    assert setup_data['status'] == 'SYSTEM_SETUP_PENDING'


# ─── 3. Spoofed Headers Defense (X-Forwarded-For / X-Real-IP) ─────────────
def test_spoofed_headers_denied(client):
    """التحقق من عدم الثقة في ترويسات الوكيل المزيفة ورفض محاولات الاحتيال."""
    # عميل LAN يرسل ترويسة تفيد بأنه localhost
    setup_resp = client.post(
        '/api/auth/setup_first_admin',
        headers={
            'X-Forwarded-For': '127.0.0.1',
            'X-Real-IP': '127.0.0.1',
            'Forwarded': 'for=127.0.0.1;proto=http'
        },
        json={
            'full_name': 'مهاجم منتحل',
            'username': 'spoofed_admin',
            'password': 'Secure#Password2026',
            'recovery_pin': '654321'
        },
        environ_base={'REMOTE_ADDR': '10.0.4.25'}
    )
    assert setup_resp.status_code == 403
    data = setup_resp.get_json()
    assert data['success'] is False
    assert data['error_code'] == ErrorCode.FORBIDDEN_ORIGIN


# ─── 4. First Sysadmin Creation with Offline Recovery Enrollment ──────────
def test_first_sysadmin_creation_success(client):
    """التحقق من إنشاء أول مدير نظام بنجاح وتوليد بطاقة استرداد الحساب الفورية."""
    setup_resp = client.post(
        '/api/auth/setup_first_admin',
        json={
            'full_name': 'د. حسام الدين مدير النظام',
            'username': 'main_sysadmin',
            'password': 'Super#SecureAdmin2026!',
            'recovery_pin': '987654'
        },
        environ_base={'REMOTE_ADDR': '127.0.0.1'}
    )
    assert setup_resp.status_code == 200
    data = setup_resp.get_json()
    assert data['success'] is True
    assert data['user']['username'] == 'main_sysadmin'
    assert data['user']['role'] == 'system_admin'

    # التحقق من بيانات بطاقة الاسترداد الفورية
    card = data['recovery_card']
    assert card is not None
    assert card['username'] == 'main_sysadmin'
    assert card['credential_id'].startswith('RC-')
    assert card['qr_image_data_url'].startswith('data:image/png;base64,')
    assert len(card['manual_recovery_code'].replace('-', '')) == 64

    # التحقق من قاعدة البيانات
    with get_session() as session:
        admin_user = session.query(User).filter(User.username == 'main_sysadmin').first()
        assert admin_user is not None
        assert admin_user.role == 'system_admin'

        state = session.query(SystemSecurityState).filter(SystemSecurityState.key == 'bootstrap_completed').first()
        assert state is not None
        assert state.value == '1'

        rec_cred = session.query(AccountRecoveryCredential).filter(AccountRecoveryCredential.user_id == admin_user.id).first()
        assert rec_cred is not None
        assert rec_cred.status == 'active'
        assert rec_cred.secret_verifier.startswith('$argon2id$')
        assert rec_cred.pin_verifier.startswith('$argon2id$')


# ─── 5. Second Bootstrap Attempt Denied ────────────────────────────────────
def test_second_bootstrap_attempt_denied(client):
    """التحقق من رفض أي محاولة لاحقة لإنشاء مدير أول بعد اكتمال التهيئة."""
    # الإعداد الأول
    client.post(
        '/api/auth/setup_first_admin',
        json={
            'full_name': 'المدير الأول الشرعي',
            'username': 'first_admin',
            'password': 'First#AdminPass2026',
            'recovery_pin': '123456'
        },
        environ_base={'REMOTE_ADDR': '127.0.0.1'}
    )

    # المحاولة الثانية
    second_resp = client.post(
        '/api/auth/setup_first_admin',
        json={
            'full_name': 'مدير ثان متطفل',
            'username': 'second_admin',
            'password': 'Second#AdminPass2026',
            'recovery_pin': '654321'
        },
        environ_base={'REMOTE_ADDR': '127.0.0.1'}
    )
    assert second_resp.status_code == 400
    data = second_resp.get_json()
    assert data['success'] is False
    assert data['error_code'] == ErrorCode.FIRST_ADMIN_ALREADY_EXISTS


# ─── 6. Concurrent Bootstrap Submissions Race Condition ────────────────────
def test_concurrent_bootstrap_submissions_atomic(app_instance):
    """التحقق من أن الطلبات المتزامنة في نفس اللحظة تنشئ حساباً واحداً فقط بأمان."""
    results = []

    def try_create(idx):
        with app_instance.test_client() as c:
            resp = c.post(
                '/api/auth/setup_first_admin',
                json={
                    'full_name': f'مدير متزامن {idx}',
                    'username': f'admin_concurrent_{idx}',
                    'password': f'Pass#{idx}SecureAdmin2026!',
                    'recovery_pin': f'12345{idx}'
                },
                environ_base={'REMOTE_ADDR': '127.0.0.1'}
            )
            results.append(resp.status_code)

    threads = [threading.Thread(target=try_create, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # طلب واحد فقط يجب أن ينجح بـ 200 والباقي يفشل بـ 400
    success_count = results.count(200)
    fail_count = results.count(400)
    assert success_count == 1
    assert fail_count == 4

    with get_session() as session:
        assert session.query(User).count() == 1


# ─── 7. Bootstrap Remains Closed Across App Sessions ───────────────────────
def test_bootstrap_remains_closed_persistently(client):
    """التحقق من بقاء مسار التهيئة مغلقاً عبر إعادة التشغيل وجلسات العمل الجديدة."""
    user_repo.create_initial_admin('perm_admin', 'Perm#Admin2026Pass!', 'المدير الدائم')

    resp = client.get('/api/auth/status', environ_base={'REMOTE_ADDR': '127.0.0.1'})
    data = resp.get_json()
    assert data['needs_first_time_setup'] is False
    assert data['setup_required'] is False
    assert data['bootstrap_allowed'] is False


# ─── 8. Browser Cookies Deleted -> Setup Remains Closed ────────────────────
def test_cleared_cookies_shows_login_not_setup(app_instance):
    """التحقق من أن مسح الكوكيز لا يعيد فتح استمارة التهيئة الأولى."""
    user_repo.create_initial_admin('cookie_admin', 'Cookie#AdminPass2026', 'مدير الكوكيز')

    # عميل جديد تماماً بدون أي جلسات أو كوكيز سابقة
    fresh_client = app_instance.test_client()
    status_resp = fresh_client.get('/api/auth/status', environ_base={'REMOTE_ADDR': '127.0.0.1'})
    assert status_resp.get_json()['needs_first_time_setup'] is False
    assert status_resp.get_json()['setup_required'] is False

    # تسجيل الدخول متاح ويعمل بنجاح
    login_resp = fresh_client.post(
        '/api/auth/login',
        json={'username': 'cookie_admin', 'password': 'Cookie#AdminPass2026'},
        environ_base={'REMOTE_ADDR': '127.0.0.1'}
    )
    assert login_resp.status_code == 200
    assert login_resp.get_json()['success'] is True


# ─── 9. Remote Client After Setup -> Normal Login Page ─────────────────────
def test_remote_client_after_setup_sees_normal_login(client):
    """التحقق من أن عملاء الشبكة بعد التهيئة يدخلون لشاشة تسجيل الدخول العادية."""
    user_repo.create_initial_admin('lan_ready_admin', 'LanReady#Pass2026!', 'مدير الشبكة')

    resp = client.get('/api/auth/status', environ_base={'REMOTE_ADDR': '192.168.1.50'})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['needs_first_time_setup'] is False
    assert data['setup_required'] is False
    assert data['setup_pending'] is False
    assert data['bootstrap_allowed'] is False


# ─── 10. Bootstrap Route Cannot Assign Arbitrary Roles ─────────────────────
def test_bootstrap_role_is_strictly_system_admin(client):
    """التحقق من أن مسار التهيئة لا يقبل تعيين أي دور مخصص سوى system_admin."""
    setup_resp = client.post(
        '/api/auth/setup_first_admin',
        json={
            'full_name': 'مدير تجريبي',
            'username': 'role_check_admin',
            'password': 'Role#CheckPass2026!',
            'role': 'reviewer',  # محاولة تمرير دور مختلف
            'recovery_pin': '888999'
        },
        environ_base={'REMOTE_ADDR': '127.0.0.1'}
    )
    assert setup_resp.status_code == 200

    with get_session() as session:
        u = session.query(User).filter(User.username == 'role_check_admin').first()
        assert u.role == 'system_admin'


# ─── 11. Complete First-Run Offline QR Recovery Flow ───────────────────────
def test_first_admin_full_offline_recovery_flow(client):
    """
    التحقق من دورة استرداد الحساب الكاملة للمدير الأول:
    1. إنشاء المدير الأول وتوليد رمز QR والرمز اليدوي.
    2. استخراج بيانات QR من الصورة وتفكيكها محلياً.
    3. تسجيل الخروج وطلب استرداد كلمة المرور باستخدام QR ورمز PIN.
    4. الحصول على رمز إعادة التعيين لمرة واحدة وتحديث كلمة المرور.
    5. التحقق من فشل كلمة المرور القديمة ونجاح كلمة المرور الجديدة.
    """
    # 1. إنشاء أول مدير
    setup_resp = client.post(
        '/api/auth/setup_first_admin',
        json={
            'full_name': 'العميد د. أحمد الشافعي',
            'username': 'dean_ahmed',
            'password': 'Initial#DeanPass2026',
            'recovery_pin': '741852'
        },
        environ_base={'REMOTE_ADDR': '127.0.0.1'}
    )
    assert setup_resp.status_code == 200
    card = setup_resp.get_json()['recovery_card']
    assert card is not None
    qr_data_url = card['qr_image_data_url']
    manual_code = card['manual_recovery_code']
    cred_id = card['credential_id']

    # فك تشفير صورة QR
    b64_str = qr_data_url.split(',', 1)[1]
    img_bytes = base64.b64decode(b64_str)
    dec_ok, payload, dec_msg = recovery_service.decode_qr_from_bytes(img_bytes)
    assert dec_ok is True
    assert payload['account_public_id'] == 'dean_ahmed'
    raw_secret = payload['secret']

    # 2. فحص محاولة الاسترداد برمز PIN خاطئ -> فشل
    bad_pin_resp = client.post(
        '/api/recovery/verify_and_authorize',
        json={
            'username': 'dean_ahmed',
            'secret': raw_secret,
            'credential_id': cred_id,
            'pin': '000000'
        }
    )
    assert bad_pin_resp.status_code == 400

    # 3. محاولة الاسترداد بالبيانات الصحيحة ورمز PIN الصحيح -> نجاح
    auth_resp = client.post(
        '/api/recovery/verify_and_authorize',
        json={
            'username': 'dean_ahmed',
            'secret': raw_secret,
            'credential_id': cred_id,
            'pin': '741852'
        }
    )
    assert auth_resp.status_code == 200
    auth_data = auth_resp.get_json()
    assert auth_data['success'] is True
    reset_token = auth_data['reset_token']

    # 4. تعيين كلمة مرور جديدة
    reset_resp = client.post(
        '/api/recovery/complete_reset',
        json={
            'reset_token': reset_token,
            'new_password': 'BrandNew#DeanPass2026!',
            'confirm_password': 'BrandNew#DeanPass2026!'
        }
    )
    assert reset_resp.status_code == 200
    assert reset_resp.get_json()['success'] is True

    # 5. محاولة استخدام رمز التعيين مرة ثانية -> مرفوض
    reuse_resp = client.post(
        '/api/recovery/complete_reset',
        json={
            'reset_token': reset_token,
            'new_password': 'BrandNew#DeanPass2026!',
            'confirm_password': 'BrandNew#DeanPass2026!'
        }
    )
    assert reuse_resp.status_code == 400

    # 6. تسجيل الدخول بكلمة المرور القديمة -> فشل
    old_login = client.post(
        '/api/auth/login',
        json={'username': 'dean_ahmed', 'password': 'Initial#DeanPass2026'}
    )
    assert old_login.status_code == 401 or old_login.get_json().get('success') is False

    # 7. تسجيل الدخول بكلمة المرور الجديدة -> نجاح تام
    new_login = client.post(
        '/api/auth/login',
        json={'username': 'dean_ahmed', 'password': 'BrandNew#DeanPass2026!'}
    )
    assert new_login.status_code == 200
    assert new_login.get_json()['success'] is True
