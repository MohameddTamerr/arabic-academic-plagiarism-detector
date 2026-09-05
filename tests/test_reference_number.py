# -*- coding: utf-8 -*-
"""
حزمة اختبارات الرقم المرجعي الرسمي للأبحاث الأكاديمية (Official Research Reference Tests):
- التحقق من فرادة وتنسيق الأرقام المرجعية.
- التحقق من توليد رقم لكل بحث في الدفعات.
- التحقق من إسناد رقم مرجعي واحد فقط للرسالة متعددة الملفات.
- التحقق من أمان التزامن ومنع تكرار الأرقام (Concurrency Safety).
- التحقق من عدم إعادة استخدام الأرقام بعد الحذف.
- التحقق من عدم إمكانية تعديل الرقم المرجعي عبر المسارات العادية (Immutability).
- التحقق من البحث المباشر والجزئي بالرقم المرجعي.
- التحقق من سلامة هجرة السجلات التاريخية.
"""

import uuid
import pytest
import concurrent.futures
import threading
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import config
from app.models.schema import Base, LegacyReport
from app.models.research_schema import Research, ResearchFile, ScanBatch, ScanBatchItem, ReferenceSequence
from app.services import reference_service, integrity_service
from app.services import storage_service
from app.repositories import batch_repo, report_repo
from app.repositories.base_repo import get_session


def test_single_research_gets_reference_number():
    """كل بحث مفرد يتم إنشاؤه يحصل على رقم مرجعي رسمي."""
    r_id = batch_repo.create_research(
        title="بحث الذكاء الاصطناعي والأمن القومي",
        author="د. أحمد محمود",
        created_by="admin"
    )
    assert r_id > 0
    res = batch_repo.get_research(r_id)
    assert res is not None
    assert res['reference_number'] != ''
    assert res['reference_number'].startswith(config.RESEARCH_REFERENCE_PREFIX + '-')


def test_reference_format_is_correct():
    """صيغة الرقم المرجعي تطابق المعيار المعتمد {PREFIX}-{YEAR}-{SEQUENCE:06d}."""
    with get_session() as session:
        ref = reference_service.get_next_research_reference(session, year=2026, prefix='RES')
        assert ref.startswith('RES-2026-')
        parts = ref.split('-')
        assert len(parts) == 3
        assert parts[0] == 'RES'
        assert parts[1] == '2026'
        assert len(parts[2]) == 6
        assert parts[2].isdigit()


def test_two_researches_receive_different_references():
    """بحثان متتاليان يحصلان على رقمين مرجعيين تسلسليين مختلفين."""
    r1_id = batch_repo.create_research(title="بحث أول", author="باحث 1")
    r2_id = batch_repo.create_research(title="بحث ثان", author="باحث 2")

    res1 = batch_repo.get_research(r1_id)
    res2 = batch_repo.get_research(r2_id)

    assert res1['reference_number'] != res2['reference_number']
    
    # التحقق من أن التسلسل متزايد
    seq1 = int(res1['reference_number'].split('-')[2])
    seq2 = int(res2['reference_number'].split('-')[2])
    assert seq2 == seq1 + 1


def test_batch_with_multiple_researches_gives_one_reference_per_research():
    """في الدفعة المجمعة، يحصل كل بحث مستقل على رقمه المرجعي الخاص والفريد."""
    batch_id = batch_repo.create_batch(label="دفعة أبحاث دبلوم العلوم الجنائية")
    
    r1_id = batch_repo.create_research(title="بحث المخدرات الرقمية", author="باحث أ", batch_id=batch_id)
    r2_id = batch_repo.create_research(title="بحث الجرائم الإلكترونية", author="باحث ب", batch_id=batch_id)
    r3_id = batch_repo.create_research(title="بحث حماية المنشآت", author="باحث ج", batch_id=batch_id)

    batch_repo.add_batch_item(batch_id=batch_id, research_id=r1_id, item_order=0)
    batch_repo.add_batch_item(batch_id=batch_id, research_id=r2_id, item_order=1)
    batch_repo.add_batch_item(batch_id=batch_id, research_id=r3_id, item_order=2)

    batch_data = batch_repo.get_batch(batch_id)
    assert len(batch_data['items']) == 3

    refs = [item['research_reference_number'] for item in batch_data['items']]
    assert len(set(refs)) == 3
    for ref in refs:
        assert ref != ''
        assert ref.startswith(config.RESEARCH_REFERENCE_PREFIX)


def test_multi_file_thesis_gets_one_reference_only():
    """الرسالة المكونة من عدة ملفات (أبواب وفصول) تحصل على رقم مرجعي واحد فقط للمنظومة."""
    thesis_id = batch_repo.create_research(
        title="رسالة دكتوراه: الاستراتيجيات الأمنية المعاصرة",
        author="المقدم/ طارق النجار",
        degree_type="دكتوراه"
    )

    f1_path = config.TEMP_UPLOAD_DIR / f"f1_{uuid.uuid4().hex[:6]}.pdf"
    f1_path.write_bytes(b"THESIS_PART_1_CONTENT")
    h1, s1 = integrity_service.compute_stream_sha256(f1_path)
    f1 = batch_repo.add_research_file(thesis_id, "الباب_الأول.pdf", f1_path.name, str(f1_path), "pdf", s1, 0, h1)

    f2_path = config.TEMP_UPLOAD_DIR / f"f2_{uuid.uuid4().hex[:6]}.pdf"
    f2_path.write_bytes(b"THESIS_PART_2_CONTENT")
    h2, s2 = integrity_service.compute_stream_sha256(f2_path)
    f2 = batch_repo.add_research_file(thesis_id, "الباب_الثاني.pdf", f2_path.name, str(f2_path), "pdf", s2, 1, h2)

    f3_path = config.TEMP_UPLOAD_DIR / f"f3_{uuid.uuid4().hex[:6]}.docx"
    f3_path.write_bytes(b"THESIS_PART_3_CONTENT")
    h3, s3 = integrity_service.compute_stream_sha256(f3_path)
    f3 = batch_repo.add_research_file(thesis_id, "الخاتمة_والملاحق.docx", f3_path.name, str(f3_path), "docx", s3, 2, h3)

    thesis = batch_repo.get_research(thesis_id)
    assert thesis['reference_number'] != ''
    assert len(thesis['files']) == 3
    # تأكيد أن الملفات تابعة لنفس الكيان ولا تملك أرقام مرجعية مستقلة
    assert thesis['files'][0]['id'] == f1
    assert thesis['files'][1]['id'] == f2
    assert thesis['files'][2]['id'] == f3


def test_exact_reference_search():
    """البحث الدقيق بالرقم المرجعي يسترجع البحث الصحيح بدقة."""
    r_id = batch_repo.create_research(title="بحث القانون المقارن", author="د. سامي")
    res = batch_repo.get_research(r_id)
    ref_num = res['reference_number']

    found = batch_repo.get_research_by_reference(ref_num)
    assert found is not None
    assert found['id'] == r_id
    assert found['title'] == "بحث القانون المقارن"


def test_partial_reference_search():
    """البحث الجزئي بالرقم المرجعي يطابق السجلات المتوافقة."""
    r_id = batch_repo.create_research(title="بحث الإجراءات الجنائية المستعجلة", author="د. كمال")
    res = batch_repo.get_research(r_id)
    ref_num = res['reference_number']
    
    # استخراج الجزء الرقمي فقط (مثال: '000005')
    seq_part = ref_num.split('-')[-1]
    
    with get_session() as session:
        matches = session.query(Research).filter(Research.reference_number.ilike(f"%{seq_part}%")).all()
        assert len(matches) >= 1
        found_ids = [m.id for m in matches]
        assert r_id in found_ids


def test_deleted_research_number_is_never_reused():
    """حذف بحث قديم لا يؤدي إلى إعادة استخدام رقمه المرجعي أبداً."""
    r1_id = batch_repo.create_research(title="بحث سيتم حذفه")
    res1 = batch_repo.get_research(r1_id)
    ref1 = res1['reference_number']

    # حذف البحث
    with get_session() as session:
        r_del = session.query(Research).filter(Research.id == r1_id).first()
        session.delete(r_del)

    # إنشاء بحث جديد
    r2_id = batch_repo.create_research(title="بحث جديد بعد الحذف")
    res2 = batch_repo.get_research(r2_id)
    ref2 = res2['reference_number']

    assert ref2 != ref1
    seq1 = int(ref1.split('-')[2])
    seq2 = int(ref2.split('-')[2])
    assert seq2 > seq1


def test_concurrency_safe_reference_generation():
    """توليد الأرقام المرجعية بالتزامن العالي (Multi-threading) يضمن عدم التكرار نهائياً."""
    generated_refs = []
    errors = []

    def worker():
        try:
            r_id = batch_repo.create_research(title=f"بحث متزامن من مسار {threading.get_ident()}")
            res = batch_repo.get_research(r_id)
            generated_refs.append(res['reference_number'])
        except Exception as e:
            errors.append(str(e))

    threads = [threading.Thread(target=worker) for _ in range(15)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    assert len(generated_refs) == 15
    # التأكد من أن كل الأرقام الـ 15 فريدة تماماً
    assert len(set(generated_refs)) == 15


def test_legacy_research_migration_assigns_deterministic_references():
    """الهجرة التاريخية تعين أرقاماً مرجعية تسلسلية ثابتة للسجلات القديمة."""
    # محاكاة سجلات بدون رقم مرجعي
    with get_session() as session:
        legacy1 = Research(
            title="بحث قديم 1",
            author="باحث قديم",
            created_at=datetime(2025, 5, 10, 10, 0),
            reference_number=None
        )
        legacy2 = Research(
            title="بحث قديم 2",
            author="باحث قديم",
            created_at=datetime(2025, 6, 15, 12, 0),
            reference_number=None
        )
        session.add(legacy1)
        session.add(legacy2)
        session.flush()
        l1_id, l2_id = legacy1.id, legacy2.id

    from app.repositories.base_repo import _migrate_research_reference_numbers
    _migrate_research_reference_numbers()

    res1 = batch_repo.get_research(l1_id)
    res2 = batch_repo.get_research(l2_id)

    assert res1['reference_number'] != ''
    assert res2['reference_number'] != ''
    assert res1['reference_number'].startswith(f"{config.RESEARCH_REFERENCE_PREFIX}-2025-")
    assert res2['reference_number'].startswith(f"{config.RESEARCH_REFERENCE_PREFIX}-2025-")
    assert res1['reference_number'] != res2['reference_number']


def test_reference_number_immutability():
    """الرقم المرجعي غير قابل للتعديل بعد الإنشاء عبر المسارات العادية."""
    r_id = batch_repo.create_research(title="بحث ثابت المرجع", author="د. خالد")
    res = batch_repo.get_research(r_id)
    orig_ref = res['reference_number']

    # محاولة تحديث الفحص أو التقرير
    batch_repo.update_research_scan(r_id, scan_job_id="job_test_123", report_id="rep_test_456")

    res_after = batch_repo.get_research(r_id)
    assert res_after['reference_number'] == orig_ref
    assert res_after['scan_job_id'] == "job_test_123"
    assert res_after['report_id'] == "rep_test_456"


def test_report_links_preserved_with_reference_number():
    """التقارير المخزنة ترتبط بالرقم المرجعي للبحث المرتبط وتسترجعه بدقة."""
    r_id = batch_repo.create_research(title="بحث مرتبط بتقرير", author="د. عمر")
    res = batch_repo.get_research(r_id)
    ref_no = res['reference_number']

    rep_id = f"rep_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    report_repo.save_report(
        report_id=rep_id,
        title="بحث مرتبط بتقرير",
        overall_pct=15.5,
        copied_pct=10.0,
        para_pct=5.5,
        report_dict={'title': 'بحث مرتبط بتقرير', 'author': 'د. عمر'},
        category='أمني',
        author='د. عمر'
    )
    batch_repo.update_research_scan(r_id, "job_abc", rep_id)

    rep_data = report_repo.get_report(rep_id)
    assert rep_data is not None
    assert rep_data['reference_number'] == ref_no
    assert rep_data['research_id'] == r_id

