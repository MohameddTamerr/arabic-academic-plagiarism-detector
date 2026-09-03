# -*- coding: utf-8 -*-
"""
كاشف ومستبعد أقسام المراجع والفهارس (Bibliography & Reference Section Detector):
- كشف العناوين الدالة على بدء قسم المراجع (قائمة المراجع، المصادر، References...).
- استبعاد فقرات المراجع من حساب نسبة الاستلال غير الموثق لمنع تضخيم النتائج دون داعٍ.
"""

import re

_BIBLIOGRAPHY_HEADERS_RE = re.compile(
    r'^(?:(?:قائمة|ثبت|فهرس)\s+)?(?:المصادر\s+و\s*المراجع|المراجع\s+و\s*المصادر|المراجع|المصادر|'
    r'المراجع\s+العربية|المراجع\s+الأجنبية|References|Bibliography|Works\s+Cited)\s*[:\-–]?$',
    re.IGNORECASE
)

# نمط التعرف على سطر فردي يشبه مرجعاً أكاديمياً (اسم باحث، سنة، عنوان، دار نشر)
_BIB_ENTRY_RE = re.compile(
    r'^[0-9\-\.\[\]]+\s*[ا-يA-Za-z\s]+[\.،,]\s*\(?[12][09][0-9]{2}\)?[\.،,].{15,}'
)


def is_bibliography_header(line: str) -> bool:
    """فحص إذا كان السطر يمثل عنوان قسم المراجع."""
    clean = line.strip().strip('#*-_ ')
    # إزالة الأرقام والترقيم التعدادي مثل "1." أو "2-" أو "أولاً:" في بداية السطر
    clean = re.sub(r'^(?:[0-9]+[\.\-\)]\s*|(?:أولاً|ثانياً|ثالثاً|رابعاً|خامساً|سادساً|الفصل\s+[ا-ي0-9]+)\s*[:\-–]?\s*)', '', clean).strip()
    clean = clean.strip(':–- ')
    return bool(_BIBLIOGRAPHY_HEADERS_RE.match(clean))


def is_bibliography_entry(text: str) -> bool:
    """فحص إذا كان السطر يطابق هيكل مدخلات المراجع الببليوغرافية."""
    clean = text.strip()
    return bool(_BIB_ENTRY_RE.match(clean))


def filter_bibliography_sections(segments: list[dict]) -> tuple[list[dict], int]:
    """
    فحص قائمة المقاطع وتحديد التي تقع داخل قسم المراجع.
    تُحدَّد علامة 'is_bibliography': True لتلك المقاطع.
    ترجع القائمة المعدلة وعدد المقاطع المستبعدة.
    """
    in_bib_section = False
    bib_count = 0

    for seg in segments:
        text = seg.get('text', '').strip()
        lines = text.split('\n')
        first_line = lines[0].strip() if lines else text

        if is_bibliography_header(first_line) or is_bibliography_header(text):
            in_bib_section = True
            seg['is_bibliography'] = True
            seg['status'] = 'bibliography'
            bib_count += 1
            continue

        if not in_bib_section and is_bibliography_entry(text):
            in_bib_section = True

        if in_bib_section:
            seg['is_bibliography'] = True
            seg['status'] = 'bibliography'
            bib_count += 1
        else:
            seg['is_bibliography'] = False

    return segments, bib_count
