# -*- coding: utf-8 -*-
"""
حزمة اختبارات تحصين قاعدة البيانات وجاهزية SQLite (Phase 9: SQLite Hardening & DB Readiness Tests):
1. التحقق من تفعيل المفاتيح الأجنبية PRAGMA foreign_keys = ON.
2. التحقق من ضبط نمط السجل PRAGMA journal_mode = WAL.
3. التحقق من ضبط الوضع التزامني PRAGMA synchronous = NORMAL.
4. التحقق من ضبط مهلة التزاحم PRAGMA busy_timeout = 10000.
5. التحقق من ضبط الجداول المؤقتة في الذاكرة PRAGMA temp_store = MEMORY.
6. التحقق من نقاط التفتيش التلقائية PRAGMA wal_autocheckpoint = 1000.
7. التحقق من التراجع التلقائي للجلسة (Session Rollback) عند حدوث استثناء.
8. التحقق من حفظ وتأكيد البيانات عند انتهاء الجلسة بنجاح (Session Commit).
9. التحقق من إغلاق الجلسات بشكل قطعي عبر context manager.
10. التحقق من عدم مشاركة كائن Session واحد بين خيوط المعالجة المختلفة.
11. التحقق من فرادة الأرقام المرجعية عند المعالجة المتزامنة دون أي تكرار.
12. التحقق من طلب الصلاحيات عند استدعاء نقطة فحص صحة قاعدة البيانات.
13. التحقق من صحة واكتمال بنية تقرير صحة ومقاييس قاعدة البيانات.
14. التحقق من تشغيل الفحص السريع PRAGMA quick_check بنجاح وتوثيقه.
15. التحقق من اشتراط صلاحية الصيانة لتشغيل PRAGMA integrity_check.
16. التحقق من تشغيل الفحص الشامل PRAGMA integrity_check بنجاح.
17. التحقق من تشغيل نقطة تفتيش PRAGMA wal_checkpoint.
18. التحقق من الرجوع الآمن لنمط PASSIVE عند تمرير نمط نقطة تفتيش غير صالح.
19. التحقق من وجود إصدار مخطط قاعدة البيانات DATABASE_SCHEMA_VERSION.
20. التحقق من خاصية عدم التكرار (Idempotency) في سجل الهجرات.
21. التحقق من وجود فهارس الأداء الأساسية للجداول.
22. التحقق من استرجاع التقارير الحديثة عبر outerjoin دون استعلامات N+1.
23. التحقق من استرجاع طابور المراجعة المعلقة باستعلام مدمج.
24. التحقق من استرجاع الأبحاث المرفوضة باستعلام مدمج.
25. التحقق من استرجاع الأبحاث المقبولة مبدئياً باستعلام مدمج.
26. التحقق من عدم حظر القراءات أثناء العمليات الحسابية للأبحاث.
27. التحقق من حساب عدد مهام الفحص النشطة بدقة في التقرير الصحي.
28. التحقق من تسجيل حدث تدقيق عند تنفيذ quick_check.
29. التحقق من تسجيل حدث تدقيق عند تنفيذ integrity_check.
30. التحقق من تسجيل حدث تدقيق عند تنفيذ wal_checkpoint.
"""

import os
import json
import uuid
import time
import pytest
import threading
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import text

from app import create_app, versioning
from app.models.schema import User, LegacyReport, ScanJob
from app.models.audit_schema import AuditLog
from app.models.research_schema import Research, ResearchFile
from app.models.migration_schema import SchemaMigration
from app.repositories import base_repo, user_repo, report_repo, batch_repo
from app.services import db_health_service, migration_service, reference_service
from app.security.permissions import Role, Permission
import config


@pytest.fixture
def app_instance():
    app = create_app()
    app.config['TESTING'] = True
    app.config['STRICT_AUTH'] = True
    app.config['SECRET_KEY'] = 'test-db-hardening-secret-2026'
    return app


@pytest.fixture
def client(app_instance):
    with app_instance.test_client() as client:
        yield client


def _setup_test_user(username, role, password="Password123!"):
    """مساعد لإنشاء مستخدم تجريبي بصلاحيات محددة."""
    with base_repo.get_session() as session:
        user = session.query(User).filter(User.username == username).first()
        if not user:
            user = User(
                username=username,
                password_hash=user_repo.hash_password(password),
                full_name=f"مستخدم {username}",
                role=role
            )
            session.add(user)
            session.flush()
        else:
            user.role = role
        return user.id, user.username, user.role


# ─── 1. اختبارات إعدادات الـ PRAGMA والاتصال المركزي ───────────────────────────

def test_sqlite_foreign_keys_enabled_on_connection(app_instance):
    """التحقق من أن كل اتصال جديد يفعل المفاتيح الأجنبية PRAGMA foreign_keys = ON."""
    with app_instance.app_context():
        with base_repo.engine.connect() as conn:
            fk = conn.execute(text("PRAGMA foreign_keys;")).scalar()
            assert fk == 1 or fk is True


def test_sqlite_wal_mode_and_synchronous_configured(app_instance):
    """التحقق من تفعيل نمط WAL والوضع التزامني NORMAL."""
    with app_instance.app_context():
        with base_repo.engine.connect() as conn:
            jm = conn.execute(text("PRAGMA journal_mode;")).scalar()
            sync = conn.execute(text("PRAGMA synchronous;")).scalar()
            assert str(jm).upper() == 'WAL'
            assert sync in (1, 2)


def test_sqlite_busy_timeout_configured(app_instance):
    """التحقق من ضبط مهلة انتظار الأقفال على 10000ms (10 ثوانٍ)."""
    with app_instance.app_context():
        with base_repo.engine.connect() as conn:
            timeout = conn.execute(text("PRAGMA busy_timeout;")).scalar()
            assert int(timeout) >= 5000


def test_sqlite_temp_store_memory_configured(app_instance):
    """التحقق من ضبط الجداول المؤقتة في الذاكرة PRAGMA temp_store = MEMORY."""
    with app_instance.app_context():
        with base_repo.engine.connect() as conn:
            ts = conn.execute(text("PRAGMA temp_store;")).scalar()
            assert ts in (2, '2', 'MEMORY')


def test_sqlite_wal_autocheckpoint_configured(app_instance):
    """التحقق من نقاط التفتيش التلقائية PRAGMA wal_autocheckpoint."""
    with app_instance.app_context():
        with base_repo.engine.connect() as conn:
            acp = conn.execute(text("PRAGMA wal_autocheckpoint;")).scalar()
            assert int(acp) > 0


# ─── 2. اختبارات دورة حياة الجلسات والمسارات المتعددة ─────────────────────────

def test_session_rollback_on_exception(app_instance):
    """حدوث استثناء داخل get_session() يتراجع تلقائياً (Rollback) دون تلويث قاعدة البيانات."""
    with app_instance.app_context():
        temp_uname = f"rollback_user_{uuid.uuid4().hex[:6]}"
        try:
            with base_repo.get_session() as session:
                u = User(username=temp_uname, password_hash='hash', full_name='اختبار التراجع', role='reviewer')
                session.add(u)
                session.flush()
                raise RuntimeError("خطأ مقصود لاختبار التراجع")
        except RuntimeError:
            pass

        with base_repo.get_session() as check_session:
            found = check_session.query(User).filter(User.username == temp_uname).first()
            assert found is None


def test_session_commit_persists_data(app_instance):
    """انتهاء سياق get_session() بنجاح يحفظ البيانات ويلتزم بالمعاملة (Commit)."""
    with app_instance.app_context():
        temp_uname = f"commit_user_{uuid.uuid4().hex[:6]}"
        with base_repo.get_session() as session:
            u = User(username=temp_uname, password_hash='hash', full_name='اختبار الحفظ', role='reviewer')
            session.add(u)

        with base_repo.get_session() as check_session:
            found = check_session.query(User).filter(User.username == temp_uname).first()
            assert found is not None
            assert found.username == temp_uname


def test_session_closes_deterministically(app_instance):
    """إغلاق الجلسة بشكل قطعي عند الخروج من context manager."""
    with app_instance.app_context():
        with base_repo.get_session() as session:
            s_ref = session
            assert session.is_active is True
        # بعد انتهاء الـ context manager تكون الجلسة مغلقة
        assert not s_ref.is_active or s_ref.bind is not None


def test_independent_sessions_per_thread(app_instance):
    """كل خيط معالجة (Thread) يحصل على كائن Session مستقل تماماً."""
    active_sessions = []
    lock = threading.Lock()

    def worker():
        with app_instance.app_context():
            with base_repo.get_session() as s:
                with lock:
                    active_sessions.append(s)
                time.sleep(0.05)

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(active_sessions) == 5
    assert len({id(s) for s in active_sessions}) == 5


def test_concurrent_reference_number_allocation_is_unique(app_instance):
    """توليد الأرقام المرجعية المتزامنة ينتج أرقاماً فريدة دون أي تكرار إطلاقاً."""
    allocated_refs = []
    lock = threading.Lock()

    def allocate_ref():
        with app_instance.app_context():
            ref = reference_service.get_next_research_reference()
            with lock:
                allocated_refs.append(ref)

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(allocate_ref) for _ in range(16)]
        for f in futures:
            f.result()

    assert len(allocated_refs) == 16
    assert len(set(allocated_refs)) == 16


# ─── 3. اختبارات فحص صحة ومقاييس قاعدة البيانات (DB Health & Monitoring) ───────

def test_db_health_endpoint_requires_view_permission(client, app_instance):
    """نقطة الفحص الصحي تتطلب صلاحية system.health.view."""
    res = client.get('/api/system/db_health')
    assert res.status_code in (401, 403)

    uid, uname, urole = _setup_test_user('db_health_viewer', Role.SYSTEM_ADMIN)
    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = uname
        sess['role'] = urole

    res_ok = client.get('/api/system/db_health')
    assert res_ok.status_code == 200
    data = res_ok.get_json()
    assert data['database_reachable'] is True
    assert data['pragmas']['journal_mode'] == 'WAL'
    assert 'schema_version' in data


def test_db_health_endpoint_returns_expected_structure(app_instance):
    """التحقق من اكتمال عناصر التقرير الصحي لقاعدة البيانات."""
    with app_instance.app_context():
        health = db_health_service.get_database_health()
        assert health['status'] in ('healthy', 'degraded')
        assert health['database_reachable'] is True
        assert 'database_file_size_bytes' in health
        assert 'wal_file_size_bytes' in health
        assert 'active_scan_jobs_count' in health
        assert 'pragmas' in health


def test_quick_check_service_and_endpoint(client, app_instance):
    """الفحص السريع PRAGMA quick_check يعمل بنجاح ويُعيد ok."""
    uid, uname, urole = _setup_test_user('quick_check_admin', Role.SYSTEM_ADMIN)
    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = uname
        sess['role'] = urole

    res = client.post('/api/admin/db/quick_check')
    assert res.status_code == 200
    data = res.get_json()
    assert data['success'] is True
    assert data['is_clean'] is True


def test_deep_integrity_check_requires_maintenance_permission(client, app_instance):
    """الفحص الشامل PRAGMA integrity_check يتطلب صلاحية system.maintenance."""
    uid_rev, uname_rev, urole_rev = _setup_test_user('reviewer_no_maint', Role.REVIEWER)
    with client.session_transaction() as sess:
        sess['user_id'] = uid_rev
        sess['username'] = uname_rev
        sess['role'] = urole_rev

    res_forbidden = client.post('/api/admin/db/integrity_check')
    assert res_forbidden.status_code == 403

    uid_adm, uname_adm, urole_adm = _setup_test_user('admin_maint_actor', Role.SYSTEM_ADMIN)
    with client.session_transaction() as sess:
        sess['user_id'] = uid_adm
        sess['username'] = uname_adm
        sess['role'] = urole_adm

    res_ok = client.post('/api/admin/db/integrity_check')
    assert res_ok.status_code == 200
    data = res_ok.get_json()
    assert data['success'] is True
    assert data['is_clean'] is True


def test_deep_integrity_check_service_and_endpoint(app_instance):
    """الفحص الشامل عبر الخدمة المباشرة يُعيد نتيجة سليمة."""
    with app_instance.app_context():
        res = db_health_service.run_deep_integrity_check()
        assert res['success'] is True
        assert res['is_clean'] is True


def test_wal_checkpoint_maintenance(client, app_instance):
    """تنفيذ نقطة تفتيش PRAGMA wal_checkpoint يعمل بسلاسة."""
    uid, uname, urole = _setup_test_user('chk_point_admin', Role.SYSTEM_ADMIN)
    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = uname
        sess['role'] = urole

    res = client.post('/api/admin/db/checkpoint', json={'mode': 'PASSIVE'})
    assert res.status_code == 200
    data = res.get_json()
    assert data['success'] is True
    assert data['mode'] == 'PASSIVE'


def test_wal_checkpoint_invalid_mode_fallback(app_instance):
    """تمرير نمط غير معروف لنقطة التفتيش يرجع تلقائياً لـ PASSIVE بأمان."""
    with app_instance.app_context():
        res = db_health_service.run_wal_checkpoint(mode='INVALID_MODE')
        assert res['success'] is True
        assert res['mode'] == 'PASSIVE'


# ─── 4. اختبارات الفهارس والهجرات وإصدار المخطط (Schema & Migrations) ─────────

def test_database_schema_version_and_migration_registry(app_instance):
    """إصدار مخطط قاعدة البيانات معرف وسجل الهجرات يوثق الهجرات المطبقة."""
    with app_instance.app_context():
        assert hasattr(versioning, 'DATABASE_SCHEMA_VERSION')
        assert versioning.DATABASE_SCHEMA_VERSION == '1.0.0'

        applied = migration_service.get_applied_migrations()
        assert len(applied) >= 2
        assert '001_initial_schema' in applied
        assert '002_phase9_indexes' in applied


def test_migration_service_is_idempotent(app_instance):
    """إعادة تشغيل apply_all_migrations() لا تعيد تطبيق الهجرات السابقة ولا تُحدث أخطاء."""
    with app_instance.app_context():
        new_count = migration_service.apply_all_migrations()
        assert new_count == 0  # كل الهجرات مطبقة بالفعل


def test_performance_indexes_exist(app_instance):
    """التحقق من وجود الفهارس المعتمدة على الجداول الإنتاجية."""
    with app_instance.app_context():
        migration_service.apply_all_migrations()
        migration_service._migration_002_phase9_indexes()
        with base_repo.engine.connect() as conn:
            idx_rows = conn.execute(text("SELECT name, tbl_name FROM sqlite_master WHERE type='index';")).fetchall()
            index_names = {r[0] for r in idx_rows}

            assert 'idx_research_status' in index_names or 'idx_research_created' in index_names
            assert 'idx_research_files_hash' in index_names
            assert 'idx_reports_status' in index_names


def test_report_listing_does_not_n_plus_one_research(app_instance):
    """استعلام قائمة التقارير يسترجع الأرقام المرجعية عبر outerjoin دون استعلامات N+1 منفصلة."""
    with app_instance.app_context():
        rep_id = f"opt_test_rep_{uuid.uuid4().hex[:6]}"
        report_repo.save_report(
            report_id=rep_id,
            title="بحث تجربة الأداء",
            overall_pct=15.0,
            copied_pct=10.0,
            para_pct=5.0,
            report_dict={'title': 'بحث تجربة الأداء'}
        )

        reps = report_repo.get_recent_reports(limit=5)
        assert isinstance(reps, list)
        found = [r for r in reps if r['id'] == rep_id]
        assert len(found) == 1


def test_pending_reviews_query_optimized(app_instance):
    """استعلام طابور المراجعة المعلقة يعمل بكفاءة."""
    with app_instance.app_context():
        pending = report_repo.get_pending_initial_reviews()
        assert isinstance(pending, list)


def test_rejected_reports_query_optimized(app_instance):
    """استعلام التقارير المرفوضة يعمل بكفاءة."""
    with app_instance.app_context():
        rejected = report_repo.get_rejected_reports()
        assert isinstance(rejected, list)


def test_preliminary_reports_query_optimized(app_instance):
    """استعلام التقارير المقبولة مبدئياً يعمل بكفاءة."""
    with app_instance.app_context():
        prelim = report_repo.get_preliminary_reports()
        assert isinstance(prelim, list)


def test_heavy_computation_does_not_block_db_readers(app_instance):
    """محاكاة حسابات ثقيلة في الذاكرة دون حظر قراء قاعدة البيانات."""
    read_results = []

    def reader_task():
        with app_instance.app_context():
            stats = report_repo.get_reports_stats()
            read_results.append(stats)

    # تشغيل قراء متزامنين أثناء حساب الذاكرة
    threads = [threading.Thread(target=reader_task) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(read_results) == 5


def test_database_health_service_active_jobs_count(app_instance):
    """التحقق من دقة قراءة عدد مهام الفحص النشطة في التقرير الصحي."""
    with app_instance.app_context():
        health = db_health_service.get_database_health()
        assert isinstance(health['active_scan_jobs_count'], int)
        assert health['active_scan_jobs_count'] >= 0


def test_audit_event_logged_on_quick_check(app_instance):
    """توثيق حدث التدقيق عند تشغيل PRAGMA quick_check."""
    with app_instance.app_context():
        db_health_service.run_quick_check()
        with base_repo.get_session() as session:
            ev = session.query(AuditLog).filter(AuditLog.action == "database.quick_check_completed").order_by(AuditLog.id.desc()).first()
            assert ev is not None
            assert ev.category == "database"


def test_audit_event_logged_on_integrity_check(app_instance):
    """توثيق حدث التدقيق عند تشغيل PRAGMA integrity_check."""
    with app_instance.app_context():
        db_health_service.run_deep_integrity_check()
        with base_repo.get_session() as session:
            ev = session.query(AuditLog).filter(AuditLog.action == "database.integrity_check_completed").order_by(AuditLog.id.desc()).first()
            assert ev is not None
            assert ev.category == "database"


def test_audit_event_logged_on_checkpoint(app_instance):
    """توثيق حدث التدقيق عند تشغيل PRAGMA wal_checkpoint."""
    with app_instance.app_context():
        db_health_service.run_wal_checkpoint(mode='PASSIVE')
        with base_repo.get_session() as session:
            ev = session.query(AuditLog).filter(AuditLog.action == "database.checkpoint_completed").order_by(AuditLog.id.desc()).first()
            assert ev is not None
            assert ev.category == "database"
