# سجل التبعيات والمستلزمات للبيئة المعزولة (Offline Dependencies & Supply Chain Inventory)
## منظومة كاشف السرقات العلمية الأكاديمي للنصوص العربية — الإصدار v1.4.0-rc

---

## 1. مصفوفة التبعيات البرمجية وتصنيفها (Dependency Classification Matrix)

| الحزمة / المكون البرمجي | الإصدار المعتمد | التصنيف والحالة | الوظيفة والدور في المنظومة | ملاحظات العزل والأوفلاين |
| :--- | :--- | :--- | :--- | :--- |
| **Python** | 3.13.x / 3.11+ | **REQUIRED** | بيئة التشغيل الأساسية | بيئة محلية مستقلة |
| **Flask** | 3.x | **REQUIRED** | إطار عمل خوادم الويب وواجهات API | لا استدعاءات سحابية |
| **SQLAlchemy** | 2.x | **REQUIRED** | طبقة التجريد والتعامل مع قواعد البيانات | دعم SQLite و PostgreSQL محلياً |
| **bcrypt** | 4.x | **REQUIRED** | تشفير كلمات المرور (Cost = 12) | مكتبة محلية بدون شبكة |
| **pypdf / PyPDF2** | 3.x | **REQUIRED** | استخراج النصوص من ملفات PDF النصية | فحص بنيوي محلي |
| **python-docx** | 1.x | **REQUIRED** | استخراج النصوص من ملفات Word DOCX | فحص بنيوي محلي |
| **pytest** | 7.x | **REQUIRED (Dev/QA)** | إطار اختبارات الجودة والتراجع الشامل | تشغيل معزول 100% |
| **Tesseract-OCR (ara)**| 5.x | **UNAVAILABLE** | التعرف الضوئي على المستندات الممسوحة | يتطلب تثبيت `ara.traineddata` يدوياً |
| **PyTorch / Transformers**| - | **UNAVAILABLE / DISABLED**| النموذج الدلالي للترادف العميق | يتطلب توفير ملف الأوزان محلياً |
| **PostgreSQL Server** | 15.x+ | **OPTIONAL (Target)** | خادم قاعدة البيانات للبيئات الموزعة | جاهز معمارياً؛ غير مثبت محلياً |

---

## 2. استراتيجية حماية سلسلة الإمداد البرمجي (Supply Chain Security & Wheelhouse)

1. **حزم التثبيت المعزولة مسبقاً (Offline Wheelhouse):**
   - يُنصح بتجهيز مستودع حزم Python محلي مستقل (`pip wheel --wheel-dir=./wheelhouse -r requirements.txt`).
   - تثبيت كافة الحزم في البيئة الوزارية عبر الأمر المعزول:
     ```bash
     pip install --no-index --find-links=./wheelhouse -r requirements.txt
     ```
2. **تثبيت الإصدارات الصارم (Version Pinning & Hashes):**
   - كافة الحزم مثبتة بإصداراتها الدقيقة في ملف `requirements.txt` مع منع التحديث التلقائي الصامت أثناء التشغيل.
   - حظر تام لأي محاولة تنزيل ديناميكي عبر الإنترنت داخل أي وحدة برمجية (`No Runtime Auto-Downloads`).
