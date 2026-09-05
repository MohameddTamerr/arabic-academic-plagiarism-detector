@echo off
setlocal EnableExtensions
title Arabic Academic Plagiarism Detector - Stop System

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

set "PYTHON="
if exist "%ROOT%\Runtime\python.exe" (
    set "PYTHON=%ROOT%\Runtime\python.exe"
) else (
    where python >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON=python"
    )
)

if "%PYTHON%"=="" (
    echo ======================================================================
    echo RUNTIME NOT FOUND
    echo ======================================================================
    echo Python executable was not found in:
    echo   %ROOT%\Runtime\python.exe
    echo nor in the system PATH.
    echo ======================================================================
    pause
    exit /b 1
)

set "CLI="
if exist "%ROOT%\Tools\portable_cli.py" (
    set "CLI=%ROOT%\Tools\portable_cli.py"
) else if exist "%ROOT%\tools\portable_cli.py" (
    set "CLI=%ROOT%\tools\portable_cli.py"
)

if "%CLI%"=="" (
    echo ======================================================================
    echo PORTABLE CLI NOT FOUND
    echo ======================================================================
    echo Could not locate portable_cli.py in:
    echo   %ROOT%\Tools\portable_cli.py
    echo ======================================================================
    pause
    exit /b 1
)

cd /d "%ROOT%"
"%PYTHON%" "%CLI%" stop

pause
