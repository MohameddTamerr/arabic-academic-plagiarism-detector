# تدقيق المعمارية وتوزيع المهام المؤسسية (Distributed Processing Audit)
## Ministry Roadmap — Prompt 3: Processing Model Transformation

---

## 1. ملخص التدقيق للوضع السابق (Pilot Legacy Audit)

في الإصدارات السابقة (Pilot RC2 و Prompt 1/2)، كانت معالجة المهام تعتمد على خيط تنفيذ محلي داخل نفس مساحة الذاكرة (In-Process Daemon Thread) المدارة عبر `app/services/job_queue_service.py`:

| الخاصية | النموذج السابق (Single-Node In-Process) | النموذج الموزع المعتمد (Prompt 3 Distributed Queue) |
| :--- | :--- | :--- |
| **موضع تخزين المهام** | قائمة ذاكرية `queue.Queue` ومصفوفات في RAM | جدول دائم في قاعدة البيانات `queue_jobs` |
| **آلية الاستحواذ (Claiming)** | سحب من الذاكرة المحلية دون أقفال موزعة | استحواذ ذري عبر المعاملات وبطاقات الاستحواذ `claim_token` |
| **استقرار المهام عند الانهيار** | فقدان حالة المهام الجارية عند إعادة تشغيل التطبيق | عقد إيجار مؤقت `lease_expires_at` مع استعادة تلقائية |
| **نبضات العامل (Heartbeats)** | لا توجد نبضات للعمال المستقلين | نبضات دورية في `worker_registry` لتمييز العامل البطيء عن الميت |
| **تعدد العمال والعمليات** | محصور داخل معالج بايثون واحد | عمال مستقلون عبر عدة عمليات وحواسيب على شبكة الوزارة |
| **توجيه الإمكانيات (Capabilities)** | كل عامل ينفذ جميع أنواع المهام | توجيه مخصص (`SCAN`, `OCR`, `INDEX_BUILD`, `EXPORT`) |
| **عدالة الأقسام (Fairness)** | معالجة بأسبقية الوصول (FIFO) قد تسد الطابور | حصص وجدولة عادلة بين الأقسام الأكاديمية |
| **مقاومة الضغط (Backpressure)** | استمرار قبول الرفع حتى امتلاء القرص أو الانهيار | رفض أو إبطاء منضبط عند تجاوز حدود الموارد |

---

## 2. تتبع دورة حياة المهام (Job Lifecycle Transitions)

```
[QUEUED] ──(Atomic Claim with Lease)──> [PROCESSING] ──(Scan Finished)──> [COMPLETED]
   │                                          │
   │ (Admin Cancel)                           ├──(Recoverable Failure)──> [RETRY_WAITING] ──> [QUEUED]
   v                                          │
[CANCELLED]                                   ├──(Unrecoverable/Fatal)──> [FAILED]
                                              │
                                              └──(Worker Crash / Lease Timeout)──> [STALE_RECOVERED] ──> [QUEUED]
```

### الحالات المعتمدة:
1. `QUEUED`: المهمة جاهزة ومتاحة للاستحواذ وفق الأولوية وعدالة القسم.
2. `PROCESSING`: تم الاستحواذ عليها من عامل محدد مع توثيق `claimed_by` و `claim_token` و `lease_expires_at`.
3. `RETRY_WAITING`: حدث خطأ قابل للإعادة (مثل انقطاع مؤقت) مع تطبيق التراجع الأسي (Exponential Backoff).
4. `COMPLETED`: اكتملت المعالجة بنجاح وتم توليد التقرير المعتمد.
5. `FAILED`: فشل دائم غير قابل للإعادة (مثل تلف هيكلي في ملف PDF) مع تشفير رمز الخطأ.
6. `CANCELLED`: تم إلغاء المهمة بأمر إداري معتمد.
7. `STALE_RECOVERED`: انتهى عقد إيجار العامل المنقطع واستعادت المنظومة المهمة للطابور.
