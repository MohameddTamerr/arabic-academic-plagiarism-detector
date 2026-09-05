# -*- coding: utf-8 -*-
"""
نموذج سجل هجرات وتحديثات قاعدة البيانات (Schema Migrations ORM Model):
- توثيق وترتيب جميع الهجرات التراكمية المطبقة على قاعدة البيانات محلياً.
- تتبع وقت التنفيذ والحالة والإصدار بدقة دون الاعتماد على أدوات خارجية.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from app.models.schema import Base


class SchemaMigration(Base):
    """
    سجل هجرات وتعديلات هيكل قاعدة البيانات.
    """
    __tablename__ = 'schema_migrations'

    id = Column(Integer, primary_key=True, autoincrement=True)
    version = Column(String(50), unique=True, nullable=False, index=True) # e.g. "001_initial_schema", "002_phase9_indexes"
    description = Column(String(255), nullable=False)
    applied_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    execution_time_ms = Column(Integer, default=0)
    status = Column(String(20), default='completed')
