# -*- coding: utf-8 -*-
"""
وحدة تشغيل خادم الإنتاج المعتمد (Centralized Production WSGI Server - Waitress):
- توفر نقطة انطلاق مركزية ومحصنة لتشغيل خادم Waitress الإنتاجي عبر كافة أنماط التشغيل.
- تمنع تماماً أي تراجع صامت إلى خادم Flask التطويري (app.run) في بيئة الإنتاج أو الحزمة التنفيذية الموحدة (Single EXE).
- تضمن سياسة الإغلاق الحازم (Fail-Closed Architecture) عند تعذر استدعاء Waitress:
  عرض رسالة 'PRODUCTION WSGI SERVER NOT AVAILABLE' والخروج الفوري برمز خطأ غير صفري (Exit Code 1).
"""

import os
import sys
import logging
from pathlib import Path
from typing import Optional, Any
from flask import Flask

import config

logger = logging.getLogger("waitress")


def print_fail_closed_error(error_msg: str, log_file: Optional[Path] = None) -> None:
    """طباعة رسالة الخطأ الحرج المعتمدة عند تعذر تشغيل خادم الإنتاج Waitress."""
    banner = "=" * 70
    formatted_msg = (
        f"{banner}\n"
        f"PRODUCTION WSGI SERVER NOT AVAILABLE\n"
        f"{banner}\n"
        f"Failed to start production WSGI server (Waitress): {error_msg}\n"
        f"Check:\n"
        f"  Logs/server.log\n"
        f"{banner}\n"
    )
    print(formatted_msg, file=sys.stderr)
    if log_file:
        try:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n[CRITICAL] PRODUCTION WSGI SERVER NOT AVAILABLE: {error_msg}\n")
        except Exception:
            pass


def start_production_server(
    app: Flask,
    host: str = "127.0.0.1",
    port: int = 5000,
    threads: int = 8,
    channel_timeout: int = 120,
    cleanup_interval: int = 30,
    log_file: Optional[Path] = None
) -> Any:
    """
    إنشاء وتهيئة كائن خادم الإنتاج Waitress بشكل إلزامي.
    يعيد كائن Server جاهز للتشغيل.
    """
    try:
        import waitress
        from waitress.server import create_server
    except (ImportError, Exception) as e:
        print_fail_closed_error(str(e), log_file=log_file)
        sys.exit(1)

    try:
        server = create_server(
            app,
            host=host,
            port=port,
            threads=threads,
            channel_timeout=channel_timeout,
            cleanup_interval=cleanup_interval
        )
        return server
    except Exception as e:
        print_fail_closed_error(f"Cannot bind/listen on {host}:{port} - {e}", log_file=log_file)
        sys.exit(1)


def run_production_server(
    app: Flask,
    host: str = "127.0.0.1",
    port: int = 5000,
    threads: int = 8,
    channel_timeout: int = 120,
    cleanup_interval: int = 30,
    log_file: Optional[Path] = None
) -> None:
    """
    تشغيل خادم الإنتاج Waitress بشكل حاجب ومباشر (Blocking WSGI Serve).
    """
    server = start_production_server(
        app=app,
        host=host,
        port=port,
        threads=threads,
        channel_timeout=channel_timeout,
        cleanup_interval=cleanup_interval,
        log_file=log_file
    )

    try:
        import waitress
        w_ver = getattr(waitress, '__version__', '3.0.2')
    except Exception:
        w_ver = '3.0.2'

    start_banner = f"Starting production Waitress (v{w_ver}) on http://{host}:{port}..."
    serve_msg = f"waitress: Serving on http://{host}:{port}"

    logger.info(start_banner)
    logger.info(serve_msg)
    print(f"[✓] {start_banner}")
    print(f"[✓] {serve_msg}")

    if log_file:
        try:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n{start_banner}\n{serve_msg}\n")
        except Exception:
            pass

    server.run()
