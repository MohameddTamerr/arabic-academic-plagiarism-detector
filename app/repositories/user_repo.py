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


def is_first_time_setup() -> bool:
    """هل النظام في مرحلة الإعداد الأولى (لا يوجد أي مدير مسجل)؟"""
    with get_session() as session:
        admin_count = session.query(User).filter(User.role == 'admin').count()
        return admin_count == 0


def create_initial_admin(username: str, password: str, full_name: str) -> tuple[bool, str]:
    """إنشاء حساب مدير النظام الأول في مرحلة الإعداد الآمن الأولى."""
    if not username or not password or not full_name:
        return False, "كافة حقول المدير مطلوبة"
    if len(password) < 6:
        return False, "كلمة المرور يجب ألا تقل عن 6 خانات"

    with get_session() as session:
        existing = session.query(User).filter(User.username == username.strip()).first()
        if existing:
            return False, "اسم المستخدم مسجل بالفعل"

        new_admin = User(
            username=username.strip(),
            password_hash=hash_password(password),
            full_name=full_name.strip(),
            role='admin'
        )
        session.add(new_admin)
        return True, "تم إنشاء حساب مدير النظام بنجاح"


def _find_user_flexible(session, clean_user: str) -> Optional[User]:
    """البحث المرن عن المستخدم بالاسم أو اسم المستخدم أو 'admin' أو 'tamer' أو الاسم العربي."""
    if not clean_user:
        return None
    # 1. تطابق مباشر غير حساس لحالة الأحرف
    user = session.query(User).filter(User.username.ilike(clean_user)).first()
    if user:
        return user

    # 2. مطابقة الكلمات الشائعة لمدير النظام
    if clean_user.lower() in ('admin', 'tamer', 'تامر', 'tamer darwish', 'tamer_darwish', 'مدير'):
        admin_user = session.query(User).filter(User.role == 'admin').first()
        if admin_user:
            return admin_user

    # 3. مطابقة جزئية في اسم المستخدم أو الاسم الكامل
    user = session.query(User).filter(
        (User.username.ilike(f"%{clean_user}%")) |
        (User.full_name.ilike(f"%{clean_user}%"))
    ).first()
    return user


def authenticate_user(username: str, password: str) -> Optional[dict]:
    """
    تسجيل الدخول مع الترقية التلقائية إلى bcrypt إذا كان الهاش قديماً.
    """
    if not username or not password:
        return None

    clean_user = username.strip()
    with get_session() as session:
        user = _find_user_flexible(session, clean_user)
        if not user:
            return None

        if verify_password(password, user.password_hash):
            # إذا كان الهاش ليس bcrypt، نقوم بترقيته في الخلفية فوراً
            if not (user.password_hash.startswith('$2b$') or user.password_hash.startswith('$2a$')):
                user.password_hash = hash_password(password)
                logger.info(f"تمت ترقية هاش كلمة مرور المستخدم {user.username} إلى bcrypt بنجاح.")

            return {
                'id': user.id,
                'username': user.username,
                'full_name': user.full_name,
                'role': user.role
            }

    return None


def authenticate_or_reset_user(username: str, password: str) -> tuple[Optional[dict], bool]:
    """تسجيل الدخول مع فحص ما إذا كان هناك طلب تغيير كلمة مرور معتمد."""
    if not username or not password:
        return None, False

    clean_user = username.strip()
    with get_session() as session:
        user = _find_user_flexible(session, clean_user)
        if not user:
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
                # اعتماد كلمة المرور الجديدة في حساب المستخدم
                user.password_hash = hash_password(password)
                req.status = 'applied'
                was_reset = True
                return {
                    'id': user.id,
                    'username': user.username,
                    'full_name': user.full_name,
                    'role': user.role
                }, True

        # تسجيل الدخول الطبيعي
        if verify_password(password, user.password_hash):
            if not (user.password_hash.startswith('$2b$') or user.password_hash.startswith('$2a$')):
                user.password_hash = hash_password(password)
            return {
                'id': user.id,
                'username': user.username,
                'full_name': user.full_name,
                'role': user.role
            }, was_reset

    return None, False


def add_user(username: str, password: str, full_name: str, role: str = 'employee') -> tuple[bool, str]:
    """إضافة موظف أو مستخدم جديد."""
    if not username or not password or not full_name:
        return False, "كافة الحقول مطلوبة"
    if len(password) < 4:
        return False, "كلمة المرور يجب أن لا تقل عن 4 خانات"

    clean_user = username.strip()
    with get_session() as session:
        exists = session.query(User).filter(User.username.ilike(clean_user)).first()
        if exists:
            return False, "اسم المستخدم مسجل بالفعل"

        user = User(
            username=clean_user,
            password_hash=hash_password(password),
            full_name=full_name.strip(),
            role=role if role in ('admin', 'employee') else 'employee'
        )
        session.add(user)
        return True, "تم إضافة المستخدم بنجاح"


def get_users_list() -> list[dict]:
    """استرجاع قائمة المستخدمين."""
    with get_session() as session:
        users = session.query(User).order_by(User.id.asc()).all()
        return [
            {
                'id': u.id,
                'username': u.username,
                'full_name': u.full_name,
                'role': u.role,
                'created_at': u.created_at.strftime('%Y-%m-%d') if u.created_at else ''
            }
            for u in users
        ]


def change_password(username: str, old_pass: str, new_pass: str) -> bool:
    """تغيير كلمة المرور من قبل المستخدم نفسه."""
    with get_session() as session:
        user = session.query(User).filter(User.username.ilike(username.strip())).first()
        if not user or not verify_password(old_pass, user.password_hash):
            return False
        user.password_hash = hash_password(new_pass)
        return True


def admin_reset_user_password(user_id: int, new_pass: str) -> tuple[bool, str]:
    """إعادة تعيين كلمة مرور موظف مباشرة من قبل المدير."""
    if len(new_pass) < 4:
        return False, "كلمة المرور يجب أن لا تقل عن 4 خانات"
    with get_session() as session:
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            return False, "المستخدم غير موجود"
        user.password_hash = hash_password(new_pass)
        return True, f"تم تغيير كلمة مرور المستخدم {user.username} بنجاح"


def request_password_reset(username: str, new_password: str) -> tuple[bool, str]:
    """تقديم طلب استعادة كلمة مرور من الموظف لمدير النظام."""
    clean_user = username.strip()
    with get_session() as session:
        user = session.query(User).filter(User.username.ilike(clean_user)).first()
        if not user:
            return False, "اسم المستخدم غير موجود بالنظام"

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
    with get_session() as session:
        req = session.query(PasswordResetRequest).filter(PasswordResetRequest.id == req_id).first()
        if not req:
            return False, "الطلب غير موجود"
        req.status = 'approved'
        return True, f"تمت الموافقة على طلب استعادة كلمة المرور للمستخدم {req.username}"


def decline_password_reset(req_id: int) -> tuple[bool, str]:
    with get_session() as session:
        req = session.query(PasswordResetRequest).filter(PasswordResetRequest.id == req_id).first()
        if not req:
            return False, "الطلب غير موجود"
        req.status = 'declined'
        return True, f"تم رفض طلب استعادة كلمة المرور للمستخدم {req.username}"
