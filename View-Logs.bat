@echo off
chcp 65001 >nul
title Arabic Academic Plagiarism Detector - Log Monitor
cd /d "%~dp0"

if exist "Tools\portable_cli.py" (
    python "Tools\portable_cli.py" logs
) else if exist "tools\portable_cli.py" (
    python "tools\portable_cli.py" logs
) else (
    echo [خطأ] لم يتم العثور على أداة التحكم المحمولة tools/portable_cli.py
    pause
)
