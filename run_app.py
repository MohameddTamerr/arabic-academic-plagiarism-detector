# -*- coding: utf-8 -*-
"""
مشغل التطبيق المحمول:
يبدأ خادم Web المحلي ويفتح المتصفح تلقائيًا على الواجهة الجديدة.
"""

import sys
import os
import webbrowser
import threading
import time

# ── إضافة المسار ─────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_VENDOR = os.path.join(_HERE, 'vendor')
for _p in [_HERE, _VENDOR]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from server import app

def open_browser():
    """فتح المتصفح بعد ثانية واحدة من تشغيل الخادم."""
    time.sleep(1.2)
    webbrowser.open('http://localhost:5000')

if __name__ == '__main__':
    print("=" * 60)
    print("   نظام كشف الاستلال العلمي والاستشهادات")
    print("   جاري فتح الواجهة الرسومية على المتصفح...")
    print("   http://localhost:5000")
    print("=" * 60)

    # تشغيل فتح المتصفح في الخلفية
    threading.Thread(target=open_browser, daemon=True).start()

    # بدء خادم Waitress الإنتاجي (100% Offline)
    import config
    is_prod = getattr(config, 'PRODUCTION_MODE', False) or getattr(config, 'PORTABLE_MODE', False) or getattr(config, 'SINGLE_EXE_MODE', False) or os.environ.get('PORTABLE_MODE') == '1' or os.path.basename(_HERE).lower() == 'app'
    log_file = config.LOGS_DIR / "server.log"

    if is_prod:
        from app.wsgi_server import run_production_server
        run_production_server(app, host='0.0.0.0', port=5000, threads=16, log_file=log_file)
    else:
        is_explicit_dev = os.environ.get('FLASK_ENV') == 'development' or os.environ.get('APP_ENV') == 'development' or '--dev' in sys.argv
        if is_explicit_dev:
            print("   تشغيل خادم Flask المحلي (نمط التطوير الصريح)...")
            app.run(host='0.0.0.0', port=5000, threaded=True, debug=False)
        else:
            from app.wsgi_server import run_production_server
            run_production_server(app, host='0.0.0.0', port=5000, threads=16, log_file=log_file)


