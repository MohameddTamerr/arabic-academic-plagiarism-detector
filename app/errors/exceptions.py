# -*- coding: utf-8 -*-
"""
تصنيف الاستثناءات المنضبط للمنظومة (Narrow Application Exception Taxonomy):
- هيكلية استثناءات واضحة تعين كل خطأ لكود قياسي وحالة HTTP مناسبة.
- تحمل رسائل آمنة للمستخدم وسياقاً تشغيلياً آمناً للمسؤولين.
"""

from typing import Optional, Dict, Any
from app.errors.error_codes import ErrorCode


class ApplicationError(Exception):
    """الاستثناء الأساسي لكافة أخطاء التطبيق المعرفة."""
    def __init__(
        self,
        message: str = "حدث خطأ أثناء معالجة الطلب.",
        code: str = ErrorCode.INTERNAL_ERROR,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class ValidationError(ApplicationError):
    """خطأ في التحقق من صحة المدخلات أو المعاملات أو الملفات المرفوعة (400 / 413)."""
    def __init__(
        self,
        message: str = "البيانات المدخلة غير مكتملة أو غير صالحة.",
        code: str = ErrorCode.VALIDATION_ERROR,
        status_code: int = 400,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message=message, code=code, status_code=status_code, details=details)


class AuthenticationError(ApplicationError):
    """خطأ عدم وجود مصادقة أو انتهاء صلاحية الجلسة (401)."""
    def __init__(
        self,
        message: str = "يجب تسجيل الدخول أولاً للوصول إلى هذه الخدمة.",
        code: str = ErrorCode.AUTH_REQUIRED,
        status_code: int = 401,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message=message, code=code, status_code=status_code, details=details)


class AuthorizationError(ApplicationError):
    """خطأ محاولة الوصول لمورد دون امتلاك الصلاحية المطلوبة (403)."""
    def __init__(
        self,
        message: str = "غير مصرح: ليس لديك صلاحية لتنفيذ هذا الإجراء.",
        code: str = ErrorCode.AUTH_FORBIDDEN,
        status_code: int = 403,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message=message, code=code, status_code=status_code, details=details)


class NotFoundError(ApplicationError):
    """خطأ عدم العثور على المورد المطلوب (404)."""
    def __init__(
        self,
        message: str = "المورد أو العنصر المطلوب غير موجود.",
        code: str = ErrorCode.NOT_FOUND,
        status_code: int = 404,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message=message, code=code, status_code=status_code, details=details)


class ExtractionError(ApplicationError):
    """خطأ في استخراج النصوص أو قراءة الملف المرفوع (400)."""
    def __init__(
        self,
        message: str = "تعذر استخراج النص من الملف المرفوع.",
        code: str = ErrorCode.FILE_EXTRACTION_FAILED,
        status_code: int = 400,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message=message, code=code, status_code=status_code, details=details)


class IntegrityError(ApplicationError):
    """خطأ فشل التحقق من سلامة وبصمة الملف الرقمي (400)."""
    def __init__(
        self,
        message: str = "فشل التحقق من مطابقة وسلامة الملف الرقمي (SHA-256).",
        code: str = ErrorCode.FILE_INTEGRITY_FAILED,
        status_code: int = 400,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message=message, code=code, status_code=status_code, details=details)


class StorageError(ApplicationError):
    """خطأ في وحدة التخزين أو المساحة (500)."""
    def __init__(
        self,
        message: str = "حدث خطأ أثناء التعامل مع وحدة التخزين.",
        code: str = ErrorCode.STORAGE_ERROR,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message=message, code=code, status_code=status_code, details=details)


class BackupError(ApplicationError):
    """خطأ في إنشاء أو فحص النسخة الاحتياطية (500)."""
    def __init__(
        self,
        message: str = "فشلت عملية إنشاء أو فحص النسخة الاحتياطية.",
        code: str = ErrorCode.BACKUP_FAILED,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message=message, code=code, status_code=status_code, details=details)


class RestoreError(ApplicationError):
    """خطأ في استعادة النسخة الاحتياطية (500)."""
    def __init__(
        self,
        message: str = "فشلت عملية استعادة النسخة الاحتياطية.",
        code: str = ErrorCode.RESTORE_FAILED,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message=message, code=code, status_code=status_code, details=details)


class DatabaseError(ApplicationError):
    """خطأ في عمليات واستعلامات قاعدة البيانات (500)."""
    def __init__(
        self,
        message: str = "حدث خطأ أثناء معالجة بيانات قاعدة البيانات.",
        code: str = ErrorCode.DATABASE_ERROR,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message=message, code=code, status_code=status_code, details=details)
