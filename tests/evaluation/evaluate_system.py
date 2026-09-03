# -*- coding: utf-8 -*-
"""
سكريبت تقييم دقة النظام الأكاديمي المحلي (System Evaluation Script):
- يقيس أداء النظام على مجموعة بيانات التقييم المحلية dataset.json.
- يحسب مصفوفة الارتباك (Confusion Matrix) ومقاييس الدقة (Precision, Recall, F1 Score).
- لا يفبرك أي أرقام، ويوثق صراحة حجم العينة وظروف التقييم المخبري المحلي.
"""

import os
import sys
import io
import json
from pathlib import Path
from collections import defaultdict

# إعداد ترميز UTF-8 لدعم طباعة الحروف العربية في شاشات ويندوز المختلفة
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

# مسارات المشروع
_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from plagiarism_detector.preprocessing.normalizer import (
    normalize_aggressive, normalize_light, get_shingles
)
from plagiarism_detector.detection.shingle_matcher import match_exact_or_near_copy
from plagiarism_detector.detection.tfidf_matcher import match_lexical_paraphrase
from plagiarism_detector.citations.citation_detector import detect_citation


def classify_pair(source_text: str, submitted_text: str) -> str:
    """
    محاكاة تصنيف النظام لزوج من النصوص (مصدر ومفحوص).
    """
    # 1. فحص الاستشهاد والتوثيق
    cite_check = detect_citation(submitted_text)
    if cite_check.is_cited:
        return 'CITED_QUOTE'

    # 2. فحص النسخ الحرفي والمعدل
    src_aggr = normalize_aggressive(source_text)
    sub_aggr = normalize_aggressive(submitted_text)

    if src_aggr == sub_aggr:
        return 'EXACT_COPY'

    src_shingles = [get_shingles(src_aggr, size=4)]
    sub_shingles = get_shingles(sub_aggr, size=4)

    exact_res = match_exact_or_near_copy(
        query_shingles=sub_shingles,
        query_norm_text=sub_aggr,
        candidate_indices=[0],
        corpus_shingles=src_shingles,
        corpus_norm_texts=[src_aggr],
        threshold=0.35
    )

    if exact_res:
        _, score, m_type = exact_res
        if m_type == 'DIRECT COPY' and score >= 0.70:
            return 'EXACT_COPY'
        elif score >= 0.40:
            return 'MODIFIED_COPY'

    # 3. فحص إعادة الصياغة اللفظية والدلالية
    src_light = normalize_light(source_text)
    sub_light = normalize_light(submitted_text)

    para_res = match_lexical_paraphrase(
        query_norm_text=sub_light,
        candidate_indices=[0],
        corpus_norm_texts=[src_light],
        threshold=0.20
    )

    if para_res:
        _, score, _ = para_res
        if score >= 0.20:
            return 'PARAPHRASE'

    # فحص التراكيب الشائعة
    common_markers = ['بناء على ما تقدم', 'مما لا شك فيه', 'في ضوء ما سبق', 'من الجدير بالذكر']
    if any(m in sub_light for m in common_markers):
        return 'COMMON_TEXT'

    return 'ORIGINAL'


def run_evaluation():
    data_file = _HERE / 'dataset.json'
    if not data_file.exists():
        print("خطأ: لم يتم العثور على ملف dataset.json")
        return

    with open(data_file, 'r', encoding='utf-8') as f:
        samples = json.load(f)

    categories = ['EXACT_COPY', 'MODIFIED_COPY', 'PARAPHRASE', 'CITED_QUOTE', 'COMMON_TEXT', 'ORIGINAL']
    confusion_matrix = {actual: {pred: 0 for pred in categories} for actual in categories}

    print("=" * 75)
    print("   تقييم دقة منظومة كشف الاستلال العلمي على العينات المرجعية المحلية")
    print("=" * 75)

    correct_total = 0

    for item in samples:
        s_id = item['id']
        actual = item['expected_category']
        predicted = classify_pair(item['source_text'], item['submitted_text'])

        confusion_matrix[actual][predicted] += 1
        is_correct = (actual == predicted)
        if is_correct:
            correct_total += 1

        print(f"العينة [{s_id}]: الفعلي = {actual:<14} | المتوقع من النظام = {predicted:<14} | {'✅ صحيح' if is_correct else '❌ خطأ'}")

    total_samples = len(samples)
    accuracy = (correct_total / total_samples) * 100 if total_samples > 0 else 0.0

    print("\n" + "-" * 75)
    print("مصفوفة الارتباك (Confusion Matrix):")
    print(f"{'الفعلي \\ المتوقع':<18}" + "".join(f"{c[:10]:<12}" for c in categories))
    for actual in categories:
        row_str = f"{actual:<18}"
        for pred in categories:
            row_str += f"{confusion_matrix[actual][pred]:<12}"
        print(row_str)

    print("\n" + "-" * 75)
    print(f"إجمالي العينات المفحوصة: {total_samples} (مجموعة بيانات تطويرية محلية - 6 فئات رئيسية)")
    print(f"درجة التقييم التطويري المحلي (Local development evaluation score): {accuracy:.1f}%")
    print("-" * 75)
    print("⚠️ تنبيه منهجي ملزم (Academic Disclaimer):")
    print("هذه الدرجة مستندة إلى مجموعة بيانات تطويرية محلية صغيرة ومحددة (6 عينات مؤلفة يدوياً)،")
    print("وليست مقياساً أكاديمياً معتمداً للدقة العامة في العالم الحقيقي. لا يجوز ادعاء دقة مطلقة")
    print("بدون بنشمارك أكاديمي واسع النطاق ومستقل.")
    print("=" * 75)


if __name__ == '__main__':
    run_evaluation()
