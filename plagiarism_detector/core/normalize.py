# -*- coding: utf-8 -*-
"""
واجهة التوافق العكسي لموديول التطبيع العربي (Backward Compatibility Layer).
يوجه الاستدعاءات إلى plagiarism_detector.preprocessing.normalizer و cheating_detector.
"""

from plagiarism_detector.preprocessing.normalizer import (
    normalize_light,
    normalize_aggressive,
    split_sentences,
    get_shingles
)
from plagiarism_detector.preprocessing.cheating_detector import (
    detect_cheating_manipulation,
    clean_cheating_text
)

# للتوافق القديم: دالة normalize_arabic الافتراضية
def normalize_arabic(text: str) -> str:
    """الدالة القديمة: تستخدم التطبيع الخفيف للمقارنات العامة."""
    return normalize_light(text)

def clean_arabic_display_text(text: str) -> str:
    """تنظيف العرض."""
    return normalize_light(text)

__all__ = [
    'normalize_arabic',
    'normalize_light',
    'normalize_aggressive',
    'clean_arabic_display_text',
    'split_sentences',
    'get_shingles',
    'detect_cheating_manipulation',
    'clean_cheating_text'
]
