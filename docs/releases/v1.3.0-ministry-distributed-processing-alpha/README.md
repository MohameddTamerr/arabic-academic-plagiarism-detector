# وثيقة الإصدار: Release v1.3.0-ministry-distributed-processing-alpha (Distributed Queue & Multi-Worker Architecture)

---

## 1. ملخص الإصدار (Release Overview)

يمثل الإصدار **`v1.3.0-ministry-distributed-processing-alpha`** الأساس المعماري لمعالجة المهام الموزعة وتوزيع أعباء الفحص عبر خوادم وعمال متعددين لمسار التحول الوزاري (Ministry Roadmap — Prompt 3)، والذي يفصل خوادم التطبيق والواجهات عن عمال الفحص المستقلين عبر طابور مهام دائم ومعاملاتي في قاعدة البيانات، مع دعم الاستحواذ الذري، عقود الإيجار، نبضات القلب، عدالة الأقسام، ومقاومة الضغط.

- **معرف الإصدار:** `v1.3.0-ministry-distributed-processing-alpha`
- **إصدار التطبيق:** `2.7.0`
- **إصدار محرك الفحص:** `1.5.0`
- **محرك طابور المهام:** `DatabaseJobQueue` مع الاستحواذ الذري وعقود الإيجار المؤقتة
- **إصدار بروتوكول العامل:** `1.3.0`
- **سقف تزامن OCR:** `1` (محكوم بحوكمة الموارد)
- **محرك الاسترجاع:** `LocalDiskRetrievalIndex` ثنائي المرحلة مع سقف $K \le 50$
- **أدوات الإدارة والتشغيل:**
  - [`tools/run_worker.py`](file:///c:/Users/user/Downloads/Baba/tools/run_worker.py)
  - [`tools/benchmark_queue_concurrency.py`](file:///c:/Users/user/Downloads/Baba/tools/benchmark_queue_concurrency.py)
  - [`tools/recover_stale_jobs.py`](file:///c:/Users/user/Downloads/Baba/tools/recover_stale_jobs.py)

---

## 2. الإنجازات المحققة في هذا الإصدار (Milestone Deliverables)

1. **طابور المهام الموزع الدائم (Persistent Distributed Job Queue):**
   - جدول دائم `queue_jobs` يدعم الاستحواذ الذري عبر بطاقات الأمان `claim_token` مع منع تام للمعالجة المزدوجة وفقدان المهام.
2. **عقود الإيجار ونبضات الحياة والتعافي التلقائي (Leases, Heartbeats & Crash Recovery):**
   - تمديد دوري لعقود إيجار المهام النشطة، واستعادة تلقائية وسلسة للمهام المنقطعة عند انهيار العمال دون فقدان لحالة النظام.
3. **توجيه الإمكانيات ووضع التجفيف (Capability Routing & Drain Mode):**
   - إمكانية تشغيل خوادم وعمال مخصصين (`SCAN`, `OCR`, `INDEX_BUILD`, `EXPORT`) مع دعم الإيقاف السلس.
4. **حوكمة الموارد ومقاومة الضغط وعدالة الأقسام (Resource Governance & Fairness):**
   - حظر سحب المهام عند انخفاض مساحة القرص عن 5 GB، وتوزيع عادل للحصص بين الأقسام الأكاديمية.
5. **الاستمرار الصارم بالعزل الهوائي والأوفلاين (Zero External Broker Dependencies):**
   - المنظومة تعمل بنسبة 100% بدون أي وسطاء سحابيين أو برامج خارجية إجبارية.
