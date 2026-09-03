# -*- coding: utf-8 -*-
"""
واجهة التوافق العكسي لموديول استخراج النصوص (Backward Compatibility Layer).
يوجه الاستدعاءات إلى الحزمة الجديدة المنظمة plagiarism_detector.extraction.page_extractor.
"""

from plagiarism_detector.extraction.page_extractor import (
    extract_text,
    extract_document_pages,
    clean_arabic_pdf_glyphs,
    unreverse_arabic_text
)
from plagiarism_detector.extraction.ocr_engine import check_ocr_availability

__all__ = [
    'extract_text',
    'extract_document_pages',
    'clean_arabic_pdf_glyphs',
    'unreverse_arabic_text',
    'check_ocr_availability'
]
