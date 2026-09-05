# دليل نشر وإعداد خادم PostgreSQL الوزاري أوفلاين (Offline PostgreSQL Deployment)

---

## 1. المتطلبات والسياسات العامة (Requirements & Policies)

1. **العمل أوفلاين بالكامل (100% Air-Gapped):**
   - يتم تثبيت PostgreSQL يدوياً أو عبر مستودعات الحزم المحلية داخل الشبكة الداخلية للوزارة دون الاتصال بالإنترنت.
2. **بروتوكول التوثيق المعتمد:**
   - استخدام `SCRAM-SHA-256` حصراً في `pg_hba.conf`.
3. **تشفير الاتصال الداخلي (LAN TLS):**
   - تفعيل TLS للاتصالات عبر الشبكة المحلية باستخدام شهادات رقمية صادرة من المرجع المصدق الداخلي للمؤسسة (Internal Enterprise CA) دون الحاجة لأي مراجع خارجية.
4. **حظر المستخدم الافتراضي (No Hardcoded Superuser):**
   - حظر استخدام كلمة مرور افتراضية، وإنشاء مستخدم مخصص معزول لصلاحيات التطبيق فقط.

---

## 2. خطوات تهيئة قاعدة البيانات للمنظومة (Database Initialization Script)

```sql
-- 1. إنشاء قاعدة البيانات ومستخدم التطبيق داخل الشبكة الداخلية
CREATE USER plagiarism_app WITH PASSWORD 'SECURE_STRONG_LOCAL_PASSWORD' ENCRYPTED SCRAM-SHA-256;
CREATE DATABASE plagiarism_db OWNER plagiarism_app ENCODING 'UTF8' LC_COLLATE 'C' LC_CTYPE 'C';

-- 2. منح الصلاحيات اللازمة للمستخدم
GRANT ALL PRIVILEGES ON DATABASE plagiarism_db TO plagiarism_app;
\c plagiarism_db plagiarism_app

-- 3. ضبط معايير الجلسة القياسية
ALTER ROLE plagiarism_app SET client_encoding TO 'utf8';
ALTER ROLE plagiarism_app SET timezone TO 'UTC';
```

---

## 3. متغيرات البيئة لخادم التطبيق (Application Environment Configuration)

يتم تكوين خادم التطبيق عبر متغيرات البيئة التالية أو عبر ملف الإعدادات المحلي المحمي:

```bash
# تفعيل محرك PostgreSQL
DB_BACKEND=postgresql
DATABASE_BACKEND=postgresql

# معلمات الاتصال بالشبكة الداخلية (LAN Host)
DB_HOST=10.0.1.50
DB_PORT=5432
DB_NAME=plagiarism_db
DB_USER=plagiarism_app
DB_PASSWORD=YOUR_STRONG_PASSWORD

# معلمات مجمع الاتصالات (Connection Pool Tuning)
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=1800
```

---

## 4. حماية بيانات الاعتماد والسجلات (Credential Protection & Redaction)

- لا يتم تضمين كلمات المرور أو سلاسل DSN الكاملة في أي سجلات أو استجابات لنقاط فحص صحة المنظومة (`/api/v1/system/health`).
- يتم إخفاء كلمة المرور واستبدالها بنجوم في تمثيلات السلاسل النصية: `postgresql://plagiarism_app:***@10.0.1.50:5432/plagiarism_db`.
