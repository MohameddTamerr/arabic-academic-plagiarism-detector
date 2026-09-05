# -*- coding: utf-8 -*-
"""
مستودع بيانات النسخ الاحتياطية (Backup Repository):
- إدارة جداول وسجلات BackupCatalog.
- حفظ واسترجاع وتحديث بيانات وحالات النسخ الاحتياطية.
"""

import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from app.repositories.base_repo import get_session
from app.models.backup_schema import BackupCatalog

logger = logging.getLogger(__name__)


def create_backup_entry(
    backup_identifier: str,
    file_name: str,
    file_path: str,
    created_by: str = 'system',
    backup_type: str = 'full',
    status: str = 'creating',
    size_bytes: int = 0,
    checksum: str = '',
    application_version: str = '1.0.0',
    engine_version: str = '1.0.0',
    manifest_version: str = '1.0'
) -> int:
    """إنشاء سجل جديد للنسخة الاحتياطية في الفهرس. يُعيد معرف السجل."""
    with get_session() as session:
        entry = BackupCatalog(
            backup_identifier=backup_identifier,
            file_name=file_name,
            file_path=file_path,
            created_by=created_by,
            backup_type=backup_type,
            status=status,
            size_bytes=size_bytes,
            checksum=checksum,
            application_version=application_version,
            engine_version=engine_version,
            manifest_version=manifest_version
        )
        session.add(entry)
        session.flush()
        return entry.id


def get_backup_entry(backup_identifier: str) -> Optional[Dict[str, Any]]:
    """استرجاع بيانات نسخة احتياطية محددة بالمعرف الرسمي."""
    if not backup_identifier:
        return None
    with get_session() as session:
        b = session.query(BackupCatalog).filter(BackupCatalog.backup_identifier == backup_identifier).first()
        if not b:
            return None
        return _serialize_backup(b)


def list_backups() -> List[Dict[str, Any]]:
    """استرجاع قائمة كافة النسخ الاحتياطية المسجلة مرتبة من الأحدث إلى الأقدم."""
    with get_session() as session:
        backups = session.query(BackupCatalog).order_by(BackupCatalog.created_at.desc()).all()
        return [_serialize_backup(b) for b in backups]


def update_backup_status(
    backup_identifier: str,
    status: str,
    size_bytes: Optional[int] = None,
    checksum: Optional[str] = None
) -> bool:
    """تحديث حالة النسخة الاحتياطية وحجمها وبصمتها."""
    with get_session() as session:
        b = session.query(BackupCatalog).filter(BackupCatalog.backup_identifier == backup_identifier).first()
        if not b:
            return False
        b.status = status
        if size_bytes is not None:
            b.size_bytes = size_bytes
        if checksum is not None:
            b.checksum = checksum
        return True


def update_backup_validation(
    backup_identifier: str,
    validation_status: str,
    validation_details: dict
) -> bool:
    """تحديث حالة وتفاصيل التحقق من سلامة النسخة."""
    with get_session() as session:
        b = session.query(BackupCatalog).filter(BackupCatalog.backup_identifier == backup_identifier).first()
        if not b:
            return False
        b.validation_status = validation_status
        b.validated_at = datetime.utcnow()
        b.validation_details = json.dumps(validation_details, ensure_ascii=False)
        return True


def mark_backup_restored(backup_identifier: str) -> bool:
    """توثيق نجاح استعادة النسخة الاحتياطية."""
    with get_session() as session:
        b = session.query(BackupCatalog).filter(BackupCatalog.backup_identifier == backup_identifier).first()
        if not b:
            return False
        b.restored_at = datetime.utcnow()
        b.status = 'restored'
        return True


def delete_backup_entry(backup_identifier: str) -> bool:
    """حذف سجل النسخة الاحتياطية من الفهرس."""
    with get_session() as session:
        b = session.query(BackupCatalog).filter(BackupCatalog.backup_identifier == backup_identifier).first()
        if not b:
            return False
        session.delete(b)
        return True


def _serialize_backup(b: BackupCatalog) -> Dict[str, Any]:
    try:
        details = json.loads(b.validation_details) if b.validation_details else {}
    except Exception:
        details = {}

    return {
        'id': b.id,
        'backup_identifier': b.backup_identifier,
        'created_at': b.created_at.strftime('%Y-%m-%d %H:%M:%S') if b.created_at else '',
        'created_by': b.created_by,
        'backup_type': b.backup_type,
        'status': b.status,
        'file_name': b.file_name,
        'file_path': b.file_path,
        'size_bytes': b.size_bytes,
        'size_mb': round(b.size_bytes / (1024 * 1024), 2) if b.size_bytes else 0.0,
        'checksum': b.checksum,
        'application_version': b.application_version,
        'engine_version': b.engine_version,
        'manifest_version': b.manifest_version,
        'validated_at': b.validated_at.strftime('%Y-%m-%d %H:%M:%S') if b.validated_at else None,
        'validation_status': b.validation_status,
        'validation_details': details,
        'restored_at': b.restored_at.strftime('%Y-%m-%d %H:%M:%S') if b.restored_at else None
    }
