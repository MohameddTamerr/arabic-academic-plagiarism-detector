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

    try:
        from waitress import serve
        logger.info(f"بدء تشغيل خادم الإنتاج Waitress على المنفذ {config.PORT}...")
        serve(app, host=config.HOST, port=config.PORT, threads=8)
    except Exception as e:
        logger.warning(f"تعذر تشغيل Waitress ({e})، جاري استخدام خادم Flask الافتراضي...")
        app.run(host=config.HOST, port=config.PORT, threaded=True, debug=config.DEBUG)
