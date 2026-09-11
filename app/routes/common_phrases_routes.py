# -*- coding: utf-8 -*-
"""
مسارات إدارة الجمل المؤسسية الشائعة المخصصة (Custom Common Phrases Routes)
"""

import json
import logging
from flask import Blueprint, request, jsonify
from app.security.permissions import Permission
from app.security.authorization import require_permission
import config

logger = logging.getLogger(__name__)

common_phrases_bp = Blueprint('common_phrases_bp', __name__)

_CUSTOM_PHRASES_FILE = config.CONFIG_DIR / 'custom_phrases.json'


def _load_custom_phrases() -> list:
    try:
        if _CUSTOM_PHRASES_FILE.exists():
            with open(_CUSTOM_PHRASES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    return [str(p) for p in data if p]
    except Exception as e:
        logger.warning(f"تعذر تحميل الجمل المخصصة: {e}")
    return []


def _save_custom_phrases(phrases: list) -> bool:
    try:
        config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(_CUSTOM_PHRASES_FILE, 'w', encoding='utf-8') as f:
            json.dump(phrases, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"تعذر حفظ الجمل المخصصة: {e}")
        return False


def _reload_custom_phrases_in_memory(custom: list):
    try:
        from plagiarism_detector.filters import common_phrases as cp_module
        from plagiarism_detector.preprocessing.normalizer import normalize_aggressive
        combined = cp_module.EXPANDED_COMMON_INSTITUTIONAL_MARKERS + custom
        cp_module._NORM_MARKERS = [(m, normalize_aggressive(m)) for m in combined]
        cp_module._CUSTOM_PHRASES_RUNTIME = custom
    except Exception as e:
        logger.warning(f"تعذر تحديث القائمة في الذاكرة: {e}")


@common_phrases_bp.route('/api/common-phrases', methods=['GET'])
@require_permission(Permission.SETTINGS_VIEW)
def get_common_phrases():
    from plagiarism_detector.filters.common_phrases import EXPANDED_COMMON_INSTITUTIONAL_MARKERS
    custom = _load_custom_phrases()
    return jsonify({
        'default_phrases': EXPANDED_COMMON_INSTITUTIONAL_MARKERS,
        'custom_phrases': custom,
        'total': len(EXPANDED_COMMON_INSTITUTIONAL_MARKERS) + len(custom)
    })


@common_phrases_bp.route('/api/common-phrases', methods=['POST'])
@require_permission(Permission.SETTINGS_MANAGE)
def add_common_phrase():
    data = request.get_json(silent=True) or {}
    phrase = (data.get('phrase') or '').strip()
    if not phrase:
        return jsonify({'success': False, 'error': 'الجملة فارغة'}), 400
    custom = _load_custom_phrases()
    if phrase in custom:
        return jsonify({'success': False, 'error': 'الجملة موجودة مسبقا'}), 409
    custom.append(phrase)
    if _save_custom_phrases(custom):
        _reload_custom_phrases_in_memory(custom)
        return jsonify({'success': True, 'custom_phrases': custom, 'total_custom': len(custom)})
    return jsonify({'success': False, 'error': 'تعذر الحفظ'}), 500


@common_phrases_bp.route('/api/common-phrases/<int:index>', methods=['DELETE'])
@require_permission(Permission.SETTINGS_MANAGE)
def delete_common_phrase(index: int):
    custom = _load_custom_phrases()
    if index < 0 or index >= len(custom):
        return jsonify({'success': False, 'error': 'رقم خارج النطاق'}), 404
    removed = custom.pop(index)
    if _save_custom_phrases(custom):
        _reload_custom_phrases_in_memory(custom)
        return jsonify({'success': True, 'removed': removed, 'custom_phrases': custom})
    return jsonify({'success': False, 'error': 'تعذر الحفظ'}), 500
