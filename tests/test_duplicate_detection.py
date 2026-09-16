# -*- coding: utf-8 -*-
"""
حزمة اختبارات كشف التكرار وسلامة الملفات (Duplicate Detection & File Integrity Tests — Phase 7):
1. التحقق من أن تطابق البايتات مع نفس الاسم يُكتشف كتكرار دقيق.
2. التحقق من أن تطابق البايتات مع أسماء مختلفة يُكتشف كتكرار دقيق (الاعتماد على SHA-256 حصراً).
3. التحقق من أن تشابه اسم الملف مع اختلاف البايتات لا يُعتبر تكراراً دقيقاً.
4. التحقق من أن الرفع الفردي للملف المكرر لا يبدأ فحصاً جديداً تلقائياً.
5. التحقق من أن إعادة الفحص المصرح بها (Authorized Rescan) تعمل بنجاح.
6. التحقق من كشف التكرار الداخلي والخارجي في الدفعات مع عدم إلغاء باقي عناصر الدفعة.
7. التحقق من استبعاد الفصول المكررة في الرسائل متعددة الملفات من الدمج والتحليل المزدوج.
8. التحقق من حظر تكرار المراجع في الفهرس المرجعي وعدم رفع إصدار الفهرس دون تغيير فعلي.
9. التحقق من حماية الخصوصية ومنع تسريب بيانات الأبحاث السابقة للمستخدمين غير المصرح لهم.
10. التحقق من توليد أسماء التخزين الآمنة وحصانتها ضد هجمات Path Traversal.
11. التحقق من دالة فحص السلامة (Integrity Check) وتوثيق أحداث التدقيق بدقة.
12. التحقق من أن تغيير دور المستخدم ينعكس فورياً على الجلسات المفتوحة.
"""

import io
import json
import uuid
import hashlib
import pytest
from flask import session as flask_session
from app import create_app
from app.repositories import user_repo, report_repo, batch_repo, document_repo, base_repo
from app.models.schema import User, Document
from app.models.research_schema import Research, ResearchFile
from app.models.audit_schema import AuditLog
from app.services import integrity_service, audit_service, snapshot_service, paper_service
from app.security.permissions import Permission, Role


@pytest.fixture
def app_instance():
    app = create_app()
    app.config['TESTING'] = True
    app.config['STRICT_AUTH'] = True
    app.config['SECRET_KEY'] = 'test-dup-secret-key-2026'
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


def test_user_role_change_takes_effect_immediately(client, app_instance):
    """تعديل دور المستخدم يبطل الجلسة القديمة عبر session_version لفرض المصادقة بالدور الجديد."""
    uid, uname, _ = _setup_test_user('session_role_test_user', Role.DATA_ENTRY)

    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = uname
        sess['role'] = Role.DATA_ENTRY
        sess['session_version'] = 1

    # مدخل البيانات محظور من الإعدادات -> 403
    res_before = client.get('/api/settings')
    assert res_before.status_code == 403

    # ترقية المستخدم في قاعدة البيانات إلى مدير نظام تزيد session_version
    user_repo.update_user_role(uid, Role.SYSTEM_ADMIN)

    # الجلسة القديمة تبطل فوراً ولا يمكن استغلالها
    res_stale = client.get('/api/settings')
    assert res_stale.status_code == 401

    # عند الدخول بالجلسة المحدثة يتمتع بالصلاحيات الجديدة فوراً -> 200 OK
    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = uname
        sess['role'] = Role.SYSTEM_ADMIN
        sess['session_version'] = 2

    res_after = client.get('/api/settings')
    assert res_after.status_code == 200


def _make_valid_test_pdf(text: str = "Sample") -> bytes:
    tag_b = text.encode('ascii', errors='ignore')
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>\nendobj\n"
        b"4 0 obj\n<< /Length 44 >>\nstream\nBT /F1 12 Tf 100 700 Td (" + tag_b + b") Tj ET\nendstream\nendobj\n"
        b"xref\n0 5\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000214 00000 n \n"
        b"trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n308\n%%EOF"
    )


def test_exact_same_bytes_and_same_filename_detected(client, app_instance):
    """تطابق البايتات ونفس الاسم يُكتشف كتكرار دقيق ولا يطلق فحصاً جديداً."""
    uid, uname, urole = _setup_test_user('dup_tester_1', Role.REVIEWER)
    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = uname
        sess['role'] = urole

    import uuid
    uniq = uuid.uuid4().hex[:8]
    content = _make_valid_test_pdf(f"exact_dup_{uniq}")
    # الرفع الأول
    res1 = client.post(
        '/api/analyze_async',
        data={'file': (io.BytesIO(content), 'research_doc.pdf'), 'title': f'بحث أول {uniq}'},
        content_type='multipart/form-data'
    )
    assert res1.status_code == 200
    assert 'task_id' in res1.get_json()

    # محاكاة تسجيل البحث السابق بالبصمة
    hash_val, _ = integrity_service.compute_stream_sha256(io.BytesIO(content))
    r_id = batch_repo.create_research(title=f'بحث أول {uniq}', author='د. تجريبي', created_by=uname)
    batch_repo.add_research_file(
        research_id=r_id,
        original_filename='research_doc.pdf',
        stored_filename='stored_123.pdf',
        file_path='',
        file_type='pdf',
        file_size_bytes=len(content),
        file_order=0,
        file_hash=hash_val,
        storage_status='registry_only'
    )

    # الرفع الثاني بنفس البايتات والاسم
    res2 = client.post(
        '/api/analyze_async',
        data={'file': (io.BytesIO(content), 'research_doc.pdf'), 'title': 'بحث مكرر'},
        content_type='multipart/form-data'
    )
    assert res2.status_code == 200
    data2 = res2.get_json()
    assert data2.get('duplicate') is True
    assert data2.get('scope') == 'existing_research'
    assert 'task_id' not in data2


def test_same_bytes_different_filename_detected_as_duplicate(client, app_instance):
    """تطابق البايتات مع اسم ملف مختلف تماماً يُكتشف كتكرار دقيق اعتماداً على SHA-256."""
    uid, uname, urole = _setup_test_user('dup_tester_2', Role.REVIEWER)
    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = uname
        sess['role'] = urole

    content = _make_valid_test_pdf("unique_renamed_998877")
    hash_val, _ = integrity_service.compute_stream_sha256(io.BytesIO(content))

    r_id = batch_repo.create_research(title='البحث الأصلي', author='الباحث الأول', created_by=uname)
    batch_repo.add_research_file(
        research_id=r_id,
        original_filename='original_paper.pdf',
        stored_filename='stored_original.pdf',
        file_path='',
        file_type='pdf',
        file_size_bytes=len(content),
        file_order=0,
        file_hash=hash_val,
        storage_status='registry_only'
    )

    # رفع نفس البايتات باسم مختلف كلياً
    res = client.post(
        '/api/analyze_async',
        data={'file': (io.BytesIO(content), 'completely_different_name.pdf'), 'title': 'نسخة معادة التسمية'},
        content_type='multipart/form-data'
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data.get('duplicate') is True
    assert data.get('scope') == 'existing_research'


def test_same_filename_different_bytes_not_detected_as_duplicate(client, app_instance):
    """نفس اسم الملف مع اختلاف المحتوى والبايتات لا يُعتبر تكراراً ويُفحص كبحث جديد."""
    uid, uname, urole = _setup_test_user('dup_tester_3', Role.REVIEWER)
    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = uname
        sess['role'] = urole

    content1 = _make_valid_test_pdf("version_1_alpha")
    content2 = _make_valid_test_pdf("version_2_beta")

    hash_val1, _ = integrity_service.compute_stream_sha256(io.BytesIO(content1))
    r_id = batch_repo.create_research(title='الإصدار الأول', author='الباحث', created_by=uname)
    batch_repo.add_research_file(
        research_id=r_id,
        original_filename='paper.pdf',
        stored_filename='stored_v1.pdf',
        file_path='',
        file_type='pdf',
        file_size_bytes=len(content1),
        file_order=0,
        file_hash=hash_val1,
        storage_status='registry_only'
    )

    # رفع ملف بنفس الاسم 'paper.pdf' ولكن ببايتات مختلفة
    res = client.post(
        '/api/analyze_async',
        data={'file': (io.BytesIO(content2), 'paper.pdf'), 'title': 'الإصدار الثاني المعدل'},
        content_type='multipart/form-data'
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data.get('duplicate') is not True
    assert 'task_id' in data


def test_authorized_rescan_proceeds_with_new_scan(client, app_instance):
    """إعادة الفحص المصرّح بها (force_rescan / allow_rescan) تتجاوز حظر التكرار وتنشئ فحصاً جديداً."""
    uid, uname, urole = _setup_test_user('rescan_actor', Role.REVIEWER)
    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = uname
        sess['role'] = urole

    content = _make_valid_test_pdf("rescan_xyz")
    hash_val, _ = integrity_service.compute_stream_sha256(io.BytesIO(content))

    r_id = batch_repo.create_research(title='بحث سابق', author='باحث', created_by=uname)
    batch_repo.add_research_file(
        research_id=r_id,
        original_filename='doc.pdf',
        stored_filename='stored_doc.pdf',
        file_path='',
        file_type='pdf',
        file_size_bytes=len(content),
        file_order=0,
        file_hash=hash_val,
        storage_status='registry_only'
    )

    # طلب إعادة الفحص صراحة
    res = client.post(
        '/api/analyze_async',
        data={
            'file': (io.BytesIO(content), 'doc.pdf'),
            'title': 'إعادة فحص بحث',
            'allow_rescan': 'true'
        },
        content_type='multipart/form-data'
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data.get('duplicate') is not True
    assert 'task_id' in data

    with base_repo.get_session() as session:
        ev = (
            session.query(AuditLog)
            .filter(AuditLog.action == 'research.duplicate_rescan_requested')
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert ev is not None


def test_batch_internal_duplicate_detected(client, app_instance):
    """كشف التكرار الداخلي بين ملفات نفس الدفعة دون إلغاء باقي ملفات الدفعة."""
    from unittest.mock import patch
    uid, uname, urole = _setup_test_user('batch_dup_tester', Role.REVIEWER)
    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = uname
        sess['role'] = urole

    content_a = _make_valid_test_pdf("batch_file_a")
    content_b = _make_valid_test_pdf("batch_file_b")
    content_a_copy = content_a # مطابق لـ A

    data = {
        'files[]': [
            (io.BytesIO(content_a), "paper_a.pdf"),
            (io.BytesIO(content_b), "paper_b.pdf"),
            (io.BytesIO(content_a_copy), "paper_a_copy.pdf")
        ],
        'titles[]': ['بحث أ', 'بحث ب', 'نسخة من بحث أ'],
        'authors[]': ['باحث 1', 'باحث 2', 'باحث 1']
    }

    with patch('app.routes.batch_routes.start_batch_scan', return_value='mock-batch-123') as mock_scan:
        res = client.post('/api/batch/independent', data=data, content_type='multipart/form-data')
    assert res.status_code == 202
    resp_data = res.get_json()
    assert 'duplicates_warning' in resp_data
    assert 'paper_a_copy.pdf' in resp_data['duplicates_warning']


def test_thesis_duplicate_chapter_excluded_from_scan(client, app_instance):
    """استبعاد الفصل المكرر داخل نفس الرسالة من الدمج والتحليل المزدوج."""
    from unittest.mock import patch
    uid, uname, urole = _setup_test_user('thesis_dup_tester', Role.REVIEWER)
    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = uname
        sess['role'] = urole

    ch1 = _make_valid_test_pdf("thesis_chapter_1")
    ch2 = _make_valid_test_pdf("thesis_chapter_2")
    ch1_dup = ch1 # مكرر

    data = {
        'files[]': [
            (io.BytesIO(ch1), "chapter1.pdf"),
            (io.BytesIO(ch2), "chapter2.pdf"),
            (io.BytesIO(ch1_dup), "chapter1_accidental_copy.pdf")
        ],
        'orders[]': ['0', '1', '2'],
        'title': 'رسالة بأبواب متكررة',
        'author': 'الباحث الأكاديمي'
    }

    with patch('app.routes.batch_routes.start_thesis_scan', return_value='mock-thesis-123') as mock_scan:
        res = client.post('/api/batch/thesis', data=data, content_type='multipart/form-data')
    assert res.status_code == 202
    resp_data = res.get_json()
    assert resp_data['file_count'] == 2 # تم إدخال فصلين فقط واستبعاد الثالث المكرر
    assert 'duplicates_warning' in resp_data


def test_reference_database_exact_duplicate_blocked(client, app_instance):
    """حظر تكرار إضافة نفس البحث في قاعدة المراجع المعتمدة."""
    uid, uname, urole = _setup_test_user('ref_dup_admin', Role.UNIT_MANAGER)
    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = uname
        sess['role'] = urole

    import uuid
    uniq = uuid.uuid4().hex[:8]
    content = f"نص بحث مرجعي فريد لاختبار منع التكرار في الفهرس المرجعي 2026 {uniq}."
    res1 = paper_service.import_reference_paper(title=f'مرجع فريد {uniq}', raw_text=content)
    assert res1['success'] is True

    # محاولة إضافة نفس المحتوى كمرجع ثانٍ
    res2 = paper_service.import_reference_paper(title=f'مرجع مكرر بنفس النص {uniq}', raw_text=content)
    assert res2['success'] is False
    assert res2['is_duplicate'] is True


def test_unauthorized_user_receives_generic_duplicate_message(client, app_instance):
    """المستخدم غير المصرح له لا يتلقى أي تفاصيل حساسة (اسم الباحث، النسبة، التقرير) عن البحث السابق."""
    # إنشاء مستخدم بدون صلاحية الاطلاع على أبحاث الآخرين
    restricted_id, restricted_name, _ = _setup_test_user('restricted_entry_user', Role.DATA_ENTRY)

    content = b"HIGHLY_CONFIDENTIAL_PREVIOUS_RESEARCH_BYTES"
    hash_val, _ = integrity_service.compute_stream_sha256(io.BytesIO(content))

    # تسجيل بحث سابق بواسطة باحث آخر
    r_id = batch_repo.create_research(
        title='بحث سري للغاية لوزارة التعليم',
        author='د. أحمد عبد الرحمن السرّي',
        created_by='another_unit'
    )
    batch_repo.add_research_file(
        research_id=r_id,
        original_filename='confidential.pdf',
        stored_filename='confidential_stored.pdf',
        file_path='',
        file_type='pdf',
        file_size_bytes=len(content),
        file_order=0,
        file_hash=hash_val,
        storage_status='registry_only'
    )

    dup_info = integrity_service.check_file_duplicate_in_repository(
        hash_val,
        current_user={'id': restricted_id, 'username': restricted_name, 'role': Role.DATA_ENTRY}
    )

    assert dup_info is not None
    assert dup_info['duplicate'] is True
    assert dup_info['can_view_existing'] is False
    assert 'existing_title' not in dup_info
    assert 'existing_author' not in dup_info
    assert 'existing_similarity_pct' not in dup_info


def test_safe_storage_filename_neutralizes_path_traversal():
    """دالة توليد اسم التخزين تحيد هجمات مسارات الملفات والحركات غير الآمنة."""
    dangerous_names = [
        "../../../../etc/passwd",
        "..\\..\\Windows\\System32\\calc.exe",
        "CON.pdf",
        "NUL.txt",
        "research\x00_hidden.pdf",
        "C:\\Users\\Administrator\\Desktop\\file.pdf"
    ]

    for d_name in dangerous_names:
        safe_name = integrity_service.get_safe_storage_filename(d_name)
        assert ".." not in safe_name
        assert "/" not in safe_name
        assert "\\" not in safe_name
        assert "\x00" not in safe_name
        assert not safe_name.upper().startswith("CON.")
        assert not safe_name.upper().startswith("NUL.")


def test_file_integrity_verification_detects_corrupted_bytes(tmp_path):
    """دالة فحص السلامة تكتشف أي تعديل في بايتات الملف المخزن وتوثق الحدث."""
    test_file = tmp_path / "integrity_test.pdf"
    test_file.write_bytes(b"ORIGINAL_CLEAN_BYTES_12345")

    expected_hash, _ = integrity_service.compute_stream_sha256(test_file)

    # 1. فحص ملف سليم
    is_valid, comp_hash, _ = integrity_service.verify_stored_file_integrity(str(test_file), expected_hash)
    assert is_valid is True
    assert comp_hash == expected_hash

    # 2. تعديل بايت واحد في الملف
    test_file.write_bytes(b"CORRUPTED_BYTES_ALTERED_54321")
    is_valid_corrupt, comp_hash_corrupt, _ = integrity_service.verify_stored_file_integrity(str(test_file), expected_hash)
    assert is_valid_corrupt is False
    assert comp_hash_corrupt != expected_hash


def test_duplicate_reference_does_not_increment_corpus_version(client, app_instance):
    """محاولة إضافة مرجع مكرر لا ترفع إصدار الفهرس المرجعي ولا تنشئ سجلاً جديداً."""
    uid, uname, urole = _setup_test_user('corpus_ver_tester', Role.UNIT_MANAGER)
    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = uname
        sess['role'] = urole

    uniq = uuid.uuid4().hex[:8]
    content = f"محتوى مرجع لفحص عدم تغيير رقم الإصدار {uniq}"

    v_before, fp_before = snapshot_service.get_current_reference_corpus_info()
    res1 = paper_service.import_reference_paper(title=f'مرجع 1 {uniq}', raw_text=content)
    assert res1['success'] is True

    v_after1, fp_after1 = snapshot_service.get_current_reference_corpus_info()

    # محاولة إضافة نفس المحتوى مجدداً (تكرار)
    res2 = paper_service.import_reference_paper(title=f'مرجع مكرر {uniq}', raw_text=content)
    assert res2['success'] is False

    v_after2, fp_after2 = snapshot_service.get_current_reference_corpus_info()

    # يجب ألا يتغير إصدار الفهرس وبصمته بين بعد الإضافة الأولى وبعد محاولة التكرار
    assert v_after1 == v_after2
    assert fp_after1 == fp_after2


def test_duplicate_detection_produces_audit_event(client, app_instance):
    """اكتشاف التكرار ينتج حدث تدقيق research.duplicate_detected متضمناً البصمة والرقم المرجعي."""
    uid, uname, urole = _setup_test_user('audit_dup_tester', Role.REVIEWER)
    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = uname
        sess['role'] = urole

    uniq = uuid.uuid4().hex[:8]
    content = _make_valid_test_pdf(f"audit_dup_{uniq}")
    hash_val, _ = integrity_service.compute_stream_sha256(io.BytesIO(content))

    r_id = batch_repo.create_research(title=f'بحث سابق للتدقيق {uniq}', author='باحث', created_by=uname)
    batch_repo.add_research_file(
        research_id=r_id,
        original_filename='doc.pdf',
        stored_filename='stored_doc.pdf',
        file_path='',
        file_type='pdf',
        file_size_bytes=len(content),
        file_order=0,
        file_hash=hash_val,
        storage_status='registry_only'
    )

    res = client.post(
        '/api/analyze_async',
        data={'file': (io.BytesIO(content), 'doc.pdf'), 'title': 'محاولة فحص مكررة'},
        content_type='multipart/form-data'
    )
    assert res.status_code == 200
    assert res.get_json()['duplicate'] is True

    with base_repo.get_session() as session:
        evs = (
            session.query(AuditLog)
            .filter(AuditLog.action == 'research.duplicate_detected')
            .order_by(AuditLog.id.desc())
            .all()
        )
        assert len(evs) > 0
        latest_meta = evs[0].metadata_json or ''
        assert 'hash_prefix' in latest_meta or 'filename' in latest_meta


def test_stream_sha256_handles_chunks_correctly(tmp_path):
    """دالة القراءة المتدفقة تحسب نفس الهاش الدقيق لملف كبير دون تحميله دفعة واحدة."""
    large_file = tmp_path / "large_sample.dat"
    # إنشاء ملف بحجم 256KB
    chunk = b"0123456789ABCDEF" * 1024 # 16KB
    with open(large_file, 'wb') as f:
        for _ in range(16):
            f.write(chunk)

    expected_hash = hashlib.sha256(large_file.read_bytes()).hexdigest()
    computed_hash, size_bytes = integrity_service.compute_stream_sha256(large_file, chunk_size=8192)

    assert computed_hash == expected_hash
    assert size_bytes == 256 * 1024


def test_authorized_user_receives_previous_report_details(client, app_instance):
    """المستخدم المصرح له يتلقى الرقم المرجعي ومعرف التقرير وتاريخ الفحص ونسبة الاستلال."""
    uid, uname, urole = _setup_test_user('senior_dup_viewer', Role.SENIOR_REVIEWER)
    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = uname
        sess['role'] = urole

    uniq = uuid.uuid4().hex[:8]
    content = _make_valid_test_pdf(f"auth_disclosure_{uniq}")
    hash_val, _ = integrity_service.compute_stream_sha256(io.BytesIO(content))

    rep_id = f"rep_{uniq}"
    report_repo.save_report(
        report_id=rep_id,
        title=f'بحث سابق متكامل {uniq}',
        overall_pct=18.5,
        copied_pct=12.0,
        para_pct=6.5,
        report_dict={'title': f'بحث سابق متكامل {uniq}', 'overall_pct': 18.5},
        author='د. حسام محمود'
    )

    r_id = batch_repo.create_research(
        title=f'بحث سابق متكامل {uniq}',
        author='د. حسام محمود',
        created_by='unit_a'
    )
    batch_repo.update_research_scan(r_id, 'job_123', rep_id)
    batch_repo.add_research_file(
        research_id=r_id,
        original_filename='paper.pdf',
        stored_filename='stored_paper.pdf',
        file_path='',
        file_type='pdf',
        file_size_bytes=len(content),
        file_order=0,
        file_hash=hash_val,
        storage_status='registry_only'
    )

    dup_info = integrity_service.check_file_duplicate_in_repository(
        hash_val,
        current_user={'id': uid, 'username': uname, 'role': Role.SENIOR_REVIEWER}
    )

    assert dup_info is not None
    assert dup_info['duplicate'] is True
    assert dup_info['can_view_existing'] is True
    assert dup_info['existing_report_id'] == rep_id
    assert dup_info['existing_similarity_pct'] == 18.5
    assert dup_info['existing_author'] == 'د. حسام محمود'


def test_unauthorized_rescan_fails_without_scan_permission(client, app_instance):
    """محاولة طلب الفحص من قبل مستخدم غير ممتلك لصلاحية scan.start تُرفض برمز 403."""
    uid, uname, _ = _setup_test_user('guest_no_scan', 'guest')
    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = uname
        sess['role'] = 'guest'

    content = _make_valid_test_pdf("TEST_DATA_FOR_PERMISSION_CHECK")
    res = client.post(
        '/api/analyze_async',
        data={'file': (io.BytesIO(content), 'doc.pdf'), 'title': 'محاولة فحص', 'allow_rescan': 'true'},
        content_type='multipart/form-data'
    )

    assert res.status_code == 403



def test_sha256_stability_across_file_renames(tmp_path):
    """بصمة SHA-256 تظل ثابتة تماماً مهما تغير اسم الملف أو مساره."""
    content = b"RELIABLE_CONTENT_FOR_HASH_STABILITY_123"
    file1 = tmp_path / "first_name.pdf"
    file2 = tmp_path / "second_name_completely_different.pdf"
    file1.write_bytes(content)
    file2.write_bytes(content)

    h1, s1 = integrity_service.compute_stream_sha256(file1)
    h2, s2 = integrity_service.compute_stream_sha256(file2)

    assert h1 == h2
    assert s1 == s2 == len(content)


def test_multiple_distinct_files_get_distinct_hashes():
    """كل ملف متميز بمحتواه يُنتج بصمة SHA-256 فريدة ومختلفة كلياً."""
    c1 = b"DISTINCT_CONTENT_AAA"
    c2 = b"DISTINCT_CONTENT_BBB"
    c3 = b"DISTINCT_CONTENT_CCC"

    h1, _ = integrity_service.compute_stream_sha256(io.BytesIO(c1))
    h2, _ = integrity_service.compute_stream_sha256(io.BytesIO(c2))
    h3, _ = integrity_service.compute_stream_sha256(io.BytesIO(c3))

    assert len({h1, h2, h3}) == 3


def test_safe_filename_handles_arabic_names_cleanly():
    """توليد اسم التخزين الآمن يحافظ على قابلية القراءة والامتداد العربي السليم."""
    orig = "رسالة الماجستير_الباب الأول_نهائي.pdf"
    safe = integrity_service.get_safe_storage_filename(orig)

    assert safe.endswith(".pdf")
    assert ".." not in safe
    assert "/" not in safe
    assert "\\" not in safe


def test_empty_file_hashing_handled_safely():
    """حساب الهاش لملف فارغ يُعيد البصمة القياسية للملف الصفري دون أخطاء."""
    empty_content = b""
    h, size = integrity_service.compute_stream_sha256(io.BytesIO(empty_content))

    expected_empty_hash = hashlib.sha256(b"").hexdigest()
    assert h == expected_empty_hash
    assert size == 0


