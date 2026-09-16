# -*- coding: utf-8 -*-
"""
سلسلة الاختبارات الآلية للتحقق من سلامة مشغلات الويندوز التنفيذية (.exe launchers):
- التحقق من وجود وحجم وصحة المشغلات الثمانية.
- التحقق من رفض التشغيل (Fail-Closed) عند غياب Runtime\python.exe.
- التحقق من صحة استدعاء الأوامر عبر portable_cli.
"""

import os
import sys
import subprocess
import pytest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT_DIR / "dist" / "Arabic-Academic-Plagiarism-System"

EXE_NAMES = [
    "Start-System.exe",
    "Stop-System.exe",
    "Setup-System.exe",
    "Check-System.exe",
    "Backup-System.exe",
    "Restore-System.exe",
    "View-Logs.exe",
    "Create-Diagnostic-Package.exe"
]


def test_all_exe_launchers_exist_in_package():
    """التحقق من وجود كافة ملفات الـ EXE الثمانية وأحجامها الإيجابية."""
    from tools.build_exe_launchers import build_launchers
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    build_launchers(DIST_DIR)

    for exe_name in EXE_NAMES:
        exe_path = DIST_DIR / exe_name
        assert exe_path.exists(), f"EXE missing: {exe_name}"
        assert exe_path.stat().st_size > 10000, f"EXE too small: {exe_name}"


def test_start_exe_fails_closed_when_runtime_missing(tmp_path):
    """التحقق من أن Start-System.exe يرفض الإقلاع بحزم إذا لم يجد Runtime\\python.exe."""
    from tools.build_exe_launchers import build_launchers
    build_launchers(tmp_path)
    
    start_exe = tmp_path / "Start-System.exe"
    assert start_exe.exists()

    # تشغيل الـ EXE بدون وجود مجلد Runtime
    res = subprocess.run([str(start_exe)], input="\n", capture_output=True, text=True, cwd=str(tmp_path))
    assert res.returncode == 1
    assert "RUNTIME NOT FOUND" in res.stdout


def test_check_exe_executes_with_bundled_runtime(tmp_path):
    """التحقق من استدعاء Check-System.exe وتنفيذ أمر الفحص التشخيصي بنجاح."""
    from tools.build_exe_launchers import build_launchers
    build_launchers(tmp_path)

    # إنشاء مجلد Runtime وهمي بملف بايثون وهمي للاختبار السريع
    runtime_dir = tmp_path / "Runtime"
    runtime_dir.mkdir(exist_ok=True)
    tools_dir = tmp_path / "Tools"
    tools_dir.mkdir(exist_ok=True)

    fake_cli = tools_dir / "portable_cli.py"
    fake_cli.write_text('import sys; print("PORTABLE_CLI_CALLED_WITH:", sys.argv[1:]); sys.exit(0)', encoding='utf-8')

    # نسخ بايثون الحالي إلى Runtime
    import shutil
    shutil.copy2(sys.executable, runtime_dir / "python.exe")

    check_exe = tmp_path / "Check-System.exe"
    res = subprocess.run([str(check_exe), "--no-pause"], input="\n", capture_output=True, text=True, cwd=str(tmp_path))
    assert res.returncode == 0
    assert "PORTABLE_CLI_CALLED_WITH: ['check'" in res.stdout
