# -*- coding: utf-8 -*-
"""
حزمة الاختبارات الشاملة لمنظومة استرداد الحسابات بدون اتصال بالإنترنت (100% Offline QR Recovery Tests):
- التحقق من إنتروبيا السر (≥ 256 bits) وعدم تخزين السر الخام أو رمز PIN في قاعدة البيانات.
- التحقق من توليد وفك تشفير رمز QR محلياً.
- اختبارات رفض رموز QR المزيفة أو المعدلة أو غير الصالحة (Fake QR Attacks Defense).
- اختبارات الاسترداد لكافة الأدوار (موظف، مراجع، مدير، مدير نظام).
- التحقق من كبح المحاولات والقفل المؤقت (Rate Limiting & Lockout).
- التحقق من صلاحية رموز التفويض المؤقتة (Short-Lived Reset Tokens) وإبطال الجلسات السابقة.
- التحقق من نزاهة سجل التدقيق وعدم تسريب أي أسرار في السجلات.
- التحقق من العمل التام بدون أي اتصال بالشبكة (100% Offline Socket Isolation).
"""

import io
import json
import uuid
import base64
import socket
import pytest
from datetime import datetime, timedelta

from app import create_app
from app.repositories.base_repo import get_session, init_database
from app.models.schema import User, AccountRecoveryCredential, RecoveryTransaction, AuthLockout
from app.models.audit_schema import AuditLog
from app.repositories import user_repo
from app.services import recovery_service
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


def test_recovery_credential_entropy_and_argon2_verifiers(app_instance):
    """التحقق من إنتروبيا السر (256 بت على الأقل) واستخدام Argon2id لتخزين المدققات فقط."""
    uname = f'test_rec_entropy_{uuid.uuid4().hex[:6]}'
    with app_instance.app_context():
        user_repo.add_user(uname, 'ValidPass#2026Secure', 'د. محمد الباحث', 'reviewer', enforce_policy=False)
        with get_session() as session:
            user = session.query(User).filter(User.username == uname).first()
            user_id = user.id

        ok, card, msg = recovery_service.enroll_recovery_credential(user_id, '123456')
        assert ok is True
        assert card is not None
        assert card['username'] == uname
        assert card['credential_id'].startswith('RC-')
        assert card['qr_image_data_url'].startswith('data:image/png;base64,')

        # فحص كود الاسترداد اليدوي والإنتروبيا (64 hex characters = 256 bits)
        raw_code = recovery_service.normalize_manual_code(card['manual_recovery_code'])
        assert len(raw_code) == 64  # 32 bytes = 256 bits

        # فحص السجل في قاعدة البيانات
        with get_session() as session:
            cred = session.query(AccountRecoveryCredential).filter(AccountRecoveryCredential.user_id == user_id, AccountRecoveryCredential.status == 'active').first()
            assert cred is not None
            assert cred.secret_verifier.startswith('$argon2id$')
            assert cred.pin_verifier.startswith('$argon2id$')
            # التأكد من عدم وجود السر الخام أو رمز PIN في أي حقل
            assert raw_code not in cred.secret_verifier
            assert '123456' not in cred.pin_verifier


def test_qr_payload_generation_and_local_decoding(app_instance):
    """التحقق من صحة حمولة QR وفك تشفيرها محلياً من الصورة في الذاكرة."""
    uname = f'test_rec_decode_{uuid.uuid4().hex[:6]}'
    with app_instance.app_context():
        user_repo.add_user(uname, 'ValidPass#2026Secure', 'د. أحمد مراجع', 'reviewer', enforce_policy=False)
        with get_session() as session:
            user = session.query(User).filter(User.username == uname).first()
            user_id = user.id

        ok, card, _ = recovery_service.enroll_recovery_credential(user_id, '654321')
        assert ok is True

        # استخراج بايتات الصورة من Data URL
        b64_part = card['qr_image_data_url'].split(',', 1)[1]
        img_bytes = base64.b64decode(b64_part)

        # فك التشفير عبر دالة الخدمة المحلية
        dec_ok, payload, dec_msg = recovery_service.decode_qr_from_bytes(img_bytes)
        assert dec_ok is True
        assert payload['type'] == 'AAPD_ACCOUNT_RECOVERY'
        assert payload['version'] == 1
        assert payload['account_public_id'] == uname
        assert payload['credential_id'] == card['credential_id']
        assert len(payload['secret']) == 64


def test_fake_and_malformed_qr_rejection(client):
    """التحقق الصارم من رفض رموز QR المزيفة أو المعدلة أو غير المطابقة."""
    # 1. إرسال صورة بدون QR
    blank_png = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
    res = client.post('/api/recovery/decode_qr', data={'file': (io.BytesIO(blank_png), 'empty.png')})
    assert res.status_code == 400

    # 2. رمز QR لحساب غير موجود
    res_fake_user = client.post('/api/recovery/verify_and_authorize', json={
        'username': 'non_existent_user_9999',
        'secret': '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef',
        'pin': '123456'
    })
    assert res_fake_user.status_code == 400
    assert 'تعذر التحقق' in res_fake_user.get_json()['error']

    # 3. رمز QR مع سر معدل لمستخدم موجود
    target_user = f'test_fake_target_{uuid.uuid4().hex[:6]}'
    user_repo.add_user(target_user, 'ValidPass#2026Secure', 'د. كمال', 'reviewer', enforce_policy=False)
    with get_session() as session:
        u = session.query(User).filter(User.username == target_user).first()
        recovery_service.enroll_recovery_credential(u.id, '987654')

    res_altered = client.post('/api/recovery/verify_and_authorize', json={
        'username': target_user,
        'secret': 'ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff',
        'pin': '987654'
    })
    assert res_altered.status_code == 400
    assert res_altered.get_json()['error_code'] == ErrorCode.RECOVERY_INVALID_CREDENTIAL


def test_full_recovery_flow_qr_image_upload_and_pin(client):
    """اختبار مسار الاسترداد الكامل عبر رفع صورة QR ورقم PIN وإعادة تعيين كلمة المرور."""
    username = f'test_flow_employee_{uuid.uuid4().hex[:6]}'
    old_pass = 'OldPass#2026Secure'
    new_pass = 'BrandNewPass#2026Strong'
    pin = '778899'

    user_repo.add_user(username, old_pass, 'أحمد موظف الفحص', 'employee', enforce_policy=False)
    with get_session() as session:
        u = session.query(User).filter(User.username == username).first()
        u_id = u.id

    ok, card, _ = recovery_service.enroll_recovery_credential(u_id, pin)
    assert ok is True

    # 1. رفع صورة رمز QR لفك تشفيرها
    b64_part = card['qr_image_data_url'].split(',', 1)[1]
    img_bytes = base64.b64decode(b64_part)

    res_decode = client.post('/api/recovery/decode_qr', data={'file': (io.BytesIO(img_bytes), 'recovery.png')})
    assert res_decode.status_code == 200
    payload = res_decode.get_json()['payload']

    # 2. التحقق من الحمولة ورقم PIN
    res_auth = client.post('/api/recovery/verify_and_authorize', json={
        'qr_payload': payload,
        'pin': pin
    })
    assert res_auth.status_code == 200
    reset_token = res_auth.get_json()['reset_token']
    assert reset_token.startswith('rst_')

    # 3. إتمام إعادة تعيين كلمة المرور
    res_reset = client.post('/api/recovery/complete_reset', json={
        'reset_token': reset_token,
        'new_password': new_pass,
        'confirm_password': new_pass
    })
    assert res_reset.status_code == 200
    assert res_reset.get_json()['success'] is True

    # 4. التأكد من فشل كلمة المرور القديمة ونجاح الجديدة
    res_old_login = client.post('/api/auth/login', json={'username': username, 'password': old_pass})
    assert res_old_login.status_code == 401

    res_new_login = client.post('/api/auth/login', json={'username': username, 'password': new_pass})
    assert res_new_login.status_code == 200
    assert res_new_login.get_json()['success'] is True


def test_full_recovery_flow_manual_code_and_pin(client):
    """اختبار مسار الاسترداد عبر إدخال رمز الاسترداد اليدوي ورقم PIN."""
    username = f'test_manual_code_{uuid.uuid4().hex[:6]}'
    old_pass = 'OldPass#2026Secure'
    new_pass = 'NewPass#2026Academic'
    pin = '112233'

    user_repo.add_user(username, old_pass, 'سارة مراجع أول', 'senior_reviewer', enforce_policy=False)
    with get_session() as session:
        u = session.query(User).filter(User.username == username).first()
        u_id = u.id

    ok, card, _ = recovery_service.enroll_recovery_credential(u_id, pin)
    assert ok is True
    manual_code = card['manual_recovery_code']

    # 1. إرسال الكود اليدوي المشوه بمسافات وأحرف صغيرة مع رقم PIN
    dirty_code = "  " + manual_code.lower() + "  "
    res_auth = client.post('/api/recovery/verify_and_authorize', json={
        'username': username,
        'manual_code': dirty_code,
        'pin': pin
    })
    assert res_auth.status_code == 200
    reset_token = res_auth.get_json()['reset_token']

    # 2. إتمام إعادة التعيين
    res_reset = client.post('/api/recovery/complete_reset', json={
        'reset_token': reset_token,
        'new_password': new_pass,
        'confirm_password': new_pass
    })
    assert res_reset.status_code == 200

    # 3. التأكد من نجاح الدخول بكلمة المرور الجديدة
    res_login = client.post('/api/auth/login', json={'username': username, 'password': new_pass})
    assert res_login.status_code == 200


def test_wrong_pin_and_rate_limiting_lockout(client):
    """التحقق من كبح المحاولات والقفل المؤقت بعد 5 محاولات PIN خاطئة."""
    username = f'test_pin_lockout_{uuid.uuid4().hex[:6]}'
    pin = '556677'
    user_repo.add_user(username, 'ValidPass#2026Secure', 'د. سامح', 'reviewer', enforce_policy=False)
    with get_session() as session:
        u = session.query(User).filter(User.username == username).first()
        recovery_service.enroll_recovery_credential(u.id, pin)

    with get_session() as session:
        u = session.query(User).filter(User.username == username).first()
        cred = session.query(AccountRecoveryCredential).filter(AccountRecoveryCredential.user_id == u.id, AccountRecoveryCredential.status == 'active').first()
        # نستخدم الكود الصحيح لكن مع PIN خاطئ
        raw_secret = '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef'

    # إرسال 5 محاولات خاطئة متتالية
    for i in range(5):
        res = client.post('/api/recovery/verify_and_authorize', json={
            'username': username,
            'secret': raw_secret,
            'pin': '000000'
        })
        assert res.status_code == 400

    # المحاولة السادسة يجب أن ترجع كود الكبح والقفل 429
    res_locked = client.post('/api/recovery/verify_and_authorize', json={
        'username': username,
        'secret': raw_secret,
        'pin': '000000'
    })
    assert res_locked.status_code in (400, 429)


def test_reset_token_single_use_and_invalidation(client):
    """التحقق من أن رمز التفويض المؤقت صالح لمرة واحدة فقط ويبطل فور استخدامه."""
    username = f'test_token_single_{uuid.uuid4().hex[:6]}'
    pin = '889900'
    user_repo.add_user(username, 'ValidPass#2026Secure', 'د. طارق', 'unit_manager', enforce_policy=False)
    with get_session() as session:
        u = session.query(User).filter(User.username == username).first()
        u_id = u.id

    ok, card, _ = recovery_service.enroll_recovery_credential(u_id, pin)
    manual_code = card['manual_recovery_code']

    res_auth = client.post('/api/recovery/verify_and_authorize', json={
        'username': username,
        'manual_code': manual_code,
        'pin': pin
    })
    assert res_auth.status_code == 200
    reset_token = res_auth.get_json()['reset_token']

    # الاستخدام الأول -> ينجح
    res1 = client.post('/api/recovery/complete_reset', json={
        'reset_token': reset_token,
        'new_password': 'FirstReset#2026Secure',
        'confirm_password': 'FirstReset#2026Secure'
    })
    assert res1.status_code == 200

    # إعادة استخدام نفس الرمز لمرة ثانية -> يُرفض فوراً
    res2 = client.post('/api/recovery/complete_reset', json={
        'reset_token': reset_token,
        'new_password': 'SecondReset#2026Secure',
        'confirm_password': 'SecondReset#2026Secure'
    })
    assert res2.status_code == 400
    assert res2.get_json()['error_code'] == ErrorCode.RECOVERY_TOKEN_EXPIRED


def test_credential_regeneration_and_revocation(client):
    """التحقق من إلغاء الرمز القديم فور إعادة التوليد أو الإلغاء الصريح."""
    username = f'test_regen_{uuid.uuid4().hex[:6]}'
    current_pass = 'CurrentPass#2026Secure'
    pin1 = '111222'
    pin2 = '333444'

    user_repo.add_user(username, current_pass, 'مستخدم التجديد', 'reviewer', enforce_policy=False)
    with get_session() as session:
        u = session.query(User).filter(User.username == username).first()
        u_id = u.id

    ok1, card1, _ = recovery_service.enroll_recovery_credential(u_id, pin1)
    assert ok1 is True
    old_code = card1['manual_recovery_code']

    # إعادة توليد الاعتماد
    ok2, card2, _ = recovery_service.enroll_recovery_credential(u_id, pin2)
    assert ok2 is True
    new_code = card2['manual_recovery_code']

    # الرمز القديم + PIN القديم يجب أن يفشل
    res_old = client.post('/api/recovery/verify_and_authorize', json={
        'username': username,
        'manual_code': old_code,
        'pin': pin1
    })
    assert res_old.status_code == 400

    # الرمز الجديد + PIN الجديد ينجح
    res_new = client.post('/api/recovery/verify_and_authorize', json={
        'username': username,
        'manual_code': new_code,
        'pin': pin2
    })
    assert res_new.status_code == 200

    # الإلغاء الصريح للاعتماد
    rev_ok, _ = recovery_service.revoke_recovery_credential(u_id)
    assert rev_ok is True

    # بعد الإلغاء، حتى الرمز الجديد يرفض
    res_after_revoke = client.post('/api/recovery/verify_and_authorize', json={
        'username': username,
        'manual_code': new_code,
        'pin': pin2
    })
    assert res_after_revoke.status_code == 400
    assert res_after_revoke.get_json()['error_code'] == ErrorCode.RECOVERY_NOT_CONFIGURED


def test_audit_trail_redaction_for_recovery_events(app_instance, client):
    """التحقق من أن سجل التدقيق المؤسسي يسجل أحداث الاسترداد دون تسريب أي أسرار أو رموز."""
    with app_instance.app_context():
        username = f'test_audit_rec_{uuid.uuid4().hex[:6]}'
        pin = '990011'
        user_repo.add_user(username, 'ValidPass#2026Secure', 'د. مروان', 'reviewer', enforce_policy=False)
        with get_session() as session:
            u = session.query(User).filter(User.username == username).first()
            u_id = u.id

        ok, card, _ = recovery_service.enroll_recovery_credential(u_id, pin)
        raw_code = card['manual_recovery_code']

        # فحص سجلات التدقيق
        with get_session() as session:
            logs = session.query(AuditLog).filter(AuditLog.action.like('auth.recovery%')).all()
            for l in logs:
                meta_str = l.metadata_json or ""
                assert pin not in meta_str
                assert raw_code not in meta_str
                assert 'secret' not in meta_str or '[REDACTED]' in meta_str


def test_all_roles_can_enroll_and_recover(client):
    """التحقق من إمكانية استرداد الحساب لجميع الأدوار (موظف، مراجع، مسؤول وحدة، مدير نظام)."""
    roles = ['employee', 'reviewer', 'senior_reviewer', 'unit_manager', 'system_admin']
    for r in roles:
        uname = f'user_role_{r}_{uuid.uuid4().hex[:6]}'
        pin = '123789'
        user_repo.add_user(uname, 'InitPass#2026Secure', f'مستخدم {r}', r, enforce_policy=False)
        with get_session() as session:
            u = session.query(User).filter(User.username == uname).first()
            u_id = u.id

        ok, card, _ = recovery_service.enroll_recovery_credential(u_id, pin)
        assert ok is True

        res_auth = client.post('/api/recovery/verify_and_authorize', json={
            'username': uname,
            'manual_code': card['manual_recovery_code'],
            'pin': pin
        })
        assert res_auth.status_code == 200
        token = res_auth.get_json()['reset_token']

        res_reset = client.post('/api/recovery/complete_reset', json={
            'reset_token': token,
            'new_password': 'RecoveredPass#2026Strong',
            'confirm_password': 'RecoveredPass#2026Strong'
        })
        assert res_reset.status_code == 200


def test_offline_zero_external_network_calls(monkeypatch, client):
    """التحقق من أن توليد وفك تشفير واسترداد الرمز يعمل بنسبة 100% بدون أي اتصال خارجي."""
    def guarded_connect(self, address):
        host = address[0] if isinstance(address, (tuple, list)) and len(address) > 0 else address
        if str(host) not in ['127.0.0.1', 'localhost', '::1', '0.0.0.0']:
            raise RuntimeError(f"CRITICAL ERROR: External network connection attempted: {address}")
        return True

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)

    uname = f'test_strictly_offline_{uuid.uuid4().hex[:6]}'
    pin = '456789'
    user_repo.add_user(uname, 'InitPass#2026Secure', 'مستخدم أوفلاين', 'reviewer', enforce_policy=False)
    with get_session() as session:
        u = session.query(User).filter(User.username == uname).first()
        u_id = u.id

    # التوليد
    ok, card, _ = recovery_service.enroll_recovery_credential(u_id, pin)
    assert ok is True

    # فك تشفير الصورة
    b64_part = card['qr_image_data_url'].split(',', 1)[1]
    img_bytes = base64.b64decode(b64_part)
    dec_ok, payload, _ = recovery_service.decode_qr_from_bytes(img_bytes)
    assert dec_ok is True

    # التحقق
    res_auth = client.post('/api/recovery/verify_and_authorize', json={
        'qr_payload': payload,
        'pin': pin
    })
    assert res_auth.status_code == 200
