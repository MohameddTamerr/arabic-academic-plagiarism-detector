# -*- coding: utf-8 -*-
"""
نقطة الدخول الرئيسية للتطبيق:
- تشغيل التطبيق محلياً: python main.py أو python run_app.py
- تشغيل من خلال Uvicorn/WSGI: uvicorn server:app أو python main.py
"""
import sys
import os

# ── إضافة مسار المشروع والـ vendor ──────────────────────────────────────────
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

# تصدير متغير app لتتمكن خوادم مثل Uvicorn / Gunicorn / Flask من قراءته مباشرة (main:app)
from server import app

if __name__ == '__main__':
    import webbrowser
    import threading
    import time

    def open_browser():
        time.sleep(1.2)
        webbrowser.open('http://localhost:5000')

    print("=" * 60)
    print("   تشغيل نظام كشف الاستلال العلمي والاستشهادات")
    print("   http://localhost:5000")
    print("=" * 60)

    threading.Thread(target=open_browser, daemon=True).start()
    app.run(host='127.0.0.1', port=5000, debug=False)

