# وثيقة الإصدار: Release v1.2.0-ministry-storage-retrieval-alpha (Enterprise Storage & Million-Scale Retrieval Foundation)

---

## 1. ملخص الإصدار (Release Overview)

يمثل الإصدار **`v1.2.0-ministry-storage-retrieval-alpha`** الأساس التخزيني واسترجاع المرشحات الفائق لمسار التحول الوزاري (Ministry Roadmap — Prompt 2)، والذي يوفر تجريداً كاملاً لطبقة تخزين المستندات الأكاديمية بنظام العنونة بالمحتوى (Content-Addressed Storage CAS) مع فهرس استرجاع مقلوب ثنائي القناة (Dual-Channel Inverted Index) يدعم استرجاع المرشحات بزمن تحت خطي فائق السرعة عبر ملايين المقاطع.

- **معرف الإصدار:** `v1.2.0-ministry-storage-retrieval-alpha`
- **إصدار التطبيق:** `2.6.0`
- **إصدار محرك الفحص:** `1.4.0`
- **طبقة التخزين المعتمدة:** `FileSystemStorageBackend` بنظام التجزئة `storage/documents/ab/cd/<sha256>/`
- **محرك الاسترجاع:** `LocalDiskRetrievalIndex` ثنائي القناة (Word Postings + Char 3-gram Postings)
- **سقف المرشحات الصارم:** $K \le 50$ (Top-K Bounded Contract)
- **أدوات الإدارة والتشغيل:**
  - [`tools/rebuild_retrieval_index.py`](file:///c:/Users/user/Downloads/Baba/tools/rebuild_retrieval_index.py)
  - [`tools/migrate_storage_layout.py`](file:///c:/Users/user/Downloads/Baba/tools/migrate_storage_layout.py)
  - [`tools/benchmark_retrieval_scale.py`](file:///c:/Users/user/Downloads/Baba/tools/benchmark_retrieval_scale.py)

---

## 2. الإنجازات المحققة في هذا الإصدار (Milestone Deliverables)

1. **تجريد طبقة التخزين المؤسسي (Enterprise Storage Abstraction):**
   - تصميم واجهة `StorageBackend` وتطبيق `FileSystemStorageBackend` بنظام تجزئة بادلين (2-level prefix sharding) يمنع تكدس المجلدات ويدعم إلغاء التكرار الذكي المعتمد على بصمة SHA-256 مع عدادات مراجع دقيقة.
2. **فهرس استرجاع المرشحات عالي القابلية للتوسع (Persistent Sublinear Retrieval Index):**
   - استبدال المسح الخطي $O(N \times M)$ بفهرس مقلوب ثنائي القناة يعالج استعلامات النصوص بزمن تحت خطي مع عزل نطاق الأقسام وحفظ ذري مشفر ببصمة تحقق SHA-256.
3. **تدقيق سلامة التخزين والترميم الذاتي (Storage Integrity & Auditability):**
   - وظيفة `verify_storage_integrity()` لمطابقة البصمات، كشف الملفات المعزولة، وتحديث أطوال الملفات بدقة تامة.
4. **أدوات تشغيل وإعادة فهرسة متقدمة (Operational CLI Tools):**
   - أدوات متكاملة لإعادة بناء الفهارس دورياً، هجرة الملفات من التخزين المسطح القديم إلى CAS، وقياس الأداء التوسعي حتى مليون مقطع نصي.
5. **الالتزام الصارم بالأوفلاين والعزل الهوائي (Zero External Dependencies):**
   - يعمل النظام كلياً بدون أي اتصالات إنترنت، سحابة، أو مكتبات خارجية غير مثبتة محلياً.
