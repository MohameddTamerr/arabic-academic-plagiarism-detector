# -*- coding: utf-8 -*-
"""
إعدادات المنظومة الأكاديمية (Academic Integrity Configuration)
تدعم القراءة من متغيرات البيئة مع قيم افتراضية آمنة للتشغيل المحلي أوفلاين بالكامل.
مُهيئة للتحول المستقبلي إلى خادم مركزي وشبكة داخلية (LAN) دون تعديل الكود.
"""

import os
import secrets
from pathlib import Path

# المسارات الأساسية للنظام
BASE_DIR = Path(__file__).resolve().parent

# مجلد بيانات التطبيق المحلي (أوفلاين)
APPDATA_DIR = Path(os.environ.get('APPDATA', os.path.expanduser('~'))) / 'ArabicPlagiarismDetector'
APPDATA_DIR.mkdir(parents=True, exist_ok=True)

# مسار التخزين وقواعد البيانات
DEFAULT_SQLITE_PATH = APPDATA_DIR / 'papers.db'
DATABASE_URL = os.environ.get('DATABASE_URL', f"sqlite:///{DEFAULT_SQLITE_PATH.as_posix()}")

# مجلد التخزين المؤقت والملفات المرفوعة
STORAGE_ROOT = Path(os.environ.get('STORAGE_ROOT', APPDATA_DIR / 'storage'))
STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
TEMP_UPLOAD_DIR = STORAGE_ROOT / 'temp_uploads'
TEMP_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR = STORAGE_ROOT / 'backups'
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# مجلد النماذج المحلية أوفلاين
MODELS_DIR = BASE_DIR / 'models'
SEMANTIC_MODEL_PATH = Path(os.environ.get('SEMANTIC_MODEL_PATH', MODELS_DIR / 'semantic_model'))

# مفتاح الجلسة الآمن (Flask Secret Key)
_SECRET_KEY_FILE = APPDATA_DIR / '.secret_key'
if os.environ.get('SECRET_KEY'):
    SECRET_KEY = os.environ['SECRET_KEY']
else:
    if not _SECRET_KEY_FILE.exists():
        with open(_SECRET_KEY_FILE, 'w', encoding='utf-8') as f:
            f.write(secrets.token_hex(32))
    try:
        with open(_SECRET_KEY_FILE, 'r', encoding='utf-8') as f:
            SECRET_KEY = f.read().strip()
    except Exception:
        SECRET_KEY = secrets.token_hex(32)

# إعدادات تشغيل الخادم
HOST = os.environ.get('HOST', '127.0.0.1')
PORT = int(os.environ.get('PORT', 5000))
DEBUG = os.environ.get('FLASK_DEBUG', '0') == '1'

# الحدود الأكاديمية الافتراضية القابلة للتخصيص
DEFAULT_SETTINGS = {
    'shingle_size': 5,                     # حجم متوالية الكلمات لكشف النسخ الحرفي
    'jaccard_threshold': 0.40,             # عتبة النسخ الحرفي (Jaccard >= 40%)
    'tfidf_threshold': 0.40,               # عتبة إعادة الصياغة اللفظية (Cosine >= 40%)
    'semantic_threshold': 0.70,            # عتبة التشابه الدلالي (Semantic >= 70%)
    'min_sentence_words': 4,               # الحد الأدنى لكلمات الجملة المعتبرة
    'allowed_similarity_pct': 20.0,        # النسبة الكلية المسموح بها للاستلال
    'words_per_page': 250,                 # معدل الكلمات التقديري لكل صفحة
    'max_allowed_pages_per_source': 5.0,   # الحد الأقصى للصفحات المقتبسة من مرجع واحد
    'enable_semantic_model': False,        # النموذج الدلالي (معطل افتراضياً لسرعة المعالج)
    'enable_ocr': True,                    # تفعيل OCR المشروط عند توفر Tesseract
    'detection_profile': 'LIGHT',          # أنماط الكشف: LIGHT, BALANCED, ADVANCED
    'max_candidate_retrieval': 50,         # أقصى عدد مرشحين للفقرة الواحدة لتفادي البطء
}

# مسار ملف إعدادات المستخدم إن وُجد
SETTINGS_FILE = APPDATA_DIR / 'academic_settings.json'

# إعدادات الأمان
MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 500 MB max upload
ALLOWED_EXTENSIONS = {'.pdf', '.docx', '.doc', '.txt'}
BCRYPT_ROUNDS = 12

# الحد الأقصى لعمليات الفحص المتزامنة في الدفعة الواحدة
# قيمة منخفضة لحماية الأجهزة المتواضعة من الإجهاد
MAX_CONCURRENT_SCANS = int(os.environ.get('MAX_CONCURRENT_SCANS', 2))
