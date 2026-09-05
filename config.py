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

# مسارات النمط المحمول والتوزيع المستقل (Portable Offline Deployment Layout)
PORTABLE_MODE = os.environ.get('PORTABLE_MODE', '0') == '1'
PORTABLE_ROOT = Path(os.environ.get('PORTABLE_ROOT', BASE_DIR)).resolve()

# مجلد بيانات التطبيق المحلي (أوفلاين)
_RAW_APPDATA = os.environ.get('APPDATA', os.path.expanduser('~'))
LIVE_DEFAULT_SQLITE_PATH = (Path(_RAW_APPDATA) / 'ArabicPlagiarismDetector' / 'papers.db').resolve()

if PORTABLE_MODE:
    APPDATA_DIR = PORTABLE_ROOT
    DATABASE_DIR = Path(os.environ.get('DATABASE_DIR', PORTABLE_ROOT / 'Database'))
    CONFIG_DIR = Path(os.environ.get('CONFIG_DIR', PORTABLE_ROOT / 'Config'))
    LOGS_DIR = Path(os.environ.get('LOGS_DIR', PORTABLE_ROOT / 'Logs'))
    STORAGE_ROOT = Path(os.environ.get('STORAGE_ROOT', PORTABLE_ROOT / 'Storage'))
    BACKUP_DIR = Path(os.environ.get('BACKUP_DIR', PORTABLE_ROOT / 'Backups'))
else:
    APPDATA_DIR = Path(os.environ.get('APPDATA_OVERRIDE', _RAW_APPDATA)) / 'ArabicPlagiarismDetector'
    DATABASE_DIR = APPDATA_DIR
    CONFIG_DIR = APPDATA_DIR
    LOGS_DIR = Path(os.environ.get('LOGS_DIR', APPDATA_DIR / 'logs'))
    STORAGE_ROOT = Path(os.environ.get('STORAGE_ROOT', APPDATA_DIR / 'storage'))
    BACKUP_DIR = Path(os.environ.get('BACKUP_DIR', STORAGE_ROOT / 'backups'))

# التأكد من إنشاء المجلدات المطلوبة محلياً
APPDATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)
STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# مسار التخزين وقواعد البيانات (محلي دائماً على القرص الصلب)
DEFAULT_SQLITE_PATH = (DATABASE_DIR / 'papers.db').resolve()

# تهيئة ونوع محرك قاعدة البيانات (Database Backend Selection)
DB_BACKEND = os.environ.get('DB_BACKEND', os.environ.get('DATABASE_BACKEND', 'sqlite')).strip().lower()
if DB_BACKEND not in ('sqlite', 'postgresql'):
    DB_BACKEND = 'sqlite'

# معلمات خادم PostgreSQL للشبكات الداخلية المعزولة
DB_HOST = os.environ.get('DB_HOST', '127.0.0.1')
DB_PORT = int(os.environ.get('DB_PORT', 5432))
DB_NAME = os.environ.get('DB_NAME', 'plagiarism_db')
DB_USER = os.environ.get('DB_USER', 'plagiarism_app')
DB_PASSWORD = os.environ.get('DB_PASSWORD', '')

# إعدادات مجمع الاتصالات (Connection Pool Tuning)
DB_POOL_SIZE = int(os.environ.get('DB_POOL_SIZE', 10))
DB_MAX_OVERFLOW = int(os.environ.get('DB_MAX_OVERFLOW', 20))
DB_POOL_TIMEOUT = int(os.environ.get('DB_POOL_TIMEOUT', 30))
DB_POOL_RECYCLE = int(os.environ.get('DB_POOL_RECYCLE', 1800))

# تكوين DATABASE_URL المعتمد
if DB_BACKEND == 'postgresql':
    if os.environ.get('DATABASE_URL'):
        DATABASE_URL = os.environ['DATABASE_URL']
    else:
        auth_part = f"{DB_USER}:{DB_PASSWORD}@" if DB_PASSWORD else f"{DB_USER}@"
        DATABASE_URL = f"postgresql://{auth_part}{DB_HOST}:{DB_PORT}/{DB_NAME}"
else:
    DATABASE_URL = os.environ.get('DATABASE_URL', f"sqlite:///{DEFAULT_SQLITE_PATH.as_posix()}")


def get_masked_database_url(url: str = None) -> str:
    """إخفاء كلمة المرور وبيانات الاعتماد من أي DSN لتفادي تسريبها في السجلات ونقاط الفحص."""
    target = url or DATABASE_URL
    if not target or not target.startswith('postgresql'):
        return target
    import re
    return re.sub(r':([^:@]+)@', r':***@', target)


# مجلد التخزين المؤقت والملفات المرفوعة
TEMP_UPLOAD_DIR = Path(os.environ.get('TEMP_UPLOAD_DIR', STORAGE_ROOT / 'temp_uploads'))
TEMP_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# مجلد النماذج المحلية أوفلاين
MODELS_DIR = BASE_DIR / 'models'
SEMANTIC_MODEL_PATH = Path(os.environ.get('SEMANTIC_MODEL_PATH', MODELS_DIR / 'semantic_model'))

# مفتاح الجلسة الآمن (Flask Secret Key)
_SECRET_KEY_FILE = CONFIG_DIR / '.secret_key'
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

# مسار ملف إعدادات المستخدم إن وُجد
SETTINGS_FILE = CONFIG_DIR / 'academic_settings.json'


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
    'candidate_retrieval_mode': 'dual_channel',  # نمط الاسترجاع: 'dual_channel' (RC2) أو 'baseline' (RC1)
    'common_text_filter_mode': 'span_level',    # فلترة النصوص الشائعة: 'span_level' (RC2) أو 'baseline' (RC1)
    'citation_filter_mode': 'refined',          # كاشف الاستشهاد: 'refined' (RC2) أو 'baseline' (RC1)
}

# مسار ملف إعدادات المستخدم إن وُجد
SETTINGS_FILE = APPDATA_DIR / 'academic_settings.json'

# ─── إعدادات الأمان وتدقيق المدخلات (Phase 13: Upload & Ingestion Security Limits) ───
ALLOWED_EXTENSIONS = {'.pdf', '.docx', '.txt'}
BCRYPT_ROUNDS = 12

# الحدود القصوى للأحجام والملفات
MAX_UPLOAD_BYTES = int(os.environ.get('MAX_UPLOAD_BYTES', 50 * 1024 * 1024))          # 50 MB للملف الفردي
MAX_BATCH_TOTAL_BYTES = int(os.environ.get('MAX_BATCH_TOTAL_BYTES', 150 * 1024 * 1024)) # 150 MB لإجمالي الدفعة
MAX_THESIS_TOTAL_BYTES = int(os.environ.get('MAX_THESIS_TOTAL_BYTES', 100 * 1024 * 1024)) # 100 MB لإجمالي الرسالة
MAX_REFERENCE_UPLOAD_BYTES = int(os.environ.get('MAX_REFERENCE_UPLOAD_BYTES', 50 * 1024 * 1024)) # 50 MB لملف المرجع

MAX_FILES_PER_BATCH = int(os.environ.get('MAX_FILES_PER_BATCH', 30))
MAX_FILES_PER_THESIS = int(os.environ.get('MAX_FILES_PER_THESIS', 20))

MAX_PDF_PAGES = int(os.environ.get('MAX_PDF_PAGES', 1000))
MAX_DOCX_ENTRIES = int(os.environ.get('MAX_DOCX_ENTRIES', 1000))
MAX_DOCX_UNCOMPRESSED_BYTES = int(os.environ.get('MAX_DOCX_UNCOMPRESSED_BYTES', 100 * 1024 * 1024)) # 100 MB
MAX_DOCX_COMPRESSION_RATIO = float(os.environ.get('MAX_DOCX_COMPRESSION_RATIO', 50.0))
MAX_DOCX_SINGLE_ENTRY_BYTES = int(os.environ.get('MAX_DOCX_SINGLE_ENTRY_BYTES', 30 * 1024 * 1024)) # 30 MB
MAX_TXT_BYTES = int(os.environ.get('MAX_TXT_BYTES', 20 * 1024 * 1024)) # 20 MB

MAX_CONTENT_LENGTH = MAX_BATCH_TOTAL_BYTES  # سقف طلب Flask الإجمالي (150 MB)

# الحد الأقصى لعمليات الفحص والمهام المتزامنة لحماية موارد الخادم (Phase 17 Concurrency Bounds)
MAX_CONCURRENT_SCANS = int(os.environ.get('MAX_CONCURRENT_SCANS', 2))
MAX_CONCURRENT_OCR_JOBS = int(os.environ.get('MAX_CONCURRENT_OCR_JOBS', 1))
MAX_CONCURRENT_INDEX_BUILDS = int(os.environ.get('MAX_CONCURRENT_INDEX_BUILDS', 1))
MAX_CONCURRENT_BACKUPS = int(os.environ.get('MAX_CONCURRENT_BACKUPS', 1))
OCR_LOCK_TIMEOUT_SECONDS = int(os.environ.get('OCR_LOCK_TIMEOUT_SECONDS', 60))
OCR_LOCK_FILE = os.environ.get('OCR_LOCK_FILE', '')

# سقف طابور المهام وضغط العمل الخلفي (Backpressure & Queue Limits)
MAX_QUEUED_JOBS = int(os.environ.get('MAX_QUEUED_JOBS', 1000))
MAX_QUEUED_SCAN_ITEMS = int(os.environ.get('MAX_QUEUED_SCAN_ITEMS', 500))
JOB_HEARTBEAT_INTERVAL_SECONDS = int(os.environ.get('JOB_HEARTBEAT_INTERVAL_SECONDS', 10))
JOB_STUCK_HEARTBEAT_MINUTES = int(os.environ.get('JOB_STUCK_HEARTBEAT_MINUTES', 5))
JOB_RETENTION_DAYS = int(os.environ.get('JOB_RETENTION_DAYS', 30))

# البادئة الرسمية للرقم المرجعي للأبحاث الأكاديمية
RESEARCH_REFERENCE_PREFIX = os.environ.get('RESEARCH_REFERENCE_PREFIX', 'RES')

# ─── عتبات المراقبة والجاهزية التشغيلية (Phase 11: Operational Health Thresholds) ───
DISK_WARNING_PERCENT = int(os.environ.get('DISK_WARNING_PERCENT', 15))      # تنبيه عند انخفاض المساحة المتاحة عن 15%
DISK_CRITICAL_PERCENT = int(os.environ.get('DISK_CRITICAL_PERCENT', 5))     # حالة حرجة عند انخفاض المساحة المتاحة عن 5%
STUCK_JOB_MINUTES = int(os.environ.get('STUCK_JOB_MINUTES', 30))           # اعتبار المهمة عالقة بعد 30 دقيقة من المعالجة
BACKUP_MAX_AGE_HOURS = int(os.environ.get('BACKUP_MAX_AGE_HOURS', 48))      # اعتبار النسخ متأخرة إذا تجاوز عمر آخر نسخة 48 ساعة
HEALTH_AUTO_REFRESH_SECONDS = int(os.environ.get('HEALTH_AUTO_REFRESH_SECONDS', 30))  # الفاصل الزمني لتحديث لوحة الصحة
AUDIT_ALERT_SUPPRESSION_SECONDS = int(os.environ.get('AUDIT_ALERT_SUPPRESSION_SECONDS', 300))  # كتم تكرار التنبيهات في سجل التدقيق

# ─── إعدادات المصادقة وأمان الجلسات (Phase 14: Authentication & Session Hardening) ───
AUTH_PASSWORD_MIN_LENGTH = int(os.environ.get('AUTH_PASSWORD_MIN_LENGTH', 12))  # الحد الأدنى لطول كلمة المرور
AUTH_SESSION_IDLE_TIMEOUT_MINUTES = int(os.environ.get('AUTH_SESSION_IDLE_TIMEOUT_MINUTES', 30))  # مهلة الخمول للجلسة
AUTH_SESSION_MAX_LIFETIME_HOURS = int(os.environ.get('AUTH_SESSION_MAX_LIFETIME_HOURS', 8))  # السقف الزمني المطلق للجلسة
AUTH_MAX_LOGIN_ATTEMPTS = int(os.environ.get('AUTH_MAX_LOGIN_ATTEMPTS', 5))  # محاولات الدخول الخاطئة للحساب قبل القفل المؤقت
AUTH_MAX_IP_ATTEMPTS = int(os.environ.get('AUTH_MAX_IP_ATTEMPTS', 20))  # محاولات الدخول الخاطئة للـ IP قبل الكبح
AUTH_LOCKOUT_DURATION_MINUTES = int(os.environ.get('AUTH_LOCKOUT_DURATION_MINUTES', 15))  # مدة القفل الأولي بالدقائق
AUTH_EXTENDED_LOCKOUT_DURATION_MINUTES = int(os.environ.get('AUTH_EXTENDED_LOCKOUT_DURATION_MINUTES', 60))  # مدة القفل عند التكرار
AUTH_COOKIE_HTTPONLY = True
AUTH_COOKIE_SAMESITE = os.environ.get('AUTH_COOKIE_SAMESITE', 'Lax')
AUTH_COOKIE_SECURE = os.environ.get('AUTH_COOKIE_SECURE', 'false').lower() in ('true', '1', 'yes')
AUTH_CSRF_ENABLED = os.environ.get('AUTH_CSRF_ENABLED', 'true').lower() in ('true', '1', 'yes')
APP_ENV = os.environ.get('APP_ENV', 'development')



