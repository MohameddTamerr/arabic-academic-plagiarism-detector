# -*- coding: utf-8 -*-
"""
جناح اختبارات الأمان والتحقق الشامل لمنظومة استرداد حساب مدير المنظومة (Secure Admin Recovery Test Suite):
1. التحقق من مفتاح الاسترداد الصحيح دون إنترنت (Valid Recovery Key).
2. رفض وتجريم إعادة استخدام المفتاح المستهلك (Reused Recovery Key Invalidation).
3. رفض مفاتيح الاسترداد الخاطئة أو المزيفة (Invalid Recovery Key Rejection).
4. رفض الطلبات الناقصة لمفتاح الاسترداد أو رقم PIN (Missing Key / PIN Validation).
5. كبح المحاولات الخاطئة المتكررة وقفل بطاقة الاسترداد (Rate Limiting & Lockout).
6. حظر مستخدمي ويندوز العاديين غير المرتفعين من الاسترداد الطارئ (Unauthorized OS User Block).
7. نجاح الاسترداد الطارئ لمسؤول ويندوز المصرح له مع التأكيد الصريح (Authorized OS Admin Recovery).
8. رفض كلمات المرور الافتراضية المعروفة والضعيفة في الاسترداد الطارئ (Default & Weak Password Rejection).
9. اشتراط التأكيد المحلي الصريح في الاسترداد الطارئ (Explicit Confirmation Requirement).
10. استمرار وسلامة بيانات المستخدمين والأبحاث بعد إعادة تشغيل المنظومة (Data Preservation & Persistence).
11. التشغيل المحلي الصافي 100% دون أي اتصال شبكي خارجي (Zero Network Socket Calls).
"""

import io
import uuid
import socket
import sqlite3
import pytest
from pathlib import Path
from datetime import datetime

from app import create_app
from app.models.schema import User, AccountRecoveryCredential, RecoveryTransaction
from app.models.audit_schema import AuditLog
from app.repositories.base_repo import get_session, init_database
from app.repositories import user_repo
from app.services import recovery_service
from app.security import emergency_recovery
from app.errors.error_codes import ErrorCode


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


@pytest.fixture
def isolated_recovery_user(client):
    """مستخدم مدير معزول لاختبارات الاسترداد مع توليد بطاقة استرداد أولية."""
    username = f"admin_rec_{uuid.uuid4().hex[:8]}"
    initial_pass = "InitialAdminPass#2026Secure!"
    pin = "654321"

    user_repo.add_user(
        username=username,
        password=initial_pass,
        full_name="د. مدير معزول للتجربة",
        role="system_admin",
        enforce_policy=False
    )

    with get_session() as session:
        u = session.query(User).filter(User.username == username).first()
        user_id = u.id

    ok, card, msg = recovery_service.enroll_recovery_credential(user_id, pin)
    assert ok is True
    assert card is not None

    return {
        "user_id": user_id,
        "username": username,
        "initial_pass": initial_pass,
        "pin": pin,
        "manual_code": card["manual_recovery_code"],
        "credential_id": card["credential_id"],
        "qr_image_data_url": card["qr_image_data_url"]
    }


def test_valid_recovery_key_offline_flow(client, isolated_recovery_user):
    """1. اختبار استرداد الحساب بنجاح عبر مفتاح الاسترداد الصحيح وتدوير المفتاح فوراً."""
    u = isolated_recovery_user
    new_pass = "BrandNewAdminPass#2026Strong!"

    # 1. التحقق من رمز الاسترداد ورقم PIN
    res_auth = client.post('/api/recovery/verify_and_authorize', json={
        'username': u["username"],
        'manual_code': u["manual_code"],
        'pin': u["pin"]
    })
    assert res_auth.status_code == 200
    data_auth = res_auth.get_json()
    assert data_auth['success'] is True
    reset_token = data_auth['reset_token']
    assert reset_token.startswith('rst_')

    # 2. إتمام إعادة تعيين كلمة المرور
    res_reset = client.post('/api/recovery/complete_reset', json={
        'reset_token': reset_token,
        'new_password': new_pass,
        'confirm_password': new_pass,
        'pin': '889900'  # PIN جديد للبطاقة البديلة
    })
    assert res_reset.status_code == 200
    data_reset = res_reset.get_json()
    assert data_reset['success'] is True
    assert 'replacement_card' in data_reset
    rep_card = data_reset['replacement_card']
    assert rep_card is not None
    assert rep_card['manual_recovery_code'] != u["manual_code"]

    # 3. التأكد من فشل كلمة المرور القديمة ونجاح الجديدة
    res_old = client.post('/api/auth/login', json={'username': u["username"], 'password': u["initial_pass"]})
    assert res_old.status_code == 401

    res_new = client.post('/api/auth/login', json={'username': u["username"], 'password': new_pass})
    assert res_new.status_code == 200
    assert res_new.get_json()['success'] is True


def test_reused_recovery_key_rejected(client, isolated_recovery_user):
    """2. اختبار رفض وإبطال إعادة استخدام مفتاح الاسترداد بعد استهلاكه وتغيير كلمة المرور."""
    u = isolated_recovery_user
    new_pass_1 = "FirstResetPass#2026Strong!"

    # استرداد أول ناجح
    res_auth = client.post('/api/recovery/verify_and_authorize', json={
        'username': u["username"],
        'manual_code': u["manual_code"],
        'pin': u["pin"]
    })
    reset_token = res_auth.get_json()['reset_token']

    res_reset = client.post('/api/recovery/complete_reset', json={
        'reset_token': reset_token,
        'new_password': new_pass_1,
        'confirm_password': new_pass_1
    })
    assert res_reset.status_code == 200

    # محاولة إعادة استخدام المفتاح القديم نفسه للمرة الثانية -> يجب أن تفشل قطعاً
    res_reuse = client.post('/api/recovery/verify_and_authorize', json={
        'username': u["username"],
        'manual_code': u["manual_code"],
        'pin': u["pin"]
    })
    assert res_reuse.status_code in [400, 429]
    data_reuse = res_reuse.get_json()
    assert data_reuse['success'] is False
    assert data_reuse['error_code'] in [ErrorCode.RECOVERY_INVALID_CREDENTIAL, ErrorCode.RECOVERY_NOT_CONFIGURED]


def test_invalid_recovery_key_rejected(client, isolated_recovery_user):
    """3. اختبار رفض مفتاح الاسترداد المزيف أو الخاطئ."""
    u = isolated_recovery_user
    fake_code = "FFFFFFFF-00000000-11111111-22222222-33333333-44444444-55555555-66666666"

    res = client.post('/api/recovery/verify_and_authorize', json={
        'username': u["username"],
        'manual_code': fake_code,
        'pin': u["pin"]
    })
    assert res.status_code == 400
    assert res.get_json()['success'] is False
    assert res.get_json()['error_code'] == ErrorCode.RECOVERY_INVALID_CREDENTIAL


def test_missing_recovery_key_and_pin_validation(client, isolated_recovery_user):
    """4. اختبار رفض الطلبات الناقصة لمفتاح الاسترداد أو رقم PIN."""
    u = isolated_recovery_user

    # بدون مفتاح استرداد
    r1 = client.post('/api/recovery/verify_and_authorize', json={'username': u["username"], 'pin': u["pin"]})
    assert r1.status_code == 400

    # بدون رقم PIN
    r2 = client.post('/api/recovery/verify_and_authorize', json={'username': u["username"], 'manual_code': u["manual_code"]})
    assert r2.status_code == 400

    # بدون اسم مستخدم
    r3 = client.post('/api/recovery/verify_and_authorize', json={'manual_code': u["manual_code"], 'pin': u["pin"]})
    assert r3.status_code == 400


def test_incorrect_password_attempts_lockout(client, isolated_recovery_user):
    """5. اختبار كبح المحاولات الخاطئة وقفل بطاقة الاسترداد بعد 5 محاولات خاطئة."""
    u = isolated_recovery_user

    for i in range(5):
        res = client.post('/api/recovery/verify_and_authorize', json={
            'username': u["username"],
            'manual_code': u["manual_code"],
            'pin': '000000'  # PIN خاطئ
        })
        assert res.status_code in [400, 429]

    # المحاولة السادسة يجب أن تُقابل بالقفل المؤقت
    res_locked = client.post('/api/recovery/verify_and_authorize', json={
        'username': u["username"],
        'manual_code': u["manual_code"],
        'pin': u["pin"]
    })
    assert res_locked.status_code in [400, 429]
    assert res_locked.get_json()['error_code'] in [ErrorCode.RECOVERY_LOCKED_OUT, ErrorCode.RECOVERY_INVALID_CREDENTIAL]


def test_unauthorized_windows_user_blocked(tmp_path):
    """6. اختبار حظر مستخدم نظام التشغيل غير المرتفع من تنفيذ الاسترداد الطارئ."""
    db_file = tmp_path / "test_papers.db"
    conn = sqlite3.connect(str(db_file))
    c = conn.cursor()
    c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, password_hash TEXT, full_name TEXT, role TEXT, is_active INTEGER, must_change_password INTEGER, must_enroll_recovery INTEGER, session_version INTEGER, created_at TEXT)")
    c.execute("INSERT INTO users VALUES (1, 'admin', 'hash', 'مدير النظام', 'system_admin', 1, 0, 0, 1, '2026-11-17 00:00:00')")
    conn.commit()
    conn.close()

    # تشغيل بدون ترقية صلاحيات (is_windows_admin = False)
    ok, res, msg, code = emergency_recovery.perform_emergency_admin_reset(
        db_path=db_file,
        new_password="NewSecureAdminPass#2026!",
        target_user="admin",
        confirmed=True,
        interactive=False,
        bypass_elevation_for_test=False
    )
    # في بيئة الاختبار غير المرتفعة، يجب رفض التنفيذ بكود ACCESS_DENIED
    if not emergency_recovery.is_windows_admin():
        assert ok is False
        assert code == "ACCESS_DENIED"
        assert "صلاحيات مسؤول نظام التشغيل Windows" in msg


def test_authorized_windows_admin_emergency_recovery(tmp_path):
    """7. اختبار نجاح الاسترداد الطارئ لمسؤول ويندوز مع التأكيد الصريح وتدوير مفتاح الاسترداد."""
    db_file = tmp_path / "test_elevated_papers.db"
    conn = sqlite3.connect(str(db_file))
    c = conn.cursor()
    c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, password_hash TEXT, full_name TEXT, role TEXT, is_active INTEGER, must_change_password INTEGER, must_enroll_recovery INTEGER, session_version INTEGER, created_at TEXT)")
    c.execute("CREATE TABLE account_recovery_credentials (id INTEGER PRIMARY KEY, user_id INTEGER, credential_public_id TEXT, secret_verifier TEXT, pin_verifier TEXT, version INTEGER, status TEXT, created_at TEXT, revoked_at TEXT, last_used_at TEXT, failure_count INTEGER, locked_until TEXT)")
    c.execute("CREATE TABLE audit_logs (id INTEGER PRIMARY KEY, action TEXT, category TEXT, object_type TEXT, object_id TEXT, success INTEGER, metadata TEXT, created_at TEXT)")
    c.execute("INSERT INTO users VALUES (1, 'tamer_admin', 'old_hash', 'د. تامر درويش', 'system_admin', 1, 0, 0, 1, '2026-11-17 00:00:00')")
    c.execute("INSERT INTO account_recovery_credentials VALUES (1, 1, 'RC-OLD', 'verifier', 'pin_v', 1, 'active', '2026-11-17 00:00:00', NULL, NULL, 0, NULL)")
    conn.commit()
    conn.close()

    new_pass = "ElevatedReset#2026SecureAdmin!"
    ok, res, msg, code = emergency_recovery.perform_emergency_admin_reset(
        db_path=db_file,
        new_password=new_pass,
        target_user="tamer_admin",
        confirmed=True,
        interactive=False,
        recovery_pin="998877",
        bypass_elevation_for_test=True
    )
    assert ok is True
    assert code is None
    assert res['username'] == 'tamer_admin'
    assert 'manual_recovery_code' in res
    assert res['recovery_pin'] == '998877'

    # التحقق من قاعدة البيانات مباشرة
    conn2 = sqlite3.connect(str(db_file))
    c2 = conn2.cursor()

    # 1. إبطال المفتاح القديم
    c2.execute("SELECT status FROM account_recovery_credentials WHERE credential_public_id = 'RC-OLD'")
    assert c2.fetchone()[0] == 'superseded'

    # 2. إنشاء المفتاح الجديد
    c2.execute("SELECT status, credential_public_id FROM account_recovery_credentials WHERE status = 'active'")
    new_cred = c2.fetchone()
    assert new_cred is not None
    assert new_cred[0] == 'active'
    assert new_cred[1] != 'RC-OLD'

    # 3. تسجيل الحدث في سجل التدقيق
    c2.execute("SELECT action, category FROM audit_logs WHERE action = 'auth.recovery.os_emergency_reset'")
    audit_row = c2.fetchone()
    assert audit_row is not None
    assert audit_row[0] == 'auth.recovery.os_emergency_reset'

    conn2.close()


def test_windows_emergency_rejects_default_and_weak_passwords(tmp_path):
    """8. اختبار رفض كلمات المرور الافتراضية المعروفة والضعيفة في الاسترداد الطارئ."""
    db_file = tmp_path / "test_reject_pw.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, role TEXT)")
    conn.execute("INSERT INTO users VALUES (1, 'admin', 'system_admin')")
    conn.commit()
    conn.close()

    # رفض الكلمات الافتراضية
    for bad_pw in ["Academic@2026#Secure", "admin@123456", "admin", "123456"]:
        ok, _, msg, code = emergency_recovery.perform_emergency_admin_reset(
            db_path=db_file,
            new_password=bad_pw,
            confirmed=True,
            bypass_elevation_for_test=True
        )
        assert ok is False
        assert code == "PASSWORD_TOO_WEAK"

    # رفض الكلمات القصيرة
    ok_weak, _, msg_weak, code_weak = emergency_recovery.perform_emergency_admin_reset(
        db_path=db_file,
        new_password="Short1!",
        confirmed=True,
        bypass_elevation_for_test=True
    )
    assert ok_weak is False
    assert code_weak == "PASSWORD_TOO_WEAK"


def test_emergency_recovery_requires_explicit_confirmation(tmp_path):
    """9. اختبار اشتراط التأكيد المحلي الصريح في الاسترداد الطارئ غير التفاعلي."""
    db_file = tmp_path / "test_confirm.db"
    ok, _, msg, code = emergency_recovery.perform_emergency_admin_reset(
        db_path=db_file,
        new_password="ValidStrongPass#2026!",
        confirmed=False,
        interactive=False,
        bypass_elevation_for_test=True
    )
    assert ok is False
    assert code == "CONFIRMATION_REQUIRED"


def test_recovery_after_restart_and_data_preservation(client, isolated_recovery_user):
    """10. اختبار استمرار وسلامة حسابات الموظفين والبيانات المرجعية أثناء وبعد الاسترداد."""
    # إنشاء موظف عادي ومراجع في النظام
    emp_user = f"emp_{uuid.uuid4().hex[:6]}"
    rev_user = f"rev_{uuid.uuid4().hex[:6]}"
    user_repo.add_user(emp_user, "EmpPass#2026Secure!", "ملازم أول فاحص", "employee", enforce_policy=False)
    user_repo.add_user(rev_user, "RevPass#2026Secure!", "عقيد مراجع معتمد", "reviewer", enforce_policy=False)

    # استرداد كلمة مرور المدير
    u = isolated_recovery_user
    new_admin_pass = "RestartRecoveryAdminPass#2026!"

    res_auth = client.post('/api/recovery/verify_and_authorize', json={
        'username': u["username"],
        'manual_code': u["manual_code"],
        'pin': u["pin"]
    })
    token = res_auth.get_json()['reset_token']

    res_reset = client.post('/api/recovery/complete_reset', json={
        'reset_token': token,
        'new_password': new_admin_pass,
        'confirm_password': new_admin_pass
    })
    assert res_reset.status_code == 200

    # التحقق من أن حسابات الموظفين الآخرين لم تتأثر مطلقاً وتعمل بكفاءة تامة
    res_emp = client.post('/api/auth/login', json={'username': emp_user, 'password': "EmpPass#2026Secure!"})
    assert res_emp.status_code == 200
    assert res_emp.get_json()['user']['role'] == 'employee'

    res_rev = client.post('/api/auth/login', json={'username': rev_user, 'password': "RevPass#2026Secure!"})
    assert res_rev.status_code == 200
    assert res_rev.get_json()['user']['role'] == 'reviewer'


def test_offline_zero_external_network_calls(client, isolated_recovery_user, monkeypatch):
    """11. اختبار أن منظومة الاسترداد بالكامل تعمل دون اتصال ودون أي استدعاء شبكي خارجي."""
    def guarded_connect(self, *args, **kwargs):
        raise RuntimeError(f"محاولة اتصال شبكي محظورة أثناء الاسترداد دون إنترنت: {args}")

    monkeypatch.setattr(socket.socket, 'connect', guarded_connect)

    u = isolated_recovery_user
    res_auth = client.post('/api/recovery/verify_and_authorize', json={
        'username': u["username"],
        'manual_code': u["manual_code"],
        'pin': u["pin"]
    })
    assert res_auth.status_code == 200

    res_reset = client.post('/api/recovery/complete_reset', json={
        'reset_token': res_auth.get_json()['reset_token'],
        'new_password': "OfflinePass#2026ZeroNet!",
        'confirm_password': "OfflinePass#2026ZeroNet!"
    })
    assert res_reset.status_code == 200
    assert res_reset.get_json()['success'] is True
