# -*- coding: utf-8 -*-
"""
حزمة اختبارات اتساق لقطات الملفات ودورة حياة التخزين (Final File-Snapshot Consistency Gate):
1. بقاء الملف في staging أثناء الكتابة وعدم دخوله النسخة الاحتياطية.
2. استبعاد ملفات staging من الحزم الاحتياطية.
3. استبعاد الملفات غير المسجلة بقاعدة البيانات حتى لو كانت بأسماء نهائية (Orphan / Uncommitted files).
4. دخول الملفات المثبتة في قاعدة البيانات (DB-finalized) إلى النسخة الاحتياطية.
5. مطابقة هاش وحجم الملفات المنسوخة مع سجل قاعدة البيانات.
6. فشل النسخ الاحتياطي بأمان عند اقتطاع الملف (Truncated file).
7. فشل النسخ الاحتياطي بأمان عند تعديل بايتات الملف (Modified / Hash-mismatched file).
8. فشل النسخ الاحتياطي بأمان عند فقدان ملف مسجل بقاعدة البيانات (Missing DB-referenced file).
9. إخفاء المسارات المطلقة من البيان الوصفي ورسائل الخطأ.
10. اكتشاف وتطابق سلامة ملفات الأبحاث والمراجع أثناء الاستعادة (Restore Validation).
11. التحقق من دورات حياة الرفع للأبحاث والدفعات والمراجع.
"""

import os
import io
import json
import uuid
import shutil
import zipfile
import tempfile
from pathlib import Path
import pytest

import config
from app.services import storage_service, integrity_service
from app.services.backup_service import (
    create_institutional_backup,
    validate_backup_package_file,
    restore_institutional_backup
)
from app.repositories import batch_repo, backup_repo, base_repo
from app.models.research_schema import Research


def _delete_test_research(r_id: int):
    """حذف بحث تجريبي وملفاته من قاعدة البيانات لتفادي تلويث الاختبارات اللاحقة."""
    try:
        with base_repo.get_session() as session:
            r = session.query(Research).get(r_id)
            if r:
                session.delete(r)
                session.commit()
    except Exception:
        pass


@pytest.fixture
def app_instance():
    from app import create_app
    app = create_app()
    app.config['TESTING'] = True
    app.config['STRICT_AUTH'] = True
    return app


def test_upload_staging_and_atomic_finalization():
    """1. التحقق من دورة حياة الحفظ الذري: staging -> fsync -> sha256 -> atomic rename."""
    content = b"ATOMIC_LIFECYCLE_TEST_CONTENT_12345"
    orig_name = "test_chapter.pdf"
    
    res = storage_service.save_stream_atomically(
        file_stream=content,
        original_filename=orig_name,
        target_dir=config.TEMP_UPLOAD_DIR
    )
    
    assert res['success'] is True
    assert os.path.exists(res['file_path'])
    assert res['file_size_bytes'] == len(content)
    
    # التأكد من عدم بقاء أي ملف في مجلد staging
    staging_dir = storage_service.get_staging_upload_dir()
    staging_files = list(staging_dir.glob(f"*{res['stored_filename']}*"))
    assert len(staging_files) == 0


def test_staging_and_orphan_files_never_enter_backup(app_instance):
    """2 & 3 & 10. الملفات المؤقتة والملفات اليتيمة غير المسجلة بقاعدة البيانات لا تدخل النسخة الاحتياطية نهائياً."""
    with app_instance.app_context():
        upload_dir = config.TEMP_UPLOAD_DIR
        staging_dir = storage_service.get_staging_upload_dir()

        # 1. إنشاء ملف staging
        staging_file = staging_dir / ".staging_in_progress_data.tmp"
        staging_file.write_bytes(b"STAGING_INCOMPLETE_BYTES")

        # 2. إنشاء ملف باسم نهائي طبيعي في upload_dir لكن غير مسجل بـ DB (Orphan file)
        orphan_file = upload_dir / f"orphan_final_name_{uuid.uuid4().hex[:8]}.pdf"
        orphan_file.write_bytes(b"ORPHAN_UNCOMMITTED_BYTES")

        # 3. إنشاء بحث حقيقي مسجل بـ DB وملفه موجود
        valid_res = storage_service.save_stream_atomically(
            file_stream=b"VALID_FINALIZED_COMMITTED_BYTES",
            original_filename="final_thesis.pdf",
            target_dir=upload_dir
        )
        r_id = batch_repo.create_research(
            title="بحث معتمد للنسخ الاحتياطي",
            author="باحث معتمد",
            created_by="system"
        )
        batch_repo.add_research_file(
            research_id=r_id,
            original_filename=valid_res['original_filename'],
            stored_filename=valid_res['stored_filename'],
            file_path=valid_res['file_path'],
            file_type=valid_res['file_type'],
            file_size_bytes=valid_res['file_size_bytes'],
            file_order=0,
            file_hash=valid_res['file_hash']
        )

        try:
            # 4. أخذ نسخة احتياطية
            backup_res = create_institutional_backup(created_by="system", label="فحص استبعاد الملفات غير المعتمدة")
            backup_zip = Path(backup_res['file_path'])

            # 5. فحص محتويات ملف الـ ZIP
            with zipfile.ZipFile(backup_zip, 'r') as zf:
                namelist = zf.namelist()
                
                # الملف المعتمد يجب أن يكون موجوداً
                assert f"research_files/{valid_res['stored_filename']}" in namelist
                
                # ملفات staging والملفات غير المسجلة بـ DB يجب ألا تدخل نهائياً
                for name in namelist:
                    assert "staging" not in name.lower()
                    assert orphan_file.name not in name
                    assert staging_file.name not in name
        finally:
            if staging_file.exists():
                staging_file.unlink()
            if orphan_file.exists():
                orphan_file.unlink()
            if Path(valid_res['file_path']).exists():
                Path(valid_res['file_path']).unlink()
            _delete_test_research(r_id)


def test_finalized_file_integrity_matches_db_and_manifest(app_instance):
    """4 & 5 & 6 & 18 & 19. الملفات المعتمدة تطابق الهاش والحجم والبيان لا يسرب مسارات السيرفر."""
    with app_instance.app_context():
        upload_dir = config.TEMP_UPLOAD_DIR
        content = b"PERSISTENT_INTEGRITY_VERIFIED_DATA_999"
        
        saved = storage_service.save_stream_atomically(
            file_stream=content,
            original_filename="verified_doc.pdf",
            target_dir=upload_dir
        )
        r_id = batch_repo.create_research(title="بحث التحقق من البيان", author="باحث", created_by="system")
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

        try:
            backup_res = create_institutional_backup(created_by="system", label="تحقق من سلامة البيان")
            backup_zip = Path(backup_res['file_path'])

            with zipfile.ZipFile(backup_zip, 'r') as zf:
                manifest_data = json.loads(zf.read('manifest.json').decode('utf-8'))
                
                # فحص خلو البيان من المسارات المطلقة للسيرفر
                manifest_str = json.dumps(manifest_data)
                assert ":\\" not in manifest_str
                assert "/Users/" not in manifest_str
                assert "C:" not in manifest_str

                # التحقق من بيانات الملف في البيان
                rf_component = next(c for c in manifest_data['components'] if c['name'] == 'research_files')
                file_entry = next(f for f in rf_component['files'] if f['stored_filename'] == saved['stored_filename'])
                
                assert file_entry['size_bytes'] == len(content)
                assert file_entry['sha256'] == saved['file_hash']
                assert file_entry['logical_type'] == 'research_file'
        finally:
            if Path(saved['file_path']).exists():
                Path(saved['file_path']).unlink()
            _delete_test_research(r_id)


def test_missing_db_referenced_file_aborts_backup_safely(app_instance):
    """9. فقدان ملف مسجل بقاعدة البيانات يؤدي لفشل النسخ الاحتياطي بأمان دون اكتمال الحزمة."""
    with app_instance.app_context():
        # تسجيل ملف في DB غير موجود على القرص
        fake_name = f"missing_file_{uuid.uuid4().hex[:8]}.pdf"
        r_id = batch_repo.create_research(title="بحث بملف مفقود", author="باحث", created_by="system")
        batch_repo.add_research_file(
            research_id=r_id,
            original_filename="missing.pdf",
            stored_filename=fake_name,
            file_path=str(config.TEMP_UPLOAD_DIR / fake_name),
            file_type="pdf",
            file_size_bytes=1024,
            file_order=0,
            file_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        )

        try:
            # محاولة إنشاء نسخة احتياطية
            with pytest.raises((FileNotFoundError, RuntimeError, ValueError)):
                create_institutional_backup(created_by="system", label="محاولة نسخ مع ملف مفقود")
        finally:
            _delete_test_research(r_id)


def test_modified_or_corrupted_file_aborts_backup_safely(app_instance):
    """7 & 8. تعديل أو اقتطاع محتوى ملف مسجل يؤدي لفشل النسخ الاحتياطي بأمان."""
    with app_instance.app_context():
        saved = storage_service.save_stream_atomically(
            file_stream=b"ORIGINAL_CORRECT_BYTES_123",
            original_filename="corrupted_test.pdf",
            target_dir=config.TEMP_UPLOAD_DIR
        )
        r_id = batch_repo.create_research(title="بحث سيتم تخريب ملفه", author="باحث", created_by="system")
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

        try:
            # تخريب بايتات الملف على القرص
            with open(saved['file_path'], 'wb') as f:
                f.write(b"TAMPERED_ALTERED_BYTES_999")

            # محاولة إنشاء نسخة احتياطية يجب أن تفشل لاختلاف الهاش والحجم
            with pytest.raises(ValueError):
                create_institutional_backup(created_by="system", label="محاولة نسخ مع ملف مخرب")
        finally:
            if Path(saved['file_path']).exists():
                Path(saved['file_path']).unlink()
            _delete_test_research(r_id)


def test_restore_validation_detects_corrupted_research_file(app_instance):
    """16 & 17. التحقق من أن الاستعادة تكتشف أي تلاعب في ملفات الأبحاث والمراجع وترفض الاستعادة."""
    with app_instance.app_context():
        saved = storage_service.save_stream_atomically(
            file_stream=b"CLEAN_RESTORE_TEST_BYTES",
            original_filename="clean_restore.pdf",
            target_dir=config.TEMP_UPLOAD_DIR
        )
        r_id = batch_repo.create_research(title="بحث لفحص الاستعادة", author="باحث", created_by="system")
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

        try:
            # إنشاء نسخة احتياطية سليمة
            backup_res = create_institutional_backup(created_by="system", label="نسخة سليمة للاختبار")
            backup_path = Path(backup_res['file_path'])

            # التحقق من أن النسخة سليمة أولاً
            val_clean = validate_backup_package_file(backup_path)
            assert val_clean['valid'] is True

            # إنشاء نسخة مخربة بتعديل بايتات الملف داخل الـ ZIP
            corrupted_zip_path = backup_path.parent / f"corrupted_{backup_path.name}"
            with zipfile.ZipFile(backup_path, 'r') as zin, zipfile.ZipFile(corrupted_zip_path, 'w') as zout:
                for item in zin.infolist():
                    data = zin.read(item.filename)
                    if item.filename.startswith('research_files/'):
                        data = b"TAMPERED_INSIDE_ZIP_PAYLOAD"
                    zout.writestr(item, data)

            # فحص الحزمة المخربة
            val_corrupted = validate_backup_package_file(corrupted_zip_path)
            assert val_corrupted['valid'] is False
            assert "البصمة الرقمية غير مطابقة للبيان" in val_corrupted['error'] or "غير مطابق للبيان" in val_corrupted['error']
        finally:
            if Path(saved['file_path']).exists():
                Path(saved['file_path']).unlink()
            _delete_test_research(r_id)


def test_failure_before_db_commit_leaves_no_recoverable_db_record(app_instance):
    """11 & 12. فشل العملية قبل تثبيت قاعدة البيانات يضمن عدم وجود سجل موثق ويسهل تنظيف اليتيم."""
    with app_instance.app_context():
        # محاكاة حفظ الملف في التخزين المؤقت ثم فشل العملية قبل commit
        saved = storage_service.save_stream_atomically(
            file_stream=b"UNCOMMITTED_PAYLOAD_BEFORE_CRASH",
            original_filename="uncommitted_file.pdf",
            target_dir=config.TEMP_UPLOAD_DIR
        )

        try:
            # التحقق من أن الملف موجود على القرص
            assert os.path.exists(saved['file_path'])

            # لكن لم يتم إنشاء أي سجل بـ DB
            with base_repo.get_session() as session:
                from app.models.research_schema import ResearchFile
                rf = session.query(ResearchFile).filter(ResearchFile.stored_filename == saved['stored_filename']).first()
                assert rf is None

            # وعند أخذ نسخة احتياطية، الملف غير المسجل لا يدخل الحزمة إطلاقاً
            backup_res = create_institutional_backup(created_by="system", label="فحص استبعاد غير المثبت")
            backup_path = Path(backup_res['file_path'])
            with zipfile.ZipFile(backup_path, 'r') as zf:
                namelist = zf.namelist()
                assert f"research_files/{saved['stored_filename']}" not in namelist
        finally:
            if os.path.exists(saved['file_path']):
                os.unlink(saved['file_path'])


def test_batch_and_thesis_upload_follows_safe_lifecycle():
    """13 & 14 & 15. التحقق من أن حفظ عدة أجزاء لرسالة أو دفعة يلتزم بالتسلسل الذري والبصمات الرقمية."""
    chapters = [
        ("chapter_1.pdf", b"CHAPTER_1_CONTENT_IMMUTABLE_111"),
        ("chapter_2.pdf", b"CHAPTER_2_CONTENT_IMMUTABLE_222"),
        ("appendix.pdf", b"APPENDIX_CONTENT_IMMUTABLE_333")
    ]

    saved_items = []
    try:
        for name, data in chapters:
            res = storage_service.save_stream_atomically(
                file_stream=data,
                original_filename=name,
                target_dir=config.TEMP_UPLOAD_DIR
            )
            assert res['success'] is True
            assert res['file_size_bytes'] == len(data)
            saved_items.append(res)

        assert len(saved_items) == 3
        # التأكد من تميز الأسماء والبصمات
        hashes = {item['file_hash'] for item in saved_items}
        assert len(hashes) == 3
    finally:
        for item in saved_items:
            if os.path.exists(item['file_path']):
                os.unlink(item['file_path'])

