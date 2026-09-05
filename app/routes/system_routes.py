# -*- coding: utf-8 -*-
"""
مسارات تشخيص وصيانة المنظومة والنسخ الاحتياطي (System, Backup & Disaster Recovery Routes):
- فحص الجاهزية الشاملة أوفلاين (Diagnostics).
- إنشاء، استعراض، والتحقق من النسخ الاحتياطية المؤسسية.
- الاستعادة الآمنة المحصنة مع التأكيد الصريح ونسخة الطوارئ المسبقة.
- تنظيف الملفات المؤقتة مع توثيق التدقيق الإداري.
"""

import os
from pathlib import Path
from flask import Blueprint, jsonify, request, send_file

from app.services.system_service import run_system_diagnostics
from app.services.system_health_service import get_system_health
from app.services import backup_service, audit_service
from app.security.permissions import Permission
from app.security.authorization import require_permission, get_authenticated_user
import config

system_bp = Blueprint('system_bp', __name__)


@system_bp.route('/api/system/ping', methods=['GET'])
def system_ping():
    """نقطة فحص سريعة وخفيفة للتأكد من جاهزية واستجابة الخادم عند بدء التشغيل."""
    return jsonify({
        'status': 'ok',
        'ready': True,
        'app': 'Arabic Academic Plagiarism Detector',
        'version': '2.7.0',
        'mode': 'portable' if getattr(config, 'PORTABLE_MODE', False) else 'standard'
    }), 200


@system_bp.route('/api/system/health', methods=['GET'])

@require_permission(Permission.SYSTEM_HEALTH_VIEW)
def get_system_health_route():
    """
    استرجاع الفحص التشخيصي الموحد لجاهزية وصحة النظام (صلاحية system.health.view).
    خفيف وسريع وأوفلاين ولا يُنشئ أي سجلات تدقيق لمنع التضخم.
    """
    health_data = get_system_health()
    return jsonify(health_data), 200


@system_bp.route('/api/system/diagnostics', methods=['GET'])
@require_permission(Permission.SYSTEM_HEALTH_VIEW)
def get_diagnostics():
    """فحص جاهزية النظام والمكونات أوفلاين (صلاحية system.health.view)."""
    return jsonify(run_system_diagnostics())


@system_bp.route('/api/admin/backup', methods=['POST'])
@require_permission(Permission.BACKUP_CREATE)
def backup_database():
    """
    إنشاء نسخة احتياطية مؤسسية شاملة ومتسقة (صلاحية backup.create).
    """
    current_user = get_authenticated_user()
    created_by = current_user.get('username') if current_user else 'system_admin'

    try:
        result = backup_service.create_institutional_backup(
            created_by=created_by,
            backup_type='full',
            label=request.form.get('label') or request.json.get('label') if request.is_json else ''
        )
        return jsonify({
            'success': True,
            'backup': result,
            'backup_id': result.get('backup_identifier'),
            'message': f"تم إنشاء النسخة الاحتياطية «{result.get('backup_identifier')}» بنجاح وتوثيق سلامتها."
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@system_bp.route('/api/admin/backups', methods=['GET'])
@require_permission(Permission.BACKUP_CREATE)
def list_backups_route():
    """استرجاع قائمة النسخ الاحتياطية المسجلة في الفهرس (صلاحية backup.create)."""
    backups = backup_service.backup_repo.list_backups()
    return jsonify({'success': True, 'backups': backups})


@system_bp.route('/api/admin/backups/<backup_id>/validate', methods=['POST'])
@require_permission(Permission.BACKUP_CREATE)
def validate_backup_route(backup_id: str):
    """التحقق من سلامة وصلاحية نسخة احتياطية محددة (صلاحية backup.create)."""
    res = backup_service.validate_backup(backup_id)
    if not res.get('valid'):
        return jsonify({'success': False, 'validation': res, 'error': res.get('error')}), 400
    return jsonify({'success': True, 'validation': res, 'message': 'تم التحقق من سلامة النسخة وصحة قواعد بياناتها بنجاح.'})


@system_bp.route('/api/admin/backups/<backup_id>/restore', methods=['POST'])
@require_permission(Permission.BACKUP_RESTORE)
def restore_backup_route(backup_id: str):
    """
    استعادة آمنة ومحصنة لنسخة احتياطية (صلاحية backup.restore).
    تتطلب تأكيداً صريحاً يطابق معرف النسخة backup_id.
    """
    current_user = get_authenticated_user()
    req_data = request.get_json(silent=True) or request.form or {}
    confirmation = req_data.get('confirmation', '').strip()

    if not confirmation:
        return jsonify({
            'success': False,
            'error': 'رمز التأكيد الصريح مطلوب لتنفيذ الاستعادة. يرجى إدخال معرف النسخة كرمز تأكيد.'
        }), 400

    try:
        result = backup_service.restore_institutional_backup(
            backup_identifier=backup_id,
            confirmation=confirmation,
            current_user=current_user
        )
        return jsonify(result), 200
    except ValueError as val_err:
        return jsonify({'success': False, 'error': str(val_err)}), 400
    except RuntimeError as run_err:
        return jsonify({'success': False, 'error': str(run_err)}), 409
    except Exception as e:
        return jsonify({'success': False, 'error': f"فشلت الاستعادة: {str(e)}"}), 500


@system_bp.route('/api/admin/backups/<backup_id>/download', methods=['GET'])
@require_permission(Permission.BACKUP_CREATE)
def download_backup_route(backup_id: str):
    """تحميل ملف حزمة النسخة الاحتياطية بأمان مع منع هجمات مسارات الملفات (صلاحية backup.create)."""
    entry = backup_service.backup_repo.get_backup_entry(backup_id)
    if not entry:
        return jsonify({'error': 'النسخة الاحتياطية غير مسجلة'}), 404

    backup_dir = backup_service.get_backup_dir()
    file_p = Path(entry['file_path']) if entry.get('file_path') else backup_dir / f"{backup_id}_full.zip"

    # التحقق من أن المسار يقع بأمان داخل مجلد النسخ الاحتياطية
    try:
        file_p = file_p.resolve()
        backup_dir = backup_dir.resolve()
        if not str(file_p).startswith(str(backup_dir)):
            return jsonify({'error': 'مسار غير مصرح به'}), 403
    except Exception:
        return jsonify({'error': 'خطأ في معالجة المسار'}), 400

    if not file_p.exists():
        return jsonify({'error': 'ملف النسخة الاحتياطية غير موجود على القرص'}), 404

    return send_file(
        str(file_p),
        as_attachment=True,
        download_name=entry.get('file_name', f"{backup_id}.zip"),
        mimetype='application/zip'
    )


@system_bp.route('/api/admin/cleanup_temp', methods=['POST'])
@require_permission(Permission.SYSTEM_MAINTENANCE)
def cleanup_temp():
    """تنظيف الملفات المؤقتة (صلاحية system.maintenance)."""
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

    audit_service.record_event(
        action="admin.cleanup_temp",
        category="admin",
        object_type="system",
        success=True,
        metadata={'cleaned_files_count': cleaned}
    )
    return jsonify({'success': True, 'cleaned_files_count': cleaned, 'message': 'تم تنظيف الملفات المؤقتة بنجاح'})


# ─── مسارات مراقبة وصيانة قاعدة البيانات (Phase 9 Database Hardening) ────────

@system_bp.route('/api/system/db_health', methods=['GET'])
@require_permission(Permission.SYSTEM_HEALTH_VIEW)
def get_db_health():
    """استرجاع الفحص الصحي والتشخيصي لقاعدة بيانات SQLite (صلاحية system.health.view)."""
    from app.services import db_health_service
    return jsonify(db_health_service.get_database_health())


@system_bp.route('/api/admin/db/quick_check', methods=['POST'])
@require_permission(Permission.SYSTEM_HEALTH_VIEW)
def run_db_quick_check():
    """تشغيل فحص سريع لسلامة الهيكل PRAGMA quick_check (صلاحية system.health.view)."""
    from app.services import db_health_service
    result = db_health_service.run_quick_check()
    return jsonify(result), 200 if result.get('success') else 500


@system_bp.route('/api/admin/db/integrity_check', methods=['POST'])
@require_permission(Permission.SYSTEM_MAINTENANCE)
def run_db_integrity_check():
    """تشغيل فحص عميق وشامل لسلامة SQLite PRAGMA integrity_check (صلاحية system.maintenance)."""
    from app.services import db_health_service
    result = db_health_service.run_deep_integrity_check()
    return jsonify(result), 200 if result.get('success') else 500


@system_bp.route('/api/admin/db/checkpoint', methods=['POST'])
@require_permission(Permission.SYSTEM_MAINTENANCE)
def run_db_checkpoint():
    """تنفيذ نقطة تفتيش لسجل المعاملات PRAGMA wal_checkpoint (صلاحية system.maintenance)."""
    from app.services import db_health_service
    req_data = request.get_json(silent=True) or request.form or {}
    mode = req_data.get('mode', 'PASSIVE')
    result = db_health_service.run_wal_checkpoint(mode=mode)
    return jsonify(result), 200 if result.get('success') else 500

