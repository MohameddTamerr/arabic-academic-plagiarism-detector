# -*- coding: utf-8 -*-
"""
مسارات ضبط القواعد الأكاديمية (Settings Routes):
- جلب وتحديث العتبات والنسب والحدود المسموحة.
"""

from flask import Blueprint, request, jsonify
from app.services.settings_service import get_current_settings, save_settings

settings_bp = Blueprint('settings_bp', __name__)


@settings_bp.route('/api/settings', methods=['GET'])
def get_settings_route():
    """استرجاع الإعدادات الحالية."""
    return jsonify(get_current_settings())


@settings_bp.route('/api/settings', methods=['POST'])
def update_settings_route():
    """تحديث الإعدادات الأكاديمية."""
    data = request.get_json(silent=True) or request.form or {}
    ok, msg = save_settings(data)
    if ok:
        return jsonify({'success': True, 'message': msg, 'settings': get_current_settings()})
    return jsonify({'success': False, 'error': msg}), 400
