# وثيقة خط الأساس للإصدار النهائي المعتمد (Release Baseline)
## Arabic Academic Plagiarism Detector — Release Candidate v1.0.0-rc

تُحدد هذه الوثيقة خط الأساس الفني والبيئي الثابت لنسخة الإصدار النهائي المعتمد (Release Candidate) لمنظومة كشف الاستلال العلمي والأمانة الأكاديمية.

---

### 1. بيانات المستودع والشفرة المصدرية (Source Provenance)
- **فرع الإصدار (Git Branch):** `release/v1-final-rc`
- **معرف الالتزام الأساسي (Git HEAD Commit):** `fbfd6538b8137ba936fe26b528b1bb711e74bebb`
- **حالة تجميد المصدر (Source Freeze Status):** `FROZEN (مجمّد بالكامل)`
- **تاريخ التجميد والاعتماد:** 2026-09-17

---

### 2. بيئة البناء والتطوير المعتمدة (Build Environment)
- **نظام التشغيل المستخدم في البناء:** Windows 11 Enterprise x64 (Build 10.0.26100)
- **بيئة لغة بايثون:** Python 3.13.2 (64-bit AMD64)
- **أداة التجميع والحزم المستقل:** PyInstaller 6.19.0
- **خادم الإنتاج المدمج:** Waitress WSGI Server v3.0.2
- **محرك قاعدة البيانات:** SQLite 3 (WAL Mode - Journal Mode WAL + Synchronous NORMAL)
- **محرك التعرف الضوئي (OCR):** Tesseract Engine 5.x مع حزم بيانات `ara.traineddata` و `eng.traineddata`
- **محرك الأمان المحلي (Antivirus):** Windows Defender CLI (`MpCmdRun.exe`) / ClamAV (`clamscan`)

---

### 3. المسارات المرجعية الرسمية للبيانات (Authoritative Storage & Database Root)
- **المجلد الجذري الرسمي لبيانات المنظومة:**
  `%LOCALAPPDATA%\ArabicAcademicPlagiarismSystem\Data`
- **مسار قاعدة البيانات الرسمية المعتمدة:**
  `%LOCALAPPDATA%\ArabicAcademicPlagiarismSystem\Data\Database\papers.db`
- **مجلد تخزين المحتوى والملفات المعتمدة (CAS Content-Addressable Storage):**
  `%LOCALAPPDATA%\ArabicAcademicPlagiarismSystem\Data\Storage`
- **مجلد النسخ الاحتياطية:**
  `%LOCALAPPDATA%\ArabicAcademicPlagiarismSystem\Data\Backups`
- **مجلد السجلات ومسارات التدقيق (Audit Logs):**
  `%LOCALAPPDATA%\ArabicAcademicPlagiarismSystem\Data\Logs`

---

### 4. حزمة الإصدار الموحدة الرسمية (Modern Windows Release Binary)
- **اسم الحزمة التنفيذية:** `Arabic-Plagiarism-System.exe`
- **المسار في حزمة الإصدار:** `FINAL_RELEASE/windows-modern/Arabic-Plagiarism-System.exe`
- **الحجم الدقيق بالبايت:** `292,123,420 bytes` (278.59 MB)
- **بصمة التجزئة SHA-256:**
  `8d000483de7c4104ece76143834caeb22853764343a502e524f26793ea8cb3bc`
- **نوع المعمارية الثنائية (PE Architecture):** `PE32+ (x64 / AMD64)`
- **النظام الفرعي (PE Subsystem):** `2 (IMAGE_SUBSYSTEM_WINDOWS_GUI)` — واجهة مستخدم رسومية بدون أي نافذة سطر أوامر سوداء.

---

### 5. ثوابت الأمان والحسابات الإدارية المعتمدة (Security Invariants)
- **حساب مدير النظام الرئيسي (SYSTEM_ADMIN):** `Tamer Darwish` (ID: 1, Active: 1)
- **حالة التثبيت الأولي (Bootstrap State):** مغلق نهائياً (`is_initial_admin_allowed() == False`)
- **عزل الصلاحيات (RBAC):** صارم 100% (موظف الفحص `EMPLOYEE` محظور نهائياً من أي قرارات اعتماد أو رفض أو إدارة مستخدمين بكود رد 403 Forbidden).
- **سياسة فحص الفيروسات:** Fail-Closed (حظر الملفات غير المفحوصة والمشبوهة تلقائياً).
