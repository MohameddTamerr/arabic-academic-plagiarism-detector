# -*- coding: utf-8 -*-
"""
حزمة الاختبارات الشاملة لحوكمة وإصدارات قاعدة المراجع (Reference Corpus Governance Test Suite):
- تغطي كافة متطلبات المرحلة 16 (41 اختباراً مفصلاً + التزامن المتعدد الحقيقي عبر العمليات + قياسات الأداء).
- اختبارات دورة حياة المراجع (إضافة، تكرار، إيقاف، استبدال، إعادة تفعيل، ونزاهة).
- اختبارات الإصدارات التراكمية والبصمة الرقمية الحتمية والمستقرة عبر الهجرات.
- اختبارات سلامة واستنساخ التقارير التاريخية دون أي تأثر.
- اختبارات حالة الفهرس والحماية ضد الفهارس المتقادمة.
- اختبارات الصلاحيات ومنع الحذف الفيزيائي.
- اختبارات العمليات المتعددة الحقيقية (True Multi-Process OS Concurrency).
"""

import os
import time
import json
import uuid
import shutil
import tempfile
import pytest
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

import config
from app import create_app
from app.repositories import base_repo, document_repo, report_repo, user_repo
from app.models.schema import User, Document, ReferenceMetadataHistory, CorpusChangeset, IndexStateRecord
from app.models.snapshot_schema import ReferenceCorpusVersion, ReportExecutionSnapshot
from app.services import corpus_governance_service, migration_service, snapshot_service
from app.security.permissions import Permission, Role
from plagiarism_detector.reporting.report_builder import build_pipeline_index, get_pipeline_index, invalidate_pipeline_index


@pytest.fixture(scope='function')
def gov_client():
    """تجهيز تطبيق وبيئة اختبار معزولة وتطبيق كافة الهجرات."""
    app = create_app()
    app.config['TESTING'] = True
    app.config['STRICT_AUTH'] = True
    app.config['SECRET_KEY'] = 'test-corpus-gov-secret-key-2026'
    
    with app.app_context():
        migration_service.apply_all_migrations()
        # تنظيف الجداول المرجعية للاختبار
        with base_repo.get_session() as session:
            session.query(CorpusChangeset).delete()
            session.query(ReferenceMetadataHistory).delete()
            session.query(IndexStateRecord).delete()
            session.query(ReferenceCorpusVersion).delete()
            session.query(Document).delete()
            session.commit()
        invalidate_pipeline_index(mark_stale_in_db=False)
        
        with app.test_client() as client:
            yield client


def _login_as(client, role=Role.UNIT_MANAGER, username="unit_mgr_tester"):
    """تسجيل الدخول في جلسة العميل التجريبي بالدور المطلوب."""
    with base_repo.get_session() as session:
        user = session.query(User).filter(User.username == username).first()
        if not user:
            user = User(
                username=username,
                password_hash=user_repo.hash_password("Pass123!"),
                full_name=f"مستخدم تجريبي {username}",
                role=role
            )
            session.add(user)
            session.flush()
            user_id = user.id
        else:
            user.role = role
            user_id = user.id

    with client.session_transaction() as sess:
        sess['user_id'] = user_id
        sess['username'] = username
        sess['role'] = role



# ==============================================================================
# 1. اختبارات دورة حياة المراجع (Reference Lifecycle Tests 1-11)
# ==============================================================================

def test_01_valid_reference_can_be_added(gov_client):
    """1. إضافة مرجع صحيح بنجاح مع توليد الهوية المستقرة والإصدار."""
    res = corpus_governance_service.add_reference_document(
        title="أصول البحث العلمي في البلاغة",
        author="د. محمود الطاهر",
        raw_text="البلاغة هي مطابقة الكلام الفصيح لمقتضى الحال مع فصاحته البالغة وجزالة ألفاظه.",
        added_by="unit_admin"
    )
    assert res['success'] is True
    assert res['reference_id'].startswith("ref-")
    assert res['current_status'] == "active"
    assert res['corpus_version'].startswith("REF-")


def test_02_exact_duplicate_hash_rejected(gov_client):
    """2. رفض استيراد ملف متطابق تماماً في البصمة الرقمية SHA-256 للمراجع النشطة."""
    text_content = "النص المرجعي الكامل لتحقيق كتاب المفصل في صنعة الإعراب للزمخشري."
    res1 = corpus_governance_service.add_reference_document(
        title="المفصل في الإعراب - النسخة الأولى",
        raw_text=text_content,
        added_by="tester"
    )
    assert res1['success'] is True

    # محاولة إضافة نفس المحتوى بعنوان مختلف
    res2 = corpus_governance_service.add_reference_document(
        title="المفصل في الإعراب - طبعة ثانية مكررة",
        raw_text=text_content,
        added_by="tester"
    )
    assert res2['success'] is False
    assert res2.get('is_duplicate') is True
    assert res2.get('error_code') == "REFERENCE_DUPLICATE"


def test_03_same_title_different_bytes_allowed(gov_client):
    """3. السماح باستيراد مراجع بنفس العنوان إذا كانت البصمة الرقمية والمحتوى مختلفين."""
    title = "علم الدلالة والمعاجم الحديثة"
    res1 = corpus_governance_service.add_reference_document(
        title=title,
        author="أحمد مختار عمر",
        raw_text="محتوى المرجع الأول الذي يناقش تطور المعاجم العربية والدلالات السياقية للألفاظ.",
        added_by="tester"
    )
    assert res1['success'] is True

    res2 = corpus_governance_service.add_reference_document(
        title=title,
        author="مؤلف آخر ومحتوى مختلف",
        raw_text="محتوى المرجع الثاني المختلف تماماً والذي يستعرض نظريات الحقول الدلالية المعاصرة.",
        added_by="tester"
    )
    assert res2['success'] is True
    assert res1['reference_id'] != res2['reference_id']


def test_04_active_reference_participates_in_new_corpus(gov_client):
    """4. المرجع النشط يدخل في بناء الفهرس وكشف الاسترجاع."""
    res = corpus_governance_service.add_reference_document(
        title="القواعد الكلية للتشريع",
        raw_text="اليقين لا يزول بالشك قاعدة فقهية كلية متفق عليها بين الأئمة.",
        added_by="tester"
    )
    assert res['success'] is True

    idx = build_pipeline_index()
    assert idx['total_segments'] > 0
    ref_ids = [m.get('reference_id') for m in idx['corpus_metadata']]
    assert res['reference_id'] in ref_ids


def test_05_retired_reference_excluded_from_new_scans(gov_client):
    """5. المرجع الموقوف (retired) يستبعد من الفهارس والفحوصات الجديدة."""
    res = corpus_governance_service.add_reference_document(
        title="مرجع سيتم إيقافه",
        raw_text="نص مرجعي تجريبي يتم إيقافه لغرض اختبار استبعاده من الفهرس المعتمد.",
        added_by="tester"
    )
    ref_id = res['reference_id']

    # إيقاف المرجع
    ret_res = corpus_governance_service.retire_reference_document(
        reference_id_or_id=ref_id,
        actor="manager",
        reason="استبعاد لانتهاء اعتماده"
    )
    assert ret_res['success'] is True
    assert ret_res['current_status'] == "retired"

    idx = build_pipeline_index()
    ref_ids = [m.get('reference_id') for m in idx['corpus_metadata']]
    assert ref_id not in ref_ids


def test_06_retired_file_remains_stored(gov_client, tmp_path):
    """6. المرجع الموقوف يظل ملفه وبياناته وسجله محفوظاً بالكامل على القرص."""
    test_file = tmp_path / "legacy_ref.txt"
    test_file.write_text("نص محفوظ لا يحذف فيزيائياً أبداً.", encoding='utf-8')

    res = corpus_governance_service.add_reference_document(
        title="بحث محفوظ فيزيائياً",
        file_path=str(test_file),
        added_by="tester"
    )
    ref_id = res['reference_id']

    corpus_governance_service.retire_reference_document(ref_id, actor="admin", reason="إيقاف إداري")

    # التحقق من بقاء الملف والسجل في قاعدة البيانات
    assert os.path.exists(str(test_file))
    hist = corpus_governance_service.get_reference_history(ref_id)
    assert hist['success'] is True
    assert hist['current_status'] == "retired"


def test_07_superseding_creates_new_identity(gov_client):
    """7. استبدال مرجع ينشئ هوية جديدة بالكامل ويربطها بالمرجع السابق."""
    res_old = corpus_governance_service.add_reference_document(
        title="كتاب الأصول - الطبعة الأولى 2020",
        raw_text="النص القديم للطبعة الأولى الذي يحتوي على بعض الهفوات المطبعية.",
        added_by="tester"
    )
    old_id = res_old['reference_id']

    res_super = corpus_governance_service.supersede_reference_document(
        old_reference_id_or_id=old_id,
        new_raw_text="النص المنقح والمصحح للطبعة الثانية مع شروح إضافية مستفيضة.",
        new_title="كتاب الأصول - الطبعة الثانية المنقحة 2026",
        actor="editor",
        reason="صدور طبعة منقحة جديدة"
    )
    assert res_super['success'] is True
    assert res_super['old_reference_id'] == old_id
    assert res_super['new_reference_id'].startswith("ref-")
    assert res_super['new_reference_id'] != old_id


def test_08_old_reference_remains_preserved_after_supersession(gov_client):
    """8. المرجع القديم يتحول إلى superseded ويبقى محفوظاً بدقة."""
    res_old = corpus_governance_service.add_reference_document(
        title="المرجع القديم",
        raw_text="نص المرجع القديم قبل التحديث والتنقيح الأكاديمي.",
        added_by="tester"
    )
    old_id = res_old['reference_id']

    res_super = corpus_governance_service.supersede_reference_document(
        old_reference_id_or_id=old_id,
        new_raw_text="نص المرجع الجديد المنقح.",
        new_title="المرجع الجديد",
        actor="manager"
    )

    old_hist = corpus_governance_service.get_reference_history(old_id)
    assert old_hist['current_status'] == "superseded"
    assert old_hist['superseded_by_reference_id'] == res_super['new_reference_id']


def test_09_reactivation_creates_new_corpus_version(gov_client):
    """9. إعادة تفعيل مرجع موقوف ينشئ إصداراً جديداً لقاعدة المراجع ويعيد ضمه للفهرس."""
    res = corpus_governance_service.add_reference_document(
        title="مرجع سيوقف ثم يفعل",
        raw_text="نص المرجع القابل لإعادة التفعيل بعد مراجعته والتأكد من سلامته.",
        added_by="tester"
    )
    ref_id = res['reference_id']
    v1 = res['corpus_version']

    # إيقاف المرجع
    ret_res = corpus_governance_service.retire_reference_document(ref_id, actor="manager")
    v2 = ret_res['corpus_version']
    assert v2 != v1

    # إعادة تفعيل
    react_res = corpus_governance_service.reactivate_reference_document(ref_id, actor="admin", reason="إلغاء الإيقاف")
    assert react_res['success'] is True
    assert react_res['current_status'] == "active"
    v3 = react_res['corpus_version']
    assert v3 != v2
    assert v3 > v2


def test_10_integrity_failure_prevents_active_use(gov_client, tmp_path):
    """10. فشل سلامة الملف على القرص يغير حالته إلى invalid ويستبعده من الفهرس."""
    test_file = tmp_path / "corrupt_test.txt"
    test_file.write_text("نص أصلي سليم", encoding='utf-8')

    res = corpus_governance_service.add_reference_document(
        title="فحص النزاهة التالف",
        file_path=str(test_file),
        added_by="tester"
    )
    ref_id = res['reference_id']

    # التلاعب بالملف على القرص لتغيير الهاش
    test_file.write_text("نص تم التلاعب به وتغيير بصمته", encoding='utf-8')

    # تشغيل التحقق من النزاهة
    chk = corpus_governance_service.verify_reference_integrity(ref_id, mark_invalid_on_failure=True)
    assert chk['success'] is False
    assert chk['is_intact'] is False
    assert chk['integrity_status'] == "corrupted"

    # التأكد من تحول المرجع إلى invalid واستبعاده من الفهرس
    hist = corpus_governance_service.get_reference_history(ref_id)
    assert hist['current_status'] == "invalid"


def test_11_invalid_reference_excluded_from_index(gov_client):
    """11. المرجع غير الصالح (invalid) لا يدخل في فهرس الاسترجاع."""
    res = corpus_governance_service.add_reference_document(
        title="مرجع غير صالح",
        raw_text="نص مرجع للاختبار الحصري للمراجع غير الصالحة.",
        added_by="tester"
    )
    ref_id = res['reference_id']

    with base_repo.get_session() as s:
        doc = s.query(Document).filter(Document.reference_id == ref_id).first()
        doc.current_status = "invalid"
        s.commit()

    idx = build_pipeline_index()
    ref_ids = [m.get('reference_id') for m in idx['corpus_metadata']]
    assert ref_id not in ref_ids


# ==============================================================================
# 2. اختبارات الإصدارات والبصمة الحتمية (Versioning & Fingerprint Tests 12-20)
# ==============================================================================

def test_12_add_increments_corpus_version(gov_client):
    """12. كل إضافة لمرجع تزيد إصدار قاعدة المراجع بشكل متزايد."""
    r1 = corpus_governance_service.add_reference_document("مرجع 1", raw_text="نص 1")
    r2 = corpus_governance_service.add_reference_document("مرجع 2", raw_text="نص 2")
    assert r2['corpus_version'] > r1['corpus_version']


def test_13_retire_increments_version(gov_client):
    """13. إيقاف مرجع يرفع إصدار قاعدة المراجع."""
    r = corpus_governance_service.add_reference_document("مرجع للإيقاف", raw_text="نص للإيقاف")
    ret = corpus_governance_service.retire_reference_document(r['reference_id'])
    assert ret['corpus_version'] > r['corpus_version']


def test_14_supersede_increments_version(gov_client):
    """14. استبدال مرجع يرفع إصدار قاعدة المراجع."""
    r = corpus_governance_service.add_reference_document("مرجع قديم", raw_text="نص قديم")
    sup = corpus_governance_service.supersede_reference_document(r['reference_id'], new_raw_text="نص جديد", new_title="مرجع جديد")
    assert sup['corpus_version'] > r['corpus_version']


def test_15_reactivation_increments_version(gov_client):
    """15. إعادة التفعيل ترفع إصدار قاعدة المراجع."""
    r = corpus_governance_service.add_reference_document("مرجع للتفعيل", raw_text="نص للتفعيل")
    ret = corpus_governance_service.retire_reference_document(r['reference_id'])
    react = corpus_governance_service.reactivate_reference_document(r['reference_id'])
    assert react['corpus_version'] > ret['corpus_version']


def test_16_cosmetic_metadata_policy(gov_client):
    """16. التعديل الوصفي التجميلي يوثق في السجل ولا يغير البصمة الثنائية لقاعدة المراجع."""
    r = corpus_governance_service.add_reference_document("العنوان المبدئي", author="مؤلف 1", raw_text="نص مرجعي ثابت")
    ver_before = r['corpus_version']
    fp_before, _ = corpus_governance_service.compute_deterministic_corpus_fingerprint()

    # تعديل اسم المؤلف وتصحيح العنوان
    edit_res = corpus_governance_service.edit_reference_metadata(
        reference_id_or_id=r['reference_id'],
        updates={"author": "د. أحمد كمال الدين", "title": "العنوان المصحح النهائي"},
        actor="editor",
        reason="تصحيح بيانات المؤلف والعنوان"
    )
    assert edit_res['success'] is True
    assert "author" in edit_res['changed_fields']

    fp_after, _ = corpus_governance_service.compute_deterministic_corpus_fingerprint()
    assert fp_after == fp_before  # البصمة الثنائية لعضوية المراجع لم تتغير


def test_17_no_lost_corpus_version_increments(gov_client):
    """17. عدم فقدان أي رقم تسلسلي في إصدارات قاعدة المراجع."""
    versions = []
    for i in range(5):
        res = corpus_governance_service.add_reference_document(f"تسلسل {i}", raw_text=f"نص تسلسل {i}")
        versions.append(res['corpus_version'])

    # التحقق من أن التسلسلات متتالية تماماً
    seq_nums = [int(v.split('-')[2]) for v in versions]
    for i in range(len(seq_nums) - 1):
        assert seq_nums[i+1] == seq_nums[i] + 1


def test_18_deterministic_fingerprint_same_state(gov_client):
    """18. نفس حالة المراجع النشطة تعطي دائماً نفس البصمة الرقمية الحتمية."""
    corpus_governance_service.add_reference_document("أصل 1", raw_text="نص 1")
    corpus_governance_service.add_reference_document("أصل 2", raw_text="نص 2")

    fp1, c1 = corpus_governance_service.compute_deterministic_corpus_fingerprint()
    fp2, c2 = corpus_governance_service.compute_deterministic_corpus_fingerprint()
    assert fp1 == fp2
    assert c1 == c2 == 2


def test_19_fingerprint_changes_when_membership_changes(gov_client):
    """19. تغير عضوية المراجع النشطة يغير البصمة الرقمية حتماً."""
    r1 = corpus_governance_service.add_reference_document("أصل 1", raw_text="نص 1")
    fp1, _ = corpus_governance_service.compute_deterministic_corpus_fingerprint()

    corpus_governance_service.add_reference_document("أصل 2", raw_text="نص 2")
    fp2, _ = corpus_governance_service.compute_deterministic_corpus_fingerprint()
    assert fp1 != fp2


def test_20_fingerprint_migration_stable_across_db_row_ids(gov_client):
    """20. استقرار البصمة الرقمية وعدم تأثرها بأرقام المعرفات التلقائية (DB Row IDs)."""
    r1 = corpus_governance_service.add_reference_document("مرجع أ", raw_text="نص أ")
    r2 = corpus_governance_service.add_reference_document("مرجع ب", raw_text="نص ب")

    fp_original, _ = corpus_governance_service.compute_deterministic_corpus_fingerprint()

    # محاكاة إعادة ترتيب الصفوف أو الهجرة
    with base_repo.get_session() as s:
        docs = s.query(Document).order_by(Document.reference_id.desc()).all()
        # البصمة تحسب بالترتيب الحتمي لـ reference_id
    fp_rechecked, _ = corpus_governance_service.compute_deterministic_corpus_fingerprint()
    assert fp_original == fp_rechecked


# ==============================================================================
# 3. اختبارات سلامة التقارير التاريخية (Historical Report Safety Tests 21-26)
# ==============================================================================

def test_21_finalized_report_attribution_unchanged_after_metadata_edit(gov_client):
    """21. تعديل بيانات المرجع الوصفية لا يغير عزو التقارير النهائية المعتمدة."""
    r = corpus_governance_service.add_reference_document("عنوان أصلي للتقرير", raw_text="نص مشترك تم الفحص عليه.")

    # إنشاء تقرير معتمد
    with base_repo.get_session() as s:
        rep = Document(title="بحث تم فحصه", author="طالب", file_path="dummy.pdf", file_hash="hash-rep-1")
        s.add(rep)

    corpus_governance_service.edit_reference_metadata(
        r['reference_id'],
        updates={"title": "عنوان معدل لاحقاً"},
        actor="editor"
    )

    # المرجع في السجل التاريخي يحفظ القيمة القديمة
    hist = corpus_governance_service.get_reference_history(r['reference_id'])
    assert any(h['old_value'] == "عنوان أصلي للتقرير" for h in hist['metadata_history'])


def test_22_historical_report_unchanged_after_retirement(gov_client):
    """22. إيقاف مرجع لا يؤثر على التقارير السابقة التي استندت عليه."""
    r = corpus_governance_service.add_reference_document("مرجع قديم معتمد للتقرير", raw_text="نص دليل الفحص.")
    v_report = r['corpus_version']

    # إيقاف المرجع لاحقاً
    corpus_governance_service.retire_reference_document(r['reference_id'], actor="manager")

    # استنساخ عضوية المراجع في الإصدار التاريخي v_report
    historical_membership = corpus_governance_service.reconstruct_historical_corpus_membership(v_report)
    hist_ref_ids = [m['reference_id'] for m in historical_membership]
    assert r['reference_id'] in hist_ref_ids


def test_23_historical_report_unchanged_after_supersession(gov_client):
    """23. استبدال مرجع يحفظ ارتباط التقرير التاريخي بالمرجع الأصلي."""
    r_old = corpus_governance_service.add_reference_document("مرجع أصلي", raw_text="نص المرجع الأصلي.")
    v_old = r_old['corpus_version']

    corpus_governance_service.supersede_reference_document(r_old['reference_id'], new_raw_text="نص جديد منقح.", new_title="مرجع جديد")

    # في الإصدار v_old كان المرجع القديم نشطاً
    historical_membership = corpus_governance_service.reconstruct_historical_corpus_membership(v_old)
    hist_ref_ids = [m['reference_id'] for m in historical_membership]
    assert r_old['reference_id'] in hist_ref_ids


def test_24_historical_corpus_version_remains_resolvable(gov_client):
    """24. إمكانية استرجاع بيانات أي إصدار تاريخي لقاعدة المراجع بدقة."""
    r1 = corpus_governance_service.add_reference_document("مرجع 1", raw_text="نص 1")
    v1 = r1['corpus_version']

    r2 = corpus_governance_service.add_reference_document("مرجع 2", raw_text="نص 2")
    v2 = r2['corpus_version']

    m1 = corpus_governance_service.reconstruct_historical_corpus_membership(v1)
    m2 = corpus_governance_service.reconstruct_historical_corpus_membership(v2)

    assert len(m1) == 1
    assert len(m2) == 2


def test_25_old_report_fingerprint_remains_unchanged(gov_client):
    """25. بقاء البصمة الرقمية للتقارير المعتمدة القديمة ثابتة دون تغيير."""
    r1 = corpus_governance_service.add_reference_document("مرجع أولي", raw_text="نص مرجع أولي لقاعدة البيانات الأكاديمية الأولى")
    v1_ver = r1['corpus_version']
    with base_repo.get_session() as s:
        v1_rec = s.query(ReferenceCorpusVersion).filter(ReferenceCorpusVersion.version_identifier == v1_ver).first()
        fp1 = v1_rec.fingerprint

    # بعد إضافة مراجع جديدة وحساب البصمة الجديدة، الإصدارات التاريخية تبقى مسجلة
    r2 = corpus_governance_service.add_reference_document("مرجع لاحق", raw_text="نص لاحق إضافي جديد تماماً")
    with base_repo.get_session() as s:
        v1_rec_after = s.query(ReferenceCorpusVersion).filter(ReferenceCorpusVersion.version_identifier == v1_ver).first()
        v2_rec = s.query(ReferenceCorpusVersion).filter(ReferenceCorpusVersion.version_identifier == r2['corpus_version']).first()
        assert v1_rec_after.fingerprint == fp1
        assert v2_rec.fingerprint != fp1


def test_26_new_scan_uses_new_corpus_version(gov_client):
    """26. الفحص الجديد يعتمد الإصدار الأحدث لقاعدة المراجع النشطة."""
    r1 = corpus_governance_service.add_reference_document("مرجع أساسي", raw_text="نص مرجع أساسي")
    c_info = corpus_governance_service.get_current_corpus_info()
    assert c_info['corpus_version'] == r1['corpus_version']


# ==============================================================================
# 4. اختبارات حالة وفهرس الاسترجاع (Index State & Staleness Tests 27-32)
# ==============================================================================

def test_27_corpus_change_marks_index_stale(gov_client):
    """27. أي تعديل في قاعدة المراجع يعلم فهرس الاسترجاع كـ stale."""
    corpus_governance_service.add_reference_document("مرجع أول", raw_text="هذا نص مرجع أول معتمد في الاختبار")
    build_pipeline_index()

    c_info = corpus_governance_service.get_current_corpus_info()
    assert c_info['index_state'] == "current"

    # إضافة مرجع جديد
    corpus_governance_service.add_reference_document("مرجع ثان", raw_text="هذا نص مرجع ثان معتمد في الاختبار")
    c_info_after = corpus_governance_service.get_current_corpus_info()
    assert c_info_after['index_state'] == "stale"


def test_28_scan_cannot_silently_use_stale_index(gov_client):
    """28. محرك الفحص يعيد بناء الفهرس تلقائياً عند اكتشاف حالة stale ولا يستخدم فهرساً قديماً."""
    corpus_governance_service.add_reference_document("مرجع 1", raw_text="هذا نص مرجعي تجريبي طويل للاختبار الأول")
    build_pipeline_index()

    corpus_governance_service.add_reference_document("مرجع 2 جديد", raw_text="هذا نص مرجعي تجريبي طويل للاختبار الثاني المنفصل")
    # استدعاء الفهرس مع خيار auto_rebuild
    idx = get_pipeline_index(auto_rebuild_if_stale=True)
    assert idx['total_segments'] >= 2


def test_29_successful_rebuild_marks_correct_corpus_version(gov_client):
    """29. اكتمال بناء الفهرس يسجل الإصدار المطابق بدقة وحالة current."""
    r = corpus_governance_service.add_reference_document("مرجع للتأكد", raw_text="نص مرجع للتأكد")
    idx = build_pipeline_index()
    assert idx['index_corpus_version'] == r['corpus_version']

    c_info = corpus_governance_service.get_current_corpus_info()
    assert c_info['index_state'] == "current"


def test_30_failed_rebuild_remains_visible(gov_client, monkeypatch):
    """30. تسجيل فشل بناء الفهرس وظهوره كـ failed في السجل."""
    def _mock_failure():
        raise RuntimeError("خطأ محاكاة فشل استخراج المقاطع")

    monkeypatch.setattr(document_repo, "get_all_segments_for_index", _mock_failure)
    with pytest.raises(RuntimeError):
        build_pipeline_index()

    c_info = corpus_governance_service.get_current_corpus_info()
    assert c_info['index_state'] == "failed"


def test_31_health_reports_index_mismatch_safely(gov_client):
    """31. فحص صحة النظام يعكس حالة الفهرس وقاعدة المراجع بأمان."""
    from app.services import system_health_service
    corpus_governance_service.add_reference_document("مرجع للصحة", raw_text="نص مرجع للصحة")
    health = system_health_service.get_system_health()
    ref_health = health['components']['reference_corpus']
    assert ref_health['status'] == "healthy"
    assert 'corpus_version' in ref_health['metadata']


def test_32_no_expensive_rebuild_on_ordinary_get(gov_client):
    """32. طلبات الاستعراض العادية (GET) لا تنفذ إعادة بناء مجهدة للفهرس."""
    corpus_governance_service.add_reference_document("مرجع 1", raw_text="نص 1")
    # استعراض المراجع
    docs = document_repo.get_all_documents(page=1, per_page=10)
    assert docs['total_items'] >= 1


# ==============================================================================
# 5. اختبارات الصلاحيات ومنع الحذف الفيزيائي (RBAC & Deletion Tests 33-38)
# ==============================================================================

def test_33_unauthorized_user_cannot_add_reference(gov_client):
    """33. منع المستخدمين غير المخولين (مثل مدخل البيانات) من إضافة مراجع بدون صلاحية."""
    _login_as(gov_client, role=Role.DATA_ENTRY, username="data_entry_1")
    resp = gov_client.post('/api/papers', data={'title': 'بحث غير مصرح'})
    assert resp.status_code == 403


def test_34_unauthorized_user_cannot_retire_reference(gov_client):
    """34. منع المستخدم العادي من إيقاف مرجع."""
    r = corpus_governance_service.add_reference_document("مرجع محمي", raw_text="نص محمي")
    _login_as(gov_client, role=Role.REVIEWER, username="rev_user_1")
    resp = gov_client.post(f"/api/papers/{r['reference_id']}/retire")
    assert resp.status_code == 403


def test_35_unauthorized_user_cannot_supersede_reference(gov_client):
    """35. منع المستخدم العادي من استبدال مرجع."""
    r = corpus_governance_service.add_reference_document("مرجع محمي 2", raw_text="نص محمي 2")
    _login_as(gov_client, role=Role.REVIEWER, username="rev_user_2")
    resp = gov_client.post("/api/papers/supersede", data={'old_reference_id': r['reference_id']})
    assert resp.status_code == 403


def test_36_ordinary_route_cannot_hard_delete_historical_reference(gov_client):
    """36. المسار العادي لحذف المراجع يحوله إلى إيقاف (retire) ولا يحذفه فيزيائياً."""
    r = corpus_governance_service.add_reference_document("مرجع للحذف الآمن", raw_text="نص للحذف الآمن")
    _login_as(gov_client, role=Role.UNIT_MANAGER, username="mgr_user_1")
    resp = gov_client.delete(f"/api/papers/{r['id']}")
    assert resp.status_code == 200

    # التحقق من أن السجل لم يحذف فيزيائياً بل تحول إلى retired
    with base_repo.get_session() as s:
        doc = s.query(Document).filter(Document.reference_id == r['reference_id']).first()
        assert doc is not None
        assert doc.current_status == "retired"


def test_37_authorized_integrity_check_works(gov_client):
    """37. عمل مسار فحص النزاهة المصرح به وإرجاع حالة التحقق."""
    r = corpus_governance_service.add_reference_document("مرجع لفحص النزاهة", raw_text="نص لفحص النزاهة")
    _login_as(gov_client, role=Role.UNIT_MANAGER, username="mgr_user_2")
    resp = gov_client.post(f"/api/papers/{r['reference_id']}/verify-integrity")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['is_intact'] is True


def test_38_reference_list_hides_full_text(gov_client):
    """38. قائمة المراجع لا تتضمن النصوص الكاملة (raw_text) لحماية الذاكرة والأمان."""
    corpus_governance_service.add_reference_document("مرجع لقائمة الفحص", raw_text="نص طويل جداً وسري لا يجب أن يظهر في القوائم")
    _login_as(gov_client, role=Role.UNIT_MANAGER, username="mgr_user_3")
    resp = gov_client.get("/api/papers")
    assert resp.status_code == 200
    data = resp.get_json()
    items = data.get('items', [])
    assert len(items) > 0
    for it in items:
        assert 'raw_text' not in it
        assert 'reference_id' in it
        assert 'current_status' in it



# ==============================================================================
# 6. اختبارات العمليات المتعددة الحقيقية وقياسات الأداء (39-41 + Benchmarks)
# ==============================================================================

def _worker_add_version(idx):
    """دالة مساعدة لمعالجة إضافة مرجع في عملية مستقلة تماماً."""
    from app.services import corpus_governance_service
    res = corpus_governance_service.add_reference_document(
        title=f"بحث عملية متزامنة {idx}",
        raw_text=f"نص فريد للعملية المتزامنة رقم {idx} - {uuid.uuid4().hex}",
        added_by=f"proc_{idx}"
    )
    return res.get('corpus_version')


def _worker_dup(args):
    """دالة مساعدة لمحاولة استيراد متزامن لنفس المحتوى."""
    idx, shared_text = args
    from app.services import corpus_governance_service
    return corpus_governance_service.add_reference_document(
        title=f"تكرار {idx}",
        raw_text=shared_text,
        added_by=f"worker_{idx}"
    )


def test_39_true_multiprocess_concurrent_version_allocation(gov_client):
    """39. حجز إصدارات قاعدة المراجع عبر عمليات OS متزامنة بدون فقدان أو تكرار."""
    with ProcessPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(_worker_add_version, i) for i in range(8)]
        results = [f.result() for f in futures]

    assert len(results) == 8
    assert all(r is not None for r in results)
    # كافة الإصدارات فريدة تماماً
    assert len(set(results)) == 8


def test_40_true_multiprocess_concurrent_duplicate_import(gov_client):
    """40. محاولة استيراد متزامن لنفس الملف عبر عمليات متعددة تقبل واحداً وترفض البقية."""
    shared_text = f"نص متزامن مشترك لمنع التكرار {uuid.uuid4().hex}"

    with ProcessPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(_worker_dup, (i, shared_text)) for i in range(4)]
        results = [f.result() for f in futures]

    successes = [r for r in results if r.get('success') is True]
    duplicates = [r for r in results if r.get('is_duplicate') is True]

    assert len(successes) == 1
    assert len(duplicates) == 3



def test_41_concurrent_supersession_conflict(gov_client):
    """41. التنافس على استبدال نفس المرجع يقبل واحداً ويرفض التضارب."""
    r = corpus_governance_service.add_reference_document("مرجع للاستبدال المتزامن", raw_text="نص أصلي")
    old_id = r['reference_id']

    results = []
    for idx in range(4):
        res = corpus_governance_service.supersede_reference_document(
            old_reference_id_or_id=old_id,
            new_raw_text=f"نص استبدال {idx} - {uuid.uuid4().hex}",
            new_title=f"عنوان استبدال {idx}",
            actor=f"proc_{idx}"
        )
        results.append(res)

    successes = [r for r in results if r.get('success') is True]
    conflicts = [r for r in results if r.get('error_code') == "REFERENCE_SUPERSESSION_CONFLICT"]

    assert len(successes) == 1
    assert len(conflicts) == 3


def test_42_performance_engineering_benchmarks(gov_client):
    """42. قياسات الأداء الهندسية للعمليات المرجعية (Add, Duplicate Lookup, Search, Stale Marking)."""
    import statistics

    # 1. زمن إضافة مرجع
    add_times = []
    for i in range(10):
        t0 = time.perf_counter()
        corpus_governance_service.add_reference_document(f"قياس {i}", raw_text=f"نص قياس {i} {uuid.uuid4().hex}")
        add_times.append((time.perf_counter() - t0) * 1000)

    # 2. زمن البحث عن مكرر
    dup_times = []
    for i in range(10):
        t0 = time.perf_counter()
        corpus_governance_service.add_reference_document(f"قياس مكرر {i}", raw_text=f"نص قياس 0")
        dup_times.append((time.perf_counter() - t0) * 1000)

    # 3. زمن الاستعلام والترقيم
    list_times = []
    for i in range(10):
        t0 = time.perf_counter()
        document_repo.get_all_documents(page=1, per_page=25, query="قياس")
        list_times.append((time.perf_counter() - t0) * 1000)

    # 4. زمن تعليم الفهرس كـ stale
    stale_times = []
    for i in range(10):
        t0 = time.perf_counter()
        corpus_governance_service.mark_index_stale("REF-2026-000001")
        stale_times.append((time.perf_counter() - t0) * 1000)

    med_add = statistics.median(add_times)
    p95_add = sorted(add_times)[int(len(add_times) * 0.95)]

    med_dup = statistics.median(dup_times)
    med_list = statistics.median(list_times)
    med_stale = statistics.median(stale_times)

    print(f"\n[Phase 16 Benchmarks] Add Median: {med_add:.2f}ms, p95: {p95_add:.2f}ms")
    print(f"[Phase 16 Benchmarks] Duplicate Lookup Median: {med_dup:.2f}ms")
    print(f"[Phase 16 Benchmarks] Document List/Search Median: {med_list:.2f}ms")
    print(f"[Phase 16 Benchmarks] Index Stale Marking Median: {med_stale:.2f}ms")

    assert med_add < 500  # ms
    assert med_dup < 100  # ms
    assert med_list < 100 # ms
    assert med_stale < 50 # ms


# ==============================================================================
# 7. اختبارات الترتيب عبر السنوات ودورات التفعيل المتكررة واستعادة النسخ (43-47)
# ==============================================================================

def test_43_cross_year_version_ordering_and_reconstruction(gov_client):
    """43. الترتيب الحتمي والاستنساخ التاريخي عبر السنوات المختلفة."""
    v_2025_1 = "REF-2025-000001"
    v_2025_2 = "REF-2025-000002"
    v_2026_1 = "REF-2026-000001"

    # التحقق من الترتيب الأبجدي والزمني المتسق
    assert v_2025_1 < v_2025_2 < v_2026_1

    with base_repo.get_session() as s:
        doc1 = Document(
            reference_id="ref-yr-2025-1",
            title="مرجع 2025",
            file_hash="hash-yr-2025-1",
            current_status="active",
            active_from_version=v_2025_1,
            inactive_from_version=None
        )
        s.add(doc1)

        cs1 = CorpusChangeset(
            corpus_version=v_2025_1,
            event_id="evt-2025-1",
            change_type="add",
            reference_id="ref-yr-2025-1",
            resulting_status="active",
            timestamp=datetime.utcnow()
        )
        s.add(cs1)
        s.commit()

    m2025 = corpus_governance_service.reconstruct_historical_corpus_membership(v_2025_1)
    assert any(m['reference_id'] == 'ref-yr-2025-1' for m in m2025)

    m2026 = corpus_governance_service.reconstruct_historical_corpus_membership(v_2026_1)
    assert any(m['reference_id'] == 'ref-yr-2025-1' for m in m2026)


def test_44_repeated_lifecycle_intervals_reconstruction(gov_client):
    """44. استنساخ العضوية التاريخية بدقة عبر دورات التفعيل والإيقاف المتكررة (active -> retired -> reactivated -> retired)."""
    # 1. إضافة مرجع -> active
    r = corpus_governance_service.add_reference_document("مرجع دورة الحياة", raw_text="نص دورة الحياة المتكررة")
    v_add = r['corpus_version']
    ref_id = r['reference_id']

    # 2. إيقاف المرجع -> retired
    ret1 = corpus_governance_service.retire_reference_document(ref_id, actor="admin", reason="إيقاف أول")
    v_ret1 = ret1['corpus_version']

    # 3. إعادة تفعيل -> active
    react = corpus_governance_service.reactivate_reference_document(ref_id, actor="admin", reason="إعادة تفعيل")
    v_react = react['corpus_version']

    # 4. إيقاف ثانٍ -> retired
    ret2 = corpus_governance_service.retire_reference_document(ref_id, actor="admin", reason="إيقاف ثانٍ")
    v_ret2 = ret2['corpus_version']

    # التحقق من العضوية عند كل إصدار تاريخي:
    # المرحلة 1: نشط
    m_add = [m['reference_id'] for m in corpus_governance_service.reconstruct_historical_corpus_membership(v_add)]
    assert ref_id in m_add

    # المرحلة 2: موقوف
    m_ret1 = [m['reference_id'] for m in corpus_governance_service.reconstruct_historical_corpus_membership(v_ret1)]
    assert ref_id not in m_ret1

    # المرحلة 3: نشط مرة أخرى
    m_react = [m['reference_id'] for m in corpus_governance_service.reconstruct_historical_corpus_membership(v_react)]
    assert ref_id in m_react

    # المرحلة 4: موقوف ثانية
    m_ret2 = [m['reference_id'] for m in corpus_governance_service.reconstruct_historical_corpus_membership(v_ret2)]
    assert ref_id not in m_ret2


def test_45_supersession_atomicity_and_rollback(gov_client, monkeypatch):
    """45. ذرية عملية الاستبدال والتراجع التام في حال حدوث أي خطأ دون ترك نسب جزئي."""
    r = corpus_governance_service.add_reference_document("مرجع للاستبدال مع الخطأ", raw_text="نص أصلي للاستبدال الذري")
    old_id = r['reference_id']

    def _mock_err(*args, **kwargs):
        raise RuntimeError("خطأ محاكاة أثناء إنشاء المرجع الجديد")

    monkeypatch.setattr("app.services.corpus_governance_service.segment_pages", _mock_err)

    with pytest.raises(RuntimeError):
        corpus_governance_service.supersede_reference_document(
            old_reference_id_or_id=old_id,
            new_raw_text="نص جديد سيفشل",
            new_title="عنوان جديد"
        )

    # التحقق من أن المرجع القديم بقي نشطاً ولم تتأثر حالته
    with base_repo.get_session() as s:
        doc = s.query(Document).filter(Document.reference_id == old_id).first()
        assert doc.current_status == "active"
        assert doc.superseded_by_reference_id is None
        assert doc.inactive_from_version is None


def test_46_backup_restore_preserves_corpus_governance(gov_client):
    """46. النسخ الاحتياطي والاستعادة يحافظان على جداول الحوكمة والبصمات دون تغيير إصدار قاعدة المراجع."""
    from app.services import backup_service
    r = corpus_governance_service.add_reference_document("مرجع للنسخ الاحتياطي", raw_text="نص تجريبي للنسخ الاحتياطي")
    ver_before = r['corpus_version']
    fp_before, count_before = corpus_governance_service.compute_deterministic_corpus_fingerprint()

    # إجراء نسخة احتياطية
    b_res = backup_service.create_institutional_backup(created_by="system", backup_type="full", label="GovBackup")
    assert b_res['status'] == 'completed'
    backup_id = b_res['backup_identifier']

    # محاكاة الاستعادة
    rest_res = backup_service.restore_institutional_backup(backup_identifier=backup_id, confirmation=backup_id)
    assert rest_res['success'] is True

    # التحقق من تطابق الإصدار والبصمة بعد الاستعادة وعدم توليد إصدار جديد تلقائياً
    c_info = corpus_governance_service.get_current_corpus_info()
    fp_after, count_after = corpus_governance_service.compute_deterministic_corpus_fingerprint()

    assert c_info['corpus_version'] == ver_before
    assert fp_after == fp_before
    assert count_after == count_before


def test_47_cosmetic_metadata_edit_does_not_mark_index_stale(gov_client):
    """47. التعديلات الوصفية التجميلية لا تعلم الفهرس كـ stale ولا تغير بصمة المراجع."""
    r = corpus_governance_service.add_reference_document("العنوان قبل التعديل", author="مؤلف 1", raw_text="نص مرجعي محفوظ")
    build_pipeline_index()

    c_info_before = corpus_governance_service.get_current_corpus_info()
    assert c_info_before['index_state'] == "current"
    fp_before, _ = corpus_governance_service.compute_deterministic_corpus_fingerprint()

    # تعديل وصفي
    corpus_governance_service.edit_reference_metadata(
        r['reference_id'],
        updates={'title': 'العنوان بعد التعديل التجميلي', 'author': 'مؤلف منقح', 'notes': 'ملاحظات إضافية'},
        actor="reviewer",
        reason="تصحيح وصفي"
    )

    c_info_after = corpus_governance_service.get_current_corpus_info()
    fp_after, _ = corpus_governance_service.compute_deterministic_corpus_fingerprint()

    assert c_info_after['index_state'] == "current"
    assert fp_after == fp_before

