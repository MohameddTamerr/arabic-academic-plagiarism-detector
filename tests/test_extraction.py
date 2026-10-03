# -*- coding: utf-8 -*-
"""
اختبارات استخراج النصوص وحفظ أرقام الصفحات و OCR المشروط (Extraction Unit Tests).
"""

import tempfile
import os
import config
from plagiarism_detector.extraction.page_extractor import (
    extract_document_pages,
    clean_arabic_pdf_glyphs,
    unreverse_arabic_text,
    pdf_text_needs_ocr,
    alternative_pdf_text_is_usable,
    merge_native_and_image_ocr_text,
    pdf_text_quality_score,
    native_pdf_text_is_sufficient,
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


def test_adaptive_ocr_concurrency_protects_weak_devices_and_scales_up():
    assert config._detect_safe_ocr_concurrency(cpu_count=2, memory_gb=3.0) == 1
    assert config._detect_safe_ocr_concurrency(cpu_count=4, memory_gb=6.0) == 2
    assert config._detect_safe_ocr_concurrency(cpu_count=8, memory_gb=12.0) == 3
    assert config._detect_safe_ocr_concurrency(cpu_count=16, memory_gb=32.0) == 4


def test_identical_page_uses_persistent_ocr_cache(tmp_path, monkeypatch):
    from PIL import Image
    from plagiarism_detector.extraction import ocr_engine

    class DummyLock:
        def __init__(self, *args, **kwargs):
            pass

        def acquire(self, *args, **kwargs):
            return True

        def release(self):
            pass

    calls = {'count': 0}

    def fake_image_to_string(*args, **kwargs):
        calls['count'] += 1
        return 'نص عربي مستخرج بجودة ثابتة'

    monkeypatch.setattr(config, 'OCR_CACHE_ENABLED', True)
    monkeypatch.setattr(config, 'OCR_CACHE_DIR', tmp_path / 'ocr-cache')
    monkeypatch.setattr(
        ocr_engine,
        'check_ocr_availability',
        lambda: {
            'available': True,
            'has_arabic': True,
            'cmd_path': 'tesseract',
            'tessdata_path': str(tmp_path),
        },
    )
    monkeypatch.setattr(ocr_engine, 'CrossProcessOcrLock', DummyLock)
    monkeypatch.setattr('pytesseract.image_to_string', fake_image_to_string)

    image = Image.new('L', (120, 80), color=255)
    first = ocr_engine.ocr_page_pixmap(image)
    second = ocr_engine.ocr_page_pixmap(image)

    assert first == second
    assert calls['count'] == 1
    assert len(list((tmp_path / 'ocr-cache').glob('*.json'))) == 1


def test_corrupt_legacy_arabic_text_layer_requires_ocr():
    corrupted = "\ufffd\x1b الدراساتå الأمنية والقانونية والعلوم العربية المستخرجة من طبقة نص قديمة غير سليمة إطلاقاً"
    needs_ocr, reason = pdf_text_needs_ocr(corrupted)
    assert needs_ocr is True
    assert reason == 'corrupt_text_layer'


def test_corrupt_english_control_glyph_layer_requires_ocr():
    corrupted = ("\x11\x18\x0e\x06 broken encoded English slide content " * 12)
    needs_ocr, reason = pdf_text_needs_ocr(corrupted)
    assert needs_ocr is True
    assert reason == 'corrupt_text_layer'


def test_image_ocr_text_is_merged_without_repeating_native_text():
    native = "Executive Summary\nThis native sentence is already searchable."
    ocr = "Executive Summary\nThis native sentence is already searchable.\nINSTANT Software\nنص داخل صورة"
    merged, used_ocr = merge_native_and_image_ocr_text(native, ocr)

    assert used_ocr is True
    assert merged.count("Executive Summary") == 1
    assert "INSTANT Software" in merged
    assert "نص داخل صورة" in merged


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


def test_identical_pdf_reuses_full_extraction_cache(tmp_path, monkeypatch):
    import fitz
    from plagiarism_detector.extraction import page_extractor

    pdf_path = tmp_path / 'cached-document.pdf'
    document = fitz.open()
    document.new_page().insert_text(
        (72, 72),
        'Searchable academic document page with enough stable English words for extraction cache testing',
    )
    document.save(pdf_path)
    document.close()

    cache_dir = tmp_path / 'pdf-extraction-cache'
    monkeypatch.setattr(config, 'PDF_EXTRACTION_CACHE_ENABLED', True)
    monkeypatch.setattr(config, 'PDF_EXTRACTION_CACHE_DIR', cache_dir)

    first = page_extractor.extract_document_pages(str(pdf_path), enable_ocr=False)
    assert len(first) == 1
    assert len(list(cache_dir.glob('*.json'))) == 1

    def fail_if_extracted_again(*args, **kwargs):
        raise AssertionError('A byte-identical PDF must reuse the full extraction cache')

    monkeypatch.setattr(page_extractor, '_extract_pages_from_pdf', fail_if_extracted_again)
    updates = []
    second = page_extractor.extract_document_pages(
        str(pdf_path),
        enable_ocr=False,
        progress_callback=lambda done, total, page: updates.append((done, total, page)),
    )

    assert second == first
    assert updates == [(1, 1, 1)]


def test_pdf_extraction_cache_invalidates_when_file_changes(tmp_path, monkeypatch):
    import fitz
    from plagiarism_detector.extraction import page_extractor

    pdf_path = tmp_path / 'changing-document.pdf'
    cache_dir = tmp_path / 'pdf-extraction-cache'
    monkeypatch.setattr(config, 'PDF_EXTRACTION_CACHE_ENABLED', True)
    monkeypatch.setattr(config, 'PDF_EXTRACTION_CACHE_DIR', cache_dir)

    first_document = fitz.open()
    first_document.new_page().insert_text((72, 72), 'First document content for cache identity validation')
    first_document.save(pdf_path)
    first_document.close()
    first = page_extractor.extract_document_pages(str(pdf_path), enable_ocr=False)

    pdf_path.unlink()
    second_document = fitz.open()
    second_document.new_page().insert_text((72, 72), 'Second and different document content for cache identity validation')
    second_document.save(pdf_path)
    second_document.close()
    second = page_extractor.extract_document_pages(str(pdf_path), enable_ocr=False)

    assert first != second
    assert len(list(cache_dir.glob('*.json'))) == 2


def test_docx_uses_rendered_pdf_pages_when_preview_is_available(tmp_path, monkeypatch):
    import fitz
    from plagiarism_detector.extraction import page_extractor

    docx_path = tmp_path / 'page-aware.docx'
    docx_path.write_bytes(b'PK\x03\x04-test')
    preview_path = tmp_path / 'page-aware.pdf'
    document = fitz.open()
    document.new_page().insert_text((72, 72), 'First rendered Word page with searchable content')
    document.new_page().insert_text((72, 72), 'Second rendered Word page with searchable content')
    document.save(preview_path)
    document.close()

    monkeypatch.setattr(
        'app.services.document_preview_service.ensure_pdf_preview',
        lambda _path: preview_path,
    )

    pages = page_extractor.extract_document_pages(str(docx_path), enable_ocr=False)

    assert [page['page_number'] for page in pages] == [1, 2]
    assert 'First rendered Word page' in pages[0]['text']
    assert 'Second rendered Word page' in pages[1]['text']


def _build_test_pdf_with_image(pdf_path, text: str, large_image: bool = True):
    import io
    from PIL import Image
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    if large_image:
        img = Image.new('RGB', (200, 200), color=(128, 128, 128))
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        page.insert_image(fitz.Rect(50, 50, 400, 400), stream=buf.getvalue())
    if text:
        page.insert_textbox(fitz.Rect(50, 420, 550, 800), text)
    doc.save(pdf_path)
    doc.close()


def test_dense_clean_arabic_text_is_sufficient():
    clean_text = (
        "تعتبر معالجة اللغات الطبيعية فرعاً حيوياً من فروع الذكاء الاصطناعي "
        "التي تهدف إلى فهم وتحليل وتوليد النصوص اللغوية بدقة متناهية. "
        "وتسهم هذه التقنيات المتقدمة في فحص الأوراق العلمية وكشف الانتحال الأكاديمي "
        "في مختلف الجامعات والمؤسسات البحثية مع الحفاظ على أعلى معايير الجودة العلمية."
    )
    score = pdf_text_quality_score(clean_text)
    assert score >= config.PDF_NATIVE_TEXT_MIN_QUALITY
    assert native_pdf_text_is_sufficient(clean_text) is True


def test_fragmented_arabic_remains_insufficient():
    fragmented_text = "ا ل د ر ا س ة ا ل ت ط ب ي ق ي ة ل ل ذ ك ا ء ا ل ا ص ط ن ا ع ي ف ي ك ش ف ا ل ا ن ت ح ا ل"
    score = pdf_text_quality_score(fragmented_text)
    assert score < config.PDF_NATIVE_TEXT_MIN_QUALITY
    assert native_pdf_text_is_sufficient(fragmented_text) is False


def test_sparse_arabic_remains_insufficient():
    sparse_text = "شكل رقم 1: رسم بياني توضيحي"
    assert native_pdf_text_is_sufficient(sparse_text) is False


def test_corrupt_arabic_and_control_glyphs_require_ocr():
    corrupt_text = "\ufffd\x1b دراسات أمنية غير سليمة إطلاقاً \x00 " * 15
    needs_ocr, reason = pdf_text_needs_ocr(corrupt_text)
    assert needs_ocr is True
    assert reason == 'corrupt_text_layer'
    assert native_pdf_text_is_sufficient(corrupt_text) is False


def test_simulated_large_image_page_with_dense_searchable_text_skips_ocr(tmp_path, monkeypatch):
    from plagiarism_detector.extraction import page_extractor

    pdf_path = tmp_path / 'smart_skip.pdf'
    dense_text = (
        "This comprehensive scientific investigation evaluates machine learning algorithms "
        "applied to natural language processing and modern academic integrity systems. "
        "Our empirical results demonstrate substantial performance improvements across multiple "
        "evaluation benchmarks in higher education research."
    )
    _build_test_pdf_with_image(pdf_path, dense_text, large_image=True)

    ocr_calls = []

    def fake_ocr_worker(pix, orig_text, orig_words, langs, merge):
        ocr_calls.append(orig_text)
        return 'Fake OCR text', True

    monkeypatch.setattr(config, 'SMART_PDF_OCR_ENABLED', True)
    monkeypatch.setattr(
        page_extractor,
        'check_ocr_availability',
        lambda: {'available': True, 'has_arabic': True},
    )
    monkeypatch.setattr(page_extractor, '_ocr_pdf_pixmap', fake_ocr_worker)

    pages = page_extractor.extract_document_pages(str(pdf_path), enable_ocr=True)

    assert len(pages) == 1
    assert len(ocr_calls) == 0, "Smart OCR should have skipped full-page OCR for dense clean text"
    assert pages[0]['is_ocr'] is False
    assert pages[0]['extraction_engine'] == 'pymupdf'
    assert "scientific investigation evaluates" in pages[0]['text']


def test_large_image_page_with_insufficient_text_calls_ocr(tmp_path, monkeypatch):
    from plagiarism_detector.extraction import page_extractor

    pdf_path = tmp_path / 'insufficient_text.pdf'
    sparse_caption = "Figure 1: Chart."
    _build_test_pdf_with_image(pdf_path, sparse_caption, large_image=True)

    ocr_calls = []

    def fake_ocr_worker(pix, orig_text, orig_words, langs, merge):
        ocr_calls.append(orig_text)
        return 'Extracted OCR diagram content', True

    monkeypatch.setattr(config, 'SMART_PDF_OCR_ENABLED', True)
    monkeypatch.setattr(
        page_extractor,
        'check_ocr_availability',
        lambda: {'available': True, 'has_arabic': True},
    )
    monkeypatch.setattr(page_extractor, '_ocr_pdf_pixmap', fake_ocr_worker)

    pages = page_extractor.extract_document_pages(str(pdf_path), enable_ocr=True)

    assert len(pages) == 1
    assert len(ocr_calls) == 1, "Sparse text with large image must still trigger OCR"
    assert pages[0]['is_ocr'] is True
    assert 'Extracted OCR diagram content' in pages[0]['text']


def test_smart_ocr_disabled_preserves_legacy_behavior(tmp_path, monkeypatch):
    from plagiarism_detector.extraction import page_extractor

    pdf_path = tmp_path / 'legacy_ocr.pdf'
    dense_text = (
        "This comprehensive scientific investigation evaluates machine learning algorithms "
        "applied to natural language processing and modern academic integrity systems. "
        "Our empirical results demonstrate substantial performance improvements across multiple "
        "evaluation benchmarks in higher education research."
    )
    _build_test_pdf_with_image(pdf_path, dense_text, large_image=True)

    ocr_calls = []

    def fake_ocr_worker(pix, orig_text, orig_words, langs, merge):
        ocr_calls.append(orig_text)
        return 'Merged legacy OCR text', True

    monkeypatch.setattr(config, 'SMART_PDF_OCR_ENABLED', False)
    monkeypatch.setattr(
        page_extractor,
        'check_ocr_availability',
        lambda: {'available': True, 'has_arabic': True},
    )
    monkeypatch.setattr(page_extractor, '_ocr_pdf_pixmap', fake_ocr_worker)

    pages = page_extractor.extract_document_pages(str(pdf_path), enable_ocr=True)

    assert len(pages) == 1
    assert len(ocr_calls) == 1, "Disabling SMART_PDF_OCR_ENABLED must preserve legacy OCR trigger"
    assert pages[0]['is_ocr'] is True
