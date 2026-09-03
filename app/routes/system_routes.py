# -*- coding: utf-8 -*-
"""
مسارات تشخيص وصيانة المنظومة (System & Maintenance Routes):
- فحص الجاهزية الشاملة أوفلاين (Diagnostics).
- النسخ الاحتياطي وتنظيف الملفات المؤقتة.
"""

import os
from flask import Blueprint, jsonify

from app.services.system_service import run_system_diagnostics
from plagiarism_detector.core.db import create_database_backup, get_backups_list
import config

system_bp = Blueprint('system_bp', __name__)


@system_bp.route('/api/system/diagnostics', methods=['GET'])
def get_diagnostics():
    """فحص جاهزية النظام والمكونات أوفلاين."""
    return jsonify(run_system_diagnostics())


@system_bp.route('/api/admin/backup', methods=['POST'])
def backup_database():
    """إنشاء نسخة احتياطية فورية لقاعدة البيانات."""
    try:
        path = create_database_backup()
        return jsonify({'success': True, 'filename': os.path.basename(path), 'message': 'تم إنشاء النسخة الاحتياطية بنجاح'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@system_bp.route('/api/admin/backups', methods=['GET'])
def list_backups():
    """قائمة النسخ الاحتياطية السابقة."""
    return jsonify({'backups': get_backups_list()})


@system_bp.route('/api/admin/cleanup_temp', methods=['POST'])
def cleanup_temp():
    """تنظيف الملفات المؤقتة."""
    cleaned = 0
    temp_dir = config.TEMP_UPLOAD_DIR
    if temp_dir.exists():
        for f in temp_dir.iterdir():
            if f.is_file():
                try:
                    f.unlink()
                    cleaned += 1
                except Exception:
                    pass
    return jsonify({'success': True, 'cleaned_files_count': cleaned, 'message': 'تم تنظيف الملفات المؤقتة بنجاح'})
