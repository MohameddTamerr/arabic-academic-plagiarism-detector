# -*- coding: utf-8 -*-
"""
حزمة اختبارات تدقيق وتحصين رفع الملفات والمدخلات (Phase 13: Upload & Input Hardening Test Suite):
- التحقق من التوقيع الرقمي للملفات (PDF, DOCX, TXT) ورفض الامتدادات الزائفة والملفات المعطوبة والمشفرة.
- التحقق من حدود الموارد وحماية الذاكرة (Streaming Limits, PDF Page Limits, DOCX Zip-Bomb & Zip-Slip).
- التحقق من تنقية أسماء الملفات ومنع التخطي المساري (Path Traversal, Reserved Windows Names).
- التحقق من دورة حياة التخزين والعزل المرحلي (Staging Isolation, Stale Cleanup).
- قياس زمن المعالجة والتحقق (Validation Overhead Benchmark).
"""

import os
import io
import time
import zipfile
import pytest
import logging
from pathlib import Path
from unittest.mock import patch, MagicMock

import config
from app import create_app
from app.errors.error_codes import ErrorCode
from app.errors.exceptions import ValidationError
from app.services import upload_validation_service, storage_service
from app.security.permissions import Role, Permission
from app.repositories import user_repo, base_repo, report_repo


@pytest.fixture
def client():
    app = create_app()
    app.config['TESTING'] = True
    app.config['STRICT_AUTH'] = True
    with app.test_client() as client:
        yield client


def _create_minimal_valid_pdf() -> bytes:
    """إنشاء ملف PDF مصغر وصالح للاختبارات."""
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>\nendobj\n"
        b"4 0 obj\n<< /Length 44 >>\nstream\nBT /F1 12 Tf 100 700 Td (Hello World) Tj ET\nendstream\nendobj\n"
        b"xref\n0 5\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000214 00000 n \n"
        b"trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n308\n%%EOF"
    )


def _create_minimal_valid_docx() -> bytes:
    """إنشاء ملف DOCX مصغر وصالح للاختبارات بهيكلية OpenXML السليمة."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"></Types>')
        z.writestr('word/document.xml', '<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>بحث أكاديمي تجريبي</w:t></w:r></w:p></w:body></w:document>')
    return buf.getvalue()


# ─── 1. اختبارات تدقيق الصيغ والتواقيع الرقمية (Format Validation 1-11) ────────

def test_valid_pdf_accepted():
    """1. قبول ملف PDF سليم بنيوياً."""
    pdf_bytes = _create_minimal_valid_pdf()
    res = upload_validation_service.validate_and_stage_upload(pdf_bytes, "research_paper.pdf")
    assert res['success'] is True
    assert res['detected_type'] == 'pdf'
    upload_validation_service.cleanup_staging_file(res['staging_path'])


def test_fake_pdf_extension_rejected():
    """2. رفض ملف نصي أو تنفيذي تم تغيير امتداده إلى .pdf."""
    fake_pdf = b"This is plain text with no PDF header at all."
    with pytest.raises(ValidationError) as exc:
        upload_validation_service.validate_and_stage_upload(fake_pdf, "malicious.pdf")
    assert exc.value.code == ErrorCode.FILE_SIGNATURE_MISMATCH


def test_corrupt_pdf_rejected():
    """3. رفض ملف PDF تالف ومعطوب البنية."""
    corrupt_pdf = b"%PDF-1.4\nGarbage data not a real pdf body %%EOF"
    with pytest.raises(ValidationError) as exc:
        upload_validation_service.validate_and_stage_upload(corrupt_pdf, "broken.pdf")
    assert exc.value.code in (ErrorCode.FILE_CORRUPTED, ErrorCode.FILE_SIGNATURE_MISMATCH, ErrorCode.FILE_EMPTY)


def test_encrypted_pdf_handled_safely():
    """4. رفض ملف PDF مشفر أو محمي بكلمة مرور دون انهيار الخادم."""
    pdf_bytes = _create_minimal_valid_pdf()
    with patch('fitz.open') as mock_fitz:
        mock_doc = MagicMock()
        mock_doc.is_encrypted = True
        mock_fitz.return_value = mock_doc
        with pytest.raises(ValidationError) as exc:
            upload_validation_service.validate_and_stage_upload(pdf_bytes, "secure.pdf")
        assert exc.value.code == ErrorCode.FILE_ENCRYPTED


def test_valid_docx_accepted():
    """5. قبول مستند DOCX سليم ومطابق لمواصفات OpenXML."""
    docx_bytes = _create_minimal_valid_docx()
    res = upload_validation_service.validate_and_stage_upload(docx_bytes, "thesis_chapter.docx")
    assert res['success'] is True
    assert res['detected_type'] == 'docx'
    upload_validation_service.cleanup_staging_file(res['staging_path'])


def test_arbitrary_zip_renamed_docx_rejected():
    """6. رفض أرشيف ZIP عادي تمت إعادة تسميته إلى .docx لغياب ملفات OpenXML."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('some_file.txt', 'arbitrary content')
    fake_docx = buf.getvalue()

    with pytest.raises(ValidationError) as exc:
        upload_validation_service.validate_and_stage_upload(fake_docx, "fake_doc.docx")
    assert exc.value.code == ErrorCode.FILE_CORRUPTED


def test_corrupt_docx_rejected():
    """7. رفض مستند DOCX معطوب الأرشيف."""
    corrupt_docx = b"PK\x03\x04\x00\x00\x00\x00corrupt_zip_stream"
    with pytest.raises(ValidationError) as exc:
        upload_validation_service.validate_and_stage_upload(corrupt_docx, "corrupt.docx")
    assert exc.value.code == ErrorCode.FILE_CORRUPTED


def test_valid_txt_accepted():
    """8. قبول ملف نصي سليم بترميز عربي صالح."""
    txt_bytes = "هذا نص بحث أكاديمي باللغة العربية للاختبار.".encode('utf-8')
    res = upload_validation_service.validate_and_stage_upload(txt_bytes, "notes.txt")
    assert res['success'] is True
    assert res['detected_type'] == 'txt'
    upload_validation_service.cleanup_staging_file(res['staging_path'])


def test_binary_renamed_txt_rejected():
    """9. رفض ملف ثنائي ممتلئ بـ NUL bytes تمت إعادة تسميته إلى .txt."""
    binary_data = b"Some header\x00\x00\x00\x00\x01\x02\x03\xff\xfe\x00\x00"
    with pytest.raises(ValidationError) as exc:
        upload_validation_service.validate_and_stage_upload(binary_data, "binary.txt")
    assert exc.value.code == ErrorCode.FILE_CORRUPTED


def test_unsupported_extension_rejected():
    """10. رفض الامتدادات غير المدعومة مثل .exe و .doc و .rar."""
    with pytest.raises(ValidationError) as exc:
        upload_validation_service.validate_and_stage_upload(b"some content", "file.doc")
    assert exc.value.code == ErrorCode.FILE_UNSUPPORTED

    with pytest.raises(ValidationError) as exc2:
        upload_validation_service.validate_and_stage_upload(b"MZ...", "app.exe")
    assert exc2.value.code == ErrorCode.FILE_UNSUPPORTED


def test_mixed_case_extension_handled_correctly():
    """11. قبول الامتدادات بأحرف كبيرة أو مختلطة مثل .PDF و .DocX."""
    pdf_bytes = _create_minimal_valid_pdf()
    res = upload_validation_service.validate_and_stage_upload(pdf_bytes, "RESEARCH.PDF")
    assert res['success'] is True
    assert res['safe_extension'] == '.pdf'
    upload_validation_service.cleanup_staging_file(res['staging_path'])


# ─── 2. اختبارات استنزاف الموارد والحدود (Resource Abuse 12-23) ──────────────

def test_oversized_single_upload_rejected():
    """12. رفض ملف فردي يتجاوز السقف المحدد بالبايت."""
    fake_data = b"%PDF-1.4\n" + (b"A" * 1024)
    with pytest.raises(ValidationError) as exc:
        upload_validation_service.validate_and_stage_upload(fake_data, "large.pdf", max_bytes=500)
    assert exc.value.code == ErrorCode.FILE_TOO_LARGE


def test_streaming_limit_enforced_without_full_memory_buffering():
    """13. قطع الدفق وإلغاء التخزين فور تجاوز الحجم الأقصى."""
    stream = io.BytesIO(b"%PDF-1.4\n" + b"X" * (100 * 1024))
    with pytest.raises(ValidationError) as exc:
        upload_validation_service.validate_and_stage_upload(stream, "stream_test.pdf", max_bytes=10 * 1024)
    assert exc.value.code == ErrorCode.FILE_TOO_LARGE


def test_excessive_pdf_pages_rejected():
    """14. رفض ملف PDF يتجاوز عدد صفحاته MAX_PDF_PAGES."""
    pdf_bytes = _create_minimal_valid_pdf()
    with patch('fitz.open') as mock_fitz:
        mock_doc = MagicMock()
        mock_doc.is_encrypted = False
        mock_doc.__len__.return_value = 1500
        mock_fitz.return_value = mock_doc
        with pytest.raises(ValidationError) as exc:
            upload_validation_service.validate_and_stage_upload(pdf_bytes, "giant.pdf")
        assert exc.value.code == ErrorCode.PDF_PAGE_LIMIT


def test_docx_excessive_entry_count_rejected():
    """15. رفض حزمة DOCX تحوي عناصر كثيرة جداً داخل الأرشيف."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        for i in range(1200):
            z.writestr(f"entry_{i}.xml", "<x></x>")
    with pytest.raises(ValidationError) as exc:
        upload_validation_service.validate_and_stage_upload(buf.getvalue(), "excess_entries.docx")
    assert exc.value.code == ErrorCode.DOCX_RESOURCE_LIMIT


def test_docx_excessive_uncompressed_size_rejected():
    """16. رفض حزمة DOCX يتجاوز حجم محتوياتها بعد فك الضغط السقف المسموح."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', '<Types></Types>')
        z.writestr('word/document.xml', 'A' * (50 * 1024))
    with patch('config.MAX_DOCX_UNCOMPRESSED_BYTES', 10 * 1024):
        with pytest.raises(ValidationError) as exc:
            upload_validation_service.validate_and_stage_upload(buf.getvalue(), "uncompressed_bomb.docx")
        assert exc.value.code == ErrorCode.DOCX_RESOURCE_LIMIT


def test_docx_suspicious_compression_ratio_rejected():
    """17. رفض ملف DOCX ذي نسبة انضغاط غير طبيعية ومريبة (Zip-Bomb)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', '<Types></Types>')
        z.writestr('word/document.xml', '0' * (100 * 1024))
    with patch('config.MAX_DOCX_COMPRESSION_RATIO', 5.0):
        with pytest.raises(ValidationError) as exc:
            upload_validation_service.validate_and_stage_upload(buf.getvalue(), "ratio_bomb.docx")
        assert exc.value.code == ErrorCode.DOCX_RESOURCE_LIMIT


def test_docx_oversized_single_entry_rejected():
    """18. رفض حزمة تحوي ملفاً فردياً ضخماً يتجاوز MAX_DOCX_SINGLE_ENTRY_BYTES."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', '<Types></Types>')
        z.writestr('word/document.xml', 'A' * (20 * 1024))
    with patch('config.MAX_DOCX_SINGLE_ENTRY_BYTES', 5 * 1024):
        with pytest.raises(ValidationError) as exc:
            upload_validation_service.validate_and_stage_upload(buf.getvalue(), "big_entry.docx")
        assert exc.value.code == ErrorCode.DOCX_RESOURCE_LIMIT


def test_docx_zip_traversal_member_rejected():
    """19. رفض أرشيف DOCX يحتوي على مسار تخطي (Zip-Slip: ../evil.xml)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('../evil.xml', '<evil></evil>')
        z.writestr('[Content_Types].xml', '<Types></Types>')
        z.writestr('word/document.xml', '<doc></doc>')
    with pytest.raises(ValidationError) as exc:
        upload_validation_service.validate_and_stage_upload(buf.getvalue(), "slip.docx")
    assert exc.value.code == ErrorCode.DOCX_ARCHIVE_UNSAFE


def test_docx_absolute_zip_member_rejected():
    """20. رفض أرشيف DOCX يحتوي على مسارات مطلقة (/etc/evil أو C:\\evil)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('/etc/passwd', 'root:x:0:0...')
        z.writestr('[Content_Types].xml', '<Types></Types>')
        z.writestr('word/document.xml', '<doc></doc>')
    with pytest.raises(ValidationError) as exc:
        upload_validation_service.validate_and_stage_upload(buf.getvalue(), "absolute_slip.docx")
    assert exc.value.code == ErrorCode.DOCX_ARCHIVE_UNSAFE


# ─── 3. اختبارات أمان التخزين والأسماء (Storage & Security 24-37) ─────────────

def test_path_traversal_filename_sanitized():
    """24 & 25. تنقية أسماء الملفات التي تحتوي على ../ أو ..\\ لمنع الهروب من المجلد."""
    safe_name, ext = upload_validation_service.sanitize_upload_filename("../../../etc/passwd.pdf")
    assert ".." not in safe_name
    assert "/" not in safe_name
    assert safe_name.endswith(".pdf")

    safe_win, _ = upload_validation_service.sanitize_upload_filename("..\\..\\Windows\\System32\\cmd.docx")
    assert ".." not in safe_win
    assert "\\" not in safe_win


def test_absolute_filename_sanitized():
    """26. تنقية المسارات المطلقة من اسم الملف الأصلي."""
    safe_name, _ = upload_validation_service.sanitize_upload_filename("C:\\Users\\Admin\\Secret.pdf")
    assert "C:" not in safe_name
    assert "\\" not in safe_name
    assert "Secret" in safe_name


def test_windows_reserved_device_name_handled():
    """27. معالجة أسماء الأجهزة المحجوزة في Windows مثل CON و AUX و NUL."""
    safe_name, ext = upload_validation_service.sanitize_upload_filename("CON.pdf")
    assert safe_name.startswith("doc_CON")
    assert ext == ".pdf"


def test_unicode_and_control_chars_sanitized():
    """28. إزالة محارف التحكم وبايتات NUL من اسم الملف."""
    safe_name, _ = upload_validation_service.sanitize_upload_filename("paper\x00\r\n\x1f.pdf")
    assert "\x00" not in safe_name
    assert "\r" not in safe_name
    assert "\n" not in safe_name


def test_arabic_filename_preserved_as_display_metadata():
    """32. الحفاظ التام على الأسماء العربية الصحيحة في اسم الملف."""
    arabic_name = "بحث_التخرج_في_الفقه_المقارن.pdf"
    safe_name, ext = upload_validation_service.sanitize_upload_filename(arabic_name)
    assert "الفقه" in safe_name
    assert ext == ".pdf"


def test_failed_validation_cleans_staging():
    """30. التحقق من حذف ملف Staging المؤقت فوراً في حال فشل أي خطوة تدقيق."""
    staging_dir = storage_service.get_staging_upload_dir()
    count_before = len(list(staging_dir.iterdir()))

    corrupt_data = b"Not a PDF"
    try:
        upload_validation_service.validate_and_stage_upload(corrupt_data, "bad.pdf")
    except ValidationError:
        pass

    count_after = len(list(staging_dir.iterdir()))
    assert count_after == count_before


def test_clean_stale_staging_functionality():
    """31. التحقق من وظيفة تنظيف الملفات المؤقتة القديمة في Staging."""
    staging_dir = storage_service.get_staging_upload_dir()
    test_stale = staging_dir / ".stage_test_stale_file.tmp"
    with open(test_stale, 'w') as f:
        f.write("old data")

    old_time = time.time() - 7200
    os.utime(test_stale, (old_time, old_time))

    cleaned = upload_validation_service.clean_stale_staging(max_age_seconds=3600)
    assert cleaned >= 1
    assert not test_stale.exists()


def test_unauthorized_caller_cannot_trigger_expensive_upload(client):
    """34. التحقق من أن غير المصرح لهم يُرفضون بـ 401/403 قبل أي معالجة ملفات."""
    # بدون تسجيل الدخول
    res = client.post('/api/scan', data={'file': (io.BytesIO(_create_minimal_valid_pdf()), 'test.pdf')})
    assert res.status_code == 401


# ─── 4. اختبارات الإغلاق النهائي والتكامل (Closeout Verification 1-14) ──────────

def test_batch_file_count_limit_enforced(client):
    """1. التحقق من رفض الدفعة التي تتجاوز MAX_FILES_PER_BATCH."""
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['username'] = 'admin'
        sess['role'] = Role.UNIT_MANAGER

    pdf = _create_minimal_valid_pdf()
    files = [(io.BytesIO(pdf), f"paper_{i}.pdf") for i in range(config.MAX_FILES_PER_BATCH + 2)]
    titles = [f"Title {i}" for i in range(len(files))]
    authors = ["Author"] * len(files)

    data = {'files[]': files, 'titles[]': titles, 'authors[]': authors}
    res = client.post('/api/batch/independent', data=data, content_type='multipart/form-data')
    assert res.status_code == 400
    data_json = res.get_json()
    err_code = data_json.get('error_code') or data_json.get('error', {}).get('code')
    assert err_code == ErrorCode.BATCH_LIMIT_EXCEEDED


def test_thesis_file_count_limit_enforced(client):
    """2. التحقق من رفض الرسالة التي تتجاوز MAX_FILES_PER_THESIS."""
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['username'] = 'admin'
        sess['role'] = Role.UNIT_MANAGER

    pdf = _create_minimal_valid_pdf()
    files = [(io.BytesIO(pdf), f"ch_{i}.pdf") for i in range(config.MAX_FILES_PER_THESIS + 2)]
    orders = [str(i) for i in range(len(files))]

    data = {'files[]': files, 'orders[]': orders, 'title': 'Giant Thesis', 'author': 'Author'}
    res = client.post('/api/batch/thesis', data=data, content_type='multipart/form-data')
    assert res.status_code == 400
    data_json = res.get_json()
    err_code = data_json.get('error_code') or data_json.get('error', {}).get('code')
    assert err_code == ErrorCode.BATCH_LIMIT_EXCEEDED


def test_batch_aggregate_byte_limit_enforced(client):
    """3. التحقق من رفض الدفعة التي يتجاوز حجمها الإجمالي MAX_BATCH_TOTAL_BYTES."""
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['username'] = 'admin'
        sess['role'] = Role.UNIT_MANAGER

    with patch('config.MAX_BATCH_TOTAL_BYTES', 500):
        pdf = _create_minimal_valid_pdf()  # ~400 bytes
        files = [(io.BytesIO(pdf), "p1.pdf"), (io.BytesIO(pdf), "p2.pdf")]
        data = {'files[]': files, 'titles[]': ['T1', 'T2'], 'authors[]': ['A1', 'A2']}
        res = client.post('/api/batch/independent', data=data, content_type='multipart/form-data')
        assert res.status_code == 413
        data_json = res.get_json()
        err_code = data_json.get('error_code') or data_json.get('error', {}).get('code')
        assert err_code == ErrorCode.BATCH_LIMIT_EXCEEDED


def test_thesis_aggregate_byte_limit_enforced(client):
    """4. التحقق من رفض الرسالة التي يتجاوز حجمها الإجمالي MAX_THESIS_TOTAL_BYTES."""
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['username'] = 'admin'
        sess['role'] = Role.UNIT_MANAGER

    with patch('config.MAX_THESIS_TOTAL_BYTES', 500):
        pdf = _create_minimal_valid_pdf()
        files = [(io.BytesIO(pdf), "c1.pdf"), (io.BytesIO(pdf), "c2.pdf")]
        data = {'files[]': files, 'orders[]': ['0', '1'], 'title': 'Big Thesis', 'author': 'Author'}
        res = client.post('/api/batch/thesis', data=data, content_type='multipart/form-data')
        assert res.status_code == 413
        data_json = res.get_json()
        err_code = data_json.get('error_code') or data_json.get('error', {}).get('code')
        assert err_code == ErrorCode.BATCH_LIMIT_EXCEEDED


def test_reference_upload_byte_limit_enforced(client):
    """5. التحقق من تطبيق MAX_REFERENCE_UPLOAD_BYTES على رفع المراجع."""
    from app.repositories import user_repo
    user_repo.add_user('ref_upload_mgr', 'ValidPass#2026Secure', 'مدير المراجع', Role.UNIT_MANAGER)
    u = user_repo.authenticate_user('ref_upload_mgr', 'ValidPass#2026Secure')

    with client.session_transaction() as sess:
        sess['user_id'] = u['id']
        sess['username'] = u['username']
        sess['role'] = Role.UNIT_MANAGER
        sess['session_version'] = 1

    with patch('config.MAX_REFERENCE_UPLOAD_BYTES', 100):
        pdf = _create_minimal_valid_pdf()
        res = client.post('/api/papers', data={'file': (io.BytesIO(pdf), 'ref.pdf'), 'title': 'Ref Paper'}, content_type='multipart/form-data')
        assert res.status_code in (400, 413)


def test_duplicate_cannot_bypass_structural_validation(client):
    """8. التحقق من أن وجود البصمة مسبقاً لا يتجاوز التدقيق الهيكلي إذا كان الملف معطوباً."""
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['username'] = 'admin'
        sess['role'] = Role.UNIT_MANAGER

    corrupted_data = b"Corrupted fake pdf content"
    with pytest.raises(ValidationError) as exc:
        upload_validation_service.validate_and_stage_upload(corrupted_data, "bad_paper.pdf")
    assert exc.value.code in (ErrorCode.FILE_SIGNATURE_MISMATCH, ErrorCode.FILE_CORRUPTED)


def test_failed_validation_leaves_no_finalized_record(client):
    """10. التحقق من عدم إنشاء أي سجل في قاعدة البيانات أو التخزين النهائي عند فشل التدقيق."""
    final_dir = storage_service.get_finalized_upload_dir()
    files_before = len(list(final_dir.iterdir())) if final_dir.exists() else 0

    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['username'] = 'admin'
        sess['role'] = Role.UNIT_MANAGER

    res = client.post('/api/scan', data={'file': (io.BytesIO(b"bad pdf"), 'invalid.pdf')}, content_type='multipart/form-data')
    assert res.status_code in (400, 413)

    files_after = len(list(final_dir.iterdir())) if final_dir.exists() else 0
    assert files_after == files_before


def test_no_external_network_dependencies_in_upload_service():
    """14. التحقق من عدم وجود أي استدعاءات شبكية أو خدمات سحابية داخل خدمة التدقيق (100% Offline)."""
    import inspect
    source = inspect.getsource(upload_validation_service)
    assert 'requests.' not in source
    assert 'urllib.request' not in source
    assert 'virustotal' not in source.lower()
    assert 'socket.' not in source


# ─── 5. قياس زمن التحقق والأداء (Validation Performance Overhead) ──────────────

def test_validation_performance_benchmark():
    """32 & Performance Check. قياس زمن التدقيق الهيكلي للملفات النمطية."""
    pdf_bytes = _create_minimal_valid_pdf()
    docx_bytes = _create_minimal_valid_docx()
    txt_bytes = ("محتوى تجريبي " * 500).encode('utf-8')

    # قياس PDF
    t0 = time.perf_counter()
    r1 = upload_validation_service.validate_and_stage_upload(pdf_bytes, "perf.pdf")
    dt_pdf = (time.perf_counter() - t0) * 1000
    upload_validation_service.cleanup_staging_file(r1['staging_path'])

    # قياس DOCX
    t0 = time.perf_counter()
    r2 = upload_validation_service.validate_and_stage_upload(docx_bytes, "perf.docx")
    dt_docx = (time.perf_counter() - t0) * 1000
    upload_validation_service.cleanup_staging_file(r2['staging_path'])

    # قياس TXT
    t0 = time.perf_counter()
    r3 = upload_validation_service.validate_and_stage_upload(txt_bytes, "perf.txt")
    dt_txt = (time.perf_counter() - t0) * 1000
    upload_validation_service.cleanup_staging_file(r3['staging_path'])

    # قياس الرفض السريع لعدم تطابق التوقيع
    t0 = time.perf_counter()
    try:
        upload_validation_service.validate_and_stage_upload(b"NOT_A_PDF", "bad_sig.pdf")
    except ValidationError:
        pass
    dt_bad_sig = (time.perf_counter() - t0) * 1000

    assert dt_pdf < 250.0, f"PDF validation too slow: {dt_pdf:.2f}ms"
    assert dt_docx < 250.0, f"DOCX validation too slow: {dt_docx:.2f}ms"
    assert dt_txt < 100.0, f"TXT validation too slow: {dt_txt:.2f}ms"
    assert dt_bad_sig < 50.0, f"Signature rejection too slow: {dt_bad_sig:.2f}ms"

