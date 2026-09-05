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
    year: str = '',
    publisher: str = '',
    edition: str = '',
    document_type: str = 'paper',
    source_category: str = 'academic',
    category: str = '',
    file_path: str = '',
    raw_text: str = '',
    original_filename: str = '',
    added_by: str = 'system',
    notes: str = '',
    ownership_note: str = ''
) -> dict:
    """
    استيراد بحث مرجعي عبر خدمة حوكمة المراجع المركزية مع حفظ الهوية المستقرة وإصدار النسخة.
    """
    from app.services import corpus_governance_service
    return corpus_governance_service.add_reference_document(
        title=title,
        author=author,
        year=year,
        publisher=publisher,
        edition=edition,
        document_type=document_type,
        source_category=source_category,
        category=category,
        file_path=file_path,
        raw_text=raw_text,
        original_filename=original_filename,
        added_by=added_by,
        notes=notes,
        ownership_note=ownership_note
    )

