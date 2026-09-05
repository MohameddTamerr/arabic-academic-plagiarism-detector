# دليل التثبيت والنشر المؤسسي (Institutional Deployment Runbook)
## Arabic Academic Plagiarism Detector — Release v1.0.0-rc1

---

### 1. المتطلبات الأساسية للبيئة (Prerequisites)

- **نظام التشغيل:** Windows 10 / 11 / Windows Server 2019+ (64-bit).
- **بيئة التشغيل البرمجية:** Python 3.11 إلى 3.13 (مع تفعيل إضافة المسار إلى المتغيرات البيئية `PATH`).
- **محرك OCR المحلي (اختياري):** Tesseract OCR (الإصدار 5.x) مع حزمة اللغة العربية `ara.traineddata` مثبتة في مجلد `tessdata`.
- **الشبكة:** شبكة محلية معزولة (LAN / Air-Gapped) دون حاجة للاتصال بالإنترنت.

---

### 2. هيكل المجلدات والمسارات على الخادم (Directory Layout)

تقوم المنظومة تلقائياً بتهيئة مسارات التخزين والبيانات في مسار التطبيق المحلي للمستخدم (`APPDATA`):

```text
%APPDATA%\ArabicPlagiarismDetector\
├── papers.db                 # قاعدة بيانات SQLite المحصنة (WAL Mode)
├── .secret_key               # مفتاح الجلسات المشفر (32-bytes hex)
├── academic_settings.json    # إعدادات الفحص المخصصة إن وجدت
├── storage\
│   ├── research\             # الأبحاث والرسائل المرفوعة للفحص
│   ├── references\           # المراجع وأوراق المقارنة المعتمدة
│   └── temp\                 # مجلدات المعالجة المؤقتة واستخراج النصوص
└── backups\
    ├── catalog.json          # سجل النسخ الاحتياطية الموثقة
    └── *.zip                 # ملفات النسخ الاحتياطية المشفرة والمفهرسة
```

---

### 3. خطوات التثبيت خطوة بخطوة (Clean-Slate Installation Steps)

#### الخطوة 1: استخراج حزمة البرنامج وتثبيت الاعتماديات
من داخل موجه الأوامر (PowerShell / Command Prompt) في بيئة معزولة:
```powershell
cd C:\PlagiarismDetector
pip install -r requirements.txt --no-index --find-links=./wheels
```

#### الخطوة 2: تهيئة المشرف الأول (First-Admin Bootstrap)
تشغيل أمر التهيئة لإنشاء حساب المشرف الرئيسي عند أول تشغيل للمنظومة:
```powershell
python -m app.cli create-admin --username admin --email admin@institution.edu.sa --password "StrongAdminPassword123!"
```

#### الخطوة 3: التحقق من جاهزية قاعدة البيانات والصحة التشغيلية
```powershell
python -c "from app.services.db_health_service import run_quick_db_check; print(run_quick_db_check())"
```

#### الخطوة 4: تشغيل الخدمة على الشبكة المؤسسية (LAN Binding)
لتشغيل الخادم وربطه على عنوان IP الشبكة المحلية للمؤسسة:
```powershell
$env:HOST = "192.168.1.100"
$env:PORT = "5000"
python app.py
```

---

### 4. قواعد جدار الحماية والأمان للشبكة (Firewall & LAN Policy)

- **المنفذ الافتراضي:** `5000` (TCP).
- **نطاق الوصول:** أجهزة لجان التحكيم والباحثين داخل الشبكة الداخلية (Institutional Subnet) حصراً.
- **حظر الوصول الخارجي:** يُمنع فتح المنفذ عبر موجهات الإنترنت (No Port Forwarding / No Public IP).
- **التشفير الداخلي (TLS):** يوصى باستخدام خادم وسيط عكسي (Reverse Proxy مثل Nginx/IIS) مع شهادة SSL داخلية عند تشغيل المنظومة عبر شبكة جامعية واسعة.
