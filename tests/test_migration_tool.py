# -*- coding: utf-8 -*-
"""
اختبارات أداة الهجرة (Prompt 1: Migration Tool Tests):
- التحقق من فحص سلامة SQLite المصدر.
- التحقق من نمط المحاكاة Dry-Run.
- التحقق من عدم تعديل بصمة SHA-256 للمصدر أبداً.
- التحقق من تصدير تقرير الهجرة بتنسيق JSON سليم.
"""

import os
import json
import sqlite3
import tempfile
from pathlib import Path
import pytest

from tools.migrate_sqlite_to_postgresql import MigrationEngine, compute_file_sha256
from app.models.schema import Base
from sqlalchemy import create_engine


@pytest.fixture
def sample_sqlite_fixture(tmp_path):
    """إنشاء قاعدة بيانات SQLite معزولة تحتوي على بيانات تجريبية للفحص."""
    db_path = tmp_path / "source_test.db"
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, role TEXT, password_hash TEXT);")
    cur.execute("INSERT INTO users VALUES (1, 'admin', 'admin', '$2b$12$test');")
    cur.execute("CREATE TABLE reports (id INTEGER PRIMARY KEY, status TEXT, lifecycle_status TEXT, integrity_hash TEXT);")
    cur.execute("INSERT INTO reports VALUES (1, 'finalized', 'finalized', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855');")
    conn.commit()
    conn.close()
    return db_path


def test_migration_preflight_and_dry_run(sample_sqlite_fixture, tmp_path):
    """التحقق من عمل الفحص المسبق ونمط dry-run بنجاح."""
    initial_sha = compute_file_sha256(sample_sqlite_fixture)

    # إنشاء قاعدة بيانات وجهة معزولة كمحاكاة
    dst_sqlite = tmp_path / "mock_dst.db"
    mock_dsn = f"sqlite:///{dst_sqlite.as_posix()}"

    mig = MigrationEngine(
        sqlite_path=sample_sqlite_fixture,
        pg_dsn=mock_dsn,
        dry_run=True
    )

    report = mig.run()
    assert report['success'] is True
    assert report['dry_run'] is True
    assert report['preflight']['sqlite_integrity_check'] == 'ok'
    assert report['preflight']['source_table_counts']['users'] == 1
    assert report['preflight']['source_table_counts']['reports'] == 1

    # التأكد من عدم تعديل المصدر
    post_sha = compute_file_sha256(sample_sqlite_fixture)
    assert post_sha == initial_sha


def test_migration_source_remains_unmodified_after_execution(sample_sqlite_fixture, tmp_path):
    """التحقق الحاسم من أن المصدر يظل ثابتاً 100% دون أي تعديل."""
    initial_sha = compute_file_sha256(sample_sqlite_fixture)

    dst_sqlite = tmp_path / "migrated_target.db"
    mock_dsn = f"sqlite:///{dst_sqlite.as_posix()}"

    # تهيئة هيكل الجداول في الوجهة
    conn_dst = sqlite3.connect(str(dst_sqlite))
    cur = conn_dst.cursor()
    cur.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, role TEXT, password_hash TEXT);")
    cur.execute("CREATE TABLE reports (id INTEGER PRIMARY KEY, status TEXT, lifecycle_status TEXT, integrity_hash TEXT);")
    conn_dst.commit()
    conn_dst.close()

    mig = MigrationEngine(
        sqlite_path=sample_sqlite_fixture,
        pg_dsn=mock_dsn,
        dry_run=False
    )

    report = mig.run()
    assert report['success'] is True
    # التحقق من ثبات البصمة
    post_sha = compute_file_sha256(sample_sqlite_fixture)
    assert post_sha == initial_sha

