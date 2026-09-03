# -*- coding: utf-8 -*-
"""
خدمة إدارة الإعدادات والقواعد الأكاديمية (Academic Settings Service):
- إدارة الأوزان والعتبات والحدود المسموحة (Thresholds & Allowances).
- تخزين الإعدادات محلياً واسترجاعها بأمان مع قيم افتراضية موثوقة.
"""

import json
import logging
from pathlib import Path
import config

logger = logging.getLogger(__name__)


def get_current_settings() -> dict:
    """استرجاع الإعدادات المحفوظة أو الإعدادات الافتراضية."""
    settings = dict(config.DEFAULT_SETTINGS)
    settings_file: Path = config.SETTINGS_FILE

    if settings_file.exists():
        try:
            with open(settings_file, 'r', encoding='utf-8') as f:
                saved = json.load(f)
                settings.update(saved)
        except Exception as e:
            logger.warning(f"تعذر قراءة ملف الإعدادات: {e}")

    if 'tfidf_threshold' in settings and 'cosine_threshold' not in settings:
        settings['cosine_threshold'] = settings['tfidf_threshold']

    return settings


def save_settings(new_settings: dict) -> tuple[bool, str]:
    """تحديث الإعدادات وحفظها على القرص مع التحقق من صحة المدخلات."""
    current = get_current_settings()

    try:
        if 'shingle_size' in new_settings:
            val = int(new_settings['shingle_size'])
            if 2 <= val <= 15:
                current['shingle_size'] = val

        if 'jaccard_threshold' in new_settings:
            val = float(new_settings['jaccard_threshold'])
            if 0.05 <= val <= 1.0:
                current['jaccard_threshold'] = val

        if 'tfidf_threshold' in new_settings:
            val = float(new_settings['tfidf_threshold'])
            if 0.05 <= val <= 1.0:
                current['tfidf_threshold'] = val
                current['cosine_threshold'] = val
        elif 'cosine_threshold' in new_settings:
            val = float(new_settings['cosine_threshold'])
            if 0.05 <= val <= 1.0:
                current['tfidf_threshold'] = val
                current['cosine_threshold'] = val

        if 'semantic_threshold' in new_settings:
            val = float(new_settings['semantic_threshold'])
            if 0.05 <= val <= 1.0:
                current['semantic_threshold'] = val

        if 'min_sentence_words' in new_settings:
            val = int(new_settings['min_sentence_words'])
            if 2 <= val <= 20:
                current['min_sentence_words'] = val

        if 'allowed_similarity_pct' in new_settings:
            val = float(new_settings['allowed_similarity_pct'])
            if 0.0 <= val <= 100.0:
                current['allowed_similarity_pct'] = val

        if 'words_per_page' in new_settings:
            val = int(new_settings['words_per_page'])
            if 50 <= val <= 1000:
                current['words_per_page'] = val

        if 'max_allowed_pages_per_source' in new_settings:
            val = float(new_settings['max_allowed_pages_per_source'])
            if 0.5 <= val <= 50.0:
                current['max_allowed_pages_per_source'] = val

        if 'enable_semantic_model' in new_settings:
            current['enable_semantic_model'] = bool(new_settings['enable_semantic_model'])

        if 'enable_ocr' in new_settings:
            current['enable_ocr'] = bool(new_settings['enable_ocr'])

        if 'detection_profile' in new_settings:
            prof = str(new_settings['detection_profile']).upper()
            if prof in ('LIGHT', 'BALANCED', 'ADVANCED'):
                current['detection_profile'] = prof
                # ضبط تلقائي لمعايير النمط المحدد
                if prof == 'LIGHT':
                    current['enable_semantic_model'] = False
                elif prof in ('BALANCED', 'ADVANCED'):
                    current['enable_semantic_model'] = True

        with open(config.SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(current, f, ensure_ascii=False, indent=2)

        return True, "تم حفظ الإعدادات الأكاديمية بنجاح"
    except Exception as e:
        logger.error(f"فشل حفظ الإعدادات: {e}")
        return False, f"خطأ أثناء حفظ الإعدادات: {str(e)}"
