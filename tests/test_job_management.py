# -*- coding: utf-8 -*-
"""
حزمة الاختبارات الشاملة لمنظومة إدارة طابور المهام والتزامن والأداء (Phase 17 Job Management Test Suite):
- اختبارات آلة الحالات والسحب الذري الآمن (Atomic Multi-Process Claiming).
- اختبارات سقف التزامن وضغط العمل الخلفي (Concurrency Bounds & Backpressure).
- اختبارات عدالة الجدولة ومنع تجويع الأبحاث الفردية (Batch Fairness & Anti-Starvation).
- اختبارات نبض الحياة ورصد المهام العالقة (Heartbeat & Stuck Detection).
- اختبارات الإلغاء التعاوني المنضبط (Cooperative Cancellation).
- اختبارات سياسة التراجع الزمني وإعادة المحاولة (Bounded Retries & Exponential Backoff).
- اختبارات استعادة التشغيل التلقائية عند الإقلاع (Restart Recovery).
- اختبارات ترقية الفهرس المرحلية (Index Staging & Atomic Promotion).
- اختبارات أمان العزل وصلاحيات الواجهة البرمجية (API Privacy & RBAC).
- اختبارات الأداء والمحاكاة الحملية (Performance Benchmarks & Load Simulation).
"""

import os
import time
import uuid
import json
import pytest
import sqlite3
import threading
import multiprocessing
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import config
from app.repositories import base_repo, report_repo
from app.models.schema import JobRecord, IndexStateRecord, ScanJob
from app.services import job_queue_service
from app.services.job_queue_service import JobType, JobStatus
from app.errors.error_codes import ErrorCode
from plagiarism_detector.reporting.report_builder import build_pipeline_index, trigger_async_index_rebuild, get_pipeline_index


from app import create_app


@pytest.fixture
def app_instance():
    app = create_app()
    app.config['TESTING'] = True
    app.config['STRICT_AUTH'] = False
    return app


@pytest.fixture
def client(app_instance):
    with app_instance.test_client() as client:
        yield client


@pytest.fixture(autouse=True)
def clean_job_records():
    """تنظيف سجلات مهام الاختبار قبل وبعد كل اختبار."""
    yield
    with base_repo.get_session() as session:
        session.query(JobRecord).delete()
        session.commit()


# ─── 1. اختبارات إدراج واسترجاع وسحب المهام (Enqueue & State Machine) ─────────


def test_enqueue_and_get_job():
    """1. إدراج مهمة جديدة في الطابور واسترجاعها بنجاح مع التحقق من الحقول الأساسية."""
    job_id, err = job_queue_service.enqueue_job(
        job_type=JobType.SCAN,
        payload={'file_path': 'sample.pdf', 'title': 'بحث تجريبي'},
        requested_by='researcher_1',
        priority=5,
        research_id=101,
        scan_execution_id='exec-sample-101'
    )

    assert err is None
    assert job_id is not None

    job = job_queue_service.get_job(job_id)
    assert job is not None
    assert job['id'] == job_id
    assert job['job_type'] == JobType.SCAN
    assert job['status'] == JobStatus.QUEUED
    assert job['priority'] == 5
    assert job['requested_by'] == 'researcher_1'
    assert job['research_id'] == 101
    assert job['scan_execution_id'] == 'exec-sample-101'
    assert job['payload']['title'] == 'بحث تجريبي'


def test_backpressure_max_queued_jobs():
    """2. رفض استقبال مهام جديدة عندما يصل الطابور إلى الحد الأقصى (JOB_QUEUE_FULL)."""
    with patch.object(config, 'MAX_QUEUED_JOBS', 3):
        # ملء الطابور بـ 3 مهام
        for i in range(3):
            jid, err = job_queue_service.enqueue_job(job_type=JobType.SCAN, requested_by='user1')
            assert err is None

        # المحاولة الرابعة يجب أن تُرفض
        jid4, err4 = job_queue_service.enqueue_job(job_type=JobType.SCAN, requested_by='user1')
        assert jid4 is None
        assert err4 == ErrorCode.JOB_QUEUE_FULL


def test_index_rebuild_deduplication():
    """3. منع تكرار مهام إعادة بناء الفهرس لنفس الإصدار (Deduplication)."""
    target_ver = 'REF-2026-TEST-DEDUP'
    
    jid1, err1 = job_queue_service.enqueue_job(
        job_type=JobType.REFERENCE_INDEX_REBUILD,
        target_corpus_version=target_ver,
        requested_by='admin'
    )
    assert err1 is None

    # محاولة ثانية لنفس الإصدار أثناء وجود الأولى في الطابور
    jid2, err2 = job_queue_service.enqueue_job(
        job_type=JobType.REFERENCE_INDEX_REBUILD,
        target_corpus_version=target_ver,
        requested_by='admin2'
    )
    assert err2 is None
    assert jid2 == jid1  # يجب إعادة نفس المعرف دون إنشاء مهمة مكررة


# ─── 2. اختبارات حدود التزامن والسحب الذري (Concurrency & Claiming) ──────────

def test_atomic_claim_respects_scan_concurrency_limit():
    """4. سحب المهام يحترم سقف التزامن MAX_CONCURRENT_SCANS بدقة."""
    with patch.object(config, 'MAX_CONCURRENT_SCANS', 2):
        j1, _ = job_queue_service.enqueue_job(job_type=JobType.SCAN, priority=1)
        j2, _ = job_queue_service.enqueue_job(job_type=JobType.SCAN, priority=2)
        j3, _ = job_queue_service.enqueue_job(job_type=JobType.SCAN, priority=3)

        # سحب أول مهمتين
        c1 = job_queue_service.claim_next_job(worker_pid=1001)
        assert c1 is not None
        assert c1['id'] == j3  # الأعلى أولوية
        assert c1['status'] == JobStatus.RUNNING

        c2 = job_queue_service.claim_next_job(worker_pid=1002)
        assert c2 is not None
        assert c2['id'] == j2

        # السحب الثالث يجب أن يعيد None لاكتمال سقف التزامن (2 من 2)
        c3 = job_queue_service.claim_next_job(worker_pid=1003)
        assert c3 is None

        # إكمال إحدى المهمتين يتيح سحب المهمة الثالثة
        job_queue_service.complete_job(c1['id'])
        c3_after = job_queue_service.claim_next_job(worker_pid=1003)
        assert c3_after is not None
        assert c3_after['id'] == j1


def test_batch_fairness_prevents_single_scan_starvation():
    """5. جدولة عادلة تمنع عناصر دفعة واحدة كبيرة من احتكار الطابور وتجويع الأبحاث الفردية."""
    with patch.object(config, 'MAX_CONCURRENT_SCANS', 2):
        # إدراج دفعة مكونة من 5 عناصر
        batch_id = 'batch-fairness-001'
        for i in range(5):
            job_queue_service.enqueue_job(
                job_type=JobType.BATCH_SCAN,
                batch_id=batch_id,
                batch_item_id=i,
                priority=0
            )

        # إدراج بحث مستقل فردي
        single_job_id, _ = job_queue_service.enqueue_job(
            job_type=JobType.SCAN,
            priority=0,
            requested_by='independent_researcher'
        )

        # سحب أول مهمة (ستكون أول عنصر من الدفعة)
        c1 = job_queue_service.claim_next_job(worker_pid=2001)
        assert c1['batch_id'] == batch_id

        # سحب المهمة الثانية: يجب أن يفضل البحث المستقل لمنع تجويعه بالرغم من أن بقية عناصر الدفعة أقدم منه
        c2 = job_queue_service.claim_next_job(worker_pid=2002)
        assert c2['id'] == single_job_id


# ─── 3. اختبارات نبض الحياة ورصد المهام العالقة (Heartbeat & Stuck Detection) ─

def test_heartbeat_and_progress_throttling():
    """6. نبض الحياة يُحدث التوقيت والنسبة بدقة ويكبح التحديثات الزائدة."""
    jid, _ = job_queue_service.enqueue_job(job_type=JobType.SCAN)
    claimed = job_queue_service.claim_next_job()
    assert claimed is not None

    # تحديث التقدم والمرحلة
    res = job_queue_service.update_job_progress(jid, progress=45, stage="مرحلة المطابقة المعجمية")
    assert res is True

    job = job_queue_service.get_job(jid)
    assert job['progress'] == 45
    assert job['stage'] == "مرحلة المطابقة المعجمية"
    assert job['heartbeat_at'] is not None


def test_stuck_job_detection():
    """7. رصد المهام الجارية التي توقف نبض حياتها وتجاوزت الحد المسموح."""
    jid, _ = job_queue_service.enqueue_job(job_type=JobType.SCAN)
    job_queue_service.claim_next_job()

    # محاكاة توقف نبض الحياة منذ 10 دقائق
    old_hb = datetime.utcnow() - timedelta(minutes=10)
    with base_repo.get_session() as session:
        j = session.query(JobRecord).filter(JobRecord.id == jid).first()
        j.heartbeat_at = old_hb
        session.commit()

    with patch.object(config, 'JOB_STUCK_HEARTBEAT_MINUTES', 5):
        stuck_jobs = job_queue_service.get_stuck_jobs()
        assert len(stuck_jobs) >= 1
        assert any(sj['id'] == jid for sj in stuck_jobs)


# ─── 4. اختبارات الإلغاء التعاوني (Cooperative Cancellation) ──────────────────

def test_cancellation_of_queued_job():
    """8. إلغاء مهمة في طور الانتظار يحولها فوراً إلى cancelled."""
    jid, _ = job_queue_service.enqueue_job(job_type=JobType.SCAN, requested_by='user1')
    
    ok, msg, err = job_queue_service.request_job_cancellation(jid, actor='user1', reason='عدم الحاجة')
    assert ok is True
    assert err is None

    job = job_queue_service.get_job(jid)
    assert job['status'] == JobStatus.CANCELLED
    assert 'عدم الحاجة' in job['safe_error_message']


def test_cooperative_cancellation_of_running_job():
    """9. طلب إلغاء مهمة جارية يرفع علم cancel_requested ويتيح للبرمجية الإنهاء النظيف."""
    jid, _ = job_queue_service.enqueue_job(job_type=JobType.SCAN)
    job_queue_service.claim_next_job()

    ok, msg, err = job_queue_service.request_job_cancellation(jid, actor='admin', reason='إلغاء إداري')
    assert ok is True
    
    # فحص راية الإلغاء التعاوني
    assert job_queue_service.is_cancellation_requested(jid) is True

    # تأكيد الإلغاء من قبل العامل بعد تنظيف الملفات
    cleaned = []
    job_queue_service.finalize_cancellation(jid, cleanup_fn=lambda: cleaned.append(True))
    assert len(cleaned) == 1

    job = job_queue_service.get_job(jid)
    assert job['status'] == JobStatus.CANCELLED


def test_cancellation_rejected_for_completed_job():
    """10. رفض طلب إلغاء مهمة اكتملت مسبقاً بكود JOB_CANCEL_NOT_ALLOWED."""
    jid, _ = job_queue_service.enqueue_job(job_type=JobType.SCAN)
    job_queue_service.claim_next_job()
    job_queue_service.complete_job(jid, result={'overall_pct': 12.5})

    ok, msg, err = job_queue_service.request_job_cancellation(jid)
    assert ok is False
    assert err == ErrorCode.JOB_CANCEL_NOT_ALLOWED


# ─── 5. اختبارات إعادة المحاولة والتراجع الزمني (Retries & Backoff) ──────────

def test_transient_failure_schedules_backoff_retry():
    """11. الفشل العابر يجدول إعادة المحاولة مع زيادة المحاولة وتعيين retry_at."""
    jid, _ = job_queue_service.enqueue_job(job_type=JobType.SCAN, max_attempts=3)
    c = job_queue_service.claim_next_job()

    # محاكاة خطأ عابر في قاعدة البيانات
    job_queue_service.fail_job(
        job_id=jid,
        error_code=ErrorCode.DATABASE_LOCKED,
        error_message="sqlite3.OperationalError: database is locked",
        is_transient=True
    )

    job = job_queue_service.get_job(jid)
    assert job['status'] == JobStatus.QUEUED  # أعيد إلى الطابور
    assert job['attempt_count'] == 1
    assert job['retry_at'] is not None


def test_permanent_failure_does_not_retry():
    """12. الفشل البنيوي الدائم (مثل ملف تالف) يفشل فوراً دون إعادة جدولة."""
    jid, _ = job_queue_service.enqueue_job(job_type=JobType.SCAN, max_attempts=3)
    job_queue_service.claim_next_job()

    job_queue_service.fail_job(
        job_id=jid,
        error_code=ErrorCode.FILE_CORRUPTED,
        error_message="ملف PDF تالف وغير قابل للقراءة",
        is_transient=False
    )

    job = job_queue_service.get_job(jid)
    assert job['status'] == JobStatus.FAILED
    assert job['error_code'] == ErrorCode.FILE_CORRUPTED
    assert job['retry_at'] is None


def test_max_attempts_exhausted_marks_failed():
    """13. استنفاد أقصى عدد للمحاولات العابرة يحول المهمة إلى FAILED بكود JOB_RETRY_LIMIT_REACHED."""
    jid, _ = job_queue_service.enqueue_job(job_type=JobType.SCAN, max_attempts=2)

    # المحاولة 1
    job_queue_service.claim_next_job()
    job_queue_service.fail_job(jid, ErrorCode.DATABASE_LOCKED, "database is locked", is_transient=True)
    
    # المحاكاة الفورية لتخطي وقت retry_at
    with base_repo.get_session() as session:
        session.query(JobRecord).filter(JobRecord.id == jid).update({'retry_at': datetime.utcnow() - timedelta(seconds=1)})
        session.commit()

    # المحاولة 2 (الأخيرة)
    job_queue_service.claim_next_job()
    job_queue_service.fail_job(jid, ErrorCode.DATABASE_LOCKED, "database is locked", is_transient=True)

    job = job_queue_service.get_job(jid)
    assert job['status'] == JobStatus.FAILED
    assert job['error_code'] == ErrorCode.JOB_RETRY_LIMIT_REACHED


def test_manual_retry_reschedules_failed_job():
    """14. إعادة المحاولة اليدوية تعيد جدولة المهمة الفاشلة أو المنقطعة إلى الطابور."""
    jid, _ = job_queue_service.enqueue_job(job_type=JobType.SCAN)
    job_queue_service.claim_next_job()
    job_queue_service.fail_job(jid, ErrorCode.SCAN_FAILED, "خطأ فحص", is_transient=False)

    ok, msg, err = job_queue_service.retry_job_manually(jid, actor='admin')
    assert ok is True
    assert err is None

    job = job_queue_service.get_job(jid)
    assert job['status'] == JobStatus.QUEUED
    assert job['attempt_count'] == 0


# ─── 6. اختبارات التعافي عند إعادة التشغيل (Restart Recovery) ─────────────────

def test_restart_recovery_converts_running_to_interrupted():
    """15. إقلاع الخادم يستدرك المهام العالقة في running ويحولها إلى interrupted."""
    jid, _ = job_queue_service.enqueue_job(job_type=JobType.SCAN)
    job_queue_service.claim_next_job(worker_pid=99999)

    # استدعاء التعافي كما يحدث عند بدء التشغيل
    recovered = job_queue_service.recover_interrupted_jobs()
    assert recovered >= 1

    job = job_queue_service.get_job(jid)
    assert job['status'] == JobStatus.INTERRUPTED
    assert job['error_code'] == ErrorCode.JOB_INTERRUPTED


# ─── 7. اختبارات ترقية الفهرس المرحلية (Index Rebuild Staging Promotion) ───────

def test_index_rebuild_staging_promotion_atomic():
    """16. بناء الفهرس يتم في كائن مرحلي ويرقى ذرياً عند الاكتمال، والفشل لا يفسد الفهرس القديم."""
    from plagiarism_detector.reporting import report_builder
    target_ver = 'REF-2026-TEST-PROMO'

    # بناء أولي ناجح
    idx1 = build_pipeline_index()
    assert idx1 is not None
    orig_cached = report_builder._CACHED_INDEX
    assert orig_cached is not None

    # محاكاة فشل استخراج المراجع أثناء البناء اللاحق
    with patch('app.repositories.document_repo.get_all_segments_for_index', side_effect=RuntimeError("خطأ قاعدة بيانات")):
        with pytest.raises(RuntimeError):
            build_pipeline_index()

        # التأكد من بقاء الفهرس الصالح القديم في الذاكرة دون تلف
        assert report_builder._CACHED_INDEX is not None
        assert report_builder._CACHED_INDEX['total_segments'] == orig_cached['total_segments']


# ─── 8. اختبارات تنظيف السجلات القديمة (Retention Cleanup) ───────────────────

def test_retention_cleanup_completed_jobs():
    """17. تنظيف سجلات المهام المكتملة أو الملغاة التي تجاوزت فترة الاحتفاظ."""
    old_time = datetime.utcnow() - timedelta(days=40)
    jid, _ = job_queue_service.enqueue_job(job_type=JobType.SCAN)
    job_queue_service.claim_next_job()
    job_queue_service.complete_job(jid)

    with base_repo.get_session() as session:
        session.query(JobRecord).filter(JobRecord.id == jid).update({'finished_at': old_time})
        session.commit()

    deleted = job_queue_service.cleanup_completed_jobs(retention_days=30)
    assert deleted >= 1
    assert job_queue_service.get_job(jid) is None


# ─── 9. اختبارات الواجهة البرمجية والصلاحيات (API & RBAC) ─────────────────────

def test_api_list_jobs_privacy_scoping(client):
    """18. المستخدم العادي يشاهد مهامه فقط بينما مدير النظام يستعرض كافة المهام."""
    # إنشاء مهمتين: واحدة لمستخدم عادي والأخرى لمدير
    j_user, _ = job_queue_service.enqueue_job(job_type=JobType.SCAN, requested_by='regular_emp')
    j_admin, _ = job_queue_service.enqueue_job(job_type=JobType.SCAN, requested_by='admin_user')

    # استعلام المستخدم العادي (يجب أن يرى مهمته فقط)
    headers_user = {'X-User-Role': 'data_entry', 'X-User-Name': 'regular_emp'}
    resp_user = client.get('/api/jobs', headers=headers_user)
    assert resp_user.status_code == 200
    user_jobs = resp_user.get_json()['items']
    assert all(j['requested_by'] == 'regular_emp' for j in user_jobs)

    # استعلام المدير (يرى كل المهام)
    headers_admin = {'X-User-Role': 'system_admin', 'X-User-Name': 'admin_user'}
    resp_admin = client.get('/api/jobs', headers=headers_admin)
    assert resp_admin.status_code == 200
    admin_jobs = resp_admin.get_json()['items']
    assert len(admin_jobs) >= 2


def test_api_cancel_and_retry_endpoints(client):
    """19. اختبار واجهات الإلغاء وإعادة المحاولة والتحقق من التوثيق في سجل التدقيق."""
    headers = {'X-User-Role': 'system_admin', 'X-User-Name': 'admin_user'}
    jid, _ = job_queue_service.enqueue_job(job_type=JobType.SCAN, requested_by='admin_user')

    # 1. إلغاء المهمة عبر API
    resp_cancel = client.post(f'/api/jobs/{jid}/cancel', json={'reason': 'إلغاء تجريبي'}, headers=headers)
    assert resp_cancel.status_code == 200
    assert resp_cancel.get_json()['success'] is True

    # 2. إعادة محاولة المهمة الملغاة عبر API
    resp_retry = client.post(f'/api/jobs/{jid}/retry', headers=headers)
    assert resp_retry.status_code == 200
    assert resp_retry.get_json()['success'] is True

    job = job_queue_service.get_job(jid)
    assert job['status'] == JobStatus.QUEUED


def test_api_queue_stats(client):
    """20. اختبار واجهة إحصائيات الطابور المجمعة."""
    headers = {'X-User-Role': 'system_admin', 'X-User-Name': 'admin_user'}
    resp = client.get('/api/jobs/stats', headers=headers)
    assert resp.status_code == 200
    stats = resp.get_json()['stats']
    assert 'queued_count' in stats
    assert 'running_count' in stats
    assert 'max_concurrent_scans' in stats



# ─── 10. اختبار السحب المتعدد عبر العمليات (Multi-Process Atomic Claiming) ─────

def _worker_claim_task(worker_id: int, db_path: str, return_list):
    """دالة عامل مستقل تسحب مهام من قاعدة بيانات منعزلة."""
    import sqlite3
    conn = sqlite3.connect(db_path, timeout=30.0)
    cur = conn.cursor()
    claimed_ids = []

    for _ in range(15):
        try:
            cur.execute("BEGIN IMMEDIATE;")
            cur.execute("SELECT id FROM job_records WHERE status = 'queued' ORDER BY queued_at ASC LIMIT 1;")
            row = cur.fetchone()
            if row:
                jid = row[0]
                cur.execute("UPDATE job_records SET status = 'running', worker_pid = ? WHERE id = ?;", (worker_id, jid))
                conn.commit()
                claimed_ids.append(jid)
            else:
                conn.commit()
                break
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            time.sleep(0.01)

    conn.close()
    return_list.extend(claimed_ids)


def test_multi_process_atomic_claim_safety(tmp_path):
    """21. اختبار عمليات متعددة تسحب مهام متزامنة من نفس قاعدة البيانات دون أي تصادم أو فقدان."""
    test_db = str(tmp_path / 'multi_worker_test.db')
    conn = sqlite3.connect(test_db)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("""
        CREATE TABLE job_records (
            id VARCHAR(64) PRIMARY KEY,
            status VARCHAR(50) DEFAULT 'queued',
            queued_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            worker_pid INTEGER
        );
    """)
    # إدراج 30 مهمة في الطابور
    for i in range(30):
        conn.execute("INSERT INTO job_records (id, status) VALUES (?, 'queued');", (f"job_mp_{i}",))
    conn.commit()
    conn.close()

    manager = multiprocessing.Manager()
    claimed_all = manager.list()

    # إطلاق 4 عمليات عمال متزامنة
    processes = []
    for wid in range(4):
        p = multiprocessing.Process(target=_worker_claim_task, args=(wid + 1, test_db, claimed_all))
        processes.append(p)
        p.start()

    for p in processes:
        p.join(timeout=10)

    # التحقق:
    # 1. تم سحب جميع الـ 30 مهمة
    assert len(claimed_all) == 30
    # 2. لا توجد أي مهمة تم سحبها أكثر من مرة (Zero Duplicates)
    assert len(set(claimed_all)) == 30


# ─── 11. قياس الأداء والمحاكاة الحملية (Benchmarks & Load Simulation) ──────────

def test_performance_benchmarks_and_load_simulation():
    """22. قياس سرعة الإدراج والسحب لـ 200 مهمة ومحاكاة حمل دفعة كاملة (Load Simulation)."""
    start_time = time.perf_counter()

    # 1. إدراج 100 مهمة وقياس الأداء
    for i in range(100):
        job_queue_service.enqueue_job(
            job_type=JobType.SCAN,
            payload={'index': i},
            requested_by=f'user_{i%5}'
        )

    enqueue_elapsed = time.perf_counter() - start_time
    assert enqueue_elapsed < 5.0  # يجب أن يكون الإدراج سريعاً جداً

    # 2. محاكاة سحب 100 مهمة مع التزامن
    with patch.object(config, 'MAX_CONCURRENT_SCANS', 10):
        claim_start = time.perf_counter()
        claimed_count = 0
        for _ in range(100):
            c = job_queue_service.claim_next_job(worker_pid=999)
            if c:
                claimed_count += 1
                job_queue_service.complete_job(c['id'])

        claim_elapsed = time.perf_counter() - claim_start
        assert claimed_count == 100
        assert claim_elapsed < 5.0

    # 3. محاكاة حمل دفعة أبحاث 20 بحثاً مع 5 أبحاث مستقلة والتأكد من تفريغ الطابور deterministically
    batch_id = 'bench-batch-100'
    for b in range(20):
        job_queue_service.enqueue_job(job_type=JobType.BATCH_SCAN, batch_id=batch_id, batch_item_id=b)
    for s in range(5):
        job_queue_service.enqueue_job(job_type=JobType.SCAN, requested_by='solo_user')

    with patch.object(config, 'MAX_CONCURRENT_SCANS', 4):
        drained = 0
        while True:
            c = job_queue_service.claim_next_job()
            if not c:
                break
            job_queue_service.complete_job(c['id'])
            drained += 1

        assert drained == 25


# ─── 12. اختبارات الإثبات التشغيلي الشامل (Phase 17 Closeout Operational Proofs) ─

def _multi_process_worker_fn(proc_id: int, db_path: str, return_list):
    """دالة عامل مستقل تسحب مهام حقيقية وتحدث حالتها في قاعدة بيانات منعزلة."""
    import sqlite3
    import uuid
    conn = sqlite3.connect(db_path, timeout=60.0)
    cur = conn.cursor()
    claimed = []

    while True:
        try:
            cur.execute("BEGIN IMMEDIATE;")
            cur.execute("""
                SELECT id FROM job_records
                WHERE status = 'queued'
                ORDER BY priority DESC, queued_at ASC
                LIMIT 1;
            """)
            row = cur.fetchone()
            if not row:
                conn.commit()
                break
            jid = row[0]
            lease = uuid.uuid4().hex
            cur.execute("""
                UPDATE job_records
                SET status = 'running',
                    worker_pid = ?,
                    lease_token = ?,
                    heartbeat_at = datetime('now'),
                    attempt_count = attempt_count + 1
                WHERE id = ? AND status = 'queued';
            """, (proc_id, lease, jid))
            if cur.rowcount > 0:
                conn.commit()
                claimed.append((jid, proc_id, lease))
            else:
                conn.rollback()
        except sqlite3.OperationalError:
            try:
                conn.rollback()
            except Exception:
                pass
            time.sleep(0.005)
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            break

    conn.close()
    return_list.extend(claimed)


def _mp_backup_worker_fn(worker_id: int, lock_file_str: str, return_list):
    """عامل مستقل على مستوى نظام التشغيل لاختبار قفل النسخ الاحتياطي عبر العمليات."""
    import time
    from pathlib import Path
    from app.services.backup_service import CrossProcessBackupLock
    lock = CrossProcessBackupLock(owner=f'worker_{worker_id}', timeout_seconds=10, lock_file_path=Path(lock_file_str))
    acquired = lock.acquire(blocking=False)
    if acquired:
        t_enter = time.time()
        time.sleep(0.15)
        t_exit = time.time()
        lock.release()
        return_list.append((worker_id, True, t_enter, t_exit))
    else:
        return_list.append((worker_id, False, 0.0, 0.0))


def _mp_index_dedup_worker_fn(worker_id: int, db_url: str, target_ver: str, return_list):
    """عامل مستقل على مستوى نظام التشغيل لاختبار منع تكرار بناء الفهرس عبر العمليات."""
    import os
    os.environ['DATABASE_URL'] = db_url
    os.environ['TESTING'] = '1'
    from app.repositories import base_repo
    from sqlalchemy.orm import sessionmaker
    base_repo.engine = base_repo._create_configured_engine(db_url)
    base_repo.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=base_repo.engine)
    from app.services import job_queue_service
    from app.services.job_queue_service import JobType
    jid, err = job_queue_service.enqueue_job(
        job_type=JobType.REFERENCE_INDEX_REBUILD,
        target_corpus_version=target_ver,
        requested_by=f'proc_{worker_id}'
    )
    return_list.append((worker_id, jid, err))


def _mp_ocr_worker_fn(worker_id: int, lock_file_str: str, duration: float, return_list):
    """عامل مستقل على مستوى نظام التشغيل لاختبار حجز فتحة OCR الفعلية عبر العمليات."""
    import time
    from pathlib import Path
    from plagiarism_detector.extraction.ocr_engine import CrossProcessOcrLock
    lock = CrossProcessOcrLock(owner=f'worker_proc_{worker_id}', timeout_seconds=15, lock_file_path=Path(lock_file_str))
    acquired = lock.acquire(blocking=True, timeout_seconds=15)
    if acquired:
        t_enter = time.time()
        time.sleep(duration)
        t_exit = time.time()
        lock.release()
        return_list.append((worker_id, True, t_enter, t_exit))
    else:
        return_list.append((worker_id, False, 0.0, 0.0))


def _mp_crashing_ocr_holder_fn(lock_file_str: str, ready_event):
    """عملية تحجز قفل OCR ثم تموت فجأة لمحاكاة انهيار العامل دون استدعاء cleanup."""
    import os
    import json
    import time
    from pathlib import Path
    lock_p = Path(lock_file_str)
    flags = os.O_CREAT | os.O_EXCL | os.O_RDWR
    fd = os.open(str(lock_p), flags, 0o600)
    payload = {
        'token': 'crash-token-test',
        'owner': f'crashing_proc_{os.getpid()}',
        'pid': os.getpid(),
        'acquired_at': time.time(),
        'expires_at': time.time() + 300
    }
    os.write(fd, json.dumps(payload).encode('utf-8'))
    os.close(fd)
    ready_event.set()
    os._exit(0)


def test_true_multi_process_claim_safety_120_jobs(tmp_path):
    """23. اختبار تزامن العمليات الحقيقية: 5 عمليات مستقلة تسحب 120 مهمة دون أي تكرار أو فقدان."""
    test_db = str(tmp_path / 'mp_claim_120_test.db')
    conn = sqlite3.connect(test_db)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    conn.execute("""
        CREATE TABLE job_records (
            id VARCHAR(64) PRIMARY KEY,
            job_type VARCHAR(50) NOT NULL,
            status VARCHAR(50) DEFAULT 'queued',
            priority INTEGER DEFAULT 0,
            queued_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            started_at DATETIME,
            finished_at DATETIME,
            heartbeat_at DATETIME,
            retry_at DATETIME,
            requested_by VARCHAR(255) DEFAULT '',
            worker_pid INTEGER,
            lease_token VARCHAR(64),
            progress INTEGER DEFAULT 0,
            stage VARCHAR(255) DEFAULT '',
            cancel_requested INTEGER DEFAULT 0,
            attempt_count INTEGER DEFAULT 0,
            max_attempts INTEGER DEFAULT 3
        );
    """)
    conn.commit()

    num_jobs = 120
    num_workers = 5

    for i in range(num_jobs):
        conn.execute("INSERT INTO job_records (id, job_type, status, priority) VALUES (?, 'scan', 'queued', 0);", (f"job-{i:04d}",))
    conn.commit()
    conn.close()

    manager = multiprocessing.Manager()
    claimed_all = manager.list()

    procs = []
    for wid in range(num_workers):
        p = multiprocessing.Process(target=_multi_process_worker_fn, args=(wid + 1, test_db, claimed_all))
        procs.append(p)
        p.start()

    for p in procs:
        p.join(timeout=30)

    conn = sqlite3.connect(test_db)
    cur = conn.cursor()
    cur.execute("PRAGMA integrity_check;")
    integrity = cur.fetchone()[0]

    cur.execute("SELECT status, count(*) FROM job_records GROUP BY status;")
    status_counts = dict(cur.fetchall())

    cur.execute("SELECT count(*) FROM job_records WHERE status = 'queued';")
    unclaimed = cur.fetchone()[0]
    conn.close()

    all_claimed = list(claimed_all)
    claimed_ids = [c[0] for c in all_claimed]
    unique_claimed_ids = set(claimed_ids)
    duplicates = len(claimed_ids) - len(unique_claimed_ids)

    assert integrity == 'ok'
    assert len(claimed_ids) == 120
    assert len(unique_claimed_ids) == 120
    assert duplicates == 0
    assert unclaimed == 0
    assert status_counts.get('running') == 120


def test_lease_ownership_enforcement():
    """24. التحقق من حماية رمز الإيجار (lease_token) ورفض التعديل برمز خاطئ أو قديم."""
    jid, _ = job_queue_service.enqueue_job(job_type=JobType.SCAN)
    claimed = job_queue_service.claim_next_job(worker_pid=1001)
    assert claimed is not None
    valid_lease = claimed['lease_token']
    wrong_lease = "wrong-lease-token-12345"

    # 1. محاولة تحديث نبض الحياة برمز إيجار خاطئ (يجب أن ترفض)
    res_hb_wrong = job_queue_service.heartbeat_job(jid, progress=20, lease_token=wrong_lease)
    assert res_hb_wrong is False

    # 2. محاولة إكمال المهمة برمز خاطئ (يجب أن ترفض)
    res_comp_wrong = job_queue_service.complete_job(jid, result={'score': 5}, lease_token=wrong_lease)
    assert res_comp_wrong is False

    # 3. محاولة تسجيل فشل برمز خاطئ (يجب أن ترفض)
    res_fail_wrong = job_queue_service.fail_job(jid, ErrorCode.SCAN_FAILED, "خطأ مزعوم", lease_token=wrong_lease)
    assert res_fail_wrong is False

    # 4. محاولة تأكيد إلغاء برمز خاطئ (يجب أن ترفض)
    res_cancel_wrong = job_queue_service.finalize_cancellation(jid, lease_token=wrong_lease)
    assert res_cancel_wrong is False

    # 5. التحديث بالرمز الصحيح ينجح
    res_hb_valid = job_queue_service.heartbeat_job(jid, progress=50, stage="مطابقة", min_interval_seconds=0, lease_token=valid_lease)
    assert res_hb_valid is True

    res_comp_valid = job_queue_service.complete_job(jid, result={'score': 5}, lease_token=valid_lease)
    assert res_comp_valid is True

    job = job_queue_service.get_job(jid)
    assert job['status'] == JobStatus.COMPLETED


def test_stuck_job_detection_comprehensive_matrix():
    """25. مصفوفة التحقق الدقيقة للمهام العالقة (طازجة، قديمة، مكتملة، ملغاة)."""
    # 1. مهمة جارية حديثة -> ليست عالقة
    j_fresh, _ = job_queue_service.enqueue_job(job_type=JobType.SCAN)
    job_queue_service.claim_next_job()

    # 2. مهمة جارية توقف نبضها لأكثر من 15 دقيقة -> عالقة
    j_stuck, _ = job_queue_service.enqueue_job(job_type=JobType.SCAN)
    job_queue_service.claim_next_job()
    old_time = datetime.utcnow() - timedelta(minutes=20)
    with base_repo.get_session() as session:
        session.query(JobRecord).filter(JobRecord.id == j_stuck).update({'heartbeat_at': old_time, 'started_at': old_time})
        session.commit()

    # 3. مهمة مكتملة منذ وقت طويل -> ليست عالقة إطلاقاً
    j_done, _ = job_queue_service.enqueue_job(job_type=JobType.SCAN)
    job_queue_service.claim_next_job()
    job_queue_service.complete_job(j_done)
    with base_repo.get_session() as session:
        session.query(JobRecord).filter(JobRecord.id == j_done).update({'heartbeat_at': old_time, 'finished_at': old_time})
        session.commit()

    # 4. مهمة ملغاة منذ وقت طويل -> ليست عالقة إطلاقاً
    j_cancel, _ = job_queue_service.enqueue_job(job_type=JobType.SCAN)
    job_queue_service.claim_next_job()
    job_queue_service.finalize_cancellation(j_cancel)
    with base_repo.get_session() as session:
        session.query(JobRecord).filter(JobRecord.id == j_cancel).update({'heartbeat_at': old_time, 'finished_at': old_time})
        session.commit()

    with patch.object(config, 'JOB_STUCK_HEARTBEAT_MINUTES', 5):
        stuck_list = job_queue_service.get_stuck_jobs()
        stuck_ids = [j['id'] for j in stuck_list]

        assert j_stuck in stuck_ids
        assert j_fresh not in stuck_ids
        assert j_done not in stuck_ids
        assert j_cancel not in stuck_ids


def test_atomic_manual_retry_concurrency():
    """26. التحقق من ذرية إعادة الجدولة اليدوية ومنع تكرار الجدولة بين العمليات المتزامنة."""
    jid, _ = job_queue_service.enqueue_job(job_type=JobType.SCAN)
    job_queue_service.claim_next_job()
    job_queue_service.fail_job(jid, ErrorCode.SCAN_FAILED, "فشل أولي", is_transient=False)

    # محاولة إعادة المحاولة المتزامنة
    res1, msg1, err1 = job_queue_service.retry_job_manually(jid, actor='admin_1')
    assert res1 is True
    assert err1 is None

    # المحاولة الثانية المباشرة يجب أن تفشل لأن المهمة أصبحت queued بالفعل
    res2, msg2, err2 = job_queue_service.retry_job_manually(jid, actor='admin_2')
    assert res2 is False
    assert err2 == ErrorCode.JOB_ALREADY_RUNNING

    job = job_queue_service.get_job(jid)
    assert job['status'] == JobStatus.QUEUED
    assert job['attempt_count'] == 0


def test_attempt_count_contract_boundaries():
    """27. التحقق من عقد زيادة عداد المحاولات عند السحب فقط وسلوك الحدود القصوى max_attempts."""
    # max_attempts = 1
    jid, _ = job_queue_service.enqueue_job(job_type=JobType.SCAN, max_attempts=1)
    job_before = job_queue_service.get_job(jid)
    assert job_before['attempt_count'] == 0  # لم يزد بمجرد الإدراج

    # السحب يزيد المحاولة إلى 1
    claimed = job_queue_service.claim_next_job()
    assert claimed['id'] == jid
    assert claimed['attempt_count'] == 1

    # الفشل العابر مع max_attempts = 1 يجب أن يحولها فوراً إلى FAILED (JOB_RETRY_LIMIT_REACHED)
    job_queue_service.fail_job(jid, ErrorCode.DATABASE_LOCKED, "database is locked", is_transient=True)
    job_after = job_queue_service.get_job(jid)
    assert job_after['status'] == JobStatus.FAILED
    assert job_after['error_code'] == ErrorCode.JOB_RETRY_LIMIT_REACHED


def test_backoff_persisted_retry_at_no_sleep():
    """28. التأكد من أن السحب يتجاوز المهام ذات retry_at المستقبلي دون تجميد أو نوم الخيوط."""
    jid, _ = job_queue_service.enqueue_job(job_type=JobType.SCAN, max_attempts=3)
    c = job_queue_service.claim_next_job()
    job_queue_service.fail_job(jid, ErrorCode.DATABASE_LOCKED, "database locked", is_transient=True)

    # المهمة في الطابور بانتظار retry_at المستقبلي (بعد 5 ثوانٍ)
    job = job_queue_service.get_job(jid)
    assert job['status'] == JobStatus.QUEUED
    assert job['retry_at'] is not None

    # محاولة السحب الفورية يجب أن تتجاهلها ولا تسحبها
    c_immediate = job_queue_service.claim_next_job()
    assert c_immediate is None

    # عند تقديم الوقت لتجاوز retry_at، تصبح قابلة للسحب
    with base_repo.get_session() as session:
        session.query(JobRecord).filter(JobRecord.id == jid).update({'retry_at': datetime.utcnow() - timedelta(seconds=1)})
        session.commit()

    c_after = job_queue_service.claim_next_job()
    assert c_after is not None
    assert c_after['id'] == jid
    assert c_after['attempt_count'] == 2


def test_scheduler_fairness_anti_starvation_simulation():
    """29. محاكاة شاملة لجدولة 20 بحثاً مستقلاً و5 دفعات (100 عنصر) وإثبات عدم التجويع."""
    # 1. إدراج 5 دفعات × 20 عنصر
    for b in range(1, 6):
        batch_id = f"batch-anti-starve-{b:02d}"
        for item in range(20):
            job_queue_service.enqueue_job(
                job_type=JobType.BATCH_SCAN,
                batch_id=batch_id,
                batch_item_id=item,
                priority=0,
                requested_by=f"batch_user_{b}"
            )

    # 2. إدراج 20 بحثاً مستقلاً
    for s in range(20):
        job_queue_service.enqueue_job(
            job_type=JobType.SCAN,
            priority=0,
            requested_by=f"solo_user_{s}"
        )

    # 3. تفريغ الطابور مع سقف تزامن 4
    with patch.object(config, 'MAX_CONCURRENT_SCANS', 4):
        claims_log = []
        batch_progress = {f"batch-anti-starve-{b:02d}": 0 for b in range(1, 6)}
        standalone_serviced = 0

        step = 0
        while True:
            step += 1
            claimed = job_queue_service.claim_next_job(worker_pid=1000 + (step % 4))
            if not claimed:
                with base_repo.get_session() as session:
                    running_jobs = session.query(JobRecord).filter(JobRecord.status == JobStatus.RUNNING).all()
                    if not running_jobs:
                        break
                    job_queue_service.complete_job(running_jobs[0].id)
                    continue

            jid = claimed['id']
            jtype = claimed['job_type']
            bid = claimed.get('batch_id')
            claims_log.append((jtype, bid, jid))

            if jtype == JobType.SCAN:
                standalone_serviced += 1
            elif bid in batch_progress:
                batch_progress[bid] += 1

            job_queue_service.complete_job(jid)

        with base_repo.get_session() as session:
            for r in session.query(JobRecord).filter(JobRecord.status == JobStatus.RUNNING).all():
                job_queue_service.complete_job(r.id)

    # التحقق:
    assert len(claims_log) == 120
    assert standalone_serviced == 20
    assert all(count == 20 for count in batch_progress.values())


def test_index_rebuild_dedup_concurrency():
    """30. التحقق من منع تكرار مهام بناء الفهرس لنفس الإصدار تحت الطلبات المتزامنة."""
    target_ver = 'REF-2026-DEDUP-CONCURRENT'

    jid1, err1 = job_queue_service.enqueue_job(
        job_type=JobType.REFERENCE_INDEX_REBUILD,
        target_corpus_version=target_ver,
        requested_by='user_a'
    )
    assert err1 is None

    jid2, err2 = job_queue_service.enqueue_job(
        job_type=JobType.REFERENCE_INDEX_REBUILD,
        target_corpus_version=target_ver,
        requested_by='user_b'
    )
    assert err2 is None
    assert jid1 == jid2

    # بعد اكتمال المهمة الأولى، يمكن جدولة مهمة جديدة لنفس الإصدار
    claimed = job_queue_service.claim_next_job()
    assert claimed['id'] == jid1
    job_queue_service.complete_job(jid1)

    jid3, err3 = job_queue_service.enqueue_job(
        job_type=JobType.REFERENCE_INDEX_REBUILD,
        target_corpus_version=target_ver,
        requested_by='user_c'
    )
    assert err3 is None
    assert jid3 != jid1


def test_cancellation_checkpoint_no_partial_finalized_report():
    """31. التحقق من أن إلغاء المهمة أثناء المعالجة لا يترك تقريراً نهائياً في قاعدة البيانات."""
    jid, _ = job_queue_service.enqueue_job(job_type=JobType.SCAN, research_id=999)
    job_queue_service.claim_next_job()

    # طلب الإلغاء
    job_queue_service.request_job_cancellation(jid, actor='admin', reason='إلغاء أمني')
    assert job_queue_service.is_cancellation_requested(jid) is True

    # إنهاء الإلغاء دون تسجيل تقرير
    cleaned = []
    job_queue_service.finalize_cancellation(jid, cleanup_fn=lambda: cleaned.append("cleaned"))
    assert len(cleaned) == 1

    job = job_queue_service.get_job(jid)
    assert job['status'] == JobStatus.CANCELLED
    assert job['report_id'] is None


def test_job_api_privacy_strict_scoping(client):
    """32. التحقق من الخصوصية الصارمة لواجهات المهام ومنع كشف مهام المستخدمين الآخرين."""
    j_user_a, _ = job_queue_service.enqueue_job(job_type=JobType.SCAN, requested_by='user_a')

    # المستخدم B يحاول استعراض مهمة المستخدم A مباشرة عبر المعرف
    headers_b = {'X-User-Role': 'data_entry', 'X-User-Name': 'user_b'}
    resp_b = client.get(f'/api/jobs/{j_user_a}', headers=headers_b)
    assert resp_b.status_code == 403
    assert resp_b.get_json()['error_code'] == ErrorCode.AUTH_FORBIDDEN

    # المستخدم B يحاول إلغاء مهمة المستخدم A
    resp_cancel_b = client.post(f'/api/jobs/{j_user_a}/cancel', json={'reason': 'تطفل'}, headers=headers_b)
    assert resp_cancel_b.status_code == 403
    assert resp_cancel_b.get_json()['error_code'] == ErrorCode.AUTH_FORBIDDEN


def test_research_scan_status_canonical_validation():
    """33. التحقق من أن Research.scan_status ترفض الحالات غير القانونية (pending, cancelled, error)."""
    from app.workflow.statuses import validate_scan_transition, ScanStatus
    from app.repositories import batch_repo
    from app.models.research_schema import Research

    # 1. التحقق المباشر من validate_scan_transition
    assert validate_scan_transition(None, 'queued') is True
    assert validate_scan_transition(None, 'processing') is True
    assert validate_scan_transition('queued', 'processing') is True
    assert validate_scan_transition('processing', 'completed') is True
    assert validate_scan_transition('processing', 'failed') is True
    assert validate_scan_transition('processing', 'interrupted') is True

    # الحالات الممنوعة تماماً
    assert validate_scan_transition(None, 'pending') is False
    assert validate_scan_transition(None, 'cancelled') is False
    assert validate_scan_transition(None, 'error') is False
    assert validate_scan_transition('queued', 'pending') is False
    assert validate_scan_transition('processing', 'cancelled') is False
    assert validate_scan_transition('processing', 'error') is False

    # 2. التحقق من تحديث السجل عبر قاعدة البيانات
    with base_repo.get_session() as session:
        res = Research(title="بحث اختبار الحالات القانونية", scan_status=ScanStatus.QUEUED.value)
        session.add(res)
        session.commit()
        res_id = res.id

    # محاولة التحديث لحالة غير قانونية
    assert batch_repo.update_research_scan_status(res_id, "pending") is False
    assert batch_repo.update_research_scan_status(res_id, "cancelled") is False
    assert batch_repo.update_research_scan_status(res_id, "error") is False

    # التحقق من أن الحالة لم تتغير
    r_check = batch_repo.get_research(res_id)
    assert r_check['scan_status'] == ScanStatus.QUEUED.value

    # تحديث لحالة قانونية ينجح
    assert batch_repo.update_research_scan_status(res_id, ScanStatus.PROCESSING.value) is True
    r_check2 = batch_repo.get_research(res_id)
    assert r_check2['scan_status'] == ScanStatus.PROCESSING.value


def test_backup_cross_process_serialization_multiprocess(tmp_path):
    """34. التحقق من أن قفل النسخ الاحتياطي يمنع تنفيذ عمليتي نسخ متزامنتين عبر عمليتي نظام تشغيل حقيقيتين."""
    lock_file = str(tmp_path / '.backup.lock')

    manager = multiprocessing.Manager()
    results = manager.list()

    p1 = multiprocessing.Process(target=_mp_backup_worker_fn, args=(1, lock_file, results))
    p2 = multiprocessing.Process(target=_mp_backup_worker_fn, args=(2, lock_file, results))

    p1.start()
    time.sleep(0.02)  # إعطاء فرصة طفيفة للعملية الأولى لحجز القفل
    p2.start()

    p1.join(timeout=15)
    p2.join(timeout=15)

    res_list = list(results)
    assert len(res_list) == 2

    # عملية واحدة فقط يجب أن تنجح في حجز القفل والوصول للمنطقة الحرجة
    acquired_workers = [r for r in res_list if r[1] is True]
    rejected_workers = [r for r in res_list if r[1] is False]

    assert len(acquired_workers) == 1
    assert len(rejected_workers) == 1


def test_ocr_concurrency_bounding_with_mock():
    """35. التحقق من أن سقف تشغيل OCR (MAX_CONCURRENT_OCR_JOBS = 1) يحمي تنفيذ Tesseract الفعلي."""
    from PIL import Image
    from concurrent.futures import ThreadPoolExecutor
    from plagiarism_detector.extraction import ocr_engine

    active_executions = 0
    max_concurrent_seen = 0
    exec_lock = threading.Lock()

    def mock_image_to_string(image, lang='ara+eng', config='--psm 6'):
        nonlocal active_executions, max_concurrent_seen
        with exec_lock:
            active_executions += 1
            if active_executions > max_concurrent_seen:
                max_concurrent_seen = active_executions
        time.sleep(0.05)  # محاكاة زمن معالجة Tesseract
        with exec_lock:
            active_executions -= 1
        return "نص مستخرج عبر OCR"

    dummy_img = Image.new('RGB', (100, 100), color='white')

    with patch('plagiarism_detector.extraction.ocr_engine.check_ocr_availability', return_value={'available': True, 'has_arabic': True, 'cmd_path': 'dummy'}):
        with patch('pytesseract.image_to_string', side_effect=mock_image_to_string):
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(ocr_engine.ocr_page_pixmap, dummy_img) for _ in range(5)]
                results = [f.result() for f in futures]

    assert len(results) == 5
    assert all(r == "نص مستخرج عبر OCR" for r in results)
    assert max_concurrent_seen == 1


def test_index_rebuild_dedup_multiprocess(tmp_path):
    """36. التحقق من منع تكرار مهام بناء الفهرس لنفس الإصدار ذرياً عبر عمليات نظام تشغيل حقيقية."""
    from sqlalchemy.orm import sessionmaker
    test_db = str(tmp_path / 'mp_dedup_test.db')
    db_url = f"sqlite:///{test_db}"

    # تهيئة الجداول في قاعدة بيانات الاختبار
    orig_db_url = os.environ.get('DATABASE_URL')
    try:
        os.environ['DATABASE_URL'] = db_url
        os.environ['TESTING'] = '1'
        base_repo.engine = base_repo._create_configured_engine(db_url)
        base_repo.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=base_repo.engine)
        base_repo.init_database()

        target_ver = 'REF-2026-MP-DEDUP-TEST'
        manager = multiprocessing.Manager()
        results = manager.list()

        procs = []
        for wid in range(4):
            p = multiprocessing.Process(target=_mp_index_dedup_worker_fn, args=(wid + 1, db_url, target_ver, results))
            procs.append(p)
            p.start()

        for p in procs:
            p.join(timeout=20)

        res_list = list(results)
        assert len(res_list) == 4

        # التحقق من أن كافة العمليات أرجعت نفس معرف المهمة وبدون أخطاء
        job_ids = [r[1] for r in res_list]
        errors = [r[2] for r in res_list]

        assert all(err is None for err in errors)
        assert len(set(job_ids)) == 1
        assert None not in job_ids

        # التحقق من وجود سجل واحد فقط في قاعدة البيانات
        conn = sqlite3.connect(test_db)
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM job_records WHERE job_type = 'reference_index_rebuild' AND target_corpus_version = ?;", (target_ver,))
        count = cur.fetchone()[0]
        conn.close()

        assert count == 1
    finally:
        if orig_db_url:
            os.environ['DATABASE_URL'] = orig_db_url
            base_repo.engine = base_repo._create_configured_engine(orig_db_url)
            base_repo.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=base_repo.engine)


def test_cross_process_ocr_concurrency_bounding_multiprocess(tmp_path):
    """37. التحقق من أن قفل OCR عبر العمليات (CrossProcessOcrLock) يضمن تشغيل واحد فقط (concurrency=1) عبر عمليات نظام تشغيل حقيقية."""
    lock_file = str(tmp_path / '.ocr.lock')
    manager = multiprocessing.Manager()
    results = manager.list()

    num_procs = 4
    procs = []
    for wid in range(num_procs):
        p = multiprocessing.Process(target=_mp_ocr_worker_fn, args=(wid + 1, lock_file, 0.08, results))
        procs.append(p)
        p.start()

    for p in procs:
        p.join(timeout=20)

    res_list = list(results)
    assert len(res_list) == num_procs

    # التحقق من أن جميع العمليات تمكنت من الاستحواذ بالتتابع
    assert all(r[1] is True for r in res_list)

    # حساب التزامن الفعلي عبر فترات الدخول والخروج [t_enter, t_exit]
    intervals = [(r[2], r[3]) for r in res_list]
    for i in range(len(intervals)):
        for j in range(i + 1, len(intervals)):
            t1_start, t1_end = intervals[i]
            t2_start, t2_end = intervals[j]
            overlap = max(0.0, min(t1_end, t2_end) - max(t1_start, t2_start))
            assert overlap == 0.0, f"تداخل غير مسموح في المنطقة الحرجة لـ OCR بين العملية {i} والعملية {j} بمقدار {overlap}s"

    # التأكد من تنظيف القفل بعد الانتهاء
    assert not os.path.exists(lock_file)


def test_cross_process_ocr_crash_recovery(tmp_path):
    """38. التحقق من التعافي التلقائي لقفل OCR عند انهيار العملية المالكة (Dead PID recovery) دون الحاجة لتدخل يدوي."""
    from pathlib import Path
    from plagiarism_detector.extraction.ocr_engine import CrossProcessOcrLock
    lock_file = str(tmp_path / '.ocr_crash.lock')
    ready_evt = multiprocessing.Event()

    # إطلاق عملية تحجز القفل ثم تنهار فوراً
    p_crash = multiprocessing.Process(target=_mp_crashing_ocr_holder_fn, args=(lock_file, ready_evt))
    p_crash.start()

    ready_evt.wait(timeout=5)
    p_crash.join(timeout=5)
    assert p_crash.exitcode == 0
    assert os.path.exists(lock_file)

    # محاولة عملية جديدة حجز القفل -> يجب أن تكتشف موت العملية السابقة وتسترد القفل بأمان
    lock_b = CrossProcessOcrLock(owner='worker_proc_b', timeout_seconds=5, lock_file_path=Path(lock_file))
    acquired = lock_b.acquire(blocking=True, timeout_seconds=5)
    assert acquired is True

    # تحرير القفل
    lock_b.release()
    assert not os.path.exists(lock_file)



