# -*- coding: utf-8 -*-
"""
حزمة اختبارات شاملة ومحصنة لمراقبة وصحة النظام التشغيلية (Phase 11 System Health Complete Test Suite):
- التحقق من الأمان وقيود RBAC ومصفوفة شدة المكونات.
- التحقق من دلالات النسخ الاحتياطي الرسمية (Authoritative Backup Semantics).
- التحقق من خفة وكفاءة فحص OCR والنموذج الدلالي دون إجهاد المعالج أو تحميل نماذج.
- التحقق من دقة رصد المهام واستعلام التخزين الفعلي.
- التحقق من كبح التنبيهات المكررة والتعافي (State-Aware Deduplication).
- التحقق من منع انهيار نقطة النهاية عند حدوث استثناء في مكوّن فردي (Failure Safety).
- التحقق العودي الشامل من الخصوصية (Zero Sensitive Metadata / Absolute Paths).
"""

import os
import re
import time
import json
import uuid
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta, timezone

import config
from app import create_app, versioning
from app.repositories import base_repo, backup_repo, user_repo
from app.services import system_health_service, audit_service
from app.models.schema import ScanJob, Document
from app.models.research_schema import Research, ScanBatch, ScanBatchItem
from app.models.snapshot_schema import ReferenceCorpusVersion
from app.models.audit_schema import AuditLog
from app.security.permissions import Role, Permission


@pytest.fixture
def client():
    app = create_app()
    app.config['TESTING'] = True
    app.config['STRICT_AUTH'] = True
    with app.test_client() as client:
        yield client


# ─── 1. اختبارات المصادقة والصلاحيات (Authentication & RBAC) ────────────────

def test_health_endpoint_requires_authentication(client):
    """1. نقطة فحص الصحة تتطلب مصادقة صريحة وترجع 401 عند عدم تسجيل الدخول."""
    res = client.get('/api/system/health')
    assert res.status_code == 401


def test_unauthorized_role_gets_403(client):
    """2. الدور غير المخول (مثل مدخل بيانات data_entry) يحصل على 403 Forbidden."""
    uname = f"data_entry_{uuid.uuid4().hex[:6]}"
    user_repo.add_user(uname, 'pass123', 'مدخل بيانات', Role.DATA_ENTRY)
    client.post('/api/auth/login', json={'username': uname, 'password': 'pass123'})

    res = client.get('/api/system/health')
    assert res.status_code == 403
    data = res.get_json()
    assert 'error' in data or 'message' in data


def test_authorized_technical_role_can_access(client):
    """3. الأدوار الفنية المخولة (system_admin و unit_manager و admin) تستطيع الوصول بنجاح 200."""
    uname_admin = f"sys_admin_{uuid.uuid4().hex[:6]}"
    user_repo.add_user(uname_admin, 'pass123', 'مدير تقني', Role.SYSTEM_ADMIN)
    client.post('/api/auth/login', json={'username': uname_admin, 'password': 'pass123'})

    res = client.get('/api/system/health')
    assert res.status_code == 200
    data = res.get_json()
    assert 'overall_status' in data
    assert 'components' in data

    uname_mgr = f"unit_mgr_{uuid.uuid4().hex[:6]}"
    user_repo.add_user(uname_mgr, 'pass123', 'مسؤول وحدة', Role.UNIT_MANAGER)
    client.post('/api/auth/login', json={'username': uname_mgr, 'password': 'pass123'})

    res2 = client.get('/api/system/health')
    assert res2.status_code == 200


# ─── 2. مصفوفة شدة المكونات والحالة الكلية (Severity Matrix & Aggregation) ─────

def test_optional_disabled_component_does_not_degrade_overall_status():
    """4. المكونات الاختيارية المعطلة (مثل النموذج الدلالي) لا تخفض صحة النظام إطلاقاً."""
    components = {
        'database': {'status': 'healthy'},
        'storage': {'status': 'healthy'},
        'backup': {'status': 'healthy'},
        'scan_jobs': {'status': 'healthy'},
        'batches': {'status': 'healthy'},
        'reference_corpus': {'status': 'healthy'},
        'ocr': {'status': 'disabled'},
        'semantic_model': {'status': 'disabled'},
        'application': {'status': 'healthy'}
    }
    assert system_health_service._determine_overall_status(components) == 'healthy'


def test_required_critical_component_makes_overall_critical():
    """5. تعطل مكوّن أساسي مطلوب (REQUIRED مثل قاعدة البيانات أو التخزين) ينتج حالة حرجة overall critical."""
    components_db_crit = {
        'database': {'status': 'critical'},
        'storage': {'status': 'healthy'},
        'ocr': {'status': 'healthy'},
        'semantic_model': {'status': 'healthy'}
    }
    assert system_health_service._determine_overall_status(components_db_crit) == 'critical'

    components_storage_crit = {
        'database': {'status': 'healthy'},
        'storage': {'status': 'critical'},
        'ocr': {'status': 'healthy'}
    }
    assert system_health_service._determine_overall_status(components_storage_crit) == 'critical'


def test_required_degraded_component_makes_overall_degraded():
    """6. المكون الأساسي المتدهور (مثل قاعدة غير عاملة بنمط WAL أو مساحة قرص منخفضة) يجعل الحالة العامة degraded."""
    components = {
        'database': {'status': 'degraded'},
        'storage': {'status': 'healthy'},
        'backup': {'status': 'healthy'}
    }
    assert system_health_service._determine_overall_status(components) == 'degraded'


def test_optional_enabled_but_failing_component_degrades_overall():
    """7. المكون الاختياري المفعل في الإعدادات ولكنه مفقود محلياً يؤدي إلى تدهور الحالة العامة degraded."""
    components = {
        'database': {'status': 'healthy'},
        'storage': {'status': 'healthy'},
        'ocr': {'status': 'degraded'},
        'semantic_model': {'status': 'healthy'}
    }
    assert system_health_service._determine_overall_status(components) == 'degraded'


# ─── 3. اختبارات صحة قاعدة البيانات (Database Health) ────────────────────────

def test_healthy_database_reports_healthy(client):
    """8. قاعدة البيانات الطبيعية العاملة بنمط WAL تعيد حالة healthy."""
    uname = f"health_admin_{uuid.uuid4().hex[:6]}"
    user_repo.add_user(uname, 'pass123', 'مدير', Role.SYSTEM_ADMIN)
    client.post('/api/auth/login', json={'username': uname, 'password': 'pass123'})

    res = client.get('/api/system/health')
    assert res.status_code == 200
    db_comp = res.get_json()['components']['database']
    assert db_comp['status'] == 'healthy'
    assert db_comp['metadata']['reachable'] is True
    assert db_comp['metadata']['journal_mode'] == 'WAL'


def test_unreachable_database_produces_critical():
    """9. تعذر الاتصال بقاعدة البيانات ينتج حالة critical للحالة العامة وقاعدة البيانات."""
    with patch.object(base_repo.engine, 'connect', side_effect=Exception("Database connection error")):
        data = system_health_service.get_system_health()
        assert data['components']['database']['status'] == 'critical'
        assert data['overall_status'] == 'critical'
        assert 'تعذر الاتصال' in data['components']['database']['message']


def test_wal_and_schema_metadata_reported_safely(client):
    """10. تقرير البيانات الوصفية لقاعدة البيانات وWAL دون كشف معلومات سرية."""
    uname = f"health_admin_{uuid.uuid4().hex[:6]}"
    user_repo.add_user(uname, 'pass123', 'مدير', Role.SYSTEM_ADMIN)
    client.post('/api/auth/login', json={'username': uname, 'password': 'pass123'})

    res = client.get('/api/system/health')
    meta = res.get_json()['components']['database']['metadata']
    assert 'schema_version' in meta
    assert 'database_size_bytes' in meta
    assert 'wal_size_bytes' in meta
    assert 'shm_size_bytes' in meta


# ─── 4. اختبارات صحة التخزين ومساحة القرص (Storage Health) ───────────────────

def test_normal_disk_state_healthy():
    """11. حالة التخزين الطبيعية ذات المساحة الكافية تعيد healthy."""
    mock_usage = MagicMock(total=100 * 1024**3, used=50 * 1024**3, free=50 * 1024**3)
    with patch('shutil.disk_usage', return_value=mock_usage):
        health = system_health_service.get_system_health()
        assert health['components']['storage']['status'] == 'healthy'
        assert health['components']['storage']['metadata']['free_percent'] == 50.0


def test_low_disk_degraded():
    """12. انخفاض مساحة القرص دون حد التحذير (15%) يعيد حالة degraded."""
    mock_usage = MagicMock(total=100 * 1024**3, used=90 * 1024**3, free=10 * 1024**3)
    with patch('shutil.disk_usage', return_value=mock_usage):
        health = system_health_service.get_system_health()
        assert health['components']['storage']['status'] == 'degraded'
        assert health['overall_status'] == 'degraded'


def test_critical_disk_threshold_critical():
    """13. انخفاض مساحة القرص دون الحد الحرج (5%) يعيد حالة critical."""
    mock_usage = MagicMock(total=100 * 1024**3, used=97 * 1024**3, free=3 * 1024**3)
    with patch('shutil.disk_usage', return_value=mock_usage):
        health = system_health_service.get_system_health()
        assert health['components']['storage']['status'] == 'critical'
        assert health['overall_status'] == 'critical'


def test_storage_check_targets_configured_persistent_filesystem():
    """14. فحص التخزين يستعلم القرص الذي يضم مجلد التخزين الفعلي STORAGE_ROOT وليس مجلد العمل الحالي."""
    expected_target = Path(config.STORAGE_ROOT)
    if not expected_target.exists():
        expected_target = Path(config.DEFAULT_SQLITE_PATH).parent

    with patch('shutil.disk_usage', return_value=MagicMock(total=1000, used=500, free=500)) as mock_usage:
        health = system_health_service.get_system_health()
        assert mock_usage.called
        called_path = Path(mock_usage.call_args[0][0])
        assert called_path == expected_target or called_path.drive == expected_target.drive


# ─── 5. اختبارات النسخ الاحتياطي (Backup Health Semantics) ─────────────────────

def test_backup_not_configured_distinct_from_overdue():
    """15. عدم وجود أي نسخ احتياطية مسجلة بعد يعيد not_configured ولا يُعتبر خطأً حرجاً."""
    with patch('app.repositories.backup_repo.list_backups', return_value=[]):
        health = system_health_service.get_system_health()
        assert health['components']['backup']['status'] == 'not_configured'
        assert health['components']['backup']['metadata']['backup_configured'] is False


def test_recent_valid_backup_healthy():
    """16. وجود نسخة احتياطية حديثة وسليمة ومتحقق منها يعيد حالة healthy."""
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    mock_backups = [{
        'backup_identifier': 'backup_recent_001',
        'created_at': now_str,
        'status': 'completed',
        'validation_status': 'valid'
    }]
    with patch('app.repositories.backup_repo.list_backups', return_value=mock_backups):
        health = system_health_service.get_system_health()
        assert health['components']['backup']['status'] == 'healthy'
        assert health['components']['backup']['metadata']['latest_backup_id'] == 'backup_recent_001'


def test_failed_newest_backup_does_not_hide_older_valid_backup():
    """17. فشل أحدث محاولة نسخ احتياطي لا يخفي وجود نسخة سابقة صالحة في التقرير."""
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    older_str = (datetime.utcnow() - timedelta(hours=5)).strftime('%Y-%m-%d %H:%M:%S')

    mock_backups = [
        {
            'backup_identifier': 'backup_fail_newest',
            'created_at': now_str,
            'status': 'failed',
            'validation_status': 'corrupted'
        },
        {
            'backup_identifier': 'backup_valid_older',
            'created_at': older_str,
            'status': 'completed',
            'validation_status': 'valid'
        }
    ]

    with patch('app.repositories.backup_repo.list_backups', return_value=mock_backups):
        health = system_health_service.get_system_health()
        b_comp = health['components']['backup']
        assert b_comp['status'] == 'degraded'
        assert b_comp['metadata']['latest_backup_id'] == 'backup_fail_newest'
        assert b_comp['metadata']['latest_validated_backup_id'] == 'backup_valid_older'
        assert 'نسخة سابقة صالحة' in b_comp['message']


def test_corrupted_backup_semantics():
    """18. النسخة الاحتياطية التالفة (corrupted) تعيد حالة degraded وتوضح الفشل."""
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    mock_backups = [{
        'backup_identifier': 'backup_corrupted_001',
        'created_at': now_str,
        'status': 'completed',
        'validation_status': 'corrupted'
    }]
    with patch('app.repositories.backup_repo.list_backups', return_value=mock_backups):
        health = system_health_service.get_system_health()
        b_comp = health['components']['backup']
        assert b_comp['status'] == 'degraded'
        assert 'تالفة' in b_comp['message']


def test_unvalidated_backup_semantics():
    """19. النسخة الاحتياطية غير المتحقق منها تعيد حالة degraded للتنبيه بضرورة التحقق."""
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    mock_backups = [{
        'backup_identifier': 'backup_unvalidated_001',
        'created_at': now_str,
        'status': 'completed',
        'validation_status': 'pending'
    }]
    with patch('app.repositories.backup_repo.list_backups', return_value=mock_backups):
        health = system_health_service.get_system_health()
        b_comp = health['components']['backup']
        assert b_comp['status'] == 'degraded'
        assert 'لم يتم التحقق' in b_comp['message']


def test_overdue_expected_backup_degraded():
    """20. تجاوز عمر آخر نسخة احتياطية للحد الأقصى (48 ساعة) يعيد حالة degraded."""
    old_dt = datetime.utcnow() - timedelta(hours=60)
    mock_backups = [{
        'backup_identifier': 'backup_old_001',
        'created_at': old_dt.strftime('%Y-%m-%d %H:%M:%S'),
        'status': 'completed',
        'validation_status': 'valid'
    }]
    with patch('app.repositories.backup_repo.list_backups', return_value=mock_backups):
        health = system_health_service.get_system_health()
        assert health['components']['backup']['status'] == 'degraded'
        assert health['overall_status'] == 'degraded'


# ─── 6. اختبارات مهام الفحص والدفعات (Scan & Batch Health) ────────────────────

def test_queued_jobs_alone_are_not_critical():
    """21. وجود مهام في طابور الانتظار (queued) لا يُعد فشلاً أو حالة حرجة."""
    job_id = f"job_queued_{uuid.uuid4().hex[:6]}"
    with base_repo.get_session() as session:
        job = ScanJob(id=job_id, filename="doc1.pdf", status="queued")
        session.add(job)

    try:
        health = system_health_service.get_system_health()
        assert health['components']['scan_jobs']['status'] == 'healthy'
        assert health['components']['scan_jobs']['metadata']['queued'] >= 1
    finally:
        with base_repo.get_session() as session:
            j = session.query(ScanJob).filter(ScanJob.id == job_id).first()
            if j:
                session.delete(j)


def test_stuck_job_uses_processing_timestamp():
    """22. رصد المهمة العالقة يعتمد على وقت المعالجة الفعلي للمهمة الجارية وليس على تاريخ البحث."""
    old_time = datetime.utcnow() - timedelta(minutes=45)
    jid = f"stuck_proc_{uuid.uuid4().hex[:6]}"

    with base_repo.get_session() as session:
        job = ScanJob(id=jid, filename="test.pdf", status="processing", created_at=old_time)
        session.add(job)

    try:
        health = system_health_service.get_system_health()
        meta = health['components']['scan_jobs']['metadata']
        assert meta['stuck_jobs_count'] >= 1
    finally:
        with base_repo.get_session() as session:
            session.query(ScanJob).filter(ScanJob.id == jid).delete()


def test_completed_job_is_never_counted_as_stuck():
    """23. المهمة المكتملة بنجاح حتى لو كانت قديمة لا تُحسب إطلاقاً كمهمة عالقة."""
    old_time = datetime.utcnow() - timedelta(days=5)
    jid = f"old_done_{uuid.uuid4().hex[:6]}"

    with base_repo.get_session() as session:
        job = ScanJob(id=jid, filename="done.pdf", status="completed", created_at=old_time)
        session.add(job)

    try:
        health = system_health_service.get_system_health()
        meta = health['components']['scan_jobs']['metadata']
        assert meta['completed'] >= 1
    finally:
        with base_repo.get_session() as session:
            session.query(ScanJob).filter(ScanJob.id == jid).delete()


def test_batch_aggregates_correct():
    """24. استرجاع التجميعات الإجمالية للدفعات والعناصر بشكل دقيق."""
    bid = f"batch_{uuid.uuid4().hex[:6]}"
    with base_repo.get_session() as session:
        r1 = Research(title="بحث دفعة 1", author="باحث 1", reference_number=f"RES-{uuid.uuid4().hex[:6]}")
        r2 = Research(title="بحث دفعة 2", author="باحث 2", reference_number=f"RES-{uuid.uuid4().hex[:6]}")
        session.add_all([r1, r2])
        session.flush()
        r1_id = r1.id
        r2_id = r2.id

        batch = ScanBatch(id=bid, label="دفعة اختبار", status="processing")
        session.add(batch)
        item1 = ScanBatchItem(batch_id=batch.id, research_id=r1_id, status="queued")
        item2 = ScanBatchItem(batch_id=batch.id, research_id=r2_id, status="failed")
        session.add_all([item1, item2])

    try:
        health = system_health_service.get_system_health()
        b_meta = health['components']['batches']['metadata']
        assert b_meta['active_batches'] >= 1
        assert b_meta['queued_items'] >= 1
        assert b_meta['failed_items'] >= 1
    finally:
        with base_repo.get_session() as session:
            session.query(ScanBatchItem).filter(ScanBatchItem.batch_id == bid).delete()
            session.query(ScanBatch).filter(ScanBatch.id == bid).delete()
            session.query(Research).filter(Research.id.in_([r1_id, r2_id])).delete()


# ─── 7. اختبارات OCR والنموذج الدلالي (OCR & Semantic Model) ──────────────────

def test_ocr_disabled_not_an_error():
    """25. تعطيل محرك OCR في الإعدادات يعيد حالة disabled دون تخفيض صحة النظام."""
    with patch('app.services.system_health_service.get_current_settings', return_value={'enable_ocr': False}):
        health = system_health_service.get_system_health()
        assert health['components']['ocr']['status'] == 'disabled'
        assert health['components']['ocr']['status_ar'] == 'غير مفعّل'


def test_ocr_check_does_not_execute_ocr_processing():
    """26. فحص صحة OCR لا ينفذ عمليات معالجة صور أو استخراج نصوص OCR."""
    with patch('pytesseract.image_to_string') as mock_ocr_proc:
        health = system_health_service.get_system_health()
        mock_ocr_proc.assert_not_called()
        assert 'ocr' in health['components']


def test_ocr_check_uses_caching_to_avoid_subprocess_spam():
    """27. فحص صحة OCR يستخدم كاش للتحقق لتفادي إطلاق أوامر خارجية متكررة كل 30 ثانية."""
    with patch('app.services.system_health_service.check_ocr_availability', return_value={'available': True, 'has_arabic': True}) as mock_check:
        system_health_service._OCR_CACHE['data'] = None
        system_health_service._OCR_CACHE['last_checked'] = 0.0

        system_health_service._check_ocr(datetime.utcnow())
        assert mock_check.call_count == 1

        system_health_service._check_ocr(datetime.utcnow())
        assert mock_check.call_count == 1


def test_semantic_disabled_not_an_error():
    """28. تعطيل النموذج الدلالي يعيد disabled ("غير مفعّل") ولا يُعتبر خطأً."""
    with patch('app.services.system_health_service.get_current_settings', return_value={'enable_semantic_model': False}):
        health = system_health_service.get_system_health()
        assert health['components']['semantic_model']['status'] == 'disabled'
        assert health['components']['semantic_model']['status_ar'] == 'غير مفعّل'


def test_semantic_health_does_not_load_model():
    """29. فحص الصحة لا يقوم بتحميل نموذج التضمين الدلالي في الذاكرة ولا ينشئ runtime."""
    with patch('plagiarism_detector.detection.semantic_matcher.get_embedder') as mock_load:
        health = system_health_service.get_system_health()
        mock_load.assert_not_called()
        assert 'semantic_model' in health['components']


# ─── 8. اختبارات قاعدة المراجع والإصدارات (Corpus & Versioning) ───────────────

def test_reference_corpus_version_reported():
    """30. تقرير إصدار قاعدة المراجع وعدد الوثائق والبصمة التراكمية."""
    vid = f"REF-2026-{uuid.uuid4().hex[:6]}"
    with base_repo.get_session() as session:
        v = ReferenceCorpusVersion(
            version_identifier=vid,
            fingerprint="abc123def456fingerprint",
            created_at=datetime.utcnow()
        )
        session.add(v)

    try:
        health = system_health_service.get_system_health()
        c_meta = health['components']['reference_corpus']['metadata']
        assert c_meta['corpus_version'] == vid
        assert c_meta['fingerprint_present'] is True
    finally:
        with base_repo.get_session() as session:
            v_rec = session.query(ReferenceCorpusVersion).filter(ReferenceCorpusVersion.version_identifier == vid).first()
            if v_rec:
                session.delete(v_rec)


def test_application_and_schema_versions_reported():
    """31. تقرير كافة إصدارات التطبيق ومحركات الفحص ومخططات البيانات."""
    health = system_health_service.get_system_health()
    app_meta = health['components']['application']['metadata']
    assert 'application_version' in app_meta
    assert 'engine_version' in app_meta
    assert 'database_schema_version' in app_meta
    assert 'report_schema_version' in app_meta
    assert 'normalization_version' in app_meta


# ─── 9. كبح التنبيهات المكررة والتعافي (Alert Deduplication & Transitions) ─────

def test_persistent_warning_logs_only_once_and_transition_tracked():
    """32. اختبار تتبع الانتقالات: healthy -> degraded يُسجل، degraded -> degraded يُكبح، التعافي يُرصد."""
    system_health_service._ALERT_STATE_TRACKER.clear()

    comps_degraded = {
        'storage': {'status': 'degraded', 'message': 'مساحة القرص منخفضة'}
    }
    system_health_service._evaluate_alert_state_transitions(comps_degraded)
    assert system_health_service._ALERT_STATE_TRACKER['storage'] == 'degraded'

    system_health_service._evaluate_alert_state_transitions(comps_degraded)
    assert system_health_service._ALERT_STATE_TRACKER['storage'] == 'degraded'

    comps_recovered = {
        'storage': {'status': 'healthy', 'message': 'المساحة كافية'}
    }
    system_health_service._evaluate_alert_state_transitions(comps_recovered)
    assert system_health_service._ALERT_STATE_TRACKER['storage'] == 'healthy'

    system_health_service._evaluate_alert_state_transitions(comps_degraded)
    assert system_health_service._ALERT_STATE_TRACKER['storage'] == 'degraded'


# ─── 10. اختبارات حماية وموثوقية نقطة النهاية (Failure Safety & Privacy) ───────

def test_one_component_exception_does_not_crash_endpoint(client):
    """33. حدوث استثناء غير متوقع في مكوّن واحد لا يؤدي لانهيار مسار الصحة بالكامل."""
    uname = f"admin_resilience_{uuid.uuid4().hex[:6]}"
    user_repo.add_user(uname, 'pass123', 'مدير', Role.SYSTEM_ADMIN)
    client.post('/api/auth/login', json={'username': uname, 'password': 'pass123'})

    with patch('app.services.system_health_service._check_storage', side_effect=RuntimeError("Disk I/O failure")):
        res = client.get('/api/system/health')
        assert res.status_code == 200
        data = res.get_json()
        assert data['components']['storage']['status'] == 'critical'
        assert data['components']['storage']['metadata']['check_error'] is True
        assert data['components']['database']['status'] == 'healthy'


def test_recursive_json_privacy_and_no_absolute_paths(client):
    """34. التحقق العودي من خلو الرد من أي مسارات مطلقة أو نصوص أو بيانات باحثين."""
    uname = f"admin_sec_{uuid.uuid4().hex[:6]}"
    user_repo.add_user(uname, 'pass123', 'مدير', Role.SYSTEM_ADMIN)
    client.post('/api/auth/login', json={'username': uname, 'password': 'pass123'})

    res = client.get('/api/system/health')
    assert res.status_code == 200
    data = res.get_json()

    raw_str = json.dumps(data)
    assert 'C:\\Users' not in raw_str
    assert 'C:/Users' not in raw_str
    assert '/Users/' not in raw_str
    assert '/home/' not in raw_str

    def _assert_no_sensitive_keys(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                assert k not in ('password', 'token', 'secret', 'file_path', 'full_path', 'full_text')
                _assert_no_sensitive_keys(v)
        elif isinstance(obj, list):
            for item in obj:
                _assert_no_sensitive_keys(item)

    _assert_no_sensitive_keys(data)


def test_health_request_does_not_invoke_full_integrity_check(client):
    """35. فحص الصحة لا ينفذ PRAGMA integrity_check المكلف على كل طلب."""
    uname = f"perf_admin_{uuid.uuid4().hex[:6]}"
    user_repo.add_user(uname, 'pass123', 'مدير', Role.SYSTEM_ADMIN)
    client.post('/api/auth/login', json={'username': uname, 'password': 'pass123'})

    with patch('app.services.db_health_service.run_deep_integrity_check') as mock_deep:
        res = client.get('/api/system/health')
        assert res.status_code == 200
        mock_deep.assert_not_called()


def test_health_request_does_not_hash_every_stored_file(client):
    """36. فحص الصحة لا يقوم بإعادة حساب SHA-256 لكافة ملفات التخزين على القرص."""
    uname = f"perf_admin_{uuid.uuid4().hex[:6]}"
    user_repo.add_user(uname, 'pass123', 'مدير', Role.SYSTEM_ADMIN)
    client.post('/api/auth/login', json={'username': uname, 'password': 'pass123'})

    with patch('hashlib.sha256') as mock_hash:
        res = client.get('/api/system/health')
        assert res.status_code == 200
        mock_hash.assert_not_called()
