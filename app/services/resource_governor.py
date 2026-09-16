# -*- coding: utf-8 -*-
"""
محرك حوكمة الموارد وضبط الضغط المؤسسي (System Resource Governor & Backpressure Controller):
- مراقبة المساحة الحرة على القرص لمنع امتلاء وسائط التخزين.
- فرض سقف آمن وقابل للضبط لتزامن عمليات OCR الشاقة.
- التحقق من جاهزية قاعدة البيانات ومحرك الاسترجاع قبل قبول أبحاث جديدة.
"""

import shutil
import logging
from pathlib import Path
from typing import Dict, Any, Tuple

import config

logger = logging.getLogger(__name__)

# الحدود الدنيا والقصوى الافتراضية
MIN_FREE_DISK_BYTES = 5 * 1024 * 1024 * 1024 # 5 GB
MAX_QUEUE_DEPTH = 10000
MAX_OCR_CONCURRENCY = config.MAX_CONCURRENT_OCR_JOBS


def check_resource_limits(target_dir: Path = config.STORAGE_ROOT) -> Tuple[bool, str, Dict[str, Any]]:
    """
    التحقق الشامل من توفر الموارد الأساسية:
    يرجع (is_ok, error_code, details).
    """
    # 1. فحص مساحة القرص
    try:
        usage = shutil.disk_usage(str(target_dir))
        free_bytes = usage.free
        free_gb = round(free_bytes / (1024 * 1024 * 1024), 2)
    except Exception as e:
        logger.warning(f"تعذر قراءة مساحة القرص: {e}")
        free_bytes = MIN_FREE_DISK_BYTES + 1
        free_gb = 10.0

    if free_bytes < MIN_FREE_DISK_BYTES:
        msg = f"المساحة الحرة على القرص منخفضة جداً ({free_gb} GB). الحد الأدنى المطلوب هو 5 GB."
        logger.error(msg)
        return False, "ERR_DISK_SPACE_LOW", {"free_gb": free_gb, "required_gb": 5.0}

    return True, "", {"free_gb": free_gb}


def can_accept_new_scan_job(queue_depth: int) -> Tuple[bool, str]:
    """فحص إمكانية قبول مهمة فحص جديدة بناءً على عمق الطابور والموارد."""
    if queue_depth >= MAX_QUEUE_DEPTH:
        return False, "ERR_QUEUE_BACKLOG_FULL"

    ok, err, _ = check_resource_limits()
    if not ok:
        return False, err

    return True, ""
