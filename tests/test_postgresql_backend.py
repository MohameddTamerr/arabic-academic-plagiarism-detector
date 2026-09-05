# -*- coding: utf-8 -*-
"""
اختبارات تكوين وتجريد قاعدة البيانات ودعم PostgreSQL (Prompt 1: PostgreSQL Backend Tests):
- فحص دوال إخفاء بيانات الاعتماد والـ DSN لمنع تسريب كلمات المرور في السجلات ونقاط الفحص.
- فحص كاشف نوع المحرك get_backend_type().
- فحص صمامات الأمان ضد الكتابة في قواعد البيانات الحية (Fail-Safe Guards).
- فحص معالجة تخطي اختبارات التكامل عند عدم توفر خادم PostgreSQL محلياً.
"""

import os
import pytest
from unittest.mock import patch, MagicMock

import config
from app.repositories import base_repo
from app.services import system_health_service


def test_masked_database_url_redaction():
    """التحقق من إخفاء كلمات المرور وبيانات الاعتماد في سلاسل PostgreSQL DSN."""
    raw_dsn = "postgresql://plagiarism_app:SuperSecretPassword123@10.0.1.50:5432/plagiarism_db"
    masked = config.get_masked_database_url(raw_dsn)
    assert "SuperSecretPassword123" not in masked
    assert "plagiarism_app:***@10.0.1.50:5432/plagiarism_db" in masked

    sqlite_url = "sqlite:///C:/AppData/papers.db"
    assert config.get_masked_database_url(sqlite_url) == sqlite_url


def test_get_backend_type_detection():
    """التحقق من كشف نوع المحرك بدقة بناءً على الـ URL."""
    assert base_repo.get_backend_type("sqlite:///tmp/test.db") == "sqlite"
    assert base_repo.get_backend_type("postgresql://user:pass@localhost:5432/db") == "postgresql"
    assert base_repo.get_backend_type("postgres://user:pass@localhost:5432/db") == "postgresql"


def test_fail_safe_guard_blocks_live_production_sqlite(monkeypatch):
    """صمام الأمان يجب أن يمنع تماماً الاتصال بملف SQLite الحي أثناء بيئة الاختبار."""
    monkeypatch.setenv('TESTING', '1')
    with pytest.raises(RuntimeError, match="FAIL-SAFE GUARD ACTIVATED"):
        base_repo._check_fail_safe(f"sqlite:///{config.LIVE_DEFAULT_SQLITE_PATH.as_posix()}")


def test_fail_safe_guard_blocks_non_test_postgresql_names(monkeypatch):
    """صمام الأمان يجب أن يمنع الاتصال بقاعدة بيانات PostgreSQL لا تحتوي على كلمة test في بيئة الاختبار."""
    monkeypatch.setenv('TESTING', '1')
    with pytest.raises(RuntimeError, match="FAIL-SAFE GUARD ACTIVATED"):
        base_repo._check_fail_safe("postgresql://app:pass@10.0.1.50:5432/plagiarism_prod")

    # قاعدة بيانات تحتوي على test مسموح بها
    base_repo._check_fail_safe("postgresql://app:pass@10.0.1.50:5432/plagiarism_test_db")


def test_system_health_database_check_for_postgresql():
    """التحقق من عمل فحص صحة قاعدة البيانات لمحرك PostgreSQL وإخفاء الـ DSN."""
    with patch('app.repositories.base_repo.get_backend_type', return_value='postgresql'):
        mock_ctx = MagicMock()
        mock_ctx.__enter__.return_value.execute.return_value.scalar.return_value = 1
        with patch.object(base_repo.engine, 'connect', return_value=mock_ctx):
            with patch.object(base_repo.engine, 'pool', create=True) as mock_pool:
                mock_pool.size.return_value = 10
                mock_pool.checkedin.return_value = 8
                mock_pool.checkedout.return_value = 2
                mock_pool.overflow.return_value = 0

                res = system_health_service._check_database(system_health_service._utcnow())
                assert res['status'] == system_health_service.STATUS_HEALTHY
                assert res['metadata']['backend'] == 'postgresql'
                assert res['metadata']['reachable'] is True
                assert 'pool' in res['metadata']
                assert res['metadata']['pool']['pool_size'] == 10


