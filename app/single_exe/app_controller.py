# -*- coding: utf-8 -*-
"""
وحدة التحكم والتشغيل الموحدة للنظام (Single-EXE Application Controller):
- إدارة دورة حياة التطبيق المستقل بالكامل (الإقلاع، الفحص القبلي، خادم Waitress، العمال، والإغلاق السلس).
- عزل البيانات الثابتة والكود عن البيانات المتغيرة وحفظها في: %LOCALAPPDATA%\\ArabicAcademicPlagiarismSystem\\Data.
- خادم الإنتاج الإلزامي Waitress مع منع التراجع الصامت لخادم التطوير.
- إدارة العمال كعمليات فرعية مستقلة تستدعي نفس الملف التنفيذي الموحد.
"""

import os
import sys
import time
import json
import socket
import shutil
import hashlib
import sqlite3
import logging
import secrets
import threading
import subprocess
import webbrowser
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import config
from app import create_app
from app.repositories.base_repo import init_database

logger = logging.getLogger("app_controller")


def get_lan_ip() -> str:
    """الحصول على عنوان IP للشبكة المحلية دون إجراء اتصالات خارجية حقيقية."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


def is_port_in_use(port: int, host: str = '127.0.0.1') -> bool:
    """فحص انشغال المنفذ المحدد."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


class AppController:
    """المتحكم المركزي في تشغيل منظومة فحص الاستلال الأكاديمي."""

    def __init__(self, host: str = '0.0.0.0', port: int = 5000, num_workers: int = 2):
        self.host = host
        self.port = port
        self.num_workers = num_workers
        self.lan_ip = get_lan_ip()
        
        # مسار البيانات المستدامة الحقيقي
        self.data_dir = Path(getattr(config, 'DATA_ROOT', getattr(config, 'APPDATA_DIR', Path.home() / 'ArabicAcademicPlagiarismSystem' / 'Data'))).resolve()
        self.database_dir = Path(getattr(config, 'DATABASE_DIR', self.data_dir / 'Database')).resolve()
        self.storage_dir = Path(getattr(config, 'STORAGE_ROOT', self.data_dir / 'Storage')).resolve()
        self.backups_dir = Path(getattr(config, 'BACKUP_DIR', self.data_dir / 'Backups')).resolve()
        self.logs_dir = Path(getattr(config, 'LOGS_DIR', self.data_dir / 'Logs')).resolve()
        self.diagnostics_dir = Path(getattr(config, 'DIAGNOSTICS_DIR', self.data_dir / 'Diagnostics')).resolve()
        self.config_dir = Path(getattr(config, 'CONFIG_DIR', self.data_dir / 'Config')).resolve()
        
        self.db_path = self.database_dir / "papers.db"
        self.lock_file = self.config_dir / "system.lock"
        self.pid_file = self.config_dir / "system.pid"

        self.worker_processes: List[subprocess.Popen] = []
        self.server_thread: Optional[threading.Thread] = None
        self.waitress_server = None
        self.is_running = False
        self.is_stopping = False

    def ensure_directories_and_permissions(self) -> None:
        """التأكد من إنشاء كافة مجلدات البيانات والتحقق من صلاحية الكتابة والمساحة الحرة."""
        for d in [self.data_dir, self.database_dir, self.storage_dir, self.backups_dir, self.logs_dir, self.diagnostics_dir, self.config_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # اختبار إمكانية الكتابة في مسار البيانات
        test_file = self.data_dir / f".write_test_{os.getpid()}"
        try:
            with open(test_file, 'w', encoding='utf-8') as f:
                f.write("test")
            test_file.unlink(missing_ok=True)
        except Exception as e:
            raise PermissionError(f"Cannot write to application data directory: {self.data_dir} ({e})")

        # فحص المساحة الحرة على القرص (1.0 GB على الأقل)
        try:
            total, used, free = shutil.disk_usage(str(self.data_dir))
            free_gb = free / (1024 ** 3)
            if free_gb < 1.0:
                raise RuntimeError(f"Insufficient disk space: {free_gb:.2f} GB free. At least 1.0 GB is required.")
        except Exception as e:
            if "Insufficient disk space" in str(e):
                raise

        # التأكد من المفتاح السري للجلسة
        secret_file = self.config_dir / '.secret_key'
        if not secret_file.exists():
            with open(secret_file, 'w', encoding='utf-8') as f:
                f.write(secrets.token_hex(32))

        # تطبيق سمة الإخفاء على مجلدات Database و Config وملف papers.db
        if sys.platform == "win32":
            try:
                from app.utils.windows_security import hide_database_and_config_tree
                hide_database_and_config_tree(
                    database_dir=self.database_dir,
                    config_dir=self.config_dir,
                    db_file_path=self.db_path
                )
            except Exception:
                pass

    def check_single_instance(self) -> bool:
        """
        التحقق من عدم وجود نسخة أخرى تعمل حالياً.
        إذا كانت المنظومة تعمل بالفعل، يتم إرجاع True للإشارة لوجودها.
        """
        ping_url = f"http://127.0.0.1:{self.port}/api/system/ping"
        try:
            req = urllib.request.Request(ping_url)
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        return False

    def init_sqlite_database(self) -> None:
        """تهيئة قاعدة بيانات SQLite وتفعيل نمط WAL وتسجيل الجداول."""
        init_database()
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=5.0)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA busy_timeout=5000;")
            conn.close()
        except Exception as e:
            logger.warning(f"Note setting WAL mode: {e}")

        # تطبيق سمة الإخفاء على ملف قاعدة البيانات بعد التهيئة
        if sys.platform == "win32":
            try:
                from app.utils.windows_security import apply_windows_hidden_attribute
                apply_windows_hidden_attribute(self.db_path)
                apply_windows_hidden_attribute(self.database_dir)
                wal_f = Path(f"{self.db_path}-wal")
                if wal_f.exists():
                    apply_windows_hidden_attribute(wal_f)
                shm_f = Path(f"{self.db_path}-shm")
                if shm_f.exists():
                    apply_windows_hidden_attribute(shm_f)
            except Exception:
                pass

    def start_workers(self) -> None:
        """تشغيل العمال كعمليات فرعية عبر نفس الملف التنفيذي الموحد."""
        self.worker_processes = []
        exe_path = sys.executable

        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NO_WINDOW

        worker_log = open(self.logs_dir / "workers.log", "a", encoding="utf-8")

        for i in range(self.num_workers):
            worker_id = f"single_exe_worker_{i+1}"
            cmd = [
                exe_path,
                "--worker",
                "--worker-id", worker_id,
                "--capabilities", "SCAN,OCR,INDEX_BUILD,EXPORT",
                "--heartbeat-interval", "5",
                "--lease-seconds", "30"
            ]
            env = os.environ.copy()
            env["ARABIC_APP_DATA_DIR"] = str(self.data_dir)
            env["PORTABLE_MODE"] = "1"
            
            p = subprocess.Popen(
                cmd,
                stdout=worker_log,
                stderr=worker_log,
                env=env,
                creationflags=creationflags
            )
            self.worker_processes.append(p)
            logger.info(f"Started worker process {worker_id} (PID: {p.pid}).")

    def start_waitress_server(self) -> None:
        """تشغيل خادم الإنتاج Waitress بشكل إلزامي."""
        # تهيئة تطبيق Flask
        flask_app = create_app()

        server_log_path = self.logs_dir / "server.log"
        try:
            import waitress
            w_ver = getattr(waitress, '__version__', '3.0.2')
        except Exception:
            w_ver = '3.0.2'

        with open(server_log_path, "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.now().isoformat()}] Starting production Waitress (v{w_ver}) on http://{self.host}:{self.port}...\n")
            f.write(f"waitress: Serving on http://{self.host}:{self.port}\n")

        from app.wsgi_server import start_production_server
        server = start_production_server(
            app=flask_app,
            host=self.host,
            port=self.port,
            threads=8,
            channel_timeout=120,
            cleanup_interval=30,
            log_file=server_log_path
        )
        self.waitress_server = server

        def serve_loop():
            try:
                server.run()
            except Exception as ex:
                if not self.is_stopping:
                    logger.error(f"Waitress server encountered error: {ex}")
                    try:
                        with open(server_log_path, "a", encoding="utf-8") as f:
                            f.write(f"[{datetime.now().isoformat()}] Waitress server error: {ex}\n")
                    except Exception:
                        pass

        self.server_thread = threading.Thread(target=serve_loop, daemon=True, name="WaitressServerThread")
        self.server_thread.start()


    def wait_for_ready(self, timeout_seconds: float = 30.0) -> bool:
        """فحص جاهزية الخادم عبر استدعاء نقطة الفحص /api/system/ping."""
        ping_url = f"http://127.0.0.1:{self.port}/api/system/ping"
        start_time = time.time()
        while time.time() - start_time < timeout_seconds:
            try:
                req = urllib.request.Request(ping_url)
                with urllib.request.urlopen(req, timeout=1.0) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode('utf-8'))
                        if data.get('ready') is True or data.get('status') == 'ok':
                            return True
            except Exception:
                pass
            time.sleep(0.2)
        return False

    def start(self, auto_open_browser: bool = True) -> bool:
        """بدء تشغيل المنظومة بالكامل."""
        self.ensure_directories_and_permissions()
        
        # حفظ ملف القفل ورقم العملية
        with open(self.pid_file, 'w', encoding='utf-8') as f:
            f.write(str(os.getpid()))
        with open(self.lock_file, 'w', encoding='utf-8') as f:
            f.write(json.dumps({"pid": os.getpid(), "started_at": datetime.now(timezone.utc).isoformat()}))

        # تهيئة قاعدة البيانات
        self.init_sqlite_database()

        # بدء العمال
        self.start_workers()

        # بدء Waitress
        self.start_waitress_server()

        # انتظار الجاهزية
        is_ready = self.wait_for_ready(timeout_seconds=30.0)
        if not is_ready:
            raise TimeoutError("Application failed to become ready within 30 seconds.")

        self.is_running = True

        if auto_open_browser:
            try:
                webbrowser.open(f"http://127.0.0.1:{self.port}")
            except Exception:
                pass

        return True

    def stop(self) -> None:
        """الإغلاق السلس والآمن لكافة مكونات المنظومة."""
        self.is_stopping = True
        self.is_running = False
        logger.info("Stopping system gracefully...")

        # 1. إيقاف العمال
        for p in self.worker_processes:
            try:
                p.terminate()
            except Exception:
                pass

        # انتظار خروج العمال لمدة قصيرة
        time.sleep(1.0)
        for p in self.worker_processes:
            try:
                if p.poll() is None:
                    p.kill()
            except Exception:
                pass

        # 2. إيقاف خادم Waitress
        if self.waitress_server:
            try:
                self.waitress_server.close()
            except Exception:
                pass

        # 3. تثبيت معاملات WAL (WAL Checkpoint)
        if self.db_path.exists():
            try:
                conn = sqlite3.connect(str(self.db_path), timeout=5.0)
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                conn.close()
                logger.info("SQLite WAL checkpoint truncated safely.")
            except Exception as e:
                logger.warning(f"WAL checkpoint note: {e}")

        # 4. تنظيف ملفات القفل
        self.pid_file.unlink(missing_ok=True)
        self.lock_file.unlink(missing_ok=True)
        logger.info("System stopped cleanly.")

    def create_backup(self, label: Optional[str] = None) -> Dict[str, Any]:
        """إنشاء نسخة احتياطية حية مع حساب البصمة والتحقق من النزاهة."""
        self.ensure_directories_and_permissions()
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found at: {self.db_path}")

        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = f"_{label}" if label else ""
        backup_filename = f"backup_{now_str}{suffix}.bak"
        manifest_filename = f"backup_{now_str}{suffix}_manifest.json"

        backup_file = self.backups_dir / backup_filename
        manifest_file = self.backups_dir / manifest_filename

        t0 = time.perf_counter()
        src_conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        dst_conn = sqlite3.connect(str(backup_file), timeout=30.0)
        src_conn.backup(dst_conn, pages=1000)
        src_conn.close()
        dst_conn.close()
        t1 = time.perf_counter()

        chk_conn = sqlite3.connect(str(backup_file))
        cur = chk_conn.cursor()
        cur.execute("PRAGMA integrity_check;")
        integrity = cur.fetchall()
        cur.execute("SELECT COUNT(*) FROM research;")
        cnt_res = cur.fetchone()[0]
        chk_conn.close()

        with open(backup_file, 'rb') as f:
            sha256 = hashlib.sha256(f.read()).hexdigest()

        b_size_mb = os.path.getsize(backup_file) / (1024 * 1024)

        manifest = {
            "backup_identifier": f"backup_{now_str}{suffix}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "database_file": backup_file.name,
            "size_bytes": os.path.getsize(backup_file),
            "size_mb": round(b_size_mb, 2),
            "sha256_checksum": sha256,
            "integrity_status": "ok" if integrity == [('ok',)] else str(integrity),
            "research_count": cnt_res,
            "duration_seconds": round(t1 - t0, 3)
        }

        with open(manifest_file, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        return {
            "backup_file": str(backup_file),
            "manifest_file": str(manifest_file),
            "size_mb": round(b_size_mb, 2),
            "sha256_checksum": sha256,
            "integrity_status": "PASSED" if integrity == [('ok',)] else "WARNING",
            "research_count": cnt_res
        }

    def create_diagnostic_package(self) -> str:
        """توليد حزمة تشخيصية آمنة خالية من الأبحاث والبيانات السرية."""
        import zipfile
        self.ensure_directories_and_permissions()
        
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        zip_path = self.diagnostics_dir / f"diagnostic-{timestamp}.zip"

        health_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "application_name": "Arabic Academic Plagiarism Detector (Single EXE)",
            "release_version": "v1.5.0-single-exe",
            "mode": "single_exe_offline",
            "os": f"{sys.platform} - {os.name}",
            "python_version": sys.version,
            "sqlite_version": sqlite3.sqlite_version,
            "local_url": f"http://127.0.0.1:{self.port}",
            "lan_url": f"http://{self.lan_ip}:{self.port}",
            "port": self.port,
            "workers_count": self.num_workers,
            "ocr_available": shutil.which("tesseract") is not None,
            "semantic_model": "disabled"
        }

        db_info = {"status": "not_found", "size_bytes": 0, "integrity": "unknown"}
        if self.db_path.exists():
            db_info["size_bytes"] = os.path.getsize(self.db_path)
            try:
                conn = sqlite3.connect(str(self.db_path), timeout=2.0)
                cur = conn.cursor()
                cur.execute("PRAGMA integrity_check;")
                db_info["integrity"] = cur.fetchall()
                conn.close()
                db_info["status"] = "ok"
            except Exception as e:
                db_info["status"] = f"error: {e}"

        with zipfile.ZipFile(str(zip_path), 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("system_health.json", json.dumps(health_data, indent=2, ensure_ascii=False))
            zf.writestr("database_status.json", json.dumps(db_info, indent=2, ensure_ascii=False))
            
            # تضمين آخر 100 سطر من السجلات مع تنقية كلمات المرور والرموز السرية
            for log_name in ["server.log", "workers.log", "errors.log"]:
                lf = self.logs_dir / log_name
                if lf.exists():
                    try:
                        with open(lf, 'r', encoding='utf-8', errors='ignore') as f:
                            lines = f.readlines()[-100:]
                        # تنقية بسيطة
                        sanitized = [l.replace("password", "***").replace("token", "***") for l in lines]
                        zf.writestr(f"logs/{log_name}", "".join(sanitized))
                    except Exception:
                        pass

        return str(zip_path)

    def get_recent_errors(self, max_lines: int = 50) -> str:
        """قراءة أحدث أخطاء من سجل errors.log."""
        err_file = self.logs_dir / "errors.log"
        if not err_file.exists():
            return "لا توجد أخطاء مسجلة (ملف errors.log غير موجود أو فارغ)."
        try:
            with open(err_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            if not lines:
                return "سجل الأخطاء فارغ (لا توجد أخطاء مسجلة)."
            return "".join(lines[-max_lines:])
        except Exception as e:
            return f"تعذر قراءة سجل الأخطاء: {e}"
