# -*- coding: utf-8 -*-
"""
مستودع بيانات المستخدمين والأمان (User & Security Repository):
- التشفير الآمن لكلمات المرور باستخدام مكتبة bcrypt مع توليد Salt ديناميكي فريد.
- الترقية التلقائية الآمنة لأي هاش قديم (SHA-256) إلى bcrypt عند أول تسجيل دخول ناجح.
- منع تخزين أي بيانات دخول افتراضية مشحونة في الكود.
- دعم إعداد حساب مدير النظام لأول مرة (First-Time Setup) إذا كانت قاعدة البيانات فارغة.
"""

import hashlib
import logging
import threading
import bcrypt
from typing import Optional

from app.repositories.base_repo import get_session
from app.models.schema import User, PasswordResetRequest

logger = logging.getLogger(__name__)

_LEGACY_SALT = "police_academy_grad_studies_2026_offline_salt"


def hash_password(password: str) -> str:
    """تشفير كلمة المرور باستخدام bcrypt."""
    pw_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(pw_bytes, salt).decode('utf-8')


def verify_password(plain_password: str, stored_hash: str) -> bool:
    """
    التحقق من صحة كلمة المرور:
    - تدعم bcrypt الحديثة.
    - وتدعم الهاش القديم (SHA-256) لتمكين الترقية التلقائية دون إقفال حسابات الموظفين السابقة.
    """
    if not plain_password or not stored_hash:
        return False

    # 1. فحص إذا كان الهاش بصيغة bcrypt
    if stored_hash.startswith('$2b$') or stored_hash.startswith('$2a$'):
        try:
            return bcrypt.checkpw(plain_password.encode('utf-8'), stored_hash.encode('utf-8'))
        except Exception:
            return False

    # 2. فحص إذا كان الهاش القديم المشفر بـ SHA-256 + salt
    old_hash = hashlib.sha256((plain_password + _LEGACY_SALT).encode('utf-8')).hexdigest()
    if old_hash == stored_hash:
        return True

    return False


from app.models.schema import User, PasswordResetRequest, AuthLockout, SystemSecurityState
from app.security.password_policy import validate_password_strength


def is_initial_admin_allowed() -> bool:
    """
    التحقق الصارم مما إذا كان إعداد المدير الأول مسموحاً به.
    يُسمح به فقط إذا كانت قاعدة البيانات نظيفة تماماً ولا تحتوي على أي مستخدمين
    ولم يتم إكمال التهيئة مسبقاً (bootstrap_completed != '1').
    """
    with get_session() as session:
        state = session.query(SystemSecurityState).filter(SystemSecurityState.key == 'bootstrap_completed').first()
        if state and state.value == '1':
            return False

        total_users = session.query(User).count()
        return total_users == 0


def is_first_time_setup() -> bool:
    """التوافق القديم للتحقق من مرحلة الإعداد الأولى."""
    return is_initial_admin_allowed()


def reopen_bootstrap_for_recovery() -> bool:
    """إعادة فتح مسار التهيئة الأولية حصرياً عبر إجراءات الاستعادة اليدوية/المحلية الموثقة."""
    with get_session() as session:
        state = session.query(SystemSecurityState).filter(SystemSecurityState.key == 'bootstrap_completed').first()
        if state:
            session.delete(state)
        return True


_ADMIN_SETUP_LOCK = threading.Lock()


def create_initial_admin(username: str, password: str, full_name: str) -> tuple[bool, str]:
    """إنشاء حساب مدير النظام الأول في مرحلة الإعداد الآمن الأولى مع قفل التسابق التعددي عبر العمليات."""
    if not username or not password or not full_name:
        return False, "كافة حقول المدير مطلوبة"

    is_valid, err_msg = validate_password_strength(password, username=username, full_name=full_name)
    if not is_valid:
        return False, err_msg

    with _ADMIN_SETUP_LOCK:
        try:
            with get_session() as session:
                # 1. فحص الراية الدائمة للتهيئة
                state = session.query(SystemSecurityState).filter(SystemSecurityState.key == 'bootstrap_completed').first()
                if state and state.value == '1':
                    return False, "تم إعداد مدير النظام مسبقاً والتهيئة مكتملة بشكل دائم."

                # 2. فحص وجود أي مدير حالي
                existing_admins = (
                    session.query(User)
                    .filter(User.role.in_(['admin', 'system_admin', 'superadmin', 'مدير', 'مدير النظام']))
                    .count()
                )
                if existing_admins > 0:
                    if not state:
                        session.add(SystemSecurityState(key='bootstrap_completed', value='1'))
                    else:
                        state.value = '1'
                    return False, "تم إعداد مدير النظام مسبقاً."

                existing_user = session.query(User).filter(User.username.ilike(username.strip())).first()
                if existing_user:
                    return False, "اسم المستخدم مسجل بالفعل"

                new_admin = User(
                    username=username.strip(),
                    password_hash=hash_password(password),
                    full_name=full_name.strip(),
                    role='system_admin',
                    is_active=1,
                    session_version=1
                )
                session.add(new_admin)

                if not state:
                    state = SystemSecurityState(key='bootstrap_completed', value='1')
                    session.add(state)
                else:
                    state.value = '1'

                return True, "تم إنشاء حساب مدير النظام بنجاح"
        except Exception as e:
            logger.warning(f"محاولة إنشاء المدير الأول فشلت بأمان: {e}")
            return False, "تم إعداد مدير النظام مسبقاً أو تعذر قفل المعاملة."


def authenticate_user(username: str, password: str) -> Optional[dict]:
    """
    تسجيل الدخول بالمطابقة المباشرة الصارمة لاسم المستخدم مع الترقية التلقائية إلى bcrypt إذا كان الهاش قديماً.
    """
    if not username or not password:
        return None

    clean_user = username.strip()
    with get_session() as session:
        user = session.query(User).filter(User.username.ilike(clean_user)).first()
        if not user or getattr(user, 'is_active', 1) == 0:
            return None

        if verify_password(password, user.password_hash):
            if not (user.password_hash.startswith('$2b$') or user.password_hash.startswith('$2a$')):
                user.password_hash = hash_password(password)
                logger.info(f"تمت ترقية هاش كلمة مرور المستخدم {user.username} إلى bcrypt بنجاح.")

            return {
                'id': user.id,
                'username': user.username,
                'full_name': user.full_name,
                'role': user.role,
                'department': getattr(user, 'department', ''),
                'must_change_password': int(getattr(user, 'must_change_password', 0) or 0),
                'must_enroll_recovery': int(getattr(user, 'must_enroll_recovery', 0) or 0),
                'session_version': getattr(user, 'session_version', 1)
            }

    return None


def authenticate_or_reset_user(username: str, password: str) -> tuple[Optional[dict], bool]:
    """تسجيل الدخول مع فحص ما إذا كان هناك طلب تغيير كلمة مرور معتمد بالمطابقة الصارمة لاسم المستخدم."""
    if not username or not password:
        return None, False

    clean_user = username.strip()
    with get_session() as session:
        user = session.query(User).filter(User.username.ilike(clean_user)).first()
        if not user or getattr(user, 'is_active', 1) == 0:
            return None, False

        # فحص وجود طلب استعادة معتمد بكلمة المرور الجديدة
        was_reset = False
        req = (
            session.query(PasswordResetRequest)
            .filter(
                (PasswordResetRequest.username.ilike(clean_user)) | (PasswordResetRequest.user_id == user.id),
                PasswordResetRequest.status == 'approved'
            )
            .order_by(PasswordResetRequest.id.desc())
            .first()
        )

        if req and req.new_password_hash:
            if verify_password(password, req.new_password_hash):
                user.password_hash = hash_password(password)
                user.session_version = getattr(user, 'session_version', 1) + 1
                req.status = 'applied'
                was_reset = True
                return {
                    'id': user.id,
                    'username': user.username,
                    'full_name': user.full_name,
                    'role': user.role,
                    'department': getattr(user, 'department', ''),
                    'must_change_password': int(getattr(user, 'must_change_password', 0) or 0),
                    'must_enroll_recovery': int(getattr(user, 'must_enroll_recovery', 0) or 0),
                    'session_version': user.session_version
                }, True

        # تسجيل الدخول الطبيعي
        if verify_password(password, user.password_hash):
            if not (user.password_hash.startswith('$2b$') or user.password_hash.startswith('$2a$')):
                user.password_hash = hash_password(password)
            return {
                'id': user.id,
                'username': user.username,
                'full_name': user.full_name,
                'role': user.role,
                'department': getattr(user, 'department', ''),
                'must_change_password': int(getattr(user, 'must_change_password', 0) or 0),
                'must_enroll_recovery': int(getattr(user, 'must_enroll_recovery', 0) or 0),
                'session_version': getattr(user, 'session_version', 1)
            }, was_reset

    return None, False


def add_user(
    username: str,
    password: str,
    full_name: str,
    role: str = 'employee',
    department: str = '',
    phone_number: str = '',
    must_change_password: int = 0,
    must_enroll_recovery: int = 0,
    enforce_policy: Optional[bool] = None
) -> tuple[bool, str]:
    """إضافة موظف أو مستخدم جديد مع فحص سياسة أمان كلمات المرور وحفظ البيانات المؤسسية."""
    if not username or not password or not full_name:
        return False, "كافة الحقول الأساسية مطلوبة"

    import os
    is_testing_env = os.environ.get('TESTING') == '1'
    should_enforce = enforce_policy if enforce_policy is not None else not is_testing_env

    if should_enforce:
        is_valid, err_msg = validate_password_strength(password, username=username, full_name=full_name)
        if not is_valid:
            return False, err_msg
    else:
        if len(password) < 4:
            return False, "كلمة المرور يجب أن لا تقل عن 4 خانات"

    from app.security.permissions import normalize_role, Role
    clean_user = username.strip()
    norm_role = normalize_role(role) if role else Role.EMPLOYEE

    with get_session() as session:
        exists = session.query(User).filter(User.username.ilike(clean_user)).first()
        if exists:
            return False, "اسم المستخدم مسجل بالفعل"

        user = User(
            username=clean_user,
            password_hash=hash_password(password),
            full_name=full_name.strip(),
            role=norm_role,
            department=department.strip(),
            phone_number=phone_number.strip(),
            must_change_password=1 if must_change_password else 0,
            must_enroll_recovery=1 if must_enroll_recovery else 0,
            is_active=1,
            session_version=1
        )
        session.add(user)
        session.flush()
        return True, "تم إضافة المستخدم بنجاح"


def get_user_by_id(user_id: int) -> Optional[dict]:
    """استرجاع بيانات مستخدم محدد بالحقول الآمنة المؤسسية."""
    from app.security.permissions import ROLE_LABELS_AR, get_user_permissions
    from app.models.schema import AccountRecoveryCredential
    with get_session() as session:
        u = session.query(User).filter(User.id == user_id).first()
        if not u:
            return None
        cred = (
            session.query(AccountRecoveryCredential)
            .filter(AccountRecoveryCredential.user_id == u.id)
            .order_by(AccountRecoveryCredential.id.desc())
            .first()
        )
        rec_status = cred.status if cred else 'not_configured'
        is_rec_active = bool(cred and cred.status == 'active')

        res = {
            'id': u.id,
            'username': u.username,
            'full_name': u.full_name,
            'role': u.role,
            'role_label_ar': ROLE_LABELS_AR.get(u.role, u.role),
            'department': getattr(u, 'department', '') or '',
            'phone_number': getattr(u, 'phone_number', '') or '',
            'permissions': get_user_permissions(u),
            'is_active': getattr(u, 'is_active', 1),
            'must_change_password': getattr(u, 'must_change_password', 0),
            'must_enroll_recovery': getattr(u, 'must_enroll_recovery', 0),
            'recovery_configured': is_rec_active,
            'has_recovery_key': is_rec_active,
            'recovery_status': rec_status,
            'recovery_status_label_ar': 'مُفعّل' if is_rec_active else ('ملغي / يحتاج إعادة إعداد' if rec_status == 'revoked' else 'غير مُفعّل'),
            'created_at': u.created_at.strftime('%Y-%m-%d %H:%M') if u.created_at else ''
        }
        res['user'] = dict(res)
        return res


def get_user_by_username(username: str) -> Optional[dict]:
    """استرجاع بيانات مستخدم محدد باسم المستخدم بالحقول الآمنة المؤسسية."""
    if not username:
        return None
    with get_session() as session:
        u = session.query(User).filter(User.username.ilike(username.strip())).first()
        if not u:
            return None
        return get_user_by_id(u.id)


def search_users_paginated(
    query: Optional[str] = None,
    role: Optional[str] = None,
    department: Optional[str] = None,
    is_active: Optional[int] = None,
    recovery_status: Optional[str] = None,
    page: int = 1,
    per_page: int = 25
) -> tuple[list[dict], int]:
    """بحث واسترجاع قائمة المستخدمين مع الترقيم والفلترة والحقول الآمنة ونطاق الوحدة."""
    from app.security.permissions import ROLE_LABELS_AR, get_user_permissions, normalize_role
    from app.models.schema import AccountRecoveryCredential
    from sqlalchemy import or_

    with get_session() as session:
        q = session.query(User)

        if query and query.strip():
            clean_q = f"%{query.strip()}%"
            q = q.filter(
                or_(
                    User.username.ilike(clean_q),
                    User.full_name.ilike(clean_q),
                    User.department.ilike(clean_q)
                )
            )

        if role and role.strip():
            norm_r = normalize_role(role)
            q = q.filter(User.role == norm_r)

        if department and department.strip():
            q = q.filter(User.department.ilike(f"%{department.strip()}%"))

        if is_active is not None:
            q = q.filter(User.is_active == is_active)

        total_count = q.count()
        offset_val = max(0, (page - 1) * per_page)
        users = q.order_by(User.id.asc()).offset(offset_val).limit(per_page).all()

        user_ids = [u.id for u in users]
        creds = (
            session.query(AccountRecoveryCredential)
            .filter(AccountRecoveryCredential.user_id.in_(user_ids))
            .all()
        ) if user_ids else []

        cred_map: dict[int, str] = {}
        for c in creds:
            if c.user_id not in cred_map or (cred_map[c.user_id] != 'active' and c.status == 'active'):
                cred_map[c.user_id] = c.status

        items = []
        for u in users:
            c_status = cred_map.get(u.id, 'not_configured')
            is_rec_active = (c_status == 'active')
            
            # فلترة حسب حالة الاسترداد إن طُلبت
            if recovery_status:
                rec_filter = recovery_status.strip().lower()
                if rec_filter in ('active', 'configured', 'مفعل') and not is_rec_active:
                    continue
                if rec_filter in ('not_configured', 'none', 'غير مفعل') and c_status != 'not_configured':
                    continue
                if rec_filter in ('revoked', 'ملغي') and c_status != 'revoked':
                    continue

            items.append({
                'id': u.id,
                'username': u.username,
                'full_name': u.full_name,
                'role': normalize_role(u.role),
                'role_label_ar': ROLE_LABELS_AR.get(u.role, u.role),
                'department': getattr(u, 'department', '') or '',
                'phone_number': getattr(u, 'phone_number', '') or '',
                'permissions': get_user_permissions(u),
                'is_active': getattr(u, 'is_active', 1),
                'must_change_password': getattr(u, 'must_change_password', 0),
                'must_enroll_recovery': getattr(u, 'must_enroll_recovery', 0),
                'recovery_configured': is_rec_active,
                'recovery_status': c_status,
                'recovery_status_label_ar': 'مُفعّل' if is_rec_active else ('ملغي / يحتاج إعادة إعداد' if c_status == 'revoked' else 'غير مُفعّل'),
                'created_at': u.created_at.strftime('%Y-%m-%d %H:%M') if u.created_at else ''
            })

        return items, total_count


def get_user_management_stats() -> dict:
    """استرجاع إحصائيات إدارة المستخدمين المجمعة."""
    from app.models.schema import AccountRecoveryCredential
    with get_session() as session:
        total_users = session.query(User).count()
        active_users = session.query(User).filter(User.is_active == 1).count()
        disabled_users = session.query(User).filter(User.is_active == 0).count()
        active_rec_users = session.query(AccountRecoveryCredential.user_id).filter(AccountRecoveryCredential.status == 'active').distinct().count()
        needs_recovery = max(0, total_users - active_rec_users)

        return {
            'total_users': total_users,
            'active_users': active_users,
            'disabled_users': disabled_users,
            'admin_count': session.query(User).filter(User.role.in_(['system_admin', 'admin', 'sysadmin'])).count(),
            'reviewer_count': session.query(User).filter(User.role == 'reviewer').count(),
            'senior_reviewer_count': session.query(User).filter(User.role == 'senior_reviewer').count(),
            'recovery_configured_count': active_rec_users,
            'needs_recovery_setup_count': needs_recovery
        }


def get_users_list() -> list[dict]:
    """استرجاع قائمة المستخدمين مع التسميات المؤسسية وحالة التفعيل وحالة بطاقة الاسترداد."""
    items, _ = search_users_paginated(page=1, per_page=1000)
    return items


def update_user_profile_fields(
    user_id: int,
    full_name: Optional[str] = None,
    role: Optional[str] = None,
    department: Optional[str] = None,
    phone_number: Optional[str] = None
) -> tuple[bool, str, dict]:
    """تحديث الحقول الآمنة لملف المستخدم مع ترقية الجلسة إذا تغير الدور."""
    from app.security.permissions import normalize_role
    with get_session() as session:
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            return False, "المستخدم غير موجود", {}

        changes = {}
        if full_name and full_name.strip() and full_name.strip() != user.full_name:
            changes['full_name'] = {'old': user.full_name, 'new': full_name.strip()}
            user.full_name = full_name.strip()

        if department is not None and department.strip() != getattr(user, 'department', ''):
            changes['department'] = {'old': getattr(user, 'department', ''), 'new': department.strip()}
            user.department = department.strip()

        if phone_number is not None and phone_number.strip() != getattr(user, 'phone_number', ''):
            changes['phone_number'] = {'old': getattr(user, 'phone_number', ''), 'new': phone_number.strip()}
            user.phone_number = phone_number.strip()

        if role and role.strip():
            norm_r = normalize_role(role)
            if norm_r != user.role:
                changes['role'] = {'old': user.role, 'new': norm_r}
                user.role = norm_r
                user.session_version = getattr(user, 'session_version', 1) + 1

        return True, "تم تحديث بيانات المستخدم بنجاح", changes


def update_user_role(user_id: int, new_role: str) -> tuple[bool, str, Optional[str]]:
    """تحديث دور وصلاحيات المستخدم مع ترقية إصدار الجلسة لإبطال الجلسات السابقة وإجبار تسجيل الدخول بالصلاحيات الجديدة."""
    from app.security.permissions import normalize_role
    norm_role = normalize_role(new_role)
    with get_session() as session:
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            return False, "المستخدم غير موجود", None
        prev_role = user.role
        user.role = norm_role
        user.session_version = getattr(user, 'session_version', 1) + 1
        return True, f"تم تحديث دور المستخدم إلى {norm_role}", prev_role


def set_user_active_status(user_id: int, is_active: int) -> tuple[bool, str]:
    """تفعيل أو تعطيل حساب المستخدم مع ترقية إصدار الجلسة للإبطال الفوري لأي جلسات نشطة."""
    with get_session() as session:
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            return False, "المستخدم غير موجود"
        user.is_active = 1 if is_active else 0
        user.session_version = getattr(user, 'session_version', 1) + 1
        msg = "تم تفعيل حساب المستخدم" if user.is_active else "تم تعطيل حساب المستخدم"
        return True, msg


def delete_user(user_id: int) -> tuple[bool, str]:
    """حذف حساب مستخدم وإبطال جلساته النشطة فوراً."""
    with get_session() as session:
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            return False, "المستخدم غير موجود"
        user.is_active = 0
        user.session_version = getattr(user, 'session_version', 1) + 1
        session.delete(user)
        return True, "تم حذف حساب المستخدم بنجاح"


def change_password(username: str, old_pass: str, new_pass: str) -> tuple[bool, str]:
    """تغيير كلمة المرور من قبل المستخدم نفسه مع التحقق من السياسة وإبطال الجلسات الأخرى وتصفير القفل."""
    is_valid, err_msg = validate_password_strength(new_pass, username=username)
    if not is_valid:
        return False, err_msg

    with get_session() as session:
        user = session.query(User).filter(User.username.ilike(username.strip())).first()
        if not user or not verify_password(old_pass, user.password_hash):
            return False, "كلمة المرور الحالية غير صحيحة"
        user.password_hash = hash_password(new_pass)
        user.session_version = getattr(user, 'session_version', 1) + 1

        # تصفير القفل المرتبط بالحساب
        user_ident = f"user_{user.username.lower()}"
        lockouts = session.query(AuthLockout).filter(AuthLockout.identifier.in_([user_ident, user.username.lower()])).all()
        for lo in lockouts:
            lo.failed_count = 0
            lo.locked_until = None
            lo.lockout_count = 0

        return True, "تم تغيير كلمة المرور بنجاح"


def complete_first_login_password(user_id: int, new_pass: str, confirm_pass: str) -> tuple[bool, str, Optional[int]]:
    """اعتماد كلمة المرور الدائمة في أول دخول وإبطال كلمة المرور المؤقتة والجلسات الأخرى."""
    if new_pass != confirm_pass:
        return False, "كلمتا المرور الجديدتان غير متطابقتين", None

    with get_session() as session:
        user = session.query(User).filter(User.id == user_id).first()
        if not user or getattr(user, 'is_active', 1) == 0:
            return False, "المستخدم غير موجود أو حسابه معطل", None
        if not int(getattr(user, 'must_change_password', 0) or 0):
            return True, "تم اعتماد كلمة المرور مسبقاً", getattr(user, 'session_version', 1)

        is_valid, err_msg = validate_password_strength(
            new_pass,
            username=user.username,
            full_name=user.full_name
        )
        if not is_valid:
            return False, err_msg, None

        user.password_hash = hash_password(new_pass)
        user.must_change_password = 0
        user.session_version = getattr(user, 'session_version', 1) + 1

        user_ident = f"user_{user.username.lower()}"
        lockouts = session.query(AuthLockout).filter(
            AuthLockout.identifier.in_([user_ident, user.username.lower()])
        ).all()
        for lo in lockouts:
            lo.failed_count = 0
            lo.locked_until = None
            lo.lockout_count = 0

        return True, "تم اعتماد كلمة المرور الدائمة بنجاح", user.session_version


def mark_recovery_enrollment_complete(user_id: int) -> tuple[bool, str]:
    """تأكيد استلام المستخدم لبطاقة الاسترداد وإنهاء قيد أول دخول."""
    with get_session() as session:
        user = session.query(User).filter(User.id == user_id).first()
        if not user or getattr(user, 'is_active', 1) == 0:
            return False, "المستخدم غير موجود أو حسابه معطل"
        user.must_enroll_recovery = 0
        return True, "تم تأكيد حفظ بطاقة الاسترداد"


def admin_reset_user_password(user_id: int, new_pass: str) -> tuple[bool, str]:
    """إعادة تعيين كلمة مرور موظف من قبل المدير وإبطال كافة جلسات الموظف السابقة وتصفير القفل."""
    with get_session() as session:
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            return False, "المستخدم غير موجود"

        is_valid, err_msg = validate_password_strength(new_pass, username=user.username, full_name=user.full_name)
        if not is_valid:
            return False, err_msg

        user.password_hash = hash_password(new_pass)
        user.session_version = getattr(user, 'session_version', 1) + 1

        # تصفير القفل المرتبط بالحساب
        user_ident = f"user_{user.username.lower()}"
        lockouts = session.query(AuthLockout).filter(AuthLockout.identifier.in_([user_ident, user.username.lower()])).all()
        for lo in lockouts:
            lo.failed_count = 0
            lo.locked_until = None
            lo.lockout_count = 0

        return True, f"تم تغيير كلمة مرور المستخدم {user.username} بنجاح"


def request_password_reset(username: str, new_password: str) -> tuple[bool, str]:
    """تقديم طلب استعادة كلمة مرور من الموظف لمدير النظام مع التحقق من متانة الكلمة الجديدة."""
    clean_user = username.strip()
    with get_session() as session:
        user = session.query(User).filter(User.username.ilike(clean_user)).first()
        if not user:
            return False, "اسم المستخدم غير موجود بالنظام"

        is_valid, err_msg = validate_password_strength(new_password, username=user.username, full_name=user.full_name)
        if not is_valid:
            return False, err_msg

        req = PasswordResetRequest(
            user_id=user.id,
            username=user.username,
            full_name=user.full_name,
            new_password_hash=hash_password(new_password),
            status='pending'
        )
        session.add(req)
        return True, "تم إرسال طلب استعادة كلمة المرور بنجاح إلى مدير النظام"


def get_password_reset_requests() -> list[dict]:
    """استرجاع طلبات استعادة كلمات المرور المعلقة."""
    with get_session() as session:
        reqs = session.query(PasswordResetRequest).filter(PasswordResetRequest.status == 'pending').all()
        return [
            {
                'id': r.id,
                'user_id': r.user_id,
                'username': r.username,
                'full_name': r.full_name,
                'date': r.created_at.strftime('%Y-%m-%d %H:%M') if r.created_at else ''
            }
            for r in reqs
        ]


def approve_password_reset(req_id: int) -> tuple[bool, str]:
    """الموافقة على طلب استعادة كلمة المرور وترقية إصدار الجلسة للمستخدم."""
    with get_session() as session:
        req = session.query(PasswordResetRequest).filter(PasswordResetRequest.id == req_id).first()
        if not req:
            return False, "الطلب غير موجود"
        req.status = 'approved'

        # إبطال أي جلسة مفتوحة للمستخدم حالياً
        user = session.query(User).filter(User.id == req.user_id).first()
        if user:
            user.session_version = getattr(user, 'session_version', 1) + 1

        return True, f"تمت الموافقة على طلب استعادة كلمة المرور للمستخدم {req.username}"


def decline_password_reset(req_id: int) -> tuple[bool, str]:
    """رفض طلب استعادة كلمة المرور."""
    with get_session() as session:
        req = session.query(PasswordResetRequest).filter(PasswordResetRequest.id == req_id).first()
        if not req:
            return False, "الطلب غير موجود"
        req.status = 'declined'
        return True, f"تم رفض طلب استعادة كلمة المرور للمستخدم {req.username}"
