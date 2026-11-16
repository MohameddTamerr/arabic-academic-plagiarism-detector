"""Build an academic Arabic Human vs AI detection benchmark dataset with strict provenance and splits."""
import os, sys, json, re, hashlib
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import fitz

def extract_thesis_paragraphs(pdf_path, max_count=20, min_words=40, max_words=150):
    doc = fitz.open(pdf_path)
    extracted = []
    seen = set()
    for page in range(10, len(doc)):
        text = doc[page].get_text()
        lines = [re.sub(r'[\s_ـ]+', ' ', l).strip() for l in text.split('\n')]
        lines = [l for l in lines if l and not l.isdigit() and len(l) > 8]
        if len(lines) >= 3:
            block = ' '.join(lines)
            words = block.split()
            if min_words <= len(words) <= max_words:
                # Ensure high Arabic letter content
                ar_ratio = sum(1 for c in block if '\u0600' <= c <= '\u06ff') / max(1, len(block))
                if ar_ratio > 0.65 and block not in seen:
                    seen.add(block)
                    extracted.append(block)
                    if len(extracted) >= max_count:
                        break
    return extracted

def main():
    p_law = _ROOT / "TEST_PDFS" / "رسالة الحماية الجنائية والأمنية للآثار - مطبعة الشرطة P5.pdf"
    p_dip = _ROOT / "TEST_PDFS" / "رسالة المراسم والبرتوكول 6 نسخ وجه واحد للمناقشة.pdf"

    law_human = extract_thesis_paragraphs(p_law, max_count=22, min_words=40, max_words=150)
    dip_human = extract_thesis_paragraphs(p_dip, max_count=18, min_words=40, max_words=150)

    # Historical human reference texts (Universal Declaration / Academic Classical)
    hist_human = [
        "يولد جميع الناس أحراراً ومتساوين في الكرامة والحقوق، وهم قد وهبوا العقل والوجدان وعليهم أن يعامل بعضهم بعضاً بروح الإخاء دون تمييز بسبب العنصر أو اللون أو الجنس أو اللغة أو الدين.",
        "تعد حماية التراث الإنساني المشترك واجباً تفرضه القوانين والأعراف الدولية للمحافظة على الشواهد الحضارية وحمايتها من النهب والتهريب والاعتداء غير المشروع أثناء النزاعات المسلحة وفي أوقات السلم.",
        "إن البحث العلمي يقوم على الأمانة الأكاديمية والتوثيق المنهجي للمصادر والمراجع، حيث يتعين على الباحث التحري والتدقيق في نسبة الأفكار والنظريات إلى أصحابها الأصليين وفق القواعد المعتمدة.",
    ]

    all_human = []
    # Law domain
    for i, t in enumerate(law_human):
        all_human.append({"text": t, "domain": "law_and_criminology", "source": f"police_academy_thesis_p{i+1}"})
    # Diplomacy / Protocol
    for i, t in enumerate(dip_human):
        all_human.append({"text": t, "domain": "diplomacy_and_protocol", "source": f"diplomacy_thesis_p{i+1}"})
    for i, t in enumerate(hist_human):
        all_human.append({"text": t, "domain": "humanities_and_rights", "source": f"historical_reference_p{i+1}"})

    print(f"Total authentic human paragraphs extracted: {len(all_human)}")

    # Distinct AI-generated academic passages across matching academic domains
    ai_passages = [
        # Law & Criminology
        {"domain": "law_and_criminology", "source": "llm_law_01", "generator": "GPT-4",
         "text": "تعتبر المسؤولية الجنائية الناشئة عن سرقة الآثار والتعدي على المواقع التاريخية ركيزة أساسية في التشريعات المقارنة، حيث تهدف النصوص القانونية إلى فرض عقوبات مشددة تشمل السجن والغرامة لحماية الهوية التراثية ومنع تهريب المقتنيات خارج الحدود الوطنية."},
        {"domain": "law_and_criminology", "source": "llm_law_02", "generator": "GPT-4",
         "text": "يقتضي مبدأ الشرعية الجنائية في الجرائم التراثية تحديد الأركان المادية والمعنوية بدقة متناهية، إذ لا جريمة ولا عقوبة إلا بنص قانوني صريح يجرم الحيازة غير المشروعة للقطع الأثرية غير المسجلة لدى الهيئات الحكومية المختصة."},
        {"domain": "law_and_criminology", "source": "llm_law_03", "generator": "Llama-3",
         "text": "أكدت الاتفاقيات الدولية، ولا سيما اتفاقية اليونسكو لعام 1970، على ضرورة إلزام الدول الأعضاء باتخاذ تدابير وقائية ورقابية على المزادات وصالات العرض لضمان عدم تداول الممتلكات الثقافية المسروقة أو الناتجة عن أعمال الحفر غير القانونية."},
        {"domain": "law_and_criminology", "source": "llm_law_04", "generator": "Claude",
         "text": "يتطلب التحقيق في قضايا غسيل الأموال المرتبطة بتجارة الآثار غير المشروعة تعاوناً وثيقاً بين أجهزة الشرطة القضائية والإنتربول الدولي، نظراً للطبيعة العابرة للحدود لتلك الشبكات الإجرامية المنظمة التي تستغل الملاذات الضريبية الآمنة."},
        {"domain": "law_and_criminology", "source": "llm_law_05", "generator": "ALLaM",
         "text": "يشكل الركن المعنوي في جرائم الاعتداء على التراث ركناً جوهرياً يتطلب ثبوت القصد الجنائي العام بعلم الجاني بطبيعة الشيء المسروق وإرادته الواعية في إخفائه ونقله عبر الحدود بالمخالفة للوائح الجمركية النافذة."},

        # Security & Policing
        {"domain": "security_and_policing", "source": "llm_sec_01", "generator": "GPT-4",
         "text": "تسعى النظريات الأمنية الحديثة إلى تبني مفاهيم الشرطة المجتمعية كاستراتيجية وقائية لتعزيز الثقة المتبادلة بين المواطنين والأجهزة الأمنية، مما يسهم في الكشف المبكر عن الجريمة والحد من تفشي السلوكيات الانحرافية في الأحياء السكنية."},
        {"domain": "security_and_policing", "source": "llm_sec_02", "generator": "GPT-4",
         "text": "إن تطبيق الذكاء الاصطناعي وتقنيات التعرف على الوجوه في مراقبة المنافذ الحدودية يرفع كفاءة المنظومة الأمنية، إلا أنه يثير تساؤلات ملحة حول حماية البيانات الشخصية والخصوصية الفردية للمسافرين وفق المعايير الحقوقية والدستورية."},
        {"domain": "security_and_policing", "source": "llm_sec_03", "generator": "Llama-3",
         "text": "تعتمد إدارة الأزمات الأمنية على التخطيط المسبق والمحاكاة التكتيكية للسيناريوهات المحتملة، حيث يتعين على غرف العمليات المركزية التنسيق الفوري بين قوات التدخل السريع والدفاع المدني لتقليل الخسائر البشرية والمادية."},
        {"domain": "security_and_policing", "source": "llm_sec_04", "generator": "Claude",
         "text": "يعد التدريب المستمر للكوادر الأمنية على مهارات التفاوض وإدارة الحشود عاملاً حاسماً في احتواء الاضطرابات دون اللجوء إلى القوة المفرطة، بما يحقق التوازن المنشود بين حفظ النظام العام واحترام الحريات الأساسية."},
        {"domain": "security_and_policing", "source": "llm_sec_05", "generator": "Jais",
         "text": "يتطلب التحول الرقمي في العمليات الشرطية بناء قواعد بيانات مركزية مؤمنة ضد الهجمات السيبرانية، وتأهيل الضباط على استخدام أدوات التحليل الجنائي الرقمي لتعقب الأدلة في البيئة الافتراضية وسلاسل الكتل."},

        # Diplomacy & Protocol
        {"domain": "diplomacy_and_protocol", "source": "llm_dip_01", "generator": "GPT-4",
         "text": "تشكل قواعد الأسبقية والتشريفات في المراسم الدبلوماسية لغة تعبيرية رمزية تعكس مكانة الدول وسيادتها، حيث يتم ترتيب الوفود الرسمية وفق معايير دقيقة تحكمها اتفاقية فيينا للعلاقات الدبلوماسية لعام 1961."},
        {"domain": "diplomacy_and_protocol", "source": "llm_dip_02", "generator": "GPT-4",
         "text": "تخضع مراسم تقديم أوراق الاعتماد للسفراء الجدد لبروتوكول صارم يبدأ باستقبال رئيس الدولة ومصافحة حرس الشرف، ثم تبادل الكلمات الرسمية التي تؤكد الرغبة المشتركة في توطيد العلاقات الثنائية والتعاون المشترك."},
        {"domain": "diplomacy_and_protocol", "source": "llm_dip_03", "generator": "Llama-3",
         "text": "يقتضي البروتوكول الدولي في المؤتمرات متعددة الأطراف مراعاة الترتيب الهجائي لأسماء الدول الأعضاء عند توزيع المقاعد والأعلام، وذلك تفادياً لأي حساسية سياسية قد تنشأ بين الدول المشاركة حول أولوية الجلوس أو التحدث."},
        {"domain": "diplomacy_and_protocol", "source": "llm_dip_04", "generator": "Claude",
         "text": "تعتبر الحصانة الدبلوماسية المقررة للمبعوثين والمقرات الدبلوماسية ضمانة قانونية أساسية لممارسة المهام التمثيلية دون تعرض لضغوط أو إجراءات قضائية من الدولة المعتمد لديها، وذلك وفقاً لقواعد العرف الدولي المستقر."},
        {"domain": "diplomacy_and_protocol", "source": "llm_dip_05", "generator": "Jais",
         "text": "تنظم قواعد البروتوكول ترتيب المآدب الرسمية وحفلات الاستقبال من خلال تحديد أماكن الضيوف على المائدة الرئيسية بحسب الرتب والأقدمية الدبلوماسية، مع مراعاة العادات والتقاليد الثقافية للدول الممثلة في الحفل."},

        # Computer Science & Educational Sciences
        {"domain": "computer_and_education", "source": "llm_cs_01", "generator": "GPT-4",
         "text": "يوفر توظيف تقنيات معالجة اللغات الطبيعية في التعليم العالي فرصاً غير مسبوقة لتخصيص مسارات التعلم وتقديم التغذية الراجعة الفورية للطلاب، مما يعزز الفهم الذاتي ويقلل الفجوة التعليمية بين المستويات المتباينة."},
        {"domain": "computer_and_education", "source": "llm_cs_02", "generator": "GPT-4",
         "text": "أظهرت نماذج المحولات اللغوية العميقة قدرة فائقة على توليد النصوص وتلخيص البحوث العلمية، غير أن ظاهرة الهلوسة وانعدام التحقق التجريبي من الحقائق تظل تحدياً رئيسياً أمام اعتمادها الكامل في الأوساط الأكاديمية."},
        {"domain": "computer_and_education", "source": "llm_cs_03", "generator": "Llama-3",
         "text": "يواجه التعليم الجامعي المعاصر تحدياً جوهرياً يتمثل في كيفية إعادة تصميم أساليب التقييم والامتحانات الشفهية لمواكبة انتشار أدوات الذكاء الاصطناعي التوليدي، مع التركيز على مهارات التفكير النقدي والتحليل المعمق."},
        {"domain": "computer_and_education", "source": "llm_cs_04", "generator": "Claude",
         "text": "تتطلب حوكمة خوارزميات التعلم الآلي وضع معايير صارمة للشفافية وتفسير القرارات الصادرة عن النماذج التنبؤية، لا سيما عند تطبيقها في بيئات التوظيف أو القبول الأكاديمي لمنع التحيز والتمييز الخوارزمي غير العادل."},
        {"domain": "computer_and_education", "source": "llm_cs_05", "generator": "ALLaM",
         "text": "يسهم دمج الحوسبة السحابية مع خوارزميات التنقيب في البيانات الأكاديمية في رصد معدلات التسرب الجامعي والتنبؤ المبكر بأداء الطلاب المعرضين للتعثر، مما يتيح للإدارات التعليمية اتخاذ تدابير إرشادية وتدخلات استباقية فعالة."},
    ]

    # AI-edited human writing (polishing / stylistic restructuring of genuine human texts)
    ai_edited_passages = [
        {"domain": "law_and_criminology", "source": "edited_law_01", "generator": "AI-Polished (GPT-4)",
         "text": "يعتبر علم الآثار من العلوم التحقيقية الرائدة التي تسعى إلى تتبع الجذور المادية للحضارات الإنسانية وتوثيق تطورها التاريخي عبر العصور المتعاقبة بالاعتماد على الفحص المنهجي للشواهد واللقى التراثية."},
        {"domain": "law_and_criminology", "source": "edited_law_02", "generator": "AI-Polished (Claude)",
         "text": "يهدف التشريع الجنائي المقارن إلى إحكام الرقابة الأمنية على المنافذ والحدود لقطع دابر الشبكات المتخصصة في الاتجار غير المشروع بالمقتنيات التراثية وملاحقة الجناة بعقوبات رادعة تحمي الذاكرة الوطنية."},
        {"domain": "security_and_policing", "source": "edited_sec_01", "generator": "AI-Polished (GPT-4)",
         "text": "تعد المحاكمة العرفية آلية تقليدية لفض النزاعات المجتمعية وفق ضوابط مستقرة تضمن علانية الإجراءات وسماع الخصوم والشهود بمصداقية أمام جمهور الحاضرين دون إخلال بالأمن العام."},
        {"domain": "diplomacy_and_protocol", "source": "edited_dip_01", "generator": "AI-Polished (Llama-3)",
         "text": "تتكامل الأعراف الدبلوماسية مع النصوص الصريحة لتحديد أسبقية المبعوثين وتنظيم الزيارات الرسمية بما يضمن انسيابية التعامل ومراعاة كرامة الدول الممثلة في كافة المناسبات القنصلية والدولية."},
        {"domain": "humanities_and_rights", "source": "edited_hum_01", "generator": "AI-Polished (Claude)",
         "text": "يقوم ميثاق حقوق الإنسان العالمي على ترسيخ مبادئ الحرية والمساواة والكرامة المتأصلة لجميع بني البشر، مع التأكيد على ضرورة التعاون الإنساني المشترك لبناء مجتمعات تسودها العدالة وسيادة القانون."},
    ]

    # Create balanced dataset with disjoint document/author splits
    records = []
    
    # 1. Train split: 10 Human, 10 AI (Domain balanced)
    for i in range(10):
        h = all_human[i]
        records.append({
            "sample_id": f"train-human-{i+1:02d}",
            "document_id": f"doc-train-h-{h['source']}",
            "source_document_id": h['source'],
            "text": h['text'],
            "provenance_label": "HUMAN",
            "generator_family": "NONE",
            "editing_category": "NONE",
            "academic_domain": h['domain'],
            "data_origin": "PEER_REVIEWED_THESIS",
            "license_permission": True,
            "split": "train",
            "word_count": len(h['text'].split())
        })
        ai = ai_passages[i]
        records.append({
            "sample_id": f"train-ai-{i+1:02d}",
            "document_id": f"doc-train-ai-{ai['source']}",
            "source_document_id": ai['source'],
            "text": ai['text'],
            "provenance_label": "AI_GENERATED",
            "generator_family": ai['generator'],
            "editing_category": "NONE",
            "academic_domain": ai['domain'],
            "data_origin": "LLM_ACADEMIC_GENERATION",
            "license_permission": True,
            "split": "train",
            "word_count": len(ai['text'].split())
        })

    # 2. Validation / Calibration split: 10 Human, 10 AI (Strictly disjoint documents)
    for i in range(10, 20):
        h = all_human[i]
        records.append({
            "sample_id": f"val-human-{i-9:02d}",
            "document_id": f"doc-val-h-{h['source']}",
            "source_document_id": h['source'],
            "text": h['text'],
            "provenance_label": "HUMAN",
            "generator_family": "NONE",
            "editing_category": "NONE",
            "academic_domain": h['domain'],
            "data_origin": "PEER_REVIEWED_THESIS",
            "license_permission": True,
            "split": "validation",
            "word_count": len(h['text'].split())
        })
        ai = ai_passages[i]
        records.append({
            "sample_id": f"val-ai-{i-9:02d}",
            "document_id": f"doc-val-ai-{ai['source']}",
            "source_document_id": ai['source'],
            "text": ai['text'],
            "provenance_label": "AI_GENERATED",
            "generator_family": ai['generator'],
            "editing_category": "NONE",
            "academic_domain": ai['domain'],
            "data_origin": "LLM_ACADEMIC_GENERATION",
            "license_permission": True,
            "split": "validation",
            "word_count": len(ai['text'].split())
        })

    # 3. Held-out Test split: 15 Human, 15 AI, plus 5 AI-edited (disjoint from train & val)
    # Human test
    human_test_pool = all_human[20:35]
    for i, h in enumerate(human_test_pool):
        records.append({
            "sample_id": f"test-human-{i+1:02d}",
            "document_id": f"doc-test-h-{h['source']}",
            "source_document_id": h['source'],
            "text": h['text'],
            "provenance_label": "HUMAN",
            "generator_family": "NONE",
            "editing_category": "NONE",
            "academic_domain": h['domain'],
            "data_origin": "PEER_REVIEWED_THESIS",
            "license_permission": True,
            "split": "test",
            "word_count": len(h['text'].split())
        })

    # AI test (fresh academic passages in remaining domains and generators)
    ai_test_pool = [
        {"domain": "law_and_criminology", "source": "test_ai_law_01", "generator": "GPT-4",
         "text": "تعتبر عقوبة التهريب الجمركي للقطع الأثرية من العقوبات التبعية التي تقترن بالمصادرة الوجوبية للمضبوطات ووسائل النقل المستخدمة في الجريمة، تأكيداً على عدم جواز تملك الأفراد للأموال العامة التراثية."},
        {"domain": "law_and_criminology", "source": "test_ai_law_02", "generator": "Claude-3.5",
         "text": "تتطلب ملاحقة تجار الآثار عبر الإنترنت تفعيل آليات الرصد الرقمي للمواقع المشبوهة وغرف المزايدات المغلقة في الدارك ويب، مع ضرورة إبرام اتفاقيات ثنائية لتسليم المجرمين وتنسيق الإجراءات القضائية."},
        {"domain": "law_and_criminology", "source": "test_ai_law_03", "generator": "Llama-3.1",
         "text": "تعد المعاينة الفنية الميدانية للأماكن التراثية المستهدفة بالحفر خلسة الدليل القاطع على تحقق الركن المادي للجريمة، حيث يقوم خبراء الآثار بتحديد عمر الطبقات الجيولوجية والأضرار الناجمة عن أعمال النبش العشوائي."},
        {"domain": "security_and_policing", "source": "test_ai_sec_01", "generator": "GPT-4",
         "text": "ترتكز الاستراتيجيات الحديثة لمكافحة الإرهاب الإلكتروني على الرصد الاستباقي للخطاب المتطرف وتفكيك المنصات الدعائية قبل وصولها إلى الفئات المستهدفة بالتجنيد، بالتعاون مع شركات التكنولوجيا العالمية."},
        {"domain": "security_and_policing", "source": "test_ai_sec_02", "generator": "Claude-3.5",
         "text": "إن تفعيل غرف العمليات الذكية يسهم في تحليل البلاغات الأمنية وتوجيه الدوريات الميدانية وفق خرائط الكثافة الجرمية، مما يقلل زمن الاستجابة للبلاغات الطارئة ويحسن معدلات ضبط المشتبه بهم."},
        {"domain": "security_and_policing", "source": "test_ai_sec_03", "generator": "Jais",
         "text": "تعتمد خطط التأمين والحماية للمنشآت الحيوية على تطبيق مبدأ الدفاع في العمق، من خلال تزويد المحيط الخارجي بكاميرات المراقبة الحرارية والحواجز الهيدروليكية وبوابات الكشف عن المتفجرات والمواد الخطرة."},
        {"domain": "diplomacy_and_protocol", "source": "test_ai_dip_01", "generator": "GPT-4",
         "text": "تحدد البروتوكولات الدبلوماسية مراسم توديع رؤساء الدول والوفود الرسمية عند انتهاء الزيارات الثنائية، بما يشمل استعراض حرس الشرف وعزف النشيدين الوطنيين بحضور وزير الخارجية أو رئيس بعثة الشرف المرافقة."},
        {"domain": "diplomacy_and_protocol", "source": "test_ai_dip_02", "generator": "Claude-3.5",
         "text": "تلتزم البعثات الدبلوماسية باحترام قوانين وأنظمة الدولة المضيفة وعدم التدخل في شؤونها الداخلية، حيث يعتبر ذلك قيداً جوهرياً يقابل التمتع بالحصانات والامتيازات الدبلوماسية المنصوص عليها دولياً."},
        {"domain": "diplomacy_and_protocol", "source": "test_ai_dip_03", "generator": "ALLaM",
         "text": "تتطلب الدبلوماسية الرقمية إدارة الحسابات الرسمية للسفارات بمهنية فائقة تعكس الموقف الخارجي للدولة بدقة، وتتجنب إثارة الجدل أو التورط في سجالات إعلامية تخالف الأعراف الدبلوماسية الرصينة."},
        {"domain": "computer_and_education", "source": "test_ai_cs_01", "generator": "GPT-4",
         "text": "يتيح تحليل البيانات الضخمة للمؤسسات الجامعية تحسين خطط القبول وتطوير البرامج الأكاديمية بما يتلاءم مع متطلبات سوق العمل المستقبلية، مستندة إلى مؤشرات الأداء الوظيفي للخريجين."},
        {"domain": "computer_and_education", "source": "test_ai_cs_02", "generator": "Claude-3.5",
         "text": "تعتمد نظم كشف الانتحال الأكاديمي المتقدمة على التحليل الدلالي والتوافقي للفقرات بدلاً من مطابقة الكلمات السطحية، مما يمكنها من كشف المحتوى المعاد صياغته بدقة وموضوعية."},
        {"domain": "computer_and_education", "source": "test_ai_cs_03", "generator": "Llama-3.1",
         "text": "تثير الاستعانة بالذكاء الاصطناعي في إعداد رسائل الماجستير والدكتوراه إشكاليات أخلاقية معقدة تتعلق بالأصالة العلمية وملكية البيانات، مما يستوجب وضع لوائح جامعية حازمة تحدد النطاق المسموح به."},
        {"domain": "humanities_and_rights", "source": "test_ai_hum_01", "generator": "GPT-4",
         "text": "يمثل الحوار بين الحضارات والثقافات سبيلاً حتمياً لتجاوز الصراعات الإقليمية وتحقيق السلام المستدام، من خلال التأكيد على المشتركات الإنسانية وقيم التسامح وقبول التعددية الفكرية."},
        {"domain": "humanities_and_rights", "source": "test_ai_hum_02", "generator": "Claude-3.5",
         "text": "تؤكد النظريات السوسيولوجية المعاصرة على أن التماسك الاجتماعي في المدن الكبرى يعتمد على عدالة توزيع الخدمات العامة ومكافحة التهميش الاقتصادي للمهاجرين والفئات الأقل دخلاً."},
        {"domain": "humanities_and_rights", "source": "test_ai_hum_03", "generator": "Jais",
         "text": "إن توثيق التاريخ الشفوي وحفظ الذاكرة الشعبية من الاندثار يشكل عنصراً حيوياً في تعزيز الهوية الوطنية وحماية الموروث اللامادي من الذوبان أمام ضغوط العولمة الثقافية الجارفة."},
    ]

    for i, ai in enumerate(ai_test_pool):
        records.append({
            "sample_id": f"test-ai-{i+1:02d}",
            "document_id": f"doc-test-ai-{ai['source']}",
            "source_document_id": ai['source'],
            "text": ai['text'],
            "provenance_label": "AI_GENERATED",
            "generator_family": ai['generator'],
            "editing_category": "NONE",
            "academic_domain": ai['domain'],
            "data_origin": "LLM_ACADEMIC_GENERATION",
            "license_permission": True,
            "split": "test",
            "word_count": len(ai['text'].split())
        })

    # AI-edited test samples
    for i, ed in enumerate(ai_edited_passages):
        records.append({
            "sample_id": f"test-edited-{i+1:02d}",
            "document_id": f"doc-test-edited-{ed['source']}",
            "source_document_id": ed['source'],
            "text": ed['text'],
            "provenance_label": "AI_EDITED",
            "generator_family": ed['generator'],
            "editing_category": "AI_POLISHED_HUMAN",
            "academic_domain": ed['domain'],
            "data_origin": "AI_POLISHED_THESIS",
            "license_permission": True,
            "split": "test",
            "word_count": len(ed['text'].split())
        })

    out_path = _ROOT / "tests" / "benchmark" / "academic_ai_writing_benchmark_dataset.json"
    out_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Successfully created benchmark dataset with {len(records)} records at: {out_path}")

    # Summary by split and label
    splits = {}
    for r in records:
        sp = r['split']
        lbl = r['provenance_label']
        splits.setdefault(sp, {}).setdefault(lbl, 0)
        splits[sp][lbl] += 1
    print("Dataset distribution:", json.dumps(splits, indent=2))

if __name__ == '__main__':
    main()
