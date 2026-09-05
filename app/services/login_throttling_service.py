# -*- coding: utf-8 -*-
"""
خدمة الحد من محاولات الدخول والقفل المؤقت (Login Throttling & Lockout Service):
- حماية النظام ضد هجمات القوة الغاشمة (Brute-Force Protection) دون أي تبعيات خارجية.
- تخزين ومزامنة حالة القفل المؤقت داخل قاعدة بيانات SQLite لضمان فاعليتها عبر العمليات المتعددة (Multi-Process Safe).
- فصل كبح الحساب (Account Throttling) عن كبح عنوان المصدر (Source IP Throttling) لمنع هجمات حرمان الخدمة عن بقية المستخدمين.
- تطبيق عقوبة تصاعدية عند تكرار دورات القفل مع استخدام توقيتات UTC موحدة ومحصنة.
- مقاومة استكشاف وتعداد المستخدمين (User Enumeration Resistance).
- عدم حفظ أو تسجيل أي كلمات مرور مدخلة إطلاقاً في جداول القفل أو السجلات.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Tuple, Optional
from sqlalchemy import text

import config
from app.repositories.base_repo import get_session, engine
from app.models.schema import AuthLockout

logger = logging.getLogger(__name__)


def normalize_identifier(username: str = '', ip_address: str = '') -> str:
    """تطبيع معرف المحاولة للحساب أو عنوان IP."""
    u = (username or '').strip().lower()
    if u:
        return f"user_{u}" if not u.startswith("user_") else u
    ip = (ip_address or '').strip()
    return f"ip_{ip}" if ip else "ip_unknown"


def _get_utc_now(now_dt: Optional[datetime] = None) -> datetime:
    """استرجاع التوقيت الحالي بتوقيت UTC بصيغة موحدة."""
    if now_dt is not None:
        if now_dt.tzinfo is not None:
            return now_dt.astimezone(timezone.utc).replace(tzinfo=None)
        return now_dt
    return datetime.now(timezone.utc).replace(tzinfo=None)


def is_locked_out(
    username: str = '',
    ip_address: str = '',
    now_dt: Optional[datetime] = None
) -> Tuple[bool, int, Optional[datetime]]:
    """
    التحقق مما إذا كان الحساب أو عنوان IP يخضع حالياً للقفل المؤقت.
    
    :return: (is_locked: bool, remaining_seconds: int, locked_until: Optional[datetime])
    """
    now = _get_utc_now(now_dt)
    candidates = []
    if username and username.strip():
        candidates.append(normalize_identifier(username=username))
    if ip_address and ip_address.strip():
        candidates.append(normalize_identifier(ip_address=ip_address))

    if not candidates:
        return False, 0, None

    with get_session() as session:
        lockouts = session.query(AuthLockout).filter(AuthLockout.identifier.in_(candidates)).all()
        for lockout in lockouts:
            if lockout.locked_until and lockout.locked_until > now:
                remaining = int((lockout.locked_until - now).total_seconds())
                return True, max(1, remaining), lockout.locked_until

    return False, 0, None


def _atomic_record_identifier_failure(
    ident: str,
    max_attempts: int,
    now: datetime,
    lockout_minutes: int,
    extended_lockout_minutes: int,
    max_retries: int = 15
) -> Tuple[bool, int, Optional[datetime]]:
    """تسجيل محاولة فاشلة لمعرف مفرد مع تحديث ذري حقيقي عبر SQLite UPSERT لمنع فقدان التحديثات بين العمليات."""
    import time
    for attempt in range(max_retries):
        try:
            with get_session() as session:
                session.execute(
                    text("""
                        INSERT INTO auth_lockouts (identifier, failed_count, last_failed_at, lockout_count)
                        VALUES (:ident, 1, :now, 0)
                        ON CONFLICT(identifier) DO UPDATE SET
                            failed_count = auth_lockouts.failed_count + 1,
                            last_failed_at = :now
                    """),
                    {'ident': ident, 'now': now}
                )
                session.commit()

                lockout = session.query(AuthLockout).filter(AuthLockout.identifier == ident).first()
                if lockout and lockout.failed_count >= max_attempts:
                    if not lockout.locked_until or lockout.locked_until <= now:
                        lockout.lockout_count += 1
                        duration = extended_lockout_minutes if lockout.lockout_count > 1 else lockout_minutes
                        lockout.locked_until = now + timedelta(minutes=duration)
                        session.commit()
                        logger.warning(
                            f"تم قفل تسجيل الدخول مؤقتاً للمعرف [{ident}] لمدة {duration} دقيقة بعد {lockout.failed_count} محاولات خاطئة."
                        )
                        return True, lockout.failed_count, lockout.locked_until
                    return True, lockout.failed_count, lockout.locked_until

                return False, lockout.failed_count if lockout else 1, None
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(0.05 * (attempt + 1))
                continue
            logger.error(f"فشل تحديث قفل المعرف {ident}: {e}")
            return False, 1, None


def record_failed_attempt(
    username: str = '',
    ip_address: str = '',
    now_dt: Optional[datetime] = None
) -> Tuple[bool, int, Optional[datetime]]:
    """
    تسجيل محاولة دخول خاطئة وتحديث عداد الإخفاق وحالة القفل لكل من الحساب والـ IP بصورة متزامنة وآمنة.
    
    :return: (is_now_locked: bool, total_failed: int, locked_until: Optional[datetime])
    """
    now = _get_utc_now(now_dt)
    max_user_attempts = getattr(config, 'AUTH_MAX_LOGIN_ATTEMPTS', 5)
    max_ip_attempts = getattr(config, 'AUTH_MAX_IP_ATTEMPTS', 20)
    lockout_minutes = getattr(config, 'AUTH_LOCKOUT_DURATION_MINUTES', 15)
    extended_lockout_minutes = getattr(config, 'AUTH_EXTENDED_LOCKOUT_DURATION_MINUTES', 60)

    user_locked, user_count, user_until = False, 0, None
    if username and username.strip():
        user_ident = normalize_identifier(username=username)
        user_locked, user_count, user_until = _atomic_record_identifier_failure(
            user_ident, max_user_attempts, now, lockout_minutes, extended_lockout_minutes
        )

    ip_locked, ip_count, ip_until = False, 0, None
    if ip_address and ip_address.strip():
        ip_ident = normalize_identifier(ip_address=ip_address)
        ip_locked, ip_count, ip_until = _atomic_record_identifier_failure(
            ip_ident, max_ip_attempts, now, lockout_minutes, extended_lockout_minutes
        )

    if user_locked:
        return True, user_count, user_until
    if ip_locked:
        return True, ip_count, ip_until

    return False, user_count or ip_count, None


def record_successful_login(username: str = '', ip_address: str = '') -> None:
    """تصفير محاولات الدخول الخاطئة وإلغاء القفل عند نجاح المصادقة."""
    candidates = []
    if username and username.strip():
        candidates.append(normalize_identifier(username=username))

    if not candidates:
        return

    now = _get_utc_now()
    with get_session() as session:
        lockouts = session.query(AuthLockout).filter(AuthLockout.identifier.in_(candidates)).all()
        for lockout in lockouts:
            lockout.failed_count = 0
            lockout.locked_until = None
            lockout.lockout_count = 0
            lockout.last_failed_at = now

