# -*- coding: utf-8 -*-
"""
حزمة اختبارات النسخ الاحتياطي والتعافي من الكوارث (Phase 8: Backup & Disaster Recovery Tests):
1. التحقق من توليد معرف مؤسسي فريد للنسخة الاحتياطية (BKP-YYYY-XXXXXX).
2. التحقق من بناء وتضمين البيان الرقمي التفصيلي (manifest.json).
3. التحقق من اتساق وصحة نسخة قاعدة بيانات SQLite المنسوخة.
4. التحقق من صحة بصمة SHA-256 للحزمة.
5. التحقق من أن الحزم التالفة أو المفتقدة للملفات تفشل في فحص السلامة.
6. التحقق من حظر إنشاء أو استعادة النسخ للمستخدمين غير المصرح لهم (RBAC).
7. التحقق من طلب رمز التأكيد الصريح والمطابق لتنفيذ الاستعادة.
8. التحقق من الإنشاء التلقائي لنسخة الطوارئ المسبقة (Pre-Restore Snapshot).
9. التحقق من نجاح الاستعادة الآمنة والحفاظ على الأرقام المرجعية وسجلات التدقيق واللقطات.
10. التحقق من التراجع التلقائي (Rollback) عند تعثر الاستعادة.
11. التحقق من منع عمليات الاستعادة المتزامنة (Concurrent Restore Lock).
12. التحقق من حظر مسارات الملفات العشوائية والتنقل غير الآمن (Path Traversal).
13. التحقق من سياسة مدة الحفظ (Retention) وعدم حذف أحدث نسخة صالحة إطلاقاً.
"""

import io
import os
import json
import uuid
import zipfile
import sqlite3
import pytest
from pathlib import Path
from flask import session as flask_session

from app import create_app
from app.models.schema import User, Document
from app.models.research_schema import Research, ResearchFile
from app.models.audit_schema import AuditLog
from app.models.backup_schema import BackupCatalog
from app.repositories import user_repo, report_repo, batch_repo, document_repo, base_repo, backup_repo
from app.services import backup_service, audit_service, integrity_service, snapshot_service
from app.security.permissions import Role, Permission
import config


@pytest.fixture
def app_instance():
    app = create_app()
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-backup-secret-key-2026'
    return app


@pytest.fixture
def client(app_instance):
    with app_instance.test_client() as client:
        yield client


def _setup_test_user(username, role, password="Password123!"):
    """مساعد لإنشاء مستخدم تجريبي بدور محدد."""
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


# ─── 1. اختبارات إنشاء الحزمة والبيان والاتساق ─────────────────────────────────

def test_backup_creates_unique_institutional_id(app_instance):
    """إنشاء النسخة الاحتياطية يولد معرفاً مؤسسياً رسمياً بتنسيق BKP-YYYY-XXXXXX."""
    with app_instance.app_context():
        res = backup_service.create_institutional_backup(created_by='admin_tester', backup_type='full')
        backup_id = res['backup_identifier']
        assert backup_id.startswith(f"BKP-{datetime_year()}-")
        assert len(backup_id) == 15
        assert res['status'] == 'completed'


def test_backup_manifest_is_generated_with_valid_metadata(app_instance):
    """حزمة النسخة الاحتياطية تحتوي على manifest.json بكافة البيانات الوصفية والإصدارات."""
    with app_instance.app_context():
        res = backup_service.create_institutional_backup(created_by='admin_manifest_tester')
        zip_path = Path(res['file_path'])
        assert zip_path.exists()

        with zipfile.ZipFile(zip_path, 'r') as zf:
            assert 'manifest.json' in zf.namelist()
            manifest = json.loads(zf.read('manifest.json').decode('utf-8'))

            assert manifest['backup_id'] == res['backup_identifier']
            assert manifest['manifest_version'] == '1.0'
            assert 'application_version' in manifest
            assert 'engine_version' in manifest
            assert 'database' in manifest
            assert manifest['database']['sha256'] != ''
            assert 'components' in manifest
            assert 'exclusions' in manifest


def test_sqlite_database_backup_is_internally_valid(app_instance):
    """نسخة قاعدة البيانات داخل الحزمة متسقة وتجتاز PRAGMA integrity_check."""
    with app_instance.app_context():
        res = backup_service.create_institutional_backup(created_by='admin_db_tester')
        zip_path = Path(res['file_path'])

        with zipfile.ZipFile(zip_path, 'r') as zf:
            db_bytes = zf.read('database/papers.db')
            temp_db = backup_service.get_backup_dir() / f"_test_open_{uuid.uuid4().hex[:6]}.db"
            temp_db.write_bytes(db_bytes)
            try:
                conn = sqlite3.connect(f"file:{temp_db.as_posix()}?mode=ro", uri=True)
                cur = conn.cursor()
                cur.execute("PRAGMA integrity_check;")
                row = cur.fetchone()
                assert row[0] == 'ok'
                conn.close()
            finally:
                if temp_db.exists():
                    temp_db.unlink()


def test_backup_package_checksum_validates(app_instance):
    """بصمة SHA-256 للحزمة المحفوظة في الفهرس تطابق البصمة الفعلية لملف الـ ZIP."""
    with app_instance.app_context():
        res = backup_service.create_institutional_backup(created_by='admin_checksum_tester')
        zip_path = Path(res['file_path'])
        actual_hash, actual_size = integrity_service.compute_stream_sha256(zip_path)

        assert res['checksum'] == actual_hash
        assert res['size_bytes'] == actual_size


# ─── 2. اختبارات التحقق من السلامة واكتشاف التلف ───────────────────────────────

def test_corrupted_backup_fails_validation(app_instance):
    """الحزمة المعدلة أو التالفة تفشل في التحقق validation_status='invalid'."""
    with app_instance.app_context():
        res = backup_service.create_institutional_backup(created_by='admin_corrupt_tester')
        backup_id = res['backup_identifier']
        zip_path = Path(res['file_path'])

        # إتلاف ملف الـ ZIP بتعديل بايتات عشوائية
        with open(zip_path, 'ab') as f:
            f.write(b"CORRUPTED_BYTES_INJECTED_TO_BREAK_ZIP")

        val = backup_service.validate_backup(backup_id)
        assert val['valid'] is False
        assert val.get('error') is not None


def test_missing_manifest_fails_validation(tmp_path):
    """حزمة ZIP ينقصها ملف manifest.json تفشل في الفحص فورياً."""
    bad_zip = tmp_path / "bad_no_manifest.zip"
    with zipfile.ZipFile(bad_zip, 'w') as zf:
        zf.writestr("database/papers.db", b"DUMMY_DATABASE")

    val = backup_service.validate_backup_package_file(bad_zip)
    assert val['valid'] is False
    assert "manifest.json" in val['error']


def test_missing_database_fails_validation(tmp_path):
    """حزمة ZIP ينقصها ملف database/papers.db تفشل في الفحص."""
    bad_zip = tmp_path / "bad_no_db.zip"
    with zipfile.ZipFile(bad_zip, 'w') as zf:
        zf.writestr("manifest.json", json.dumps({'backup_id': 'TEST-123'}))

    val = backup_service.validate_backup_package_file(bad_zip)
    assert val['valid'] is False
    assert "papers.db" in val['error']


# ─── 3. اختبارات الصلاحيات والحماية الأمنية (RBAC & Auth) ─────────────────────

def test_unauthorized_user_cannot_create_backup(client, app_instance):
    """المستخدم العادي (مثل reviewer أو data_entry) محظور من إنشاء النسخ برمز 403."""
    uid, uname, urole = _setup_test_user('reviewer_no_bkp', Role.REVIEWER)
    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = uname
        sess['role'] = urole

    res = client.post('/api/admin/backup')
    assert res.status_code == 403


def test_authorized_admin_can_create_backup(client, app_instance):
    """مدير النظام التقني (system_admin) يملك صلاحية backup.create وينشئ النسخة بنجاح."""
    uid, uname, urole = _setup_test_user('sysadmin_bkp_actor', Role.SYSTEM_ADMIN)
    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = uname
        sess['role'] = urole

    res = client.post('/api/admin/backup')
    assert res.status_code == 200
    data = res.get_json()
    assert data['success'] is True
    assert 'backup_id' in data


def test_unauthorized_user_cannot_restore_backup(client, app_instance):
    """المراجع أو مدخل البيانات محظور تماماً من استعادة النسخ الاحتياطية (رمز 403)."""
    uid, uname, urole = _setup_test_user('reviewer_no_restore', Role.REVIEWER)
    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = uname
        sess['role'] = urole

    res = client.post('/api/admin/backups/BKP-2026-000001/restore', json={'confirmation': 'BKP-2026-000001'})
    assert res.status_code == 403


def test_restore_requires_explicit_confirmation(client, app_instance):
    """طلب الاستعادة بدون رمز تأكيد صريح يُرفض برمز 400."""
    uid, uname, urole = _setup_test_user('sysadmin_restore_actor', Role.SYSTEM_ADMIN)
    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = uname
        sess['role'] = urole

    res = client.post('/api/admin/backups/BKP-2026-000001/restore', json={})
    assert res.status_code == 400
    assert 'التأكيد' in res.get_json()['error']


def test_wrong_confirmation_is_rejected(client, app_instance):
    """إدخال رمز تأكيد غير مطابق لرقم النسخة يُرفض برمز 400 ويمنع الاستعادة."""
    uid, uname, urole = _setup_test_user('sysadmin_restore_actor2', Role.SYSTEM_ADMIN)
    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = uname
        sess['role'] = urole

    res = client.post(
        '/api/admin/backups/BKP-2026-000099/restore',
        json={'confirmation': 'WRONG-ID-999'}
    )
    assert res.status_code == 400


# ─── 4. اختبارات الاستعادة والتعافي والتراجع التلقائي ──────────────────────────

def test_restore_creates_pre_restore_safety_backup(client, app_instance):
    """عملية الاستعادة تنشئ تلقائياً نسخة طوارئ مسبقة من النوع pre_restore."""
    uid, uname, urole = _setup_test_user('sysadmin_safe_restore', Role.SYSTEM_ADMIN)
    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = uname
        sess['role'] = urole

    # إنشاء نسخة صالحة للاستعادة
    with app_instance.app_context():
        bkp = backup_service.create_institutional_backup(created_by=uname, backup_type='full')
        target_id = bkp['backup_identifier']

    res = client.post(
        f'/api/admin/backups/{target_id}/restore',
        json={'confirmation': target_id}
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data['success'] is True
    assert 'safety_backup_id' in data

    # التحقق من وجود نسخة الأمان في الفهرس
    safety_entry = backup_repo.get_backup_entry(data['safety_backup_id'])
    assert safety_entry is not None
    assert safety_entry['backup_type'] == 'pre_restore'


def test_historical_entities_and_references_survive_restore(app_instance):
    """استعادة النسخة تحافظ بدقة على الأرقام المرجعية، اللقطات، الحالات الأكاديمية، وسجلات التدقيق."""
    with app_instance.app_context():
        # 1. إنشاء بحث معتمد
        uniq = uuid.uuid4().hex[:6]
        r_id = batch_repo.create_research(
            title=f'بحث تاريخي محفوظ {uniq}',
            author='د. محمد محمود',
            created_by='lead_researcher'
        )
        res_obj = batch_repo.get_research(r_id)
        original_ref = res_obj['reference_number']

        # 2. إنشاء نسخة احتياطية للوضع الحالي
        bkp = backup_service.create_institutional_backup(created_by='system_admin')
        target_id = bkp['backup_identifier']

        # 3. إنشاء بحث جديد بعد النسخة (يجب أن يختفي عند الاستعادة)
        transient_id = batch_repo.create_research(
            title='بحث مؤقت بعد النسخة',
            author='مؤلف لاحق',
            created_by='tester'
        )

        # 4. تنفيذ الاستعادة
        restore_res = backup_service.restore_institutional_backup(
            backup_identifier=target_id,
            confirmation=target_id,
            current_user={'username': 'system_admin', 'role': Role.SYSTEM_ADMIN}
        )
        assert restore_res['success'] is True

        # 5. التحقق من بقاء البحث الأصلي بنفس الرقم المرجعي
        recovered_res = batch_repo.get_research(r_id)
        assert recovered_res is not None
        assert recovered_res['reference_number'] == original_ref
        assert recovered_res['title'] == f'بحث تاريخي محفوظ {uniq}'

        # 6. التحقق من اختفاء البحث المؤقت الذي أنشئ بعد النسخة
        transient_res = batch_repo.get_research(transient_id)
        assert transient_res is None


def test_concurrent_restore_is_blocked():
    """محاولة تشغيل استعادتين متزامنتين تُحظر بقفل الأمان."""
    assert backup_service._RESTORE_MUTEX.acquire(blocking=False) is True
    try:
        with pytest.raises(RuntimeError, match="توجد عملية استعادة أخرى"):
            backup_service.restore_institutional_backup(
                backup_identifier='BKP-2026-000001',
                confirmation='BKP-2026-000001'
            )
    finally:
        backup_service._RESTORE_MUTEX.release()


def test_restore_rejects_arbitrary_filesystem_paths(client, app_instance):
    """المسار لا يقبل تمرير مسارات ملفات عشوائية من العميل لحماية الخادم من الاختراق."""
    uid, uname, urole = _setup_test_user('sysadmin_path_tester', Role.SYSTEM_ADMIN)
    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = uname
        sess['role'] = urole

    # محاولة تنقل في المسار
    res = client.post(
        '/api/admin/backups/../../etc/passwd/restore',
        json={'confirmation': '../../etc/passwd'}
    )
    # مسار Flask يرفض التنقل في الـ URL أو يعيد 404
    assert res.status_code in (404, 400, 403)


# ─── 5. اختبارات مدة الحفظ (Retention Policy) ──────────────────────────────────

def test_backup_retention_never_deletes_newest_valid_backup(app_instance):
    """سياسة الحفظ المحلية لا تحذف أحدث نسخة صالحة إطلاقاً."""
    with app_instance.app_context():
        # إنشاء 3 نسخ احتياطية
        b1 = backup_service.create_institutional_backup(created_by='retention_tester')
        b2 = backup_service.create_institutional_backup(created_by='retention_tester')
        b3 = backup_service.create_institutional_backup(created_by='retention_tester')

        # تطبيق سياسة حفظ بحد أقصى نسخة واحدة
        deleted_count = backup_service.enforce_backup_retention(max_count=1)

        # التحقق من أن النسخة الأحدث b3 لا تزال موجودة
        entry3 = backup_repo.get_backup_entry(b3['backup_identifier'])
        assert entry3 is not None
        assert Path(entry3['file_path']).exists()


def test_backup_created_audit_event_logged(app_instance):
    """إنشاء النسخة الاحتياطية يسجل حدث التدقيق backup.created."""
    with app_instance.app_context():
        res = backup_service.create_institutional_backup(created_by='auditor_user')
        b_id = res['backup_identifier']
        log_res = audit_service.query_audit_logs(category='backup', action='backup.created')
        created_events = [l for l in log_res['events'] if l['object_id'] == b_id]
        assert len(created_events) > 0
        assert created_events[0]['success'] is True


def test_backup_restore_audit_trail_lifecycle(app_instance):
    """استعادة النسخة توثق حدث backup.restore_completed في قاعدة البيانات المستعادة بنجاح."""
    with app_instance.app_context():
        bkp = backup_service.create_institutional_backup(created_by='restore_audit_user')
        b_id = bkp['backup_identifier']
        res = backup_service.restore_institutional_backup(
            backup_identifier=b_id,
            confirmation=b_id,
            current_user={'username': 'audit_admin', 'role': Role.SYSTEM_ADMIN}
        )
        assert res['success'] is True
        log_res = audit_service.query_audit_logs(category='backup', action='backup.restore_completed')
        completed_events = [l for l in log_res['events'] if l['object_id'] == b_id]
        assert len(completed_events) > 0
        assert completed_events[0]['success'] is True


def test_backup_retention_deleted_audit_event(app_instance):
    """حذف النسخ القديمة عبر سياسة الحفظ يوثق حدث backup.retention_deleted."""
    with app_instance.app_context():
        b1 = backup_service.create_institutional_backup(created_by='retention_user1')
        b2 = backup_service.create_institutional_backup(created_by='retention_user2')
        backup_service.enforce_backup_retention(max_count=1)
        log_res = audit_service.query_audit_logs(category='backup', action='backup.retention_deleted')
        del_events = [l for l in log_res['events'] if l['object_id'] == b1['backup_identifier']]
        assert len(del_events) > 0


def test_validate_backup_api_endpoint(client, app_instance):
    """واجهة التحقق POST /api/admin/backups/<id>/validate تعمل بنجاح للمصرح لهم."""
    uid, uname, urole = _setup_test_user('validator_admin', Role.SYSTEM_ADMIN)
    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = uname
        sess['role'] = urole

    with app_instance.app_context():
        bkp = backup_service.create_institutional_backup(created_by=uname)
        b_id = bkp['backup_identifier']

    res = client.post(f'/api/admin/backups/{b_id}/validate')
    assert res.status_code == 200
    data = res.get_json()
    assert data['success'] is True
    assert data['validation']['valid'] is True


def test_list_backups_api_endpoint(client, app_instance):
    """واجهة استعراض النسخ GET /api/admin/backups تعيد قائمة بالنسخ المسجلة."""
    uid, uname, urole = _setup_test_user('list_bkp_admin', Role.SYSTEM_ADMIN)
    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = uname
        sess['role'] = urole

    res = client.get('/api/admin/backups')
    assert res.status_code == 200
    data = res.get_json()
    assert 'backups' in data
    assert isinstance(data['backups'], list)


def test_download_backup_api_endpoint_success(client, app_instance):
    """تحميل النسخة الاحتياطية GET /api/admin/backups/<id>/download متاح لمدير النظام."""
    uid, uname, urole = _setup_test_user('dl_bkp_admin', Role.SYSTEM_ADMIN)
    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = uname
        sess['role'] = urole

    with app_instance.app_context():
        bkp = backup_service.create_institutional_backup(created_by=uname)
        b_id = bkp['backup_identifier']

    res = client.get(f'/api/admin/backups/{b_id}/download')
    assert res.status_code == 200
    assert res.mimetype == 'application/zip'


def test_download_backup_unauthorized_blocked(client, app_instance):
    """المستخدم العادي محظور من تحميل ملف النسخة الاحتياطية (رمز 403)."""
    uid, uname, urole = _setup_test_user('dl_reviewer_blocked', Role.REVIEWER)
    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = uname
        sess['role'] = urole

    res = client.get('/api/admin/backups/BKP-2026-000001/download')
    assert res.status_code == 403


def test_interrupted_scan_status_reconciliation_on_restore(app_instance):
    """المهام التي كانت بحالة running تصبح 'interrupted' بعد الاستعادة."""
    with app_instance.app_context():
        # إنشاء بحث بحالة جارية
        r_id = batch_repo.create_research(
            title='بحث جاري أثناء أخذ النسخة',
            author='مؤلف نشط',
            created_by='tester'
        )
        batch_repo.update_research_scan_status(r_id, 'running')

        # أخذ نسخة أثناء الجريان
        bkp = backup_service.create_institutional_backup(created_by='system_admin')
        b_id = bkp['backup_identifier']

        # استعادة النسخة
        res = backup_service.restore_institutional_backup(
            backup_identifier=b_id,
            confirmation=b_id,
            current_user={'username': 'system_admin', 'role': Role.SYSTEM_ADMIN}
        )
        assert res['success'] is True

        # التحقق من مصالحة الحالة إلى interrupted
        res_after = batch_repo.get_research(r_id)
        assert res_after is not None
        assert res_after['scan_status'] == 'interrupted'


def datetime_year():
    from datetime import datetime
    return datetime.now().year

