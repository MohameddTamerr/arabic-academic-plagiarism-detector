# دليل هجرة البيانات من SQLite إلى PostgreSQL أوفلاين (Database Migration Guide)

---

## 1. أهداف وضمانات الهجرة (Migration Goals & Safety Guarantees)

تهدف أداة الهجرة [`tools/migrate_sqlite_to_postgresql.py`](file:///c:/Users/user/Downloads/Baba/tools/migrate_sqlite_to_postgresql.py) إلى نقل كافة البيانات التاريخية والمعتمدة من بيئة SQLite المحلية إلى خادم PostgreSQL الوزاري دون أي فقد للبيانات وبأمان تام:

1. **سلامة المصدر (Read-Only Source Integrity):**
   - لا تعدل الأداة أي بايت داخل ملف SQLite المصدر.
   - يتم احتساب وحفظ بصمة SHA-256 لملف SQLite قبل وبعد الهجرة للتأكد من عدم حدوث أي تعديل.
2. **مطابقة بصمات التقارير المعتمدة (Finalized Report Hash Invariant):**
   - مطابقة تامة لبصمات التجزئة SHA-256 للتقارير المعتمدة قبل وبعد الهجرة للتأكد من ثبات محتوى التقارير.
3. **مطابقة بصمة قاعدة المراجع (Reference Corpus Fingerprint Invariant):**
   - التأكد من تطابق بصمات إصدارات المراجع وحالاتها وسلاسل التعديلات بدقة.
4. **الحفاظ على تجزئات كلمات المرور (Password Hashes Preservation):**
   - نقل تجزئات bcrypt كما هي دون إعادة تشفير أو تعديل، مع الاحتفاظ بـ `session_version` وحالات المستخدمين.
5. **إيقاف المعالجة عند أي خطأ (Fail-Safe Execution):**
   - تتوقف الأداة فوراً مع تقرير تفصيلي في حال فشل أي قيد فريد أو مفتاح أجنبي.

---

## 2. خطوات تشغيل الهجرة (Step-by-Step Execution Runbook)

### المرحلة 1: التحقق المسبق (Preflight Checks)
```powershell
python tools/migrate_sqlite_to_postgresql.py --sqlite-path "%APPDATA%\ArabicPlagiarismDetector\papers.db" --pg-dsn "postgresql://plagiarism_app:SECURE_PASS@127.0.0.1:5432/plagiarism_db" --dry-run
```

### المرحلة 2: تنفيذ الهجرة الفعلية (Live Migration)
```powershell
python tools/migrate_sqlite_to_postgresql.py --sqlite-path "%APPDATA%\ArabicPlagiarismDetector\papers.db" --pg-dsn "postgresql://plagiarism_app:SECURE_PASS@127.0.0.1:5432/plagiarism_db" --output-report "migration_report.json"
```

---

## 3. محتويات تقرير الهجرة (Migration Verification Report)

ينتج عن تنفيذ الأداة تقرير بصيغة JSON يتضمن:
- البصمات الإلكترونية لقاعدة البيانات المصدر والوجهة.
- عدد السجلات المنقولة والمطابقة لكل جدول على حدة.
- قائمة بالبصمات المعتمدة للتقارير للتأكد من مطابقتها بنسبة 100%.
- الطوابع الزمنية لبدء ونهاية الهجرة وإجمالي الوقت المستغرق.
