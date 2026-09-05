# -*- coding: utf-8 -*-
"""
معالجات الأخطاء المركزية لمنظومة Flask (Centralized Error Handlers):
- توحيد مغلف استجابات الخطأ (Standardized Error Envelope).
- إرجاع رسائل عربية آمنة خالية تماماً من المسارات المطلقة أو نصوص SQL أو أسرار النظام.
- ربط كافة الاستجابات بمعرف الطلب الفريد (request_id).
- تسجيل تفاصيل الأخطاء وسياقها التشغيلي محلياً دون تسريبها للواجهة.
- التراجع التلقائي عن المعاملات غير المكتملة في قاعدة البيانات (Session Rollback).
"""

import logging
from typing import Tuple, Dict, Any, Optional
from flask import Flask, jsonify, request, g
from werkzeug.exceptions import HTTPException

from app.errors.error_codes import ErrorCode
from app.errors.exceptions import ApplicationError, DatabaseError, StorageError
from app.logging_config import get_request_id, log_operational_event
from app.repositories import base_repo

logger = logging.getLogger(__name__)


def make_error_response(
    message: str,
    code: str = ErrorCode.INTERNAL_ERROR,
    status_code: int = 400,
    details: Optional[Dict[str, Any]] = None
) -> Tuple[Any, int]:
    """
    إنشاء مغلف استجابة الخطأ الموحد للمنظومة:
    {
      "success": false,
      "error": {
        "code": "CODE_NAME",
        "message": "رسالة آمنة للمستخدم",
        "request_id": "..."
      },
      "message": "رسالة آمنة للمستخدم",
      "error_code": "CODE_NAME",
      "request_id": "..."
    }
    """
    req_id = get_request_id()
    ref_id = req_id[:8] if req_id else "unknown"
    error_dict = {
        'code': code,
        'message': message,
        'request_id': req_id,
        'reference_id': ref_id
    }
    if details:
        error_dict['details'] = details

    payload = {
        'success': False,
        'error': error_dict,
        'message': message,
        'error_code': code,
        'request_id': req_id,
        'reference_id': ref_id
    }
    return jsonify(payload), status_code


def register_error_handlers(app: Flask) -> None:
    """تسجيل معالجات الأخطاء المركزية على تطبيق Flask."""

    @app.errorhandler(ApplicationError)
    def handle_application_error(e: ApplicationError):
        """معالجة استثناءات التطبيق المعرفة هيكلياً."""
        log_operational_event(
            level=logging.WARNING if e.status_code < 500 else logging.ERROR,
            message=f"خطأ تطبيقي: {e.code} - {e.message}",
            component="application",
            error_code=e.code,
            metadata=e.details
        )
        safe_msg = e.message
        if e.status_code >= 500:
            if isinstance(e, DatabaseError) or e.code == ErrorCode.DATABASE_ERROR:
                safe_msg = "حدث خطأ أثناء معالجة بيانات قاعدة البيانات."
            elif isinstance(e, StorageError) or e.code == ErrorCode.STORAGE_ERROR:
                safe_msg = "حدث خطأ أثناء التعامل مع وحدة التخزين."

        return make_error_response(
            message=safe_msg,
            code=e.code,
            status_code=e.status_code,
            details=e.details
        )

    @app.errorhandler(400)
    def handle_400(e):
        return make_error_response(
            message="الطلب غير صالح أو تنقصه بعض المعاملات الأساسية.",
            code=ErrorCode.VALIDATION_ERROR,
            status_code=400
        )

    @app.errorhandler(401)
    def handle_401(e):
        return make_error_response(
            message="يجب تسجيل الدخول أولاً للوصول إلى هذه الخدمة.",
            code=ErrorCode.AUTH_REQUIRED,
            status_code=401
        )

    @app.errorhandler(403)
    def handle_403(e):
        return make_error_response(
            message="غير مصرح: ليس لديك صلاحية لتنفيذ هذا الإجراء.",
            code=ErrorCode.AUTH_FORBIDDEN,
            status_code=403
        )

    @app.errorhandler(404)
    def handle_404(e):
        return make_error_response(
            message="المورد أو الرابط المطلوب غير موجود.",
            code=ErrorCode.NOT_FOUND,
            status_code=404
        )

    @app.errorhandler(405)
    def handle_405(e):
        return make_error_response(
            message="طريقة الطلب غير مسموح بها لهذا المسار.",
            code=ErrorCode.METHOD_NOT_ALLOWED,
            status_code=405
        )

    @app.errorhandler(413)
    def handle_413(e):
        return make_error_response(
            message="حجم الملف المرفوع يتجاوز الحد الأقصى المسموح به في المنظومة.",
            code=ErrorCode.PAYLOAD_TOO_LARGE,
            status_code=413
        )

    @app.errorhandler(429)
    def handle_429(e):
        return make_error_response(
            message="تم تجاوز الحد المسموح به من الطلبات. يرجى الانتظار قليلاً.",
            code=ErrorCode.RATE_LIMITED,
            status_code=429
        )

    @app.errorhandler(500)
    def handle_500(e):
        _rollback_db_safely()
        log_operational_event(
            level=logging.ERROR,
            message="خطأ داخلي 500 في الخادم",
            component="server",
            error_code=ErrorCode.INTERNAL_ERROR,
            exc_info=True
        )
        return make_error_response(
            message="حدث خطأ داخلي غير متوقع في الخادم. يرجى تزويد الدعم الفني برقم التتبع.",
            code=ErrorCode.INTERNAL_ERROR,
            status_code=500
        )

    @app.errorhandler(Exception)
    def handle_unhandled_exception(e: Exception):
        """صائد الاستثناءات غير المعالجة لحماية الخادم من تسريب أي تفاصيل أو مسارات."""
        _rollback_db_safely()

        if isinstance(e, HTTPException):
            return make_error_response(
                message=e.description or "حدث خطأ أثناء معالجة الطلب.",
                code=ErrorCode.INTERNAL_ERROR,
                status_code=e.code or 500
            )

        log_operational_event(
            level=logging.ERROR,
            message=f"استثناء غير معالج: {type(e).__name__} - {str(e)}",
            component="server",
            error_code=ErrorCode.INTERNAL_ERROR,
            exc_info=True
        )

        return make_error_response(
            message="حدث خطأ داخلي غير متوقع. يرجى تزويد مسؤول النظام برقم التتبع.",
            code=ErrorCode.INTERNAL_ERROR,
            status_code=500
        )


def _rollback_db_safely():
    """التراجع الآمن عن أي معاملة غير مكتملة في قاعدة البيانات."""
    try:
        base_repo.scoped_session.rollback()
        base_repo.scoped_session.remove()
    except Exception:
        pass
