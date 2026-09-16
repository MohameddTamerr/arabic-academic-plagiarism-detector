# تقرير تدقيق المتطلبات النهائية

**التاريخ:** 2026-09-10  
**النطاق:** نسخة العمل الحالية في `C:\Users\user\Downloads\Baba` بما فيها التعديلات غير الملتزم بها في Git.  
**نوع العمل:** تدقيق قراءة فقط؛ لم يتم تعديل الكود أو العتبات أو المستخدمين أو البيانات، ولم يُبنَ ملف EXE.

## الخلاصة التنفيذية

النسخة الحالية **لا تحقق التصميم النهائي المطلوب**. توجد أجزاء قوية قابلة للبناء عليها، أهمها: رفع متعدد الملفات، تخزين مرحلي قبل التثبيت، SHA-256، فحص بنيوي أولي، تقارير مستقلة للأجزاء في مسار Backend جديد، وحساب مجمع موزون. لكن توجد أربعة عوائق حرجة:

1. نموذج الصلاحيات الحالي ما زال يعتمد على أدوار متعددة، والقرار الأكاديمي ممنوح لـ `REVIEWER` و`SENIOR_REVIEWER` بدل أن يكون محصورًا في `SYSTEM_ADMIN`.
2. `SYSTEM_ADMIN` لا يملك فعليًا صلاحيات `REVIEW_PRELIMINARY` أو `REVIEW_REJECT` أو `REVIEW_FINAL`، ولذلك مسارات القبول والرفض والاعتماد النهائي ترفضه، بينما تسمح للأدوار القديمة.
3. تكامل Antivirus موجود لكنه **Fail Open**: غياب المحرك أو انتهاء المهلة أو فشل التنفيذ لا يمنع تثبيت الملف في التخزين الدائم.
4. لا يوجد PDF Viewer داخلي، ولا انتقال إلى صفحة المطابقة، ولا إحداثيات/Bounding Boxes، والتلوين الحالي يغطي Segment كاملًا لا الكلمات أو الـmatched span.

**قرار الجاهزية:** `NOT READY` للتسليم وفق المتطلبات النهائية.

## النتائج الحرجة حسب الأولوية

### P0 — الأدوار والقرار النهائي: BROKEN

- الكود يعرّف: `EMPLOYEE`, `DATA_ENTRY`, `REVIEWER`, `SENIOR_REVIEWER`, `UNIT_MANAGER`, `SYSTEM_ADMIN` وأدوارًا قديمة. الدليل: `app/security/permissions.py:92-113`.
- صلاحيات القبول المبدئي والرفض ممنوحة لـ`REVIEWER`، والاعتماد النهائي لـ`SENIOR_REVIEWER`. الدليل: `app/security/permissions.py:161-210`.
- `SYSTEM_ADMIN` لديه `REVIEW_VIEW` فقط ولا يملك `REVIEW_PRELIMINARY`, `REVIEW_REJECT`, `REVIEW_FINAL`. الدليل: `app/security/permissions.py:246-290`.
- مسارات القرار نفسها محمية بهذه الصلاحيات القديمة: القبول `app/routes/report_routes.py:202-204`، الرفض `:295-297`، الاعتماد النهائي `:499-502`.
- قاعدة البيانات الحية قُرئت بوضع read-only وتحتوي حاليًا: `admin=3`, `data_entry=7`, `employee=1`, `reviewer=31`, `senior_reviewer=3`, `system_admin=18`, `unit_manager=4`. لم يُحذف أو يُعدل أي حساب.
- مسار المستخدمين الحديث يسمح للمدير بإسناد جميع هذه الأدوار، والمسار القديم `/users` يجعل `reviewer` الدور الافتراضي. الدليل: `app/routes/user_routes.py:23-47,127-173` و`app/routes/auth_routes.py:301-325`.

**الأثر:** الـBackend لا يطبق قاعدة “Admin وEmployee فقط”، وصاحب القرار الفعلي ليس الـAdmin كما هو مطلوب.

### P0 — Antivirus وFail-Closed: BROKEN

- يوجد Staging ثم SHA-256 ثم استدعاء فحص malware ثم فحص بنيوي ثم نقل ذري. الدليل: `app/services/upload_validation_service.py:83-178,547-590`.
- يوجد اكتشاف محلي لـMicrosoft Defender ثم ClamAV. الدليل: `app/services/upload_validation_service.py:197-235`.
- عند عدم وجود محرك Antivirus، تستمر العملية بلا رفض؛ لا توجد حالة `ANTIVIRUS_UNAVAILABLE` ولا سياسة مطلوبة في الإعدادات.
- عند timeout يسجل Warning ويستمر صراحةً مع الفحص البنيوي. الدليل: `app/services/upload_validation_service.py:309-312`.
- أخطاء تشغيل المحرك تُبتلع ويستمر الإدخال. كما أن exit codes غير المتوقعة لا تُعامل كـ`SCAN_FAILED`.
- لا تُحفظ حالات `ANTIVIRUS_AVAILABLE / UNAVAILABLE / SCAN_CLEAN / THREAT_FOUND / FAILED` في نموذج بيانات أو Audit دائم.
- على جهاز التدقيق الحالي: Microsoft Defender موجود ومفعّل، Real-Time Protection مفعلة، والتوقيعات محدثة في 2026-09-10؛ ClamAV غير مثبت. هذا يثبت توفر المحرك على هذا الجهاز فقط، ولا يصحح سياسة Fail Open في التطبيق.
- توثيق Microsoft يقر استخدام `MpCmdRun.exe` للأتمتة ويدعم custom scan و`-DisableRemediation`: https://learn.microsoft.com/en-us/defender-endpoint/command-line-arguments-microsoft-defender-antivirus

**الأثر:** قد يعرض النظام الملف كـvalidated ويثبته رغم أن Antivirus لم يعمل.

### P1 — معمارية الرسائل مزدوجة وغير متسقة: PARTIAL

يوجد مساران منفصلان غير موحدين:

1. واجهة المستخدم تستعمل `/api/batch/thesis`، تحفظ الأجزاء كـ`ResearchFile` ثم تدمج النص وتنتج تقريرًا واحدًا فقط. الدليل: `templates/index.html:4111-4146` و`app/routes/batch_routes.py:181-334`.
2. Backend أحدث يستعمل `/api/thesis` وكيانات `Thesis/ThesisPart`، ويدعم إضافة أجزاء وترتيبها وفصلها وتقريرًا لكل جزء وتقريرًا مجمعًا. الدليل: `app/routes/thesis_routes.py:43-562` و`app/services/thesis_service.py:34-462`.

الواجهة لا تستعمل دورة `Thesis/ThesisPart` الحديثة، لذلك ميزات الإضافة اللاحقة والتقارير لكل جزء والتقرير المجمع ليست متاحة للمستخدم النهائي. لا يوجد مسار لاستبدال ملف جزء؛ مسار update يعدل الاسم والترتيب فقط (`app/routes/thesis_routes.py:336-373`).

### P1 — ملكية بيانات الموظف: BROKEN

- `EMPLOYEE` يملك صلاحيات إنشاء/تعديل/إضافة/إزالة/فحص الرسائل (`app/security/permissions.py:119-139`).
- فحص الوصول للرسائل يعتمد على Department فقط، وإذا كان فارغًا يعتبر عامًا؛ لا يقارن `created_by_user_id` بالمستخدم. الدليل: `app/security/authorization.py:167-192,226-240`.
- قائمة الرسائل لا تُفلتر بمالك الرسالة للموظف. الدليل: `app/routes/thesis_routes.py:43-81`.

**الأثر:** موظف قد يرى أو يعدل رسالة موظف آخر، خصوصًا عند Department فارغ، رغم أن الواجهة المطلوبة هي “أبحاثي/الرسائل”.

### P1 — الاعتماد النهائي وإضافة المرجع غير ذريين ويفقدان provenance: BROKEN

- يتم تغيير حالة التقرير إلى `final_accepted` قبل التحقق من نجاح إضافة المرجع (`app/routes/report_routes.py:543-565`).
- نتيجة `import_reference_paper` لا يُفحص فيها `success` قبل تسجيل القرار الناجح.
- التقرير المجمع الحديث لا يحمل `file_path` موحدًا؛ الاعتماد يحول `segments` إلى نص واحد.
- لا تُمرر هوية الرسالة، هوية الجزء، ترتيب الجزء، hash الجزء، أو page provenance إلى المرجع النهائي.

**الأثر:** يمكن أن يصبح التقرير “معتمدًا نهائيًا” مع فشل الإضافة إلى Corpus، ورسالة متعددة الملفات لا تُحفظ كمصدر قابل للعزو إلى “الرسالة ← الجزء ← الصفحة”.

## مصفوفة الحالة المطلوبة صراحة

| البند | الحالة | الدليل/الملاحظة |
|---|---|---|
| MULTI-FILE THESIS | **PARTIAL** | رفع وترتيب أولي يعمل؛ يوجد Backend أحدث للإضافة/إعادة الترتيب/الفصل، لكنه غير مربوط بالواجهة، والاستبدال غير موجود. |
| COMBINED LOGICAL DOCUMENT | **WORKING** | `/api/batch/thesis` يرتب الملفات ثم يجمع نص الصفحات منطقيًا بالترتيب في `scan_service.py:142-208`. |
| COMBINED THESIS REPORT | **PARTIAL** | تقرير واحد موحد في المسار المرئي، وتقرير مجمع في Backend الحديث؛ لا توجد تجربة UI متكاملة، ويمكن إنشاء تقرير مجمع مع أجزاء غير مكتملة وتحذير فقط. |
| WEIGHTED COMBINED SCORE | **WORKING** | مجموع matched words ÷ مجموع total words في `app/services/thesis_service.py:223-315`؛ لا يستخدم متوسط النسب. توجد اختبارات إثبات في `tests/test_weighted_aggregation_math.py` لكنها لم تُشغل لتجنب كتابة بيانات. |
| PER-PART REPORT | **PARTIAL** | Backend الحديث يفحص كل جزء ويحفظ `report_id`؛ الواجهة المستخدمة فعليًا تنتج تقريرًا واحدًا ولا تعرض Tabs للأجزاء. |
| TEXT SPAN HIGHLIGHT | **PARTIAL** | يوجد تلوين للنص المستخرج، لكنه على مستوى Segment كامل (`templates/index.html:4739-4760`). |
| WORD/TOKEN HIGHLIGHT | **NOT IMPLEMENTED** | لا توجد offsets أو token spans أو exact phrase boundaries؛ الواجهة تلون `seg.text` كاملًا. |
| PDF VIEWER INSIDE SYSTEM | **NOT IMPLEMENTED** | لا توجد مكتبة PDF.js محلية ولا endpoint آمن لبث PDF ولا iframe/object viewer. الموجود هو Extracted Text Viewer فقط. |
| SOURCE PDF VIEWER | **NOT IMPLEMENTED** | لا يوجد فتح داخلي لملف المصدر المرجعي. |
| JUMP TO MATCHED PAGE | **NOT IMPLEMENTED** | أرقام صفحات المصدر قد تظهر كنص، لكن لا يوجد رابط/حدث يفتح Viewer على الصفحة. |
| PDF COORDINATES AVAILABLE | **NOT IMPLEMENTED** | الاستخراج يحتفظ بـ`page_number` و`text` فقط؛ لا توجد Bounding Boxes أو coordinates. |
| PDF OVERLAY HIGHLIGHT | **NOT IMPLEMENTED** | غير ممكن بالبيانات الحالية؛ المتاح فقط Highlight فوق extracted text. |
| CURRENT FILE COUNT LIMIT | **INCONSISTENT** | المسار المرئي: 50 ملفًا للرسالة (`config.py:193`, `batch_routes.py:206-210`). مسارات `/api/thesis` و`/parts` لا تفرض حد عدد كلي، ما يسمح بتجاوزه. |
| CURRENT PER-FILE SIZE LIMIT | **500 MB** | PDF/DOCX: 500MB افتراضيًا؛ TXT يخضع لاحقًا إلى 100MB. القيم عبر environment وليست إعدادات UI مؤسسية. |
| CURRENT TOTAL THESIS SIZE LIMIT | **INCONSISTENT** | 500MB في `/api/batch/thesis`، لكن يتم التحقق بعد تثبيت كل ملف؛ مسار `/api/thesis` لا يفرض إجماليًا. سقف طلب Flask العام 1GB. |
| CURRENT PDF PAGE LIMIT | **10,000 pages/PDF** | `config.py:195` و`upload_validation_service.py:347-388`؛ configurable عبر environment فقط. |
| ANTIVIRUS INTEGRATION | **PARTIAL** | استدعاء محرك محلي موجود، لكن لا حالات مهيكلة ولا ضمان تشغيل ولا Fail Closed. |
| WINDOWS DEFENDER INTEGRATION | **PARTIAL** | اكتشاف `MpCmdRun.exe` وتشغيل custom scan موجود؛ Defender متاح على جهاز التدقيق، لكن timeout/error/unavailable يسمح بالاستمرار. |
| CLAMAV SUPPORT | **PARTIAL** | اكتشاف `clamdscan`/`clamscan` وتشغيله موجود؛ غير مثبت على الجهاز الحالي، ولا إعداد صريح أو health/status. |
| UPLOAD QUARANTINE | **PARTIAL** | Staging قبل التثبيت موجود، لكنه مجلد مؤقت عادي وليس نطاق quarantine موثقًا بصلاحيات/ACL وعزل تشغيلي. |
| FAIL-CLOSED SECURITY SCAN | **BROKEN** | غياب المحرك أو timeout أو exception لا يمنع promote. |
| MALWARE SCAN AUDIT | **PARTIAL** | threat قد يسجل operational event؛ لا يوجد سجل دائم لكل محاولة بنتيجة engine/status/duration/signature version/hash، ولا تسجيل clean/unavailable/failed. |

## فحص Workflow والقرارات

| المتطلب | الحالة | الملاحظة |
|---|---|---|
| الرفع ثم الفحص الأمني ثم البنيوي ثم التثبيت | **PARTIAL** | الترتيب موجود، لكن الفحص الأمني Fail Open. |
| الاستخراج والمقارنة وإنشاء التقرير | **WORKING/PARTIAL** | موجود؛ جودة detector والعتبات خارج نطاق هذا التدقيق ولم تُغير. |
| Pending Admin Review | **PARTIAL** | التقارير تبدأ `pending_review` ويوجد submit-to-admin، لكن نموذج الأدوار القديم يحكم القرار. |
| Admin Accept/Reject/Final Accept | **BROKEN** | صلاحيات القرار ليست ممنوحة لـSYSTEM_ADMIN. |
| Employee ممنوع من القرارات عبر API | **WORKING** | EMPLOYEE لا يملك `REVIEW_*`، فيرجع decorator 403؛ لكن المنع يعتمد على مصفوفة أدوار يجب تبسيطها. |
| Similarity 0% لا يسبب قبولًا تلقائيًا | **WORKING** | لم يوجد مسار auto-accept مبني على النسبة؛ الحالة تبقى pending حتى قرار API. |
| Final Accept يضيف إلى Reference Corpus | **PARTIAL/BROKEN** | الاستدعاء موجود، لكنه غير ذري ولا يتحقق من النجاح ويفقد provenance متعدد الأجزاء. |

## فحص أمان الصيغ

### DOCX — PARTIAL

موجود: magic bytes، عدد entries، الحجم بعد الفك، compression ratio، حد لكل entry، path traversal، كشف VBA وبعض الامتدادات التنفيذية، والتحقق من بنية OpenXML الأساسية (`upload_validation_service.py:399-503`).

ناقص: تحليل وحظر external relationships فعليًا، كشف OLE/embedded packages على نحو شامل، حدود parsing للـXML نفسها، وتسجيل نتيجة أمنية مهيكلة. `DOCM` مرفوض ضمنيًا لأنه ليس في `ALLOWED_EXTENSIONS` (`config.py:183`).

### PDF — PARTIAL

موجود: signature، حظر `/Launch` في عينة أولية، رفض encrypted، فتح بنيوي، وعدد الصفحات (`upload_validation_service.py:329-396`).

ناقص: فحص شامل لـJavaScript actions وOpenAction/AA، embedded files، object count، stream/decompression bombs، recursive object limits، ونتيجة مهيكلة. البحث عن `/Launch` في أول 1MB فقط وبشرط وجود `/Action` ليس تغطية كاملة.

### SHA-256 — WORKING

يُحسب أثناء streaming قبل التثبيت ويُحفظ مع الملف (`upload_validation_service.py:120-176`). يُستخدم في كشف التكرار، لكنه ليس Antivirus.

## حدود الموارد

- القيم الافتراضية الحالية: 500MB لكل ملف، 500MB لإجمالي الرسالة في المسار المرئي، 1GB لإجمالي الطلب، 50 جزءًا للرسالة، 10,000 صفحة PDF، تزامن فحص=2، OCR=1، queue=1000 (`config.py:186-214`).
- الحدود قابلة للتعديل عبر environment فقط، وليست settings مدارة من الـAdmin كما طلبت المتطلبات.
- `resource_governor.py` يحتوي فحص 5GB مساحة حرة، لكنه غير مستدعى من مسارات الرفع؛ لذلك disk-space check غير مطبق على ingestion.
- فحص إجمالي الدفعة/الرسالة يتم بعد نقل كل ملف للتخزين النهائي، ما قد يترك ملفات مثبتة أو سجلات جزئية عند تجاوز الإجمالي.
- backpressure موجود في job queue، لكنه لا يمنع استقبال وتثبيت الرفع قبل امتلاء الطابور في كل المسارات.

## الواجهة والقوائم الجانبية

- الشريط الجانبي الحالي ليس مطابقًا حرفيًا للقائمتين النهائيتين؛ ما زالت تسميات ومراحل مثل “الفحص الأولي” و“الأبحاث المقبولة مبدئيًا” موجودة (`templates/index.html:1762-1808`).
- إخفاء عناصر admin يتم في الواجهة، لكنه يعتبر `unit_manager` إداريًا أيضًا (`templates/index.html:5495`).
- واجهة إدارة المستخدمين ما زالت تعرض أسماء الأدوار القديمة (`templates/index.html:5843-5847`).
- لا توجد صفحة “إدارة الرسائل والأطروحات” متصلة بكيانات Thesis الحديثة، ولا “أبحاثي/الرسائل” مفلترة بالملكية.
- لا توجد حالات رفع مرئية منفصلة: “جارٍ الفحص الأمني / جارٍ التحقق / جاهز / مرفوض كملف غير آمن”.

## Reference Corpus

**الحالة: PARTIAL**

- إضافة/بحث/Retire/Re-activate/Re-index موجودة ومحمية بصلاحيات مرجعية (`app/routes/paper_routes.py:62-328`).
- إضافة المرجع تمر بخدمة validation نفسها، وبالتالي تستفيد من Staging وSHA-256 والفحص البنيوي، لكنها ترث Fail Open للـAntivirus.
- لا يوجد PDF Viewer داخلي للمراجع.
- `EMPLOYEE` يملك `REFERENCE_VIEW` حاليًا؛ الواجهة تخفي الإدارة لكن API يسمح بعرض قائمة المراجع. يلزم حسم هل هذا العرض ضروري للتقرير فقط أم يخالف عدم إظهار قاعدة المراجع الإدارية.
- Final Accept للرسالة لا يحفظ thesis/part/page provenance المطلوب.

## عناصر يجب الحفاظ عليها أثناء الإصلاح اللاحق

- عدم حذف الأدوار أو الحسابات القديمة مباشرة. يلزم migration موثق مع mapping ونسخة احتياطية وتقرير أثر قبل أي تغيير.
- الحفاظ على `Thesis/ThesisPart` كالمسار المرجح، وتوحيد الواجهة و`/api/batch/thesis` حوله بدل استمرار نموذجين.
- الحفاظ على الحساب الموزون القائم على عدد الكلمات وعدم استبداله بمتوسط نسب الأجزاء.
- الحفاظ على SHA-256، staging، الفحص البنيوي، وعزو `part_id/part_title` الموجود في التقرير المجمع، مع استكمال page provenance.

## ترتيب الإصلاح المقترح للمرحلة التالية (لم يُنفذ)

1. Migration آمن إلى دورين فقط، ومنح كل قرارات المراجعة لـSYSTEM_ADMIN وسحبها من غيره، مع اختبارات 403/200 صريحة.
2. جعل Antivirus Fail Closed مع حالات مهيكلة وAudit دائم وhealth endpoint واختبارات unavailable/timeout/error/threat/clean.
3. توحيد معمارية الرسالة وربط UI بكيانات Thesis الحديثة، وإضافة replacement وownership checks وحدود كلية قابلة للإدارة.
4. جعل Final Accept transaction/outbox موثوقًا ويحفظ هوية الرسالة والجزء والصفحة والهاش في Corpus.
5. إضافة PDF.js محلي بالكامل مع endpoint تفويض وبث آمن، ثم jump-to-page؛ وإضافة overlays فقط بعد حفظ bounding boxes.
6. تطوير detector/report schema ليحفظ matched spans/token offsets بدل تلوين Segment كامل.

## حدود هذا التدقيق

- لم تُشغل الاختبارات لأن عددًا منها يكتب في قواعد البيانات/المجلدات التجريبية، والمتطلب صريح بعدم تغيير البيانات في مرحلة الـAudit.
- لم يُنفذ فحص Antivirus على ملف عينة؛ تم فقط فحص توفر Defender وحالته read-only.
- لم تُراجع دقة detector أو thresholds ولم تُغير، التزامًا بالنطاق.

**STOP:** هذا التقرير هو ناتج مرحلة الـAudit فقط، ولم يبدأ أي تنفيذ للإصلاحات.
