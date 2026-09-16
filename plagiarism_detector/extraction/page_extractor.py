# -*- coding: utf-8 -*-
"""
وحدة استخراج نصوص المستندات مع الحفاظ التام على أرقام الصفحات (Page-Level Document Extractor):
- استخراج صفحة-بصفحة من ملفات PDF مع حفظ رقم الصفحة الأصلي بدقة.
- استخراج فقرات مستندات Word (.docx) و (.txt) مع وسم رقم الصفحة بـ None (غير متاح).
- دعم معالجة الحروف المعكوسة (Bidi) وتنظيف شوائب خطوط PDF العربية.
- تفعيل OCR للصفحات المصمتة ولطبقات النص العربية ذات الترميز التالف.
"""

import os
import re
import logging
import unicodedata
from pathlib import Path
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from typing import Callable, Optional

import config
from .ocr_engine import check_ocr_availability, ocr_page_pixmap

logger = logging.getLogger(__name__)

# الكلمات المعكوسة الشائعة لاكتشاف مشاكل الـ Bidi
_REVERSED_ARABIC = re.compile(r'\b(ة[ا-ي]{2,}|[ا-ي]{2,}لا|[ا-ي]{2,}ةي|هيلع|ءاكذ|ميلعت)\b')
_ARABIC_CHAR_RE = re.compile(r'[\u0600-\u06FF\uFB50-\uFDFF\uFE70-\uFEFF]')
_LATIN_CHAR_RE = re.compile(r'[a-zA-Z]')
_LEGACY_PDF_GLYPH_RE = re.compile(r'[\u0080-\u009F\u00E5\u00C5]')


def pdf_text_needs_ocr(text: str, min_words: int = 20) -> tuple[bool, str]:
    """Detect empty/scanned pages and corrupt legacy Arabic PDF text layers."""
    if not text or not text.strip():
        return True, 'empty'

    arabic_chars = len(_ARABIC_CHAR_RE.findall(text))
    replacement_chars = text.count('\uFFFD')
    control_chars = sum(
        1 for char in text
        if unicodedata.category(char) == 'Cc' and char not in '\n\r\t'
    )
    legacy_glyphs = len(_LEGACY_PDF_GLYPH_RE.findall(text))
    if arabic_chars >= 20 and (replacement_chars or control_chars or legacy_glyphs):
        return True, 'corrupt_text_layer'

    words = text.split()
    if len(words) < min_words:
        return True, 'sparse'

    return False, ''


def clean_arabic_pdf_glyphs(text: str) -> str:
    """
    تنظيف الشوائب الناتجة عن فك ترميز خطوط PDF العربية:
    - إزالة المحارف الصفرية المعطوبة.
    - تصحيح الشوائب الشهيرة مثل (امل / املم -> ال).
    - تصحيح بعض الكلمات المعكوسة شائعة الحدوث في عناوين الخطوط القديمة.
    """
    if not text:
        return ''

    text = unicodedata.normalize('NFKC', text)
    # إزالة الرموز والمحارف التحكمية غير المقروءة
    text = re.sub(r'[\uFFFD\u0000-\u0008\u000B\u000C\u000E-\u001F\u25C6\u25C7\u25A0\u25A1]', ' ', text)
    text = re.sub(r'[\u200E\u200F\u202A-\u202E\u2066-\u2069]', '', text)
    text = text.replace('\u0640', '')  # إزالة الكشيدة

    # تصحيح تراكيب ال التعريف الشائعة في الخطوط المعطوبة
    text = re.sub(r'\bاملم([ا-ي]{2,})', r'الم\1', text)
    text = re.sub(r'\bامل([ا-ي]{2,})', r'الم\1', text)
    text = re.sub(r'\bيف\b', 'في', text)
    text = re.sub(r'\bعل[»|م]\b', 'على', text)
    text = re.sub(r'\bإل[»|م]\b', 'إلى', text)

    return text


def unreverse_arabic_text(text: str) -> str:
    """
    كشف وتصحيح الكلمات العربية المعكوسة من ملفات الـ PDF القديمة مع تجنب المساس بالنصوص الإنجليزية والفرنسية.
    """
    if not text:
        return ''

    lines = text.split('\n')
    out_lines = []

    for line in lines:
        if _LATIN_CHAR_RE.search(line):
            out_lines.append(line)
            continue

        words = line.split()
        if not words:
            out_lines.append(line)
            continue

        arabic_words = [w for w in words if _ARABIC_CHAR_RE.search(w)]
        if len(arabic_words) < 3:
            out_lines.append(line)
            continue

        rev_count = sum(1 for w in arabic_words if w.startswith('ة') or w.endswith('لا') or w.startswith('ات'))
        if (rev_count / len(arabic_words)) >= 0.55:
            # ترتيب الكلمات والحروف معكوس
            fixed = []
            for w in reversed(words):
                fixed.append(w[::-1])
            out_lines.append(' '.join(fixed))
        else:
            out_lines.append(line)

    return '\n'.join(out_lines)


def extract_document_pages(
    file_path: str,
    enable_ocr: bool = True,
    progress_callback: Optional[Callable[[int, int, int], None]] = None,
) -> list[dict]:
    """
    استخراج محتوى المستند صفحة-بصفحة.
    يرجع قائمة بالقواميس:
    [
        {'page_number': 1, 'text': '...', 'is_ocr': False},
        ...
    ]
    في ملفات Word و TXT، تكون قيمة 'page_number': None
    """
    ext = os.path.splitext(file_path)[1].lower()
    pages: list[dict] = []

    if ext == '.pdf':
        pages = _extract_pages_from_pdf(
            file_path,
            enable_ocr=enable_ocr,
            progress_callback=progress_callback,
        )
    elif ext in ('.docx', '.doc'):
        pages = _extract_pages_from_docx(file_path)
    elif ext == '.txt':
        pages = _extract_pages_from_txt(file_path)
    else:
        logger.warning(f"صيغة ملف غير مدعومة للاستخراج: {ext}")

    return pages


def _notify_pdf_progress(callback, completed: int, total: int, page_number: int) -> None:
    if not callback:
        return
    try:
        callback(completed, total, page_number)
    except Exception as exc:
        logger.debug("تعذر إرسال تقدم استخراج PDF: %s", exc)


def _clean_pdf_page_result(text: str, logical_direction: bool) -> str:
    if not text:
        return ''
    text = unicodedata.normalize('NFKC', text)
    if not logical_direction:
        text = unreverse_arabic_text(text)
    return clean_arabic_pdf_glyphs(text).strip()


def alternative_pdf_text_is_usable(primary_text: str, alternative_text: str) -> bool:
    """Accept a clean alternate text layer only when it preserves enough Arabic."""
    if not alternative_text or len(alternative_text.split()) < 20:
        return False
    alternative_needs_ocr, _ = pdf_text_needs_ocr(alternative_text)
    if alternative_needs_ocr:
        return False

    primary_arabic = len(_ARABIC_CHAR_RE.findall(primary_text or ''))
    alternative_arabic = len(_ARABIC_CHAR_RE.findall(alternative_text))
    if primary_arabic < 40:
        return alternative_arabic >= 20
    return (alternative_arabic / primary_arabic) >= 0.70


def _ocr_pdf_pixmap(pixmap, original_text: str, original_word_count: int, languages: str) -> tuple[str, bool]:
    """OCR worker for one already-rendered page, returning safe fallback text."""
    try:
        ocr_text = ocr_page_pixmap(pixmap, languages=languages)
        minimum_words = 4 if original_word_count < 20 else max(8, int(original_word_count * 0.25))
        if ocr_text and len(ocr_text.split()) >= minimum_words:
            return _clean_pdf_page_result(ocr_text, True), True
    except Exception as exc:
        logger.debug("فشل OCR لإحدى صفحات PDF: %s", exc)
    return _clean_pdf_page_result(original_text, False), False


def _extract_pages_from_pdf(
    path: str,
    enable_ocr: bool = True,
    progress_callback: Optional[Callable[[int, int, int], None]] = None,
) -> list[dict]:
    """استخراج PDF بصفحات OCR متوازية ومحدودة الذاكرة مع حفظ الترتيب."""
    ocr_status = check_ocr_availability() if enable_ocr else {'available': False}

    # المحاولة الأولى: PyMuPDF (fitz)
    try:
        import fitz
        with fitz.open(path) as doc:
            total_pages = len(doc)
            pages: list[Optional[dict]] = [None] * total_pages
            completed = 0
            worker_count = min(
                max(1, int(getattr(config, 'PDF_OCR_WORKERS', 2))),
                max(1, int(getattr(config, 'MAX_CONCURRENT_OCR_JOBS', 2))),
            )
            dpi = int(getattr(config, 'PDF_OCR_DPI', 220))
            max_pending = max(2, worker_count * 2)
            pending = {}
            alternate_reader = None
            alternate_reader_failed = False

            def collect(done_futures) -> None:
                nonlocal completed
                for future in done_futures:
                    page_idx, page_num = pending.pop(future)
                    try:
                        page_text, is_ocr = future.result()
                    except Exception as exc:
                        logger.warning("فشل عامل OCR للصفحة %s: %s", page_num, exc)
                        page_text, is_ocr = '', False
                    pages[page_idx] = {
                        'page_number': page_num,
                        'text': page_text,
                        'is_ocr': is_ocr,
                        'extraction_engine': 'tesseract' if is_ocr else 'pymupdf',
                    }
                    completed += 1
                    _notify_pdf_progress(progress_callback, completed, total_pages, page_num)

            with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix='pdf-ocr') as executor:
                for idx, page in enumerate(doc):
                    page_num = idx + 1
                    text = page.get_text('text') or ''
                    words = text.split()
                    needs_ocr, ocr_reason = pdf_text_needs_ocr(text)

                    # A second PDF parser can often recover a clean logical Arabic
                    # text layer even when PyMuPDF exposes legacy control glyphs.
                    # This avoids expensive OCR on most born-digital pages.
                    if needs_ocr and not alternate_reader_failed:
                        if alternate_reader is None:
                            try:
                                from pypdf import PdfReader
                                alternate_reader = PdfReader(path)
                            except Exception as exc:
                                logger.warning("تعذر فتح طبقة النص البديلة: %s", exc)
                                alternate_reader_failed = True
                        try:
                            if alternate_reader is None:
                                raise RuntimeError('alternate PDF reader is unavailable')
                            alternate_text = alternate_reader.pages[idx].extract_text() or ''
                            if alternative_pdf_text_is_usable(text, alternate_text):
                                pages[idx] = {
                                    'page_number': page_num,
                                    'text': _clean_pdf_page_result(alternate_text, True),
                                    'is_ocr': False,
                                    'extraction_engine': 'pypdf',
                                }
                                completed += 1
                                _notify_pdf_progress(progress_callback, completed, total_pages, page_num)
                                continue
                        except Exception as exc:
                            logger.debug("تعذر استخراج طبقة النص البديلة للصفحة %s: %s", page_num, exc)

                    can_ocr = (
                        needs_ocr
                        and enable_ocr
                        and ocr_status.get('available')
                        and ocr_status.get('has_arabic')
                    )

                    if can_ocr:
                        logger.info(
                            "الصفحة %s تحتاج OCR (%s، %s كلمة) بدقة %s DPI...",
                            page_num, ocr_reason, len(words), dpi,
                        )
                        pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY, alpha=False)
                        arabic_count = len(_ARABIC_CHAR_RE.findall(text))
                        latin_count = len(_LATIN_CHAR_RE.findall(text))
                        has_substantial_latin = latin_count >= 40 or latin_count >= (arabic_count * 0.20)
                        languages = 'ara+eng' if has_substantial_latin else 'ara'
                        future = executor.submit(
                            _ocr_pdf_pixmap, pix, text, len(words), languages
                        )
                        pending[future] = (idx, page_num)

                        if len(pending) >= max_pending:
                            done, _ = wait(tuple(pending), return_when=FIRST_COMPLETED)
                            collect(done)
                    else:
                        pages[idx] = {
                            'page_number': page_num,
                            'text': _clean_pdf_page_result(text, False),
                            'is_ocr': False,
                            'extraction_engine': 'pymupdf',
                        }
                        completed += 1
                        _notify_pdf_progress(progress_callback, completed, total_pages, page_num)

                while pending:
                    done, _ = wait(tuple(pending), return_when=FIRST_COMPLETED)
                    collect(done)

            return [page for page in pages if page is not None]
    except Exception as e:
        logger.warning(f"تعذر استخراج PDF بـ PyMuPDF: {e}. جاري استخدام pdfplumber...")

    # المحاولة البديلة: pdfplumber
    pages = []
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            total_pages = len(pdf.pages)
            for idx, p in enumerate(pdf.pages):
                page_num = idx + 1
                t = p.extract_text() or ''
                if t:
                    t = unicodedata.normalize('NFKC', t)
                    t = unreverse_arabic_text(t)
                    t = clean_arabic_pdf_glyphs(t)
                pages.append({
                    'page_number': page_num,
                    'text': t.strip(),
                    'is_ocr': False
                })
                _notify_pdf_progress(progress_callback, idx + 1, total_pages, page_num)
        return pages
    except Exception as e2:
        logger.error(f"فشل استخراج ملف PDF بالكامل: {e2}")
        return []


def _extract_pages_from_docx(path: str) -> list[dict]:
    """استخراج نصوص Word مع التوثيق الصريح بأن رقم الصفحة غير متاح."""
    try:
        import docx
        doc = docx.Document(path)
        full_paragraphs = []
        for p in doc.paragraphs:
            if p.text and p.text.strip():
                full_paragraphs.append(clean_arabic_pdf_glyphs(p.text.strip()))

        # استخراج نصوص الجداول أيضاً
        for tbl in doc.tables:
            for row in tbl.rows:
                row_txt = [c.text.strip() for c in row.cells if c.text.strip()]
                if row_txt:
                    full_paragraphs.append(' | '.join(row_txt))

        joined = '\n\n'.join(full_paragraphs)
        return [{
            'page_number': None,  # غير متاح لملفات Word
            'text': joined,
            'is_ocr': False
        }]
    except Exception as e:
        logger.error(f"فشل استخراج ملف DOCX: {e}")
        return []


def _extract_pages_from_txt(path: str) -> list[dict]:
    """استخراج النصوص العادية بترميز UTF-8 القياسي أو Windows-1256 العربي."""
    try:
        for enc in ['utf-8', 'utf-8-sig', 'windows-1256']:
            try:
                with open(path, 'r', encoding=enc) as f:
                    text = f.read()
                return [{
                    'page_number': None,
                    'text': clean_arabic_pdf_glyphs(text),
                    'is_ocr': False
                }]
            except UnicodeDecodeError:
                continue
    except Exception as e:
        logger.error(f"فشل استخراج ملف TXT: {e}")
    return []


def extract_text(file_path: str) -> str:
    """
    دالة للتوافق العكسي الكامل مع المستدعين القدامى: ترجع النص الكامل للمستند كسلسلة نصية واحدة.
    """
    pages = extract_document_pages(file_path, enable_ocr=False)
    return '\n\n'.join(p['text'] for p in pages if p['text'])
