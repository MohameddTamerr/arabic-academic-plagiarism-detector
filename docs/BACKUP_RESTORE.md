# دليل النسخ الاحتياطي والتعافي من الكوارث (Disaster Recovery Runbook)
## Arabic Academic Plagiarism Detector — Release v1.0.0-rc1

---

### 1. استراتيجية النسخ الاحتياطي الذاتي (Automated Backup Architecture)

توفر المنظومة نظام نسخ احتياطي مدمج ومحصن يضمن حفظ نسخة متناسقة كلياً تشمل:
1. **قاعدة البيانات الأساسية (`papers.db`):** تُنسخ بنمط المعاملات الآمنة مع قفل القراءة.
2. **ملفات التخزين الحيوية (`storage/research`, `storage/references`):** تُضغط ضمن أرشيف ZIP موحد.
3. **سجل الكتالوج الموثق (`catalog.json`):** يسجل بصمة التجزئة SHA-256، وحجم الأرشيف، وعدد الأبحاث، والتوقيت بدقة.

---

### 2. إنشاء نسخة احتياطية جديدة (Creating a Backup)

#### عبر الواجهة الرسومية:
الانتقال إلى لوحة المشرف -> النسخ الاحتياطي -> الضغط على **«إنشاء نسخة احتياطية جديدة»**.

#### عبر سطر الأوامر (PowerShell):
```powershell
python -c "from app.services.backup_service import create_backup; print(create_backup(label='Daily_Automated'))"
```

---

### 3. استعادة النسخة الاحتياطية (Restoring from Backup)

تتم عملية الاستعادة عبر بروتوكول سلامة صارم ثلاثي المراحل:
1. **التحقق من سلامة الأرشيف (Integrity Verification):** إعادة حساب SHA-256 للملف ومقارنته مع الكتالوج.
2. **أخذ نسخة أمان احترازية (Safety Snapshot):** نسخ الحالة الحالية للنظام تلقائياً قبل البدء بالاستعادة تحسباً لأي طارئ.
3. **الاستعادة واستئناف العمليات:** استبدال قاعدة البيانات وإعادة فك ضغط ملفات التخزين مع تشغيل `PRAGMA integrity_check`.

```powershell
python -c "from app.services.backup_service import restore_backup; print(restore_backup('backup_filename.zip'))"
```

---

### 4. أهداف زمن التعافي وفقدان البيانات (Pilot Targets & Recommended Objectives)

- **هدف نقطة التعافي المستهدف (Target RPO):** أقل من 24 ساعة (مع تنفيذ جدول النسخ اليومي الموصى به) — *مصنف كـ PILOT TARGET / RECOMMENDED OBJECTIVE*.
- **هدف زمن الاستعادة المستهدف (Target RTO):** أقل من 10 دقائق للأرشيف بحجم يصل إلى 5 جيجابايت — *مصنف كـ PILOT TARGET / RECOMMENDED OBJECTIVE*.
- **التوصية المؤسسية للتشغيل التجريبي:** نسخ ملفات الأرشيف من مجلد `backups` أسبوعياً إلى وحدة تخزين خارجية منفصلة ومعزولة (Offline External Disk).
