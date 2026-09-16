# -*- coding: utf-8 -*-
"""
خادم المنظومة الأكاديمية لكشف الاستلال والأمانة العلمية (Offline WSGI Server):
- يعمل أوفلاين بالكامل 100% دون أي اعتماد على شبكة الإنترنت.
- يعتمد على معمارية الطبقات النظيفة (Clean Layered Architecture) عبر حزمة app.
- مدعوم بخادم الإنتاج المحلي Waitress لتوفير أداء قوي وثابت على أجهزة ويندوز العادية.
- مهيأ لخدمة أجهزة متعددة على الشبكة المحلية (LAN) عند ضبط HOST=0.0.0.0.
"""

import sys
import io
import os
import logging
from pathlib import Path

# إعداد الترميز لطباعة الحروف العربية السليمة في شاشة الـ Terminal
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

import os
from pathlib import Path

# إضافة مسارات vendor المحمولة تلقائياً إلى مسار البحث sys.path
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent if _HERE.name.lower() == "app" else _HERE
for _v in [_HERE / "vendor", _ROOT / "vendor"]:
    if _v.exists() and str(_v) not in sys.path:
        sys.path.insert(0, str(_v))

import config
from app import create_app

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger('academic_detector')

app = create_app()

if __name__ == '__main__':
    print("=" * 70)
    print("   منظومة كشف الاستلال العلمي والأمانة الأكاديمية (100% Offline System)")
    print(f"   الخادم يعمل محلياً على: http://{config.HOST}:{config.PORT}")
    print("=" * 70)

    is_prod = getattr(config, 'PRODUCTION_MODE', False) or getattr(config, 'PORTABLE_MODE', False) or getattr(config, 'SINGLE_EXE_MODE', False) or os.environ.get('PORTABLE_MODE') == '1' or (_HERE.name.lower() == 'app')
    log_file = config.LOGS_DIR / "server.log"

    if is_prod:
        from app.wsgi_server import run_production_server
        run_production_server(app, host=config.HOST, port=config.PORT, threads=8, log_file=log_file)
    else:
        # Development / Source repository mode
        is_explicit_dev = os.environ.get('FLASK_ENV') == 'development' or os.environ.get('APP_ENV') == 'development' or '--dev' in sys.argv
        if is_explicit_dev:
            logger.info(f"بدء تشغيل خادم Flask المحلي (نمط التطوير الصريح) على المنفذ {config.PORT}...")
            app.run(host=config.HOST, port=config.PORT, threaded=True, debug=config.DEBUG)
        else:
            from app.wsgi_server import run_production_server
            run_production_server(app, host=config.HOST, port=config.PORT, threads=8, log_file=log_file)

