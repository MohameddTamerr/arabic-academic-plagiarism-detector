# -*- coding: utf-8 -*-
"""
خدمة إدارة الأبحاث المرجعية (Paper Service):
- استيراد وفحص المستندات (PDF / Word / TXT).
- حساب بصمة SHA-256 لمنع تكرار المراجع وتنبيه المستخدم.
- استخراج الصفحات الفردية والفقرات وتخزينها في قاعدة البيانات.
"""

import os
import hashlib
import logging
from pathlib import Path
from typing import Optional

from app.repositories import document_repo
from plagiarism_detector.extraction.page_extractor import extract_document_pages
from plagiarism_detector.preprocessing.segmenter import segment_pages
from plagiarism_detector.reporting.report_builder import invalidate_pipeline_index, build_pipeline_index
from plagiarism_detector.core.categorizer import categorize_text

logger = logging.getLogger(__name__)


def compute_file_sha256(file_path: str) -> str:
    """حساب الهاش الرقمي SHA-256 للملف لضمان عدم تكراره."""
    hasher = hashlib.sha256()
    with open(file_path, 'rb') as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def import_reference_paper(
    title: str,
    author: str = '',
    category: str = '',
    file_path: str = '',
    raw_text: str = ''
) -> dict:
    """
    استيراد بحث مرجعي مع الحفاظ على الصفحات ومنع التكرار.
    """
    title = title.strip()
    file_hash = ''

    # 1. فحص البصمة الرقمية والتكرار
    if file_path and os.path.exists(file_path):
        file_hash = compute_file_sha256(file_path)
    elif raw_text:
        file_hash = hashlib.sha256(raw_text.encode('utf-8')).hexdigest()
    else:
        file_hash = None

    if file_hash:
        existing_by_hash = document_repo.get_document_by_hash(file_hash)
        if existing_by_hash:
            return {
                'success': False,
                'is_duplicate': True,
                'error': f"هذا البحث موجود بالفعل في قاعدة الأبحاث المرجعية تحت عنوان: «{existing_by_hash['title']}»"
            }

    # فحص العنوان
    if document_repo.get_document_by_title(title):
        return {
            'success': False,
            'is_duplicate': True,
            'error': f"يوجد بحث مسجل مسبقاً بنفس العنوان: «{title}»"
        }

    # 2. استخراج الصفحات الفردية
    pages_data = []
    if file_path and os.path.exists(file_path):
        pages_data = extract_document_pages(file_path, enable_ocr=True)
        if not raw_text:
            raw_text = '\n\n'.join(p['text'] for p in pages_data if p['text'])
    elif raw_text:
        pages_data = [{'page_number': None, 'text': raw_text, 'is_ocr': False}]

    if not raw_text.strip():
        return {'success': False, 'error': 'لم يتم العثور على نص صالح للاستخراج من هذا الملف'}

    # 3. التقطيع إلى فقرات
    segments_data = segment_pages(pages_data, min_words=4)

    # 4. تصنيف التخصص إن لم يُحدد
    if not category or category == 'عام':
        category = categorize_text(raw_text)

    # 5. التخزين في قاعدة البيانات
    doc = document_repo.add_document(
        title=title,
        author=author,
        category=category,
        file_path=file_path,
        file_hash=file_hash,
        pages_data=pages_data,
        segments_data=segments_data
    )

    # 6. تحديث الفهرس
    invalidate_pipeline_index()
    build_pipeline_index()

    return {
        'success': True,
        'id': doc['id'],
        'title': doc['title'],
        'author': doc['author'],
        'category': doc['category'],
        'pages_count': len(pages_data),
        'segments_count': len(segments_data)
    }
