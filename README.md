# نظام كشف التشابه والاستلال الأكاديمي العربي
# Arabic Academic Plagiarism Detector

---

## 🇸🇦 القسم العربي (Arabic Section)

منظومة برمجية محلية (Offline) متخصصة في تحليل ومطابقة النصوص الأكاديمية العربية، صُممت لمساعدة لجان التحكيم والمراجعين في الجامعات والمؤسسات البحثية على فحص الأبحاث والرسائل العلمية ومقارنتها بقاعدة المصادر والمراجع المحلية.

> **تنبيه أكاديمي**: المنظومة هي أداة مساعدة لتقديم مؤشرات وأدلة رقمية دقيقة، ولا تصدر أحكاماً قطعية أو قرارات نهائية بشأن الانتحال؛ حيث تظل المراجعة والاعتماد البشري إلزاميين لكافة التقارير.

---

### نظرة عامة
تعتمد المؤسسات الأكاديمية على فحص نزاهة الأبحاث المقدمة إليها لضمان الأمانة العلمية. تم بناء هذه المنظومة لتعمل محلياً بالكامل (On-Premise / Air-Gapped) دون الحاجة للاتصال بالإنترنت أو الاعتماد على خدمات سحابية خارجية، مما يحافظ على الخصوصية والسرية المطلقة للأبحاث والبيانات المؤسسية، مع دعم كامل للشبكة الداخلية (LAN) لتسهيل وصول المحكمين عبر المتصفح.

---

### أهم المميزات
- **معالجة متخصصة للغة العربية**: تطبيع دقيق للأحرف العربية، وتجريد التشكيل، وتوحيد الهمزات والألف المقصورة والتاء المربوطة.
- **محرك فحص هجين**: مطابقة حرفية وتجاورية متطورة (Shingles & Jaccard) مع تحليل معجمي إحصائي (TF-IDF Vectorization).
- **استبعاد ذكي للاستشهادات والمراجع**: تمييز الاقتباسات الموثقة بين علامات التنصيص، وتحديد قائمة المراجع النهائية وتجاوزها بدقة.
- **تصفية العبارات الشائعة**: عزل المصطلحات والعبارات المتكررة في الأبحاث لتفادي نسب التشابه الخاطئة.
- **مستودع مستندات مشفر المحتوى (CAS)**: تخزين مجزأ وفعال للملفات بالاعتماد على بصمة المحتوى الرقمية (SHA-256).
- **مسار مراجعة وتحكيم مؤسسي**: إمكانية إضافة ملاحظات المحكم، وتسجيل القرارات، ومتابعة تاريخ الإصدارات والمراجعات لكل بحث.
- **تحكم في الصلاحيات (RBAC)**: أدوار محددة للمستخدمين (مسؤول نظام، رئيس وحدة، مراجع معتمد، محكّم).
- **سجل تدقيق أمني غير قابل للتعديل (Audit Trail)**: توثيق كافة العمليات، والتعديلات، وتنزيل التقارير لضمان النزاهة.
- **تشغيل محمول بدون تثبيت (Portable Deployment)**: العمل المباشر عبر قاعدة بيانات SQLite بنمط WAL دون متطلبات تثبيت خوادم معقدة.
- **حماية تامة للخصوصية**: 100% بدون اتصال خارجي، بدون تتبع، وتشفير كامل لكلمات المرور بـ Bcrypt.

---

### كيف يعمل النظام؟

```text
    رفع البحث (PDF / Word)
               ↓
    استخراج النص وتفكيك الصفحات
               ↓
     تطبيع ومعالجة النص العربي
               ↓
  استرجاع أفضل المصادر المرشحة (Dual-Channel)
               ↓
   المطابقة التفصيلية ومقارنة المقاطع
               ↓
      تحليل الاقتباسات وقائمة المراجع
               ↓
    إنشاء تقرير الفحص التفاعلي والبصمة
               ↓
     المراجعة والاعتماد البشري النهائي
```

---

### طريقة التشغيل السريع (الحزمة المحمولة)

تم تجهيز المنظومة بمشغلات دفعية تعمل بنقرة واحدة على نظام Windows دون الحاجة لمعرفة بأوامر السطر:

1. **التهيئة لأول مرة**: انقر نقراً مزدوجاً على `Setup-System.bat` لتهيئة المجلدات وقاعدة البيانات.
2. **بدء التشغيل**: انقر على `Start-System.bat`؛ ستظهر شاشة الجاهزية ويفتح المتصفح تلقائياً على عنوان المنظومة.
3. **الوصول من أجهزة الشبكة المحلية (LAN)**: يمكن لأي جهاز مراجع مصرح له فتح الرابط الموضح في نافذة التشغيل (مثل `http://192.168.1.100:5000`).
4. **الإيقاف الآمن**: استخدم `Stop-System.bat` لإغلاق الخادم وتفريغ السجلات (WAL Checkpoint) بأمان.
5. **النسخ الاحتياطي**: استخدم `Backup-System.bat` لإنشاء نسخة احتياطية فورية ومشفرة من البيانات والمستندات.
6. **الفحص التشخيصي**: استخدم `Check-System.bat` للتحقق من سلامة النظام وقاعدة البيانات والمساحة.

---

### معمارية النظام

```text
   أجهزة المراجعين (المتصفح)
             │
      الشبكة المحلية (LAN)
             │
   خادم التطبيق المركزي (Flask)
             │
     ┌───────┴───────┐
     │               │
  قاعدة البيانات    عمال المعالجة
 (SQLite / WAL)  (Multi-Process)
     │
 مستودع الملفات المحلي (CAS Storage)
```

> **ملاحظة أمان**: تبقى قاعدة بيانات SQLite وملفات التخزين حصرياً على القرص المحلي للحاسوب الخادم، ولا يجوز مشاركتها عبر مجلدات الشبكة (SMB/NAS)؛ حيث يتصل المستخدمون حصراً عبر خادم الويب.

---

### التقنيات المستخدمة
- **لغة البرمجة**: Python 3.11+
- **خادم الويب والواجهات**: Flask, Jinja2, Vanilla CSS & Modern JS (Glassmorphism UI)
- **قواعد البيانات**: SQLite (WAL Mode), SQLAlchemy
- **معالجة النصوص والمستندات**: PyMuPDF (fitz), regex
- **خوارزميات الفحص والتحليل**: scikit-learn (TF-IDF), NumPy, Custom Arabic Normalizer
- **الأمان والتحصين**: Bcrypt, CSRF Protection, SHA-256 Content-Addressing
- **الاختبارات وضمان الجودة**: Pytest, psutil

---

### تقارير الفحص
يوفر تقرير الفحص التفاعلي:
- نسبة التشابه الإجمالية ونسبة النسخ المتطابق وإعادة الصياغة.
- قائمة المصادر المطابقة والمصنفة حسب الأهمية.
- عرض المقاطع المتشابهة جنباً إلى جنب (Side-by-Side Comparison).
- بصمة التحقق من النزاهة الرقمية (SHA-256 Hash) لضمان عدم التلاعب بالتقرير بعد اعتماده.

---

### الوضع الحالي ومحددات الإطلاق
- **الإصدار الحالي**: `v1.4.1-sqlite-portable-rc`
- **نمط التشغيل**: حزمة محمولة جاهزة للنشر المؤسسي المعزول (Controlled Offline Deployment).
- **التعرف الضوئي على الحروف (Arabic OCR)**: معطل افتراضياً ويتطلب توفير ملف الحروف المحلية `ara.traineddata`.
- **النماذج الدلالية العميقة**: معطلة افتراضياً وتعتمد المنظومة بالكامل على المحرك الهجين المعجمي السريع.
- **إعادة الصياغة المعقدة**: تمثل قيداً علمياً معروفاً يتطلب دائماً التدقيق والمراجعة البشرية.

---

### الأداء والسعة المقاسة
أظهرت نتائج فحص الإجهاد لقاعدة بيانات SQLite على بيئة اختبار معزولة:
- الوصول إلى سعة **2,000,000 سجل بحثي اصطناعي (Synthetic Records)** بنحو **7.2 مليون سطر علائقي** وحجم قاعدة بيانات **4.7 جيجابايت**.
- زمن استعلام المفاتيح الأساسية والبحث: **0.01 – 0.07 مللي ثانية**.
- تصفح السجلات بالترقيم المفهرس (Keyset Pagination): **0.04 مللي ثانية**.

*(تنويه: هذا الفحص يمثل قياساً لقدرة استيعاب وسرعة محرك قواعد البيانات المليونية، ولا يعني فحص مليوني رسالة حقيقية في نفس اللحظة).*

---

### الأمان والخصوصية
- **عزل هوائي كامل (Air-Gapped)**: لا توجد أي اتصالات خارجية أو مكتبات سحابية.
- **حماية السجلات (Log Redaction)**: حجب تلقائي لكلمات المرور والرموز السرية والمسارات المطلقة من كافة السجلات.
- **تتبع الأخطاء بالمعرّف الرقمي (Reference ID)**: في حال حدوث أي استثناء، يظهر للمستخدم رقم تتبع فريد لمراجعته في السجلات دون تسريب أي تفاصيل فنية للواجهة.

---

### سجلات التشغيل والدعم الفني
في حال حدوث أي استفسار أو مشكلة تشغيلية:
1. **عرض السجلات**: افتح `View-Logs.bat` لمراقبة السجلات المباشرة وسجل الأخطاء `Logs/errors.log`.
2. **فحص النظام**: شغّل `Check-System.bat` للتحقق من سلامة الهيكل.
3. **توليد حزمة الدعم الفني**: شغّل `Create-Diagnostic-Package.bat` لتوليد ملف تشخيصي مضغوط في مجلد `Diagnostics/` لإرساله لمسؤول النظام (خالٍ تماماً من أي أبحاث أو قواعد بيانات أو أسرار).

---

### العرض التجريبي (Demo)

#### فيديو توضيحي
[شاهد العرض التجريبي](DEMO_URL_HERE)
<!-- Replace DEMO_URL_HERE with the final YouTube / Drive / approved demo URL -->

للاطلاع على دليل وخطوات تصوير العرض التجريبي، يرجى مراجعة [docs/demo/README.md](docs/demo/README.md).

---

### الاختبارات وضمان الجودة
تم التحقق التام من متانة المنظومة واستقرارها عبر حزمة اختبارات شاملة:
- **عدد الاختبارات المؤكدة**: **611 اختباراً آلياً** (نجاح بنسبة 100% عبر جولتي تشغيل متتاليتين).

---

### التثبيت للمطورين (Developer Setup)

```bash
# استنساخ المستودع
git clone https://github.com/MohameddTamerr/arabic-academic-plagiarism-detector.git
cd arabic-academic-plagiarism-detector

# إنشاء وتفعيل البيئة الافتراضية
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# تثبيت الاعتماديات
pip install -r requirements.txt

# تشغيل الاختبارات
pytest

# تشغيل الخادم المحلي للتطوير
python run_app.py
```

---

### هيكل المشروع الأساسي

```text
├── app/                          # مسارات الويب، الخدمات، والمستودعات
├── plagiarism_detector/          # محرك الفحص والتحليل ومعالجة النصوص
├── templates/ & static/          # الواجهات الرسومية والأنماط والأصول
├── tools/                        # أدوات التحكم وإدارة الحزمة المحمولة
├── docs/                         # التوثيق الفني والإداري والأدلة
├── tests/                        # حزم الاختبارات الآلية الشاملة
├── Setup-System.bat              # مشغل التهيئة الأولية
├── Start-System.bat              # مشغل بدء النظام
├── Stop-System.bat               # مشغل الإيقاف وتفريغ السجلات
├── Backup-System.bat             # مشغل النسخ الاحتياطي
├── Restore-System.bat            # مشغل استعادة النظام
├── Check-System.bat              # مشغل الفحص التشخيصي
├── View-Logs.bat                 # مشغل استعراض ومراقبة السجلات
├── Create-Diagnostic-Package.bat # مشغل توليد حزمة الدعم الفني
├── config.py                     # إعدادات المنظومة
└── release_manifest.json         # بيان الإطلاق وبصمات التشفير
```

---

### المساهمة والتطوير
نرحب بالمساهمات التطويرية الأكاديمية والتقنية. يرجى فتح `Issue` لمناقشة التعديلات المقترحة أو إرسال `Pull Request` مع التأكد من اجتياز كافة اختبارات `pytest`.

---

### الترخيص
لم يتم تحديد ترخيص بعد (No license has been selected yet).

---

### إخلاء المسؤولية
هذه المنظومة مخصصة لتقديم التحليلات والمؤشرات الإحصائية المساعدة في كشف التشابه النصي، وتظل المسؤولية الأكاديمية والقانونية لتقييم النزاهة العلمية واعتماد الأبحاث خاضعة حصراً للمحكمين واللجان الأكاديمية المخولة.

---
---

## 🇬🇧 English Section

# Arabic Academic Plagiarism Detector

An offline, air-gapped academic text analysis and similarity detection system specifically engineered for Arabic research papers, theses, and dissertations. The platform assists institutional review committees and peer reviewers in verifying academic integrity by comparing submitted works against a local reference corpus.

> **Academic Notice**: This system is a decision-support tool providing transparent digital similarity evidence. It does not autonomously issue academic misconduct judgments; human peer review remains strictly mandatory for all evaluations.

---

### Overview
Academic institutions require dependable, privacy-preserving tools to ensure research integrity. This platform is built for 100% offline, local operation (Air-Gapped), requiring no internet access or external cloud services. All institutional research and reference corpora remain confidential within the local environment, with secure local area network (LAN) access enabling browser-based review workflows.

---

### Key Features
- **Specialized Arabic NLP Processing**: Advanced Arabic letter normalization, diacritic stripping, and unification of hamzas, alef maqsura, and taa marbuta.
- **Dual-Channel Hybrid Matching Engine**: Combines exact/near-copy lexical shingling (Jaccard similarity) with statistical vector ranking (TF-IDF).
- **Intelligent Citation & Bibliography Filtering**: Accurately recognizes quoted passages and filters terminal reference bibliographies to prevent false positives.
- **Common Academic Phrase Filtering**: Filters standard formulas, titles, and common institutional phrases.
- **Content-Addressed Storage (CAS)**: Deduplicated and tamper-evident local document storage indexed by SHA-256 hashes.
- **Institutional Review Workflow**: Enables reviewer annotations, revision lineage tracking, and multi-stage review status allocation.
- **Role-Based Access Control (RBAC)**: Structured permission tiers (System Admin, Unit Manager, Senior Reviewer, Reviewer).
- **Tamper-Evident Audit Trail**: Immutable logging of all scanning, finalization, and export actions.
- **Zero-Dependency Portable SQLite Deployment**: Immediate deployment via Windows batch launchers running in SQLite WAL mode.
- **Comprehensive Privacy Posture**: Completely air-gapped, zero telemetry, bcrypt password hashing, and CSRF protection.

---

### How It Works

```text
    Upload Research Document (PDF / Word)
                     ↓
        Text & Page Extraction
                     ↓
      Arabic Text Normalization
                     ↓
  Two-Stage Candidate Retrieval (Dual-Channel)
                     ↓
      Detailed Passage Matching
                     ↓
    Citation & Bibliography Analysis
                     ↓
  Interactive Report Generation & Fingerprint
                     ↓
     Mandatory Human Review & Decision
```

---

### Quick Start (Portable Deployment)

The system includes one-click Windows launchers requiring zero command-line expertise:

1. **Initial Setup**: Double-click `Setup-System.bat` to initialize directories and the database.
2. **Start System**: Run `Start-System.bat`; the terminal will display readiness and your default browser will open automatically.
3. **LAN Access**: Authorized reviewer workstations on the same local network can navigate to the displayed URL (e.g., `http://192.168.1.100:5000`).
4. **Clean Shutdown**: Run `Stop-System.bat` to gracefully drain workers and execute a clean WAL checkpoint.
5. **Live Backup**: Run `Backup-System.bat` to create an encrypted, non-blocking backup of the database and CAS storage.
6. **System Diagnostics**: Run `Check-System.bat` to verify disk space, network binding, and database integrity.

---

### System Architecture

```text
       Reviewer Workstations (Web Browser)
                       │
             Local Area Network (LAN)
                       │
         Central Application Server (Flask)
                       │
         ┌─────────────┴─────────────┐
         │                           │
    Database                 Worker Processes
 (SQLite / WAL)               (Multi-Process)
         │
 Local CAS Document Storage
```

> **Deployment Rule**: The SQLite database file (`papers.db`) and document repository must reside on the central server's local physical disk. Storing SQLite files across network file shares (SMB/NAS) is strictly prohibited.

---

### Technology Stack
- **Backend Language**: Python 3.11+
- **Application Framework**: Flask, Jinja2, Vanilla CSS, Modern JavaScript
- **Database Engine**: SQLite (WAL Mode), SQLAlchemy ORM
- **Document Extraction**: PyMuPDF (`fitz`), Python regex engine
- **Analysis Algorithms**: scikit-learn (TF-IDF Vectorization), NumPy, Custom Arabic Normalizer
- **Security & Cryptography**: Bcrypt (cost 12), CSRF protection, SHA-256 integrity verification
- **Testing & Verification**: Pytest, psutil

---

### Academic Reports
The interactive report delivers:
- Total similarity percentage broken down into exact copying and paraphrasing indicators.
- Prioritized list of matched reference sources.
- Side-by-side passage comparison with full textual alignment.
- SHA-256 integrity verification checksum to detect any post-finalization tampering.

---

### Current Release Status
- **Current Version**: `v1.4.1-sqlite-portable-rc`
- **Deployment Posture**: Controlled offline deployment with mandatory human review.
- **Arabic OCR Engine**: Optional; requires approved local `ara.traineddata` installation.
- **Deep Semantic Embeddings**: Disabled by default; uses high-speed dual-channel lexical matching.
- **Complex Paraphrasing**: A known academic research limitation; human reviewer verification is essential.

---

### Measured Performance & Capacity
Extensive empirical benchmark results on an isolated test environment confirmed:
- Scalability tested up to **2,000,000 synthetic research records** (~7.2 million relational rows, ~4.7 GB SQLite DB).
- Primary Key and Reference Number search latency: **0.01 – 0.07 ms**.
- Keyset / Cursor Pagination latency: **0.04 ms** (eliminating traditional deep offset scan overhead).

*(Note: This measures database indexing and query scalability; it does not imply concurrent scanning of two million live documents).*

---

### Security & Privacy Posture
- **100% Air-Gapped**: Zero external socket calls, zero cloud dependencies, and zero analytics telemetry.
- **Privacy Redaction Filter**: Automatic redaction of passwords, security tokens, and physical paths in all logs.
- **User Reference Tracking**: Unhandled exceptions generate a unique tracking ID (`Reference ID`) shown to users and logged securely, preventing server stack trace leaks.

---

### Operations & Support Diagnostics
When diagnosing operational issues:
1. **View Logs**: Double-click `View-Logs.bat` to monitor real-time server activity, worker logs, or recent errors in `Logs/errors.log`.
2. **System Health**: Run `Check-System.bat` for an automated environment integrity check.
3. **Create Support Package**: Run `Create-Diagnostic-Package.bat` to bundle sanitized logs and health metrics into `Diagnostics/diagnostic-YYYYMMDD-HHMMSS.zip` (guaranteed free of research documents, database files, and secret keys).

---

### Demonstration (Demo)

#### Video Walkthrough
[Watch the System Demonstration](DEMO_URL_HERE)
<!-- Replace DEMO_URL_HERE with the final YouTube / Drive / approved demo URL -->

For detailed recording guidelines and presentation timing, refer to [docs/demo/README.md](docs/demo/README.md).

---

### Automated Testing & Quality Assurance
The codebase is validated with an exhaustive test suite:
- **Verified Test Count**: **611 automated tests** (100% pass rate achieved across consecutive regression runs).

---

### Developer Setup

```bash
# Clone the repository
git clone https://github.com/MohameddTamerr/arabic-academic-plagiarism-detector.git
cd arabic-academic-plagiarism-detector

# Create and activate virtual environment
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the test suite
pytest

# Start the local development server
python run_app.py
```

---

### Repository Structure

```text
├── app/                          # Application routes, services, models, and repositories
├── plagiarism_detector/          # Core NLP, matching algorithms, and document extractors
├── templates/ & static/          # UI templates, glassmorphism stylesheets, and static assets
├── tools/                        # Portable management CLI and packaging automation
├── docs/                         # Technical architecture, administrator guides, and releases
├── tests/                        # Comprehensive automated test suite
├── Setup-System.bat              # One-click initial setup launcher
├── Start-System.bat              # One-click startup and browser launcher
├── Stop-System.bat               # Clean shutdown and WAL checkpoint launcher
├── Backup-System.bat             # Instant live backup launcher
├── Restore-System.bat            # Interactive disaster recovery launcher
├── Check-System.bat              # System health and diagnostic check launcher
├── View-Logs.bat                 # Interactive log monitor launcher
├── Create-Diagnostic-Package.bat # Diagnostic package generator for support
├── config.py                     # Central configuration management
└── release_manifest.json         # Release candidate manifest and critical file hashes
```

---

### Contributing
Technical contributions and academic research enhancements are welcome. Please open an Issue to discuss proposed changes or submit a Pull Request accompanied by matching pytest test cases.

---

### License
No license has been selected yet.

---

### Academic Disclaimer
This software is designed strictly as a decision-support tool for similarity analysis. All final evaluations, disciplinary decisions, and academic integrity determinations remain the sole responsibility of authorized human academic committees and reviewers.
