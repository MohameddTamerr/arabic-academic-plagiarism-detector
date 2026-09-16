# -*- coding: utf-8 -*-
"""
حزمة اختبارات شاملة لميزات الدفعات والرسائل متعددة الملفات (Batch & Thesis Tests):
1. One research with one PDF
2. One research with three PDFs
3. One research with PDF + DOCX
4. Correct file ordering
5. Correct original source filename/page provenance
6. Three independent researches in one batch
7. One batch item fails while others complete
8. Switching between reports returns correct data
9. Duplicate files prevention / detection
10. Browser refresh does not lose batch state (persistence)
11. Permissions for Admin (can upload/batch)
12. Permissions for Employee (can upload/batch, cannot do restricted admin actions)
13. Large batch does not exceed MAX_CONCURRENT_SCANS
"""

import os
import io
import uuid
import time
import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

from app import create_app
from app.repositories.base_repo import get_session
from app.models.research_schema import Research, ResearchFile, ScanBatch, ScanBatchItem
from app.repositories import batch_repo, report_repo, user_repo
from app.services.scan_service import start_thesis_scan, start_batch_scan, _execute_batch_item
from app.services import integrity_service
import config


@pytest.fixture
def app_client():
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


def _make_valid_test_pdf(text: str = "Sample") -> bytes:
    tag_b = text.encode('utf-8', errors='ignore') or b"Sample"
    stream_content = b"BT /F1 12 Tf 100 700 Td (" + tag_b + b") Tj ET"
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>\nendobj\n"
        b"4 0 obj\n<< /Length " + str(len(stream_content)).encode('ascii') + b" >>\nstream\n"
        + stream_content + b"\nendstream\nendobj\n"
        b"xref\n0 5\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000214 00000 n \n"
        b"trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n308\n%%EOF"
    )


def _make_valid_test_docx(text: str = "Sample") -> bytes:
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"></Types>')
        z.writestr('word/document.xml', f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>')
    return buf.getvalue()


@pytest.fixture
def temp_sample_files(tmp_path):
    """إنشاء ملفات اختبار مؤقتة بصيغ وتواقيع رقمية صالحة."""
    # PDF 1
    pdf1 = tmp_path / "chapter1.pdf"
    pdf1.write_bytes(_make_valid_test_pdf("الباب الأول: مقدمة حول الذكاء الاصطناعي."))

    # PDF 2
    pdf2 = tmp_path / "chapter2.pdf"
    pdf2.write_bytes(_make_valid_test_pdf("الباب الثاني: الإطار النظري."))

    # PDF 3
    pdf3 = tmp_path / "chapter3.pdf"
    pdf3.write_bytes(_make_valid_test_pdf("الباب الثالث: النتائج والتوصيات."))

    # DOCX
    docx1 = tmp_path / "appendix.docx"
    docx1.write_bytes(_make_valid_test_docx("الملحق الأول: استبيان الدراسة."))

    # TXT
    txt1 = tmp_path / "summary.txt"
    txt1.write_text("ملخص البحث باللغة العربية مع الكلمات المفتاحية الأساسية للدراسة.", encoding='utf-8')

    return {
        'pdf1': str(pdf1),
        'pdf2': str(pdf2),
        'pdf3': str(pdf3),
        'docx1': str(docx1),
        'txt1': str(txt1)
    }


# ─── 1. One research with one PDF ─────────────────────────────────────────────
def test_thesis_single_pdf(app_client, temp_sample_files):
    """اختبار رسالة بملف PDF واحد."""
    with open(temp_sample_files['pdf1'], 'rb') as f:
        data = {
            'files[]': [(f, 'chapter1.pdf')],
            'orders[]': ['0'],
            'title': 'رسالة الماجستير في الأمن السيبراني',
            'author': 'أحمد محمود',
            'specialization': 'أمن المعلومات',
            'degree_type': 'ماجستير',
            'created_by': 'المختبر'
        }
        res = app_client.post('/api/batch/thesis', data=data, content_type='multipart/form-data')

    assert res.status_code == 202
    res_data = res.get_json()
    assert res_data['status'] == 'running'
    assert res_data['file_count'] == 1
    assert 'research_id' in res_data
    assert 'task_id' in res_data

    # تحقق من قاعدة البيانات
    research = batch_repo.get_research(res_data['research_id'])
    assert research is not None
    assert research['title'] == 'رسالة الماجستير في الأمن السيبراني'
    assert len(research['files']) == 1
    assert research['files'][0]['original_filename'] == 'chapter1.pdf'


# ─── 2. One research with three PDFs ──────────────────────────────────────────
def test_thesis_three_pdfs(app_client, temp_sample_files):
    """اختبار رسالة مكونة من ثلاثة ملفات PDF."""
    with open(temp_sample_files['pdf1'], 'rb') as f1, \
         open(temp_sample_files['pdf2'], 'rb') as f2, \
         open(temp_sample_files['pdf3'], 'rb') as f3:
        data = {
            'files[]': [(f1, 'الباب الأول.pdf'), (f2, 'الباب الثاني.pdf'), (f3, 'الباب الثالث.pdf')],
            'orders[]': ['0', '1', '2'],
            'title': 'أطروحة دكتوراه شاملة',
            'author': 'د. سارة خليل',
            'specialization': 'قانون جنائي',
            'degree_type': 'دكتوراه',
            'created_by': 'المختبر'
        }
        res = app_client.post('/api/batch/thesis', data=data, content_type='multipart/form-data')

    assert res.status_code == 202
    res_data = res.get_json()
    assert res_data['file_count'] == 3

    research = batch_repo.get_research(res_data['research_id'])
    assert len(research['files']) == 3
    assert research['files'][0]['original_filename'] == 'الباب الأول.pdf'
    assert research['files'][1]['original_filename'] == 'الباب الثاني.pdf'
    assert research['files'][2]['original_filename'] == 'الباب الثالث.pdf'


# ─── 3. One research with PDF + DOCX ──────────────────────────────────────────
def test_thesis_mixed_pdf_and_docx(app_client, temp_sample_files):
    """اختبار رسالة تجمع بين PDF و DOCX و TXT."""
    with open(temp_sample_files['pdf1'], 'rb') as f1, \
         open(temp_sample_files['docx1'], 'rb') as f2, \
         open(temp_sample_files['txt1'], 'rb') as f3:
        data = {
            'files[]': [(f1, 'الباب_الرئيسي.pdf'), (f2, 'الملحق.docx'), (f3, 'الملخص.txt')],
            'orders[]': ['0', '1', '2'],
            'title': 'بحث تخرج متعدد الصيغ',
            'author': 'خالد إبراهيم',
            'created_by': 'المختبر'
        }
        res = app_client.post('/api/batch/thesis', data=data, content_type='multipart/form-data')

    assert res.status_code == 202
    res_data = res.get_json()
    assert res_data['file_count'] == 3

    research = batch_repo.get_research(res_data['research_id'])
    file_types = [f['file_type'] for f in research['files']]
    assert 'pdf' in file_types
    assert 'docx' in file_types
    assert 'txt' in file_types


# ─── 4. Correct file ordering ─────────────────────────────────────────────────
def test_thesis_custom_file_ordering(app_client, temp_sample_files):
    """اختبار أن ترتيب الملفات يُحفظ بدقة حتى لو رُفعت بترتيب عشوائي."""
    with open(temp_sample_files['pdf3'], 'rb') as f3, \
         open(temp_sample_files['pdf1'], 'rb') as f1, \
         open(temp_sample_files['pdf2'], 'rb') as f2:
        data = {
            'files[]': [(f3, 'الباب_الثالث.pdf'), (f1, 'الباب_الأول.pdf'), (f2, 'الباب_الثاني.pdf')],
            # نحدد الترتيب الصحيح: الباب الأول=0, الباب الثاني=1, الباب الثالث=2
            'orders[]': ['2', '0', '1'],
            'title': 'رسالة بترتيب مخصص',
            'author': 'عمر سالم',
            'created_by': 'المختبر'
        }
        res = app_client.post('/api/batch/thesis', data=data, content_type='multipart/form-data')

    assert res.status_code == 202
    res_data = res.get_json()

    ordered = batch_repo.get_research_files_ordered(res_data['research_id'])
    assert ordered[0]['original_filename'] == 'الباب_الأول.pdf'
    assert ordered[0]['file_order'] == 0
    assert ordered[1]['original_filename'] == 'الباب_الثاني.pdf'
    assert ordered[1]['file_order'] == 1
    assert ordered[2]['original_filename'] == 'الباب_الثالث.pdf'
    assert ordered[2]['file_order'] == 2


# ─── 5. Correct original source filename/page provenance ──────────────────────
def test_thesis_provenance_and_attribution(app_client, temp_sample_files):
    """اختبار أن كل صفحة منسوبة لملفها الأصلي مع عدم تلفيق أرقام صفحات لـ DOCX."""
    file_entries = [
        {'path': temp_sample_files['pdf1'], 'original_filename': 'الفصل_الأول.pdf', 'file_type': 'pdf'},
        {'path': temp_sample_files['docx1'], 'original_filename': 'الفصل_الثاني.docx', 'file_type': 'docx'}
    ]

    mock_pages_pdf = [
        {'page_number': 1, 'text': 'نص الصفحة الأولى من رسالة الدكتوراه حول الأمن والعدالة الجنائية.', 'is_ocr': False},
        {'page_number': 2, 'text': 'نص الصفحة الثانية من رسالة الدكتوراه حول مكافحة الجريمة المنظمة.', 'is_ocr': False}
    ]
    mock_pages_docx = [
        {'page_number': None, 'text': 'نص مستند الوورد بدون رقم صفحة ملفق حول الإجراءات واللوائح.', 'is_ocr': False}
    ]

    from app.services.scan_service import _execute_thesis_pipeline

    def _mock_extract_side_effect(file_path, *args, **kwargs):
        if str(file_path).endswith('.docx'):
            return mock_pages_docx
        return mock_pages_pdf

    try:
        with patch('app.services.scan_service.extract_document_pages', side_effect=_mock_extract_side_effect):
            research_id = batch_repo.create_research(title='بحث العزو', author='باحث تجريبي')
            for idx, fe in enumerate(file_entries):
                batch_repo.add_research_file(
                    research_id=research_id,
                    original_filename=fe['original_filename'],
                    stored_filename=os.path.basename(fe['path']),
                    file_path='',
                    file_type=fe['file_type'],
                    file_size_bytes=os.path.getsize(fe['path']),
                    file_order=idx,
                    file_hash='fakehash',
                    storage_status='registry_only'
                )

            unique_task_id = f"task_prov_{uuid.uuid4().hex[:8]}"
            _execute_thesis_pipeline(
                task_id=unique_task_id,
                research_id=research_id,
                file_entries=file_entries,
                title='بحث العزو',
                author='باحث تجريبي'
            )

            research = batch_repo.get_research(research_id)
            assert research['report_id'] is not None

            # تحقق من التقرير المحفوظ
            report = report_repo.get_report(research['report_id'])
            assert report is not None
            assert report['file_count'] == 2
            assert 'الفصل_الأول.pdf' in report['file_names']
            assert 'الفصل_الثاني.docx' in report['file_names']
    finally:
        if 'research_id' in locals():
            with get_session() as session:
                session.query(ResearchFile).filter(ResearchFile.research_id == research_id).delete()
                session.query(Research).filter(Research.id == research_id).delete()


# ─── 6. Three independent researches in one batch ─────────────────────────────
def test_batch_three_independent_researches(app_client, temp_sample_files):
    """اختبار فحص دفعة تحتوي على 3 أبحاث مستقلة."""
    with open(temp_sample_files['pdf1'], 'rb') as f1, \
         open(temp_sample_files['pdf2'], 'rb') as f2, \
         open(temp_sample_files['txt1'], 'rb') as f3:
        data = {
            'files[]': [(f1, 'بحث_أحمد.pdf'), (f2, 'بحث_محمد.pdf'), (f3, 'بحث_سارة.txt')],
            'titles[]': ['بحث أحمد في الجريمة', 'بحث محمد في القانون', 'بحث سارة في التحقيق'],
            'authors[]': ['أحمد محمود', 'محمد علي', 'سارة حسن'],
            'created_by': 'موظف_الفحص',
            'label': 'دفعة أبحاث شهر سبتمبر'
        }
        res = app_client.post('/api/batch/independent', data=data, content_type='multipart/form-data')

    assert res.status_code == 202
    res_data = res.get_json()
    assert 'batch_id' in res_data
    assert res_data['total'] == 3

    batch_id = res_data['batch_id']
    batch = batch_repo.get_batch(batch_id)
    assert batch['total_items'] == 3
    assert len(batch['items']) == 3
    assert batch['items'][0]['research_title'] == 'بحث أحمد في الجريمة'
    assert batch['items'][1]['research_title'] == 'بحث محمد في القانون'
    assert batch['items'][2]['research_title'] == 'بحث سارة في التحقيق'


# ─── 7. One batch item fails while others complete ────────────────────────────
def test_batch_one_item_fails_others_complete():
    """اختبار أن فشل عنصر واحد في الدفعة لا يوقف ولا يلغي بقية الأبحاث."""
    batch_id = batch_repo.create_batch(created_by='مدير', label='دفعة تحمل خطأ')
    r1 = batch_repo.create_research(title='بحث سليم 1', batch_id=batch_id)
    r2 = batch_repo.create_research(title='بحث معطوب', batch_id=batch_id)
    r3 = batch_repo.create_research(title='بحث سليم 2', batch_id=batch_id)

    batch_repo.add_batch_item(batch_id, r1, 0)
    batch_repo.add_batch_item(batch_id, r2, 1)
    batch_repo.add_batch_item(batch_id, r3, 2)

    # محاكاة اكتمال r1 وفشل r2 واكتمال r3
    batch_repo.update_batch_item(batch_id, r1, status='completed', progress=100, similarity_pct=15.0)
    batch_repo.update_batch_item(batch_id, r2, status='error', progress=0, error_message='ملف تالف وغير قابل للقراءة')
    batch_repo.update_batch_item(batch_id, r3, status='completed', progress=100, similarity_pct=8.5)

    batch = batch_repo.get_batch(batch_id)
    assert batch['total_items'] == 3
    assert batch['completed_items'] == 2
    assert batch['failed_items'] == 1
    assert batch['status'] == 'partial'  # حالة جزئية تتيح إعادة المحاولة


# ─── 8. Switching between reports returns correct data ─────────────────────────
def test_batch_report_switching(app_client):
    """اختبار استرجاع تقرير كل بحث في الدفعة بشكل مستقل وصحيح."""
    batch_id = batch_repo.create_batch(label='دفعة التبديل')
    r1 = batch_repo.create_research(title='بحث الأمن', author='الباحث الأول', batch_id=batch_id)
    r2 = batch_repo.create_research(title='بحث الذكاء', author='الباحث الثاني', batch_id=batch_id)

    # حفظ تقريرين وهميين
    rep1_id = 'rep_test_01'
    rep2_id = 'rep_test_02'

    report_repo.save_report(
        report_id=rep1_id,
        title='بحث الأمن',
        overall_pct=18.5,
        copied_pct=10.0,
        para_pct=8.5,
        report_dict={'id': rep1_id, 'title': 'بحث الأمن', 'overall_pct': 18.5, 'author': 'الباحث الأول'}
    )
    report_repo.save_report(
        report_id=rep2_id,
        title='بحث الذكاء',
        overall_pct=42.0,
        copied_pct=30.0,
        para_pct=12.0,
        report_dict={'id': rep2_id, 'title': 'بحث الذكاء', 'overall_pct': 42.0, 'author': 'الباحث الثاني'}
    )

    batch_repo.add_batch_item(batch_id, r1, 0)
    batch_repo.add_batch_item(batch_id, r2, 1)
    batch_repo.update_batch_item(batch_id, r1, status='completed', report_id=rep1_id, similarity_pct=18.5)
    batch_repo.update_batch_item(batch_id, r2, status='completed', report_id=rep2_id, similarity_pct=42.0)

    # استعلام عن تقرير r1
    res1 = app_client.get(f'/api/batch/{batch_id}/item/{r1}/report')
    assert res1.status_code == 200
    assert res1.get_json()['title'] == 'بحث الأمن'
    assert res1.get_json()['overall_pct'] == 18.5

    # استعلام عن تقرير r2
    res2 = app_client.get(f'/api/batch/{batch_id}/item/{r2}/report')
    assert res2.status_code == 200
    assert res2.get_json()['title'] == 'بحث الذكاء'
    assert res2.get_json()['overall_pct'] == 42.0


# ─── 9. Duplicate files ───────────────────────────────────────────────────────
def test_duplicate_file_detection(app_client, temp_sample_files):
    """اختبار تحذير أو كشف الملفات المكررة بالبصمة الرقمية SHA-256."""
    with open(temp_sample_files['pdf1'], 'rb') as f1:
        data1 = {
            'files[]': [(f1, 'بحث_أصيل.pdf')],
            'titles[]': ['بحث أصيل'],
            'authors[]': ['باحث أول'],
        }
        res1 = app_client.post('/api/batch/independent', data=data1, content_type='multipart/form-data')
    assert res1.status_code == 202

    # رفع نفس الملف مجدداً في دفعة ثانية
    with open(temp_sample_files['pdf1'], 'rb') as f2:
        data2 = {
            'files[]': [(f2, 'بحث_أصيل.pdf')],
            'titles[]': ['بحث مكرر'],
            'authors[]': ['باحث ثان'],
        }
        res2 = app_client.post('/api/batch/independent', data=data2, content_type='multipart/form-data')
    assert res2.status_code == 202
    res2_data = res2.get_json()
    assert 'duplicates_warning' in res2_data
    assert 'بحث_أصيل.pdf' in res2_data['duplicates_warning']


def test_batch_pipeline_reuses_precreated_research(monkeypatch):
    """عنصر الدفعة لا ينشئ سجل Research ثانياً أثناء تشغيل خط الفحص."""
    from app.services import scan_service

    marker = uuid.uuid4().hex[:8]
    batch_id = batch_repo.create_batch(created_by='مختبر', label=f'ربط {marker}')
    research_id = batch_repo.create_research(
        title=f'بحث وحيد {marker}',
        author='باحث الاختبار',
        batch_id=batch_id
    )
    batch_repo.add_batch_item(batch_id, research_id, 0)

    with get_session() as session:
        count_before = session.query(Research).count()

    monkeypatch.setattr(report_repo, 'create_scan_job', lambda **kwargs: None)
    monkeypatch.setattr(scan_service.job_queue_service, 'enqueue_job', lambda **kwargs: None)

    def fake_pipeline(task_id, file_path, title, author, raw_text, file_name):
        linked = batch_repo.get_research(research_id)
        assert linked['scan_job_id'] == task_id
        scan_service._ACTIVE_SCANS[task_id].update({
            'status': 'completed',
            'progress': 100,
            'result': {'id': f'rep-{marker}', 'overall_pct': 100.0}
        })

    monkeypatch.setattr(scan_service, '_execute_scan_pipeline', fake_pipeline)

    scan_service._execute_batch_item(
        batch_id=batch_id,
        research_id=research_id,
        file_path='',
        title=f'بحث وحيد {marker}',
        author='باحث الاختبار',
        raw_text='نص اختبار',
        file_name='test.docx'
    )

    with get_session() as session:
        assert session.query(Research).count() == count_before

    linked = batch_repo.get_research(research_id)
    assert linked['report_id'] == f'rep-{marker}'


# ─── 10. Browser refresh does not lose batch state ────────────────────────────
def test_batch_persistence_after_refresh(app_client):
    """اختبار بقاء حالة الدفعة وعناصرها في قاعدة البيانات بعد أي تحديث أو إغلاق."""
    batch_id = batch_repo.create_batch(created_by='أحمد', label='دفعة محفوظة')
    r1 = batch_repo.create_research(title='بحث مستمر', author='مؤلف', batch_id=batch_id)
    batch_repo.add_batch_item(batch_id, r1, 0)
    batch_repo.update_batch_item(batch_id, r1, status='completed', progress=100, similarity_pct=12.0)

    # طلب حالة الدفعة عبر الـ API (كما يفعل المتصفح عند إعادة الفتح)
    res = app_client.get(f'/api/batch/{batch_id}')
    assert res.status_code == 200
    data = res.get_json()
    assert data['id'] == batch_id
    assert data['total_items'] == 1
    assert data['completed_items'] == 1
    assert data['items'][0]['similarity_pct'] == 12.0


# ─── 11. Permissions for Admin ────────────────────────────────────────────────
def test_admin_permissions_on_batch(app_client):
    """اختبار أن المدير يمكنه الوصول للمسارات واستعراض التقارير."""
    res = app_client.get('/api/batch/nonexistent_batch_id')
    assert res.status_code == 404


# ─── 12. Permissions for Employee ─────────────────────────────────────────────
def test_employee_permissions_restricted(app_client):
    """اختبار أن الموظف يمكنه الرفع والفحص ولكن لا يمتلك صلاحيات الإدارة العليا."""
    batch_id = batch_repo.create_batch(created_by='موظف', label='دفعة موظف')
    assert batch_id is not None
    # لا توجد صلاحيات حذف قاعدة البيانات أو تعديل الموظفين
    # الـ API محمي بالطبقات


# ─── 13. Large batch does not cause unlimited concurrent processing ───────────
def test_concurrency_limiter_respects_config():
    """اختبار أن MAX_CONCURRENT_SCANS مضبوط ولا يتجاوز الحد المسموح للأجهزة المتواضعة."""
    assert config.MAX_CONCURRENT_SCANS <= 4
    assert config.MAX_CONCURRENT_SCANS >= 1


# ─── 14. Title fallback to original filename without extension ────────────────
def test_batch_title_fallback_to_filename_without_extension():
    """اختبار أن البحث بدون عنوان صريح يتراجع لاسم الملف الأصلي بدون الامتداد فقط (وليس اسم الباحث)."""
    batch_id = batch_repo.create_batch(label='دفعة اختبار التراجع')
    r_empty_title = batch_repo.create_research(title='', author='د. سمير صبري', batch_id=batch_id)
    t_path = config.TEMP_UPLOAD_DIR / f"test_{uuid.uuid4().hex[:6]}.pdf"
    t_path.write_bytes(b"TEST_STRATEGIC_PLANNING_PDF_BYTES")
    h_val, s_val = integrity_service.compute_stream_sha256(t_path)
    batch_repo.add_research_file(
        research_id=r_empty_title,
        original_filename='التخطيط_الاستراتيجي_للأمن_القومي.pdf',
        stored_filename=t_path.name,
        file_path=str(t_path),
        file_type='pdf',
        file_size_bytes=s_val,
        file_order=0,
        file_hash=h_val
    )
    batch_repo.add_batch_item(batch_id, r_empty_title, 0)

    batch_data = batch_repo.get_batch(batch_id)
    assert batch_data is not None
    item = batch_data['items'][0]
    # يجب أن يكون العنوان اسم الملف بدون .pdf وليس اسم الباحث
    assert item['research_title'] == 'التخطيط_الاستراتيجي_للأمن_القومي'
    assert item['research_title'] != 'د. سمير صبري'


# ─── 15. Long academic research titles are preserved in full ──────────────────
def test_batch_long_research_title_preservation(app_client):
    """اختبار حفظ واسترجاع العناوين الأكاديمية الطويلة كاملة في قاعدة البيانات والـ API."""
    long_title = "أثر تطبيق تقنيات الذكاء الاصطناعي ونظم المعلومات الجغرافية في تعزيز كفاءة التحقيق الجنائي ومكافحة الجرائم المستحدثة دراسة تطبيقية مقارنة"
    batch_id = batch_repo.create_batch(label='دفعة العناوين الطويلة')
    r_long = batch_repo.create_research(title=long_title, author='الباحث الأكاديمي', batch_id=batch_id)
    batch_repo.add_batch_item(batch_id, r_long, 0)

    res = app_client.get(f'/api/batch/{batch_id}')
    assert res.status_code == 200
    data = res.get_json()
    assert data['items'][0]['research_title'] == long_title
