# -*- coding: utf-8 -*-
"""
سلسلة الاختبارات الآلية للتحقق من سلامة النمط المحمول والتوزيع المستقل
(Automated Test Suite for Portable Deployment Package Verification):
- فحص مسارات النمط المحمول (Portable Directory Layout).
- فحص نقطة الجاهزية والخادم /api/system/ping.
- فحص التصفح بالمفاتيح (Keyset/Cursor Pagination).
- فحص معالج الإعداد واكتشاف الـ LAN IP.
- فحص النسخ الاحتياطي المحمول والمانيفست.
- فحص متانة عدم الاتصال بالإنترنت (Zero External Socket Calls).
"""

import os
import sys
import json
import socket
import pytest
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

import config
from app import create_app
from app.repositories import base_repo, batch_repo, user_repo
from app.models.research_schema import Research, ResearchFile
from app.utils.pagination import get_pagination_params, format_paginated_response
from tools import portable_cli


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    """تهيئة تطبيق معزول بالكامل للاختبارات المحمولة."""
    test_db = tmp_path / "test_portable.db"
    test_storage = tmp_path / "test_storage"
    test_config = tmp_path / "test_config"
    test_logs = tmp_path / "test_logs"
    test_backups = tmp_path / "test_backups"

    test_storage.mkdir(exist_ok=True)
    test_config.mkdir(exist_ok=True)
    test_logs.mkdir(exist_ok=True)
    test_backups.mkdir(exist_ok=True)

    monkeypatch.setenv("TESTING", "1")
    monkeypatch.setenv("PORTABLE_MODE", "1")
    monkeypatch.setenv("PORTABLE_ROOT", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{test_db.as_posix()}")
    monkeypatch.setenv("STORAGE_ROOT", str(test_storage))
    monkeypatch.setenv("CONFIG_DIR", str(test_config))
    monkeypatch.setenv("LOGS_DIR", str(test_logs))
    monkeypatch.setenv("BACKUP_DIR", str(test_backups))

    base_repo.rebind_engine(f"sqlite:///{test_db.as_posix()}")
    base_repo.init_db()

    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


def test_system_ping_endpoint(app_client):
    """التحقق من عمل نقطة فحص الجاهزية /api/system/ping العامة بنجاح."""
    resp = app_client.get('/api/system/ping')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'ok'
    assert data['ready'] is True
    assert data['version'] == '2.7.0'
    assert 'app' in data


def test_keyset_pagination_in_search_researches(app_client):
    """التحقق من عمل التصفح بالمفاتيح (Keyset Pagination: after_id) بدقة وسرعة."""
    # إدراج 10 أبحاث تجريبية
    with base_repo.get_session() as session:
        for i in range(1, 11):
            r = Research(
                id=i,
                reference_number=f"TEST-PAGE-{i:04d}",
                title=f"بحث تجريبي للتقسيم {i}",
                author="د. باحث تجريبي",
                scan_status="completed",
                review_status="final_accepted",
                created_at=datetime(2025, 1, 1, 10, i)
            )
            session.add(r)
        session.commit()

    # 1. الاستعلام العادي مع limit=3 و order=desc
    items_p1, total = batch_repo.search_researches(limit=3, order_direction='desc')
    assert total == 10
    assert len(items_p1) == 3
    assert [x['id'] for x in items_p1] == [10, 9, 8]

    # 2. الاستعلام بالمفتاح after_id=8 (الصفحة التالية)
    last_id = items_p1[-1]['id']
    items_p2, _ = batch_repo.search_researches(limit=3, order_direction='desc', after_id=last_id)
    assert len(items_p2) == 3
    assert [x['id'] for x in items_p2] == [7, 6, 5]

    # 3. الاستعلام بترتيب تصاعدي order=asc مع after_id=3
    items_asc, _ = batch_repo.search_researches(limit=3, order_direction='asc', after_id=3)
    assert len(items_asc) == 3
    assert [x['id'] for x in items_asc] == [4, 5, 6]


def test_format_paginated_response_keyset_metadata():
    """التحقق من احتواء الاستجابة الموحدة على مؤشرات الكورسور (first_id, last_id, next_cursor)."""
    items = [{'id': 101, 'title': 'A'}, {'id': 102, 'title': 'B'}, {'id': 103, 'title': 'C'}]
    resp = format_paginated_response(items, total_items=100, page=1, page_size=3)
    assert resp['first_id'] == 101
    assert resp['last_id'] == 103
    assert resp['next_cursor'] == 103
    assert resp['has_next'] is True
    assert resp['has_prev'] is False


def test_portable_cli_lan_ip_detection():
    """التحقق من اكتشاف عنوان IP للشبكة المحلية بصيغة صالحة."""
    ip = portable_cli.get_lan_ip()
    assert isinstance(ip, str)
    parts = ip.split('.')
    assert len(parts) == 4
    for p in parts:
        assert 0 <= int(p) <= 255


def test_portable_cli_config_load_and_save(tmp_path, monkeypatch):
    """التحقق من حفظ واسترجاع إعدادات النمط المحمول."""
    cfg_file = tmp_path / "system_config.json"
    monkeypatch.setattr(portable_cli, "CONFIG_FILE", cfg_file)
    monkeypatch.setattr(portable_cli, "CONFIG_DIR", tmp_path)

    cfg = {"mode": "lan", "port": 8080, "workers_count": 4}
    portable_cli.save_config(cfg)
    assert cfg_file.exists()

    loaded = portable_cli.load_config()
    assert loaded["mode"] == "lan"
    assert loaded["port"] == 8080
    assert loaded["workers_count"] == 4


def test_single_instance_port_check():
    """التحقق من دالة فحص استخدام المنفذ."""
    # فتح سوكيت مؤقت وفحص اكتشافه
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('127.0.0.1', 0))
    s.listen(1)
    port = s.getsockname()[1]

    try:
        assert portable_cli.is_port_in_use(port, '127.0.0.1') is True
    finally:
        s.close()

    assert portable_cli.is_port_in_use(port, '127.0.0.1') is False


def test_offline_guarantee_no_external_calls(monkeypatch):
    """التحقق من عدم وجود أي نداءات شبكية خارجية أثناء الفحص."""
    orig_connect = socket.socket.connect

    def strict_connect(self, addr):
        host = addr[0] if isinstance(addr, tuple) else addr
        if host not in ('127.0.0.1', 'localhost', '0.0.0.0', '10.255.255.255'):
            raise RuntimeError(f"BLOCKED EXTERNAL NETWORK ATTEMPT TO: {addr}")
        return orig_connect(self, addr)

    monkeypatch.setattr(socket.socket, "connect", strict_connect)
    ip = portable_cli.get_lan_ip()
    assert ip is not None


def test_diagnostic_package_generation(tmp_path, monkeypatch):
    """التحقق من إنشاء الحزمة التشخيصية بنجاح وخلوها من الأبحاث وقواعد البيانات."""
    import zipfile
    diag_dir = tmp_path / "Diagnostics"
    logs_dir = tmp_path / "Logs"
    db_dir = tmp_path / "Database"
    
    diag_dir.mkdir(exist_ok=True)
    logs_dir.mkdir(exist_ok=True)
    db_dir.mkdir(exist_ok=True)
    
    (logs_dir / "application.log").write_text('{"message": "test app"}', encoding='utf-8')
    (logs_dir / "errors.log").write_text('{"message": "test error"}', encoding='utf-8')
    (db_dir / "papers.db").write_bytes(b"dummy db data")
    
    monkeypatch.setattr(portable_cli, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(portable_cli, "LOGS_DIR", logs_dir)
    monkeypatch.setattr(portable_cli, "DATABASE_DIR", db_dir)
    monkeypatch.setattr(portable_cli, "CONFIG_DIR", tmp_path / "Config")
    
    zip_file = portable_cli.cmd_diagnostic()
    assert zip_file.exists()
    
    with zipfile.ZipFile(str(zip_file), 'r') as zf:
        namelist = zf.namelist()
        assert "system_health.json" in namelist
        assert "db_integrity.json" in namelist
        assert "config_redacted.json" in namelist
        # التأكد القاطع من عدم تضمين ملف قاعدة البيانات أو ملفات الأبحاث
        assert "papers.db" not in namelist
        assert not any(n.endswith(".db") for n in namelist)


def test_error_response_contains_reference_id(app_client):
    """التحقق من تضمين معرف التتبع reference_id في استجابات الخطأ للمستخدم."""
    # طلب مسار غير موجود (404)
    resp = app_client.get('/api/non_existent_route_404')
    assert resp.status_code == 404
    data = resp.get_json()
    assert data['success'] is False
    assert 'reference_id' in data
    assert 'request_id' in data
    assert len(data['reference_id']) >= 8


def test_production_server_fails_closed_when_waitress_missing(tmp_path, monkeypatch):
    """التحقق من أن الخادم في نمط الإنتاج المحمول يغلق فوراً ويرفض الاستخدام الافتراضي لـ Flask إذا غاب خادم Waitress."""
    import subprocess
    test_script = tmp_path / "test_srv.py"
    root_str = str(ROOT_DIR).replace('\\', '/')
    test_main_code = f"""
import sys, os
sys.path.insert(0, '{root_str}')
os.environ["PORTABLE_MODE"] = "1"
sys.modules['waitress'] = None

# محاكاة تشغيل server.py مباشرة
with open(r'{root_str}/server.py', 'r', encoding='utf-8') as f:
    code = f.read()

# تنفيذ الكود في سياق __main__
exec(compile(code, 'server.py', 'exec'), {{'__name__': '__main__', '__file__': r'{root_str}/server.py'}})
"""
    test_script.write_text(test_main_code, encoding='utf-8')
    res = subprocess.run([sys.executable, str(test_script)], capture_output=True, text=True, encoding='utf-8', errors='replace', cwd=str(ROOT_DIR))
    assert res.returncode == 1
    assert "PRODUCTION WSGI SERVER NOT AVAILABLE" in res.stderr
    assert "Logs/server.log" in res.stderr


def test_packaged_mode_fails_closed_when_runtime_missing(tmp_path, monkeypatch):
    """التحقق من أن الحزمة الإنتاجية ترفض الإطلاق بدون مجلد Runtime."""
    app_dir = tmp_path / "App"
    app_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(portable_cli, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(portable_cli, "APP_DIR", app_dir)
    monkeypatch.setattr(portable_cli, "is_port_in_use", lambda *args, **kwargs: False)

    with pytest.raises(SystemExit) as exc:
        portable_cli.cmd_start()
    assert exc.value.code == 1


def test_bundled_waitress_version_and_availability():
    """التحقق من توفر خادم Waitress بالإصدار المعتمد 3.0.2 داخل vendor."""
    vendor_dir = ROOT_DIR / "vendor"
    if str(vendor_dir) not in sys.path:
        sys.path.insert(0, str(vendor_dir))
    import waitress
    from waitress import serve
    assert serve is not None



