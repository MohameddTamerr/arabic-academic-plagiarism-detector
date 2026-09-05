# -*- coding: utf-8 -*-
"""
إعدادات التسجيل الهيكلي والتحصين الخصوصي (Structured Logging & Privacy Redaction):
- تسجيل محلي أوفلاين بالكامل باستخدام RotatingFileHandler بتدوير محكوم (10MB x 5 ملفات).
- تشفير/حجب تلقائي للبيانات الحساسة وكلمات المرور والرموز السرية ومسارات نظام التشغيل.
- حماية تامة ضد هجمات حقن السجلات (Log Injection / CRLF Sanitization).
- تتبع سياق الطلب عبر Request ID موحد ومستقل.
- معالجة آمنة لفشل إنشاء مجلد السجلات بالتحويل التلقائي للكونسول دون انهيار الخادم.
"""

import os
import re
import sys
import json
import uuid
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any, Dict
from flask import has_request_context, g, request

import config

# الكلمات المفتاحية المحظورة الحساسة
_SENSITIVE_KEYS = {
    'password', 'password_hash', 'new_password', 'old_password',
    'token', 'auth_token', 'jwt', 'secret', 'secret_key',
    'cookie', 'session', 'csrf_token', 'csrf', 'authorization',
    'full_text', 'extracted_text', 'evidence', 'matched_text',
    'raw_content', 'vectors', 'embeddings', 'connection_string'
}

# نمط التعرف على المسارات المطلقة الحساسة
_PATH_PATTERN = re.compile(r'([A-Za-z]:\\[^"\'\s\<\>]+|/(?:Users|home|tmp|var)/[^"\'\s\<\>]+)')

# نمط محارف التحكم وحقن السجلات
_CONTROL_CHAR_PATTERN = re.compile(r'[\r\n\x00-\x1f\x7f-\x9f]')

_LOGGING_INITIALIZED = False


def get_request_id() -> str:
    """استرجاع معرف تتبع الطلب الحالي أو توليد معرف فريد."""
    if has_request_context():
        if not hasattr(g, 'request_id'):
            g.request_id = uuid.uuid4().hex
        return g.request_id
    return f"bg-{uuid.uuid4().hex[:8]}"


def sanitize_log_string(text: str, max_len: int = 1000) -> str:
    """تنقية النصوص من محارف التحكم والمسارات المطلقة وتقليص الطول."""
    if not isinstance(text, str):
        text = str(text)
    # 1. إزالة محارف الحقن وتسطير السطور الجديدة
    cleaned = _CONTROL_CHAR_PATTERN.sub(' ', text)
    # 2. استبدال المسارات المطلقة الحساسة
    cleaned = _PATH_PATTERN.sub('[SECURE_LOCAL_PATH]', cleaned)
    # 3. حجب أي أسرار في السلاسل النصية
    for sens in ('password=', 'secret=', 'token=', 'key='):
        if sens in cleaned.lower():
            cleaned = re.sub(rf'{sens}[^\s,;&]+', f'{sens}[REDACTED]', cleaned, flags=re.IGNORECASE)
    # 4. تقليص الطول
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len] + '...[TRUNCATED]'
    return cleaned.strip()


def sanitize_log_dict(data: Any, depth: int = 0) -> Any:
    """تنقية القواميس والقوائم عودياً من البيانات السرية ونصوص الأبحاث."""
    if depth > 5:
        return '[MAX_DEPTH]'
    if isinstance(data, dict):
        cleaned = {}
        for k, v in data.items():
            k_str = str(k).lower()
            if any(sens in k_str for sens in _SENSITIVE_KEYS):
                cleaned[k] = '[REDACTED]'
            else:
                cleaned[k] = sanitize_log_dict(v, depth + 1)
        return cleaned
    elif isinstance(data, (list, tuple, set)):
        return [sanitize_log_dict(item, depth + 1) for item in data]
    elif isinstance(data, str):
        return sanitize_log_string(data)
    elif isinstance(data, (int, float, bool)) or data is None:
        return data
    return sanitize_log_string(str(data))


class PrivacyRedactionFilter(logging.Filter):
    """مرشح أمني يحجب الحقول السرية ويمنع حقن السجلات في كافة الرسائل."""
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            # تنقية رسالة السجل
            if isinstance(record.msg, str):
                record.msg = sanitize_log_string(record.msg)
            elif isinstance(record.msg, dict):
                record.msg = sanitize_log_dict(record.msg)

            # تنقية المعاملات args
            if record.args:
                if isinstance(record.args, tuple):
                    record.args = tuple(sanitize_log_dict(a) for a in record.args)
                elif isinstance(record.args, dict):
                    record.args = sanitize_log_dict(record.args)

            # حقن request_id إذا كان مفقوداً
            if not hasattr(record, 'request_id'):
                record.request_id = get_request_id()

            # إزالة مسارات الملفات الحساسة من اسم المسار البرمجي إن وجدت
            if hasattr(record, 'pathname') and record.pathname:
                record.pathname = sanitize_log_string(record.pathname)

        except Exception:
            pass
        return True


class StructuredJsonFormatter(logging.Formatter):
    """منسق سجلات مهيكل بصيغة JSON خفيفة وقابلة للتحليل المؤسسي."""
    def format(self, record: logging.LogRecord) -> str:
        now_iso = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')

        log_payload = {
            'timestamp': now_iso,
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'request_id': getattr(record, 'request_id', get_request_id()),
            'component': getattr(record, 'component', 'application'),
            'operation': getattr(record, 'operation', None),
            'error_code': getattr(record, 'error_code', None),
        }

        # إضافة بيانات استثنائية آمنة (إذا وجدت)
        if hasattr(record, 'safe_metadata') and isinstance(record.safe_metadata, dict):
            log_payload['metadata'] = sanitize_log_dict(record.safe_metadata)

        # تفاصيل الخطأ المحلي فقط مع حجب المسارات والأسرار
        if record.exc_info:
            log_payload['exception_type'] = record.exc_info[0].__name__ if record.exc_info[0] else 'Exception'
            log_payload['exception_message'] = sanitize_log_string(str(record.exc_info[1]))

        return json.dumps(log_payload, ensure_ascii=False)


def setup_logging(app=None) -> None:
    """
    تهيئة وإعداد منظومة التسجيل المركزي للمنظومة:
    - إنشاء مجلد logs إذا لم يكن موجوداً.
    - إضافة RotatingFileHandler محكوم (10MB x 5 ملفات).
    - تعيين مرشح الخصوصية والمنسق المهيكل.
    - معالجة آمنة ومرنة في حال تعذر الكتابة على القرص.
    """
    global _LOGGING_INITIALIZED

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # التحقق من عدم تكرار إضافة المعالجات (Idempotent Configuration)
    has_file_handler = any(isinstance(h, RotatingFileHandler) for h in root_logger.handlers)

    if not has_file_handler:
        try:
            log_dir = Path(getattr(config, 'LOGS_DIR', Path(config.BASE_DIR) / 'logs'))
            log_dir.mkdir(parents=True, exist_ok=True)
            
            # 1. سجل التطبيق العام (INFO+)
            app_log_file = log_dir / 'application.log'
            file_handler = RotatingFileHandler(
                filename=str(app_log_file),
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding='utf-8'
            )
            file_handler.setLevel(logging.INFO)
            file_handler.addFilter(PrivacyRedactionFilter())
            file_handler.setFormatter(StructuredJsonFormatter())
            root_logger.addHandler(file_handler)

            # 2. سجل الأخطاء والتحذيرات المخصص (WARNING+)
            error_log_file = log_dir / 'errors.log'
            error_handler = RotatingFileHandler(
                filename=str(error_log_file),
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding='utf-8'
            )
            error_handler.setLevel(logging.WARNING)
            error_handler.addFilter(PrivacyRedactionFilter())
            error_handler.setFormatter(StructuredJsonFormatter())
            root_logger.addHandler(error_handler)
        except Exception as e:
            # Fallback آمن للكونسول دون تعطيل بدء تشغيل الخادم
            sys.stderr.write(f"Warning: Failed to initialize file logger: {e}\n")

    # معالج كونسول في بيئة التطوير
    has_console = any(isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler) for h in root_logger.handlers)
    if not has_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.addFilter(PrivacyRedactionFilter())
        console_handler.setFormatter(StructuredJsonFormatter())
        root_logger.addHandler(console_handler)

    _LOGGING_INITIALIZED = True


def get_logger(name: str) -> logging.Logger:
    """استرجاع كائن تسجيل محصن بالاسم."""
    logger = logging.getLogger(name)
    return logger


def log_operational_event(
    level: int,
    message: str,
    component: str = "application",
    operation: Optional[str] = None,
    error_code: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    exc_info: bool = False
) -> None:
    """دالة مساعدة مريحة لتسجيل الأحداث التشغيلية المهيكلة."""
    logger = logging.getLogger(f"ops.{component}")
    extra = {
        'component': component,
        'operation': operation,
        'error_code': error_code,
        'safe_metadata': metadata or {},
        'request_id': get_request_id()
    }
    logger.log(level, message, extra=extra, exc_info=exc_info)
