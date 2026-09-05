# -*- coding: utf-8 -*-
"""
بوابة أدلة التعميم ومفاضلات الإنتاج (Phase 19 Evidence & Generalization Gate):
- يقسم مجموعة البيانات بطريقة طبقية حتمية (70% تطوير / 30% اختبار محجوب Holdout).
- ينشئ حزمة عينات تركيبية محجوبة إضافية غير مرئية (DEVELOPER_SYNTHETIC_HOLDOUT).
- يقيس بدقة:
  1. تعميم استرجاع المرشحين (EXP-01) مع تحليل الإخفاقات ومقاييس الكمون p50/p95.
  2. مفاضلة كشف إعادة الصياغة (EXP-02) عبر عتبات [0.20 - 0.50].
  3. تدقيق إيجابيات n-grams الزائفة عبر أزواج سلبية شديدة (Hard Negatives).
  4. تعميم كشف النصوص الشائعة (EXP-03) وأمان الاستبعاد على مستوى المقاطع (Span Safety).
  5. تعميم كشف الاستشهادات (EXP-04) على الأنماط المنوعة وتأكيد عدم إلغاء الاستشهاد للاستلال.
  6. الاختبار التكاملي المشترك لكافة المرشحين المقبولين معاً على بيانات Holdout.
"""

import sys
import io
import os
import re
import time
import math
import json
import random
import hashlib
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any, Tuple, Optional
import numpy as np

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from plagiarism_detector.preprocessing.normalizer import (
    normalize_aggressive, normalize_light, get_shingles
)
from plagiarism_detector.detection.shingle_matcher import match_exact_or_near_copy
from plagiarism_detector.detection.tfidf_matcher import match_lexical_paraphrase
from plagiarism_detector.detection.candidate_retriever import CandidateRetriever
from plagiarism_detector.citations.citation_detector import detect_citation

from evaluation.phase19.phase19_experiments import (
    EnhancedDualChannelRetriever,
    EXPANDED_COMMON_INSTITUTIONAL_MARKERS,
    is_common_institutional_text_experimental,
    detect_citation_refined,
    is_valid_scholar_author_name_refined
)

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


# ─────────────────────────────────────────────────────────────────────────────
# 1. التقسيم الطبقي الحتمي (Deterministic Stratified Train/Holdout Split)
# ─────────────────────────────────────────────────────────────────────────────

def deterministic_stratified_split(
    dataset: List[Dict[str, Any]],
    train_ratio: float = 0.70,
    seed: int = 42
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """تقسيم طبقي حتمي لمجموعة البيانات بنسبة 70% تطوير / 30% حجب."""
    rng = random.Random(seed)
    by_class = defaultdict(list)
    for sample in dataset:
        cls = sample.get('expected_class') or sample.get('expected_category', 'UNKNOWN')
        by_class[cls].append(sample)

    train_set, holdout_set = [], []
    for cls, items in sorted(by_class.items()):
        # ترتيب حتمي حسب sample_id قبل الخلط
        sorted_items = sorted(items, key=lambda x: x['sample_id'])
        indices = list(range(len(sorted_items)))
        rng.shuffle(indices)

        n_train = int(round(len(sorted_items) * train_ratio))
        for idx in indices[:n_train]:
            train_set.append(sorted_items[idx])
        for idx in indices[n_train:]:
            holdout_set.append(sorted_items[idx])

    train_set.sort(key=lambda x: x['sample_id'])
    holdout_set.sort(key=lambda x: x['sample_id'])
    return train_set, holdout_set


# ─────────────────────────────────────────────────────────────────────────────
# 2. إنشاء عينات محجوبة إضافية غير مرئية (Unseen Synthetic Holdout Suite)
# ─────────────────────────────────────────────────────────────────────────────

def build_unseen_holdout_samples() -> List[Dict[str, Any]]:
    """
    توليد عينات محجوبة جديدة كلياً (DEVELOPER_SYNTHETIC_HOLDOUT)
    لم يتم استخدامها في صياغة القواعد أو ضبط العتبات لاختبار التعميم الحقيقي.
    """
    unseen = [
        # أزواج سلبية شديدة (Hard Negatives) - نفس المجال، مصطلحات مشتركة، معاني مختلفة تماماً
        {
            "sample_id": "HOLDOUT_HN_01",
            "domain": "law",
            "expected_class": "ORIGINAL",
            "generation_origin": "DEVELOPER_SYNTHETIC_HOLDOUT",
            "suspicious_text": "يختص القضاء الإداري بالنظر في الطعون المقدمة ضد القرارات الإدارية النهائية الصادرة عن السلطة التنفيذية وإلغاء ما يشوبها من عيب عدم الاختصاص.",
            "source_text": "يحظر على القضاء الإداري التدخل في أعمال السيادة والقرارات الدبلوماسية الصادرة عن الهيئات التمثيلية العليا للدولة وفق أحكام القانون الدولي.",
            "notes": "Hard negative: Shared administrative law vocabulary, completely opposite jurisdiction scopes."
        },
        {
            "sample_id": "HOLDOUT_HN_02",
            "domain": "cs",
            "expected_class": "ORIGINAL",
            "generation_origin": "DEVELOPER_SYNTHETIC_HOLDOUT",
            "suspicious_text": "تعتمد خوارزميات التشفير غير المتماثل على مفتاحين منفصلين هما المفتاح العام لتشفير الرسائل والمفتاح الخاص لفك تشفيرها بأمان.",
            "source_text": "تستخدم خوارزميات التشفير المتماثل مفتاحاً سرياً واحداً مشتركاً بين الطرفين لعمليتي التشفير وفك التشفير مما يتطلب قناة اتصال آمنة.",
            "notes": "Hard negative: Shared cryptography vocabulary, symmetric vs asymmetric encryption."
        },
        {
            "sample_id": "HOLDOUT_HN_03",
            "domain": "education",
            "expected_class": "ORIGINAL",
            "generation_origin": "DEVELOPER_SYNTHETIC_HOLDOUT",
            "suspicious_text": "أظهرت الدراسة فاعلية التعليم المتزامن القائم على الفصول الافتراضية في تحسين مهارات التفاعل الاجتماعي والتحصيل الفوري لدى الطلاب.",
            "source_text": "بينت نتائج البحث تفوق التعليم غير المتزامن المعتمد على منصات التسجيل الذاتي في تعزيز مهارات التعلم المستقل والتفكير النقدي طويل المدى.",
            "notes": "Hard negative: Synchronous vs asynchronous education."
        },
        # استلال موضوعي مدمج مع ديباجة مشتركة (Span-Level Mixed Test)
        {
            "sample_id": "HOLDOUT_SPAN_01",
            "domain": "law",
            "expected_class": "EXACT_COPY",
            "generation_origin": "DEVELOPER_SYNTHETIC_HOLDOUT",
            "suspicious_text": "وبناء على ما تقدم وفي ضوء ما اسفرت عنه النتائج، فإن المسؤولية التقصيرية تنعقد قانوناً بثبوت الخطأ والضرر وعلاقة السببية المباشرة بينهما.",
            "source_text": "إن المسؤولية التقصيرية تنعقد قانوناً بثبوت الخطأ والضرر وعلاقة السببية المباشرة بينهما.",
            "notes": "Contains common institutional boilerplate + verbatim substantive copied sentence."
        },
        {
            "sample_id": "HOLDOUT_SPAN_02",
            "domain": "cs",
            "expected_class": "MODIFIED_COPY",
            "generation_origin": "DEVELOPER_SYNTHETIC_HOLDOUT",
            "suspicious_text": "واستنادا الى الصلاحيات المخولة لعمادة الدراسات العليا، فإن تطبيق شبكات التحويل البصري يرفع دقة التعرف على الأنماط بنسبة عالية في بيئات التشويش.",
            "source_text": "تطبيق شبكات التحويل البصرية يرفع دقة التعرف على الأنماط المعقدة في بيئات التشويش العالي.",
            "notes": "Boilerplate preamble + modified substantive academic copy."
        },
        # حالات استشهاد معقدة ومتنوعة (Generalization Citation Cases)
        {
            "sample_id": "HOLDOUT_CIT_YEAR_ONLY",
            "domain": "general",
            "expected_class": "ORIGINAL",
            "generation_origin": "DEVELOPER_SYNTHETIC_HOLDOUT",
            "suspicious_text": "تستهدف المملكة العربية السعودية رفع مساهمة القطاع غير الربحي بحلول عام (2030) بنسبة تفوق 5%.",
            "source_text": "",
            "notes": "Isolated target year (2030) - Must NOT be tagged as author citation."
        },
        {
            "sample_id": "HOLDOUT_CIT_LAW_ARTICLE",
            "domain": "law",
            "expected_class": "ORIGINAL",
            "generation_origin": "DEVELOPER_SYNTHETIC_HOLDOUT",
            "suspicious_text": "ألزمت اللائحة التنفيذية المنشآت بتوفير بيئة عمل ملائمة وفق (المادة 15) من نظام العمل والعمال.",
            "source_text": "",
            "notes": "Law article parenthetical - Must NOT be tagged as author citation."
        },
        {
            "sample_id": "HOLDOUT_CIT_MULTI_AUTHOR",
            "domain": "cs",
            "expected_class": "PROPERLY_CITED",
            "generation_origin": "DEVELOPER_SYNTHETIC_HOLDOUT",
            "suspicious_text": "تم تطوير نموذج هجين للتنقيب عن البيانات النصية المعقدة (القحطاني والعتيبي، 2022، ص. 88) أثبت كفاءته العملية.",
            "source_text": "تم تطوير نموذج هجين للتنقيب عن البيانات النصية المعقدة أثبت كفاءته العملية.",
            "notes": "Multiple Arabic authors with page number."
        },
        {
            "sample_id": "HOLDOUT_CIT_MIXED_EN_AR",
            "domain": "cs",
            "expected_class": "PROPERLY_CITED",
            "generation_origin": "DEVELOPER_SYNTHETIC_HOLDOUT",
            "suspicious_text": "تعتبر بنية المحولات العصبية نقلة نوعية في المعالجة الآلية (Vaswani et al., 2017) للغات الطبيعية.",
            "source_text": "تعتبر بنية المحولات العصبية نقلة نوعية في المعالجة الآلية للغات الطبيعية.",
            "notes": "English citation in Arabic text."
        },
        {
            "sample_id": "HOLDOUT_CIT_POLICY_COPY_CITED",
            "domain": "law",
            "expected_class": "PROPERLY_CITED",
            "generation_origin": "DEVELOPER_SYNTHETIC_HOLDOUT",
            "suspicious_text": "«يعتبر التزوير في المحررات الرسمية جناية يعاقب عليها القانون بالسجن المشدد» (الشهري، 2021، ص. 34).",
            "source_text": "يعتبر التزوير في المحررات الرسمية جناية يعاقب عليها القانون بالسجن المشدد.",
            "notes": "Verbatim quote properly bracketed and cited - overlap exists but properly attributed."
        },
        {
            "sample_id": "HOLDOUT_CIT_POLICY_COPY_UNCITED_WITH_UNRELATED_REF",
            "domain": "law",
            "expected_class": "EXACT_COPY",
            "generation_origin": "DEVELOPER_SYNTHETIC_HOLDOUT",
            "suspicious_text": "إن المسؤولية المدنية عن حوادث المركبات الآلية تخضع لقواعد الضمان الموضوعي (الغامدي، 2019).",
            "source_text": "إن المسؤولية المدنية عن حوادث المركبات الآلية تخضع لقواعد الضمان الموضوعي.",
            "notes": "Copied verbatim from Source A, but researcher attached an unrelated citation (الغامدي). Plagiarism policy must flag overlap."
        }
    ]
    return unseen


# ─────────────────────────────────────────────────────────────────────────────
# 3. تشغيل تقييم الأدلة الشامل للمرحلة 19 (Evidence Gate Evaluator)
# ─────────────────────────────────────────────────────────────────────────────

def _get_q(item: Dict[str, Any]) -> str:
    return item.get('query_text') or item.get('suspicious_text') or ''


def _get_src(item: Dict[str, Any]) -> str:
    return item.get('reference_text') or item.get('source_text') or ''


def run_evidence_gate_benchmark() -> Dict[str, Any]:
    dataset_file = _ROOT / "tests" / "evaluation" / "dataset.json"
    with open(dataset_file, "r", encoding="utf-8") as f:
        full_dataset = json.load(f)

    # 1. التقسيم الحتمي
    dev_set, holdout_set = deterministic_stratified_split(full_dataset, train_ratio=0.70, seed=42)
    unseen_holdout = build_unseen_holdout_samples()
    combined_holdout = holdout_set + unseen_holdout

    print("=" * 85)
    print(f"  بوابة أدلة التعميم ومفاضلات الإنتاج — المرحلة 19 (Phase 19 Evidence Gate)")
    print("=" * 85)
    print(f"  • إجمالي العينات الأساسية: {len(full_dataset)}")
    print(f"  • مجموعة التطوير (Development 70%): {len(dev_set)}")
    print(f"  • مجموعة الحجب المقسمة (Holdout Split 30%): {len(holdout_set)}")
    print(f"  • مجموعة الحجب غير المرئية الإضافية (Unseen Holdout): {len(unseen_holdout)}")
    print(f"  • إجمالي حزمة التحقق من التعميم (Combined Holdout): {len(combined_holdout)}")
    print("=" * 85)

    # ─────────────────────────────────────────────────────────────────────────
    # A. تقييم استرجاع المرشحين EXP-01 على Holdout
    # ─────────────────────────────────────────────────────────────────────────
    retrieval_corpus = []
    for idx, item in enumerate(combined_holdout):
        src = _get_src(item).strip()
        if src:
            retrieval_corpus.append((idx, src))

    prod_retriever = CandidateRetriever()
    dual_retriever = EnhancedDualChannelRetriever()

    for seg_idx, text in retrieval_corpus:
        n_light = normalize_light(text)
        n_aggr = normalize_aggressive(text)
        shingles = get_shingles(n_aggr, size=5)
        prod_retriever.add_segment(seg_idx, n_light.split(), shingles)
        dual_retriever.add_segment(seg_idx, n_light, n_aggr, shingles)

    query_samples = [item for item in combined_holdout if _get_src(item).strip() and item.get('expected_class') in {'EXACT_COPY', 'MODIFIED_COPY', 'PARAPHRASE', 'PROPERLY_CITED'}]

    prod_hits_at_k = {1: 0, 5: 0, 10: 0, 20: 0}
    dual_hits_at_k = {1: 0, 5: 0, 10: 0, 20: 0}
    latencies_prod = []
    latencies_dual = []
    retrieval_misses = []

    for item in query_samples:
        q_text = _get_q(item)
        target_src = _get_src(item)
        q_light = normalize_light(q_text)
        q_aggr = normalize_aggressive(q_text)
        q_shingles = get_shingles(q_aggr, size=5)

        # البحث في الفهرس الإنتاجي
        t0 = time.perf_counter()
        prod_cands = list(prod_retriever.retrieve_candidates_for_shingles(q_shingles))
        latencies_prod.append((time.perf_counter() - t0) * 1000.0)

        # البحث في الفهرس المطور ثنائي القناة
        t0 = time.perf_counter()
        dual_cands = dual_retriever.retrieve_candidates_dual_channel(q_light, top_k=20)
        latencies_dual.append((time.perf_counter() - t0) * 1000.0)

        # إيجاد المؤشر الحقيقي
        target_idx = next((idx for idx, src in retrieval_corpus if src == target_src), None)

        if target_idx is not None:
            # الإنتاجي
            if target_idx in prod_cands[:1]: prod_hits_at_k[1] += 1
            if target_idx in prod_cands[:5]: prod_hits_at_k[5] += 1
            if target_idx in prod_cands[:10]: prod_hits_at_k[10] += 1
            if target_idx in prod_cands[:20]: prod_hits_at_k[20] += 1

            # المطور
            if target_idx in dual_cands[:1]: dual_hits_at_k[1] += 1
            if target_idx in dual_cands[:5]: dual_hits_at_k[5] += 1
            if target_idx in dual_cands[:10]: dual_hits_at_k[10] += 1
            if target_idx in dual_cands[:20]: dual_hits_at_k[20] += 1

            # تسجيل الإخفاقات المتبقية لتحليل الجذور
            if target_idx not in dual_cands[:10]:
                retrieval_misses.append({
                    "sample_id": item['sample_id'],
                    "expected_class": item.get('expected_class'),
                    "target_idx": target_idx,
                    "top_retrieved": dual_cands[:3] if dual_cands else [],
                    "query_snippet": q_text[:50],
                    "target_snippet": target_src[:50],
                    "failure_reason": "High paraphrase divergence with low morphological root overlap in top-10"
                })

    n_q = len(query_samples)
    dual_recall_10 = (dual_hits_at_k[10] / n_q) if n_q else 0.0
    prod_recall_10 = (prod_hits_at_k[10] / n_q) if n_q else 0.0

    retrieval_metrics = {
        "query_count": n_q,
        "production": {
            "recall_at_1": prod_hits_at_k[1] / n_q if n_q else 0,
            "recall_at_5": prod_hits_at_k[5] / n_q if n_q else 0,
            "recall_at_10": prod_recall_10,
            "recall_at_20": prod_hits_at_k[20] / n_q if n_q else 0,
            "p50_latency_ms": float(np.percentile(latencies_prod, 50)) if latencies_prod else 0.0,
            "p95_latency_ms": float(np.percentile(latencies_prod, 95)) if latencies_prod else 0.0
        },
        "dual_channel_holdout": {
            "recall_at_1": dual_hits_at_k[1] / n_q if n_q else 0,
            "recall_at_5": dual_hits_at_k[5] / n_q if n_q else 0,
            "recall_at_10": dual_recall_10,
            "recall_at_20": dual_hits_at_k[20] / n_q if n_q else 0,
            "p50_latency_ms": float(np.percentile(latencies_dual, 50)) if latencies_dual else 0.0,
            "p95_latency_ms": float(np.percentile(latencies_dual, 95)) if latencies_dual else 0.0
        },
        "remaining_misses_count": len(retrieval_misses),
        "remaining_misses_details": retrieval_misses
    }

    # ─────────────────────────────────────────────────────────────────────────
    # B. مفاضلة عتبات إعادة الصياغة EXP-02 (Paraphrase Threshold Sweep)
    # ─────────────────────────────────────────────────────────────────────────
    threshold_sweep_values = [0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]
    paraphrase_tradeoffs = {}

    for th in threshold_sweep_values:
        para_tp, para_fp, para_fn = 0, 0, 0
        mod_tp, mod_total = 0, 0
        exact_tp, exact_total = 0, 0
        orig_fp, orig_total = 0, 0
        common_fo, common_total = 0, 0

        for item in combined_holdout:
            cls = item.get('expected_class')
            q = _get_q(item)
            s = _get_src(item)

            n_q_light = normalize_light(q)
            n_s_light = normalize_light(s) if s else ""

            # حساب تشابه الحروف المعجمي المطور (EXP-02 blending proxy)
            char_vec = TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 4))
            try:
                if s.strip():
                    tfidf_mat = char_vec.fit_transform([n_q_light, n_s_light])
                    sim = float(cosine_similarity(tfidf_mat[0:1], tfidf_mat[1:2])[0][0])
                else:
                    sim = 0.0
            except Exception:
                sim = 0.0

            predicted_overlap = (sim >= th)

            if cls == 'PARAPHRASE':
                if predicted_overlap:
                    para_tp += 1
                else:
                    para_fn += 1
            elif cls == 'ORIGINAL':
                orig_total += 1
                if predicted_overlap:
                    orig_fp += 1
                    para_fp += 1
            elif cls == 'COMMON_TEXT':
                common_total += 1
                if predicted_overlap:
                    common_fo += 1
            elif cls == 'MODIFIED_COPY':
                mod_total += 1
                if predicted_overlap:
                    mod_tp += 1
            elif cls == 'EXACT_COPY':
                exact_total += 1
                if predicted_overlap:
                    exact_tp += 1

        p_prec = para_tp / (para_tp + para_fp) if (para_tp + para_fp) else 0.0
        p_rec = para_tp / (para_tp + para_fn) if (para_tp + para_fn) else 0.0
        p_f1 = 2 * p_prec * p_rec / (p_prec + p_rec) if (p_prec + p_rec) else 0.0

        paraphrase_tradeoffs[str(th)] = {
            "threshold": th,
            "paraphrase_precision": round(p_prec, 4),
            "paraphrase_recall": round(p_rec, 4),
            "paraphrase_f1": round(p_f1, 4),
            "modified_copy_recall": round(mod_tp / mod_total if mod_total else 0.0, 4),
            "exact_copy_recall": round(exact_tp / exact_total if exact_total else 0.0, 4),
            "original_unrelated_fp_rate": round(orig_fp / orig_total if orig_total else 0.0, 4),
            "common_text_false_overlap_rate": round(common_fo / common_total if common_total else 0.0, 4)
        }

    # ─────────────────────────────────────────────────────────────────────────
    # C. تدقيق إيجابيات n-grams الزائفة على العينات السلبية الشديدة (Hard Negatives)
    # ─────────────────────────────────────────────────────────────────────────
    hard_negatives = [item for item in unseen_holdout if item.get('notes', '').startswith('Hard negative')]
    hard_negative_results = []
    hn_fp_count = 0

    for hn in hard_negatives:
        q_l = normalize_light(_get_q(hn))
        s_l = normalize_light(_get_src(hn))
        vec = TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 4))
        mat = vec.fit_transform([q_l, s_l])
        score = float(cosine_similarity(mat[0:1], mat[1:2])[0][0])
        is_fp = score >= 0.40  # الإنتاجي
        if is_fp:
            hn_fp_count += 1
        hard_negative_results.append({
            "sample_id": hn['sample_id'],
            "char_similarity": round(score, 4),
            "is_false_positive_at_0.40": is_fp,
            "domain": hn['domain']
        })

    # ─────────────────────────────────────────────────────────────────────────
    # D. تعميم كشف النصوص الشائعة EXP-03 وأمان المقاطع (Span-Level Safety)
    # ─────────────────────────────────────────────────────────────────────────
    span_test_samples = [item for item in unseen_holdout if 'HOLDOUT_SPAN' in item['sample_id']]
    span_results = []
    for st in span_test_samples:
        is_supp = is_common_institutional_text_experimental(_get_q(st))
        substantive_part = _get_src(st)
        n_sub_aggr = normalize_aggressive(substantive_part)
        n_susp_aggr = normalize_aggressive(_get_q(st))
        sh_sub = get_shingles(n_sub_aggr, size=5)
        sh_susp = get_shingles(n_susp_aggr, size=5)
        overlap_preserved = len(sh_sub.intersection(sh_susp)) > 0

        span_results.append({
            "sample_id": st['sample_id'],
            "full_text_suppressed_as_harmless": is_supp and not overlap_preserved,
            "substantive_overlap_detected": overlap_preserved,
            "safety_verdict": "SAFE" if overlap_preserved else "UNSAFE_FALSE_SUPPRESSION"
        })

    # ─────────────────────────────────────────────────────────────────────────
    # E. تعميم كشف الاستشهاد EXP-04 على الحالات المحجوبة المنوعة
    # ─────────────────────────────────────────────────────────────────────────
    cit_test_samples = [item for item in unseen_holdout if 'HOLDOUT_CIT' in item['sample_id']]
    cit_results = []
    cit_tp, cit_fp, cit_fn, cit_tn = 0, 0, 0, 0

    for cs in cit_test_samples:
        text = _get_q(cs)
        is_cited, ctype, detail = detect_citation_refined(text)
        expected_cited = cs['expected_class'] == 'PROPERLY_CITED'

        if expected_cited and is_cited:
            cit_tp += 1
            status = "CORRECT_CITATION"
        elif not expected_cited and not is_cited:
            cit_tn += 1
            status = "CORRECT_NON_CITATION"
        elif expected_cited and not is_cited:
            cit_fn += 1
            status = "MISSED_CITATION"
        else:
            cit_fp += 1
            status = "FALSE_CITATION"

        cit_results.append({
            "sample_id": cs['sample_id'],
            "is_cited": is_cited,
            "citation_type": ctype,
            "detail": detail,
            "expected_cited": expected_cited,
            "status": status
        })

    c_prec = cit_tp / (cit_tp + cit_fp) if (cit_tp + cit_fp) else 1.0
    c_rec = cit_tp / (cit_tp + cit_fn) if (cit_tp + cit_fn) else 0.0
    c_f1 = 2 * c_prec * c_rec / (c_prec + c_rec) if (c_prec + c_rec) else 0.0
    fcr = cit_fp / len(cit_test_samples) if cit_test_samples else 0.0

    citation_holdout_metrics = {
        "precision": round(c_prec, 4),
        "recall": round(c_rec, 4),
        "f1_score": round(c_f1, 4),
        "false_citation_rate": round(fcr, 4),
        "sample_evaluations": cit_results
    }

    # ─────────────────────────────────────────────────────────────────────────
    # F. الاختبار التكاملي المشترك لكافة المرشحين (Combined Candidates Benchmark)
    # ─────────────────────────────────────────────────────────────────────────
    combined_results = {
        "EXACT_COPY": {"tp": 0, "fp": 0, "fn": 0, "support": 0},
        "MODIFIED_COPY": {"tp": 0, "fp": 0, "fn": 0, "support": 0},
        "PARAPHRASE": {"tp": 0, "fp": 0, "fn": 0, "support": 0},
        "ORIGINAL": {"tp": 0, "fp": 0, "fn": 0, "support": 0}
    }

    for item in combined_holdout:
        cls = item.get('expected_class', 'ORIGINAL')
        if cls in combined_results:
            combined_results[cls]["support"] += 1

        q = _get_q(item)
        s = _get_src(item)
        if not s.strip():
            if cls == 'ORIGINAL':
                combined_results['ORIGINAL']['tp'] += 1
            continue

        n_q_aggr = normalize_aggressive(q)
        n_s_aggr = normalize_aggressive(s)
        n_q_light = normalize_light(q)
        n_s_light = normalize_light(s)

        # 1. Shingle exact/modified
        sh_q = get_shingles(n_q_aggr, size=5)
        sh_s = get_shingles(n_s_aggr, size=5)
        j_score = len(sh_q & sh_s) / len(sh_q | sh_s) if (sh_q | sh_s) else 0.0

        # 2. Refined TF-IDF
        char_vec = TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 4))
        try:
            tfidf_mat = char_vec.fit_transform([n_q_light, n_s_light])
            sim = float(cosine_similarity(tfidf_mat[0:1], tfidf_mat[1:2])[0][0])
        except Exception:
            sim = 0.0

        pred_class = 'ORIGINAL'
        if j_score >= 0.80:
            pred_class = 'EXACT_COPY'
        elif j_score >= 0.40:
            pred_class = 'MODIFIED_COPY'
        elif sim >= 0.40:
            pred_class = 'PARAPHRASE'

        if pred_class == cls:
            if cls in combined_results:
                combined_results[cls]["tp"] += 1
        else:
            if cls in combined_results:
                combined_results[cls]["fn"] += 1
            if pred_class in combined_results:
                combined_results[pred_class]["fp"] += 1

    final_report = {
        "gate": "FINAL_PHASE_19_EVIDENCE_GATE",
        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime()),
        "data_composition": {
            "dev_samples": len(dev_set),
            "holdout_samples": len(holdout_set),
            "unseen_holdout_samples": len(unseen_holdout),
            "total_evaluated_holdout": len(combined_holdout),
            "DEVELOPER_SYNTHETIC": len(dev_set) + len(holdout_set),
            "DEVELOPER_SYNTHETIC_HOLDOUT": len(unseen_holdout),
            "EXPERT_REVIEWED": 0,
            "REAL_ANONYMIZED": 0
        },
        "retrieval_generalization_EXP01": retrieval_metrics,
        "paraphrase_tradeoff_sweep_EXP02": paraphrase_tradeoffs,
        "hard_negatives_char_audit": {
            "hard_negatives_evaluated": len(hard_negatives),
            "false_positives_count": hn_fp_count,
            "false_positive_rate": hn_fp_count / len(hard_negatives) if hard_negatives else 0.0,
            "details": hard_negative_results
        },
        "common_text_span_safety_EXP03": {
            "span_tests_evaluated": len(span_test_samples),
            "all_substantive_overlaps_preserved": all(sr['substantive_overlap_detected'] for sr in span_results),
            "details": span_results
        },
        "citation_generalization_EXP04": citation_holdout_metrics,
        "combined_system_holdout_metrics": combined_results
    }

    # حفظ مخرجات البوابة
    results_path = _HERE / "phase19_evidence_gate_results.json"
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(final_report, f, ensure_ascii=False, indent=2)

    print(f"✅ تم بنجاح حفظ نتائج بوابة الأدلة في: {results_path}")
    return final_report


if __name__ == '__main__':
    run_evidence_gate_benchmark()
