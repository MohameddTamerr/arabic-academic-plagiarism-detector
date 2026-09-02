# -*- coding: utf-8 -*-
"""
وحدة التطبيع العربي:
- توحيد الهمزات (أ إ آ ء ئ ؤ → ا)
- إزالة التشكيل والحركات
- توحيد التاء المربوطة والألف المقصورة
- إزالة علامات الترقيم وتطبيع المسافات
"""

import re
import unicodedata


# ==============================================================
# قاموس استبدال الهمزات والحروف المتشابهة
# ==============================================================
_HAMZA_MAP = str.maketrans({
    'أ': 'ا', 'إ': 'ا', 'آ': 'ا', 'ٱ': 'ا',
    'ؤ': 'و',
    'ئ': 'ي', 'ى': 'ي',
    'ة': 'ه',
    '\u0621': 'ا',   # ء → ا
    '\u0626': 'ي',   # ئ (redundant but explicit)
})

# حروف التشكيل (الحركات) والتنوين وغيرها
_DIACRITICS = re.compile(r'[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06DC\u06DF-\u06E4\u06E7\u06E8\u06EA-\u06ED]')

# كل ما ليس حرفًا عربيًا أو إنجليزيًا أو رقمًا أو مسافة
_NON_ALPHA = re.compile(r'[^\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF\w\s]')

# أنماط تقطيع الجمل (نهايات الجمل العربية والإنجليزية)
_SENT_SPLIT = re.compile(r'(?<=[.!?؟.\n])\s+|(?<=\n)\n+')


def normalize_arabic(text: str) -> str:
    """
    يُطبّع النص العربي لصيغة موحدة تُستخدم في المقارنة:
    1. يوحّد الهمزات وشكل الألف
    2. يحذف التشكيل والحركات
    3. يوحّد التاء المربوطة والألف المقصورة
    4. يحذف علامات الترقيم
    5. يطبّع المسافات البيضاء
    """
    if not text:
        return ''

    # 1. Unicode NFC normalization
    text = unicodedata.normalize('NFC', text)

    # 2. توحيد الهمزات
    text = text.translate(_HAMZA_MAP)

    # 3. إزالة التشكيل
    text = _DIACRITICS.sub('', text)

    # 4. إزالة علامات الترقيم مع الاحتفاظ بالمسافات
    text = _NON_ALPHA.sub(' ', text)

    # 5. تطبيع المسافات المتعددة
    text = ' '.join(text.split())

    return text.strip()


def clean_arabic_display_text(text: str) -> str:
    """
    تطهير وتنظيف الأسماء والعناوين من الكشيدة (ـ Tatweel) والمسافات الخفية المتعددة
    لتسهيل القراءة والعرض السليم.
    """
    if not text:
        return ''
    # 1. إزالة الكشيدة (التطويل ـ)
    text = text.replace('\u0640', '')
    # 2. إزالة المسافات الصفرية الخفية
    text = _ZERO_WIDTH_CHARS.sub('', text)
    # 3. دمج وتعديل المسافات الزائدة
    text = ' '.join(text.split())
    return text.strip()


def split_sentences(text: str, min_words: int = 4) -> list[str]:
    """
    يقسّم النص إلى جمل.
    يُجاهل الجمل التي أقل من min_words كلمات.
    """
    if not text:
        return []

    # تقطيع على أساس علامات الترقيم والأسطر الجديدة
    raw = re.split(r'[.!?؟\n]+', text)
    sentences = []
    for s in raw:
        s = s.strip()
        if s and len(s.split()) >= min_words:
            sentences.append(s)
    return sentences


def get_shingles(normalized_text: str, size: int = 6) -> set:
    """
    يُنشئ مجموعة shingles (n-grams من الكلمات) من نص مُطبَّع.
    مثال: size=3, text="أ ب ج د" → {('أ','ب','ج'), ('ب','ج','د')}
    """
    words = normalized_text.split()
    if len(words) < size:
        return {tuple(words)} if words else set()
    return {tuple(words[i:i + size]) for i in range(len(words) - size + 1)}
# ==============================================================
# كشف حيل التلاعب بالأحرف اللاتينية/السيريلية والمسافات الخفية
# ==============================================================
# خريطة الحروف المتشابهة: فقط السيريلية (المتشابهة بصرياً مع الحروف العربية)
# لا نضع الحروف الإنجليزية العادية (a, e, o...) هنا لأنها ستدمر النص الإنجليزي الطبيعي
_HOMOGLYPHS_CYRILLIC = {
    'а': 'ا',   # Cyrillic а → Arabic ا
    'е': 'ه',   # Cyrillic е → Arabic ه
    'о': 'و',   # Cyrillic о → Arabic و
    'с': 'س',   # Cyrillic с → Arabic س
    'р': 'ر',   # Cyrillic р → Arabic ر
    'х': 'خ',   # Cyrillic х → Arabic خ
    'у': 'ي',   # Cyrillic у → Arabic ي
    'і': 'ي',   # Cyrillic і → Arabic ي
}

# الحروف اللاتينية العادية المستخدمة للتلاعب داخل كلمات عربية فقط
_HOMOGLYPHS_LATIN_IN_ARABIC = {
    'a': 'ا', 'e': 'ه', 'o': 'و',
    'c': 'س', 'p': 'ر', 'x': 'خ',
    'y': 'ي', 'i': 'ي'
}

_ZERO_WIDTH_CHARS = re.compile(r'[\u200B\u200C\u200D\uFEFF\u00AD]')
_ARABIC_CHAR_RE = re.compile(r'[\u0600-\u06FF]')
_LATIN_CHAR_RE = re.compile(r'[a-zA-Z]')


def detect_cheating_manipulation(text: str) -> dict:
    """
    يكتشف محاولات التلاعب بالنص مثل:
    1. زرع حروف لاتينية أو سيريلية شبيهة بالأنساق العربية وسط الكلمات.
    2. زرع مسافات صفرية مخفية لكسر الكلمات.
    """
    if not text:
        return {'has_cheating': False, 'cheating_count': 0, 'details': []}

    details = []
    cheating_count = 0

    # 1. كشف المسافات المخفية
    zw_matches = _ZERO_WIDTH_CHARS.findall(text)
    if zw_matches:
        cheating_count += len(zw_matches)
        details.append(f"تم اكتشاف {len(zw_matches)} مسافة صفرية مخفية (Zero-Width Characters)")

    # 2. كشف الحروف الإنجليزية/السيريلية المزروعة وسط كلمات عربية
    words = text.split()
    mixed_words = []
    for w in words:
        has_arabic = bool(re.search(r'[\u0600-\u06FF]', w))
        has_foreign = bool(re.search(r'[a-zA-Z\u0400-\u04FF]', w))
        if has_arabic and has_foreign:
            mixed_words.append(w)

    if mixed_words:
        cheating_count += len(mixed_words)
        sample = ', '.join(mixed_words[:5])
        details.append(f"تم اكتشاف {len(mixed_words)} كلمة تتضمن حروفاً أجنبية مخفية (مثال: {sample})")

    return {
        'has_cheating': cheating_count > 0,
        'cheating_count': cheating_count,
        'details': details
    }


def clean_cheating_text(text: str) -> str:
    """
    ينظف النص من المسافات المخفية والحروف الأجنبية المزروعة لإتاحة المطابقة الدقيقة.
    - يزيل المسافات الصفرية المخفية
    - يستبدل الحروف السيريلية المتشابهة دائمًا
    - يستبدل الحروف اللاتينية فقط داخل الكلمات التي تحتوي أيضاً على حروف عربية
      (لعدم تدمير النص الإنجليزي الطبيعي)
    """
    if not text:
        return ''

    # إزالة المسافات الصفرية
    text = _ZERO_WIDTH_CHARS.sub('', text)

    # استبدال الحروف السيريلية المتشابهة (دائماً آمن لأنها لا تظهر في نص طبيعي)
    chars_pass1 = []
    for ch in text:
        chars_pass1.append(_HOMOGLYPHS_CYRILLIC.get(ch, ch))
    text = ''.join(chars_pass1)

    # استبدال الحروف اللاتينية المزروعة فقط داخل كلمات مختلطة (عربية + لاتينية)
    words = text.split()
    cleaned_words = []
    for w in words:
        has_arabic = bool(_ARABIC_CHAR_RE.search(w))
        has_latin = bool(_LATIN_CHAR_RE.search(w))
        if has_arabic and has_latin:
            # كلمة مختلطة: استبدال الحروف اللاتينية المزروعة بالعربية المقابلة
            cleaned_chars = []
            for ch in w:
                cleaned_chars.append(_HOMOGLYPHS_LATIN_IN_ARABIC.get(ch, ch))
            cleaned_words.append(''.join(cleaned_chars))
        else:
            # كلمة عربية صافية أو إنجليزية صافية: تُترك كما هي
            cleaned_words.append(w)
    return ' '.join(cleaned_words)

