# -*- coding: utf-8 -*-
"""
أداة بناء الحزمة التنفيذية الموحدة لنظام فحص الاستلال الأكاديمي (Arabic-Plagiarism-System.exe):
- تضمن استخدام خادم الإنتاج الإلزامي Waitress وكافة المكتبات والأصول المعتمدة.
"""
import sys
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from tools.build_single_exe import build_single_exe

if __name__ == '__main__':
    build_single_exe()

