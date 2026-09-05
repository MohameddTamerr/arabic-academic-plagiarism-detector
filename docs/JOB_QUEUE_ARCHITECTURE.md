# وثيقة المعمارية الهندسية لطابور المهام الموزع الدائم (Persistent Distributed Job Queue)
## Ministry Roadmap — Prompt 3: Queue Specification

---

## 1. تصميم الجداول وقاعدة البيانات (Queue Schema Definition)

تم اعتماد جدول `queue_jobs` كطبقة تخزين دائمة للمهام مستقلة عن ذاكرة العمليات:

```sql
CREATE TABLE queue_jobs (
    id VARCHAR(64) PRIMARY KEY,
    job_type VARCHAR(50) NOT NULL,            -- SCAN_RESEARCH, OCR_DOCUMENT, INDEX_INCREMENTAL, INDEX_REBUILD, STORAGE_INTEGRITY_SCAN, REPORT_EXPORT
    status VARCHAR(50) NOT NULL DEFAULT 'queued', -- queued, processing, retry_waiting, completed, failed, cancelled
    priority INT NOT NULL DEFAULT 3,           -- 1: CRITICAL_ADMIN, 2: INTERACTIVE, 3: NORMAL, 4: BATCH, 5: MAINTENANCE
    department_id VARCHAR(64),                 -- لجدولة العدالة المؤسسية
    research_id INT,                           -- ربط بالبحث الأكاديمي
    batch_id VARCHAR(64),                      -- ربط بدفعة الفحص
    payload_json TEXT,                         -- بيانات ومعايير الفحص (دون تضمين ملفات ضخمة)
    attempt_count INT DEFAULT 0,
    max_attempts INT DEFAULT 3,
    claimed_by VARCHAR(128),                   -- معرف العامل المستحوذ
    claim_token VARCHAR(64),                   -- رمز أمان الاستحواذ العشوائي
    lease_expires_at TIMESTAMP,                -- موعد انتهاء عقد الإيجار
    last_heartbeat_at TIMESTAMP,               -- توقيت آخر نبضة حية
    available_at TIMESTAMP NOT NULL,           -- موعد إتاحة المهمة (للتراجع الأسي)
    created_at TIMESTAMP NOT NULL,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_code VARCHAR(100),
    error_message_redacted VARCHAR(500),
    worker_protocol_version VARCHAR(20) DEFAULT '1.0.0'
);
```

---

## 2. بروتوكول الاستحواذ الذري (Atomic Claim Protocol)

### أهداف البروتوكول:
1. **منع المعالجة المزدوجة (Zero Double-Processing):** استحالة استحواذ عاملين على نفس المهمة في الوقت نفسه.
2. **عقود الإيجار (Leases):** تعيين مدة إيجار أولية (مثلاً 60 ثانية)، تتجدد بنبضات قلب العامل أثناء المعالجة النشطة.
3. **التوافق المزدوج (PostgreSQL / SQLite):**
   - في PostgreSQL: استخدام `SELECT ... FOR UPDATE SKIP LOCKED` للاستحواذ فائق التزامن دون أي تعليق أو قفل للطابور.
   - في SQLite: تنفيذ المعاملات الفورية `BEGIN IMMEDIATE` لضمان حصرية القفل المكتبي.

---

## 3. مستويات الأولوية والجدولة (Bounded Priorities)

| مستوى الأولوية | الرمز | الوصف والاستخدام |
| :--- | :--- | :--- |
| **1** | `CRITICAL_ADMIN` | عمليات الصيانة الطارئة والتحقق الإداري الفوري |
| **2** | `INTERACTIVE` | فحص المستندات الفردية المرفوعة مباشرة عبر واجهة المستخدم |
| **3** | `NORMAL` | المعالجة الاعتيادية للأبحاث والدفعات الأكاديمية الافتراضية |
| **4** | `BATCH` | معالجة دفعات الأبحاث الكبيرة خارج أوقات الذروة |
| **5** | `MAINTENANCE` | تدقيق سلامة التخزين الدوري وإعادة بناء الفهارس المجدولة |

---

## 4. عدالة الأقسام (Department Fairness & Anti-Starvation)

- **المشكلة:** قيام قسم أكاديمي واحد برفع 5,000 بحث قد يسد الطابور لأيام ويمنع الأقسام الأخرى من الفحص.
- **الحل الهندسي:**
  - يتم استعلام الطابور مع مراعاة عدد المهام الجارية لكل قسم `active_jobs_per_dept`.
  - تطبيق سقف تزامن لكل قسم (مثلاً: لا يستحوذ أي قسم على أكثر من 50% من العمال المتاحين إذا كانت هناك أقسام أخرى في قائمة الانتظار).
