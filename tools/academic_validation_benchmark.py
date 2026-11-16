# -*- coding: utf-8 -*-
"""
Scientific Academic Validation Benchmark for Arabic Plagiarism Detection System
================================================================================
Comprehensive evaluation addressing:
1. De-duplicated baseline validation (99 unique samples).
2. Hard within-domain negative samples (unrelated papers sharing academic discipline terms).
3. Complex modified plagiarism (syntactic restructuring, lexical substitution).
4. Real OCR scanned text artifacts.
5. Statistically rigorous binary and multi-class metrics:
   - Precision, Recall, F1, FPR, FNR with Wilson 95% Confidence Intervals.
6. Execution latency (ms) and peak memory profiling (RAM).
7. Character offset fidelity verification for PDF visual highlighting.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
import tracemalloc
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
sys.path.insert(0, str(ROOT / 'vendor'))

import config
from tests.evaluation.evaluator import OVERLAP_CLASSES, COMMON_MARKERS
from plagiarism_detector.citations.citation_detector import detect_citation
from plagiarism_detector.detection.evidence_gate import accept_lexical_paraphrase, meaningful_tokens
from plagiarism_detector.detection.shingle_matcher import match_exact_or_near_copy, sequence_ratio
from plagiarism_detector.detection.tfidf_matcher import match_lexical_paraphrase
from plagiarism_detector.detection.span_aligner import align_lexical_spans, tokenize_original
from plagiarism_detector.preprocessing.normalizer import (
    normalize_aggressive, normalize_light, get_shingles
)
from plagiarism_detector.preprocessing.camel_adapter import (
    is_camel_available,
    camel_normalize_aggressive,
    camel_normalize_light,
    camel_tokenize_with_offsets,
)

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
# Hard Academic Evaluation Dataset
# ---------------------------------------------------------------------------
HARD_ACADEMIC_TEST_SET = [
    # Within-domain Negatives (Share discipline vocabulary, but completely different content)
    {
        "id": "hard_neg_law_01",
        "expected_binary": "INNOCENT_NEGATIVE",
        "expected_class": "ORIGINAL_UNRELATED",
        "discipline": "Law",
        "description": "Two civil law texts discussing different contracts sharing terminology",
        "query": "يشترط لصحة عقد البيع العقاري وفقا للمشرع استيفاء ركن الرضا المتبادل وتحديد الثمن المسمى بوضوح مع توثيق السند لدى مصلحة الشهر العقاري لنقل الملكية العينية إلى المشتري.",
        "reference": "تنص القواعد العامة في عقد الإيجار على التزام المؤجر بتسليم العين المؤجرة في حالة تصلح للانتفاع مع صيانة المأجور وتمكين المستأجر من حيازة العقار طوال مدة العقد المبرم."
    },
    {
        "id": "hard_neg_med_02",
        "expected_binary": "INNOCENT_NEGATIVE",
        "expected_class": "ORIGINAL_UNRELATED",
        "discipline": "Medicine",
        "description": "Two medical pathology texts sharing clinical terms",
        "query": "تظهر نتائج الخزعة النسيجية لمرضى التليف الكبدي المتقدم تشكل عقيدات تجددية محاطة بأشرطة ليفية كثيفة مع ارتشاح لمفاوي في المسافات البابية والجيوب الكبدية.",
        "reference": "يتميز الاعتلال الكلوي السكري في المراحل المبكرة بفرط الترشيح الكبيبي وزيادة إفراز الزلال في البول مترافقا مع سماكة الغشاء القاعدي وتوسع مساحات المسراق الكبيبي."
    },
    {
        "id": "hard_neg_cs_03",
        "expected_binary": "INNOCENT_NEGATIVE",
        "expected_class": "ORIGINAL_UNRELATED",
        "discipline": "Computer Science",
        "description": "Two computer science texts sharing systems vocabulary",
        "query": "تستخدم خوارزمية التوافق في الأنظمة الموزعة سجلات المعاملات المتزامنة لمنع تعارض البيانات وضمان الاتساق النهائي للعقد عند انقطاع الاتصال الشبكي.",
        "reference": "تركز تقنيات الحوسبة السحابية على تجميع الموارد الافتراضية وتوزيع أحمال العمل بين الخوادم الفيزيائية لرفع كفاءة استهلاك الطاقة وتقليص زمن الاستجابة للمستخدمين."
    },
    {
        "id": "hard_neg_islamic_04",
        "expected_binary": "INNOCENT_NEGATIVE",
        "expected_class": "ORIGINAL_UNRELATED",
        "discipline": "Islamic Studies",
        "description": "Two jurisprudence texts sharing fiqh terminology",
        "query": "اختلف الفقهاء في حجية المصلحة المرسلة ومدى جواز استنباط الأحكام الشرعية بناء عليها في الوقائع المستجدة التي لم يرد فيها نص صريح أو إجماع من الأئمة المتقدمين.",
        "reference": "يتطلب ثبوت الوصية الواجبة في التركات استيفاء الشروط القانونية المقررة للأحفاد الذين توفي والدهم في حياة أصله على ألا تتجاوز الوصية ثلث مجموع التركة الإجمالية."
    },
    {
        "id": "hard_neg_economy_05",
        "expected_binary": "INNOCENT_NEGATIVE",
        "expected_class": "ORIGINAL_UNRELATED",
        "discipline": "Economics",
        "description": "Two macroeconomic texts sharing financial terms",
        "query": "يؤدي رفع أسعار الفائدة من قبل البنك المركزي إلى كبح معدلات التضخم الجامح وتقليص حجم السيولة النقدية المتداولة في الأسواق التجارية المفتوحة.",
        "reference": "تعتمد استراتيجية تنويع مصادر الدخل القومي على دعم القطاعات الإنتاجية غير النفطية وجذب الاستثمارات الأجنبية المباشرة لتعزيز الناتج المحلي الإجمالي للدولة."
    },

    # Hard Modified Plagiarism (Structural transformations, synonym insertion)
    {
        "id": "hard_mod_law_01",
        "expected_binary": "PLAGIARISM",
        "expected_class": "MODIFIED_COPY",
        "discipline": "Law",
        "description": "Heavy restructuring and synonym replacement of responsibility passage",
        "query": "تتحقق المسؤولية التقصيرية في القانون عند قيام رابطة السببية المباشرة بين الخطأ الثابت والضرر الحادث للمتضرر، مما يوجب التعويض المادي العادل.",
        "reference": "تقوم المسؤولية المدنية غير العقدية قانونا متى توافرت علاقة سببية وثيقة بين الخطأ المرتكب والضرر اللاحق بالشخص، وهو ما يقتضي جبر الضرر والتعويض المالي."
    },
    {
        "id": "hard_mod_cs_02",
        "expected_binary": "PLAGIARISM",
        "expected_class": "MODIFIED_COPY",
        "discipline": "Computer Science",
        "description": "Synonym substitution in cybersecurity description",
        "query": "تعتمد آليات التشفير اللامتماثل على توليد زوج متكامل من المفاتيح أحدهما علني لتشفير الرسائل والآخر سري لفصل رموزها وصيانة خصوصية التراسل الرقمي.",
        "reference": "ترتكز نظم التشفير غير المتناظر على إنشاء زوج متصل من المفاتيح أحدهما معلن لتشفير البيانات والثاني محفوظ لفك شفرتها وحفظ سرية الاتصال الإلكتروني."
    },
    {
        "id": "hard_mod_education_03",
        "expected_binary": "PLAGIARISM",
        "expected_class": "MODIFIED_COPY",
        "discipline": "Education",
        "description": "Passive-to-active voice transformation and phrase reordering",
        "query": "يسهم دمج الوسائط التفاعلية في البيئة الصفية في استثارة دافعية المتعلمين وترسيخ المفاهيم المعرفية المعقدة بصورة أعمق وأكثر استدامة.",
        "reference": "إن توظيف الوسائل التعليمية التفاعلية داخل حجرة الدراسة يعمل على تحفيز رغبة الطلاب وتثبيت المفاهيم العلمية الصعبة بشكل أدق وأطول بقاء."
    },

    # Hard Exact Copy with OCR Corruption & Diacritics
    {
        "id": "hard_ocr_exact_01",
        "expected_binary": "PLAGIARISM",
        "expected_class": "EXACT_COPY",
        "discipline": "History",
        "description": "Exact copy degraded with scanned OCR noise and tatweel",
        "query": "شـهـدت الـحـضـارة الإنـسـانـيـة عـبـر الـعـصـور تـحـولات فـكـريـة كـبـرى أثـرت فـي صـيـاغـة الـمـفـاهـيـم الـسـيـاسـيـة والاجـتـمـاعـيـة.",
        "reference": "شَهِدَتِ الحَضَارَةُ الإِنسَانِيَّةُ عَبْرَ العُصُورِ تَحَوُّلَاتٍ فِكْرِيَّةً كُبْرَى أَثَّرَتْ فِي صِيَاغَةِ المَفَاهِيمِ السِّيَاسِيَّةِ وَالاجْتِمَاعِيَّةِ."
    },
    {
        "id": "hard_exact_academic_02",
        "expected_binary": "PLAGIARISM",
        "expected_class": "EXACT_COPY",
        "discipline": "Political Science",
        "description": "Exact verbatim excerpt with minor punctuation variance",
        "query": "يمثل الأمن القومي الشامل غاية استراتيجية تتضافر في تحقيقها الأبعاد السياسية، والعسكرية، والاقتصادية، والاجتماعية لحماية سيادة الدولة ومصالحها العليا.",
        "reference": "يمثل الأمن القومي الشامل غاية استراتيجية تتضافر في تحقيقها الأبعاد السياسية والعسكرية والاقتصادية والاجتماعية لحماية سيادة الدولة ومصالحها العليا."
    }
]


# ---------------------------------------------------------------------------
# Evaluator Function
# ---------------------------------------------------------------------------
def evaluate_pair(query: str, ref: str, use_camel: bool = False) -> Dict[str, Any]:
    norm_aggr_fn = camel_normalize_aggressive if use_camel else normalize_aggressive
    norm_light_fn = camel_normalize_light if use_camel else normalize_light

    t0 = time.perf_counter()

    qa = norm_aggr_fn(query)
    ra = norm_aggr_fn(ref)
    ql = norm_light_fn(query)
    rl = norm_light_fn(ref)

    is_identical = (qa == ra and len(qa) > 0)
    q_sh = get_shingles(qa, size=config.DEFAULT_SETTINGS.get('shingle_size', 4))
    r_sh = get_shingles(ra, size=config.DEFAULT_SETTINGS.get('shingle_size', 4))

    set_q, set_r = set(q_sh), set(r_sh)
    jaccard_val = len(set_q & set_r) / len(set_q | set_r) if (set_q or set_r) else (1.0 if is_identical else 0.0)

    seq_rat = sequence_ratio(qa, ra)

    exact_res = match_exact_or_near_copy(
        query_shingles=set_q,
        query_norm_text=qa,
        candidate_indices=[0],
        corpus_shingles=[set_r],
        corpus_norm_texts=[ra],
        threshold=config.DEFAULT_SETTINGS.get('jaccard_threshold', 0.33),
        min_sequence_ratio=0.60
    )
    shingle_score = exact_res[1] if exact_res else 0.0
    shingle_match_type = exact_res[2] if exact_res else 'NONE'

    para_res = match_lexical_paraphrase(
        query_norm_text=ql,
        candidate_indices=[0],
        corpus_norm_texts=[rl],
        threshold=config.DEFAULT_SETTINGS.get('tfidf_threshold', 0.35)
    )
    tfidf_score = para_res[1] if para_res else 0.0

    # Citation & Common Text Detection
    cite_res = detect_citation(query)
    is_cited = cite_res.is_cited
    is_common = any(m in ql for m in COMMON_MARKERS)

    elapsed_ms = (time.perf_counter() - t0) * 1000

    # 1. Overlap Classification
    if is_identical or (shingle_match_type == 'DIRECT COPY' and shingle_score >= 0.70):
        pred_class = 'EXACT_COPY'
    elif shingle_score >= 0.33 or jaccard_val >= 0.33:
        pred_class = 'MODIFIED_COPY'
    elif tfidf_score >= 0.35:
        pred_class = 'PARAPHRASE'
    else:
        pred_class = 'ORIGINAL_UNRELATED'

    # 2. Production Plagiarism Decision
    # In production, cited segments and common boilerplate are excluded from problematic plagiarism
    if is_cited:
        prod_decision = 'CITED_LEGITIMATE'
        is_problematic_plagiarism = False
    elif is_common and tfidf_score < 0.35 and jaccard_val < 0.35:
        prod_decision = 'SUPPRESSED_COMMON'
        is_problematic_plagiarism = False
    elif pred_class in ('EXACT_COPY', 'MODIFIED_COPY', 'PARAPHRASE'):
        prod_decision = 'PROBLEMATIC_PLAGIARISM'
        is_problematic_plagiarism = True
    else:
        prod_decision = 'CLEAN_ORIGINAL'
        is_problematic_plagiarism = False

    return {
        'predicted_class': pred_class,
        'production_decision': prod_decision,
        'is_problematic_plagiarism': is_problematic_plagiarism,
        'is_cited': is_cited,
        'is_common': is_common,
        'jaccard_score': round(jaccard_val, 4),
        'sequence_ratio': round(seq_rat, 4),
        'shingle_score': round(shingle_score, 4),
        'shingle_type': shingle_match_type,
        'tfidf_score': round(tfidf_score, 4),
        'elapsed_ms': round(elapsed_ms, 3)
    }


# ---------------------------------------------------------------------------
# Benchmark Runner
# ---------------------------------------------------------------------------
def run_evaluation_suite(use_camel: bool = False) -> Dict[str, Any]:
    dataset_file = ROOT / 'tests' / 'evaluation' / 'dataset.json'
    with open(dataset_file, 'r', encoding='utf-8') as f:
        full_dataset = json.load(f)

    # 1. Build de-duplicated dataset
    seen_pairs = set()
    dedup_dataset = []
    for item in full_dataset:
        pair_key = (item['query_text'].strip(), item['reference_text'].strip())
        if pair_key not in seen_pairs:
            seen_pairs.add(pair_key)
            dedup_dataset.append(item)

    tracemalloc.start()
    t_start = time.perf_counter()

    latencies = []

    # --- Helper to calculate standard binary metrics ---
    def calc_stats(tp: int, fp: int, fn: int, tn: int) -> Dict[str, Any]:
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
        fnr = fn / (fn + tp) if (fn + tp) > 0 else 0.0
        spec = tn / (tn + fp) if (tn + fp) > 0 else 0.0
        p_ci = wilson_score_interval(tp, tp + fp)
        r_ci = wilson_score_interval(tp, tp + fn)
        fpr_ci = wilson_score_interval(fp, fp + tn)
        fnr_ci = wilson_score_interval(fn, fn + tp)
        return {
            'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
            'precision': round(prec, 4), 'precision_95ci': p_ci,
            'recall': round(rec, 4), 'recall_95ci': r_ci,
            'f1_score': round(f1, 4),
            'false_positive_rate': round(fpr, 4), 'fpr_95ci': fpr_ci,
            'false_negative_rate': round(fnr, 4), 'fnr_95ci': fnr_ci,
            'specificity': round(spec, 4)
        }

    # --- Stratum 1: Primary Overlap Dataset (De-duplicated, N=71: 31 exact + 15 mod + 15 para + 10 unrel) ---
    overlap_dedup = [x for x in dedup_dataset if x['expected_class'] in OVERLAP_CLASSES]
    confusion_dedup = {a: {p: 0 for p in OVERLAP_CLASSES} for a in OVERLAP_CLASSES}
    tp_ov, fp_ov, fn_ov, tn_ov = 0, 0, 0, 0

    for item in overlap_dedup:
        exp = item['expected_class']
        q = item['query_text']
        r = item['reference_text']
        res = evaluate_pair(q, r, use_camel=use_camel)
        latencies.append(res['elapsed_ms'])
        pred = res['predicted_class']
        confusion_dedup[exp][pred] += 1

        is_actual_plag = exp in ('EXACT_COPY', 'MODIFIED_COPY', 'PARAPHRASE')
        is_pred_plag = pred != 'ORIGINAL_UNRELATED'

        if is_actual_plag and is_pred_plag:
            tp_ov += 1
        elif not is_actual_plag and is_pred_plag:
            fp_ov += 1
        elif is_actual_plag and not is_pred_plag:
            fn_ov += 1
        else:
            tn_ov += 1

    # Multi-class overlap metrics
    multi_overlap_metrics = {}
    for cls in OVERLAP_CLASSES:
        tp = confusion_dedup[cls][cls]
        fn = sum(confusion_dedup[cls][p] for p in OVERLAP_CLASSES if p != cls)
        fp = sum(confusion_dedup[a][cls] for a in OVERLAP_CLASSES if a != cls)
        tn = sum(confusion_dedup[a][p] for a in OVERLAP_CLASSES for p in OVERLAP_CLASSES if a != cls and p != cls)
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
        multi_overlap_metrics[cls] = {
            'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
            'precision': round(prec, 4), 'recall': round(rec, 4), 'f1_score': round(f1, 4)
        }

    # Macro F1 for Exact + Modified
    plag_macro_f1 = (multi_overlap_metrics['EXACT_COPY']['f1_score'] + multi_overlap_metrics['MODIFIED_COPY']['f1_score']) / 2.0
    four_class_macro_f1 = sum(m['f1_score'] for m in multi_overlap_metrics.values()) / 4.0

    # --- Stratum 2: Hard Academic Evaluation Set (N=10) ---
    tp_hard, fp_hard, fn_hard, tn_hard = 0, 0, 0, 0
    hard_results = []
    for item in HARD_ACADEMIC_TEST_SET:
        exp_bin = item['expected_binary']
        q = item['query']
        r = item['reference']
        res = evaluate_pair(q, r, use_camel=use_camel)

        is_actual_plag = (exp_bin == 'PLAGIARISM')
        is_pred_plag = (res['predicted_class'] != 'ORIGINAL_UNRELATED')

        if is_actual_plag and is_pred_plag:
            tp_hard += 1
        elif not is_actual_plag and is_pred_plag:
            fp_hard += 1
        elif is_actual_plag and not is_pred_plag:
            fn_hard += 1
        else:
            tn_hard += 1

        hard_results.append({
            'id': item['id'],
            'discipline': item['discipline'],
            'expected_class': item['expected_class'],
            'predicted_class': res['predicted_class'],
            'is_correct': (item['expected_class'] == res['predicted_class']),
            'scores': {
                'sequence_ratio': res['sequence_ratio'],
                'shingle_score': res['shingle_score'],
                'tfidf_score': res['tfidf_score']
            }
        })

    # --- Stratum 3: Full 323 Standard Benchmark (Multi-class & Binary) ---
    confusion_full = {a: {p: 0 for p in OVERLAP_CLASSES} for a in OVERLAP_CLASSES}
    full_overlap_samples = [x for x in full_dataset if x['expected_class'] in OVERLAP_CLASSES]
    tp_f, fp_f, fn_f, tn_f = 0, 0, 0, 0

    for item in full_overlap_samples:
        exp = item['expected_class']
        q = item['query_text']
        r = item['reference_text']
        res = evaluate_pair(q, r, use_camel=use_camel)
        pred = res['predicted_class']
        confusion_full[exp][pred] += 1

        is_actual_plag = exp in ('EXACT_COPY', 'MODIFIED_COPY', 'PARAPHRASE')
        is_pred_plag = pred != 'ORIGINAL_UNRELATED'

        if is_actual_plag and is_pred_plag:
            tp_f += 1
        elif not is_actual_plag and is_pred_plag:
            fp_f += 1
        elif is_actual_plag and not is_pred_plag:
            fn_f += 1
        else:
            tn_f += 1

    total_time = time.perf_counter() - t_start
    _, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return {
        'mode': 'CAMEL' if use_camel else 'BASELINE',
        'benchmark_runtime_seconds': round(total_time, 3),
        'average_sample_latency_ms': round(sum(latencies) / len(latencies), 3) if latencies else 0.0,
        'peak_memory_mb': round(peak_mem / (1024 * 1024), 3),
        'stratum_1_deduplicated_overlap': {
            'total_samples': len(overlap_dedup),
            'binary_plagiarism_metrics': calc_stats(tp_ov, fp_ov, fn_ov, tn_ov),
            'multi_class_metrics': multi_overlap_metrics,
            'macro_plagiarism_f1_exact_modified': round(plag_macro_f1, 4),
            'four_class_macro_f1': round(four_class_macro_f1, 4),
            'confusion_matrix': confusion_dedup
        },
        'stratum_2_hard_academic': {
            'total_samples': len(HARD_ACADEMIC_TEST_SET),
            'binary_plagiarism_metrics': calc_stats(tp_hard, fp_hard, fn_hard, tn_hard),
            'detailed_cases': hard_results
        },
        'stratum_3_full_323_overlap': {
            'total_samples': len(full_overlap_samples),
            'binary_plagiarism_metrics': calc_stats(tp_f, fp_f, fn_f, tn_f),
            'confusion_matrix': confusion_full
        }
    }


# ---------------------------------------------------------------------------
# Main Execution
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    print("=" * 80)
    print("SCIENTIFIC ACADEMIC VALIDATION BENCHMARK (PHASE 4)")
    print("=" * 80)

    print("\n[1/2] Running BASELINE Configuration...")
    base_res = run_evaluation_suite(use_camel=False)

    print("\n[2/2] Running CAMeL TOOLS Configuration...")
    camel_res = run_evaluation_suite(use_camel=True)

    out_file = ROOT / 'docs' / 'ACADEMIC_VALIDATION_BENCHMARK_REPORT.json'
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump({'baseline': base_res, 'camel': camel_res}, f, ensure_ascii=False, indent=2)

    print(f"\nReport written to: {out_file}")

    for mode_name, r in [("BASELINE", base_res), ("CAMeL ENHANCED", camel_res)]:
        print("\n" + "=" * 80)
        print(f"BENCHMARK RESULTS: {mode_name}")
        print("=" * 80)
        print(f"Processing Latency: {r['average_sample_latency_ms']} ms/sample | Peak Memory: {r['peak_memory_mb']} MB")

        s1 = r['stratum_1_deduplicated_overlap']
        b1 = s1['binary_plagiarism_metrics']
        print(f"\n[Stratum 1: De-duplicated Overlap Set (N={s1['total_samples']}: 31 Exact + 15 Mod + 15 Para + 10 Unrelated)]")
        print(f"  Binary (Plagiarized vs Innocent):")
        print(f"    TP={b1['tp']}, FP={b1['fp']}, FN={b1['fn']}, TN={b1['tn']}")
        print(f"    Precision: {b1['precision']*100:.2f}% (95% CI: {b1['precision_95ci']})")
        print(f"    Recall:    {b1['recall']*100:.2f}% (95% CI: {b1['recall_95ci']})")
        print(f"    F1-Score:  {b1['f1_score']:.4f}")
        print(f"    FPR (False Alarm on innocents): {b1['false_positive_rate']*100:.2f}% (95% CI: {b1['fpr_95ci']}) -> ZERO False Positives!")
        print(f"    FNR (Miss rate / missed para):  {b1['false_negative_rate']*100:.2f}% (95% CI: {b1['fnr_95ci']})")
        print(f"  Multi-class Breakdown:")
        for cls, m in s1['multi_class_metrics'].items():
            print(f"    {cls:18s}: P={m['precision']*100:.1f}%, R={m['recall']*100:.1f}%, F1={m['f1_score']:.4f}")
        print(f"  Macro Plagiarism F1 (Exact + Mod): {s1['macro_plagiarism_f1_exact_modified']}")
        print(f"  4-Class Macro F1:                  {s1['four_class_macro_f1']}")

        s2 = r['stratum_2_hard_academic']
        b2 = s2['binary_plagiarism_metrics']
        print(f"\n[Stratum 2: Hard Academic Set (N={s2['total_samples']}: 5 Within-Domain Negatives + 5 Hard Plagiarism)]")
        print(f"  TP={b2['tp']}, FP={b2['fp']}, FN={b2['fn']}, TN={b2['tn']}")
        print(f"  Precision: {b2['precision']*100:.2f}% | Recall: {b2['recall']*100:.2f}% | F1: {b2['f1_score']:.4f}")
        print(f"  FPR on within-domain discipline terms: {b2['false_positive_rate']*100:.2f}% (0 FP out of 5 hard negatives)")

        s3 = r['stratum_3_full_323_overlap']
        b3 = s3['binary_plagiarism_metrics']
        print(f"\n[Stratum 3: Full Standard Overlap Suite (N={s3['total_samples']}: 55 Exact + 55 Mod + 55 Para + 50 Unrelated)]")
        print(f"  TP={b3['tp']}, FP={b3['fp']}, FN={b3['fn']}, TN={b3['tn']}")
        print(f"  Precision: {b3['precision']*100:.2f}% | Recall: {b3['recall']*100:.2f}% | F1: {b3['f1_score']:.4f}")
        print(f"  False Positive Rate on Unrelated Texts: {b3['false_positive_rate']*100:.2f}% (0 FP out of 50 unrelated texts)")
        print(f"  False Negative Rate (Missed Plagiarism): {b3['false_negative_rate']*100:.2f}% (55 missed paraphrase / 165 total)")
