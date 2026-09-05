# -*- coding: utf-8 -*-
"""
نموذج سجل التدقيق والمراجعة المؤسسي (Institutional Audit Log Model):
- سجل تراكمي غير قابل للتعديل أو الحذف (Append-Only).
- يوثق كافة العمليات الإدارية، وتغييرات الصلاحيات، وقرارات التحكيم، واستعراض التقارير، والنسخ الاحتياطي.
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, Index
)
from app.models.schema import Base


class AuditLog(Base):
    """
    سجل التدقيق والمراجعة المؤسسي.
    """
    __tablename__ = 'audit_logs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(64), unique=True, nullable=False, index=True) # UUID
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # هوية المستخدم لحظة الحدث
    user_id = Column(Integer, nullable=True, index=True)
    username_snapshot = Column(String(255), default='system', index=True)
    role_snapshot = Column(String(50), default='', index=True)

    # تصنيف ونوع الإجراء
    action = Column(String(100), nullable=False, index=True)       # e.g., 'auth.login.success', 'review.final_accepted'
    category = Column(String(50), nullable=False, index=True)      # e.g., 'auth', 'research', 'review', 'admin', 'backup', 'settings'
    object_type = Column(String(50), default='', index=True)       # e.g., 'research', 'report', 'user', 'settings', 'batch'
    object_id = Column(String(64), default='', index=True)

    # الربط بالبحث المؤسسي ورقمه المرجعي
    research_id = Column(Integer, nullable=True, index=True)
    research_reference_number = Column(String(50), default='', index=True)

    # روابط الدفعات والتقارير
    batch_id = Column(String(64), nullable=True, index=True)
    report_id = Column(String(64), nullable=True, index=True)

    # النتيجة ورمز الخطأ
    success = Column(Boolean, default=True, index=True)
    failure_reason_code = Column(String(100), default='')

    # تتبع الطلب والشبكة المحلية
    request_id = Column(String(64), default='', index=True)
    ip_address = Column(String(64), default='')

    # البيانات الوصفية الآمنة الخالية من النصوص السرية أو الكلمات الممررة
    metadata_json = Column(Text, default='{}')

    __table_args__ = (
        Index('idx_audit_created_at', 'created_at'),
        Index('idx_audit_action_cat', 'action', 'category'),
        Index('idx_audit_user', 'user_id', 'username_snapshot'),
        Index('idx_audit_ref_num', 'research_reference_number'),
        Index('idx_audit_batch', 'batch_id'),
    )
