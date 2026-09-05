# -*- coding: utf-8 -*-
"""
مسارات ضبط القواعد الأكاديمية (Settings Routes):
- جلب وتحديث العتبات والنسب والحدود المسموحة مع توثيق التعديلات في سجل التدقيق.
"""

from flask import Blueprint, request, jsonify
from app.services.settings_service import get_current_settings, save_settings
from app.services import audit_service
from app.security.permissions import Permission
from app.security.authorization import require_permission

settings_bp = Blueprint('settings_bp', __name__)


@settings_bp.route('/api/settings', methods=['GET'])
@require_permission(Permission.SETTINGS_VIEW)
def get_settings_route():
    """استرجاع الإعدادات الحالية (صلاحية settings.view)."""
    return jsonify(get_current_settings())


@settings_bp.route('/api/settings', methods=['POST'])
@require_permission(Permission.SETTINGS_MANAGE)
def update_settings_route():
    """تحديث الإعدادات الأكاديمية وتوثيق الحقول المعدلة (صلاحية settings.manage)."""
    data = request.get_json(silent=True) or request.form or {}
    changed_keys = list(data.keys()) if isinstance(data, dict) else []

    ok, msg = save_settings(data)
    if ok:
        audit_service.record_event(
            action="settings.updated",
            category="settings",
            object_type="settings",
            success=True,
            metadata={"changed_fields": changed_keys}
        )
        return jsonify({'success': True, 'message': msg, 'settings': get_current_settings()})

    audit_service.record_event(
        action="settings.update_failed",
        category="settings",
        object_type="settings",
        success=False,
        failure_reason_code="SETTINGS_VALIDATION_ERROR",
        metadata={"changed_fields": changed_keys}
    )
    return jsonify({'success': False, 'error': msg}), 400
