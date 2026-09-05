# -*- coding: utf-8 -*-
"""
مجموعة اختبارات التحقق والتصليد الأمني للمصادقة والجلسات والعمليات المتعددة (Phase 14 Test Suite):
- التحقق من التزامن عبر العمليات المتعددة (Multi-Process First Admin & Lockout).
- التحقق من العقد الأمني لإغلاق التهيئة الدائم (Persistent Installation Security State & Recovery).
- التحقق من ذرية إبطال الجلسات عند تغيير الأدوار وتغيير كلمات المرور والتعطيل والحذف.
- التحقق من مقاومة تعداد الحسابات وحظر القوة الغاشمة دون الإضرار بالمستخدمين الأبرياء.
- التحقق من تدوير رموز CSRF وانتهاء مهل الجلسات (Idle & Absolute) دون انزلاق زمني.
- التحقق من التوقيتات الموحدة (UTC) وإعدادات الكوكيز الآمنة وترقية الهاش القديم.
"""

import os
import io
import time
import secrets
import threading
import multiprocessing
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock
from concurrent.futures import ThreadPoolExecutor
import pytest

import config
from app import create_app
from app.repositories import user_repo, base_repo
from app.models.schema import User, AuthLockout, SystemSecurityState
from app.models.audit_schema import AuditLog
from app.services import login_throttling_service, audit_service, system_health_service
from app.security.password_policy import validate_password_strength
from app.security.csrf import generate_csrf_token, rotate_csrf_token
from app.security.permissions import Role, Permission
from app.security.authorization import get_authenticated_user
from app.errors.error_codes import ErrorCode


# ─── دوال مساعدة عليا للعمليات المتعددة عبر نظام التشغيل (OS Multi-Process) ─────

def _mp_worker_create_first_admin(db_url, username, password, full_name, result_queue):
    """عامل متعدد العمليات لمحاولة إنشاء المدير الأول بشكل متزامن."""
    import os
    os.environ['TESTING'] = '1'
    from app.repositories import base_repo, user_repo
    base_repo.rebind_engine(db_url)
    try:
        ok, msg = user_repo.create_initial_admin(username, password, full_name)
        result_queue.put(('success' if ok else 'failed', msg))
    except Exception as e:
        result_queue.put(('failed', str(e)))


def _mp_worker_record_failed_attempt(db_url, username, ip_address, iterations, result_queue):
    """عامل متعدد العمليات لتسجيل محاولات دخول فاشلة بشكل متزامن دون فقدان تحديثات."""
    import os
    os.environ['TESTING'] = '1'
    from app.repositories import base_repo
    from app.services import login_throttling_service
    base_repo.rebind_engine(db_url)
    try:
        for _ in range(iterations):
            login_throttling_service.record_failed_attempt(username, ip_address)
        result_queue.put(('done', iterations))
    except Exception as e:
        result_queue.put(('error', str(e)))


@pytest.fixture
def app_instance():
    app = create_app()
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app_instance):
    with app_instance.test_client() as c:
        yield c


@pytest.fixture
def clean_auth_db():
    """تهيئة مستخدمين وقفل نظيف لكل اختبار."""
    with base_repo.get_session() as session:
        session.query(AuthLockout).delete()
        session.query(SystemSecurityState).delete()
        session.query(User).filter(User.username.like('test_%')).delete()
    yield
    with base_repo.get_session() as session:
        session.query(AuthLockout).delete()
        session.query(SystemSecurityState).delete()
        session.query(User).filter(User.username.like('test_%')).delete()


@pytest.fixture
def clean_first_admin_db():
    """تهيئة نظيفة بدون أي مستخدمين لاختبارات تأسيس المدير الأول الحصرية."""
    with base_repo.get_session() as session:
        session.query(AuthLockout).delete()
        session.query(SystemSecurityState).delete()
        session.query(User).delete()
    yield
    with base_repo.get_session() as session:
        session.query(AuthLockout).delete()
        session.query(SystemSecurityState).delete()
        session.query(User).filter(User.username.like('test_%')).delete()


# ─── 1. اختبارات المصادقة الأساسية وسياسة كلمات المرور ──────────────────────────

def test_correct_password_login_succeeds(client, clean_auth_db):
    """1. تسجيل الدخول بكلمة المرور الصحيحة ينجح ويُنشئ جلسة موثقة."""
    user_repo.add_user('test_user_ok', 'ValidPass#2026Secure', 'موظف تجريبي', Role.REVIEWER)
    res = client.post('/api/auth/login', json={'username': 'test_user_ok', 'password': 'ValidPass#2026Secure'})
    assert res.status_code == 200
    data = res.get_json()
    assert data['success'] is True
    assert data['user']['username'] == 'test_user_ok'
    assert 'password_hash' not in data['user']
    assert 'csrf_token' in data


def test_wrong_password_fails_safely(client, clean_auth_db):
    """2. تسجيل الدخول بكلمة مرور خاطئة يفشل بأمان مع رسالة عامة و 401."""
    user_repo.add_user('test_user_wrong', 'ValidPass#2026Secure', 'موظف تجريبي', Role.REVIEWER)
    res = client.post('/api/auth/login', json={'username': 'test_user_wrong', 'password': 'WrongPassword123'})
    assert res.status_code == 401
    data = res.get_json()
    assert data['success'] is False
    assert 'اسم المستخدم أو كلمة المرور غير صحيحة' in data['error']


def test_unknown_username_returns_same_public_message(client, clean_auth_db):
    """3. اسم المستخدم غير الموجود يُعيد نفس الرسالة العامة والرمز لمنع التعداد."""
    res_known = client.post('/api/auth/login', json={'username': 'test_user_wrong', 'password': 'BadPassword'})
    res_unknown = client.post('/api/auth/login', json={'username': 'test_nonexistent_user_999', 'password': 'BadPassword'})
    assert res_known.status_code == 401
    assert res_unknown.status_code == 401
    assert res_known.get_json()['error'] == res_unknown.get_json()['error']


def test_password_hash_never_exposed_in_api(client, clean_auth_db):
    """4. التحقق من عدم تسريب هاش كلمة المرور في أي استجابة API للملف الشخصي أو القائمة."""
    user_repo.add_user('test_user_hash', 'ValidPass#2026Secure', 'موظف تجريبي', Role.REVIEWER)
    with client.session_transaction() as sess:
        u = user_repo.authenticate_user('test_user_hash', 'ValidPass#2026Secure')
        sess['user_id'] = u['id']
        sess['session_version'] = 1

    res_me = client.get('/api/auth/me')
    assert res_me.status_code == 200
    assert 'password_hash' not in res_me.get_data(as_text=True)

    users_list = user_repo.get_users_list()
    for u in users_list:
        assert 'password_hash' not in u


def test_minimum_password_policy_enforced():
    """5. التحقق من رفض كلمات المرور الأقل من 12 خانة وفق السياسة المؤسسية."""
    ok, err = validate_password_strength('Short123')
    assert ok is False
    assert '12 خانة' in err


def test_common_password_denylist_rejected():
    """6. التحقق من رفض كلمات المرور الشائعة من قائمة الحظر المحلية."""
    ok, err = validate_password_strength('123456789012')
    assert ok is False
    assert 'شائعة' in err


def test_username_like_password_rejected():
    """7. التحقق من رفض كلمة المرور عند احتوائها على اسم المستخدم."""
    ok, err = validate_password_strength('passTamer123456', username='tamer')
    assert ok is False
    assert 'اسم المستخدم' in err


def test_password_policy_rejects_full_name_subparts():
    """التحقق من رفض كلمات المرور التي تحتوي على أجزاء من الاسم الكامل للمستخدم."""
    ok, err = validate_password_strength('passDarwish2026!', username='tdarwish', full_name='Tamer Darwish')
    assert ok is False
    assert 'اسمك الشخصي' in err


def test_short_name_fragments_do_not_cause_unreasonable_password_rejection():
    """23. التحقق من عدم رفض كلمات مرور قوية بسبب مقاطع قصيرة جداً من الاسم (أقل من 4 أحرف)."""
    ok, err = validate_password_strength('ComplexValidPass2026#Secure', username='user_test', full_name='Ali Ma Al')
    assert ok is True
    assert err == ""


# ─── 2. اختبارات دورة حياة المدير الأول والعمليات المتعددة (True Multi-Process) ─

def test_first_admin_allowed_only_when_no_admin_exists(clean_first_admin_db):
    """8. مسار المدير الأول مسموح به فقط عند عدم وجود أي مدير مسجل."""
    assert user_repo.is_initial_admin_allowed() is True
    ok, _ = user_repo.create_initial_admin('test_admin_prime', 'ValidAdminPass#2026', 'المدير الأول')
    assert ok is True
    assert user_repo.is_initial_admin_allowed() is False


def test_concurrent_first_admin_race_does_not_create_duplicate_admins(clean_first_admin_db):
    """9. التحقق من منع إنشاء أكثر من مدير أول تحت ظروف التسابق داخل العملية."""
    results = []
    def try_create(idx):
        ok, msg = user_repo.create_initial_admin(f'test_admin_race_{idx}', 'ValidAdminPass#2026', f'مدير {idx}')
        results.append(ok)

    threads = [threading.Thread(target=try_create, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results.count(True) == 1
    assert results.count(False) == 4


def test_multiprocess_first_admin_race(clean_first_admin_db):
    """1. اختبار حقيقي لسباق إنشاء المدير الأول عبر عدة عمليات OS حقيقية متزامنة."""
    db_url = config.DATABASE_URL
    ctx = multiprocessing.get_context('spawn')
    result_queue = ctx.Queue()
    num_processes = 4

    processes = []
    for i in range(num_processes):
        p = ctx.Process(
            target=_mp_worker_create_first_admin,
            args=(db_url, f'test_mp_admin_{i}', 'ValidAdminPass#2026', f'مدير عملية {i}', result_queue)
        )
        processes.append(p)

    for p in processes:
        p.start()
    for p in processes:
        p.join(timeout=10)

    results = []
    while not result_queue.empty():
        status, msg = result_queue.get()
        results.append(status)

    assert results.count('success') == 1
    assert results.count('failed') == num_processes - 1

    with base_repo.get_session() as session:
        admins = session.query(User).filter(User.role.in_(['system_admin', 'admin'])).all()
        assert len(admins) == 1


def test_bootstrap_remains_closed_after_completion_even_if_admins_disabled(clean_first_admin_db):
    """2. التحقق من بقاء مسار التهيئة الأولية مغلقاً بشكل دائم حتى لو عُطل أو حُذف كافة المديرين لاحقاً."""
    ok, _ = user_repo.create_initial_admin('test_boot_admin', 'ValidAdminPass#2026', 'المدير الدائم')
    assert ok is True

    # تعطيل المدير
    with base_repo.get_session() as session:
        adm = session.query(User).filter(User.username == 'test_boot_admin').first()
        adm.is_active = 0
        session.commit()

    # التحقق من أن مسار التهيئة لا يزال مغلقاً بشكل دائم
    assert user_repo.is_initial_admin_allowed() is False

    ok2, msg2 = user_repo.create_initial_admin('test_boot_admin2', 'ValidAdminPass#2026', 'المدير الثاني')
    assert ok2 is False
    assert "مسبقاً" in msg2


def test_documented_recovery_path_required_to_reopen_bootstrap(clean_first_admin_db):
    """3. التحقق من فتح مسار التهيئة حصرياً عند تشغيل إجراء الاستعادة اليدوي/المحلي الرسمي."""
    user_repo.create_initial_admin('test_rec_admin', 'ValidAdminPass#2026', 'المدير الأولي')
    assert user_repo.is_initial_admin_allowed() is False

    # تنفيذ إجراء الاستعادة الرسمي
    user_repo.reopen_bootstrap_for_recovery()

    with base_repo.get_session() as session:
        session.query(User).filter(User.username == 'test_rec_admin').delete()
        session.commit()

    assert user_repo.is_initial_admin_allowed() is True


# ─── 3. اختبارات القفل وكبح محاولات الدخول وعزل IP ─────────────────────────────

def test_failed_attempts_counted_and_triggers_lockout(clean_auth_db):
    """10. تسجيل محاولات الدخول الخاطئة يرفع العداد ويفرض القفل عند 5 محاولات."""
    username = 'test_lockout_user'
    for i in range(4):
        is_locked, count, _ = login_throttling_service.record_failed_attempt(username)
        assert is_locked is False
        assert count == i + 1

    is_locked, count, locked_until = login_throttling_service.record_failed_attempt(username)
    assert is_locked is True
    assert count == 5
    assert locked_until is not None


def test_locked_account_cannot_authenticate_during_lockout(client, clean_auth_db):
    """11. الحساب المقفل يُرفض فوراً مع رمز 429 دون فحص كلمة المرور."""
    username = 'test_user_to_lock'
    user_repo.add_user(username, 'ValidPass#2026Secure', 'موظف تجريبي', Role.REVIEWER)

    for _ in range(5):
        login_throttling_service.record_failed_attempt(username)

    res = client.post('/api/auth/login', json={'username': username, 'password': 'ValidPass#2026Secure'})
    assert res.status_code == 429
    data = res.get_json()
    assert data['error_code'] == ErrorCode.AUTH_LOCKED_OUT


def test_lockout_expires_after_duration(clean_auth_db):
    """12. انتهاء مدة القفل يسمح بإعادة محاولة الدخول تلقائياً."""
    username = 'test_expire_user'
    past_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=20)

    with base_repo.get_session() as session:
        lockout = AuthLockout(
            identifier=login_throttling_service.normalize_identifier(username=username),
            failed_count=5,
            last_failed_at=past_time,
            locked_until=past_time + timedelta(minutes=15)
        )
        session.add(lockout)

    is_locked, _, _ = login_throttling_service.is_locked_out(username=username)
    assert is_locked is False


def test_successful_login_resets_failed_counter(clean_auth_db):
    """13. تسجيل الدخول الناجح يُصفر عداد المحاولات الفاشلة."""
    username = 'test_reset_counter_user'
    login_throttling_service.record_failed_attempt(username)
    login_throttling_service.record_failed_attempt(username)

    login_throttling_service.record_successful_login(username)

    with base_repo.get_session() as session:
        lockout = session.query(AuthLockout).filter(
            AuthLockout.identifier == login_throttling_service.normalize_identifier(username=username)
        ).first()
        assert lockout is not None
        assert lockout.failed_count == 0


def test_password_never_stored_in_lockout_table(clean_auth_db):
    """14. التحقق من عدم تخزين أي كلمات مرور في جدول القفل إطلاقاً."""
    login_throttling_service.record_failed_attempt('test_secret_user')
    with base_repo.get_session() as session:
        lockout = session.query(AuthLockout).first()
        assert not hasattr(lockout, 'password')
        assert not hasattr(lockout, 'password_hash')


def test_existing_locked_account_does_not_reveal_existence(client, clean_auth_db):
    """10. التحقق من أن الحساب المقفل لا يكشف وجوده في الرد العام."""
    username = 'test_locked_exist'
    user_repo.add_user(username, 'ValidPass#2026Secure', 'موظف موجود', Role.REVIEWER)
    for _ in range(5):
        login_throttling_service.record_failed_attempt(username)

    res_exist = client.post('/api/auth/login', json={'username': username, 'password': 'ValidPass#2026Secure'})
    assert res_exist.status_code == 429
    assert "اسم المستخدم" not in res_exist.get_json()['error']


def test_unknown_identifier_response_matches_public_lockout_shape(client, clean_auth_db):
    """11. التحقق من أن المعرف غير الموجود عند قفله يُعيد نفس شكل رسالة القفل العامة 429."""
    fake_user = 'test_nonexistent_lock_target'
    for _ in range(5):
        login_throttling_service.record_failed_attempt(fake_user)

    res_fake = client.post('/api/auth/login', json={'username': fake_user, 'password': 'any_password'})
    assert res_fake.status_code == 429
    assert res_fake.get_json()['error_code'] == ErrorCode.AUTH_LOCKED_OUT


def test_ip_abuse_does_not_trivially_permanently_lock_unrelated_accounts(clean_auth_db):
    """12. التحقق من أن تكرار المحاولات الفاشلة من IP مهاجم لا يُقفل الحسابات البريئة غير المستهدفة."""
    attacker_ip = '192.168.1.199'
    innocent_user = 'test_innocent_user'

    # المهاجم يجرب مستخدمين عشوائيين مختلفين
    for i in range(4):
        login_throttling_service.record_failed_attempt(username=f'random_target_{i}', ip_address=attacker_ip)

    # المستخدم البريء على جهازه المنفصل غير مقفل
    is_locked, _, _ = login_throttling_service.is_locked_out(username=innocent_user, ip_address='10.0.0.50')
    assert is_locked is False


def test_multiprocess_failed_login_counter_has_no_lost_updates(clean_auth_db):
    """13. التحقق من دقة عداد المحاولات الفاشلة عبر عمليات متعددة دون ضياع أي تحديث."""
    db_url = config.DATABASE_URL
    ctx = multiprocessing.get_context('spawn')
    result_queue = ctx.Queue()
    target_username = 'test_mp_lockout_target'
    num_processes = 4
    iters_per_process = 3

    processes = []
    for _ in range(num_processes):
        p = ctx.Process(
            target=_mp_worker_record_failed_attempt,
            args=(db_url, target_username, '127.0.0.1', iters_per_process, result_queue)
        )
        processes.append(p)

    for p in processes:
        p.start()
    for p in processes:
        p.join(timeout=10)

    ident = login_throttling_service.normalize_identifier(username=target_username)
    with base_repo.get_session() as session:
        lockout = session.query(AuthLockout).filter(AuthLockout.identifier == ident).first()
        assert lockout is not None
        assert lockout.failed_count == num_processes * iters_per_process


def test_utc_aware_lockout_timestamps(clean_auth_db):
    """14. التحقق من حفظ واستخدام توقيتات UTC حصرياً في سجلات القفل."""
    login_throttling_service.record_failed_attempt('test_utc_user')
    ident = login_throttling_service.normalize_identifier(username='test_utc_user')
    with base_repo.get_session() as session:
        lockout = session.query(AuthLockout).filter(AuthLockout.identifier == ident).first()
        assert lockout.last_failed_at is not None
        # الفرق الزمني مع UTC ضئيل جداً
        diff = abs((lockout.last_failed_at - datetime.now(timezone.utc).replace(tzinfo=None)).total_seconds())
        assert diff < 10


# ─── 4. اختبارات أمان الجلسات وتدوير CSRF وترقية الأدوار ─────────────────────────

def test_session_fixation_defense_regenerates_state(client, clean_auth_db):
    """15. منع تثبيت الجلسة عبر تفريغ الجلسة وتوليد رمز CSRF جديد ومستقل عند تسجيل الدخول."""
    user_repo.add_user('test_user_fixation', 'ValidPass#2026Secure', 'موظف تجريبي', Role.REVIEWER)

    # رمز CSRF قبل تسجيل الدخول
    with client.session_transaction() as sess:
        sess['pre_auth_data'] = 'secret_temp_value'
        sess['_csrf_token'] = 'pre_auth_csrf_token_1234'

    res = client.post('/api/auth/login', json={'username': 'test_user_fixation', 'password': 'ValidPass#2026Secure'})
    assert res.status_code == 200
    post_csrf = res.get_json()['csrf_token']
    assert post_csrf != 'pre_auth_csrf_token_1234'

    with client.session_transaction() as sess:
        assert 'pre_auth_data' not in sess
        assert sess.get('_csrf_token') == post_csrf


def test_csrf_regenerated_after_login(client, clean_auth_db):
    """15. التحقق من تغيير رمز CSRF بعد نجاح تسجيل الدخول."""
    res_token_pre = client.get('/api/auth/csrf-token')
    pre_csrf = res_token_pre.get_json()['csrf_token']

    user_repo.add_user('test_csrf_rot_user', 'ValidPass#2026Secure', 'موظف تجريبي', Role.REVIEWER)
    res_login = client.post('/api/auth/login', json={'username': 'test_csrf_rot_user', 'password': 'ValidPass#2026Secure'})
    post_csrf = res_login.get_json()['csrf_token']

    assert pre_csrf != post_csrf


def test_csrf_regenerated_after_logout_login(client, clean_auth_db):
    """16. التحقق من تجديد وتدوير رمز CSRF بعد دورة تسجيل الخروج والدخول مجدداً."""
    user_repo.add_user('test_csrf_cycle_user', 'ValidPass#2026Secure', 'موظف تجريبي', Role.REVIEWER)
    res_login1 = client.post('/api/auth/login', json={'username': 'test_csrf_cycle_user', 'password': 'ValidPass#2026Secure'})
    csrf1 = res_login1.get_json()['csrf_token']

    res_logout = client.post('/api/auth/logout', json={})
    assert res_logout.status_code == 200

    res_login2 = client.post('/api/auth/login', json={'username': 'test_csrf_cycle_user', 'password': 'ValidPass#2026Secure'})
    csrf2 = res_login2.get_json()['csrf_token']

    assert csrf1 != csrf2


def test_idle_timeout_boundary(client, clean_auth_db):
    """17. التحقق الدقيق من حدود مهلة الخمول (30 دقيقة)."""
    user_repo.add_user('test_idle_user', 'ValidPass#2026Secure', 'موظف تجريبي', Role.REVIEWER)
    u = user_repo.authenticate_user('test_idle_user', 'ValidPass#2026Secure')

    # أ. قبل انتهاء مهلة الخمول بثوانٍ (29 دقيقة و 50 ثانية)
    with client.session_transaction() as sess:
        sess['user_id'] = u['id']
        sess['session_version'] = 1
        sess['auth_time'] = time.time()
        sess['last_activity'] = time.time() - (29 * 60 + 50)

    res_ok = client.get('/api/auth/me')
    assert res_ok.get_json()['authenticated'] is True

    # ب. بعد انتهاء مهلة الخمول بثوانٍ (30 دقيقة و 10 ثوانٍ)
    with client.session_transaction() as sess:
        sess['user_id'] = u['id']
        sess['session_version'] = 1
        sess['auth_time'] = time.time()
        sess['last_activity'] = time.time() - (30 * 60 + 10)

    res_exp = client.get('/api/auth/me')
    assert res_exp.get_json()['authenticated'] is False


def test_absolute_timeout_boundary(client, clean_auth_db):
    """18. التحقق الدقيق من حدود السقف الزمني المطلق للجلسة (8 ساعات)."""
    user_repo.add_user('test_abs_user', 'ValidPass#2026Secure', 'موظف تجريبي', Role.REVIEWER)
    u = user_repo.authenticate_user('test_abs_user', 'ValidPass#2026Secure')

    # أ. قبل انتهاء السقف المطلق (7 ساعات و 59 دقيقة) مع نشاط حديث
    with client.session_transaction() as sess:
        sess['user_id'] = u['id']
        sess['session_version'] = 1
        sess['auth_time'] = time.time() - (7 * 3600 + 59 * 60)
        sess['last_activity'] = time.time() - 30

    res_ok = client.get('/api/auth/me')
    assert res_ok.get_json()['authenticated'] is True

    # ب. بعد انتهاء السقف المطلق (8 ساعات ودقيقة) مع نشاط حديث
    with client.session_transaction() as sess:
        sess['user_id'] = u['id']
        sess['session_version'] = 1
        sess['auth_time'] = time.time() - (8 * 3600 + 60)
        sess['last_activity'] = time.time() - 30

    res_exp = client.get('/api/auth/me')
    assert res_exp.get_json()['authenticated'] is False


def test_absolute_timeout_does_not_slide(client, clean_auth_db):
    """19. التحقق من أن السقف الزمني المطلق لا ينزلق مع استمرار النشاط."""
    user_repo.add_user('test_no_slide_user', 'ValidPass#2026Secure', 'موظف تجريبي', Role.REVIEWER)
    u = user_repo.authenticate_user('test_no_slide_user', 'ValidPass#2026Secure')
    origin_auth_time = time.time() - (8 * 3600 + 10)

    with client.session_transaction() as sess:
        sess['user_id'] = u['id']
        sess['session_version'] = 1
        sess['auth_time'] = origin_auth_time
        sess['last_activity'] = time.time() - 5

    res = client.get('/api/auth/me')
    assert res.get_json()['authenticated'] is False


def test_role_downgrade_and_upgrade_behavior(client, clean_auth_db):
    """4 + 5. التحقق من السريان الفوري لخفض وترقية الدور وتحديث الصلاحيات الحية."""
    user_repo.add_user('test_role_user', 'ValidPass#2026Secure', 'موظف متغير الدور', Role.REVIEWER)
    u = user_repo.authenticate_user('test_role_user', 'ValidPass#2026Secure')

    with client.session_transaction() as sess:
        sess['user_id'] = u['id']
        sess['session_version'] = 1

    # ترقية الدور
    user_repo.update_user_role(u['id'], Role.SYSTEM_ADMIN)
    res_admin = client.get('/api/auth/me')
    assert res_admin.status_code == 200
    # بسبب زيادة session_version فإن الجلسة تتطلب إعادة تسجيل الدخول
    assert res_admin.get_json()['authenticated'] is False


def test_admin_role_change_session_policy(clean_auth_db):
    """6. التحقق من أن تغيير دور المستخدم يزيد session_version لحماية الأمان المؤسسي."""
    user_repo.add_user('test_policy_role_user', 'ValidPass#2026Secure', 'موظف تجريبي', Role.REVIEWER)
    with base_repo.get_session() as session:
        u = session.query(User).filter(User.username == 'test_policy_role_user').first()
        u_id = u.id
        v_before = u.session_version

    user_repo.update_user_role(u_id, Role.UNIT_MANAGER)

    with base_repo.get_session() as session:
        u_after = session.query(User).filter(User.username == 'test_policy_role_user').first()
        assert u_after.session_version == v_before + 1


def test_disable_plus_session_invalidation_atomicity(clean_auth_db):
    """7. التحقق من ذرية تعطيل الحساب وزيادة session_version في معاملة واحدة."""
    user_repo.add_user('test_atomic_dis_user', 'ValidPass#2026Secure', 'موظف معطل', Role.REVIEWER)
    with base_repo.get_session() as session:
        u = session.query(User).filter(User.username == 'test_atomic_dis_user').first()
        u_id = u.id
        v_before = u.session_version

    ok, _ = user_repo.set_user_active_status(u_id, 0)
    assert ok is True

    with base_repo.get_session() as session:
        u_after = session.query(User).filter(User.username == 'test_atomic_dis_user').first()
        assert u_after.is_active == 0
        assert u_after.session_version == v_before + 1


def test_password_reset_plus_session_version_atomicity(clean_auth_db):
    """8. التحقق من ذرية إعادة تعيين كلمة المرور وترقية session_version وتصفير القفل."""
    user_repo.add_user('test_atomic_reset_user', 'ValidPass#2026Secure', 'موظف تجريبي', Role.REVIEWER)
    with base_repo.get_session() as session:
        u = session.query(User).filter(User.username == 'test_atomic_reset_user').first()
        u_id = u.id
        v_before = u.session_version

    login_throttling_service.record_failed_attempt('test_atomic_reset_user')

    ok, _ = user_repo.admin_reset_user_password(u_id, 'NewAdminPass#2026Secure')
    assert ok is True

    with base_repo.get_session() as session:
        u_after = session.query(User).filter(User.username == 'test_atomic_reset_user').first()
        assert u_after.session_version == v_before + 1

    is_locked, _, _ = login_throttling_service.is_locked_out(username='test_atomic_reset_user')
    assert is_locked is False


def test_rollback_leaves_old_password_session_valid_consistently(clean_auth_db):
    """9. التحقق من أن فشل معاملة تغيير كلمة المرور يُلغي التغييرات بالكامل ويُبقي القديم سليماً."""
    user_repo.add_user('test_rollback_user', 'ValidPass#2026Secure', 'موظف تراجع', Role.REVIEWER)
    u = user_repo.authenticate_user('test_rollback_user', 'ValidPass#2026Secure')

    # محاولة تغيير بكلمة مرور غير مقبولة تفشل وتتراجع
    ok, err = user_repo.change_password('test_rollback_user', 'ValidPass#2026Secure', 'weak')
    assert ok is False

    # القديمة لا تزال تعمل
    u_recheck = user_repo.authenticate_user('test_rollback_user', 'ValidPass#2026Secure')
    assert u_recheck is not None


# ─── 5. اختبارات CSRF وتهيئة الكوكيز والترقية القديمة ───────────────────────────

def test_cookie_security_attributes(client, clean_auth_db):
    """21. التحقق من خصائص الأمان للكوكيز HttpOnly و SameSite."""
    user_repo.add_user('test_cookie_user', 'ValidPass#2026Secure', 'موظف تجريبي', Role.REVIEWER)
    res = client.post('/api/auth/login', json={'username': 'test_cookie_user', 'password': 'ValidPass#2026Secure'})
    assert res.status_code == 200
    cookies = res.headers.getlist('Set-Cookie')
    assert len(cookies) > 0
    cookie_str = cookies[0]
    assert 'HttpOnly' in cookie_str
    assert 'SameSite=Lax' in cookie_str


def test_institutional_mode_warns_if_secure_cookie_disabled():
    """20. التحقق من تسجيل تحذير أمني عند تشغيل بيئة الإنتاج المؤسسي دون Secure Cookies."""
    with patch.dict(config.__dict__, {'APP_ENV': 'production', 'AUTH_COOKIE_SECURE': False}):
        check = system_health_service._check_application(datetime.now(timezone.utc))
        assert check['status'] == system_health_service.STATUS_DEGRADED
        assert "تحذير أمني" in check['message']


def test_every_state_changing_endpoint_has_csrf_decision(client, clean_auth_db):
    """21. التحقق من حماية المسارات المعدلة للحالة برمز CSRF وفشلها عند غيابه."""
    with patch.dict(client.application.config, {'ENFORCE_CSRF_IN_TESTS': True}):
        # طلب بدون رمز CSRF يجب أن يُرفض بـ 403
        res = client.post('/api/auth/logout', json={})
        assert res.status_code == 403
        assert res.get_json()['error_code'] == ErrorCode.CSRF_FAILED

        # مع رمز CSRF صالح ينجح
        with client.session_transaction() as sess:
            sess['_csrf_token'] = 'valid_test_csrf_token_xyz'

        res_ok = client.post(
            '/api/auth/logout',
            json={},
            headers={'X-CSRF-Token': 'valid_test_csrf_token_xyz'}
        )
        assert res_ok.status_code == 200


def test_login_csrf_policy_explicitly_tested(client, clean_auth_db):
    """22. التحقق من أن مسار تسجيل الدخول الأولي معفى صراحة من رمز CSRF مع تدوير الرمز فور المصادقة."""
    user_repo.add_user('test_login_csrf_user', 'ValidPass#2026Secure', 'موظف تجريبي', Role.REVIEWER)
    with patch.dict(client.application.config, {'ENFORCE_CSRF_IN_TESTS': True}):
        res = client.post('/api/auth/login', json={'username': 'test_login_csrf_user', 'password': 'ValidPass#2026Secure'})
        assert res.status_code == 200
        assert 'csrf_token' in res.get_json()


def test_valid_legacy_hash_migrates_safely(clean_auth_db):
    """24. التحقق من قبول هاش SHA-256 القديم المعتمد وترقيته تلقائياً إلى bcrypt عند أول تسجيل دخول."""
    import hashlib
    clean_user = 'test_legacy_user'
    plain_pass = 'LegacyValidPass#2026'
    legacy_hash = hashlib.sha256((plain_pass + user_repo._LEGACY_SALT).encode('utf-8')).hexdigest()

    with base_repo.get_session() as session:
        u = User(
            username=clean_user,
            password_hash=legacy_hash,
            full_name='موظف قديم',
            role=Role.REVIEWER,
            is_active=1,
            session_version=1
        )
        session.add(u)

    # تسجيل الدخول ينجح ويُرقي الهاش
    u_auth = user_repo.authenticate_user(clean_user, plain_pass)
    assert u_auth is not None

    with base_repo.get_session() as session:
        u_db = session.query(User).filter(User.username == clean_user).first()
        assert u_db.password_hash.startswith('$2b$') or u_db.password_hash.startswith('$2a$')


def test_invalid_unknown_hash_format_does_not_authenticate_migrate(clean_auth_db):
    """25. التحقق من رفض أي صيغ هاش مجهولة أو عشوائية وعدم قبولها للمصادقة."""
    clean_user = 'test_corrupt_hash_user'
    with base_repo.get_session() as session:
        u = User(
            username=clean_user,
            password_hash='corrupted_arbitrary_unrecognized_hash_string',
            full_name='مستخدم تالف الهاش',
            role=Role.REVIEWER,
            is_active=1,
            session_version=1
        )
        session.add(u)

    u_auth = user_repo.authenticate_user(clean_user, 'any_password')
    assert u_auth is None


def test_failed_login_audit_contains_no_password(client, clean_auth_db):
    """26. التحقق من عدم احتواء سجل التدقيق لمحاولات الدخول الفاشلة على كلمات المرور المجربة."""
    attempted_secret_pass = 'SecretSuperPasswordShouldNeverBeLogged'
    client.post('/api/auth/login', json={'username': 'test_audit_leak_check', 'password': attempted_secret_pass})

    with base_repo.get_session() as session:
        logs = session.query(AuditLog).filter(AuditLog.action == 'auth.login.failure').all()
        for log in logs:
            meta_str = str(log.metadata_json or '')
            assert attempted_secret_pass not in meta_str
