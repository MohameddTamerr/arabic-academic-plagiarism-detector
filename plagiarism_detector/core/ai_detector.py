# -*- coding: utf-8 -*-
"""
وحدة كشف النصوص الموالدة بالذكاء الاصطناعي (Offline AI Text Generation Detector):
تستخدم تحليلات التباين الإحصائي والتعقيد اللغوي (Perplexity & Burstiness Analysis)
وقياس التوزيع التكراري للتراكيب اللغوية لتحديد احتمال توليد النص بوساطة AI أوفلاين.
"""

import math
import re
from plagiarism_detector.core.normalize import normalize_arabic


def analyze_ai_generation(text: str) -> dict:
    """
    تحليل احتمالية أن يكون النص مجلابًا/مولدًا بالذكاء الاصطناعي أوفلاين.
    يرجع النسبة المئوية ومستوى التهديد وتفاصيل التحليل الإحصائي.
    """
    if not text:
        return {'ai_percentage': 0, 'status': 'طبيعي', 'is_ai': False, 'details': ''}

    # 1. دمج الأسطر الناعمة داخل الفقرات وتقطيع الجمل الحقيقية
    clean_p_text = re.sub(r'(?<!\n)\n(?!\n)', ' ', text)
    sentences = [s.strip() for s in re.split(r'[.!?؟]+|\n{2,}', clean_p_text) if len(s.strip().split()) >= 4]

    words = re.findall(r'[\u0600-\u06FF]+', normalize_arabic(text))
    total_words = len(words)

    if total_words < 25:
        return {
            'ai_percentage': 0,
            'status': 'غير كافٍ للتحليل',
            'is_ai': False,
            'details': 'النص قصير جداً لإجراء تحليل الذكاء الاصطناعي الإحصائي.'
        }

    unique_words = len(set(words))
    ttr = unique_words / total_words  # Type-Token Ratio

    # 2. حساب التباين في طول الجمل (Burstiness Analysis)
    sentence_lengths = [len(s.split()) for s in sentences]
    mean_len = sum(sentence_lengths) / len(sentence_lengths) if sentence_lengths else 0
    variance = sum((l - mean_len) ** 2 for l in sentence_lengths) if sentence_lengths else 0
    std_dev = math.sqrt(variance)
    burstiness_score = std_dev / mean_len if mean_len > 0 else 1.0

    # 3. أدوات وعبارات الربط الأكاديمية الشائعة جداً في نصوص نماذج الـ AI (ChatGPT/Claude)
    norm_full = normalize_arabic(clean_p_text)
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

    # 4. حساب الدرجة المجمعة لترجيح توليد الـ AI
    ai_score = 0.0

    # مطابقة عبارات الربط الأكاديمية للـ AI
    if phrase_count >= 5:
        ai_score += 45
    elif phrase_count >= 3:
        ai_score += 35
    elif phrase_count >= 1:
        ai_score += 20

    # Burstiness (انتظام الجمل والفقرات النمطي)
    if burstiness_score < 0.85:
        ai_score += 25
    elif burstiness_score < 1.1:
        ai_score += 15

    # TTR الاتساق اللفظي المتوازن في نصوص AI العربية
    if 0.40 <= ttr <= 0.70:
        ai_score += 25

    # أطوال الجمل المتوسطة النمطية للـ AI (بين 14 و 32 كلمة بالجملة)
    if 14 <= mean_len <= 32:
        ai_score += 15

    final_pct = min(round(ai_score), 95)

    status = 'منخفض (نص بشري أصلي)'
    is_ai = False
    if final_pct >= 65:
        status = 'مرتفع (احتمال كبير نص مولد بالذكاء الاصطناعي)'
        is_ai = True
    elif final_pct >= 40:
        status = 'متوسط (احتمال استعانة بالذكاء الاصطناعي)'

    details_msg = f"عبارات الـ AI المكتشفة: {phrase_count} | درجة انتظام الجمل: {round(burstiness_score, 2)}"

    return {
        'ai_percentage': final_pct,
        'status': status,
        'is_ai': is_ai,
        'details': details_msg
    }
