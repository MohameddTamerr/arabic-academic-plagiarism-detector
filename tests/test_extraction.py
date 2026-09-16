# -*- coding: utf-8 -*-
"""
اختبارات استخراج النصوص وحفظ أرقام الصفحات و OCR المشروط (Extraction Unit Tests).
"""

import tempfile
import os
from plagiarism_detector.extraction.page_extractor import (
    extract_document_pages,
    clean_arabic_pdf_glyphs,
    unreverse_arabic_text,
    pdf_text_needs_ocr,
    alternative_pdf_text_is_usable,
)
from plagiarism_detector.extraction.ocr_engine import check_ocr_availability, find_tessdata_dir


def test_clean_arabic_pdf_glyphs():
    """تنظيف شوائب الحروف في خطوط الـ PDF."""
    corrupted = "املعرفه وتطور املمجله يف القانون"
    cleaned = clean_arabic_pdf_glyphs(corrupted)
    assert "المعرفه" in cleaned
    assert "المجله" in cleaned
    assert "في" in cleaned


def test_clean_arabic_pdf_glyphs_removes_bidi_controls():
    cleaned = clean_arabic_pdf_glyphs("هذا\u200f نص\u2067 عربي\u2069 سليم")
    assert cleaned == "هذا نص عربي سليم"


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


def test_corrupt_legacy_arabic_text_layer_requires_ocr():
    corrupted = "\ufffd\x1b الدراساتå الأمنية والقانونية والعلوم العربية المستخرجة من طبقة نص قديمة غير سليمة إطلاقاً"
    needs_ocr, reason = pdf_text_needs_ocr(corrupted)
    assert needs_ocr is True
    assert reason == 'corrupt_text_layer'


def test_clean_arabic_text_layer_does_not_require_ocr():
    clean = "هذا نص عربي سليم يحتوي على كلمات واضحة ومتتابعة ويصلح للاستخراج المباشر دون تشغيل التعرف الضوئي على الحروف في المستند"
    needs_ocr, reason = pdf_text_needs_ocr(clean)
    assert needs_ocr is False
    assert reason == ''


def test_bundled_arabic_and_english_ocr_models_exist():
    tessdata_dir = find_tessdata_dir()
    assert tessdata_dir is not None
    assert (tessdata_dir / 'ara.traineddata').is_file()
    assert (tessdata_dir / 'eng.traineddata').is_file()


def test_clean_alternative_pdf_layer_skips_expensive_ocr():
    primary = ("\ufffd\x1b" + "نص عربي أكاديمي تالف الترميز " * 30)
    alternative = "نص عربي أكاديمي سليم وواضح صالح للتحليل المباشر دون تعرف ضوئي " * 30
    assert alternative_pdf_text_is_usable(primary, alternative) is True


def test_incomplete_alternative_pdf_layer_keeps_ocr_fallback():
    primary = "نص عربي أكاديمي طويل ومتكامل لكنه يحتوي على طبقة ترميز تالفة \x1b " * 30
    alternative = "عنوان قصير ناقص"
    assert alternative_pdf_text_is_usable(primary, alternative) is False


def test_pdf_progress_callback_reports_all_pages(tmp_path):
    import fitz

    pdf_path = tmp_path / 'progress.pdf'
    doc = fitz.open()
    for idx in range(3):
        page = doc.new_page()
        page.insert_text((72, 72), f'Plain English page {idx + 1} with enough words to avoid OCR processing entirely')
    doc.save(pdf_path)
    doc.close()

    updates = []
    pages = extract_document_pages(
        str(pdf_path),
        enable_ocr=False,
        progress_callback=lambda done, total, page: updates.append((done, total, page)),
    )

    assert len(pages) == 3
    assert updates[-1][:2] == (3, 3)
