# -*- coding: utf-8 -*-
"""
خدمة تشخيص وفحص جاهزية المنظومة أوفلاين (System Diagnostics Service):
- فحص جاهزية قاعدة البيانات SQLite / SQLAlchemy.
- فحص محركات استخراج PDF (PyMuPDF) و Word (python-docx).
- فحص محرك OCR المحلي (Tesseract) وملفات اللغة العربية.
- فحص النموذج الدلالي والتخزين المحلي ومساحة القرص.
"""

import os
import shutil
from pathlib import Path

import config
from app.repositories import base_repo, document_repo, user_repo
from plagiarism_detector.extraction.ocr_engine import check_ocr_availability
from plagiarism_detector.detection.semantic_matcher import check_semantic_model_availability


def run_system_diagnostics() -> dict:
    """إجراء فحص شامل لكافة مكونات النظام وإرجاع تقرير الجاهزية."""
    # 1. قاعدة البيانات
    db_status = {'ok': True, 'engine': 'SQLite' if 'sqlite' in config.DATABASE_URL else 'PostgreSQL', 'details': ''}
    try:
        doc_count = document_repo.get_document_count()
        db_status['details'] = f"الاتصال سليم. إجمالي المراجع المسجلة: {doc_count}"
        db_status['doc_count'] = doc_count
    except Exception as e:
        db_status['ok'] = False
        db_status['details'] = f"خطأ في الاتصال بقاعدة البيانات: {str(e)}"

    # 2. استخراج PDF
    pdf_status = {'ok': True, 'engine': 'PyMuPDF', 'details': 'مكتبة استخراج PDF جاهزة.'}
    try:
        import fitz
    except ImportError:
        pdf_status['ok'] = False
        pdf_status['details'] = 'مكتبة pymupdf غير متوفرة.'

    # 3. استخراج Word
    docx_status = {'ok': True, 'engine': 'python-docx', 'details': 'مكتبة استخراج Word جاهزة.'}
    try:
        import docx
    except ImportError:
        docx_status['ok'] = False
        docx_status['details'] = 'مكتبة python-docx غير متوفرة.'

    # 4. محرك OCR
    ocr_diag = check_ocr_availability()

    # 5. النموذج الدلالي
    semantic_diag = check_semantic_model_availability()
    from app.services.settings_service import get_current_settings
    settings = get_current_settings()
    semantic_diag['enabled_in_settings'] = settings.get('enable_semantic_model', False)

    # 6. التخزين ومساحة القرص
    storage_path = config.STORAGE_ROOT
    disk_info = {'ok': True, 'free_gb': 0.0, 'path': str(storage_path)}
    try:
        total, used, free = shutil.disk_usage(storage_path)
        disk_info['free_gb'] = round(free / (1024 ** 3), 2)
        disk_info['total_gb'] = round(total / (1024 ** 3), 2)
        disk_info['details'] = f"المساحة المتاحة: {disk_info['free_gb']} جيجابايت من إجمالي {disk_info['total_gb']} جيجابايت."
    except Exception as e:
        disk_info['ok'] = False
        disk_info['details'] = f"تعذر قراءة مساحة القرص: {e}"

    # 7. هل يحتاج النظام إعداد المدير لأول مرة؟
    needs_setup = user_repo.is_first_time_setup()

    return {
        'database': db_status,
        'pdf_extraction': pdf_status,
        'docx_extraction': docx_status,
        'ocr': ocr_diag,
        'semantic_model': semantic_diag,
        'storage': disk_info,
        'needs_first_time_setup': needs_setup,
        'offline_mode': True,
        'host': config.HOST,
        'port': config.PORT
    }
