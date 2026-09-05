# -*- coding: utf-8 -*-
"""
كاشف الاقتباسات الموثقة والاستشهادات الأكاديمية المحسن (EXP-04 Refined Citation Detector):
- يدعم نمطين محكومين براية الإعدادات (Feature Flag):
  1. نمط الاستشهاد المنقح (Refined Mode): يستبعد التواريخ المعزولة وأرقام المواد القانونية واللوائح الإدارية، ويدعم توثيق المؤلفين المتعددين بنظام APA.
  2. نمط خط الأساس (Baseline Mode): قواعد الكشف الأصلية للتوافق وإمكانية الرجوع الفوري لـ RC1.
- يحافظ على الفصل الصارم بين وجود التطابق النصي وبين حالة التوثيق.
"""

import re
from dataclasses import dataclass
from typing import Tuple, Optional


@dataclass
class CitationMatch:
    is_cited: bool
    citation_type: str  # 'quoted_brackets', 'author_year', 'numeric_bracket', 'attribution_phrase', 'none'
    citation_detail: str


# أنماط علامات التنصيص العربية والإنجليزية
_QUOTE_BRACKETS_RE = re.compile(r'«([^»]{6,})»|["“]([^"”]{6,})["”]')

# أنماط التوثيق الرقمي بين معقوفتين: [1] أو [12، ص. 5] أو [3, p. 12]
_NUMERIC_CITATION_RE = re.compile(
    r'\[\s*([0-9]{1,3})\s*(?:[\s،,]+(?:ص|ص\.|صفحة|p\.|pp\.)\s*([0-9\-–]+))?\s*\]'
)

# كلمات وعبارات زمنية وإدارية وقانونية غير دالة على اسم باحث
_NON_AUTHOR_WORDS_BASELINE = {
    'عام', 'سنة', 'شهر', 'يوم', 'تاريخ', 'فترة', 'مدة', 'خلال', 'في', 'منذ', 'قرابة', 'حوالي',
    'نحو', 'رقم', 'القانون', 'القرار', 'الدستور', 'المادة', 'البند', 'الفقرة', 'الجدول', 'الشكل',
    'الخطة', 'الموازنة', 'المرحلة', 'التقرير'
}

_REFINED_NON_AUTHOR_WORDS = {
    'عام', 'سنة', 'شهر', 'يوم', 'تاريخ', 'فترة', 'مدة', 'خلال', 'في', 'منذ', 'قرابة', 'حوالي',
    'نحو', 'رقم', 'القانون', 'القرار', 'الدستور', 'المادة', 'البند', 'الفقرة', 'الجدول', 'الشكل',
    'الخطة', 'الموازنة', 'المرحلة', 'التقرير', 'الدراسة', 'المرسوم', 'الهيئة', 'الوزارة', 'المملكة',
    'الجمهورية', 'المجلس', 'اللائحة', 'الاستراتيجية', 'الرؤية', 'الأهداف', 'المؤتمر', 'النظام',
    'الملكي', 'الوزاري', 'الاتفاقية', 'المعاهدة', 'المشروع', 'البرنامج', 'المحكمة', 'الدائرة'
}

# العبارات التقديمية للاستشهاد الأكاديمي
_ATTRIBUTION_VERBS_RE = re.compile(
    r'\b(أكد|يرى|أوضح|أشار|ذهب|بيّن|ذكر|أفاد|نوّه|استنتج|وفقاً\s+ل|حسب|دراسة|بحث)\s+([\u0600-\u06FF\s]{2,25})\b'
)


def _is_valid_author_baseline(candidate: str) -> bool:
    """التحقق من صحة اسم المؤلف في نمط خط الأساس."""
    words = candidate.strip().split()
    if not words or len(words) > 4:
        return False
    if words[-1] in _NON_AUTHOR_WORDS_BASELINE or words[0] in _NON_AUTHOR_WORDS_BASELINE:
        return False
    return True


def _is_valid_author_refined(name: str) -> bool:
    """التحقق الصارم من اسم المؤلف في النمط المنقح (استبعاد التواريخ والقوانين واللوائح)."""
    clean_name = re.sub(r'[،,;\.\:\-\(\)\[\]«»"“”]', ' ', name).strip()
    words = clean_name.split()
    if not words or len(words) > 4:
        return False
    for w in words:
        if w in _REFINED_NON_AUTHOR_WORDS:
            return False
    # استبعاد الأسماء التي تحتوي على أرقام
    if any(c.isdigit() for c in clean_name):
        return False
    return True


def detect_citation_baseline(text: str) -> CitationMatch:
    """كاشف الاستشهاد بنمط خط الأساس (RC1 Baseline)."""
    if not text:
        return CitationMatch(is_cited=False, citation_type='none', citation_detail='')

    # 1. علامات التنصيص
    quote_matches = _QUOTE_BRACKETS_RE.findall(text)
    if quote_matches:
        for q in quote_matches:
            found_quote = q[0] if q[0] else q[1]
            if len(found_quote.split()) >= 3:
                return CitationMatch(
                    is_cited=True,
                    citation_type='quoted_brackets',
                    citation_detail=f"اقتباس منصوص: «{found_quote[:50]}...»"
                )

    # 2. التوثيق القوسي الأساسي
    in_text_re = re.compile(
        r'\(\s*([\u0600-\u06FFA-Za-z\s]{2,35})[\s،,]+([12][09][0-9]{2})(?:[\s،,]+(?:ص|ص\.|صفحة|p\.|pp\.)\s*([0-9\-–]+))?\s*\)'
    )
    in_text = in_text_re.search(text)
    if in_text:
        candidate_author = in_text.group(1).strip()
        year = in_text.group(2)
        page = in_text.group(3)
        if _is_valid_author_baseline(candidate_author):
            page_str = f"، ص. {page}" if page else ""
            return CitationMatch(
                is_cited=True,
                citation_type='author_year',
                citation_detail=f"توثيق أكاديمي: ({candidate_author}، {year}{page_str})"
            )

    # 3. التوثيق الرقمي
    num_m = _NUMERIC_CITATION_RE.search(text)
    if num_m:
        ref_num = num_m.group(1)
        ref_page = num_m.group(2)
        page_str = f"، ص. {ref_page}" if ref_page else ""
        return CitationMatch(
            is_cited=True,
            citation_type='numeric_bracket',
            citation_detail=f"توثيق رقمي: [{ref_num}{page_str}]"
        )

    # 4. إحالة بالاسم خارج القوس
    author_year_re = re.finditer(r'([\u0600-\u06FFA-Za-z\s]{2,30})\s*\(\s*([12][09][0-9]{2})\s*\)', text)
    for m in author_year_re:
        candidate_name = m.group(1).strip()
        year = m.group(2)
        if _is_valid_author_baseline(candidate_name):
            words = candidate_name.split()
            if 1 <= len(words) <= 3:
                return CitationMatch(
                    is_cited=True,
                    citation_type='author_year',
                    citation_detail=f"إحالة للمؤلف: {candidate_name} ({year})"
                )

    # 5. الإسناد اللفظي
    attr = _ATTRIBUTION_VERBS_RE.search(text)
    if attr:
        verb = attr.group(1)
        author = attr.group(2).strip()
        if _is_valid_author_baseline(author):
            return CitationMatch(
                is_cited=True,
                citation_type='attribution_phrase',
                citation_detail=f"إسناد أكاديمي: {verb} {author}"
            )

    return CitationMatch(is_cited=False, citation_type='none', citation_detail='')


def detect_citation_refined(text: str) -> CitationMatch:
    """كاشف الاستشهاد المنقح (RC2 EXP-04 Refined Citation Filter)."""
    if not text:
        return CitationMatch(is_cited=False, citation_type='none', citation_detail='')

    # 1. علامات التنصيص الصريحة
    quote_matches = _QUOTE_BRACKETS_RE.findall(text)
    if quote_matches:
        for q in quote_matches:
            found_quote = q[0] if q[0] else q[1]
            if len(found_quote.split()) >= 3:
                return CitationMatch(
                    is_cited=True,
                    citation_type='quoted_brackets',
                    citation_detail=f"اقتباس منصوص: «{found_quote[:50]}...»"
                )

    # 2. التوثيق القوسي المنقح بنظام APA (يدعم الفواصل، واو العطف، والصفحات)
    in_text_re = re.compile(
        r'\(\s*([\u0600-\u06FFA-Za-z\s،,و\.\-]{2,40})[\s،,]+([12][09][0-9]{2})(?:[\s،,]+(?:ص|ص\.|صفحة|p\.|pp\.)\s*([0-9\-–]+))?\s*\)'
    )
    in_text = in_text_re.search(text)
    if in_text:
        raw_author = in_text.group(1).strip()
        author = re.sub(r'[،,;\.\:\-\(\)\[\]«»"“”]', ' ', raw_author).strip()
        year = in_text.group(2)
        page = in_text.group(3)
        if _is_valid_author_refined(author):
            page_str = f"، ص. {page}" if page else ""
            return CitationMatch(
                is_cited=True,
                citation_type='author_year',
                citation_detail=f"توثيق أكاديمي: ({raw_author}، {year}{page_str})"
            )

    # 3. التوثيق الرقمي المعياري
    num_m = _NUMERIC_CITATION_RE.search(text)
    if num_m:
        ref_num = num_m.group(1)
        ref_page = num_m.group(2)
        page_str = f"، ص. {ref_page}" if ref_page else ""
        return CitationMatch(
            is_cited=True,
            citation_type='numeric_bracket',
            citation_detail=f"توثيق رقمي: [{ref_num}{page_str}]"
        )

    # 4. إحالة الكاتب بالاسم خارج القوس متبوعاً بالسنة
    attr_author_re = re.finditer(
        r'\b(أكد|يرى|أوضح|أشار|ذهب|بيّن|ذكر|أفاد|نوّه|استنتج|وفقاً\s+ل|حسب|دراسة|بحث)\s+([\u0600-\u06FF\s]{2,25})\s*\(\s*([12][09][0-9]{2})\s*\)',
        text
    )
    for m in attr_author_re:
        verb = m.group(1)
        author = m.group(2).strip()
        year = m.group(3)
        if _is_valid_author_refined(author):
            return CitationMatch(
                is_cited=True,
                citation_type='attribution_phrase',
                citation_detail=f"إسناد أكاديمي: {verb} {author} ({year})"
            )

    return CitationMatch(is_cited=False, citation_type='none', citation_detail='')


def detect_citation(text: str, mode: str = 'refined') -> CitationMatch:
    """
    الموزع الموحد لكاشف الاستشهاد الأكاديمي بناءً على راية التكوين.
    """
    if mode == 'baseline':
        return detect_citation_baseline(text)
    else:
        return detect_citation_refined(text)
