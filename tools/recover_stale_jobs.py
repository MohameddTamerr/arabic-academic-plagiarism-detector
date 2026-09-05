# -*- coding: utf-8 -*-
"""
أداة استعادة المهام المنقطعة وتدقيق عقود الإيجار (Stale Jobs & Expired Lease Recovery CLI):
- فحص المهام العالقة التي انتهى عقد إيجارها دون اكتمال المعالجة.
- إعادة المحاولات القابلة للتعافي أو تحويلها إلى فاشلة بعد استنفاد المحاولات.
"""

import os
import sys
import argparse
import logging
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.queue.db_queue import DatabaseJobQueue

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s] %(message)s')
logger = logging.getLogger("recover_stale_jobs")


def main():
    parser = argparse.ArgumentParser(description="أداة استعادة المهام المنقطعة وتدقيق عقود الإيجار")
    parser.add_argument("--timeout", type=int, default=60, help="مهلة انتهاء عقد الإيجار بالثواني")
    args = parser.parse_args()

    queue = DatabaseJobQueue()
    logger.info("بدء فحص واستعادة المهام المنقطعة...")
    recovered = queue.recover_stale_jobs(timeout_seconds=args.timeout)
    logger.info(f"اكتمل الفحص. إجمالي المهام المستعادة: {recovered}")


if __name__ == '__main__':
    main()
