# -*- coding: utf-8 -*-
"""
اختبارات استخراج النصوص وحفظ أرقام الصفحات و OCR المشروط (Extraction Unit Tests).
"""

import tempfile
import os
from plagiarism_detector.extraction.page_extractor import (
    extract_document_pages,
    clean_arabic_pdf_glyphs,
    unreverse_arabic_text
)
from plagiarism_detector.extraction.ocr_engine import check_ocr_availability


def test_clean_arabic_pdf_glyphs():
    """تنظيف شوائب الحروف في خطوط الـ PDF."""
    corrupted = "املعرفه وتطور املمجله يف القانون"
    cleaned = clean_arabic_pdf_glyphs(corrupted)
    assert "المعرفه" in cleaned
    assert "المجله" in cleaned
    assert "في" in cleaned


def test_unreverse_arabic_bidi():
    """تصحيح اتجاه الحروف المعكوسة الناتجة عن ملفات الـ PDF القديمة."""
    reversed_line = "ميلعتلا تاقيبطت يف ةثيدحلا ةينقتلا"
    fixed = unreverse_arabic_text(reversed_line)
    assert "التقنية" in fixed or "الحديثة" in fixed or "تطبيقات" in fixed or "التعليم" in fixed


def test_extract_txt_page_number_unavailable():
    """التأكد من أن ملفات النصوص غير المقسمة لصفحات ترجع page_number = None دون اختلاق أرقام وهمية."""
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', suffix='.txt', delete=False) as f:
        f.write("هذا محتوى ملف نصي تجريبي لا يحتوي على تقسيم صفحات طبيعي.")
        temp_path = f.name

    try:
        pages = extract_document_pages(temp_path)
        assert len(pages) == 1
        assert pages[0]['page_number'] is None, "يجب أن يكون رقم الصفحة None لملفات TXT"
        assert "ملف نصي تجريبي" in pages[0]['text']
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_ocr_availability_check():
    """فحص جاهزية محرك Tesseract محلياً دون التسبب في انهيار التطبيق."""
    res = check_ocr_availability()
    assert isinstance(res, dict)
    assert 'available' in res
    assert 'has_arabic' in res
