# -*- coding: utf-8 -*-
"""
كاشف أساليب التلاعب والتحايل (Cheating & Evasion Detector):
- كشف الحروف اللاتينية أو السيريلية المزروعة داخل الكلمات العربية كبدائل بصرية.
- كشف واستخراج المسافات الصفرية الخفية (Zero-width characters).
- تنظيف النص المشبوه مع إعادة صياغته للمقارنة العادلة.
"""

import re

# الحروف السيريلية واللاتينية الشبيهة بصرياً بالحروف العربية
_CYRILLIC_HOMOGLYPHS = {
    'а': 'ا', 'е': 'ه', 'о': 'و', 'с': 'س',
    'р': 'ر', 'х': 'خ', 'у': 'ي', 'і': 'ي',
}

_LATIN_HOMOGLYPHS = {
    'a': 'ا', 'e': 'ه', 'o': 'و', 'c': 'س',
    'p': 'ر', 'x': 'خ', 'y': 'ي', 'i': 'ي',
}

_ZERO_WIDTH_RE = re.compile(r'[\u200B\u200C\u200D\uFEFF\u00AD\u2060]')
_ARABIC_CHAR_RE = re.compile(r'[\u0600-\u06FF]')
_FOREIGN_CHAR_RE = re.compile(r'[a-zA-Z\u0400-\u04FF]')


def detect_cheating_manipulation(text: str) -> dict:
    """
    فحص شامل لمحاولات التحايل على كواشف الاستلال:
    1. المسافات المخفية (Zero-width)
    2. الحروف المتشابهة بصرياً (Homoglyphs)
    """
    if not text:
        return {'has_cheating': False, 'cheating_count': 0, 'details': []}

    details = []
    cheating_count = 0

    # 1. كشف المسافات الصفرية
    zw_matches = _ZERO_WIDTH_RE.findall(text)
    if zw_matches:
        count = len(zw_matches)
        cheating_count += count
        details.append(f"تم كشف {count} مسافة صفرية مخفية (Zero-Width Spaces) لكسر الكلمات.")

    # 2. كشف الحروف المزروعة في كلمات عربية
    words = text.split()
    mixed_word_count = 0
    sample_mixed = []

    for word in words:
        has_ar = bool(_ARABIC_CHAR_RE.search(word))
        has_lt = bool(_FOREIGN_CHAR_RE.search(word))
        if has_ar and has_lt:
            mixed_word_count += 1
            if len(sample_mixed) < 5:
                sample_mixed.append(word)

    if mixed_word_count > 0:
        cheating_count += mixed_word_count
        details.append(
            f"تم كشف {mixed_word_count} كلمة مدمج بها أحرف لاتينية/سيريلية متشابهة بصرياً "
            f"(أمثلة: {', '.join(sample_mixed)})."
        )

    return {
        'has_cheating': cheating_count > 0,
        'cheating_count': cheating_count,
        'details': details
    }


def clean_cheating_text(text: str) -> str:
    """
    تنقية النص واستبدال المحارف التلاعبية ببدائلها العربية الطبيعية لإجراء الفحص الدقيق.
    """
    if not text:
        return ''

    # 1. إزالة المسافات الصفرية والتطويل (الكشيدة)
    text = _ZERO_WIDTH_RE.sub('', text)
    text = text.replace('\u0640', '')

    # 2. استبدال حروف التلاعب في الكلمات المختلطة مع الحفاظ التام على فواصل الأسطر والفقرات
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        words = line.split()
        cleaned_words = []
        for word in words:
            if _ARABIC_CHAR_RE.search(word) and _FOREIGN_CHAR_RE.search(word):
                # كلمة هجينة تحتوي عربياً ولاتينياً: استبدل الحروف اللاتينية بنظائرها العربية
                w_chars = []
                for ch in word:
                    if ch in _LATIN_HOMOGLYPHS:
                        w_chars.append(_LATIN_HOMOGLYPHS[ch])
                    elif ch in _CYRILLIC_HOMOGLYPHS:
                        w_chars.append(_CYRILLIC_HOMOGLYPHS[ch])
                    else:
                        w_chars.append(ch)
                cleaned_words.append(''.join(w_chars))
            else:
                cleaned_words.append(word)
        cleaned_lines.append(' '.join(cleaned_words))

    return '\n'.join(cleaned_lines)
