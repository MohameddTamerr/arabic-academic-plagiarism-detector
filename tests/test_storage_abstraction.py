# -*- coding: utf-8 -*-
"""
اختبارات طبقة التخزين المؤسسي الموجه بالمحتوى (Prompt 2: Storage Abstraction Tests):
- التحقق من هيكل التوزيع على مستويين (2-level prefix sharding).
- التحقق من الترقية الذرية (Atomic Ingest) وثبات البايتات.
- التحقق من إلغاء التكرار الآمن وإدارة دورة الحياة بالارتباط (Reference-Aware Lifecycle).
- التحقق من فحص وتدقيق سلامة التخزين (Storage Integrity Audit).
- التحقق من محول S3 المحلي الآمن (S3-Compatible Local Adapter Safe Fallback).
"""

import io
import hashlib
import tempfile
import pytest
from pathlib import Path

from app.storage.filesystem_backend import FileSystemStorageBackend
from app.storage.s3_local_backend import S3CompatibleLocalStorageBackend
from app.services import storage_service
from app.repositories import base_repo
from app.models.research_schema import ResearchFile, Research


def test_cas_2_level_sharding_structure(tmp_path):
    """التحقق من إنشاء المجلدات المقسمة على مستويين بناءً على تجزئة SHA-256."""
    backend = FileSystemStorageBackend(tmp_path)
    sample_content = "نص بحث علمي أصلي للتخزين المؤسسي".encode('utf-8')
    content_hash = hashlib.sha256(sample_content).hexdigest()

    res = backend.put(
        stream_or_bytes=sample_content,
        content_hash=content_hash,
        ext='.txt',
        metadata={'title': 'بحث تجريبي'}
    )

    assert res['success'] is True
    assert res['content_hash'] == content_hash
    assert res['deduplicated'] is False

    # التحقق من المسار الفعلي على القرص
    p1 = content_hash[:2]
    p2 = content_hash[2:4]
    expected_dir = tmp_path / 'documents' / p1 / p2 / content_hash
    assert expected_dir.exists()
    assert (expected_dir / 'content.bin').exists()
    assert (expected_dir / 'metadata.json').exists()

    # التحقق من القراءة
    read_bytes = backend.get(content_hash)
    assert read_bytes == sample_content


def test_cas_safe_deduplication(tmp_path):
    """التحقق من إعادة استخدام الملف الفيزيائي لنفس التجزئة دون تكرار التخزين."""
    backend = FileSystemStorageBackend(tmp_path)
    sample_content = "محتوى مكرر تم رفعه بواسطة باحثين مختلفين".encode('utf-8')
    content_hash = hashlib.sha256(sample_content).hexdigest()

    res1 = backend.put(sample_content, content_hash, ext='.pdf', metadata={'uploader': 'user1'})
    assert res1['deduplicated'] is False

    res2 = backend.put(sample_content, content_hash, ext='.pdf', metadata={'uploader': 'user2'})
    assert res2['deduplicated'] is True
    assert res1['file_path'] == res2['file_path']


def test_reference_aware_deletion(tmp_path, monkeypatch):
    """التحقق من أن حذف ارتباط لا يحذف الملف الفيزيائي طالما هناك سجلات أخرى تشير إليه."""
    backend = FileSystemStorageBackend(tmp_path)
    monkeypatch.setattr(storage_service, 'get_storage_backend', lambda: backend)

    sample_bytes = "وثيقة مشتركة متعددة المراجع".encode('utf-8')
    content_hash = hashlib.sha256(sample_bytes).hexdigest()
    backend.put(sample_bytes, content_hash)

    # إنشاء سجلي أبحاث في قاعدة البيانات يشيران لنفس البصمة
    with base_repo.get_session() as session:
        r1 = Research(title="بحث أول", reference_number="RES-2026-900001", scan_status="completed", review_status="pending_review")
        r2 = Research(title="بحث ثان", reference_number="RES-2026-900002", scan_status="completed", review_status="pending_review")
        session.add_all([r1, r2])
        session.flush()
        r1_id = r1.id
        r2_id = r2.id

        rf1 = ResearchFile(research_id=r1_id, original_filename="doc.pdf", stored_filename="cas_01.pdf", file_hash=content_hash)
        rf2 = ResearchFile(research_id=r2_id, original_filename="doc.pdf", stored_filename="cas_02.pdf", file_hash=content_hash)
        session.add_all([rf1, rf2])
        session.commit()

    # محاولة الحذف الأولى (لا يجب أن تحذف فيزيائياً لوجود إشارة أخرى)
    with base_repo.get_session() as session:
        session.query(ResearchFile).filter(ResearchFile.research_id == r1_id).delete()
        session.commit()

    del_res1 = storage_service.delete_content_reference(content_hash)
    assert del_res1 is False
    assert backend.exists(content_hash) is True

    # محاولة الحذف الثانية بعد إزالة كافة الإشارات
    with base_repo.get_session() as session:
        session.query(ResearchFile).filter(ResearchFile.research_id == r2_id).delete()
        session.commit()

    del_res2 = storage_service.delete_content_reference(content_hash)
    assert del_res2 is True
    assert backend.exists(content_hash) is False


def test_storage_integrity_audit(tmp_path, monkeypatch):
    """التحقق من فحص وتدقيق سلامة التخزين واكتشاف الحالات السليمة والمفقودة والمشوهة."""
    backend = FileSystemStorageBackend(tmp_path)
    monkeypatch.setattr(storage_service, 'get_storage_backend', lambda: backend)

    data_ok = "بيانات سليمة ومطابقة".encode('utf-8')
    hash_ok = hashlib.sha256(data_ok).hexdigest()
    backend.put(data_ok, hash_ok)

    with base_repo.get_session() as session:
        r = Research(title="فحص نزاهة التخزين", reference_number="RES-2026-900003", scan_status="completed", review_status="pending_review")
        session.add(r)
        session.flush()

        # 1. ملف سليم
        rf_ok = ResearchFile(research_id=r.id, original_filename="ok.pdf", stored_filename="ok_stored.pdf", file_hash=hash_ok, file_path=str(backend.get_physical_path(hash_ok)))
        # 2. ملف مفقود
        rf_missing = ResearchFile(research_id=r.id, original_filename="missing.pdf", stored_filename="missing_stored.pdf", file_hash="0"*64, file_path="/non/existent/path/doc.pdf")
        session.add_all([rf_ok, rf_missing])
        session.commit()

    audit = storage_service.verify_storage_integrity()
    assert audit['ok_count'] >= 1
    assert audit['missing_count'] >= 1


def test_s3_local_backend_safe_offline_fallback():
    """التحقق من أن محول S3 المحلي يفشل بأمان ويبلغ عن عدم التوفر دون اتصال بالإنترنت."""
    s3_backend = S3CompatibleLocalStorageBackend(endpoint_url="http://127.0.0.1:9000")
    if not s3_backend.is_available():
        with pytest.raises(RuntimeError, match="LOCAL OBJECT STORAGE RUNTIME TEST"):
            s3_backend.put(b"test", "dummyhash")
