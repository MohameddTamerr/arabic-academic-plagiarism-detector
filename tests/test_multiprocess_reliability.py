# -*- coding: utf-8 -*-
"""
حزمة اختبارات الموثوقية وتعدد العمليات (Phase 9 & Phase 10 Multiprocessing Reliability Gate):
- اختبار A: قفل الاستعادة عبر العمليات المتعددة (Cross-Process Authoritative Restore Lock).
- اختبار B: تخصيص الأرقام المرجعية الحقيقي عبر عمليات نظام تشغيل منفصلة (Multi-Process Reference Allocation).
- اختبار C: ترقية وإصدارات قاعدة المراجع عبر عمليات متعددة (Multi-Process Reference Corpus Versioning).
- اختبار D: اتساق لقطات الملفات واستبعاد ملفات الرفع المؤقتة (Application-Level File Snapshot Consistency).
- اختبار E: استمرارية كتالوج النسخ وسجلات التدقيق بعد الاستعادة (Restore Continuity Recheck).
"""

import os
import sys
import time
import json
import uuid
import shutil
import tempfile
import sqlite3
import zipfile
import multiprocessing
from pathlib import Path
import pytest

import app
from app.services.backup_service import CrossProcessRestoreLock, create_institutional_backup, restore_institutional_backup, validate_backup
from app.services import reference_service, audit_service, snapshot_service
from app.repositories import backup_repo, base_repo, batch_repo


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def app_instance():
    from app import create_app
    app = create_app()
    app.config['TESTING'] = True
    app.config['STRICT_AUTH'] = True
    app.config['SECRET_KEY'] = 'test-mp-secret-2026'
    return app


@pytest.fixture
def isolated_db_path():
    """قاعدة بيانات SQLite مستقلة ومؤقتة مجهزة للعمليات المتعددة مع PRAGMA WAL."""
    import gc
    temp_dir = tempfile.mkdtemp()
    db_file = os.path.join(temp_dir, "mp_test.db")

    conn = sqlite3.connect(db_file)
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode = WAL;")
    cur.execute("PRAGMA synchronous = NORMAL;")
    cur.execute("PRAGMA busy_timeout = 10000;")
    cur.execute("""
        CREATE TABLE reference_sequences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            namespace TEXT NOT NULL,
            year INTEGER NOT NULL,
            last_value INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_namespace_year UNIQUE (namespace, year)
        );
    """)
    conn.commit()
    conn.close()

    yield db_file

    gc.collect()
    shutil.rmtree(temp_dir, ignore_errors=True)


# ─── Helper Functions for Multiprocessing ──────────────────────────────────────

def _mp_worker_allocate_references(db_path: str, count: int, result_queue: multiprocessing.Queue):
    """عامل يعمل في عملية OS مستقلة لتوليد أرقام مرجعية متزامنة."""
    import os
    os.environ['TESTING'] = '1'
    import config
    config.DATABASE_URL = f"sqlite:///{db_path}"
    config.DEFAULT_SQLITE_PATH = Path(db_path)

    # إعادة تهيئة المحرك في العملية الفرعية عبر rebind_engine
    from app.repositories import base_repo
    base_repo.rebind_engine(config.DATABASE_URL)

    allocated = []
    for _ in range(count):
        ref = reference_service.get_next_research_reference(year=2026, prefix='RES')
        allocated.append(ref)
        time.sleep(0.005)

    base_repo.engine.dispose()
    result_queue.put(allocated)


def _mp_worker_corpus_version(db_path: str, num_versions: int, result_queue: multiprocessing.Queue):
    """عامل يعمل في عملية OS مستقلة لحجز تسلسلات إصدارات قاعدة المراجع."""
    import os
    os.environ['TESTING'] = '1'
    import config
    config.DATABASE_URL = f"sqlite:///{db_path}"
    config.DEFAULT_SQLITE_PATH = Path(db_path)

    from app.repositories import base_repo
    base_repo.rebind_engine(config.DATABASE_URL)

    allocated_versions = []
    for i in range(num_versions):
        seq = reference_service.get_next_sequence_value('reference_corpus', 2026)
        ver_id = f"REF-2026-{seq:06d}"
        allocated_versions.append(ver_id)
        time.sleep(0.005)

    base_repo.engine.dispose()
    result_queue.put(allocated_versions)


def _mp_worker_hold_restore_lock(lock_file: str, hold_duration: float, acquired_event, released_event):
    """عامل يحجز قفل الاستعادة لفترة زمنية محددة في عملية مستقلة."""
    import os
    import time
    from pathlib import Path
    os.environ['TESTING'] = '1'
    try:
        from app.services.backup_service import CrossProcessRestoreLock
        lock = CrossProcessRestoreLock(owner="process_holder", timeout_seconds=15, lock_file_path=Path(lock_file))
        if lock.acquire(blocking=False):
            acquired_event.set()
            time.sleep(hold_duration)
            lock.release()
            released_event.set()
    except Exception:
        pass


# ─── A. Cross-Process Restore Lock Tests ───────────────────────────────────────

def test_cross_process_restore_lock_blocks_second_process():
    """
    التحقق من أن قفل الاستعادة عبر العمليات يحظر العملية الثانية (Process B)
    عندما تكون العملية الأولى (Process A) مستحوذة على القفل.
    """
    temp_dir = tempfile.mkdtemp()
    lock_file = os.path.join(temp_dir, "test_restore.lock")
    try:
        acquired_evt = multiprocessing.Event()
        released_evt = multiprocessing.Event()
        p1 = multiprocessing.Process(target=_mp_worker_hold_restore_lock, args=(lock_file, 1.5, acquired_evt, released_evt))
        p1.start()

        # انتظار تأكيد الاستحواذ من العملية الأولى
        assert acquired_evt.wait(timeout=15) is True, "فشلت العملية الأولى في حجز القفل"

        # محاولة حجز القفل من العملية الحالية (يجب أن ترفض فوراً)
        lock2 = CrossProcessRestoreLock(owner="process_b", timeout_seconds=1, lock_file_path=Path(lock_file))
        assert lock2.acquire(blocking=False) is False, "تم السماح للعملية الثانية بحجز القفل وهو محجوز مسبقاً!"

        # انتظار تحرير القفل وانتهاء العملية
        assert released_evt.wait(timeout=15) is True, "فشلت العملية الأولى في تحرير القفل"
        p1.join(timeout=5)

        # بعد انتهاء العملية الأولى وتحرير القفل، يجب أن تنجح العملية الثانية
        time.sleep(0.1)
        assert lock2.acquire(blocking=False) is True, "فشلت العملية الثانية في حجز القفل بعد تحريره"
        lock2.release()
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_cross_process_restore_lock_recovers_stale_lock():

    """التحقق من استرداد القفل وتجاوز الأقفال الميتة (Stale Locks) منتهية الصلاحية."""
    temp_dir = tempfile.mkdtemp()
    lock_file = Path(temp_dir) / "stale_restore.lock"
    try:
        # كتابة قفل ميت ومنتهي الصلاحية مع PID وهمي
        stale_payload = {
            'token': str(uuid.uuid4()),
            'owner': 'dead_process',
            'pid': 99999999,
            'acquired_at': '2026-01-01T00:00:00Z',
            'expires_at': time.time() - 100  # منتهي منذ 100 ثانية
        }
        with open(lock_file, 'w', encoding='utf-8') as f:
            json.dump(stale_payload, f)

        # محاولة حجز القفل الجديد
        active_lock = CrossProcessRestoreLock(owner="recovery_process", timeout_seconds=60, lock_file_path=lock_file)
        assert active_lock.acquire(blocking=False) is True
        assert active_lock._acquired is True
        active_lock.release()
        assert not lock_file.exists()
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_cross_process_restore_lock_released_on_exception():
    """التحقق من تحرير القفل تلقائياً عند حدوث استثناء داخل كتلة السياق (Context Manager)."""
    temp_dir = tempfile.mkdtemp()
    lock_file = Path(temp_dir) / "exc_restore.lock"
    try:
        with pytest.raises(ValueError, match="خطأ اختباري متعمد"):
            with CrossProcessRestoreLock(owner="exc_tester", lock_file_path=lock_file):
                assert lock_file.exists()
                raise ValueError("خطأ اختباري متعمد")

        assert not lock_file.exists(), "لم يتم تحرير القفل بعد حدوث الاستثناء"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ─── B. True Multi-Process Reference Allocation Tests ──────────────────────────

def test_true_multi_process_reference_allocation(isolated_db_path):
    """
    اختبار الأمان الحقيقي عبر عمليات نظام التشغيل المنفصلة (True Multiprocessing):
    - تشغيل 4 عمليات Python منفصلة تماماً ومستقلة.
    - كل عملية تحجز 25 رقماً مرجعياً (إجمالي 100 حجز متزامن).
    - التحقق الصارم من:
      1. عدم وجود أي رقم مكرر نهائياً (0 duplicates).
      2. عدم فقدان أي زيادة تسلسلية (0 lost increments).
      3. القيمة النهائية لجدول التسلسل تساوي تماماً 100.
    """
    num_processes = 4
    allocs_per_process = 25
    expected_total = num_processes * allocs_per_process

    queue = multiprocessing.Queue()
    processes = []

    for _ in range(num_processes):
        p = multiprocessing.Process(
            target=_mp_worker_allocate_references,
            args=(isolated_db_path, allocs_per_process, queue)
        )
        processes.append(p)
        p.start()

    all_refs = []
    for _ in range(num_processes):
        all_refs.extend(queue.get(timeout=30))

    for p in processes:
        p.join(timeout=10)

    # 1. التحقق من العدد الكلي
    assert len(all_refs) == expected_total, f"المتوقع {expected_total} حجز، والفعلي {len(all_refs)}"

    # 2. التحقق من انعدام التكرار
    unique_refs = set(all_refs)
    assert len(unique_refs) == expected_total, f"تم اكتشاف أرقام مكررة! الفريدة {len(unique_refs)} من أصل {expected_total}"

    # 3. التحقق من تنسيق الأرقام
    for r in all_refs:
        assert r.startswith("RES-2026-"), f"تنسيق غير متوافق: {r}"

    # 4. فحص القيمة النهائية في قاعدة البيانات
    conn = sqlite3.connect(isolated_db_path)
    cur = conn.cursor()
    cur.execute("SELECT last_value FROM reference_sequences WHERE namespace = 'research' AND year = 2026;")
    row = cur.fetchone()
    conn.close()

    assert row is not None
    assert row[0] == expected_total, f"القيمة النهائية للتسلسل غير مطابقة: المتوقع {expected_total}، الفعلي {row[0]}"


# ─── C. Multi-Process Reference Corpus Versioning Tests ────────────────────────

def test_multi_process_reference_corpus_versioning(isolated_db_path):
    """
    التحقق من تخصيص إصدارات قاعدة المراجع عبر عمليات متعددة (REF-2026-XXXXXX):
    - تشغيل 3 عمليات مستقلة تحجز 15 إصداراً متزامناً لكل منها (إجمالي 45).
    - التأكد من عدم وجود أي تضارب أو أرقام مكررة أو زيادات مفقودة.
    """
    num_processes = 3
    versions_per_process = 15
    expected_total = num_processes * versions_per_process

    queue = multiprocessing.Queue()
    processes = []

    for _ in range(num_processes):
        p = multiprocessing.Process(
            target=_mp_worker_corpus_version,
            args=(isolated_db_path, versions_per_process, queue)
        )
        processes.append(p)
        p.start()

    all_versions = []
    for _ in range(num_processes):
        all_versions.extend(queue.get(timeout=30))

    for p in processes:
        p.join(timeout=10)

    assert len(all_versions) == expected_total
    assert len(set(all_versions)) == expected_total, "تم اكتشاف تضارب في معرفات إصدارات المراجع"

    for ver in all_versions:
        assert ver.startswith("REF-2026-")

    conn = sqlite3.connect(isolated_db_path)
    cur = conn.cursor()
    cur.execute("SELECT last_value FROM reference_sequences WHERE namespace = 'reference_corpus' AND year = 2026;")
    row = cur.fetchone()
    conn.close()

    assert row is not None
    assert row[0] == expected_total


# ─── D. Application-Level File Snapshot Consistency Tests ──────────────────────

def test_backup_ignores_staging_and_temporary_files(app_instance):
    """
    التحقق من أن عملية النسخ الاحتياطي تتضمن الملفات المعتمدة النهائية فقط
    وتتجاهل تماماً الملفات المؤقتة وملفات الرفع غير المكتملة (.tmp, .staging).
    """
    import config
    from app.services import storage_service
    with app_instance.app_context():
        upload_dir = config.TEMP_UPLOAD_DIR
        upload_dir.mkdir(parents=True, exist_ok=True)

        # 1. إنشاء ملف نهائي معتمد عبر دورة الحياة الذرية الصحيحة وتسجيله في DB
        saved = storage_service.save_stream_atomically(
            file_stream=b"\xd9\x87\xd8\xb0\xd8\xa7 \xd9\x85\xd9\x84\xd9\x81 \xd8\xa8\xd8\xad\xd8\xab \xd9\x85\xd8\xb9\xd8\xaa\xd9\x85\xd8\xaf.",
            original_filename="finalized_thesis_doc.docx",
            target_dir=upload_dir
        )
        stored_name = saved['stored_filename']
        r_id = batch_repo.create_research(
            title="بحث اختبار الاستبعاد",
            author="باحث اختبار",
            created_by="test_admin"
        )
        batch_repo.add_research_file(
            research_id=r_id,
            original_filename=saved['original_filename'],
            stored_filename=saved['stored_filename'],
            file_path=saved['file_path'],
            file_type=saved['file_type'],
            file_size_bytes=saved['file_size_bytes'],
            file_order=0,
            file_hash=saved['file_hash']
        )

        # 2. إنشاء ملفات مؤقتة وقيد الرفع (غير مسجلة في DB أبداً)
        temp_file1 = upload_dir / "upload_partial.tmp"
        temp_file1.write_text("ملف مؤقت قيد الكتابة", encoding='utf-8')

        temp_file2 = upload_dir / "_staging_upload_12345.bin"
        temp_file2.write_text("ملف staging", encoding='utf-8')

        temp_file3 = upload_dir / "stream_chunk.part"
        temp_file3.write_text("ملف غير مكتمل", encoding='utf-8')

        try:
            # إنشاء النسخة الاحتياطية
            backup_result = create_institutional_backup(
                created_by="test_admin",
                backup_type="full",
                label="اختبار استبعاد الملفات المؤقتة"
            )

            zip_path = Path(backup_result['file_path'])
            assert zip_path.exists()

            with zipfile.ZipFile(zip_path, 'r') as zf:
                names = zf.namelist()
                # يجب تضمين الملف المعتمد المسجل في DB
                assert f"research_files/{stored_name}" in names
                # يجب استبعاد الملفات المؤقتة غير المسجلة كلياً
                assert "research_files/upload_partial.tmp" not in names
                assert "research_files/_staging_upload_12345.bin" not in names
                assert "research_files/stream_chunk.part" not in names

        finally:
            for f in [temp_file1, temp_file2, temp_file3]:
                if f.exists():
                    f.unlink()
            # تنظيف سجل الاختبار من قاعدة البيانات (inline)
            try:
                from app.models.research_schema import Research
                with base_repo.get_session() as session:
                    r = session.get(Research, r_id)
                    if r:
                        session.delete(r)
                        session.commit()
            except Exception:
                pass


# ─── E. Restore Continuity Recheck Tests ───────────────────────────────────────

def test_restore_continuity_preserves_safety_snapshot_and_audit(app_instance):
    """
    التحقق من استمرارية سجلات التدقيق وفهرس النسخ عند الاستعادة:
    1. إنشاء نسخة احتياطية قديمة (Backup A).
    2. إجراء نشاط جديد في النظام.
    3. استعادة النسخة القديمة (Backup A).
    4. التحقق من أن نسخة الأمان المسبقة (Pre-Restore Snapshot) مسجلة وقابلة للاكتشاف في الفهرس.
    5. التحقق من توثيق حدث بدء واكتمال الاستعادة دون فقدان سجل التشغيل.
    """
    with app_instance.app_context():
        # 1. إنشاء نسخة احتياطية أولية
        old_backup = create_institutional_backup(
            created_by="system",
            backup_type="full",
            label="النسخة الأساسية الأولى"
        )
        old_backup_id = old_backup['backup_identifier']

        # 2. إضافة بحث جديد بعد النسخة الأولى
        batch_repo.create_research(
            title="بحث تجريبي تمت إضافته بعد النسخة الأولى",
            author="باحث تجريبي",
            created_by="system"
        )

        # 3. استعادة النسخة الأولى
        restore_result = restore_institutional_backup(
            backup_identifier=old_backup_id,
            confirmation=old_backup_id,
            current_user={'username': 'admin_continuity', 'role': 'admin'}
        )

        assert restore_result['success'] is True
        safety_backup_id = restore_result.get('safety_backup_id')
        assert safety_backup_id is not None, "لم يتم إنشاء نسخة طوارئ مسبقة قبل الاستعادة"

        # 4. التأكد من أن نسخة الطوارئ المسبقة موجودة ومسجلة في الفهرس بعد استعادة قاعدة البيانات
        safety_entry = backup_repo.get_backup_entry(safety_backup_id)
        assert safety_entry is not None, "نسخة الأمان المسبقة مفقودة من فهرس قاعدة البيانات المستعادة"
        assert safety_entry['backup_type'] == 'pre_restore'
        assert safety_entry['status'] == 'completed'

        # 5. التأكد من توثيق حدث اكتمال الاستعادة
        audit_res = audit_service.query_audit_logs(category="backup", action="backup.restore_completed")
        audit_events = audit_res.get('items', []) if isinstance(audit_res, dict) else audit_res
        assert len(audit_events) > 0, "سجل اكتمال الاستعادة مفقود من audit_logs بعد الاستعادة"
