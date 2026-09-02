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
    try:
        from waitress import serve
        serve(app, host='0.0.0.0', port=5000, threads=16)
    except Exception as e:
        print(f"   تشغيل خادم Flask المحلي: {e}")
        app.run(host='0.0.0.0', port=5000, threaded=True, debug=False)

