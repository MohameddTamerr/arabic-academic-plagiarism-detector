# -*- coding: utf-8 -*-
"""
مرشح النصوص المؤسسية الشائعة والديباجات على مستوى المقاطع (EXP-03 Span-Level Common-Text Filter):
- يدعم نمطين محكومين براية الإعدادات (Feature Flag):
  1. نمط الفلترة على مستوى المقاطع (Span-Level): يستبعد الديباجات والكليشيهات مع الحفاظ الكامل على المقاطع الموضوعية المنسوخة.
  2. نمط خط الأساس (Baseline): الفلترة التقليدية على مستوى كامل الفقرة للتوافق والرجوع الفوري لـ RC1.
- يمنع إسقاط السرقات الحقيقية الناتجة عن احتواء الفقرة على ديباجة عادية في بدايتها.
"""

import re
from typing import Tuple, List, Optional
from plagiarism_detector.preprocessing.normalizer import normalize_aggressive, normalize_light

# قائمة النصوص المؤسسية والأكاديمية الشائعة
EXPANDED_COMMON_INSTITUTIONAL_MARKERS = [
    'بناء على ما تقدم',
    'بعد الاطلاع على',
    'تشكلت لجنة الحكم والمناقشة',
    'من الجدير بالذكر',
    'بخالص الشكر والتقدير',
    'يتضح مما تقدم',
    'حرصا على امن وسرية',
    'وفي ضوء ما اسفرت عنه النتائج',
    'الحزمة الاحصائية للعلوم الاجتماعية',
    'استنادا الى الصلاحيات المخولة',
    'جامعة نايف',
    'كلية العدالة الجنائية',
    'قسم الدراسات الامنية',
    'المبحث الاول',
    'المطلب الاول',
    'الفرع الاول',
    'الخاتمة والتوصيات',
    'تمهيد وتقسيم',
    'استنادا الى المادة',
    'وفقا لما نصت عليه',
    'والصلاة والسلام',
    'الحمد لله رب العالمين',
    'اما بعد فهذا بحث',
    'وتجدر الاشارة',
    'ومن هذا المنطلق',
    'وعليه فان الباحث',
    'وفي هذا السياق',
    'جمهورية مصر',
    'المملكة العربية السعودية',
    'صيغة استمارة الاستبيان',
    'اجريت الدراسة الميدانية',
    'قام الباحث بتوزيع',
    'صدق وثبات الاداة',
    'معامل الفا كرونباخ',
    'العينة الاستطلاعية',
    'فروض البحث',
    'مشكلة البحث واهميته',
    'حدود البحث المكانية والزمانية',
    'مصطلحات البحث الاجرائية',
    'الدراسات السابقة والمشابهة',
    'اوصت لجنة الحكم بمنح',
    'شكر وتقدير واعتراف بالفضل',
    'اهداء الى الوالدين الكريمين',
    'قائمة المحتويات والجداول',
    'المراجع العربية والاجنبية'
]

# تجهيز النسخ المطبوعة للتطابق السريع
_CUSTOM_PHRASES_RUNTIME: list = []  # تُحدَّث في وقت التشغيل بدون إعادة تشغيل


def _load_custom_phrases_from_disk() -> list:
    """تحميل الجمل المخصصة من ملف JSON عند بدء التشغيل."""
    try:
        import json
        import config as _cfg
        _path = _cfg.CONFIG_DIR / 'custom_phrases.json'
        if _path.exists():
            with open(_path, 'r', encoding='utf-8') as _f:
                _data = json.load(_f)
                if isinstance(_data, list):
                    return [str(p) for p in _data if p]
    except Exception:
        pass
    return []


# تحميل الجمل المخصصة عند الإقلاع
_CUSTOM_PHRASES_RUNTIME = _load_custom_phrases_from_disk()

_NORM_MARKERS = [(m, normalize_aggressive(m)) for m in EXPANDED_COMMON_INSTITUTIONAL_MARKERS + _CUSTOM_PHRASES_RUNTIME]


def is_common_institutional_text(text: str, mode: str = 'span_level') -> bool:
    """
    فحص ما إذا كان النص يمثل عبارة مؤسسية شائعة أو يحتوي على ديباجة كليشيهية.
    """
    if not text or not text.strip():
        return False

    norm = normalize_aggressive(text)

    if mode == 'baseline':
        # في خط الأساس، نتحقق فقط من التطابق التام أو النسبة العالية
        for raw_m, norm_m in _NORM_MARKERS[:15]:
            if norm == norm_m or (len(norm) > 0 and norm_m in norm and len(norm) <= len(norm_m) + 15):
                return True
        return False
    else:
        # في النمط الموسع
        return any(norm_m in norm for _, norm_m in _NORM_MARKERS)


def filter_common_spans(
    text: str,
    min_substantive_words: int = 4,
    mode: str = 'span_level'
) -> Tuple[str, bool, List[str]]:
    """
    تنقية المقاطع المشتركة واستخراج النص الموضوعي الحقيقي (Span-Level Extraction).
    المخرجات: (النص الموضوعي المنقى، هل تم كشف ديباجة شائعة، قائمة الديباجات المستخرجة).
    """
    if not text or not text.strip():
        return text, False, []

    if mode == 'baseline':
        if is_common_institutional_text(text, mode='baseline'):
            return "", True, [text.strip()]
        return text, False, []

    # نمط Span-Level للإصدار RC2
    cleaned_text = text
    found_spans = []

    # البحث عن الديباجات في بداية النص أو ضمنه واستبعادها
    for raw_marker, norm_marker in _NORM_MARKERS:
        # استخدام تعبير نمطي مرن للبحث عن الديباجة
        words = raw_marker.split()
        if not words:
            continue

        # بناء نمط للبحث غير الحساس لتشكيل الحروف ومعالجة حروف العطف والجر المتصلة (و، ف، ب، ك، ل)
        pattern_str = r'(?:^|\b|[وفلبك])' + r'[\s،,\.\:\-]+'.join(re.escape(w) for w in words) + r'\b'
        try:
            matches = list(re.finditer(pattern_str, cleaned_text, re.IGNORECASE))
            if matches:
                for match in matches:
                    span_str = match.group(0).strip()
                    found_spans.append(span_str)
                cleaned_text = re.sub(pattern_str, ' ', cleaned_text, flags=re.IGNORECASE)
        except Exception:
            pass

    # تنظيف الفواصل والمسافات الزائدة بعد إزالة الديباجات
    cleaned_text = re.sub(r'[\s،,\.\:\-]+', ' ', cleaned_text).strip()
    substantive_words = len(cleaned_text.split())

    has_common = len(found_spans) > 0

    if has_common:
        # إذا لم يتبقَّ سوى كلمات قليلة جداً غير مفيدة (< min_substantive_words)، يُعتبر المقطع كله ديباجة
        if substantive_words < min_substantive_words:
            return "", True, found_spans
        else:
            # يتبقى نص موضوعي جوهري كافٍ للفحص ومقارنة الاستلال
            return cleaned_text, True, found_spans

    return text, False, []
