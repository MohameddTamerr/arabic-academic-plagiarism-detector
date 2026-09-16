# -*- coding: utf-8 -*-
"""
طبقة الحماية ضد تزوير الطلبات عبر المواقع (CSRF Protection Layer):
- توليد والتحقق من رموز CSRF المرتبطة بالجلسة (Session-Bound Cryptographic Tokens).
- حماية كافة المسارات المعدلة للحالة (POST, PUT, PATCH, DELETE).
- استثناء المسارات الآمنة (GET, HEAD, OPTIONS) ومسارات المصادقة التأسيسية.
- قبول الرمز عبر الترويسات (X-CSRF-Token / X-CSRFToken) أو مدخلات JSON/Form.
- منع تسجيل أو تسريب رموز CSRF في السجلات التشغيلية.
"""

import hmac
import secrets
import logging
from typing import Optional
from flask import request, session as flask_session, current_app, jsonify

import config
from app.errors.error_codes import ErrorCode
from app.errors.handlers import make_error_response

logger = logging.getLogger(__name__)

# المسارات المعفاة من فحص CSRF (مسارات تأسيس وتسجيل الدخول الأولي والاسترداد بدون جلسة)
CSRF_EXEMPT_ROUTES = {
    '/api/auth/login',
    '/api/auth/setup_first_admin',
    '/api/auth/setup_admin',
    '/api/auth/emergency_reset',
    '/api/recovery/decode_qr',
    '/api/recovery/verify_and_authorize',
    '/api/recovery/complete_reset',
}


def generate_csrf_token() -> str:
    """توليد أو استرجاع رمز CSRF مشفر ومربوط بالجلسة الحالية."""
    token = flask_session.get('_csrf_token')
    if not token:
        token = secrets.token_hex(32)
        flask_session['_csrf_token'] = token
    return token


def rotate_csrf_token() -> str:
    """تدوير رمز CSRF وتوليد قيمة عشوائية جديدة عند تغير حالة المصادقة."""
    token = secrets.token_hex(32)
    flask_session['_csrf_token'] = token
    return token



def validate_csrf_token() -> Optional[tuple]:
    """
    التحقق من صحة رمز CSRF للطلب الحالي.
    
    :return: None إذا كان الطلب سليماً أو معفياً، أو Tuple(response, status_code) عند الفشل.
    """
    if not getattr(config, 'AUTH_CSRF_ENABLED', True):
        return None

    # بيئة الاختبارات الافتراضية تعفى إلا إذا تم تفعيل الفحص صراحة
    if current_app and current_app.config.get('TESTING'):
        if not current_app.config.get('ENFORCE_CSRF_IN_TESTS'):
            return None

    # الطرق الآمنة لا تتطلب CSRF
    if request.method in ('GET', 'HEAD', 'OPTIONS'):
        return None

    # فحص المسارات المعفاة
    if request.path in CSRF_EXEMPT_ROUTES:
        return None

    # استرجاع الرمز المتوقع من الجلسة
    expected_token = flask_session.get('_csrf_token')
    if not expected_token:
        # جلسة بدون رمز CSRF لا يُسمح لها بتنفيذ عمليات تعديل حالة
        logger.warning(f"محاولة تنفيذ طلب {request.method} {request.path} دون وجود رمز CSRF في الجلسة.")
        return make_error_response(
            "رمز الحماية ضد تزوير الطلبات (CSRF) مفقود في الجلسة.",
            code=ErrorCode.CSRF_FAILED,
            status_code=403
        )

    # استخراج الرمز المرسل من الترويسة أو الجسم
    client_token = (
        request.headers.get('X-CSRF-Token') or
        request.headers.get('X-CSRFToken') or
        (request.form.get('csrf_token') if request.form else None)
    )

    if not client_token and request.is_json:
        data = request.get_json(silent=True) or {}
        if isinstance(data, dict):
            client_token = data.get('csrf_token')

    if not client_token or not hmac.compare_digest(str(expected_token), str(client_token)):
        logger.warning(f"فشل التحقق من رمز CSRF للطلب {request.method} {request.path}.")
        return make_error_response(
            "رمز الحماية ضد تزوير الطلبات (CSRF) غير صالح أو منتهي الصلاحية.",
            code=ErrorCode.CSRF_FAILED,
            status_code=403
        )

    return None
