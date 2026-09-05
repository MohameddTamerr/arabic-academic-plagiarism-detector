# وثيقة الإصدار: Release v1.1.0-ministry-db-alpha (Ministry Architecture Foundation)

---

## 1. ملخص الإصدار (Release Overview)

يمثل الإصدار **`v1.1.0-ministry-db-alpha`** الأساس المعماري للتحول الوزاري (Ministry Roadmap — Prompt 1)، والذي يفصل طبقة البيانات والعلاقات عن الخادم التطبيقي، مع توفير دعم كامل لمحرك **PostgreSQL** للشبكات الوزارية الداخلية مع الحفاظ التام على **SQLite** للتوافق والتشغيل المكتبي.

- **معرف الإصدار:** `v1.1.0-ministry-db-alpha`
- **إصدار التطبيق:** `2.5.0`
- **إصدار محرك الفحص:** `1.3.0`
- **محركات قواعد البيانات المدعومة:** `sqlite`, `postgresql`
- **المحرك الافتراضي:** `sqlite` (التشغيل المستقل والمحلي)
- **المحرك الوزاري المستهدف:** `postgresql` (للشبكات الداخلية مع SCRAM-SHA-256)
- **أداة الهجرة المعتمدة:** [`tools/migrate_sqlite_to_postgresql.py`](file:///c:/Users/user/Downloads/Baba/tools/migrate_sqlite_to_postgresql.py)

---

## 2. الإنجازات المحققة في هذا الإصدار (Milestone Deliverables)

1. **تجريد طبقة قواعد البيانات (Dual-Backend Abstraction):**
   - عزل كامل لمحرك قاعدة البيانات عبر SQLAlchemy وتفعيل `QueuePool` منضبط مع `pool_pre_ping=True` لـ PostgreSQL.
2. **أمان البيانات وبيانات الاعتماد (Zero-Leakage Credential Protection):**
   - حظر كلمات المرور الافتراضية، وإخفاء سلاسل DSN في السجلات ونقاط فحص الصحة (`get_masked_database_url`).
3. **أداة هجرة موثوقة (Offline SQLite to PostgreSQL Migration CLI):**
   - فحص مسبق لسلامة SQLite، ونقل جداول بترتيب القيود الخارجية، مع مطابقة تامة بنسبة 100% لبصمات التقارير المعتمدة.
4. **توليد تسلسلي ذري وآمن للتزامن (Concurrency-Safe Sequences):**
   - دعم `UPDATE ... RETURNING` في PostgreSQL لمنع أي تصادم في الأرقام المرجعية الرسمية (`RES-YYYY-XXXXXX`).
5. **استمرار الحظر الأوفلاين التام (Air-Gapped Isolation):**
   - صفر اتصالات خارجية، صفر سحابة، صفر واجهات خارجية.
