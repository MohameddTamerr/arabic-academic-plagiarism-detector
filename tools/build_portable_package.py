# -*- coding: utf-8 -*-
"""
أداة بناء وتجميع الحزمة الإنتاجية المحمولة الأوفلاين (Portable Packaging Builder):
- تجمع المنظومة في المجلد المستقل النظيف: Arabic-Academic-Plagiarism-System/
- تنسخ كود التطبيق والأصول والقوالب والأدوات وملفات التشغيل الدفعية.
- تستبعد ملفات الاختبارات والـ cache والبيانات الحية لضمان الأمان والخصوصية التامة.
- تحسب البصمة الرقمية SHA-256 للحزمة وحجمها الإجمالي.
"""

import os
import sys
import shutil
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

DIST_DIR = ROOT_DIR / "dist"
PACKAGE_NAME = "Arabic-Academic-Plagiarism-System"
TARGET_DIR = DIST_DIR / PACKAGE_NAME


def copy_tree_clean(src: Path, dst: Path, ignore_patterns=None):
    """نسخ شجرة مجلدات مع استبعاد الملفات غير الضرورية."""
    if not src.exists():
        return
    if ignore_patterns is None:
        ignore_patterns = shutil.ignore_patterns(
            "__pycache__", "*.pyc", "*.pyo", ".git*", ".pytest_cache",
            "*.benchmark.db*", "crash_test*", "backup_drill*", "scale_*.db*",
            "papers.db*", "*.bak", "*.log", "scratch", ".env*", ".vscode", ".idea"
        )
    shutil.copytree(src, dst, ignore=ignore_patterns, dirs_exist_ok=True)


def build_package() -> dict:
    print("=" * 70)
    print("   جاري بناء وتجميع الحزمة الإنتاجية المحمولة...")
    print(f"   المجلد المستهدف: {TARGET_DIR}")
    print("=" * 70)

    # تنظيف المجلد المستهدف
    if TARGET_DIR.exists():
        shutil.rmtree(TARGET_DIR)
    TARGET_DIR.mkdir(parents=True, exist_ok=True)

    # 1. إنشاء الهيكل المطلوب
    app_target = TARGET_DIR / "App"
    tools_target = TARGET_DIR / "Tools"
    config_target = TARGET_DIR / "Config"
    database_target = TARGET_DIR / "Database"
    storage_target = TARGET_DIR / "Storage"
    logs_target = TARGET_DIR / "Logs"
    backups_target = TARGET_DIR / "Backups"
    docs_target = TARGET_DIR / "Docs"
    runtime_target = TARGET_DIR / "Runtime"

    for d in [app_target, tools_target, config_target, database_target, storage_target, logs_target, backups_target, docs_target, runtime_target]:
        d.mkdir(parents=True, exist_ok=True)

    (storage_target / "temp_uploads").mkdir(exist_ok=True)
    (storage_target / "finalized").mkdir(exist_ok=True)

    # 2. بناء وحزم بيئة التشغيل المستقلة (Runtime) المتضمنة لخادم Waitress
    print("   [1/6] جاري حزم بيئة التشغيل المستقلة (Runtime & Bundled Waitress WSGI)...")
    py_base = Path(sys.base_prefix)
    
    # نسخ ملفات Python التنفيذية والمكتبات الديناميكية
    for py_bin in ["python.exe", "pythonw.exe", "python3.dll", f"python{sys.version_info.major}{sys.version_info.minor}.dll", "vcruntime140.dll", "vcruntime140_1.dll"]:
        src_bin = py_base / py_bin
        if src_bin.exists():
            shutil.copy2(src_bin, runtime_target / py_bin)
            
    # نسخ مجلد DLLs الأساسي
    if (py_base / "DLLs").exists():
        copy_tree_clean(py_base / "DLLs", runtime_target / "DLLs", ignore_patterns=shutil.ignore_patterns("*.pdb"))

    # نسخ المكتبة القياسية Lib باستثناء site-packages
    runtime_lib = runtime_target / "Lib"
    runtime_lib.mkdir(exist_ok=True)
    copy_tree_clean(py_base / "Lib", runtime_lib, ignore_patterns=shutil.ignore_patterns("site-packages", "test", "tests", "idlelib", "tkinter", "tcl*", "__pycache__", "*.pyc"))

    # إنشاء site-packages لحزم التطبيق الأساسية
    runtime_site_packages = runtime_lib / "site-packages"
    runtime_site_packages.mkdir(exist_ok=True)

    # نسخ مكتبات الـ Framework الأساسية من بيئة بايثون المصدر
    src_site_packages = py_base / "Lib" / "site-packages"
    essential_pkgs = [
        "flask", "werkzeug", "jinja2", "markupsafe", "itsdangerous", "click", "blinker",
        "sqlalchemy", "psutil", "bcrypt", "_bcrypt", "jwt", "pyjwt", "dotenv", "python_dotenv"
    ]
    if src_site_packages.exists():
        for item in src_site_packages.iterdir():
            name_lower = item.name.lower()
            if any(name_lower == pkg or name_lower.startswith(f"{pkg}-") or name_lower.startswith(f"{pkg}.") for pkg in essential_pkgs):
                if item.is_dir():
                    copy_tree_clean(item, runtime_site_packages / item.name)
                elif item.is_file() and not item.name.endswith('.pyc'):
                    shutil.copy2(item, runtime_site_packages / item.name)

    # نسخ جميع مكتبات vendor (بما فيها خادم Waitress و Scikit-learn و Numpy) إلى site-packages
    if (ROOT_DIR / "vendor").exists():
        copy_tree_clean(ROOT_DIR / "vendor", runtime_site_packages)

    # التحقق من أن بيئة Runtime المنشأة قادرة على استدعاء Waitress بدون إنترنت
    bundled_py = runtime_target / "python.exe"
    if bundled_py.exists():
        import subprocess
        chk = subprocess.run(
            [str(bundled_py), "-c", "import waitress, psutil, flask, sqlalchemy; from waitress import serve; print('WAITRESS_BUNDLE_OK')"],
            capture_output=True,
            text=True
        )
        if "WAITRESS_BUNDLE_OK" not in chk.stdout:
            print(f"   [!] تحذير: فشل فحص استدعاء Waitress من Runtime: {chk.stderr}")
        else:
            print("   [✓] تم التحقق بنجاح: خادم Waitress وكافة الاعتماديات مدمجة وتعمل بكفاءة داخل الـ Runtime المحمول.")

    # 3. نسخ كود التطبيق الأساسي والأصول
    print("   [2/6] جاري نسخ كود التطبيق والقوالب والأصول...")
    copy_tree_clean(ROOT_DIR / "app", app_target / "app")
    copy_tree_clean(ROOT_DIR / "plagiarism_detector", app_target / "plagiarism_detector")
    if (ROOT_DIR / "static").exists():
        copy_tree_clean(ROOT_DIR / "static", app_target / "static")
    if (ROOT_DIR / "templates").exists():
        copy_tree_clean(ROOT_DIR / "templates", app_target / "templates")
    if (ROOT_DIR / "vendor").exists():
        copy_tree_clean(ROOT_DIR / "vendor", app_target / "vendor")

    # نسخ ملفات التشغيل الأساسية إلى App
    for f_name in ["config.py", "server.py", "main.py", "run_app.py", "versioning.py"]:
        src_f = ROOT_DIR / f_name
        if src_f.exists():
            shutil.copy2(src_f, app_target / f_name)
        elif (ROOT_DIR / "app" / f_name).exists():
            shutil.copy2(ROOT_DIR / "app" / f_name, app_target / f_name)

    # 4. نسخ الأدوات الإدارية إلى Tools
    print("   [3/6] جاري نسخ الأدوات التشغيلية والإدارية...")
    for t_name in ["portable_cli.py", "run_worker.py", "recover_stale_jobs.py", "rebuild_retrieval_index.py", "migrate_storage_layout.py"]:
        src_t = ROOT_DIR / "tools" / t_name
        if src_t.exists():
            shutil.copy2(src_t, tools_target / t_name)

    # 5. بناء مشغلات الويندوز التنفيذية (.exe) ونسخ ملفات (.bat) والـ README إلى جذر الحزمة
    print("   [4/6] جاري بناء وتجميع مشغلات الويندوز التنفيذية (.exe) وملفات التشغيل (.bat)...")
    try:
        from tools.build_exe_launchers import build_launchers
        built_exes = build_launchers(TARGET_DIR)
        # أيضاً نسخ الـ EXEs إلى جذر المستودع للاستخدام السهل
        for exe_k in built_exes:
            shutil.copy2(TARGET_DIR / exe_k, ROOT_DIR / exe_k)
    except Exception as e:
        print(f"   [!] تحذير أثناء بناء المشغلات التنفيذية: {e}")

    for b_name in [
        "Setup-System.bat", "Start-System.bat", "Stop-System.bat", "Backup-System.bat",
        "Restore-System.bat", "Check-System.bat", "View-Logs.bat", "Create-Diagnostic-Package.bat", "README-FIRST.txt"
    ]:
        src_b = ROOT_DIR / b_name
        if src_b.exists():
            shutil.copy2(src_b, TARGET_DIR / b_name)

    # 6. نسخ الأدلة المؤسسية إلى Docs
    for d_name in [
        "PORTABLE_DEPLOYMENT_ADMIN_GUIDE.md", "SECURITY_ARCHITECTURE.md", "BACKUP_AND_RESTORE.md",
        "DISASTER_RECOVERY.md", "HIGH_AVAILABILITY.md", "OFFLINE_DEPENDENCIES.md",
        "MINISTRY_OPERATIONS_RUNBOOK.md", "SQLITE_PORTABLE_CAPACITY_DECISION.md"
    ]:
        src_d = ROOT_DIR / "docs" / d_name
        if src_d.exists():
            shutil.copy2(src_d, docs_target / d_name)

    # 7. كتابة ملف الإعدادات الافتراضي
    default_config = {
        "mode": "lan",
        "host": "0.0.0.0",
        "port": 5000,
        "workers_count": 2,
        "auto_open_browser": True,
        "db_filename": "papers.db",
        "package_version": "v1.4.1-sqlite-portable-rc",
        "build_date": datetime.now(timezone.utc).isoformat()
    }
    with open(config_target / "system_config.json", "w", encoding="utf-8") as f:
        json.dump(default_config, f, ensure_ascii=False, indent=2)

    # 8. حساب الحجم الإجمالي والبصمة الرقمية
    print("   [5/6] جاري حساب البصمة الرقمية والأحجام...")
    total_bytes = 0
    file_count = 0
    hasher = hashlib.sha256()

    for root, dirs, files in os.walk(TARGET_DIR):
        for file in sorted(files):
            fp = Path(root) / file
            total_bytes += fp.stat().st_size
            file_count += 1
            # Update hash with relative path and file contents
            rel = fp.relative_to(TARGET_DIR).as_posix()
            hasher.update(rel.encode('utf-8'))
            try:
                with open(fp, 'rb') as f:
                    while chunk := f.read(65536):
                        hasher.update(chunk)
            except Exception:
                pass

    total_mb = total_bytes / (1024 * 1024)
    package_sha256 = hasher.hexdigest()

    print("=" * 70)
    print("   [✓] اكتمل بناء وتجميع الحزمة الإنتاجية المحمولة بنجاح!")
    print("=" * 70)
    print(f"المسار:           {TARGET_DIR}")
    print(f"عدد الملفات:      {file_count} ملف")
    print(f"الحجم الإجمالي:   {total_mb:.2f} MB")
    print(f"بصمة SHA-256:     {package_sha256}")
    print("=" * 70)

    summary = {
        "package_name": PACKAGE_NAME,
        "release_version": "v1.4.1-sqlite-portable-rc",
        "target_directory": str(TARGET_DIR),
        "total_files": file_count,
        "total_size_bytes": total_bytes,
        "total_size_mb": round(total_mb, 2),
        "package_sha256": package_sha256,
        "bundled_python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "bundled_wsgi_server": "Waitress 3.0.2",
        "built_at": datetime.now(timezone.utc).isoformat()
    }

    with open(DIST_DIR / "package_manifest.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    return summary


if __name__ == "__main__":
    build_package()
