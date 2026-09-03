# -*- coding: utf-8 -*-
"""
محرك التعرف الضوئي على الحروف المشروط (Conditional Offline OCR Engine):
- يعمل أوفلاين بالكامل باستخدام محرك Tesseract-OCR المحلي المثبت مسبقاً.
- يُستدعى فقط في حال كانت صفحة الـ PDF مصمتة أو مسحوبة عبر الماسح الضوئي (Scanner).
- لا يُنزل أي نماذج عبر الإنترنت، ويوفر فحصاً آمناً للجاهزية دون التسبب في انهيار النظام.
"""

import os
import shutil
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# مسارات تيسيراكت الافتراضية على أنظمة ويندوز
_COMMON_TESSERACT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    r"C:\Tesseract-OCR\tesseract.exe",
]


def find_tesseract_cmd() -> str | None:
    """البحث التلقائي عن مسار tesseract.exe على نظام ويندوز."""
    # 1. فحص المتغير البيئي PATH
    cmd = shutil.which('tesseract')
    if cmd and os.path.exists(cmd):
        return cmd

    # 2. فحص المسارات القياسية المعروفة
    for p in _COMMON_TESSERACT_PATHS:
        if os.path.exists(p):
            return p

    return None


def check_ocr_availability() -> dict:
    """
    التحقق من جاهزية محرك OCR المحلي وحزم اللغة العربية.
    """
    cmd = find_tesseract_cmd()
    if not cmd:
        return {
            'available': False,
            'reason': 'برنامج Tesseract-OCR غير مثبت في المسار الافتراضي (C:\\Program Files\\Tesseract-OCR).',
            'has_arabic': False
        }

    try:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = cmd
        langs = pytesseract.get_languages(config='')
        has_arabic = ('ara' in langs) or ('Arabic' in langs)
        return {
            'available': True,
            'cmd_path': cmd,
            'has_arabic': has_arabic,
            'languages': langs,
            'reason': 'محرك Tesseract جاهز ومتاح أوفلاين.' if has_arabic else 'Tesseract متاح لكن ينقصه ملف اللغة العربية (ara.traineddata).'
        }
    except Exception as e:
        return {
            'available': False,
            'reason': f'تعذر تشغيل pytesseract: {str(e)}',
            'has_arabic': False
        }


def ocr_page_pixmap(pixmap_or_image) -> str:
    """
    تنفيذ OCR على صورة صفحة واحدة فقط، مع معالجة الأخطاء بأمان.
    """
    status = check_ocr_availability()
    if not status['available'] or not status.get('has_arabic', False):
        logger.debug(f"تخطي OCR: {status['reason']}")
        return ''

    try:
        import pytesseract
        from PIL import Image
        import io

        pytesseract.pytesseract.tesseract_cmd = status['cmd_path']

        # إذا كان المدخل fitz Pixmap
        if hasattr(pixmap_or_image, 'tobytes'):
            img_bytes = pixmap_or_image.tobytes('png')
            image = Image.open(io.BytesIO(img_bytes))
        elif isinstance(pixmap_or_image, Image.Image):
            image = pixmap_or_image
        else:
            return ''

        text = pytesseract.image_to_string(image, lang='ara+eng', config='--psm 6')
        return text.strip()
    except Exception as e:
        logger.warning(f"فشل أثناء إجراء OCR للصفحة: {e}")
        return ''
