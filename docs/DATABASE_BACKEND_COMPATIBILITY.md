# مصفوفة توافقية قواعد البيانات (Database Backend Compatibility Matrix)

---

## 1. التوافقية البرمجية عبر المحركات (Cross-Dialect SQL Compatibility)

| الخاصية / الوظيفة | تطبيق SQLite | تطبيق PostgreSQL | إستراتيجية التوحيد المعمارية |
| :--- | :--- | :--- | :--- |
| **المفاتيح الأساسية التلقائية** | `INTEGER PRIMARY KEY AUTOINCREMENT` | `SERIAL` / `BIGSERIAL` / `IDENTITY` | استخدام `Column(Integer, primary_key=True, autoincrement=True)` القياسي في SQLAlchemy. |
| **التسلسلات المخصصة (Reference Numbers)** | زيادة ذرية عبر SQL مع قفل كائن المعاملة | `UPDATE ... RETURNING` مع أقفال الصفوف | دالة مركزية في `app.services.reference_service` تكتشف المحرك وتنفذ الاستعلام الذري المناسب. |
| **قفل المعاملات** | قفل الملف بالكامل في نمط WAL | `SELECT ... FOR UPDATE` و MVCC | استخدام معاملات SQLAlchemy المعزولة مع `get_session()`. |
| **فحص السلامة (Health Check)** | `PRAGMA integrity_check` و `PRAGMA foreign_key_check` | استعلام `SELECT 1` وفحص اتصالات التجمع | تنفيذ الفحص الشرطي بناءً على `base_repo.get_backend_type()`. |
| **تجمع الاتصالات (Connection Pool)** | `NullPool` أو أحادي الخيط للملف المحلي | `QueuePool` مع `pool_pre_ping=True` | تهيئة المحرك ديناميكياً في `base_repo._create_configured_engine()`. |
| **إخفاء الأسرار (Secret Redaction)** | مسار الملف المحلي فقط | إخفاء كلمة المرور واستبدالها بـ `***` | دوال تنقية مركزية في `config.py` و `system_health_service.py`. |

---

## 2. قواعد كتابة الاستعلامات الموحدة (Portable Query Guidelines)

1. **حظر الدوال المخصصة لكل محرك في الاستعلامات العامة:** تجنب استخدام دوال SQLite الخاصة مثل `strftime('%Y-%m-%d', ...)` واستبدالها بكائنات `datetime` في بايثون أو دوال SQLAlchemy العامة `func.now()`.
2. **عزل أي استعلامات خاصة بالمحرك:** في حال دعت الحاجة لاستعلام خاص بمحرك معين، يتم عزله داخل فرع شرطي يفحص نوع المحرك مع كتابة اختبارات مطابقة (Contract Tests).
