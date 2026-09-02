# -*- coding: utf-8 -*-
"""
وحدة استخراج النصوص من ملفات PDF و Word (.docx).
تستخدم PyMuPDF (fitz) كخيار أول لاستخراج النصوص العربية بالترتيب الطبيعي الدقيق،
مع آلية تصحيح الاتجاه التلقائي (Bidi un-reverser) لضمان عدم عكس الحروف.
"""

import os
import re
import logging

logger = logging.getLogger(__name__)

_REVERSED_ARABIC = re.compile(r'\b(ة[ا-ي]{2,}|[ا-ي]{2,}لا|[ا-ي]{2,}ةي|هيلع|ءاكذ|ميلعت)\b')
_NORMAL_ARABIC = re.compile(r'\b(ال[ا-ي]{2,}|لل[ا-ي]{2,}|بال[ا-ي]{2,}|فال[ا-ي]{2,}|كال[ا-ي]{2,})\b')


def clean_mixed_latin_arabic_tokens(text: str) -> str:
    """
    تنظيف الحروف والرموز العربية العشوائية المزروعة داخل الكلمات الإنجليزية والفرنسية
    بسبب أخطاء ترميز الخطوط في بعض ملفات الـ PDF.
    """
    lines = text.split('\n')
    out_lines = []
    latin_re = re.compile(r'[a-zA-Z]')
    arabic_re = re.compile(r'[\u0600-\u06FF\u0660-\u066C]')
    
    for line in lines:
        words = line.split()
        cleaned_words = []
        for w in words:
            l_cnt = len(latin_re.findall(w))
            a_cnt = len(arabic_re.findall(w))
            # إذا كانت الكلمة تتكون بشكل أغلبي من حروف لاتينية وبها حرف عربي زائف
            if l_cnt > 0 and a_cnt > 0 and l_cnt >= a_cnt:
                cleaned_words.append(arabic_re.sub('', w))
            else:
                cleaned_words.append(w)
        out_lines.append(' '.join(cleaned_words))
    return '\n'.join(out_lines)


def clean_arabic_pdf_glyphs(text: str) -> str:
    """
    تنظيف وتصحيح الأخطاء التشوهية الناتجة عن استخراج النصوص من ملفات PDF ذات الخطوط التقليدية (Arabic PDF Font Artifacts):
    - تصحيح استخراج 'ال' كـ 'امل' أو 'املم' في بدايات الكلمات (مثال: املمجلّة -> المجلة، املعرفة -> المعرفة).
    - تصحيح الكلمات المعكوسة تلقائياً (مثل: يف -> في).
    - إزالة علامات التشويش والتطويل والشكل المتداخل.
    """
    import unicodedata
    if not text:
        return ''

    text = unicodedata.normalize('NFKC', text)
    text = re.sub(r'[\uFFFD\u0000-\u0008\u000B\u000C\u000E-\u001F\u25C6\u25C7\u25A0\u25A1]', ' ', text)
    text = text.replace('ـ', '')

    # إصلاح الأشكال التشكيلية الشائعة لاستخراج خطوط PDF العربية:
    text = re.sub(r'\bاملم([ا-ي]{2,})', r'الم\1', text)
    text = re.sub(r'\bامل([ا-ي]{2,})', r'الم\1', text)
    text = re.sub(r'\bيف\b', 'في', text)
    text = re.sub(r'\bعل[»|م]\b', 'على', text)
    text = re.sub(r'\bإل[»|م]\b', 'إلى', text)
    text = re.sub(r'([ا-ي])ً([ا-ي])', r'\1\2', text)

    # تنظيف الكلمات الإنجليزية والفرنسية من الحروف العربية المزروعة بالخطأ
    text = clean_mixed_latin_arabic_tokens(text)
    
    return text


def unreverse_arabic_text(text: str) -> str:
    """
    يكتشف ويصلح اتجاه الحروف العربية المعكوسة الناتجة عن بعض ملفات PDF القديمة جداً.
    يضمن عدم مساس أي سطر يحتوي على كلمات إنجليزية أو فرنسية.
    """
    if not text:
        return ''

    lines = text.split('\n')
    out_lines = []

    arabic_char_re = re.compile(r'[\u0600-\u06FF\uFB50-\uFDFF\uFE70-\uFEFF]')
    latin_char_re  = re.compile(r'[a-zA-Z]')

    for line in lines:
        # إذا كان السطر يحتوي على أي حروف إنجليزية/لاتينية، نتركه كما هو بدون عكس
        if latin_char_re.search(line):
            out_lines.append(line)
            continue

        words = line.split()
        if not words:
            out_lines.append(line)
            continue

        arabic_words = [w for w in words if arabic_char_re.search(w)]
        if not arabic_words or len(arabic_words) < 3:
            out_lines.append(line)
            continue

        rev_count = sum(1 for w in arabic_words if w.startswith('ة') or w.endswith('لا') or w.startswith('ات'))

        # يطلب نسبة 60% فأكثر من الكلمات المعكوسة الخالصة لتطبيق العكس
        if (rev_count / len(arabic_words)) >= 0.60:
            fixed = []
            for w in reversed(words):
                clean_w = w.replace('ـ', '')[::-1]
                fixed.append(clean_w)
            out_lines.append(' '.join(fixed))
        else:
            out_lines.append(line)

    return '\n'.join(out_lines)


def extract_text(file_path: str) -> str:
    """
    يستخرج النص من ملف PDF أو DOCX أو TXT ويرجع نصًا عربيًا وإنجليزيًا نقيًا.
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.pdf':
        text = _from_pdf(file_path)
        text = unreverse_arabic_text(text)
        return clean_arabic_pdf_glyphs(text)
    elif ext in ('.docx', '.doc'):
        text = _from_docx(file_path)
        return clean_arabic_pdf_glyphs(text)
    elif ext == '.txt':
        text = _from_txt(file_path)
        return clean_arabic_pdf_glyphs(text)
    else:
        logger.warning(f"نوع الملف غير مدعوم: {ext}")
        return ''


def _from_pdf(path: str) -> str:
    # 1. التجربة الأولى: PyMuPDF (fitz) - الأفضل في اللغة العربية
    try:
        import fitz  # pymupdf
        doc = fitz.open(path)
        pages = []
        for page in doc:
            t = page.get_text('text')
            if t and t.strip():
                pages.append(t)
        if pages:
            return '\n'.join(pages)
    except Exception as e:
        logger.debug(f"فشل pymupdf، تجربة pdfplumber: {e}")

    # 2. التجربة الثانية: pdfplumber كخيار احتياطي
    try:
        import pdfplumber
        pages = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text and text.strip():
                    pages.append(text)
        if pages:
            return '\n'.join(pages)
    except Exception as e:
        logger.error(f"خطأ في استخراج PDF: {e}")

    # 3. التجربة الثالثة: محاولة التعرف الضوئي الأوفلاين إن وُجد (Offline OCR Fallback)
    try:
        import pytesseract
        from PIL import Image
        import pdf2image
        images = pdf2image.convert_from_path(path)
        ocr_pages = []
        for img in images:
            txt = pytesseract.image_to_string(img, lang='ara+eng')
            if txt.strip():
                ocr_pages.append(txt)
        if ocr_pages:
            return '\n'.join(ocr_pages)
    except Exception:
        pass

    return ''



def _from_docx(path: str) -> str:
    try:
        import docx
        doc = docx.Document(path)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return '\n'.join(paragraphs)
    except Exception as e:
        logger.error(f"خطأ في استخراج DOCX: {e}")
        return ''


def _from_txt(path: str) -> str:
    encodings = ['utf-8', 'utf-8-sig', 'cp1256', 'iso-8859-6']
    for enc in encodings:
        try:
            with open(path, 'r', encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, LookupError):
            continue
    logger.error(f"تعذّر قراءة الملف: {path}")
    return ''
