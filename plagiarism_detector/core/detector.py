# -*- coding: utf-8 -*-
"""
واجهة التوافق العكسي لموديول محرك الكشف (Backward Compatibility Layer).
يوجه الاستدعاءات مباشرة إلى المحرك المتطور المنظم في plagiarism_detector.reporting.report_builder
مع دعم كامل للنسخ الحرفي، إعادة الصياغة، عزو أرقام الصفحات الحقيقية، وتمييز الاقتباس الموثق.
"""

from plagiarism_detector.reporting.report_builder import (
    build_pipeline_index,
    get_pipeline_index,
    invalidate_pipeline_index,
    analyze_academic_document
)

# ثوابت التوافق القديمة
SHINGLE_SIZE = 5
JACCARD_COPY_THRESHOLD = 0.40
COSINE_PARA_THRESHOLD = 0.60
MIN_SENTENCE_WORDS = 4


def build_index() -> dict:
    """إعادة بناء فهرس المقاطع المرجعية."""
    return build_pipeline_index()


def analyze_text(raw_text: str, pages_data: list = None) -> dict:
    """تحليل بحث جديد وتوليد التقرير المفصل مع أرقام الصفحات والتوثيق."""
    return analyze_academic_document(raw_text=raw_text, pages_data=pages_data)


__all__ = [
    'build_index',
    'analyze_text',
    'build_pipeline_index',
    'get_pipeline_index',
    'invalidate_pipeline_index',
    'analyze_academic_document'
]
