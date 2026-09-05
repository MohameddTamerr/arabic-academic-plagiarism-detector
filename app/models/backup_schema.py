# -*- coding: utf-8 -*-
"""
نموذج فهرس وسجل النسخ الاحتياطي المؤسسي (Backup Catalog ORM Model):
- توثيق جميع النسخ الاحتياطية وتاريخ إنشائها وحالتها وحجمها وبصمتها الرقمية.
- تسجيل حالة التحقق (Validation) وتاريخ الاستعادة (Restored At).
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, BigInteger, Index
from app.models.schema import Base


class BackupCatalog(Base):
    """
    سجل النسخ الاحتياطية المؤسسية.
    """
    __tablename__ = 'backup_catalog'

    id = Column(Integer, primary_key=True, autoincrement=True)
    backup_identifier = Column(String(50), unique=True, nullable=False, index=True) # e.g. BKP-2026-000001
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    created_by = Column(String(255), default='system', index=True)
    backup_type = Column(String(50), default='full', index=True) # full / automated / pre_restore
    status = Column(String(50), default='creating', index=True) # creating, completed, failed, invalid, restored
    file_name = Column(String(500), nullable=False) # e.g. BKP-2026-000001_full.zip
    file_path = Column(Text, default='') # المسار الفعلي داخل مجلد النسخ
    size_bytes = Column(BigInteger, default=0)
    checksum = Column(String(64), default='', index=True) # SHA-256 لحزمة النسخة بالكامل
    application_version = Column(String(50), default='1.0.0')
    engine_version = Column(String(50), default='1.0.0')
    manifest_version = Column(String(50), default='1.0')
    validated_at = Column(DateTime, nullable=True)
    validation_status = Column(String(50), default='unverified') # valid / invalid / unverified
    validation_details = Column(Text, default='{}')
    restored_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index('idx_backup_created_at', 'created_at'),
        Index('idx_backup_status', 'status'),
        Index('idx_backup_ident', 'backup_identifier'),
    )
