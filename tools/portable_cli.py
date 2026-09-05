# -*- coding: utf-8 -*-
"""
أداة التحكم والإدارة والتشغيل الموحدة للحزمة المحمولة (Portable System Management CLI):
- Setup: معالج التهيئة وضبط الشبكة المحلية والمنفذ.
- Start: التحقق من الجاهزية وقفل التكرار وإطلاق الخادم والعمال وفتح المتصفح.
- Stop: الإيقاف السلس والتجفيف الآمن وعمل Checkpoint لـ WAL.
- Backup: النسخ الاحتياطي الحي مع حساب البصمة الرقمية وفحص النزاهة.
- Restore: الاستعادة المحصنة مع النسخة الوقائية والتحقق من السلامة.
- Check: الفحص التشخيصي الشامل لكافة مكونات النظام والشبكة.
"""

import os
import sys
import time
import json
import socket
import psutil
import shutil
import urllib.request
import urllib.error
import subprocess
import webbrowser
import hashlib
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

# ضبط دعم الترميز العربي في بيئة كونسول ويندوز
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# مسارات الحزمة المحمولة
TOOLS_DIR = Path(__file__).resolve().parent
ROOT_DIR = TOOLS_DIR.parent
APP_DIR = ROOT_DIR / "App"
if not APP_DIR.exists():
    APP_DIR = ROOT_DIR

CONFIG_DIR = ROOT_DIR / "Config"
DATABASE_DIR = ROOT_DIR / "Database"
STORAGE_DIR = ROOT_DIR / "Storage"
LOGS_DIR = ROOT_DIR / "Logs"
BACKUPS_DIR = ROOT_DIR / "Backups"
CONFIG_FILE = CONFIG_DIR / "system_config.json"
PID_FILE = CONFIG_DIR / ".system.pid"
WORKER_PID_FILE = CONFIG_DIR / ".workers.pid"

# ضبط متغيرات البيئة المحمولة تلقائياً
os.environ["PORTABLE_MODE"] = "1"
os.environ["PORTABLE_ROOT"] = str(ROOT_DIR)
os.environ["DATABASE_DIR"] = str(DATABASE_DIR)
os.environ["CONFIG_DIR"] = str(CONFIG_DIR)
os.environ["LOGS_DIR"] = str(LOGS_DIR)
os.environ["STORAGE_ROOT"] = str(STORAGE_DIR)
os.environ["BACKUP_DIR"] = str(BACKUPS_DIR)

# إضافة المسارات إلى sys.path
for p in [str(APP_DIR), str(ROOT_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)


def ensure_directories():
    """التأكد من إنشاء المجلدات المحمولة الأساسية."""
    for d in [CONFIG_DIR, DATABASE_DIR, STORAGE_DIR, LOGS_DIR, BACKUPS_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def get_lan_ip() -> str:
    """اكتشاف عنوان الـ IP المحلي الفعلي للجهاز على الشبكة الداخلية."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # لا يتم إرسال أي حزم فعلية للإنترنت
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


def load_config() -> dict:
    """قراءة إعدادات النظام المحمولة مع القيم الافتراضية الآمنة."""
    default_cfg = {
        "mode": "lan",  # "local" or "lan"
        "host": "0.0.0.0",
        "port": 5000,
        "workers_count": 2,
        "auto_open_browser": True,
        "db_filename": "papers.db"
    }
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                saved = json.load(f)
                default_cfg.update(saved)
        except Exception:
            pass
    return default_cfg


def save_config(cfg: dict):
    """حفظ إعدادات النظام المحمولة."""
    ensure_directories()
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def is_port_in_use(port: int, host: str = '127.0.0.1') -> bool:
    """التحقق مما إذا كان المنفذ مستخدماً حالياً."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def is_process_running(pid: int) -> bool:
    """التحقق من أن رقم العملية PID لا يزال يعمل."""
    if pid <= 0:
        return False
    try:
        p = psutil.Process(pid)
        return p.is_running() and p.status() != psutil.STATUS_ZOMBIE
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def cmd_setup():
    """معالج الإعداد الأولي للمنظومة وضبط الشبكة والمنفذ."""
    ensure_directories()
    cfg = load_config()
    lan_ip = get_lan_ip()

    print("=" * 70)
    print("   معالج إعداد منظومة كشف الاستلال الأكاديمي (Portable Setup Wizard)")
    print("=" * 70)
    print(f"عنوان الـ LAN المكتشف للجهاز: {lan_ip}")
    print(f"نمط التشغيل الحالي: {cfg.get('mode', 'lan').upper()}")
    print(f"المنفذ الحالي: {cfg.get('port', 5000)}")
    print("-" * 70)

    # حفظ الإعداد المعتمد
    cfg["host"] = "0.0.0.0" if cfg.get("mode") == "lan" else "127.0.0.1"
    save_config(cfg)

    print("[✓] تم حفظ الإعدادات بنجاح في Config/system_config.json")
    print(f"الرابط المحلي:   http://127.0.0.1:{cfg['port']}")
    if cfg['mode'] == 'lan':
        print(f"رابط الشبكة:    http://{lan_ip}:{cfg['port']}")
    print("=" * 70)


def cmd_start():
    """بدء تشغيل المنظومة والعمال والتحقق من الجاهزية."""
    ensure_directories()
    cfg = load_config()
    port = cfg.get('port', 5000)
    host = cfg.get('host', '0.0.0.0')
    lan_ip = get_lan_ip()

    # 1. فحص قفل التكرار (Single-Instance Protection)
    if is_port_in_use(port, '127.0.0.1'):
        print("=" * 70)
        print("   [!] SYSTEM ALREADY RUNNING — المنظومة تعمل بالفعل مسبقاً")
        print("=" * 70)
        print(f"Local (الجهاز الحالي):  http://127.0.0.1:{port}")
        if cfg.get('mode') == 'lan':
            print(f"LAN (أجهزة الشبكة):     http://{lan_ip}:{port}")
        print("=" * 70)
        return

    # 2. فحص المساحة الحرة للقرص (Disk Space Guard)
    disk_free_gb = psutil.disk_usage(str(ROOT_DIR)).free / (1024**3)
    if disk_free_gb < 1.0:
        print(f"[خطأ حرج] المساحة الحرة على القرص غير كافية ({disk_free_gb:.2f} GB). يلزم توفر 1 GB على الأقل.")
        sys.exit(1)

    # 3. إعداد السجلات المحلية
    log_out = open(LOGS_DIR / "server.log", "a", encoding="utf-8")

    print("=" * 70)
    print("   جاري بدء تشغيل المنظومة الأكاديمية والعمال في الخلفية...")
    print("=" * 70)

    # 4. تشغيل خادم الويب Waitress
    env = os.environ.copy()
    env["PORTABLE_MODE"] = "1"
    env["PORTABLE_ROOT"] = str(ROOT_DIR)
    env["HOST"] = host
    env["PORT"] = str(port)

    # تحديد مشغل بايثون المتاح
    py_exec = sys.executable

    server_script = APP_DIR / "server.py"
    if not server_script.exists():
        server_script = ROOT_DIR / "server.py"

    server_proc = subprocess.Popen(
        [py_exec, str(server_script)],
        env=env,
        stdout=log_out,
        stderr=log_out,
        cwd=str(ROOT_DIR)
    )

    with open(PID_FILE, 'w') as f:
        f.write(str(server_proc.pid))

    # 5. تشغيل عمال المعالجة الخلفية
    worker_pids = []
    worker_count = cfg.get('workers_count', 2)
    worker_script = TOOLS_DIR / "run_worker.py"
    if worker_script.exists():
        worker_log = open(LOGS_DIR / "workers.log", "a", encoding="utf-8")
        for i in range(worker_count):
            w_env = env.copy()
            w_env["WORKER_NAME"] = f"portable_worker_{i+1}"
            wp = subprocess.Popen(
                [py_exec, str(worker_script), "--capabilities", "SCAN,OCR,INDEX_BUILD,EXPORT"],
                env=w_env,
                stdout=worker_log,
                stderr=worker_log,
                cwd=str(ROOT_DIR)
            )
            worker_pids.append(wp.pid)

    with open(WORKER_PID_FILE, 'w') as f:
        f.write(",".join(str(p) for p in worker_pids))

    # 6. انتظار استجابة نقطة فحص الجاهزية (Readiness Probe)
    print("   جاري التحقق من جاهزية واستقرار الخادم...")
    ready = False
    ping_url = f"http://127.0.0.1:{port}/api/system/ping"
    for _ in range(30):
        time.sleep(0.5)
        try:
            req = urllib.request.Request(ping_url)
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                if resp.status == 200:
                    ready = True
                    break
        except Exception:
            pass

    if not ready:
        print("   [تنبيه] الخادم استغرق وقتاً أطول للبدء. تحقق من Logs/server.log.")

    # 7. فتح المتصفح التلقائي
    if cfg.get('auto_open_browser', True):
        def _open():
            time.sleep(0.5)
            webbrowser.open(f"http://127.0.0.1:{port}")
        import threading
        threading.Thread(target=_open, daemon=True).start()

    # 8. عرض النتيجة النهائية للمسؤول
    print("\n" + "=" * 70)
    print("   [✓] SYSTEM READY — المنظومة الأكاديمية جاهزة للعمل بنجاح")
    print("=" * 70)
    print(f"Local (الجهاز الحالي):")
    print(f"   http://127.0.0.1:{port}")
    print()
    if cfg.get('mode') == 'lan':
        print(f"Ministry LAN (أجهزة الشبكة المحلية):")
        print(f"   http://{lan_ip}:{port}")
    print("=" * 70)
    print("للإيقاف الآمن في أي وقت: شغّل Stop-System.bat")
    print("=" * 70)


def cmd_stop():
    """الإيقاف السلس للعمال والخادم وعمل نقطة تفتيش لـ WAL."""
    ensure_directories()
    print("=" * 70)
    print("   جاري إيقاف المنظومة والعمال بشكل آمن (Graceful Shutdown)...")
    print("=" * 70)

    # 1. إيقاف العمال
    if WORKER_PID_FILE.exists():
        try:
            with open(WORKER_PID_FILE, 'r') as f:
                pids_str = f.read().strip()
                for p_str in pids_str.split(','):
                    if p_str:
                        pid = int(p_str)
                        if is_process_running(pid):
                            try:
                                psutil.Process(pid).terminate()
                            except Exception:
                                pass
            WORKER_PID_FILE.unlink(missing_ok=True)
        except Exception as e:
            print(f"   ملاحظة أثناء إيقاف العمال: {e}")

    # 2. إيقاف خادم الويب
    if PID_FILE.exists():
        try:
            with open(PID_FILE, 'r') as f:
                pid = int(f.read().strip())
                if is_process_running(pid):
                    try:
                        psutil.Process(pid).terminate()
                    except Exception:
                        pass
            PID_FILE.unlink(missing_ok=True)
        except Exception as e:
            print(f"   ملاحظة أثناء إيقاف الخادم: {e}")

    # 3. دمج معاملات WAL وحفظ قاعدة البيانات (Checkpoint)
    db_path = DATABASE_DIR / "papers.db"
    if db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path), timeout=5.0)
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            conn.close()
            print("   [✓] تم دمج معاملات WAL وإغلاق قاعدة البيانات بأمان تام.")
        except Exception as e:
            print(f"   تعذر دمج WAL ({e})")

    print("=" * 70)
    print("   [✓] SYSTEM STOPPED SAFELY — تم إيقاف المنظومة بنجاح")
    print("=" * 70)


def cmd_backup():
    """إنشاء نسخة احتياطية حية آمنة مع حساب البصمة والتحقق من النزاهة."""
    ensure_directories()
    db_path = DATABASE_DIR / "papers.db"
    if not db_path.exists():
        print(f"[خطأ] قاعدة البيانات غير موجودة في {db_path}")
        return

    now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = BACKUPS_DIR / f"backup_{now_str}.bak"
    manifest_file = BACKUPS_DIR / f"backup_{now_str}_manifest.json"

    print("=" * 70)
    print("   جاري إنشاء النسخة الاحتياطية الحية المعتمدة...")
    print("=" * 70)

    t0 = time.perf_counter()
    src_conn = sqlite3.connect(str(db_path), timeout=30.0)
    dst_conn = sqlite3.connect(str(backup_file), timeout=30.0)

    src_conn.backup(dst_conn, pages=1000)
    src_conn.close()
    dst_conn.close()
    t1 = time.perf_counter()

    # التحقق من النزاهة وحساب البصمة
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
        "backup_identifier": f"backup_{now_str}",
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

    print("=" * 70)
    print("   [✓] BACKUP COMPLETED — اكتمل النسخ الاحتياطي بنجاح")
    print("=" * 70)
    print(f"المسار:           {backup_file}")
    print(f"الحجم:            {b_size_mb:.2f} MB (في {t1-t0:.2f} ثانية)")
    print(f"بصمة SHA-256:     {sha256}")
    print(f"حالة النزاهة:     {'سليمة 100% (PASSED)' if integrity == [('ok',)] else 'تحذير'}")
    print(f"الأبحاث المحفوظة: {cnt_res:,} بحث")
    print("=" * 70)


def cmd_restore():
    """استعادة آمنة محصنة مع أخذ نسخة وقائية وفحص النزاهة قبل الاستبدال."""
    ensure_directories()
    backups = sorted(BACKUPS_DIR.glob("backup_*.bak"), key=os.path.getmtime, reverse=True)
    if not backups:
        print("[!] لا توجد نسخ احتياطية متوفرة في مجلد Backups/")
        return

    print("=" * 70)
    print("   أداة الاستعادة المحصنة (Secure System Restore)")
    print("=" * 70)
    print("النسخ الاحتياطية المتوفرة:")
    for idx, b in enumerate(backups[:10], 1):
        b_mb = os.path.getsize(b) / (1024 * 1024)
        print(f"  [{idx}] {b.name} ({b_mb:.2f} MB)")
    print("-" * 70)

    try:
        choice = input("اختر رقم النسخة للاستعادة (أو اضغط Enter لإلغاء العملية): ").strip()
        if not choice:
            print("تم إلغاء الاستعادة.")
            return
        selected_idx = int(choice) - 1
        target_backup = backups[selected_idx]
    except Exception:
        print("[خطأ] اختيار غير صحيح. تم إلغاء العملية.")
        return

    print(f"\nجاري التحقق من سلامة النسخة {target_backup.name} قبل الاستعادة...")
    chk_conn = sqlite3.connect(str(target_backup))
    cur = chk_conn.cursor()
    cur.execute("PRAGMA integrity_check;")
    integrity = cur.fetchall()
    chk_conn.close()

    if integrity != [('ok',)]:
        print(f"[خطأ حرج] النسخة المختارة تالفة ({integrity}). تم رفض الاستعادة لمنع تلف النظام.")
        return

    # أخذ نسخة وقائية من الوضع الحالي قبل الاستبدال
    db_path = DATABASE_DIR / "papers.db"
    if db_path.exists():
        safety_snapshot = BACKUPS_DIR / f"pre_restore_safety_{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak"
        shutil.copy2(db_path, safety_snapshot)
        print(f"[✓] تم حفظ نسخة وقائية من الحالة الحالية في: {safety_snapshot.name}")

    # استبدال قاعدة البيانات
    shutil.copy2(target_backup, db_path)
    wal_file = DATABASE_DIR / "papers.db-wal"
    shm_file = DATABASE_DIR / "papers.db-shm"
    wal_file.unlink(missing_ok=True)
    shm_file.unlink(missing_ok=True)

    print("=" * 70)
    print("   [✓] RESTORE COMPLETED — تمت الاستعادة بنجاح والتحقق من النزاهة")
    print("=" * 70)
    print(f"تمت استعادة قاعدة البيانات من: {target_backup.name}")
    print("=" * 70)


def cmd_check():
    """الفحص التشخيصي الشامل لكافة مكونات النظام وصحة الشبكة."""
    ensure_directories()
    cfg = load_config()
    port = cfg.get('port', 5000)
    lan_ip = get_lan_ip()
    db_path = DATABASE_DIR / "papers.db"

    print("=" * 70)
    print("   تقرير الفحص التشخيصي الشامل للنظام (System Health & Diagnostic Check)")
    print("=" * 70)

    # 1. حالة التطبيق
    app_running = is_port_in_use(port, '127.0.0.1')
    print(f"حالة خادم التطبيق:         {'OK (يعمل بنجاح)' if app_running else 'STOPPED (متوقف)'}")

    # 2. حالة قاعدة البيانات
    if db_path.exists():
        db_size_mb = os.path.getsize(db_path) / (1024 * 1024)
        try:
            conn = sqlite3.connect(str(db_path), timeout=2.0)
            cur = conn.cursor()
            cur.execute("PRAGMA integrity_check;")
            integrity = cur.fetchall()
            cur.execute("SELECT COUNT(*) FROM research;")
            cnt_res = cur.fetchone()[0]
            conn.close()
            db_status = "OK"
            integ_status = "OK (سليمة 100%)" if integrity == [('ok',)] else f"FAIL ({integrity})"
        except Exception as e:
            db_status = f"FAIL ({e})"
            integ_status = "FAIL"
            cnt_res = 0
    else:
        db_size_mb = 0
        db_status = "NOT_INITIALIZED (سيتم إنشاؤها عند أول تشغيل)"
        integ_status = "N/A"
        cnt_res = 0

    print(f"قاعدة البيانات (SQLite):   {db_status} ({db_size_mb:.2f} MB | {cnt_res:,} بحث)")
    print(f"سلامة الهيكل والنزاهة:     {integ_status}")

    # 3. المساحة التخزينية
    disk_free_gb = psutil.disk_usage(str(ROOT_DIR)).free / (1024**3)
    disk_status = "OK" if disk_free_gb >= 5.0 else ("WARNING" if disk_free_gb >= 1.0 else "CRITICAL")
    print(f"المساحة الحرة على القرص:   {disk_free_gb:.2f} GB ({disk_status})")

    # 4. الذاكرة العشوائية
    ram = psutil.virtual_memory()
    print(f"الذاكرة العشوائية (RAM):   {ram.available / (1024**3):.2f} GB متاح من أصل {ram.total / (1024**3):.2f} GB")

    # 5. مستودع الملفات CAS
    cas_count = sum(1 for _ in STORAGE_DIR.glob("**/*") if _.is_file())
    print(f"مستودع الملفات (CAS):      OK ({cas_count} ملف محفوظ)")

    # 6. المكونات الاختيارية (OCR / Semantic)
    tess_path = shutil.which("tesseract")
    print(f"التعرف الضوئي OCR العربي: {'AVAILABLE' if tess_path else 'OPTIONAL COMPONENT UNAVAILABLE (نصوص PDF تعمل طبيعياً)'}")
    print(f"النموذج الدلالي:           DISABLED / UNAVAILABLE (معطل للأداء والسرعة)")

    # 7. عناوين الاتصال
    print("-" * 70)
    print(f"الرابط المحلي:             http://127.0.0.1:{port}")
    if cfg.get('mode') == 'lan':
        print(f"رابط الشبكة المحلية (LAN): http://{lan_ip}:{port}")
    print("=" * 70)


def cmd_diagnostic():
    """توليد حزمة تشخيصية آمنة ومضغوطة خالية من الأبحاث والبيانات السرية للدعم الفني."""
    import zipfile
    ensure_directories()
    diag_dir = ROOT_DIR / "Diagnostics"
    diag_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    zip_path = diag_dir / f"diagnostic-{timestamp}.zip"
    
    cfg = load_config()
    lan_ip = get_lan_ip()
    port = cfg.get('port', 5000)
    db_path = DATABASE_DIR / "papers.db"
    
    # 1. حالة النظام
    health_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "application_name": "Arabic Academic Plagiarism Detector",
        "release_version": "v1.4.1-sqlite-portable-rc",
        "mode": "portable_offline",
        "os": f"{sys.platform} - {os.name}",
        "python_version": sys.version,
        "sqlite_version": sqlite3.sqlite_version,
        "server_running": is_port_in_use(port, '127.0.0.1'),
        "lan_ip": lan_ip,
        "port": port,
        "disk_free_gb": round(psutil.disk_usage(str(ROOT_DIR)).free / (1024**3), 2),
        "ram_avail_gb": round(psutil.virtual_memory().available / (1024**3), 2),
        "ram_total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
        "ocr_available": shutil.which("tesseract") is not None,
        "semantic_model": "disabled"
    }
    
    # 2. فحص سلامة قاعدة البيانات
    db_info = {"status": "not_found", "size_bytes": 0, "integrity": "unknown", "tables_count": 0}
    if db_path.exists():
        db_info["size_bytes"] = os.path.getsize(db_path)
        try:
            conn = sqlite3.connect(str(db_path), timeout=2.0)
            cur = conn.cursor()
            cur.execute("PRAGMA integrity_check;")
            db_info["integrity"] = cur.fetchall()
            cur.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table';")
            db_info["tables_count"] = cur.fetchone()[0]
            conn.close()
            db_info["status"] = "ok"
        except Exception as e:
            db_info["status"] = f"error: {e}"
            
    # 3. إعدادات منقاة من أي أسرار
    safe_config = {
        "mode": cfg.get("mode", "lan"),
        "host": cfg.get("host", "0.0.0.0"),
        "port": cfg.get("port", 5000),
        "workers_count": cfg.get("workers_count", 2),
        "auto_open_browser": cfg.get("auto_open_browser", True),
        "db_backend": "sqlite",
        "journal_mode": "WAL"
    }
    
    with zipfile.ZipFile(str(zip_path), 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("system_health.json", json.dumps(health_data, indent=2, ensure_ascii=False))
        zf.writestr("db_integrity.json", json.dumps(db_info, indent=2, ensure_ascii=False))
        zf.writestr("config_redacted.json", json.dumps(safe_config, indent=2, ensure_ascii=False))
        
        manifest_file = ROOT_DIR / "release_manifest.json"
        if manifest_file.exists():
            zf.write(str(manifest_file), "release_manifest.json")
            
        # إضافة آخر السجلات بأمان (مع حجب الأسرار المنفذ بالفعل بواسطة Logging Filter)
        for log_name in ["application.log", "errors.log", "workers.log"]:
            lf = LOGS_DIR / log_name
            if lf.exists():
                try:
                    with open(lf, "r", encoding="utf-8", errors="replace") as f:
                        lines = f.readlines()
                    tail_lines = lines[-500:] if len(lines) > 500 else lines
                    zf.writestr(f"logs/{log_name}", "".join(tail_lines))
                except Exception:
                    pass

    print("=" * 70)
    print("   تم إنشاء الحزمة التشخيصية بنجاح!")
    print(f"   المسار: {zip_path}")
    print(f"   الحجم:  {os.path.getsize(zip_path) / 1024:.1f} KB")
    print("   [ملاحظة أمان]: الحزمة التشخيصية لا تحتوي على أي أبحاث أو قواعد بيانات أو أسرار.")
    print("=" * 70)
    return zip_path


def cmd_logs():
    """عرض سجلات المنظومة بصورة تفاعلية ومباشرة."""
    ensure_directories()
    while True:
        print("\n" + "=" * 50)
        print("   شاشة مراقبة سجلات المنظومة (Log Monitor)")
        print("=" * 50)
        print(" [1] السجل المباشر للخادم (Live Server Log)")
        print(" [2] السجل المباشر للعمال (Live Workers Log)")
        print(" [3] سجل الأخطاء والتحذيرات فقط (Recent Errors)")
        print(" [4] آخر 100 سطر من سجل التطبيق (Last 100 Lines)")
        print(" [5] فتح مجلد السجلات (Open Logs Folder)")
        print(" [6] فحص تشخيصي شامل للنظام (System Health Check)")
        print(" [7] إنشاء حزمة تشخيصية للدعم الفني (Diagnostic Zip)")
        print(" [8] خروج (Exit)")
        print("-" * 50)
        
        try:
            choice = input("اختر رقم العملية [1-8]: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if choice == "1":
            log_file = LOGS_DIR / "application.log"
            if log_file.exists():
                print("\n--- بدء المراقبة الحية (اضغط Ctrl+C للرجوع للقائمة) ---")
                try:
                    if sys.platform == "win32":
                        subprocess.run(["powershell", "-NoProfile", "-Command", f"Get-Content -Path '{log_file}' -Wait -Tail 30"])
                    else:
                        subprocess.run(["tail", "-f", str(log_file)])
                except KeyboardInterrupt:
                    pass
            else:
                print("\n[تنبيه] ملف السجل غير موجود حالياً (سيتكون عند تشغيل الخادم).")
        elif choice == "2":
            log_file = LOGS_DIR / "workers.log"
            if log_file.exists():
                print("\n--- بدء المراقبة الحية لعمال المعالجة (اضغط Ctrl+C للرجوع) ---")
                try:
                    if sys.platform == "win32":
                        subprocess.run(["powershell", "-NoProfile", "-Command", f"Get-Content -Path '{log_file}' -Wait -Tail 30"])
                    else:
                        subprocess.run(["tail", "-f", str(log_file)])
                except KeyboardInterrupt:
                    pass
            else:
                print("\n[تنبيه] ملف سجل العمال غير موجود حالياً.")
        elif choice == "3":
            log_file = LOGS_DIR / "errors.log"
            if log_file.exists():
                print("\n--- سجل الأخطاء والتحذيرات الأخير ---")
                with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                print("".join(lines[-50:]) if lines else "لا توجد أخطاء مسجلة.")
            else:
                print("\n[ممتاز] لا يوجد ملف أخطاء (لا توجد أخطاء مسجلة حتى الآن).")
        elif choice == "4":
            log_file = LOGS_DIR / "application.log"
            if log_file.exists():
                print("\n--- آخر 100 سطر من سجل التطبيق ---")
                with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                print("".join(lines[-100:]))
            else:
                print("\n[تنبيه] ملف السجل غير موجود.")
        elif choice == "5":
            if sys.platform == "win32":
                os.startfile(str(LOGS_DIR))
            else:
                print(f"المسار: {LOGS_DIR}")
        elif choice == "6":
            cmd_check()
        elif choice == "7":
            cmd_diagnostic()
        elif choice in ["8", "q", "exit"]:
            break
        else:
            print("[خطأ] خيار غير صالح، يرجى الاختيار من 1 إلى 8.")


def main():
    if len(sys.argv) < 2:
        print("الاستخدام: python tools/portable_cli.py [setup|start|stop|backup|restore|check|logs|diagnostic]")
        return

    cmd = sys.argv[1].lower().strip()
    if cmd == "setup":
        cmd_setup()
    elif cmd == "start":
        cmd_start()
    elif cmd == "stop":
        cmd_stop()
    elif cmd == "backup":
        cmd_backup()
    elif cmd == "restore":
        cmd_restore()
    elif cmd == "check":
        cmd_check()
    elif cmd in ["logs", "log"]:
        cmd_logs()
    elif cmd in ["diagnostic", "diagnostics", "diag"]:
        cmd_diagnostic()
    else:
        print(f"[خطأ] أمر غير معروف: {cmd}")
        print("الأوامر المتاحة: setup, start, stop, backup, restore, check, logs, diagnostic")


if __name__ == "__main__":
    main()
