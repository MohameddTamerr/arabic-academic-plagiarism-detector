# -*- coding: utf-8 -*-
"""
حزمة اختبارات عزل بيئة الاختبارات وصمامات الأمان وقواعد اتساق النسخ الاحتياطي:
(Test Isolation & Backup Invariants Gate Tests):
1. التحقق من عزل قاعدة بيانات الاختبارات عن قاعدة الإنتاج الحية.
2. التحقق من عزل وسائط التخزين والنسخ الاحتياطي عن الإنتاج.
3. التحقق من تفعيل صمام الأمان (Fail-Safe Guard) ومنع استخدام مسار الإنتاج أثناء الفحص.
4. التحقق من استخدام العمليات الفرعية للـ Multiprocessing لقاعدة البيانات المعزولة.
5. التحقق من استبعاد سجلات البصمة فقط (registry_only) بنجاح وأمان من النسخ الاحتياطي.
6. التحقق من أن السجلات المعتمدة التالفة تفشل النسخ الاحتياطي ولا يتم تجاهلها صامتاً.
7. التحقق من أن الملفات المعتمدة المفقودة تفشل النسخ الاحتياطي بـ FileNotFoundError.
8. التحقق من أن المسار الفارغ على سجل معتمد يفشل النسخ الاحتياطي بـ FileNotFoundError.
9. التحقق من أن الملفات اليتيمة على القرص تُستبعد من النسخ الاحتياطي دون حذفها تلقائياً.
"""

import os
import sys
import io
import uuid
import time
import zipfile
import sqlite3
import multiprocessing
from pathlib import Path
import pytest

import app
import config
from app.models.research_schema import Research, ResearchFile, STORAGE_STATUS_FINALIZED, STORAGE_STATUS_REGISTRY_ONLY
from app.repositories import batch_repo, base_repo
from app.services import storage_service, backup_service, integrity_service


def _mp_probe_worker(db_path: str, result_queue: multiprocessing.Queue):
    """عامل فرعي يتأكد من استخدام المسار المعزول تحت TESTING=1."""
    import os
    import sys
    os.environ['TESTING'] = '1'
    os.environ['DATABASE_URL'] = f"sqlite:///{db_path}"
    import app
    import config
    from app.repositories import base_repo
    
    config.DATABASE_URL = f"sqlite:///{db_path}"
    config.DEFAULT_SQLITE_PATH = Path(db_path)
    base_repo.rebind_engine(config.DATABASE_URL)

    
    with base_repo.get_session() as session:
        conn = session.connection()
        # فحص المسار الفعلي المتصل به SQLite
        db_file = conn.connection.dbapi_connection.execute("PRAGMA database_list;").fetchall()
        connected_file = db_file[0][2] if db_file else ''
        
    result_queue.put(connected_file)


# ─── 1. اختبارات العزل وصمام الأمان ──────────────────────────────────────────

def test_database_is_isolated_from_live_db():
    """قاعدة بيانات الاختبارات منفصلة تماماً ومسارها مختلف عن مسار الإنتاج."""
    assert config.DEFAULT_SQLITE_PATH != config.LIVE_DEFAULT_SQLITE_PATH
    assert Path(config.DEFAULT_SQLITE_PATH).resolve() != Path(config.LIVE_DEFAULT_SQLITE_PATH).resolve()
    assert "test_papers.db" in str(config.DEFAULT_SQLITE_PATH)


def test_storage_is_isolated_from_live_storage():
    """مجلدات التخزين المؤقت والرفع والنسخ الاحتياطي معزولة بالكامل في مجلد مؤقت."""
    assert config.STORAGE_ROOT != (config.LIVE_DEFAULT_SQLITE_PATH.parent / 'storage')
    assert config.TEMP_UPLOAD_DIR.exists()
    assert config.BACKUP_DIR.exists()


def test_failsafe_guard_blocks_live_db_access_under_testing():
    """صمام الأمان يُطلق خطأ RuntimeError صريحاً إذا حاول أي استدعاء الاتصال بمسار الإنتاج تحت TESTING=1."""
    from app.repositories.base_repo import _check_fail_safe
    
    # محاولة تمرير مسار قاعدة البيانات الحية
    live_url = f"sqlite:///{config.LIVE_DEFAULT_SQLITE_PATH.as_posix()}"
    with pytest.raises(RuntimeError) as exc_info:
        _check_fail_safe(live_url)
    assert "FAIL-SAFE GUARD ACTIVATED" in str(exc_info.value)


def test_child_multiprocess_strictly_uses_isolated_db(tmp_path):
    """العملية الفرعية في multiprocessing تستخدم المسار المعزول الممرر لها دون الرجوع للإنتاج."""
    temp_db = tmp_path / "child_isolated.db"
    
    # تهيئة جداول سريعة في قاعدة البيانات المؤقتة
    conn = sqlite3.connect(str(temp_db))
    conn.execute("CREATE TABLE test_tab (id INT);")
    conn.commit()
    conn.close()
    
    q = multiprocessing.Queue()
    p = multiprocessing.Process(target=_mp_probe_worker, args=(str(temp_db), q))
    p.start()
    p.join(timeout=10)
    
    connected_path = q.get(timeout=5)
    assert connected_path != ''
    assert Path(connected_path).resolve() == Path(temp_db).resolve()
    assert Path(connected_path).resolve() != Path(config.LIVE_DEFAULT_SQLITE_PATH).resolve()


# ─── 2. اختبارات قواعد النسخ الاحتياطي وحالات التخزين (Invariants) ────────────

def _delete_test_research(r_id: int):
    """حذف بحث وملفاته من قاعدة البيانات لتفادي التأثير على الاختبارات التالية."""
    try:
        with base_repo.get_session() as session:
            r = session.get(Research, r_id)
            if r:
                session.delete(r)
                session.commit()
    except Exception:
        pass


def test_registry_only_record_is_safely_excluded_from_backup():
    """سجل البصمة الرقمية فقط (registry_only) يُستبعد بنجاح من النسخ الاحتياطي دون أخطاء."""
    r_id = batch_repo.create_research(title="بحث بصمة تجريبي", author="باحث تجريبي")
    try:
        # إضافة سجل بدون ملف فيزيائي وموسوم كـ registry_only
        rf_id = batch_repo.add_research_file(
            research_id=r_id,
            original_filename="dedup_stub.pdf",
            stored_filename="dedup_stub_nonexistent.pdf",
            file_path="",
            file_type="pdf",
            file_size_bytes=1024,
            file_order=0,
            file_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            storage_status=STORAGE_STATUS_REGISTRY_ONLY
        )
        
        # أخذ نسخة احتياطية يجب أن ينجح ويتجاوز السجل
        backup_res = backup_service.create_institutional_backup(created_by="system", label="اختبار استبعاد البصمة")
        assert backup_res['status'] == 'completed'
        
        # التحقق من أن السجل غير موجود في ملفات النسخة الاحتياطية داخل الـ ZIP
        with zipfile.ZipFile(backup_res['file_path'], 'r') as zf:
            names = zf.namelist()
            assert "research_files/dedup_stub_nonexistent.pdf" not in names
    finally:
        _delete_test_research(r_id)


def test_corrupted_finalized_record_cannot_be_silently_skipped():
    """السجل المعتمد (finalized) التالف بالهاش أو الحجم يفشل النسخ الاحتياطي ولا يُتجاهل بصمت."""
    saved = storage_service.save_stream_atomically(
        file_stream=b"VALID_ORIGINAL_BYTES_12345",
        original_filename="final_paper.pdf",
        target_dir=config.TEMP_UPLOAD_DIR
    )
    r_id = batch_repo.create_research(title="بحث تالف", author="باحث")
    try:
        batch_repo.add_research_file(
            research_id=r_id,
            original_filename=saved['original_filename'],
            stored_filename=saved['stored_filename'],
            file_path=saved['file_path'],
            file_type=saved['file_type'],
            file_size_bytes=saved['file_size_bytes'],
            file_order=0,
            file_hash=saved['file_hash'],
            storage_status=STORAGE_STATUS_FINALIZED
        )
        
        # تخريب الملف على القرص
        with open(saved['file_path'], 'wb') as f:
            f.write(b"CORRUPTED_TAMPERED_BYTES_99999")
            
        # محاولة أخذ نسخة احتياطية يجب أن تفشل برفع ValueError
        with pytest.raises(ValueError) as exc_info:
            backup_service.create_institutional_backup(created_by="system", label="فحص رفض التالف")
        assert "بصمة ملف البحث" in str(exc_info.value) or "غير مطابق" in str(exc_info.value)
    finally:
        _delete_test_research(r_id)
        if os.path.exists(saved['file_path']):
            os.unlink(saved['file_path'])


def test_missing_finalized_physical_file_fails_backup():
    """السجل المعتمد (finalized) الذي حُذف ملفه الفيزيائي يفشل النسخ الاحتياطي بـ FileNotFoundError."""
    saved = storage_service.save_stream_atomically(
        file_stream=b"FILE_WILL_BE_DELETED_SOON",
        original_filename="deleted_thesis.pdf",
        target_dir=config.TEMP_UPLOAD_DIR
    )
    r_id = batch_repo.create_research(title="بحث سيحذف ملفه", author="باحث")
    try:
        batch_repo.add_research_file(
            research_id=r_id,
            original_filename=saved['original_filename'],
            stored_filename=saved['stored_filename'],
            file_path=saved['file_path'],
            file_type=saved['file_type'],
            file_size_bytes=saved['file_size_bytes'],
            file_order=0,
            file_hash=saved['file_hash'],
            storage_status=STORAGE_STATUS_FINALIZED
        )
        
        # حذف الملف الفيزيائي من القرص
        os.unlink(saved['file_path'])
        
        # يجب أن يرفع FileNotFoundError ولا يتجاهله بصمت
        with pytest.raises(FileNotFoundError) as exc_info:
            backup_service.create_institutional_backup(created_by="system", label="فحص رفض الملف المفقود")
        assert "مفقود من وسيط التخزين" in str(exc_info.value)
    finally:
        _delete_test_research(r_id)


def test_null_or_empty_path_on_finalized_record_fails_backup():
    """السجل المعتمد (finalized) ذو المسار الفارغ في DB يفشل النسخ الاحتياطي بـ FileNotFoundError."""
    r_id = batch_repo.create_research(title="بحث بمسار فارغ", author="باحث")
    try:
        batch_repo.add_research_file(
            research_id=r_id,
            original_filename="empty_path.pdf",
            stored_filename="stored_empty.pdf",
            file_path="",  # مسار فارغ ولكن السجل موسوم كـ finalized
            file_type="pdf",
            file_size_bytes=100,
            file_order=0,
            file_hash="dummyhash123",
            storage_status=STORAGE_STATUS_FINALIZED
        )
        
        with pytest.raises(FileNotFoundError) as exc_info:
            backup_service.create_institutional_backup(created_by="system", label="فحص المسار الفارغ المعطل")
        assert "مسار التخزين الخاص به فارغ" in str(exc_info.value)
    finally:
        _delete_test_research(r_id)


def test_orphan_filesystem_file_is_excluded_from_backup_and_not_deleted():
    """الملفات اليتيمة على القرص غير المسجلة في DB تُستبعد من النسخة الاحتياطية ولا تُحذف تلقائياً."""
    orphan_file = config.TEMP_UPLOAD_DIR / f"orphan_doc_{uuid.uuid4().hex[:8]}.pdf"
    orphan_file.write_bytes(b"ORPHAN_UNREGISTERED_FILE_CONTENT")
    
    try:
        # اكتشاف الملف اليتيم عبر أداة الصيانة
        orphans = storage_service.detect_orphan_storage_files(config.TEMP_UPLOAD_DIR)
        assert any(orphan_file.name == o.name for o in orphans)
        
        # أخذ نسخة احتياطية
        backup_res = backup_service.create_institutional_backup(created_by="system", label="فحص الملف اليتيم")
        assert backup_res['status'] == 'completed'
        
        # 1. الملف لم يدخل النسخة الاحتياطية
        with zipfile.ZipFile(backup_res['file_path'], 'r') as zf:
            assert f"research_files/{orphan_file.name}" not in zf.namelist()
            
        # 2. الملف لم يُحذف تلقائياً أثناء النسخ الاحتياطي
        assert orphan_file.exists()
        
    finally:
        if orphan_file.exists():
            orphan_file.unlink()
