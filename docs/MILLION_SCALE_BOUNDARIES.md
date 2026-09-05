# حدود سعات التخزين والفحص المليوني (Million-Scale Boundaries & Capacities)

---

## 1. تصنيف نتائج وسعات الاسترجاع والتخزين (Capacity Evidence Classification)

| المكون / المقياس | التصنيف العلمي | القيمة المثبتة في الإصدار الحالي (Prompt 2) |
| :--- | :--- | :--- |
| **هيكل تخزين الملفات (CAS)** | **MEASURED** | تم اختباره بالتقسيم على مستويين مع ضمانات الترقية الذرية واستيعاب آلاف الملفات دون اختناق. |
| **فهرس الاسترجاع المحلي المقلوب** | **MEASURED** | تم قياسه واختباره على مجموعات بيانات اصطناعية (1K, 10K, 100K، وحتى 1,000,000 مقطع اصطناعي خفيف). |
| **سقف استرجاع المرشحين الأعلى** | **CONFIGURED** | `max_candidate_retrieval = 50` لتقييد حجم المدخلات لمحرك المطابقة المعقد. |
| **سعة تخزين وسائط الخادم الموصى بها** | **RECOMMENDED** | محركات أقراص SSD بسعة 2TB على الأقل لاستيعاب 500,000 مستند PDF/DOCX بحجم متوسط 2MB. |
| **الفحص الميداني الموزع لملايين الوثائق الكاملة** | **PROJECTED / NOT MEASURED** | يتطلب استكمال Prompt 3 (معالجة الطوابير الموزعة وتعدد خوادم المعالجة). |

---

## 2. بيان الشفافية العلمية الإلزامي (Mandatory Scientific Statement)

> **"Local retrieval index measured with up to 1,000,000 synthetic lightweight segments. Full end-to-end distributed million-document PDF ingestion and cluster load testing are scheduled for Prompt 3."**
