# -*- coding: utf-8 -*-
"""
خدمة توليد وإدارة الأرقام المرجعية المؤسسية (Official Research Reference Service):
- توليد أرقام مرجعية رسمية فريدة وغير قابلة للتعديل أو التكرار بتنسيق: {PREFIX}-{YEAR}-{SEQUENCE:06d}
- حماية التزامن العالي (High Concurrency Protection) عبر أقفال المعالجة ومعاملات قاعدة البيانات المباشرة.
- توفير دوال التحقق والتنسيق المركزية للمنظومة.
"""

import logging
import threading
from datetime import datetime
from typing import Optional
from sqlalchemy import text

import config
from app.models.research_schema import ReferenceSequence

logger = logging.getLogger(__name__)

# قفل أمان على مستوى الـ Thread لحماية المعالجة المتزامنة في بيئة Python / SQLite
_REFERENCE_MUTEX = threading.Lock()


def format_reference_number(prefix: str, year: int, sequence_value: int) -> str:
    """
    التنسيق المركزي القياسي للرقم المرجعي في المنظومة:
    {PREFIX}-{YEAR}-{SEQUENCE:06d}
    مثال: RES-2026-000184
    """
    clean_prefix = (prefix or 'RES').strip().upper()
    return f"{clean_prefix}-{year}-{sequence_value:06d}"


def get_next_sequence_value(namespace: str, year: int) -> int:
    """
    توليد وتحديث القيمة التسلسلية ذرياً عبر معاملات قاعدة البيانات (Cross-Process Atomic Sequence):
    - يعتمد على عبارة UPDATE ذرية مباشرة في SQL لمنع أي سباق بين العمليات المتزامنة (Zero Lost Increments).
    - يضمن الأمان التام عبر العمليات المتعددة (Multi-Process Safety) في SQLite و PostgreSQL.
    """
    from app.repositories.base_repo import get_session, get_backend_type
    with get_session() as session:
        # 1. ضمان وجود سجل التسلسل أولاً
        exists = session.query(ReferenceSequence).filter(
            ReferenceSequence.namespace == namespace,
            ReferenceSequence.year == year
        ).first()

        if not exists:
            try:
                new_seq = ReferenceSequence(
                    namespace=namespace,
                    year=year,
                    last_value=0,
                    updated_at=datetime.now()
                )
                session.add(new_seq)
                session.flush()
            except Exception:
                session.rollback()

        b_type = get_backend_type()
        if b_type == 'postgresql':
            # استعلام ذري مع إرجاع القيمة المحدثة مباشرة في PostgreSQL
            res = session.execute(
                text("""
                    UPDATE reference_sequences
                    SET last_value = last_value + 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE namespace = :ns AND year = :yr
                    RETURNING last_value;
                """),
                {'ns': namespace, 'yr': year}
            )
            val = res.scalar()
            return int(val)
        else:
            # 2. تنفيذ الزيادة الذرية في SQLite
            session.execute(
                text("""
                    UPDATE reference_sequences
                    SET last_value = last_value + 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE namespace = :ns AND year = :yr;
                """),
                {'ns': namespace, 'yr': year}
            )

            # 3. قراءة القيمة المحجوزة المؤكدة
            val = session.execute(
                text("SELECT last_value FROM reference_sequences WHERE namespace = :ns AND year = :yr;"),
                {'ns': namespace, 'yr': year}
            ).scalar()

            return int(val)



def get_next_research_reference(session=None, year: Optional[int] = None, prefix: Optional[str] = None) -> str:
    """
    توليد الرقم المرجعي التالي لسجل البحث:
    - محصن تماماً ضد التكرار وفقدان التسلسل عبر العمليات المتعددة (Multi-Process Safe).
    """
    if year is None:
        year = datetime.now().year
    if prefix is None:
        prefix = getattr(config, 'RESEARCH_REFERENCE_PREFIX', 'RES')

    with _REFERENCE_MUTEX:
        next_val = get_next_sequence_value('research', year)
        ref_number = format_reference_number(prefix, year, next_val)
        logger.info(f"تم توليد وحجز رقم مرجعي رسمي جديد: {ref_number} (تسلسل: {next_val})")
        return ref_number


def get_next_backup_reference(year: Optional[int] = None, prefix: str = 'BKP') -> str:
    """
    توليد الرقم المرجعي التالي للنسخة الاحتياطية (e.g. BKP-2026-000001).
    يتحقق من أعلى رقم مسجل في الفهرس لضمان عدم حدوث تصادم حتى بعد استعادة نسخ سابقة.
    """
    if year is None:
        year = datetime.now().year

    with _REFERENCE_MUTEX:
        from app.repositories.base_repo import get_session
        from app.models.backup_schema import BackupCatalog
        with get_session() as seq_session:
            pattern = f"{prefix}-{year}-%"
            highest = (
                seq_session.query(BackupCatalog.backup_identifier)
                .filter(BackupCatalog.backup_identifier.like(pattern))
                .order_by(BackupCatalog.backup_identifier.desc())
                .first()
            )
            max_existing = 0
            if highest and highest[0]:
                try:
                    parts = highest[0].split('-')
                    if len(parts) == 3:
                        max_existing = int(parts[2])
                except Exception:
                    max_existing = 0

            # ضمان مزامنة جدول التسلسلات مع أعلى رقم في الفهرس
            seq_record = (
                seq_session.query(ReferenceSequence)
                .filter(
                    ReferenceSequence.namespace == 'backup',
                    ReferenceSequence.year == year
                )
                .first()
            )
            if not seq_record:
                seq_record = ReferenceSequence(
                    namespace='backup',
                    year=year,
                    last_value=max_existing,
                    updated_at=datetime.now()
                )
                seq_session.add(seq_record)
                seq_session.commit()
            elif max_existing > seq_record.last_value:
                seq_record.last_value = max_existing
                seq_session.commit()

        next_val = get_next_sequence_value('backup', year)
        ref_number = format_reference_number(prefix, year, next_val)
        logger.info(f"تم توليد وحجز رقم نسخة احتياطية جديد: {ref_number}")
        return ref_number

