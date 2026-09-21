import os
import gc
import shutil
import tempfile
from pathlib import Path
import pytest

import config
from app.repositories import base_repo

@pytest.fixture(autouse=True)
def isolated_local_antivirus(monkeypatch):
    """Use a clean local scanner double; security tests override its responses."""
    from app.services import upload_validation_service as validation
    from types import SimpleNamespace
    original_run = validation.subprocess.run
    monkeypatch.setattr(validation, '_find_antivirus_engine', lambda: 'clamscan')
    def run(command, *args, **kwargs):
        if isinstance(command, list) and command and command[0] == 'clamscan':
            return SimpleNamespace(returncode=0, stdout=(str(command[-1]) + ': OK\n').encode(), stderr=b'')
        return original_run(command, *args, **kwargs)
    monkeypatch.setattr(validation.subprocess, 'run', run)

@pytest.fixture(scope="session", autouse=True)
def setup_test_database(tmp_path_factory):
    """
    تهيئة بيئة اختبارات معزولة بالكامل لكل جلسة فحص (Session-Scoped Isolation):
    1. إنشاء مجلد مؤقت منفصل تماماً عن مسارات الإنتاج.
    2. ضبط متغيرات البيئة وإعادة توجيه مسارات config.
    3. تفعيل مؤشر TESTING=1 لتشغيل صمام الأمان (Fail-Safe Guard).
    4. إعادة ربط محرك SQLAlchemy وتهيئة الجداول والهجرات.
    5. تنظيف البيئة المؤقتة عند اكتمال الجلسة.
    """
    # 1. تفعيل مؤشر الاختبارات
    os.environ['TESTING'] = '1'

    # 2. إنشاء مجلد مؤقت مستقل
    session_tmp_dir = tmp_path_factory.mktemp("academic_test_env")
    test_appdata_dir = session_tmp_dir / 'AppData'
    test_appdata_dir.mkdir(parents=True, exist_ok=True)

    test_db_path = test_appdata_dir / 'test_papers.db'
    test_storage_root = test_appdata_dir / 'storage'
    test_storage_root.mkdir(parents=True, exist_ok=True)
    test_temp_upload_dir = test_storage_root / 'temp_uploads'
    test_temp_upload_dir.mkdir(parents=True, exist_ok=True)
    test_backup_dir = test_storage_root / 'backups'
    test_backup_dir.mkdir(parents=True, exist_ok=True)

    # 3. توجيه إعدادات المنظومة ومتغيرات البيئة إلى المسار المؤقت
    os.environ['DATABASE_URL'] = f"sqlite:///{test_db_path.as_posix()}"
    os.environ['STORAGE_ROOT'] = str(test_storage_root)
    os.environ['TEMP_UPLOAD_DIR'] = str(test_temp_upload_dir)
    os.environ['BACKUP_DIR'] = str(test_backup_dir)
    os.environ['APPDATA_OVERRIDE'] = str(test_appdata_dir)

    config.APPDATA_DIR = test_appdata_dir
    config.DEFAULT_SQLITE_PATH = test_db_path
    config.DATABASE_URL = f"sqlite:///{test_db_path.as_posix()}"
    config.STORAGE_ROOT = test_storage_root
    config.TEMP_UPLOAD_DIR = test_temp_upload_dir
    config.BACKUP_DIR = test_backup_dir
    config.SETTINGS_FILE = test_appdata_dir / 'academic_settings.json'

    # 4. إعادة ربط المحرك وتهيئة الجداول
    base_repo.rebind_engine(config.DATABASE_URL)
    base_repo.init_database()

    yield session_tmp_dir

    # 5. تنظيف المحرك والمجلد المؤقت
    if base_repo.engine:
        base_repo.engine.dispose()
    gc.collect()
    try:
        shutil.rmtree(str(session_tmp_dir), ignore_errors=True)
    except Exception:
        pass
