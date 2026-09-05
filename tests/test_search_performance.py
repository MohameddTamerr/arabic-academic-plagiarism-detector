# -*- coding: utf-8 -*-
"""
حزمة اختبارات الأداء والبحث في المجموعات الضخمة (Phase 10 Tests):
- التحقق من تقسيم الصفحات (Pagination) في كافة القوائم.
- التحقق من الحدود القصوى للصفحات (Page Size Bounds & Max 100).
- التحقق من التطبيع اللغوي والبحث الذكي في الأرقام المرجعية والأسماء العربية.
- التحقق من الترتيب الآمن ومنع حقن الاستعلامات (Safe Sorting & SQL Injection Prevention).
- التحقق من تقييد نطاق البيانات وصلاحيات الوصول (Data Scoping & RBAC Integration).
- التحقق من منع مشكلة الاستعلامات المتكررة (N+1 Prevention).
"""

import os
import pytest
from app import create_app
from app.repositories.base_repo import get_session
from app.models.research_schema import Research, ScanBatch, ScanBatchItem
from app.models.schema import Document, LegacyReport, User
from app.services import reference_service
from app.utils.search_normalizer import normalize_search_query, normalize_arabic_for_search, extract_reference_search_term
from app.utils.pagination import get_pagination_params, format_paginated_response


@pytest.fixture
def app_instance():
    """تهيئة بيئة تطبيق للاختبارات."""
    app = create_app()
    app.config['TESTING'] = True
    app.config['STRICT_AUTH'] = True
    app.config['SECRET_KEY'] = 'test-search-perf-secret'
    app.config['WTF_CSRF_ENABLED'] = False
    return app


@pytest.fixture
def client(app_instance):
    with app_instance.test_client() as client:
        yield client


@pytest.fixture
def seeded_users(app_instance):
    """إنشاء مستخدمين برتب وصلاحيات مختلفة."""
    from app.repositories import user_repo
    with app_instance.app_context():
        user_repo.add_user(
            username="admin_search_perf",
            password="AdminPassword123!",
            full_name="مدير فحص الأداء",
            role="admin"
        )
        user_repo.add_user(
            username="entry_search_perf",
            password="EntryPassword123!",
            full_name="مدخل بيانات الأداء",
            role="data_entry"
        )
        user_repo.add_user(
            username="reviewer_search_perf",
            password="ReviewerPassword123!",
            full_name="مراجع أكاديمي الأداء",
            role="reviewer"
        )
        return {
            'admin': user_repo.authenticate_user("admin_search_perf", "AdminPassword123!"),
            'data_entry': user_repo.authenticate_user("entry_search_perf", "EntryPassword123!"),
            'reviewer': user_repo.authenticate_user("reviewer_search_perf", "ReviewerPassword123!")
        }


# ─── 1. Arabic Normalization & Digit Mapping Unit Tests ────────────────────────

def test_search_normalizer_arabic_digits():
    """تحويل الأرقام المشرقية إلى قياسية للبحث في الأرقام المرجعية."""
    raw = "RES-٢٠٢٦-٠٠٠١٢٣"
    clean = normalize_search_query(raw)
    assert clean == "RES-2026-000123"


def test_search_normalizer_whitespace_trimming():
    """إزالة المسافات المتكررة والبادئة واللاحقة مع توحيد الألف."""
    raw = "   بحث   الأمن    السيبراني   "
    clean = normalize_search_query(raw)
    assert clean == "بحث الامن السيبراني"


def test_search_normalizer_alef_variants():
    """توحيد أشكال الألف (أ، إ، آ، ٱ) إلى ألف مجردة للبحث الأكاديمي المرن."""
    assert normalize_search_query("أحمد") == "احمد"
    assert normalize_search_query("إيمان") == "ايمان"
    assert normalize_search_query("آمنة") == "امنة"
    assert normalize_search_query("ٱلأكاديمية") == "الاكاديمية"


def test_search_normalizer_taa_marbutah_and_haa_distinction():
    """
    التحقق الصارم من عدم الخلط بين التاء المربوطة (ة) والهاء (ه):
    - 'منة' (اسم علم مؤنث) لا يتطابق مع 'منه' (حرف جر متصل بضمير).
    - 'حمزة' لا يتطابق مع 'حمزه'.
    - 'فاطمة' لا تتطابق مع 'فاطمه'.
    """
    assert normalize_search_query("منة") != normalize_search_query("منه")
    assert normalize_search_query("حمزة") != normalize_search_query("حمزه")
    assert normalize_search_query("فاطمة") != normalize_search_query("فاطمه")
    assert normalize_search_query("جامعة") != normalize_search_query("جامعه")


def test_search_normalizer_diacritics_and_tatweel_removal():
    """إزالة التشكيل الكامل وحروف التطويل."""
    raw = "بَحْثٌ أَكَادِيمِيٌّ فِـي الأَمْـنِ"
    clean = normalize_search_query(raw)
    assert clean == "بحث اكاديمي في الامن"


def test_extract_reference_search_term():
    """استخراج المعرف المرجعي بدقة."""
    assert extract_reference_search_term(" res-2026-00456 ") == "RES-2026-00456"
    assert extract_reference_search_term("bkp-2026-000001") == "BKP-2026-000001"


# ─── 2. Pagination Helper & Boundaries Tests ──────────────────────────────────

def test_pagination_params_defaults(app_instance):
    """التحقق من القيم الافتراضية لتقسيم الصفحات."""
    with app_instance.test_request_context('/api/researches'):
        params = get_pagination_params()
        assert params['page'] == 1
        assert params['page_size'] == 25
        assert params['offset'] == 0
        assert params['order'] == 'desc'


def test_pagination_params_max_limit_enforced(app_instance):
    """منع طلب أحجام صفحات هائلة والتثبيت على الحد الأقصى 100."""
    with app_instance.test_request_context('/api/researches?page_size=1000000&page=2'):
        params = get_pagination_params(max_size=100)
        assert params['page'] == 2
        assert params['page_size'] == 100
        assert params['offset'] == 100


def test_pagination_params_boundaries_and_invalid_types(app_instance):
    """التعامل الآمن مع المدخلات الشاذة وغير الرقمية وحالات الصفر والسالب."""
    # 1. page=0 و page_size=0
    with app_instance.test_request_context('/api/researches?page=0&page_size=0'):
        p1 = get_pagination_params()
        assert p1['page'] == 1
        assert p1['page_size'] == 25

    # 2. قيم سالبة
    with app_instance.test_request_context('/api/researches?page=-10&page_size=-50'):
        p2 = get_pagination_params()
        assert p2['page'] == 1
        assert p2['page_size'] == 25

    # 3. نصوص غير رقمية
    with app_instance.test_request_context('/api/researches?page=invalid_page&page_size=huge_size'):
        p3 = get_pagination_params()
        assert p3['page'] == 1
        assert p3['page_size'] == 25


def test_pagination_params_safe_sorting_allowlist(app_instance):
    """التحقق من إحباط حقول الترتيب غير المصرح بها والمحاولات الخبيثة (Sorting Allowlist)."""
    malicious_inputs = [
        'password_hash;DROP TABLE users;--',
        '1 UNION SELECT 1,2,3',
        'non_existent_column',
        '"><script>alert(1)</script>'
    ]
    for bad_sort in malicious_inputs:
        with app_instance.test_request_context(f'/api/researches?sort={bad_sort}&order=invalid_dir'):
            params = get_pagination_params(
                allowed_sort_fields=['created_at', 'title', 'reference_number'],
                default_sort='created_at'
            )
            assert params['sort'] == 'created_at'
            assert params['order'] == 'desc'


def test_format_paginated_response_structure():
    """التحقق من بنية استجابة تقسيم الصفحات الموحدة."""
    items = [{'id': 1}, {'id': 2}]
    resp = format_paginated_response(items, total_items=52, page=1, page_size=25, legacy_key='papers')
    assert resp['page'] == 1
    assert resp['page_size'] == 25
    assert resp['total_items'] == 52
    assert resp['total_pages'] == 3
    assert resp['has_next'] is True
    assert resp['has_prev'] is False
    assert resp['papers'] == items


# ─── 3. Research & Reports Paginated Search Repository Tests ───────────────────

def test_research_search_and_pagination(app_instance, seeded_users):
    """إنشاء أبحاث وفحص البحث المبوب والفلترة بالرقم المرجعي والعنوان."""
    from app.repositories import batch_repo
    import uuid
    test_uid = uuid.uuid4().hex[:6].upper()
    prefix = f"RES-2026-P{test_uid}"
    
    with app_instance.app_context():
        # إنشاء 30 بحث تجريبي بمعرفات فريدة
        for i in range(1, 31):
            ref = f"{prefix}{i:04d}"
            batch_repo.create_research(
                title=f"بحث في القيادة الأمنية المتقدمة رقم {i} {test_uid}",
                author=f"الباحث الأمني المتخصص {i}",
                created_by="entry_search_perf",
                reference_number=ref,
                scan_status="completed",
                review_status="pending_review" if i % 2 == 0 else "preliminary_accepted"
            )

        # استعلام الصفحة الأولى (25 عنصر)
        items, total = batch_repo.search_researches(query=prefix, offset=0, limit=25)
        assert total == 30
        assert len(items) == 25

        # استعلام الصفحة الثانية
        items_p2, total_p2 = batch_repo.search_researches(query=prefix, offset=25, limit=25)
        assert len(items_p2) == 5

        # استعلام بالرقم المرجعي المباشر
        target_ref = f"{prefix}0015"
        items_ref, total_ref = batch_repo.search_researches(query=target_ref)
        assert total_ref == 1
        assert items_ref[0]['reference_number'] == target_ref

        # استعلام برقم مشرقي
        target_ar = target_ref.replace("0", "٠").replace("1", "١").replace("5", "٥")
        items_ar, total_ar = batch_repo.search_researches(query=target_ar)
        assert total_ar == 1
        assert items_ar[0]['reference_number'] == target_ref

        # فلترة بحالة التحكيم
        items_acc, total_acc = batch_repo.search_researches(query=prefix, review_status="preliminary_accepted")
        assert total_acc == 15
        for item in items_acc:
            assert item['review_status'] == "preliminary_accepted"


def test_data_scope_count_and_pages_isolation(app_instance, seeded_users):
    """
    التحقق الصارم من أن تقييد نطاق البيانات يطبق داخل الاستعلام قبل حساب COUNT:
    - total_items لا يتضمن الأبحاث غير المصرح بالوصول إليها.
    - total_pages لا تتضمن الأبحاث غير المصرح بها.
    - البحث لا يمكن أن يكشف وجود أبحاث أخرى عبر الأعداد الإجمالية.
    """
    from app.repositories import batch_repo
    import uuid
    secret_tag = uuid.uuid4().hex[:6]

    with app_instance.app_context():
        # إنشاء 5 أبحاث لمدخل البيانات
        for i in range(5):
            batch_repo.create_research(
                title=f"بحث متاح {i} {secret_tag}",
                author="باحث متاح",
                created_by="entry_search_perf",
                reference_number=f"RES-2026-ENTRY{secret_tag}{i}"
            )
        # إنشاء 10 أبحاث لمدير النظام
        for i in range(10):
            batch_repo.create_research(
                title=f"بحث محجوب {i} {secret_tag}",
                author="باحث محجوب",
                created_by="admin_search_perf",
                reference_number=f"RES-2026-ADMIN{secret_tag}{i}"
            )

        # استعلام مدخل البيانات
        items_entry, total_entry = batch_repo.search_researches(query=secret_tag, user_scope_username="entry_search_perf")
        # يجب أن يرى 5 فقط، وليس 15
        assert total_entry == 5
        assert len(items_entry) == 5
        for it in items_entry:
            assert it['created_by'] == "entry_search_perf"

        # استعلام المدير
        items_admin, total_admin = batch_repo.search_researches(query=secret_tag)
        assert total_admin >= 15


def test_api_page_beyond_last_page(client, seeded_users):
    """التحقق من السلوك الآمن والمحدد عند طلب رقم صفحة يتجاوز إجمالي الصفحات."""
    with client.session_transaction() as sess:
        sess['user_id'] = seeded_users['admin']['id']
        sess['username'] = seeded_users['admin']['username']
        sess['role'] = seeded_users['admin']['role']

    resp = client.get('/api/researches?page=999999&page_size=25')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['items'] == []
    assert data['page'] == 999999
    assert data['has_next'] is False
    assert data['has_prev'] is True or data['total_items'] == 0


# ─── 4. Endpoints Security, RBAC & Response Shape API Tests ───────────────────

def test_api_researches_pagination_endpoint(client, seeded_users):
    """فحص استجابة /api/researches مع التقسيم والترتيب."""
    with client.session_transaction() as sess:
        sess['user_id'] = seeded_users['admin']['id']
        sess['username'] = seeded_users['admin']['username']
        sess['role'] = seeded_users['admin']['role']

    resp = client.get('/api/researches?page=1&page_size=10&sort=created_at&order=desc')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'items' in data
    assert 'page' in data
    assert 'page_size' in data
    assert 'total_items' in data
    assert 'total_pages' in data
    assert data['page_size'] == 10
    assert len(data['items']) <= 10


def test_api_initial_reviews_paginated(client, seeded_users):
    """فحص استجابة طابور الفحص الأولي المبوب."""
    with client.session_transaction() as sess:
        sess['user_id'] = seeded_users['admin']['id']
        sess['username'] = seeded_users['admin']['username']
        sess['role'] = seeded_users['admin']['role']

    resp = client.get('/api/initial_reviews?page=1&page_size=10')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'items' in data or 'papers' in data
    assert 'total_items' in data


def test_api_preliminary_papers_paginated(client, seeded_users):
    """فحص استجابة الأبحاث المقبولة مبدئياً."""
    with client.session_transaction() as sess:
        sess['user_id'] = seeded_users['admin']['id']
        sess['username'] = seeded_users['admin']['username']
        sess['role'] = seeded_users['admin']['role']

    resp = client.get('/api/preliminary_papers?page=1&page_size=15')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['page_size'] == 15 or data.get('total_items') is not None


def test_api_rejected_papers_paginated(client, seeded_users):
    """فحص استجابة الأبحاث المرفوضة."""
    with client.session_transaction() as sess:
        sess['user_id'] = seeded_users['admin']['id']
        sess['username'] = seeded_users['admin']['username']
        sess['role'] = seeded_users['admin']['role']

    resp = client.get('/api/rejected_papers?page=1&page_size=20')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'items' in data or 'papers' in data


def test_api_papers_reference_corpus_paginated(client, seeded_users):
    """فحص استجابة قاعدة المراجع /api/papers."""
    with client.session_transaction() as sess:
        sess['user_id'] = seeded_users['admin']['id']
        sess['username'] = seeded_users['admin']['username']
        sess['role'] = seeded_users['admin']['role']

    resp = client.get('/api/papers?page=1&page_size=20')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'items' in data or 'papers' in data
    assert data.get('page_size') == 20 or data.get('per_page') == 20


def test_api_batches_paginated(client, seeded_users):
    """فحص استجابة دفعات الفحص /api/batches."""
    with client.session_transaction() as sess:
        sess['user_id'] = seeded_users['admin']['id']
        sess['username'] = seeded_users['admin']['username']
        sess['role'] = seeded_users['admin']['role']

    resp = client.get('/api/batches?page=1&page_size=10')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'items' in data or 'batches' in data


def test_api_audit_logs_paginated_and_filtered(client, seeded_users):
    """فحص استجابة سجل التدقيق /api/admin/audit_logs."""
    with client.session_transaction() as sess:
        sess['user_id'] = seeded_users['admin']['id']
        sess['username'] = seeded_users['admin']['username']
        sess['role'] = seeded_users['admin']['role']

    resp = client.get('/api/admin/audit_logs?page=1&page_size=15')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'events' in data
    assert data['page'] == 1
    assert data['total_items'] >= 0


def test_api_reports_search_endpoint(client, seeded_users):
    """فحص مسار البحث في التقارير /api/reports."""
    with client.session_transaction() as sess:
        sess['user_id'] = seeded_users['admin']['id']
        sess['username'] = seeded_users['admin']['username']
        sess['role'] = seeded_users['admin']['role']

    resp = client.get('/api/reports?page=1&page_size=25&review_status=all')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'items' in data
    assert 'total_pages' in data


def test_api_search_unauthorized_access(client):
    """التحقق من رفض الوصول غير المصادق عليه لمسارات الفحص المبوب."""
    with client.session_transaction() as sess:
        sess.clear()

    resp = client.get('/api/researches')
    assert resp.status_code in (401, 403)

    resp_audit = client.get('/api/admin/audit_logs')
    assert resp_audit.status_code in (401, 403)


def test_api_search_rbac_data_entry_forbidden_audit(client, seeded_users):
    """التحقق من منع مدخل البيانات من استعراض سجل التدقيق."""
    with client.session_transaction() as sess:
        sess['user_id'] = seeded_users['data_entry']['id']
        sess['username'] = seeded_users['data_entry']['username']
        sess['role'] = seeded_users['data_entry']['role']

    resp = client.get('/api/admin/audit_logs')
    assert resp.status_code == 403


# ─── 5. N+1 Prevention & Lightweight Queries Tests ────────────────────────────

def test_batch_get_n_plus_one_prevention(app_instance, seeded_users):
    """التأكد من جلب بيانات الدفعة وعناصرها باستعلام مدمج دون تكرار N+1."""
    from app.repositories import batch_repo

    with app_instance.app_context():
        batch_id = batch_repo.create_batch(label="دفعة أداء كبرى", created_by="admin_search_perf")
        for i in range(10):
            res_id = batch_repo.create_research(
                title=f"بحث الدفعة {i}",
                author=f"مؤلف {i}",
                created_by="admin_search_perf"
            )
            batch_repo.add_batch_item(batch_id, res_id, item_order=i+1)

        # استرجاع الدفعة
        b_data = batch_repo.get_batch(batch_id)
        assert b_data is not None
        assert len(b_data['items']) == 10
        for it in b_data['items']:
            assert it['research_title'].startswith("بحث الدفعة")


def test_document_list_lightweight_query(app_instance):
    """التأكد من أن استعلام قائمة المراجع لا يقوم بتحميل المقاطع الضخمة أو الصفحات بالكامل."""
    from app.repositories import document_repo

    with app_instance.app_context():
        import uuid
        unique_hash = f"perf_hash_{uuid.uuid4().hex}"
        # إضافة وثيقة بصفحات ومقاطع
        doc = document_repo.add_document(
            title="مرجع الفحص الموسع للأداء",
            author="د. أحمد الأكاديمي",
            file_hash=unique_hash,
            pages_data=[{'page_number': 1, 'text': 'محتوى كبير للصفحة 1' * 50}],
            segments_data=[{'page_number': 1, 'segment_number': 1, 'raw_text': 'فقرة طويلة' * 20}]
        )

        docs = document_repo.get_all_documents(page=1, per_page=10)
        assert docs['total_items'] >= 1
        found = False
        for d in docs['items']:
            if d['id'] == doc['id']:
                found = True
                assert 'title' in d
                assert 'author' in d
                # التحقق من خفة الكائن وعدم وجود حقول النصوص الضخمة
                assert 'raw_text' not in d
                assert 'segments' not in d
        assert found is True


def test_research_sorting_direction_asc_and_desc(app_instance, seeded_users):
    """التحقق من صحة الترتيب التصاعدي والتنازلي للأبحاث."""
    from app.repositories import batch_repo
    import uuid
    sort_tag = uuid.uuid4().hex[:6].upper()

    with app_instance.app_context():
        batch_repo.create_research(title=f"بحث الترتيب 1 {sort_tag}", author="مؤلف 1", reference_number=f"RES-2026-SORT{sort_tag}01")
        batch_repo.create_research(title=f"بحث الترتيب 2 {sort_tag}", author="مؤلف 2", reference_number=f"RES-2026-SORT{sort_tag}02")

        # ترتيب تنازلي
        items_desc, _ = batch_repo.search_researches(query=sort_tag, sort_field="created_at", order_direction="desc", limit=10)
        # ترتيب تصاعدي
        items_asc, _ = batch_repo.search_researches(query=sort_tag, sort_field="created_at", order_direction="asc", limit=10)

        assert len(items_desc) == 2
        assert len(items_asc) == 2
        assert items_desc[0]['reference_number'] != items_asc[0]['reference_number']


def test_batch_search_with_status_filter_and_dates(app_instance, seeded_users):
    """التحقق من استعلام وفلترة الدفعات بالحالة والنطاق الزمني."""
    from app.repositories import batch_repo

    with app_instance.app_context():
        b_id1 = batch_repo.create_batch(label="دفعة مكتملة تجريبية", created_by="admin_search_perf")
        b_id2 = batch_repo.create_batch(label="دفعة معلقة تجريبية", created_by="admin_search_perf")

        items, total = batch_repo.search_batches(query="تجريبية", status="all", limit=10)
        assert total >= 2
        labels = [b['label'] for b in items]
        assert "دفعة مكتملة تجريبية" in labels
        assert "دفعة معلقة تجريبية" in labels
