# -*- coding: utf-8 -*-
"""
Scientific Calibration and Held-Out Validation for Semantic Paraphrase Detection
================================================================================
Implements Phase 2:
1. Load and verify local Multilingual E5 Small ONNX INT8 model.
2. Evaluate embedding cosine similarities with 'query: ' and 'passage: ' prefixes.
3. Separate Development Set (N=20: 10 genuine paraphrases, 10 within-domain negatives) for threshold calibration.
4. Held-Out Test Set (N=20: 10 unseen paraphrases, 10 unseen within-domain negatives) for final evaluation.
5. Compute Precision, Recall, F1, FPR, FNR, Specificity with Wilson 95% Confidence Intervals.
6. CPU latency and memory benchmarking.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any, Dict, List, Tuple
import numpy as np
import psutil

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
sys.path.insert(0, str(ROOT / 'vendor'))

import config
from plagiarism_detector.detection.semantic_matcher import (
    compute_embeddings, check_semantic_model_availability, get_embedder
)
from plagiarism_detector.detection.evidence_gate import accept_semantic_paraphrase

# ---------------------------------------------------------------------------
# Wilson Score Confidence Interval
# ---------------------------------------------------------------------------
def wilson_score_interval(successes: int, total: int, confidence: float = 0.95) -> Tuple[float, float]:
    """Calculate the Wilson score 95% confidence interval for a proportion."""
    if total <= 0:
        return 0.0, 0.0
    z = 1.95996
    p_hat = successes / total
    denom = 1.0 + (z ** 2) / total
    centre = p_hat + (z ** 2) / (2.0 * total)
    margin = z * math.sqrt((p_hat * (1.0 - p_hat) + (z ** 2) / (4.0 * total)) / total)
    lower = max(0.0, (centre - margin) / denom)
    upper = min(1.0, (centre + margin) / denom)
    return round(lower, 4), round(upper, 4)


# ---------------------------------------------------------------------------
# Development Set (Calibration / Tuning) - N = 20
# ---------------------------------------------------------------------------
DEV_PARAPHRASES = [
    ("يتطلب القصد الجنائي العام في الجرائم العمدية إدراك الجاني لماديات الجريمة وتوجيه إرادته الحرة نحو إحداث النتيجة المعاقب عليها قانونا.",
     "يقوم الركن المعنوي للجريمة العمدية على عنصري العلم والإرادة بحيث يحيط الفاعل بوقائع الفعل غير المشروع وتتجه مشيئته الواعية إلى تحقيق آثاره الإجرامية.", "Law"),
    ("تنشأ مقاومة الأنسولين المحيطية في داء السكري النمط الثاني نتيجة خلل في مسارات الإشارات الخلوية مما يعيق التقاط الغلوكوز في الأنسجة العضلية والدهنية.",
     "يؤدي تراجع حساسية الخلايا المستهدفة للأنسولين إلى انخفاض امتصاص السكر في العضلات الهيكلية والأنسجة الشحمية مسببا ارتفاعا مزمنا في مستويات الغلوكوز بالدم.", "Medicine"),
    ("تهدف خوارزميات التوافق الموزع كخوارزمية رافت إلى ضمان اتساق سجلات العمليات بين العقد المستقلة حتى في حالات تعطل بعض الخوادم أو بطء قنوات الاتصال.",
     "تسعى بروتوكولات الإجماع في البيئات الموزعة إلى توحيد حالات السجلات عبر أجهزة الشبكة المتعددة مع توفير قدرة عالية على تحمل إخفاقات العقد الفردية.", "Computer Science"),
    ("يترتب على عمليات تحلية مياه البحر تفريغ محاليل ملحية عالية التركيز في البيئة الساحلية مما يهدد التنوع الحيوي البحري ويخفض مستويات الأكسجين المذاب.",
     "يؤثر تصريف المياه المرتجعة شديدة الملوحة من محطات التحلية سلبا على النظم الإيكولوجية الشاطئية مؤديا إلى اضطراب توازن الكائنات البحرية ونقص الأكسجين في الأعماق.", "Environmental Eng"),
    ("اعتمدت الدولة العباسية في عصرها الأول على البيروقراطية الفارسية في تنظيم الدواوين المالية واستحداث ديوان البريد لمراقبة عمال الأقاليم.",
     "استفادت الإدارة العباسية المبكرة من الخبرات الإدارية الساسانية في هيكلة الدوائر الحكومية وتطوير شبكات نقل الأخبار لمتابعة أداء الولاة في الولايات المتباعدة.", "History"),
    ("يلجأ البنك المركزي إلى التيسير الكمي عبر شراء السندات الحكومية طويلة الأجل لضخ السيولة في القطاع المصرفي وخفض تكلفة الاقتراض لتحفيز الاستثمار.",
     "تقوم السلطات النقدية بشراء الأوراق المالية السيادية من الأسواق المالية بهدف زيادة المعروض النقدي وتشجيع الائتمان التجاري لإنعاش النشاط الاقتصادي الراكد.", "Economics"),
    ("يركز التقويم التكويني المستمر على رصد الفجوات التعليمية لدى الطلاب أثناء الموقف التدريسي وتقديم تغذية راجعة فورية لتعديل استراتيجيات التعلم.",
     "يهدف التقييم البنائي المرحلي إلى تشخيص صعوبات الاستيعاب لدى المتعلمين وتزويدهم بتوجيهات تصحيحية آنية لتحسين نواتج العملية التعليمية.", "Education"),
    ("يخضع الدواء بعد امتصاصه في الجهاز الهضمي إلى عمليات استقلاب كبدي أولية تؤثر بشكل مباشر على توافره الحيوي وتركيزه الفعال في البلازما.",
     "تتعرض العقاقير الفموية لتأثير المرور الكبدي الأول الذي يحول جزءا من المادة الفعالة إلى نواتج أيضية مما يقلل من النسبة الواصلة إلى الدورة الدموية العامة.", "Pharmacology"),
    ("تستند القوة الناعمة للدول إلى جاذبية النموذج الثقافي والقيم السياسية والدبلوماسية العامة بدلا من استخدام الإكراه العسكري أو الضغوط الاقتصادية.",
     "تتحقق القدرة على التأثير في سلوك الفاعلين الدوليين عبر نشر الثقافة الوطنية والمصداقية السياسية والمعونات التنموية بعيدا عن أدوات الإلزام الصلبة.", "Political Science"),
    ("يؤدي تغلغل أيونات الكلوريد في الخرسانة المسلحة إلى تآكل حديد التسليح وتصدع الغطاء الخرساني الخارجي مما يقصر العمر الافتراضي للمنشآت البحرية.",
     "يتسبب نفاذ أملاح الكلوريدات عبر مسامات الخرسانة في صدأ قضبان الصلب وتفكك الطبقة الحامية مهددا السلامة الهيكلية للمباني المقامة قرب الشواطئ.", "Civil Engineering"),
]

DEV_NEGATIVES = [
    ("يتطلب القصد الجنائي العام في الجرائم العمدية إدراك الجاني لماديات الجريمة وتوجيه إرادته الحرة نحو إحداث النتيجة المعاقب عليها قانونا.",
     "يشترط المشرع في عقد التأمين التزام المؤمن له بتقديم إقرارات صحيحة حول طبيعة الخطر المؤمن منه وسداد الأقساط الدورية في المواعيد المحددة.", "Law"),
    ("تنشأ مقاومة الأنسولين المحيطية في داء السكري النمط الثاني نتيجة خلل في مسارات الإشارات الخلوية مما يعيق التقاط الغلوكوز في الأنسجة العضلية والدهنية.",
     "تتضمن معايير تشخيص التهاب المفاصل الروماتويدي وجود تورم متناظر في المفاصل الصغيرة لليدين وتيبس صباحي يتجاوز الساعة مع إيجابية العامل الروماتويدي.", "Medicine"),
    ("تهدف خوارزميات التوافق الموزع كخوارزمية رافت إلى ضمان اتساق سجلات العمليات بين العقد المستقلة حتى في حالات تعطل بعض الخوادم أو بطء قنوات الاتصال.",
     "تستخدم الشبكات العصبية الالتفافية طبقات الترشيح والتجميع لاستخراج السمات المكانية الدقيقة من الصور الرقمية بهدف تصنيف الكائنات بدقة عالية.", "Computer Science"),
    ("يترتب على عمليات تحلية مياه البحر تفريغ محاليل ملحية عالية التركيز في البيئة الساحلية مما يهدد التنوع الحيوي البحري ويخفض مستويات الأكسجين المذاب.",
     "يعتمد توليد الطاقة الكهروضوئية على استخدام ألواح السيليكون لتحويل الإشعاع الشمسي المباشر إلى تيار كهربائي مستمر دون انبعاثات غازية ضارة.", "Environmental Eng"),
    ("اعتمدت الدولة العباسية في عصرها الأول على البيروقراطية الفارسية في تنظيم الدواوين المالية واستحداث ديوان البريد لمراقبة عمال الأقاليم.",
     "شهدت الأندلس في عهد عبد الرحمن الناصر نهضة عمرانية واسعة تمثلت في بناء مدينة الزهراء وتوسعة جامع قرطبة وإنشاء مراكز الترجمة والعلوم.", "History"),
    ("يلجأ البنك المركزي إلى التيسير الكمي عبر شراء السندات الحكومية طويلة الأجل لضخ السيولة في القطاع المصرفي وخفض تكلفة الاقتراض لتحفيز الاستثمار.",
     "توضح نظرية التجارة الدولية الحديثة كيف تستفيد الدول من التخصص في إنتاج السلع التي تمتلك فيها ميزة نسبية وفرة في عناصر الإنتاج المتاحة محليا.", "Economics"),
    ("يركز التقويم التكويني المستمر على رصد الفجوات التعليمية لدى الطلاب أثناء الموقف التدريسي وتقديم تغذية راجعة فورية لتعديل استراتيجيات التعلم.",
     "تعتمد الإدارة المدرسية الفعالة على التخطيط الاستراتيجي السنوي وإشراك أولياء الأمور في مجالس الأمناء لتطوير البيئة المدرسية وتعزيز الانضباط السلوكي.", "Education"),
    ("يخضع الدواء بعد امتصاصه في الجهاز الهضمي إلى عمليات استقلاب كبدي أولية تؤثر بشكل مباشر على توافره الحيوي وتركيزه الفعال في البلازما.",
     "تستهدف المضادات الحيوية من فئة البنسلينات تثبيط بناء جدار الخلية البكتيرية عبر الارتباط بالبروتينات الرابطة للبنسلين مما يؤدي إلى تحلل البكتيريا.", "Pharmacology"),
    ("تستند القوة الناعمة للدول إلى جاذبية النموذج الثقافي والقيم السياسية والدبلوماسية العامة بدلا من استخدام الإكراه العسكري أو الضغوط الاقتصادية.",
     "يحدد دستور الدولة صلاحيات السلطة التشريعية في سن القوانين ومراقبة أعمال الحكومة والمصادقة على المعاهدات الدولية وإقرار الموازنة العامة.", "Political Science"),
    ("يؤدي تغلغل أيونات الكلوريد في الخرسانة المسلحة إلى تآكل حديد التسليح وتصدع الغطاء الخرساني الخارجي مما يقصر العمر الافتراضي للمنشآت البحرية.",
     "تتطلب أعمال الحفر العميق للمباني الشاهقة دراسة شاملة لميكانيكا التربة وتحديد منسوب المياه الجوفية لتصميم الجدران الاستنادية المناسبة.", "Civil Engineering"),
]


# ---------------------------------------------------------------------------
# Held-Out Test Set (Final Independent Evaluation) - N = 20
# ---------------------------------------------------------------------------
TEST_PARAPHRASES = [
    ("يحدث فرط التخصيص في الشبكات العصبية العميقة عندما تحفظ النماذج ضوضاء بيانات التدريب بدلا من تعلم الأنماط العامة مما يؤدي إلى ضعف قدرتها على التعميم.",
     "تعاني نماذج التعلم العميق من ظاهرة فرط المطابقة حين تستوعب تفاصيل عينة التدريب بدقة مفرطة فتفقد مرونتها في معالجة البيانات غير المرئية مسبقا.", "AI"),
    ("تستخدم المؤسسات المالية عقود الخيارات والمستقبليات للتحوط ضد تقلبات أسعار الصرف والفائدة وحماية محافظها الاستثمارية من الخسائر المفاجئة.",
     "تلجأ البنوك الاستثمارية إلى المشتقات المالية بهدف إدارة المخاطر وتثبيت هوامش الربح في ظل عدم استقرار أسواق العملات وتغير كلفة التمويل.", "Finance"),
    ("تؤدي الهجرة المتسارعة من الريف إلى المدن إلى ضغوط متزايدة على شبكات المرافق العامة وارتفاع معدلات البطالة وظهور الأحياء العشوائية غير المخططة.",
     "ينجم عن النزوح السكاني نحو المراكز الحضرية استنزاف البنية التحتية للمدن وتنامي ظاهرة السكن الهامشي مع عجز سوق العمل عن استيعاب الوافدين الجدد.", "Sociology"),
    ("يسهم استخدام المواد النانوية كالبيروفسكايت في رفع كفاءة تحويل الطاقة الشمسية إلى كهرباء مع خفض تكاليف تصنيع الخلايا الكهروضوئية الحديثة.",
     "تتيح الهياكل البلورية النانوية مثل مركبات البيروفسكايت امتصاصا أوسع للطيف الضوئي مما يعزز المردود الطاقي للخلايا الشمسية بأسعار إنتاجية منافسة.", "Materials Science"),
    ("يجوز للمحكمة المختصة بناء على طلب الخصم إصدار أوامر تحفظية عاجلة لمنع تهريب أموال المدين أو الحفاظ على الأدلة المهددة بالضياع قبل الفصل في الدعوى.",
     "يخول القانون للقاضي اتخاذ تدابير وقتية استباقية كالحجز التحفظي متى خشي الدائن ضياع حقوقه أو تبديد الضمان العام للديون أثناء سير النزاع القضائي.", "Law"),
    ("يعمل العلاج المناعي الحديث على تدريب الخلايا التائية في الجهاز المناعي للتعرف على المستقبلات الخاصة بالخلايا السرطانية ومهاجمتها بدقة متناهية دون الإضرار بالأنسجة السليمة.",
     "ترتكز الاستراتيجيات العلاجية البيولوجية على تحفيز دفاعات الجسم الطبيعية وتوجيه الخلايا اللمفاوية لاستهداف بروتينات الأورام الخبيثة بانتقائية عالية تتجنب تسمم الخلايا الطبيعية.", "Oncology"),
    ("توظف الزراعة الدقيقة أجهزة الاستشعار عن بعد ونظم المعلومات الجغرافية لتحديد الاحتياجات الفعلية للمحاصيل من المياه والأسمدة وتقليل الهدر الزراعي.",
     "تعتمد التقنيات الزراعية الذكية على بيانات الأقمار الصناعية ومجسات التربة لترشيد الري وتسميد الحقول بمقادير مدروسة تعظم الإنتاجية وتحمي البيئة.", "Agriculture"),
    ("تصف نظرية التنافر المعرفي حالة التوتر النفسي التي يعيشها الفرد عندما يحمل معتقدات متعارضة أو عندما يسلك سلوكا يتناقض مع قيمه ومبادئه الراسخة.",
     "يشعر الإنسان باضطراب وجداني حين يصطدم تصرفه مع قناعاته الفكرية مما يدفعه إلى تبرير موقفه أو تعديل أفكاره لإعادة التوازن المعرفي الداخلي.", "Psychology"),
    ("تعتمد مقاييس التقييم الآلي للترجمة مثل مقياس بلو على احتساب نسبة التطابق في متتاليات الكلمات بين المخرجات المترجمة وترجمات المترجمين البشريين المرجعية.",
     "تقيس أدوات الحكم الموضوعي على أنظمة الترجمة الآلية كمعيار بلو درجة التشابه الإحصائي بين النصوص المولدة حاسوبيا والنصوص المكتوبة بواسطة خبراء اللغة.", "Linguistics"),
    ("يستخدم قياس اضمحلال نظير الكربون المشع أربعة عشر لتحديد العمر التقريبي للبقايا العضوية القديمة مثل العظام والأخشاب الأثرية بدقة علمية مقبولة.",
     "يعتمد العلماء على تتبع انحلال ذرات الكربون المشع في العينات التاريخية البيولوجية لحساب الفترة الزمنية المنقضية منذ وفاة الكائن الحي بدقة موثقة.", "Archaeology"),
]

TEST_NEGATIVES = [
    ("يحدث فرط التخصيص في الشبكات العصبية العميقة عندما تحفظ النماذج ضوضاء بيانات التدريب بدلا من تعلم الأنماط العامة مما يؤدي إلى ضعف قدرتها على التعميم.",
     "تستخدم نظم معالجة اللغات الطبيعية نماذج المحولات لفهم العلاقات التركيبية والدلالية بين الكلمات عبر آليات الانتباه الذاتي المتعددة.", "AI"),
    ("تستخدم المؤسسات المالية عقود الخيارات والمستقبليات للتحوط ضد تقلبات أسعار الصرف والفائدة وحماية محافظها الاستثمارية من الخسائر المفاجئة.",
     "يحدد التحليل الفني لأسواق الأسهم مستويات الدعم والمقاومة من خلال قراءة حركة الرسوم البيانية وأحجام التداول لتوقع اتجاهات الأسعار المستقبلية.", "Finance"),
    ("تؤدي الهجرة المتسارعة من الريف إلى المدن إلى ضغوط متزايدة على شبكات المرافق العامة وارتفاع معدلات البطالة وظهور الأحياء العشوائية غير المخططة.",
     "تدرس نظرية التنشئة الاجتماعية كيفية اكتساب الأفراد للأدوار المجتمعية والقيم الأخلاقية عبر مؤسسات الأسرة والمدرسة ووسائل الإعلام الجماهيرية.", "Sociology"),
    ("يسهم استخدام المواد النانوية كالبيروفسكايت في رفع كفاءة تحويل الطاقة الشمسية إلى كهرباء مع خفض تكاليف تصنيع الخلايا الكهروضوئية الحديثة.",
     "تتميز المواد المركبة المصنوعة من ألياف الكربون بصلابة ميكانيكية فائقة وخفة وزن تجعلها مثالية لصناعة هياكل الطائرات وسيارات السباق.", "Materials Science"),
    ("يجوز للمحكمة المختصة بناء على طلب الخصم إصدار أوامر تحفظية عاجلة لمنع تهريب أموال المدين أو الحفاظ على الأدلة المهددة بالضياع قبل الفصل في الدعوى.",
     "يعد حق الملكية الفكرية من الحقوق المعنوية المقررة للمؤلف على مصنفه الأدبي أو الفني ويمنحه سلطة منع أي استغلال تجاري غير مصرح به.", "Law"),
    ("يعمل العلاج المناعي الحديث على تدريب الخلايا التائية في الجهاز المناعي للتعرف على المستقبلات الخاصة بالخلايا السرطانية ومهاجمتها بدقة متناهية دون الإضرار بالأنسجة السليمة.",
     "تعتمد الوقاية من أمراض الشرايين التاجية على مراقبة ضغط الدم الشرياني وخفض كوليسترول البروتين الدهني منخفض الكثافة وممارسة الرياضة الهوائية بانتظام.", "Oncology"),
    ("توظف الزراعة الدقيقة أجهزة الاستشعار عن بعد ونظم المعلومات الجغرافية لتحديد الاحتياجات الفعلية للمحاصيل من المياه والأسمدة وتقليل الهدر الزراعي.",
     "تعتبر تربية النحل في المزارع وسيلة حيوية لتحسين تلقيح المحاصيل الحقلية وزيادة عقد الثمار بالإضافة إلى إنتاج العسل والغذاء الملكي.", "Agriculture"),
    ("تصف نظرية التنافر المعرفي حالة التوتر النفسي التي يعيشها الفرد عندما يحمل معتقدات متعارضة أو عندما يسلك سلوكا يتناقض مع قيمه ومبادئه الراسخة.",
     "يركز العلاج السلوكي المعرفي على تعديل أنماط التفكير المشوهة والمعتقدات التلقائية السلبية لمساعدة المرضى على تجاوز اضطرابات القلق والاكتئاب.", "Psychology"),
    ("تعتمد مقاييس التقييم الآلي للترجمة مثل مقياس بلو على احتساب نسبة التطابق في متتاليات الكلمات بين المخرجات المترجمة وترجمات المترجمين البشريين المرجعية.",
     "تدرس الصوتيات الفيزيائية الخصائص الموجية لأصوات الكلام البشري كالتردد والشدة والرنين باستخدام أجهزة التحليل الطيفي للموجات الصوتية.", "Linguistics"),
    ("يستخدم قياس اضمحلال نظير الكربون المشع أربعة عشر لتحديد العمر التقريبي للبقايا العضوية القديمة مثل العظام والأخشاب الأثرية بدقة علمية مقبولة.",
     "تكشف التنقيبات الأثرية في وادي النيل عن تقنيات بناء الأهرامات وتطور فنون التحنيط والطقوس الجنائزية التي ميزت الحضارة المصرية القديمة.", "Archaeology"),
]


def score_pairs(pairs: List[Tuple[str, str, str]]) -> List[Dict[str, Any]]:
    queries = [p[0] for p in pairs]
    passages = [p[1] for p in pairs]
    disciplines = [p[2] for p in pairs]

    emb_q = compute_embeddings(queries, role='query')
    emb_p = compute_embeddings(passages, role='passage')

    results = []
    for i in range(len(pairs)):
        cos_sim = float(np.dot(emb_q[i], emb_p[i]))
        results.append({
            'query': queries[i],
            'passage': passages[i],
            'discipline': disciplines[i],
            'cosine_similarity': round(cos_sim, 4),
        })
    return results


def evaluate_threshold(pos_scores: List[float], neg_scores: List[float], threshold: float) -> Dict[str, Any]:
    tp = sum(1 for s in pos_scores if s >= threshold)
    fn = sum(1 for s in pos_scores if s < threshold)
    fp = sum(1 for s in neg_scores if s >= threshold)
    tn = sum(1 for s in neg_scores if s < threshold)

    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    fnr = fn / (fn + tp) if (fn + tp) > 0 else 0.0
    spec = tn / (tn + fp) if (tn + fp) > 0 else 0.0

    return {
        'threshold': round(threshold, 3),
        'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
        'precision': round(prec, 4),
        'recall': round(rec, 4),
        'f1_score': round(f1, 4),
        'fpr': round(fpr, 4),
        'fnr': round(fnr, 4),
        'specificity': round(spec, 4),
        'precision_95ci': wilson_score_interval(tp, tp + fp),
        'recall_95ci': wilson_score_interval(tp, tp + fn),
        'fpr_95ci': wilson_score_interval(fp, fp + tn),
    }


def main():
    print("=" * 80)
    print("SCIENTIFIC EVALUATION: MULTILINGUAL E5 SMALL ONNX INT8 FOR ARABIC PARAPHRASE")
    print("=" * 80)

    # 1. Check availability
    avail = check_semantic_model_availability()
    print(f"\n[1] Semantic Model Availability:\n  Status: {avail['available']}\n  Backend: {avail.get('backend')}\n  Path: {avail.get('reason')}")
    if not avail['available']:
        print("ERROR: Semantic model not available.")
        sys.exit(1)

    # Measure memory and warm-up latency
    process = psutil.Process()
    ram_init = process.memory_info().rss / (1024 * 1024)

    t0 = time.perf_counter()
    embedder = get_embedder()
    t_load_ms = (time.perf_counter() - t0) * 1000
    ram_loaded = process.memory_info().rss / (1024 * 1024)

    # Warm-up inference
    compute_embeddings(["اختبار"], role='query')
    ram_active = process.memory_info().rss / (1024 * 1024)

    print(f"\n[2] Resource Profile:\n  Cold Load Time: {t_load_ms:.2f} ms\n  Base RAM: {ram_init:.2f} MB | Loaded RAM: {ram_loaded:.2f} MB | Active RAM: {ram_active:.2f} MB\n  Net Model RAM: {ram_active - ram_init:.2f} MB")

    # 2. Score Development Set
    print("\n[3] Scoring Development Set (Calibration)...")
    dev_pos_results = score_pairs(DEV_PARAPHRASES)
    dev_neg_results = score_pairs(DEV_NEGATIVES)

    dev_pos_sims = [r['cosine_similarity'] for r in dev_pos_results]
    dev_neg_sims = [r['cosine_similarity'] for r in dev_neg_results]

    print(f"  Dev Paraphrases (N=10): min={min(dev_pos_sims):.4f}, mean={np.mean(dev_pos_sims):.4f}, max={max(dev_pos_sims):.4f}")
    print(f"  Dev Negatives   (N=10): min={min(dev_neg_sims):.4f}, mean={np.mean(dev_neg_sims):.4f}, max={max(dev_neg_sims):.4f}")

    # Threshold sweep on Dev set
    print("\n  Threshold Sweep on Development Set:")
    best_thresh = 0.84
    best_f1 = -1.0
    sweep_results = []
    for th in np.arange(0.80, 0.92, 0.01):
        res_th = evaluate_threshold(dev_pos_sims, dev_neg_sims, th)
        sweep_results.append(res_th)
        # Select highest F1 with 0 false positives on difficult negatives
        if res_th['fpr'] == 0.0 and res_th['f1_score'] > best_f1:
            best_f1 = res_th['f1_score']
            best_thresh = res_th['threshold']
        print(f"    Th={th:.2f} | TP={res_th['tp']}, FP={res_th['fp']}, FN={res_th['fn']}, TN={res_th['tn']} | P={res_th['precision']:.3f}, R={res_th['recall']:.3f}, F1={res_th['f1_score']:.4f}, FPR={res_th['fpr']:.3f}")

    print(f"\n  >> Calibrated Optimal Threshold: tau = {best_thresh:.2f} (Dev F1 = {best_f1:.4f}, Dev FPR = 0.00%)")

    # 3. Score Held-Out Test Set (Unseen)
    print("\n[4] Evaluating on Held-Out Test Set (Held-Out, N=20)...")
    t_eval_start = time.perf_counter()
    test_pos_results = score_pairs(TEST_PARAPHRASES)
    test_neg_results = score_pairs(TEST_NEGATIVES)
    t_eval_total = (time.perf_counter() - t_eval_start) * 1000

    test_pos_sims = [r['cosine_similarity'] for r in test_pos_results]
    test_neg_sims = [r['cosine_similarity'] for r in test_neg_results]

    test_eval_metrics = evaluate_threshold(test_pos_sims, test_neg_sims, best_thresh)
    avg_pair_latency_ms = t_eval_total / 20.0

    print(f"  Test Paraphrases (N=10): min={min(test_pos_sims):.4f}, mean={np.mean(test_pos_sims):.4f}, max={max(test_pos_sims):.4f}")
    print(f"  Test Negatives   (N=10): min={min(test_neg_sims):.4f}, mean={np.mean(test_neg_sims):.4f}, max={max(test_neg_sims):.4f}")

    print("\n" + "=" * 80)
    print("FINAL HELD-OUT TEST RESULTS (NO PARAMETER RETUNING)")
    print("=" * 80)
    print(f"Evaluated with Calibrated Threshold: tau = {best_thresh:.2f}")
    print(f"  True Positives (Detected Paraphrases):      {test_eval_metrics['tp']} / 10")
    print(f"  False Positives (False Alarms on Innocents): {test_eval_metrics['fp']} / 10")
    print(f"  True Negatives (Clean Innocent Negatives):   {test_eval_metrics['tn']} / 10")
    print(f"  False Negatives (Missed Paraphrases):        {test_eval_metrics['fn']} / 10")
    print(f"  Precision:   {test_eval_metrics['precision']*100:.2f}% (95% CI: {test_eval_metrics['precision_95ci']})")
    print(f"  Recall:      {test_eval_metrics['recall']*100:.2f}% (95% CI: {test_eval_metrics['recall_95ci']})")
    print(f"  F1-Score:    {test_eval_metrics['f1_score']:.4f}")
    print(f"  Specificity: {test_eval_metrics['specificity']*100:.2f}%")
    print(f"  False Positive Rate (FPR): {test_eval_metrics['fpr']*100:.2f}% (95% CI: {test_eval_metrics['fpr_95ci']})")
    print(f"  False Negative Rate (FNR): {test_eval_metrics['fnr']*100:.2f}%")
    print(f"  Inference Latency:         {avg_pair_latency_ms:.2f} ms/pair (sequential CPU)")
    print(f"  Peak Model Memory:         {ram_active - ram_init:.2f} MB")

    # Save artifact report
    output_path = ROOT / 'docs' / 'SEMANTIC_PARAPHRASE_BENCHMARK_REPORT.json'
    payload = {
        'model_name': 'intfloat/multilingual-e5-small',
        'quantization': 'INT8 ONNX Generic',
        'calibrated_threshold': best_thresh,
        'resource_usage': {
            'load_time_ms': round(t_load_ms, 2),
            'pair_latency_ms': round(avg_pair_latency_ms, 2),
            'net_ram_mb': round(ram_active - ram_init, 2),
            'total_process_ram_mb': round(ram_active, 2),
        },
        'development_calibration': {
            'samples': len(DEV_PARAPHRASES) + len(DEV_NEGATIVES),
            'sweep': sweep_results,
            'pos_similarities': dev_pos_sims,
            'neg_similarities': dev_neg_sims,
        },
        'held_out_test_evaluation': {
            'samples': len(TEST_PARAPHRASES) + len(TEST_NEGATIVES),
            'metrics': test_eval_metrics,
            'detailed_positives': test_pos_results,
            'detailed_negatives': test_neg_results,
        }
    }
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"\nArtifact saved to: {output_path}")


if __name__ == '__main__':
    main()
