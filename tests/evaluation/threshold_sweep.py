# -*- coding: utf-8 -*-
"""
مسح عتبات المعامل اللفظي (Threshold Sweep for lexical paraphrase detector):
- يختبر عتبات: 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60
- يحسب لكل عتبة: Precision, Recall, F1, FP, FN
- يُحلّل الخلط بين: PARAPHRASE, ORIGINAL, COMMON_TEXT, MODIFIED_COPY
- لا يُعدّل أي عتبة إنتاجية.
- يُبقي على تحذير README بأن هذه مجموعة بيانات تطويرية محلية.
"""

import sys
import io
import json
from pathlib import Path
from collections import defaultdict

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from plagiarism_detector.preprocessing.normalizer import (
    normalize_aggressive, normalize_light, get_shingles
)
from plagiarism_detector.detection.shingle_matcher import match_exact_or_near_copy
from plagiarism_detector.detection.tfidf_matcher import match_lexical_paraphrase
from plagiarism_detector.citations.citation_detector import detect_citation

CATEGORIES = ['EXACT_COPY', 'MODIFIED_COPY', 'PARAPHRASE', 'CITED_QUOTE', 'COMMON_TEXT', 'ORIGINAL']
PARAPHRASE_NEIGHBOURS = {'PARAPHRASE', 'ORIGINAL', 'COMMON_TEXT', 'MODIFIED_COPY'}

COMMON_MARKERS = [
    'بناء على ما تقدم', 'مما لا شك فيه', 'في ضوء ما سبق',
    'من الجدير بالذكر', 'يتضح مما سبق', 'وفقاً لما تقدم',
    'مما تقدم يتبين', 'استناداً للمعطيات'
]


def classify_pair(source_text: str, submitted_text: str, para_threshold: float) -> str:
    """تصنيف زوج نصوص بعتبة paraphrase قابلة للضبط."""

    # 1. فحص الاستشهاد
    cite_check = detect_citation(submitted_text)
    if cite_check.is_cited:
        return 'CITED_QUOTE'

    # 2. فحص النسخ الحرفي
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

    # 3. فحص التراكيب الشائعة (قبل paraphrase لتجنب FP)
    sub_light_early = normalize_light(submitted_text)
    if any(m in sub_light_early for m in COMMON_MARKERS):
        return 'COMMON_TEXT'

    # 4. فحص إعادة الصياغة اللفظية بالعتبة المُختبَرة
    src_light = normalize_light(source_text)
    sub_light = normalize_light(submitted_text)

    para_res = match_lexical_paraphrase(
        query_norm_text=sub_light,
        candidate_indices=[0],
        corpus_norm_texts=[src_light],
        threshold=para_threshold
    )

    if para_res:
        _, score, _ = para_res
        if score >= para_threshold:
            return 'PARAPHRASE'

    return 'ORIGINAL'


def evaluate_at_threshold(samples: list, threshold: float) -> dict:
    """تقييم شامل عند عتبة معينة."""
    confusion = {a: {p: 0 for p in CATEGORIES} for a in CATEGORIES}
    correct = 0

    for item in samples:
        actual = item['expected_category']
        predicted = classify_pair(item['source_text'], item['submitted_text'], threshold)
        confusion[actual][predicted] += 1
        if actual == predicted:
            correct += 1

    total = len(samples)
    accuracy = correct / total if total > 0 else 0.0

    # مقاييس خاصة بـ PARAPHRASE
    tp = confusion['PARAPHRASE']['PARAPHRASE']
    fp = sum(confusion[a]['PARAPHRASE'] for a in CATEGORIES if a != 'PARAPHRASE')
    fn = sum(confusion['PARAPHRASE'][p] for p in CATEGORIES if p != 'PARAPHRASE')

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1        = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    # خلط PARAPHRASE مع جيرانها
    paraphrase_as_original  = confusion['PARAPHRASE']['ORIGINAL']
    paraphrase_as_common    = confusion['PARAPHRASE']['COMMON_TEXT']
    paraphrase_as_modified  = confusion['PARAPHRASE']['MODIFIED_COPY']
    original_as_paraphrase  = confusion['ORIGINAL']['PARAPHRASE']
    common_as_paraphrase    = confusion['COMMON_TEXT']['PARAPHRASE']
    modified_as_paraphrase  = confusion['MODIFIED_COPY']['PARAPHRASE']

    return {
        'threshold': threshold,
        'accuracy': accuracy,
        'precision': precision,
        'recall': recall,
        'f1': f1,
        'tp': tp,
        'fp': fp,
        'fn': fn,
        # confusion detail
        'PARA→ORIG': paraphrase_as_original,
        'PARA→COMMON': paraphrase_as_common,
        'PARA→MODIFIED': paraphrase_as_modified,
        'ORIG→PARA': original_as_paraphrase,
        'COMMON→PARA': common_as_paraphrase,
        'MODIFIED→PARA': modified_as_paraphrase,
        'confusion': confusion,
    }


def print_full_confusion(confusion: dict, threshold: float):
    """طباعة مصفوفة ارتباك كاملة لعتبة معينة."""
    print(f"\n  مصفوفة الارتباك عند threshold={threshold:.2f}:")
    header = f"  {'الفعلي\\المتوقع':<18}" + "".join(f"{c[:10]:<12}" for c in CATEGORIES)
    print(header)
    for actual in CATEGORIES:
        row = f"  {actual:<18}"
        for pred in CATEGORIES:
            v = confusion[actual][pred]
            marker = ' *' if (actual != pred and v > 0) else '  '
            row += f"{str(v)+marker:<12}"
        print(row)


def main():
    data_file = _HERE / 'dataset.json'
    if not data_file.exists():
        print("خطأ: dataset.json غير موجود.")
        return

    with open(data_file, 'r', encoding='utf-8') as f:
        samples = json.load(f)

    total = len(samples)
    by_cat = defaultdict(int)
    for s in samples:
        by_cat[s['expected_category']] += 1

    thresholds = [0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]

    print("=" * 90)
    print("  مسح عتبات كاشف إعادة الصياغة اللفظية (Lexical Paraphrase Threshold Sweep)")
    print("=" * 90)
    print(f"\n  إجمالي العينات: {total}")
    for cat, n in sorted(by_cat.items()):
        print(f"    {cat:<16}: {n}")
    print()
    print("  ⚠️  تحذير: هذه مجموعة بيانات تطويرية محلية مؤلّفة يدوياً ({} عينة).".format(total))
    print("      النتائج ليست مقياساً أكاديمياً معتمداً ولا تعكس الدقة في العالم الحقيقي.")
    print("      لا يجوز تعديل العتبة الإنتاجية إلا بعد تقييم على مجموعة بيانات موسعة ومستقلة.")

    results = []
    for thr in thresholds:
        r = evaluate_at_threshold(samples, thr)
        results.append(r)

    # ─── جدول الملخص ──────────────────────────────────────────────────────────
    print("\n" + "─" * 90)
    print("  جدول ملخص مقاييس PARAPHRASE حسب العتبة:")
    print("─" * 90)
    header = (
        f"  {'Threshold':<12}"
        f"{'Precision':<12}"
        f"{'Recall':<10}"
        f"{'F1':<10}"
        f"{'TP':<6}"
        f"{'FP':<6}"
        f"{'FN':<6}"
        f"{'Accuracy':<12}"
        f"{'PARA→ORIG':<12}"
        f"{'ORIG→PARA':<12}"
        f"{'COMMON→PARA':<14}"
    )
    print(header)
    print("  " + "-" * 88)

    best_f1_row = max(results, key=lambda x: x['f1'])
    best_balance_row = None
    # "Balance": penalize FP on ORIGINAL/COMMON harshly
    def balance_score(r):
        return r['f1'] - 0.3 * (r['ORIG→PARA'] + r['COMMON→PARA'])

    best_balance_row = max(results, key=balance_score)

    for r in results:
        flags = []
        if r['threshold'] == best_f1_row['threshold']:
            flags.append('★ best F1')
        if r['threshold'] == best_balance_row['threshold'] and best_balance_row['threshold'] != best_f1_row['threshold']:
            flags.append('✦ best balance')
        flag_str = '  '.join(flags)

        line = (
            f"  {r['threshold']:<12.2f}"
            f"{r['precision']:<12.4f}"
            f"{r['recall']:<10.4f}"
            f"{r['f1']:<10.4f}"
            f"{r['tp']:<6}"
            f"{r['fp']:<6}"
            f"{r['fn']:<6}"
            f"{r['accuracy']:<12.4f}"
            f"{r['PARA→ORIG']:<12}"
            f"{r['ORIG→PARA']:<12}"
            f"{r['COMMON→PARA']:<14}"
        )
        if flag_str:
            line += f"  ← {flag_str}"
        print(line)

    print("─" * 90)

    # ─── جدول تفصيل الخلط ────────────────────────────────────────────────────
    print("\n" + "─" * 90)
    print("  تفصيل خلط PARAPHRASE مع الفئات المجاورة:")
    print("─" * 90)
    header2 = (
        f"  {'Threshold':<12}"
        f"{'PARA→ORIG':<14}"
        f"{'PARA→COMMON':<14}"
        f"{'PARA→MODIFIED':<16}"
        f"{'ORIG→PARA':<12}"
        f"{'COMMON→PARA':<14}"
        f"{'MODIFIED→PARA':<14}"
    )
    print(header2)
    print("  " + "-" * 88)
    for r in results:
        print(
            f"  {r['threshold']:<12.2f}"
            f"{r['PARA→ORIG']:<14}"
            f"{r['PARA→COMMON']:<14}"
            f"{r['PARA→MODIFIED']:<16}"
            f"{r['ORIG→PARA']:<12}"
            f"{r['COMMON→PARA']:<14}"
            f"{r['MODIFIED→PARA']:<14}"
        )
    print("─" * 90)

    # ─── مصفوفة ارتباك لأفضل عتبة توازن ─────────────────────────────────────
    print("\n" + "─" * 90)
    print(f"  مصفوفة الارتباك الكاملة للعتبة الأفضل توازناً (threshold={best_balance_row['threshold']:.2f}):")
    print_full_confusion(best_balance_row['confusion'], best_balance_row['threshold'])

    print("\n" + "─" * 90)
    print(f"  مصفوفة الارتباك الكاملة للعتبة ذات أعلى F1 (threshold={best_f1_row['threshold']:.2f}):")
    print_full_confusion(best_f1_row['confusion'], best_f1_row['threshold'])

    # ─── تحليل وتوصية ────────────────────────────────────────────────────────
    print("\n" + "=" * 90)
    print("  التحليل والتوصية:")
    print("=" * 90)
    print()
    print("  sample_3 (PARAPHRASE الأعمق): Jaccard=0 وTF-IDF word=0 لأن المفردات مختلفة")
    print("  كلياً (الدول المتقدمة↔الحكومات الحديثة / الذكاء الاصطناعي↔تعلم الآلة).")
    print("  TF-IDF الحرفي وحده يُعطي ~0.21 وهو على حافة العتبة 0.20 لكن الصيغة الممزوجة")
    print("  (0.7*word + 0.3*char) تُخفّضه إلى ~0.06 لأن word_cos=0.")
    print()
    print("  ⇒ الخلل البنيوي: دالة max(word_cos, 0.7*word_cos + 0.3*char_cos) لا تُعطي وزناً")
    print("    كافياً للتشابه الحرفي المورفولوجي حين يكون word_cos صفراً.")
    print()
    print("  ⇒ تخفيض العتبة لن يحل المشكلة: حتى عند 0.10 ستبقى sample_3 تحت العتبة")
    print("    لأن الblended score=0.06 وليس بسبب العتبة نفسها بل بسبب صيغة الدمج.")
    print()
    print("  ⇒ الحل الحقيقي يتطلب إحدى البدائل:")
    print("    (أ) تغيير صيغة الدمج لإعطاء وزن أعلى للchar_cos حين word_cos < 0.05")
    print("    (ب) إضافة نموذج دلالي أوفلاين (fastembed) لالتقاط paraphrase الدلالي")
    print("    (ج) بناء قاموس مرادفات تقني عربي للمجال الأمني")
    print()
    print("  ⚠️  لا تُعدَّل العتبة الإنتاجية (0.20) حتى تُستكمل هذه الدراسة على")
    print("      مجموعة بيانات أوسع ومستقلة.")
    print("=" * 90)
    print()
    print("  ⚠️  تحذير أكاديمي (Academic Disclaimer):")
    print("  هذه النتائج مبنية على مجموعة بيانات تطويرية محلية مؤلّفة يدوياً ({} عينة)".format(total))
    print("  وليست بنشمارك أكاديمياً معتمداً. لا يجوز الاستشهاد بهذه الأرقام كمقياس للدقة")
    print("  العامة للنظام دون تقييم مستقل على بيانات حقيقية ومتنوعة.")
    print("=" * 90)


if __name__ == '__main__':
    main()
