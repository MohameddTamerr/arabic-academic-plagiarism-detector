# -*- coding: utf-8 -*-
"""
منطق الصفحات المسموحة وحد الـ 5 صفحات (Allowed Pages & Source Allocation Logic):
- حساب عدد الكلمات المقتبسة من كل مرجع مصدر.
- حساب عدد الصفحات التقديرية (Estimated Equivalent Pages) بناءً على معدل الكلمات لكل صفحة (الافتراضي 250 كلمة).
- جمع أرقام الصفحات المصدرية الحقيقية التي ورد فيها التطابق (PDF Pages).
- إطلاق تنبيه أكاديمي واضح في حال تجاوز الاقتباس من مرجع واحد الحد الأقصى المصرح به.
"""

from typing import Optional


def compute_source_allowance(
    source_id: int,
    source_title: str,
    source_author: str,
    matched_words: int,
    matched_pages_set: set[Optional[int]],
    words_per_page: int = 250,
    max_allowed_pages: float = 5.0
) -> dict:
    """
    حساب تفاصيل الاقتباس من مرجع محدد مع الصفحات التقديرية والصفحات المصدرية الفعلية.
    """
    estimated_pages = round(matched_words / max(words_per_page, 50), 2)
    is_exceeded = estimated_pages > max_allowed_pages

    # تصفية أرقام الصفحات الحقيقية
    real_pages = sorted([p for p in matched_pages_set if p is not None])
    has_unavailable = any(p is None for p in matched_pages_set)

    pages_str_list = [f"ص. {p}" for p in real_pages]
    if has_unavailable:
        pages_str_list.append("صفحات غير مرقمة (ملف Word/نص)")

    pages_display = "، ".join(pages_str_list) if pages_str_list else "غير متاح"

    return {
        'source_id': source_id,
        'title': source_title,
        'author': source_author or 'غير محدد',
        'matched_words': matched_words,
        'words': matched_words,  # للتوافق القديم
        'estimated_pages': estimated_pages,
        'pages': estimated_pages,  # للتوافق القديم
        'is_estimated_label': '(تقديري)',
        'max_allowed_pages': max_allowed_pages,
        'is_limit_exceeded': is_exceeded,
        'matched_source_pages': real_pages,
        'matched_pages_display': pages_display,
        'alert_message': (
            f"تجاوز الحد المسموح للاقتباس من مرجع واحد! تم اقتباس ما يعادل {estimated_pages} صفحة تقريباً "
            f"من المرجع: «{source_title}» (الحد الأقصى المصرح به: {max_allowed_pages} صفحات)."
            if is_exceeded else ''
        )
    }
