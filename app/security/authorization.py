# -*- coding: utf-8 -*-
"""
طبقة الحماية والتفويض المركزية (Institutional Authorization Layer):
- التحقق الصارم من هوية المستخدم والمصادقة الموثوقة عبر الجلسة أو سياق السيرفر g.
- منع الثقة في ترويسات العميل العشوائية مثل X-User-Role أو X-Admin كحد أمني.
- فحص الصلاحيات المعيارية قبل تنفيذ أي عمليات حساسة في الـ Backend.
- توثيق محاولات الوصول غير المصرح بها في سجل التدقيق الأمني (Audit Trail).
"""

from functools import wraps
from typing import Optional, Any, Callable, List
from flask import request, jsonify, g, session as flask_session, current_app

from app.security.permissions import (
    Permission, Role, get_role_permissions, normalize_role, ROLE_LABELS_AR
)


def get_authenticated_user() -> Optional[dict]:
    """
    استرجاع بيانات المستخدم الموثقة رسمياً من جهة الخادم:
    - التحقق من سياق g.current_user أولاً.
    - التحقق من مهلة خمول الجلسة والسقف الزمني المطلق للجلسة.
    - التحقق من حالة المستخدم في قاعدة البيانات (نشط / محذوف).
    - التحقق من إصدار أمان الجلسة (session_version) للإلغاء الفوري.
    - جلب الدور المحدث مباشرة من قاعدة البيانات لضمان سريان تغيير الأدوار فوراً.
    - منع الثقة في أي ترويسات عشوائية من العميل كمرجعية تفويض في الإنتاج.
    """
    import time
    import config

    # 1. فحص سياق g
    if hasattr(g, 'current_user') and g.current_user:
        u = g.current_user
        if isinstance(u, dict):
            return u
        return {
            'id': getattr(u, 'id', None),
            'username': getattr(u, 'username', ''),
            'full_name': getattr(u, 'full_name', ''),
            'role': getattr(u, 'role', ''),
            'department': getattr(u, 'department', '')
        }

    # 2. فحص جلسة العمل الموقعة في Flask
    try:
        user_id = flask_session.get('user_id')
        if user_id:
            now_ts = time.time()

            # أ. فحص مهلة خمول الجلسة (Idle Timeout)
            idle_timeout_sec = getattr(config, 'AUTH_SESSION_IDLE_TIMEOUT_MINUTES', 30) * 60
            last_activity = flask_session.get('last_activity')
            if last_activity and (now_ts - float(last_activity)) > idle_timeout_sec:
                flask_session.clear()
                g.session_expired = True
                return None

            # ب. فحص السقف الزمني المطلق للجلسة (Absolute Lifetime)
            max_lifetime_sec = getattr(config, 'AUTH_SESSION_MAX_LIFETIME_HOURS', 8) * 3600
            auth_time = flask_session.get('auth_time')
            if auth_time and (now_ts - float(auth_time)) > max_lifetime_sec:
                flask_session.clear()
                g.session_expired = True
                return None

            # ج. التحقق المباشر من قاعدة البيانات للإصدار والحالة والدور الحي
            from app.repositories.base_repo import get_session
            from app.models.schema import User
            with get_session() as session:
                db_user = session.query(User).filter(User.id == user_id).first()
                if not db_user:
                    # في بيئة الاختبارات، إذا حُدد الدور صراحة في الجلسة، يُعتمد كجلسة اختبار اصطناعية
                    if current_app and current_app.config.get('TESTING') and flask_session.get('role'):
                        return {
                            'id': user_id,
                            'username': flask_session.get('username', 'test_user'),
                            'full_name': flask_session.get('full_name', flask_session.get('username', 'test_user')),
                            'role': flask_session.get('role'),
                            'department': flask_session.get('department', '')
                        }
                    # المستخدم تم حذفه
                    flask_session.clear()
                    return None

                if getattr(db_user, 'is_active', 1) == 0:
                    # حساب المستخدم معطل
                    flask_session.clear()
                    return None

                sess_ver = flask_session.get('session_version', 1)
                db_ver = getattr(db_user, 'session_version', 1)
                if sess_ver != db_ver:
                    # تم إبطال الجلسة بسبب تغيير كلمة المرور أو إعادة التعيين أو تسجيل الخروج الإجباري
                    flask_session.clear()
                    return None

                # تحديث وقت آخر نشاط للجلسة
                flask_session['last_activity'] = now_ts

                return {
                    'id': db_user.id,
                    'username': db_user.username,
                    'full_name': db_user.full_name,
                    'role': db_user.role,
                    'department': getattr(db_user, 'department', ''),
                    'must_change_password': int(getattr(db_user, 'must_change_password', 0) or 0),
                    'must_enroll_recovery': int(getattr(db_user, 'must_enroll_recovery', 0) or 0)
                }

        # فحص role مباشر في الجلسة (للجلسات الاصطناعية المؤقتة)
        session_role = flask_session.get('role')
        if session_role:
            return {
                'id': flask_session.get('user_id', 1),
                'username': flask_session.get('username', 'test_user'),
                'full_name': flask_session.get('full_name', flask_session.get('username', 'test_user')),
                'role': session_role,
                'department': flask_session.get('department', '')
            }
    except Exception:
        pass

    # 3. دعم بيئة الاختبارات الموروثة (Test Compatibility Mode) عند تفعيل TESTING فقط ودون تفعيل STRICT_AUTH
    if current_app and current_app.config.get('TESTING'):
        if not current_app.config.get('STRICT_AUTH'):
            test_role = request.headers.get('X-User-Role')
            test_name = request.headers.get('X-User-Name') or 'test_user'
            test_dept = request.headers.get('X-User-Department') or ''
            if test_role:
                return {
                    'id': int(request.headers.get('X-User-Id') or 1),
                    'username': test_name,
                    'full_name': test_name,
                    'role': test_role,
                    'department': test_dept
                }
            # للمسارات التشغيلية في الاختبارات السابقة الموروثة التي لم تنشئ جلسة صريحة
            return {
                'id': 1,
                'username': 'legacy_test_admin',
                'full_name': 'مدير اختبار قديم',
                'role': Role.LEGACY_ADMIN,
                'department': ''
            }

    return None


def has_permission(user_or_role: Any, permission_name: str) -> bool:
    """
    التحقق مما إذا كان المستخدم يملك الصلاحية المحددة.
    """
    if not user_or_role or not permission_name:
        return False

    role = ''
    if isinstance(user_or_role, str):
        role = user_or_role
    elif isinstance(user_or_role, dict):
        role = user_or_role.get('role', '')
    else:
        role = getattr(user_or_role, 'role', '')

    perms = get_role_permissions(role)
    return permission_name in perms


def check_unit_access(user: Optional[dict], target_department: Optional[str]) -> bool:
    """
    التحقق الصارم من نطاق الوحدة / القسم المؤسسي (Organizational Unit Scope Check):
    - SYSTEM_ADMIN / LEGACY_ADMIN: صلاحية كاملة على كافة الوحدات.
    - إذا كان المرجع أو البحث عاماً أو بدون قسم (عام / general / فارغ): متاح لكافة المحكمين والوحدات.
    - إذا كان المستخدم غير مقيد بقسم محدد (فارغ): متاح له الوصول لكافة الأقسام.
    - إذا كان المستخدم مقيداً بقسم محدد والهدف مقيد بقسم مختلف: يُمنع الوصول لحماية الخصوصية وعزل الوحدات (IDOR).
    """
    if not user:
        return False
    role = normalize_role(user.get('role', ''))
    if role in (Role.SYSTEM_ADMIN, Role.LEGACY_ADMIN):
        return True

    user_dept = (user.get('department') or '').strip().lower()
    target_dept = (target_department or '').strip().lower()

    # إذا كان القسم المستهدف عاماً أو غير محدد، فهو متاح للجميع
    if not target_dept or target_dept in ('عام', 'general', 'all', 'default'):
        return True

    # إذا كان المستخدم عاماً بدون تقييد لوحدة معينة
    if not user_dept or user_dept in ('عام', 'general', 'all'):
        return True

    return user_dept == target_dept


def can_view_research(user: Any, research: Optional[dict] = None) -> bool:
    """
    التحقق من صلاحية استعراض البحث وفق سياسة نطاق البيانات المؤسسية (Data Scoping).
    """
    if not user:
        return False
    if not has_permission(user, Permission.RESEARCH_VIEW):
        return False

    if research and isinstance(user, dict):
        role = normalize_role(user.get('role', ''))
        username = user.get('username', '')

        # الأدوار الإدارية العليا تملك صلاحية الاطلاع العام
        if role in (Role.SYSTEM_ADMIN, Role.LEGACY_ADMIN):
            return True

        # فحص نطاق الوحدة/القسم
        res_dept = research.get('department') or research.get('category', '')
        if not check_unit_access(user, res_dept):
            return False

        # مدخل البيانات (data_entry) يقتصر نطاقه على الأبحاث التي قام برفعها بنفسه
        if role == Role.DATA_ENTRY:
            created_by = research.get('created_by', '')
            if created_by and created_by != username:
                return False

    return True


def can_view_thesis(user: Any, thesis: Optional[dict] = None) -> bool:
    """التحقق من صلاحية استعراض الرسالة العلمية وفق سياسة نطاق الوحدة."""
    if not user:
        return False
    if not has_permission(user, Permission.THESIS_VIEW):
        return False
    if not thesis:
        return True
    if isinstance(user, dict):
        role = normalize_role(user.get('role', ''))
        if role in (Role.SYSTEM_ADMIN, Role.LEGACY_ADMIN):
            return True
        dept = thesis.get('department', '')
        return check_unit_access(user, dept)
    return True


def can_view_report(user: Any, report: Optional[dict] = None) -> bool:
    """التحقق من صلاحية استعراض التقرير وفق نطاق الوحدة وفصل المهام."""
    if not user:
        return False
    if not has_permission(user, Permission.REPORT_VIEW):
        return False
    if not report:
        return True
    if isinstance(user, dict):
        role = normalize_role(user.get('role', ''))
        if role in (Role.SYSTEM_ADMIN, Role.LEGACY_ADMIN):
            return True
        dept = report.get('department', '') or report.get('category', '')
        return check_unit_access(user, dept)
    return True


def record_access_denied_audit(user: Optional[dict], permission_needed: str, action_desc: str = ''):
    """توثيق محاولة الوصول غير المصرح بها في سجل التدقيق المؤسسي."""
    try:
        from app.services import audit_service
        audit_service.record_event(
            action="authorization.access_denied",
            category="security",
            user=user,
            success=False,
            failure_reason_code="FORBIDDEN_INSUFFICIENT_PERMISSIONS",
            metadata={
                'required_permission': permission_needed,
                'path': request.path if request else '',
                'method': request.method if request else '',
                'user_role': user.get('role') if user else 'anonymous',
                'description': action_desc or 'محاولة تنفيذ إجراء دون امتلاك الصلاحية المطلوبة'
            }
        )
    except Exception:
        pass


def require_authenticated():
    """محدد للتأكد من تسجيل الدخول أولاً."""
    def decorator(fn: Callable):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            from app.errors.handlers import make_error_response
            from app.errors.error_codes import ErrorCode
            user = get_authenticated_user()
            if not user:
                return make_error_response('يجب تسجيل الدخول أولاً للوصول إلى هذه الخدمة.', code=ErrorCode.AUTH_REQUIRED, status_code=401)
            if user.get('must_change_password') or user.get('must_enroll_recovery'):
                return make_error_response(
                    'يجب إكمال إعداد كلمة المرور وبطاقة الاسترداد أولاً.',
                    code='ACCOUNT_SETUP_REQUIRED',
                    status_code=428
                )
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def require_permission(permission_name: str):
    """
    محدد برمجي (Decorator) للتحقق الصارم من امتلاك المستخدم للصلاحية المطلوبة في السيرفر.
    إذا كان المستخدم غير مسجل دخول -> 401 Unauthorized.
    إذا كان مسجلاً ولا يملك الصلاحية -> 403 Forbidden مع توثيق الحدث في سجل التدقيق.
    """
    def decorator(fn: Callable):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            from app.errors.handlers import make_error_response
            from app.errors.error_codes import ErrorCode
            user = get_authenticated_user()
            if not user:
                # إذا لم يكن هناك مستخدم مسجل دخول
                record_access_denied_audit(None, permission_name, "طلب من مستخدم غير مسجل دخول")
                return make_error_response('غير مصرح: يجب تسجيل الدخول للوصول إلى هذه الخدمة.', code=ErrorCode.AUTH_REQUIRED, status_code=401)

            if user.get('must_change_password') or user.get('must_enroll_recovery'):
                return make_error_response(
                    'يجب إكمال إعداد كلمة المرور وبطاقة الاسترداد أولاً.',
                    code='ACCOUNT_SETUP_REQUIRED',
                    status_code=428
                )

            if not has_permission(user, permission_name):
                record_access_denied_audit(user, permission_name, f"المستخدم {user.get('username')} لا يملك صلاحية {permission_name}")
                return make_error_response(
                    f'غير مصرح: ليس لديك الصلاحية المطلوبة ({permission_name}) لتنفيذ هذا الإجراء.',
                    code=ErrorCode.AUTH_FORBIDDEN,
                    status_code=403,
                    details={'required_permission': permission_name}
                )

            return fn(*args, **kwargs)
        return wrapper
    return decorator


def require_any_permission(*permission_names: str):
    """
    محدد برمجي للتحقق من امتلاك المستخدم لأي صلاحية من قائمة محددة.
    """
    def decorator(fn: Callable):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            from app.errors.handlers import make_error_response
            from app.errors.error_codes import ErrorCode
            user = get_authenticated_user()
            if not user:
                record_access_denied_audit(None, ', '.join(permission_names), "طلب من مستخدم غير مسجل دخول")
                return make_error_response('غير مصرح: يجب تسجيل الدخول للوصول إلى هذه الخدمة.', code=ErrorCode.AUTH_REQUIRED, status_code=401)

            if user.get('must_change_password') or user.get('must_enroll_recovery'):
                return make_error_response(
                    'يجب إكمال إعداد كلمة المرور وبطاقة الاسترداد أولاً.',
                    code='ACCOUNT_SETUP_REQUIRED',
                    status_code=428
                )

            has_any = any(has_permission(user, p) for p in permission_names)
            if not has_any:
                record_access_denied_audit(user, ', '.join(permission_names), f"المستخدم {user.get('username')} لا يملك أي من الصلاحيات المطلوبة")
                return make_error_response(
                    'غير مصرح: ليس لديك الصلاحيات الكافية لتنفيذ هذا الإجراء.',
                    code=ErrorCode.AUTH_FORBIDDEN,
                    status_code=403,
                    details={'required_permissions': list(permission_names)}
                )

            return fn(*args, **kwargs)
        return wrapper
    return decorator
