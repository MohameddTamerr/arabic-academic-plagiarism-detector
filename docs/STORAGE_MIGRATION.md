# دليل هجرة مسارات التخزين إلى الهيكل المؤسسي المقسم (Storage Layout Migration Guide)

---

## 1. أهداف وضمانات الهجرة (Migration Safety & Invariants)

توفر أداة [`tools/migrate_storage_layout.py`](file:///c:/Users/user/Downloads/Baba/tools/migrate_storage_layout.py) آلية هجرة أوفلاين آمنة للملفات التاريخية من المجلدات المسطحة (`temp_uploads/`, `research_files/`) إلى الهيكل المقسم بالمحتوى (`storage/documents/ab/cd/<hash>/`):

1. **التحقق من البصمات (SHA-256 Verification):** احتساب بصمة كل ملف والتأكد من مطابقتها قبل النقل.
2. **عدم إتلاف المصدر أثناء الهجرة (Copy-Then-Verify):** نسخ الملفات إلى الموقع المقسم الجديد والتحقق من صحتها قبل تحديث مؤشرات قاعدة البيانات.
3. **دعم نمط المحاكاة (Dry-Run Mode):** إمكانية فحص الملفات المخطط نقلها دون تعديل أي ملف أو قاعدة بيانات.
4. **الدمج التلقائي للملفات المكررة (Deduplication Consolidation):** دمج الملفات المتطابقة في مسار فيزيائي واحد مع الإبقاء على كافة سجلات الأبحاث مستقلة.

---

## 2. تشغيل أداة هجرة التخزين (Execution Runbook)

```powershell
# 1. تشغيل المحاكاة للتأكد من حالة الملفات
python tools/migrate_storage_layout.py --dry-run

# 2. تنفيذ الهجرة الفعلية مع تصدير تقرير التدقيق
python tools/migrate_storage_layout.py --output-report "storage_migration_report.json"
```
