# -*- coding: utf-8 -*-
"""
وحدة التطبيع اللغوي العربي بمستويين (Dual-Level Arabic Normalizer):
1. normalize_light: تطبيع دلالي معتدل للـ TF-IDF والنموذج الدلالي (يحافظ على التاء المربوطة ة والهمزة المنفردة).
2. normalize_aggressive: تطبيع مشدد لكشف النسخ الحرفي ومكافحة أساليب التهرب والتحايل.
"""

import re
import unicodedata

# حروف التشكيل والتنوين
_DIACRITICS_RE = re.compile(
    r'[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06DC\u06DF-\u06E4\u06E7\u06E8\u06EA-\u06ED]'
)

# المحارف الخفية والمسافات الصفرية
_ZERO_WIDTH_RE = re.compile(r'[\u200B\u200C\u200D\uFEFF\u00AD\u2060]')

# الكشيدة (التطويل)
_TATWEEL_CHAR = '\u0640'

# علامات الترقيم والأقواس الشائعة
_PUNCTUATION_RE = re.compile(
    r'[،؛؟!\.:\-"\'`\(\)\[\]\{\}«»“”/\\]'
)

# كل ما ليس حرفاً أو رقماً أو مسافة
_NON_WORD_RE = re.compile(r'[^\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF\w\s]')

# خريطة التطبيع الخفيف:
# توحيد أشكال الألف فقط مع الألف المقصورة، مع الحفاظ على التاء المربوطة (ة) والهمزات الأخرى
_LIGHT_TRANS = str.maketrans({
    'أ': 'ا',
    'إ': 'ا',
    'آ': 'ا',
    'ٱ': 'ا',
    'ى': 'ي',  # توحيد الألف المقصورة والياء
})

# خريطة التطبيع المشدد:
# توحيد التاء المربوطة (ة -> ه) والهمزات المتنوعة (ء, ئ, ؤ) لكشف النسخ والتحايل الإملائي
_AGGRESSIVE_TRANS = str.maketrans({
    'أ': 'ا',
    'إ': 'ا',
    'آ': 'ا',
    'ٱ': 'ا',
    'ى': 'ي',
    'ة': 'ه',   # توحيد التاء المربوطة والهاء
    'ء': 'ا',   # توحيد الهمزة السطرية
    'ؤ': 'و',
    'ئ': 'ي',
})


def normalize_light(text: str) -> str:
    """
    تطبيع لغوي معتدل يُستخدم في استخراج متجهات TF-IDF والمقارنات الدلالية.
    - يزيل التشكيل، الكشيدة (التطويل)، والمسافات الصفرية.
    - يوحد أشكال الألف (أ/إ/آ/ٱ -> ا) والألف المقصورة (ى -> ي).
    - يحافظ على التاء المربوطة (ة) لتفادي الخلط المعنوي ورفع دقة الدلالة.
    """
    if not text:
        return ''

    # 1. تطبيع يونيكود قياسي
    text = unicodedata.normalize('NFC', text)

    # 2. إزالة المسافات الصفرية والكشيدة
    text = _ZERO_WIDTH_RE.sub('', text)
    text = text.replace(_TATWEEL_CHAR, '')

    # 3. إزالة علامات التشكيل
    text = _DIACRITICS_RE.sub('', text)

    # 4. توحيد الألف والياء الخفيف
    text = text.translate(_LIGHT_TRANS)

    # 5. تنظيف علامات الترقيم واستبدالها بمسافة
    text = _NON_WORD_RE.sub(' ', text)

    # 6. توحيد المسافات المتكررة
    return ' '.join(text.split()).strip()


def normalize_aggressive(text: str) -> str:
    """
    تطبيع مشدد يُستخدم في كشف النسخ الحرفي المباشر (Shingles + Jaccard)
    وفحص محاولات التهرب من الاقتباس بتغيير الهمزات أو التاء المربوطة.
    - يشمل كل خطوات normalize_light.
    - يحول (ة -> ه)، و (ء -> ا)، و (ؤ -> و)، و (ئ -> ي).
    """
    if not text:
        return ''

    text = unicodedata.normalize('NFC', text)
    text = _ZERO_WIDTH_RE.sub('', text)
    text = text.replace(_TATWEEL_CHAR, '')
    text = _DIACRITICS_RE.sub('', text)
    text = text.translate(_AGGRESSIVE_TRANS)
    text = _NON_WORD_RE.sub(' ', text)

    return ' '.join(text.split()).strip()


def split_sentences(text: str, min_words: int = 4) -> list[str]:
    """
    تقسيم النص إلى جمل مستقلة معتمدة على علامات الترقيم العربية والإنجليزية والأسطر.
    يتم استبعاد الجمل التي يقل طولها عن min_words إلا إذا كانت عنواناً صريحاً لقسم المراجع.
    """
    if not text:
        return []

    from plagiarism_detector.citations.bibliography_detector import is_bibliography_header

    # تقسيم بالاعتماد على الترقيم أو نهايات الأسطر
    raw_splits = re.split(r'[\.\!\?؟;\n]+', text)
    valid_sentences = []
    for s in raw_splits:
        clean_s = s.strip()
        if clean_s and (len(clean_s.split()) >= min_words or is_bibliography_header(clean_s)):
            valid_sentences.append(clean_s)
    return valid_sentences


def get_shingles(normalized_text: str, size: int = 5) -> set[tuple[str, ...]]:
    """
    توليد متواليات الكلمات (Word N-Grams / Shingles) من النص المطبَّع.
    """
    words = normalized_text.split()
    if not words:
        return set()
    if len(words) < size:
        return {tuple(words)}
    return {tuple(words[i:i + size]) for i in range(len(words) - size + 1)}
