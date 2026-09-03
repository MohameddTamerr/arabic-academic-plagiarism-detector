# -*- coding: utf-8 -*-
"""
اختبارات كشف الاستشهادات والتوثيق الأكاديمي واستبعاد المراجع (Citations Unit Tests).
"""

from plagiarism_detector.citations.citation_detector import detect_citation
from plagiarism_detector.citations.bibliography_detector import (
    is_bibliography_header,
    is_bibliography_entry,
    filter_bibliography_sections
)


def test_arabic_quotation_brackets():
    """كشف الاقتباس الحرفي بين علامات التنصيص العربية « »."""
    text = "وقد نص القانون صراحة على أنه «يعاقب بالحبس كل من ارتكب جريمة التزوير في المحررات الرسمية» وفقاً للمادة العاشرة."
    res = detect_citation(text)
    assert res.is_cited is True
    assert res.citation_type == 'quoted_brackets'
    assert "يعاقب بالحبس" in res.citation_detail


def test_author_year_page_citation():
    """كشف التوثيق الأكاديمي بالأقواس (المؤلف، السنة، ص. XX)."""
    text = "وتعتبر الجريمة المنظمة عابرة للحدود بطبيعتها الجغرافية (درويش، 2023، ص. 45) مما يتطلب تعاوناً دولياً."
    res = detect_citation(text)
    assert res.is_cited is True
    assert res.citation_type == 'author_year'
    assert "درويش" in res.citation_detail
    assert "2023" in res.citation_detail


def test_author_year_inline():
    """كشف صيغة المؤلف (السنة)."""
    text = "وفي هذا الصدد أكد أحمد سالم (2021) على أهمية التحول الرقمي في الإدارة."
    res = detect_citation(text)
    assert res.is_cited is True


def test_bibliography_headers_recognition():
    """التعرف على عناوين أقسام المراجع."""
    headers = [
        "المصادر والمراجع",
        "قائمة المراجع",
        "ثبت المصادر والمراجع:",
        "المراجع العربية",
        "References",
        "Bibliography"
    ]
    for h in headers:
        assert is_bibliography_header(h) is True, f"فشل التعرف على العنوان: {h}"

    assert is_bibliography_header("الفصل الأول: الإطار النظري") is False


def test_filter_bibliography_sections():
    """استبعاد المقاطع الواقعة داخل قسم المراجع من نسبة الاستلال المشبوه."""
    segments = [
        {'text': 'المقدمة وأهداف البحث العلمي وأهميته في التنمية المستدامة.'},
        {'text': 'قائمة المراجع والمصادر:'},
        {'text': '1. د. علي محمد، الجرائم الإلكترونية، دار المعارف، القاهرة، 2020.'},
        {'text': '2. د. تامر درويش، الأمن القومي الحديث، القاهرة، 2023.'}
    ]
    processed, bib_count = filter_bibliography_sections(segments)
    assert bib_count == 3  # العنوان + المرجعين
    assert processed[0]['is_bibliography'] is False
    assert processed[1]['is_bibliography'] is True
    assert processed[2]['is_bibliography'] is True
