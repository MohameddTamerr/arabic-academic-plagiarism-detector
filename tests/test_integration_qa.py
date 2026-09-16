# -*- coding: utf-8 -*-
"""
اختبارات التكامل والتحقق الشاملة للنظام (End-to-End Integration & Quality Assurance Tests):
تتحقق من سلامة خط أنابيب الكشف، إسناد الصفحات، دقة النسب الرياضية، واستبعاد المراجع الببليوغرافية.
"""

import pytest
from app.services import paper_service
from plagiarism_detector.reporting.report_builder import analyze_academic_document, invalidate_pipeline_index
from plagiarism_detector.citations.citation_detector import detect_citation
from plagiarism_detector.citations.bibliography_detector import is_bibliography_header


def test_citation_patterns_and_false_positives():
    """اختبار أنماط التوثيق المتنوعة مع التأكد من عدم تصنيف السنوات والصفحات العشوائية كتوثيق."""
    # توثيقات صحيحة
    assert detect_citation('(محمد، 2023)').is_cited is True
    assert detect_citation('(محمد، 2023، ص. 25)').is_cited is True
    assert detect_citation('(محمد أحمد، 2023، صفحة 25)').is_cited is True
    assert detect_citation('أكد محمد أحمد (2023) في دراسته').is_cited is True
    assert detect_citation('وفقاً للنموذج المقترح [1]').is_cited is True
    assert detect_citation('كما ورد سابقاً [12، ص. 5]').is_cited is True
    assert detect_citation('«نص مقتبس بدقة عالية»').is_cited is True
    assert detect_citation('"نص مقتبس بدقة عالية"').is_cited is True

    # إيجابيات كاذبة يجب أن تُرفض
    assert detect_citation('بدأت الخطة الخمسية في عام (2020) في الدولة.').is_cited is False
    assert detect_citation('بلغ الإنتاج في سنة 2023 مستويات قياسية.').is_cited is False
    assert detect_citation('تم استعراض هذا المحور في صفحة 5 من التقرير.').is_cited is False


def test_bibliography_header_recognition():
    """اختبار تمييز عناوين المراجع والتفريق بينها وبين الجمل العادية."""
    valid_headers = [
        'المراجع', 'المصادر', 'المصادر والمراجع', 'قائمة المراجع',
        'المراجع العربية', 'المراجع الأجنبية', 'References', 'Bibliography',
        '## قائمة المراجع', '1. المراجع:', 'المصادر والمراجع:'
    ]
    for h in valid_headers:
        assert is_bibliography_header(h) is True, f"Failed for header: {h}"

    invalid_headers = [
        'وفي ضوء المراجع السابقة نجد أن الأمن القومي ركيزة أساسية.',
        'تم الاعتماد على المصادر الميدانية في جمع البيانات الإحصائية.'
    ]
    for nh in invalid_headers:
        assert is_bibliography_header(nh) is False, f"False positive for: {nh}"


def test_e2e_similarity_math_and_page_limits():
    """اختبار رياضي: التأكد من أن 0 <= % <= 100 وأن النسبة المشبوهة <= النسبة الكلية."""
    # إضافة بحث مرجعي فريد
    unique_ref = "تشكل قواعد العدالة الانتقائية خطراً حقيقياً على مبادئ الدستور والنزاهة المؤسسية وسيادة القانون في المجتمع المعاصر."
    res = paper_service.import_reference_paper(
        title="العدالة الانتقائية والدستور المعاصر",
        author="د. ماهر سليم",
        raw_text=unique_ref,
        category="دستوري"
    )
    invalidate_pipeline_index()

    # فحص نص مطابق
    report = analyze_academic_document(unique_ref)

    assert 0.0 <= report['overall_pct'] <= 100.0
    assert 0.0 <= report['problematic_pct'] <= 100.0
    assert report['problematic_pct'] <= report['overall_pct'] + 1e-5
    assert report['copied_pct'] >= 80.0
    assert report['overall_pct'] >= 80.0


def test_bibliography_exclusion_from_problematic():
    """التأكد من أن فقرات قسم المراجع يتم استبعادها من الاستلال الإشكالي."""
    bib_text = (
        "المراجع والمصادر:\n"
        "1. الدسوقي، طارق، (2022)، أصول الأمن القومي والاستراتيجية، دار الفكر العربي، القاهرة.\n"
        "2. النجار، كمال، (2021)، مبادئ التنمية المستدامة والاقتصاد، دار النهضة، بيروت."
    )
    report = analyze_academic_document(bib_text)
    assert report['problematic_pct'] == 0.0
    assert report['bibliography_segments_count'] > 0


def test_identical_document_with_bibliography_is_100_percent():
    """قائمة المراجع المستبعدة لا تبقى في مقام نسبة تشابه متن مطابق حرفياً."""
    import uuid

    marker = uuid.uuid4().hex[:10]
    body = (
        f"يعالج هذا المتن الأكاديمي الفريد {marker} قواعد الملكية العامة "
        "وضمانات الأفراد في إطار سيادة القانون والرقابة القضائية المتخصصة."
    )
    full_text = (
        body
        + "\n\nالمراجع والمصادر:\n"
        + "1. سالم، محمود، (2024)، مبادئ القانون الإداري، دار المعرفة، القاهرة."
    )
    res = paper_service.import_reference_paper(
        title=f"مرجع مطابق كامل {marker}",
        author="باحث الاختبار",
        raw_text=full_text,
        category="قانون"
    )
    assert res['success'] is True
    invalidate_pipeline_index()

    report = analyze_academic_document(full_text)

    assert report['bibliography_segments_count'] > 0
    assert report['overall_pct'] == 100.0


def test_identical_submitted_reference_is_reported_as_exact_file_match():
    """A byte-identical active reference is authoritative 100%, not excluded."""
    import uuid

    marker = uuid.uuid4().hex[:10]
    body = (
        f"يفحص هذا النص الفريد {marker} استبعاد التطابق الذاتي عند إعادة رفع "
        "المستند المرجعي نفسه إلى منظومة الفحص الأكاديمي المحلية."
    )
    res = paper_service.import_reference_paper(
        title=f"مرجع اختبار الاستبعاد الذاتي {marker}",
        author="باحث الاختبار",
        raw_text=body,
        category="اختبار",
    )
    assert res['success'] is True
    invalidate_pipeline_index()

    report = analyze_academic_document(
        body,
        pages_data=[{'page_number': 1, 'text': body}],
        exact_reference_match={
            'id': res['id'],
            'reference_id': f'test-ref-{marker}',
            'title': f'مرجع اختبار التطابق الكامل {marker}',
            'author': 'باحث الاختبار',
            'file_hash': 'a' * 64,
            'segments': [{
                'segment_number': 1,
                'page_number': 1,
                'raw_text': body,
                'word_count': len(body.split()),
            }],
        },
    )

    assert report['overall_pct'] == 100.0
    assert report['problematic_pct'] == 100.0
    assert report['copied_pct'] == 100.0
    assert report['exact_file_match']['detected'] is True
    assert report['exact_file_match']['method'] == 'sha256'
    assert report['sources'][0]['source_id'] == res['id']
    assert all(seg.get('source_id') == res['id'] for seg in report['segments'])
