# دليل تشغيل وإدارة عمال الفحص الموزعين (Worker Operations & Lifecycle)
## Ministry Roadmap — Prompt 3: Worker Operations

---

## 1. هوية العامل وسجل الحالة (Worker Identity & Registry)

يتم توليد معرف فريد لكل عامل عند الإقلاع يجمع بين:
$$\text{Worker ID} = \text{hostname} + \text{"\_"} + \text{PID} + \text{"\_"} + \text{boot\_token}$$

يتم تسجيل العامل في جدول `worker_registry`:
- `worker_id`: المعرف الفريد.
- `hostname`: اسم الخادم المضيف على شبكة الوزارة.
- `capabilities`: قائمة الإمكانيات المعتمدة (مفصولة بفاصلة: `SCAN,OCR,INDEX_BUILD,EXPORT`).
- `status`: حالة العامل (`ONLINE`, `BUSY`, `DRAINING`, `OFFLINE`).
- `active_jobs_count`: عدد المهام قيد التنفيذ حالياً.
- `last_heartbeat_at`: توقيت آخر نبضة حياة.
- `worker_version`: إصدار بروتوكول العامل.

---

## 2. توجيه الإمكانيات (Capability-Based Routing)

تتيح المنظومة تشغيل خوادم مخصصة ذات عتاد محدد:
- **خوادم الفحص السريع (Scan Workers):** `--capabilities SCAN,EXPORT`
- **خوادم استخراج النصوص والـ OCR (OCR Workers):** `--capabilities OCR`
- **خوادم صيانة الفهارس والذاكرة (Index Workers):** `--capabilities INDEX_BUILD,STORAGE_INTEGRITY_SCAN`

---

## 3. وضع التجفيف والإغلاق السلس (Drain Mode & Graceful Shutdown)

- **أمر التجفيف (Drain Command):**
  - تحويل حالة العامل إلى `DRAINING` عبر واجهة الإدارة أو سطر الأوامر.
  - يتوقف العامل فوراً عن سحب أي مهام جديدة من الطابور.
  - يستمر العامل في إنهاء المهام الجارية بأمان ونزاهة تامة.
  - عند انتهاء جميع المهام، يخرج العامل بهدوء ويتحول إلى `OFFLINE`.
- **استجابة إشارات الإيقاف (`SIGINT` / `SIGTERM`):**
  - تفعيل وضع التجفيف السريع.
  - تحرير عقود الإيجار للمهام التي لم تبدأ معالجتها الحرجة بعد لتمكين العمال الآخرين من التقاطها فوراً.

---

## 4. تشغيل العامل عبر سطر الأوامر (CLI Usage)

```bash
# تشغيل عامل عام بجميع الإمكانيات
python tools/run_worker.py --concurrency 2

# تشغيل خادم مخصص لعمليات OCR
python tools/run_worker.py --capabilities OCR --concurrency 1

# تشغيل خادم مخصص للفحص بـ 4 عمال
python tools/run_worker.py --capabilities SCAN,EXPORT --concurrency 4 --heartbeat-interval 10
```
