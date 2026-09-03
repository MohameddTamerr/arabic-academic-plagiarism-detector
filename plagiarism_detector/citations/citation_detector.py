# -*- coding: utf-8 -*-
"""
كاشف الاقتباسات الموثقة والاستشهادات الأكاديمية (Citation & Quotation Detector):
- فحص علامات التنصيص العربية والإنجليزية («...»، "..."، “...”).
- كشف أنماط التوثيق الأكاديمي (الكاتب، السنة، رقم الصفحة).
- كشف عبارات التوثيق الأكاديمي الشائعة باللغة العربية (ص. 25، صفحة 12، بحسب فلان، يرى فلان...).
- تصنيف الاقتباس كـ "اقتباس موثق بنظام التوثيق" لعدم احتسابه كسرقة علمية مشبوهة.
"""

import re
from dataclasses import dataclass


@dataclass
class CitationMatch:
    is_cited: bool
    citation_type: str  # 'quoted_brackets', 'author_year', 'page_ref', 'none'
    citation_detail: str


# أنماط علامات التنصيص العربية والإنجليزية
_QUOTE_BRACKETS_RE = re.compile(r'«([^»]{6,})»|["“]([^"”]{6,})["”]')

# أنماط التوثيق بالأقواس: (محمد، 2023) أو (محمد أحمد، 2023، صفحة 25) أو (درويش، 2024، ص. 14)
_IN_TEXT_CITATION_RE = re.compile(
    r'\(\s*([\u0600-\u06FFA-Za-z\s]{2,35})[\s،,]+([12][09][0-9]{2})(?:[\s،,]+(?:ص|ص\.|صفحة|p\.|pp\.)\s*([0-9\-–]+))?\s*\)'
)

# أنماط التوثيق الرقمي بين معقوفتين: [1] أو [12، ص. 5] أو [3, p. 12]
_NUMERIC_CITATION_RE = re.compile(
    r'\[\s*([0-9]{1,3})\s*(?:[\s،,]+(?:ص|ص\.|صفحة|p\.|pp\.)\s*([0-9\-–]+))?\s*\]'
)

# كلمات وعبارات زمنية غير دالة على اسم باحث قبل السنة
_NON_AUTHOR_TIME_WORDS = {
    'عام', 'سنة', 'شهر', 'يوم', 'تاريخ', 'فترة', 'مدة', 'خلال', 'في', 'منذ', 'قرابة', 'حوالي',
    'نحو', 'رقم', 'القانون', 'القرار', 'الدستور', 'المادة', 'البند', 'الفقرة', 'الجدول', 'الشكل',
    'الخطة', 'الموازنة', 'المرحلة', 'التقرير'
}

# العبارات التقديمية للاستشهاد الأكاديمي
_ATTRIBUTION_VERBS_RE = re.compile(
    r'\b(أكد|يرى|أوضح|أشار|ذهب|بيّن|ذكر|أفاد|نوّه|استنتج|وفقاً\s+ل|حسب|دراسة|بحث)\s+([\u0600-\u06FF\s]{2,25})\b'
)


def _is_valid_author_name(candidate: str) -> bool:
    """التحقق من أن المقطع السابق للسنة يمثل اسماً أو إسناداً وليس عبارة زمنية عشوائية."""
    words = candidate.strip().split()
    if not words or len(words) > 4:
        return False
    # إذا كانت الكلمة الأخيرة من الكلمات الزمنية العامة
    if words[-1] in _NON_AUTHOR_TIME_WORDS or words[0] in _NON_AUTHOR_TIME_WORDS:
        return False
    return True


def detect_citation(text: str) -> CitationMatch:
    """
    فحص الجملة أو الفقرة لتحديد ما إذا كانت تحتوي على توثيق أكاديمي أو علامات تنصيص.
    مبني ليكون متحفظاً أكاديمياً (Conservative) لتجنب الإيجابيات الكاذبة.
    """
    if not text:
        return CitationMatch(is_cited=False, citation_type='none', citation_detail='')

    # 1. فحص علامات التنصيص الصريحة («...»، "..."، “...”)
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

    # 2. فحص التوثيق القوسي الشامل: (محمد، 2023) أو (محمد أحمد، 2023، ص. 25)
    in_text = _IN_TEXT_CITATION_RE.search(text)
    if in_text:
        candidate_author = in_text.group(1).strip()
        year = in_text.group(2)
        page = in_text.group(3)
        if _is_valid_author_name(candidate_author):
            page_str = f"، ص. {page}" if page else ""
            return CitationMatch(
                is_cited=True,
                citation_type='author_year',
                citation_detail=f"توثيق أكاديمي: ({candidate_author}، {year}{page_str})"
            )

    # 3. فحص التوثيق الرقمي المعياري: [1] أو [12، ص. 5]
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

    # 4. فحص صيغة الكاتب خارج القوس متبوعاً بالسنة: محمد أحمد (2023) أو أكد درويش (2020)
    author_year_re = re.finditer(r'([\u0600-\u06FFA-Za-z\s]{2,30})\s*\(\s*([12][09][0-9]{2})\s*\)', text)
    for m in author_year_re:
        candidate_name = m.group(1).strip()
        year = m.group(2)
        # التحقق من خلو الاسم من الكلمات الزمنية وتطابقه مع اسم باحث
        if _is_valid_author_name(candidate_name):
            # إما مسبوق بفعل إسناد، أو اسم باحث من كلمة إلى 3 كلمات
            words = candidate_name.split()
            if 1 <= len(words) <= 3:
                return CitationMatch(
                    is_cited=True,
                    citation_type='author_year',
                    citation_detail=f"إحالة للمؤلف: {candidate_name} ({year})"
                )

    # 5. فحص الإسناد اللفظي الصريح المتبوع باسم: أكد درويش في دراسته أن...
    attr = _ATTRIBUTION_VERBS_RE.search(text)
    if attr:
        verb = attr.group(1)
        author = attr.group(2).strip()
        if _is_valid_author_name(author):
            return CitationMatch(
                is_cited=True,
                citation_type='attribution_phrase',
                citation_detail=f"إسناد أكاديمي: {verb} {author}"
            )

    return CitationMatch(is_cited=False, citation_type='none', citation_detail='')
