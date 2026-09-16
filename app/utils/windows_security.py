# -*- coding: utf-8 -*-
"""
وحدة الأمان وإدارة سمات ملفات نظام ويندوز (Windows Security & File Attribute Management):
- تطبيق سمة الإخفاء (FILE_ATTRIBUTE_HIDDEN) على مجلدات وملفات النظام الداخلية (Database, Config, papers.db).
- التحقق من وجود السمة البرمجية على المسارات المحددة.
- توضيح: سمة الإخفاء هي سمة استعراض في مستكشف ويندوز (UI Convenience) وليست تشفيراً.
"""

import sys
import os
import ctypes
import logging
from pathlib import Path
from typing import Union

logger = logging.getLogger(__name__)

# الثوابت القياسية لسمات ملفات ويندوز (Win32 File Attributes)
FILE_ATTRIBUTE_READONLY = 0x01
FILE_ATTRIBUTE_HIDDEN = 0x02
FILE_ATTRIBUTE_SYSTEM = 0x04
FILE_ATTRIBUTE_DIRECTORY = 0x10
FILE_ATTRIBUTE_ARCHIVE = 0x20
FILE_ATTRIBUTE_NORMAL = 0x80


def apply_windows_hidden_attribute(path_or_str: Union[str, Path]) -> bool:
    """
    تطبيق سمة الإخفاء (FILE_ATTRIBUTE_HIDDEN) على الملف أو المجلد في بيئة ويندوز.
    - يُحافظ على السمات الحالية ويُضيف سمة الإخفاء (Bitwise OR).
    - آمن ويعيد True تلقائياً في الأنظمة غير ويندوز (Safe No-Op).
    """
    if sys.platform != "win32":
        return True

    try:
        p_str = os.path.abspath(str(path_or_str))
        if not os.path.exists(p_str):
            return False

        attrs = ctypes.windll.kernel32.GetFileAttributesW(p_str)
        if attrs == -1 or attrs == 0xFFFFFFFF:
            return False

        if not (attrs & FILE_ATTRIBUTE_HIDDEN):
            new_attrs = attrs | FILE_ATTRIBUTE_HIDDEN
            result = ctypes.windll.kernel32.SetFileAttributesW(p_str, new_attrs)
            if result != 0:
                logger.debug(f"Applied FILE_ATTRIBUTE_HIDDEN to: {p_str}")
                return True
            else:
                err_code = ctypes.GetLastError()
                logger.warning(f"Failed to apply FILE_ATTRIBUTE_HIDDEN to {p_str} (Win32 Error: {err_code})")
                return False
        return True
    except Exception as e:
        logger.warning(f"Exception applying hidden attribute to {path_or_str}: {e}")
        return False


def is_windows_hidden(path_or_str: Union[str, Path]) -> bool:
    """
    التحقق مما إذا كان الملف أو المجلد يحمل سمة الإخفاء في نظام ويندوز.
    """
    if sys.platform != "win32":
        return False

    try:
        p_str = os.path.abspath(str(path_or_str))
        if not os.path.exists(p_str):
            return False

        attrs = ctypes.windll.kernel32.GetFileAttributesW(p_str)
        if attrs == -1 or attrs == 0xFFFFFFFF:
            return False

        return bool(attrs & FILE_ATTRIBUTE_HIDDEN)
    except Exception:
        return False


def hide_database_and_config_tree(
    database_dir: Union[str, Path],
    config_dir: Union[str, Path],
    db_file_path: Union[str, Path] = None
) -> None:
    """
    تطبيق سمة الإخفاء بشكل شامل على مجلد قاعدة البيانات ومجلد الإعدادات وملف papers.db.
    """
    if sys.platform != "win32":
        return

    # 1. إخفاء مجلد Database
    if database_dir:
        apply_windows_hidden_attribute(database_dir)

    # 2. إخفاء مجلد Config
    if config_dir:
        apply_windows_hidden_attribute(config_dir)

    # 3. إخفاء ملف قاعدة البيانات وملفات الـ WAL والـ SHM المرافقة
    if db_file_path:
        db_p = Path(db_file_path)
        if db_p.exists():
            apply_windows_hidden_attribute(db_p)
        wal_p = Path(f"{db_file_path}-wal")
        if wal_p.exists():
            apply_windows_hidden_attribute(wal_p)
        shm_p = Path(f"{db_file_path}-shm")
        if shm_p.exists():
            apply_windows_hidden_attribute(shm_p)
