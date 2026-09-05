# -*- coding: utf-8 -*-
"""
محرك الأقفال الموزعة الدائمة في قاعدة البيانات (Database-Backed Distributed Lock Engine):
- يمنع تضارب العمليات الأحادية (Single-Owner Tasks مثل إعادة بناء الفهرس والنسخ الاحتياطي).
- يحتوي على مدة صلاحية (TTL) لتفادي بقاء الأقفال معلقة عند انهيار العامل المستحوذ.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.queue.base import DistributedLockBackend
from app.models.queue_schema import DistributedLockRecord
from app.repositories import base_repo

logger = logging.getLogger(__name__)


def _normalize_dt(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class DatabaseDistributedLock(DistributedLockBackend):
    """تطبيق الأقفال الموزعة عبر جداول قاعدة البيانات."""

    def acquire(self, lock_name: str, owner_token: str, ttl_seconds: int = 120) -> bool:
        """محاولة الاستحواذ على القفل الموزع بأمان ضد تضارب العمليات المتزامنة."""
        now_dt = datetime.now(timezone.utc)
        exp_dt = now_dt + timedelta(seconds=ttl_seconds)

        try:
            with base_repo.get_session() as session:
                existing = session.query(DistributedLockRecord).filter(
                    DistributedLockRecord.lock_name == lock_name
                ).first()

                if existing:
                    exp_norm = _normalize_dt(existing.expires_at)
                    # التحقق هل انتهت صلاحية القفل السابق
                    if exp_norm and exp_norm < now_dt:
                        existing.owner_token = owner_token
                        existing.acquired_at = now_dt
                        existing.expires_at = exp_dt
                        session.commit()
                        logger.info(f"تم الاستحواذ على القفل الموزع {lock_name} بعد انتهاء صلاحية القفل السابق.")
                        return True
                    elif existing.owner_token == owner_token:
                        # تجديد القفل لنفس المالك
                        existing.expires_at = exp_dt
                        session.commit()
                        return True
                    else:
                        # القفل مستحوذ عليه من عامل آخر وسارٍ
                        return False
                else:
                    # إنشاء قفل جديد
                    new_lock = DistributedLockRecord(
                        lock_name=lock_name,
                        owner_token=owner_token,
                        acquired_at=now_dt,
                        expires_at=exp_dt
                    )
                    session.add(new_lock)
                    session.commit()
                    logger.info(f"تم الاستحواذ على القفل الموزع الجديد {lock_name} للمالك {owner_token[:8]}.")
                    return True
        except Exception as e:
            logger.debug(f"فشل الاستحواذ التنافسي على القفل {lock_name}: {e}")
            return False

    def release(self, lock_name: str, owner_token: str) -> bool:
        """تحرير القفل الموزع من قِبل مالكه الشرعي."""
        with base_repo.get_session() as session:
            existing = session.query(DistributedLockRecord).filter(
                DistributedLockRecord.lock_name == lock_name,
                DistributedLockRecord.owner_token == owner_token
            ).first()

            if existing:
                session.delete(existing)
                session.commit()
                logger.info(f"تم تحرير القفل الموزع {lock_name} بنجاح.")
                return True
            return False

    def is_locked(self, lock_name: str) -> bool:
        """التحقق هل القفل نشط ومستحوذ عليه."""
        now_dt = datetime.now(timezone.utc)
        with base_repo.get_session() as session:
            existing = session.query(DistributedLockRecord).filter(
                DistributedLockRecord.lock_name == lock_name,
                DistributedLockRecord.expires_at >= now_dt
            ).first()
            return existing is not None
