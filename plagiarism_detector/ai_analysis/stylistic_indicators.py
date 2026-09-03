# -*- coding: utf-8 -*-
"""
وحدة المؤشرات الأسلوبية للكتابة الآلية (Stylistic AI-Likelihood Indicators):
- تحليل الخصائص الأسلوبية الإحصائية (انتظام أطوال الجمل Burstiness، تنوع المفردات TTR، تكرار عبارات الربط).
- تقدم نتائج نوعية واضحة (منخفض / متوسط / مرتفع) مع درجة استئناسية (0-100).
- تتضمن إشعاراً أكاديمياً صريحاً بأنها مؤشر أسلوبي لغوي فقط وليست حكماً علمياً قاطعاً على أصل النص.
"""

import math
import re
from plagiarism_detector.preprocessing.normalizer import normalize_light


def analyze_stylistic_ai_indicators(text: str) -> dict:
    """
    تحليل مؤشرات الأسلوب اللغوي المشابه للذكاء الاصطناعي أوفلاين.
    """
    disclaimer = (
        "هذه النتيجة تمثل مؤشراً أسلوبياً استئناسياً فقط مبنياً على تحليل التراكيب وتكرار العبارات، "
        "ولا تُعد بأي حال دليلاً قاطعاً أو إثباتاً علمياً على أن النص تم توليده آلياً بوساطة الذكاء الاصطناعي."
    )

    if not text:
        return {
            'indicator_level': 'منخفض (أسلوب بشري طبيعي)',
            'score': 0,
            'is_high_likelihood': False,
            'details': 'النص فارغ.',
            'warning': disclaimer
        }

    # تقطيع الجمل الحقيقية
    clean_text = re.sub(r'(?<!\n)\n(?!\n)', ' ', text)
    sentences = [s.strip() for s in re.split(r'[.!?؟]+|\n{2,}', clean_text) if len(s.strip().split()) >= 4]

    words = re.findall(r'[\u0600-\u06FF]+', normalize_light(text))
    total_words = len(words)

    if total_words < 30:
        return {
            'indicator_level': 'غير كافٍ للتحليل',
            'score': 0,
            'is_high_likelihood': False,
            'details': 'النص قصير جداً (أقل من 30 كلمة) لإجراء التحليل الأسلوبي الموثوق.',
            'warning': disclaimer
        }

    # 1. نسبة تنوع المفردات (Type-Token Ratio)
    unique_words = len(set(words))
    ttr = unique_words / total_words

    # 2. انتظام أطوال الجمل (Burstiness)
    sentence_lengths = [len(s.split()) for s in sentences]
    mean_len = sum(sentence_lengths) / len(sentence_lengths) if sentence_lengths else 0
    variance = sum((l - mean_len) ** 2 for l in sentence_lengths) if sentence_lengths else 0
    std_dev = math.sqrt(variance)
    burstiness_score = std_dev / mean_len if mean_len > 0 else 1.0

    # 3. عبارات التنسيق والربط النمطية الشائعة في نصوص الـ LLM
    norm_full = normalize_light(clean_text)
    ai_phrases = [
        'بالاضافة الى ذلك', 'من الجدير بالذكر', 'في هذا السياق', 'مما لا شك فيه',
        'لذلك فان', 'بناء على ما تقدم', 'على صعيد اخر', 'يلعب دورا هاما',
        'يلعب دورا محوريا', 'تعتبر من اهم', 'خلاصة القول', 'يهدف هذا',
        'نستنتج ان', 'من ناحية اخرى', 'في نهاية المطاف', 'حيث ان', 'كما ان',
        'على سبيل المثال', 'شهدت الاونة الاخيرة', 'على النحو التالي',
        'يعود ذلك الى', 'من المهم الاشارة الى', 'في هذا الصدد', 'تعد من ابرز',
        'من المعلوم ان', 'من الناحية العملية', 'تسليط الضوء على', 'وفي هذا الصدد',
        'على وجه الخصوص', 'وتجدر الاشارة الى', 'بصورة عامة', 'من هذا المنطلق',
        'وفي نفس الوقت', 'سواء يتعلق الامر', 'الجدير بالذكر ان', 'على عكس ذلك',
        'في ضوء ما سبق', 'يمكن القول ان', 'من الواضح ان', 'تجدر الاشارة الى ان'
    ]

    phrase_count = sum(norm_full.count(ph) for ph in ai_phrases)

    # 4. حساب الدرجة الموزونة (0 - 100)
    score = 0.0

    # تكرار عبارات الربط
    if phrase_count >= 6:
        score += 40
    elif phrase_count >= 3:
        score += 25
    elif phrase_count >= 1:
        score += 15

    # انتظام الجمل الشديد (Burstiness < 0.85)
    if burstiness_score < 0.80:
        score += 25
    elif burstiness_score < 1.05:
        score += 15

    # توازن التنوع اللفظي في نصوص الذكاء الاصطناعي
    if 0.40 <= ttr <= 0.65:
        score += 20

    # متوسط طول الجمل النمطي
    if 15 <= mean_len <= 30:
        score += 15

    final_score = min(round(score), 95)

    # تحديد المستوى النوعي
    if final_score >= 65:
        indicator_level = 'مرتفع (مؤشرات أسلوبية مكثفة)'
        is_high = True
    elif final_score >= 35:
        indicator_level = 'متوسط (بعض المؤشرات الأسلوبية المشتركة)'
        is_high = False
    else:
        indicator_level = 'منخفض (أسلوب بشري طبيعي)'
        is_high = False

    details = (
        f"عدد عبارات الربط النمطية: {phrase_count} | "
        f"معدل انتظام الجمل: {round(burstiness_score, 2)} | "
        f"تنوع المفردات: {round(ttr * 100, 1)}%"
    )

    return {
        'indicator_level': indicator_level,
        'score': final_score,
        'is_high_likelihood': is_high,
        'details': details,
        'warning': disclaimer,
        # للتوافق العكسي مع الواجهة السابقة:
        'ai_percentage': final_score,
        'status': indicator_level,
        'is_ai': is_high
    }
