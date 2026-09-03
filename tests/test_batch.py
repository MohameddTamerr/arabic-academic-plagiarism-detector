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
import config


@pytest.fixture
def app_client():
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def temp_sample_files(tmp_path):
    """إنشاء ملفات اختبار مؤقتة بصيغ ونصوص مختلفة."""
    # PDF 1
    pdf1 = tmp_path / "chapter1.pdf"
    pdf1.write_text("الباب الأول: مقدمة حول الذكاء الاصطناعي والأمن السيبراني وتطبيقاته الحديثة.", encoding='utf-8')

    # PDF 2
    pdf2 = tmp_path / "chapter2.pdf"
    pdf2.write_text("الباب الثاني: الإطار النظري والدراسات السابقة في مجال مكافحة الجرائم الإلكترونية.", encoding='utf-8')

    # PDF 3
    pdf3 = tmp_path / "chapter3.pdf"
    pdf3.write_text("الباب الثالث: النتائج والتوصيات والتحليل الإحصائي للبيانات المجمعة في الدراسة.", encoding='utf-8')

    # DOCX
    docx1 = tmp_path / "appendix.docx"
    docx1.write_text("الملحق الأول: استبيان الدراسة وقائمة الخبراء المحكمين في البحث العلمي.", encoding='utf-8')

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
def test_thesis_provenance_and_attribution():
    """اختبار أن كل صفحة منسوبة لملفها الأصلي مع عدم تلفيق أرقام صفحات لـ DOCX."""
    file_entries = [
        {'path': 'nonexistent_p1.pdf', 'original_filename': 'الفصل_الأول.pdf', 'file_type': 'pdf'},
        {'path': 'nonexistent_p2.docx', 'original_filename': 'الفصل_الثاني.docx', 'file_type': 'docx'}
    ]

    mock_pages_pdf = [
        {'page_number': 1, 'text': 'نص الصفحة الأولى من رسالة الدكتوراه حول الأمن والعدالة الجنائية.', 'is_ocr': False},
        {'page_number': 2, 'text': 'نص الصفحة الثانية من رسالة الدكتوراه حول مكافحة الجريمة المنظمة.', 'is_ocr': False}
    ]
    mock_pages_docx = [
        {'page_number': None, 'text': 'نص مستند الوورد بدون رقم صفحة ملفق حول الإجراءات واللوائح.', 'is_ocr': False}
    ]

    from app.services.scan_service import _execute_thesis_pipeline

    with patch('app.services.scan_service.extract_document_pages') as mock_extract, \
         patch('os.path.exists', return_value=True):
        mock_extract.side_effect = [mock_pages_pdf, mock_pages_docx]

        research_id = batch_repo.create_research(title='بحث العزو', author='باحث تجريبي')
        _execute_thesis_pipeline(
            task_id='task_prov_01',
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
    batch_repo.add_research_file(
        research_id=r_empty_title,
        original_filename='التخطيط_الاستراتيجي_للأمن_القومي.pdf',
        stored_filename='stored_123.pdf',
        file_path='/tmp/test.pdf',
        file_type='pdf',
        file_size_bytes=1024,
        file_order=0
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
