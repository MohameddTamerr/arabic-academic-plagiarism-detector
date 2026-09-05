@echo off
chcp 65001 >nul
title Arabic Academic Plagiarism Detector - Create Diagnostic Package
cd /d "%~dp0"

echo ======================================================================
echo    جاري إنشاء الحزمة التشخيصية للدعم الفني (Diagnostic Package)...
echo ======================================================================
echo.

if exist "Tools\portable_cli.py" (
    python "Tools\portable_cli.py" diagnostic
) else if exist "tools\portable_cli.py" (
    python "tools\portable_cli.py" diagnostic
) else (
    echo [خطأ] لم يتم العثور على أداة التحكم المحمولة tools/portable_cli.py
)

echo.
pause
