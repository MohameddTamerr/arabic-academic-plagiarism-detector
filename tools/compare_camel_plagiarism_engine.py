# -*- coding: utf-8 -*-
"""
Scientific Benchmark Comparison: BASELINE vs ENHANCED (CAMeL Tools)
Evaluates:
- Precision, Recall, F1, False Positive Rate across 323 academic evaluation samples
- Passage-level span alignment accuracy & offset fidelity
- Latency (ms) and peak memory (RAM)
"""
import io
import json
import os
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any, Dict, List, Tuple
import psutil

# Ensure paths
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
sys.path.insert(0, str(ROOT / 'vendor'))

import config
from evaluation.evaluator import OVERLAP_CLASSES, COMMON_MARKERS, compute_tfidf_components
from plagiarism_detector.citations.citation_detector import detect_citation
from plagiarism_detector.detection.shingle_matcher import match_exact_or_near_copy
from plagiarism_detector.detection.tfidf_matcher import match_lexical_paraphrase
from plagiarism_detector.detection.span_aligner import align_lexical_spans, tokenize_original
from plagiarism_detector.preprocessing.normalizer import (
    normalize_aggressive as baseline_norm_aggr,
    normalize_light as baseline_norm_light,
    get_shingles,
)
from plagiarism_detector.preprocessing.camel_adapter import (
    is_camel_available,
    camel_normalize_aggressive,
    camel_normalize_light,
    camel_tokenize_with_offsets,
)


def evaluate_sample_with_normalizer(
    query_text: str,
    reference_text: str,
    norm_aggr_fn,
    norm_light_fn,
    k_size: int = 4,
    j_thresh: float = 0.33,
    t_thresh: float = 0.35,
) -> Dict[str, Any]:
    t_start = time.perf_counter()

    q_aggr = norm_aggr_fn(query_text)
    r_aggr = norm_aggr_fn(reference_text)

    is_identical_normalized = (q_aggr == r_aggr and len(q_aggr) > 0)
    q_shingles = get_shingles(q_aggr, size=k_size)
    r_shingles = get_shingles(r_aggr, size=k_size)

    set_q = set(q_shingles)
    set_r = set(r_shingles)
    jaccard_val = len(set_q & set_r) / len(set_q | set_r) if (set_q or set_r) else (1.0 if is_identical_normalized else 0.0)

    exact_res = match_exact_or_near_copy(
        query_shingles=q_shingles,
        query_norm_text=q_aggr,
        candidate_indices=[0],
        corpus_shingles=[r_shingles],
        corpus_norm_texts=[r_aggr],
        threshold=j_thresh
    )
    shingle_score = exact_res[1] if exact_res else 0.0
    shingle_match_type = exact_res[2] if exact_res else 'NONE'

    q_light = norm_light_fn(query_text)
    r_light = norm_light_fn(reference_text)

    para_res = match_lexical_paraphrase(
        query_norm_text=q_light,
        candidate_indices=[0],
        corpus_norm_texts=[r_light],
        threshold=t_thresh
    )
    tfidf_score = para_res[1] if para_res else 0.0

    elapsed_ms = (time.perf_counter() - t_start) * 1000

    if is_identical_normalized or (shingle_match_type == 'DIRECT COPY' and shingle_score >= 0.70):
        overlap_class = 'EXACT_COPY'
    elif shingle_score >= j_thresh or jaccard_val >= j_thresh:
        overlap_class = 'MODIFIED_COPY'
    elif tfidf_score >= t_thresh:
        overlap_class = 'PARAPHRASE'
    else:
        overlap_class = 'ORIGINAL_UNRELATED'

    return {
        'overlap_class': overlap_class,
        'jaccard_score': jaccard_val,
        'shingle_score': shingle_score,
        'tfidf_score': tfidf_score,
        'elapsed_ms': elapsed_ms,
    }


def run_benchmark(mode: str) -> Dict[str, Any]:
    dataset_file = ROOT / 'tests' / 'evaluation' / 'dataset.json'
    with open(dataset_file, 'r', encoding='utf-8') as f:
        dataset = json.load(f)

    if mode == 'BASELINE':
        norm_aggr = baseline_norm_aggr
        norm_light = baseline_norm_light
    elif mode == 'CAMEL':
        norm_aggr = camel_normalize_aggressive
        norm_light = camel_normalize_light
    else:
        raise ValueError(f"Unknown mode: {mode}")

    tracemalloc.start()
    process = psutil.Process()
    start_rss = process.memory_info().rss
    t0 = time.perf_counter()

    confusion = {a: {p: 0 for p in OVERLAP_CLASSES} for a in OVERLAP_CLASSES}
    total_samples = 0
    latencies = []

    for item in dataset:
        expected = item['expected_class']
        if expected not in OVERLAP_CLASSES:
            continue
        total_samples += 1
        query = item['query_text']
        ref = item['reference_text']

        res = evaluate_sample_with_normalizer(query, ref, norm_aggr, norm_light)
        pred = res['overlap_class']
        confusion[expected][pred] += 1
        latencies.append(res['elapsed_ms'])

    total_time = time.perf_counter() - t0
    current_mem, peak_tracemalloc = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    end_rss = process.memory_info().rss
    peak_ram_mb = (end_rss - start_rss) / (1024 * 1024)

    # Calculate Precision, Recall, F1, FPR for each class
    metrics = {}
    for cls in OVERLAP_CLASSES:
        tp = confusion[cls][cls]
        fn = sum(confusion[cls][p] for p in OVERLAP_CLASSES if p != cls)
        fp = sum(confusion[a][cls] for a in OVERLAP_CLASSES if a != cls)
        tn = sum(confusion[a][p] for a in OVERLAP_CLASSES for p in OVERLAP_CLASSES if a != cls and p != cls)

        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0

        metrics[cls] = {
            'tp': tp,
            'fp': fp,
            'fn': fn,
            'tn': tn,
            'precision': round(prec, 4),
            'recall': round(rec, 4),
            'f1_score': round(f1, 4),
            'fpr': round(fpr, 4),
        }

    # Macro-averaged metrics for plagiarism detection (EXACT_COPY + MODIFIED_COPY)
    macro_p = (metrics['EXACT_COPY']['precision'] + metrics['MODIFIED_COPY']['precision']) / 2
    macro_r = (metrics['EXACT_COPY']['recall'] + metrics['MODIFIED_COPY']['recall']) / 2
    macro_f1 = (metrics['EXACT_COPY']['f1_score'] + metrics['MODIFIED_COPY']['f1_score']) / 2

    # False positive rate for non-plagiarized original text
    original_fpr = metrics['ORIGINAL_UNRELATED']['fpr']

    return {
        'mode': mode,
        'total_samples': total_samples,
        'total_time_seconds': round(total_time, 4),
        'avg_latency_ms': round(sum(latencies) / len(latencies), 3) if latencies else 0.0,
        'peak_tracemalloc_mb': round(peak_tracemalloc / (1024 * 1024), 3),
        'metrics': metrics,
        'macro_plagiarism_p': round(macro_p, 4),
        'macro_plagiarism_r': round(macro_r, 4),
        'macro_plagiarism_f1': round(macro_f1, 4),
        'original_unrelated_fpr': round(original_fpr, 4),
        'confusion_matrix': confusion,
    }


def compare_span_alignment() -> Dict[str, Any]:
    """Test passage span alignment comparing baseline tokenizer vs CAMeL offset tokenizer."""
    samples = [
        (
            "أجري الباحث دراسة ميدانية في كلية الحقوق بجامعة القاهرة وتوصل إلى نتائج هامة حول القانون.",
            "قام الباحث بإجراء دراسة ميدانية في كلية الحقوق بجامعة القاهرة وخلص إلى نتائج هامة في القانون."
        ),
        (
            "تعتبر المسؤولية المدنية من أهم الموضوعات القانونية المعاصرة وتخضع لقواعد دقيقة ومحددة في التشريع المصري.",
            "إن المسؤولية المدنية من أهم الموضوعات القانونية المعاصرة وتخضع لضوابط دقيقة ومحددة في التشريع المصري."
        )
    ]
    results = []
    for s_idx, (suspect, source) in enumerate(samples):
        # Baseline alignment
        t0 = time.perf_counter()
        base_aligned = align_lexical_spans(suspect, source)
        base_time = (time.perf_counter() - t0) * 1000

        # CAMeL alignment with offsets
        t1 = time.perf_counter()
        camel_tokens_sus = camel_tokenize_with_offsets(suspect)
        camel_tokens_src = camel_tokenize_with_offsets(source)
        camel_time = (time.perf_counter() - t1) * 1000

        # Verify offset fidelity: text[start:end] == original
        sus_offsets_valid = all(suspect[t.start:t.end] == t.original for t in camel_tokens_sus)
        src_offsets_valid = all(source[t.start:t.end] == t.original for t in camel_tokens_src)

        results.append({
            'sample_idx': s_idx + 1,
            'baseline_spans_count': len(base_aligned.get('spans', [])),
            'baseline_time_ms': round(base_time, 3),
            'camel_tokens_sus_count': len(camel_tokens_sus),
            'camel_tokens_src_count': len(camel_tokens_src),
            'camel_time_ms': round(camel_time, 3),
            'sus_offsets_valid': sus_offsets_valid,
            'src_offsets_valid': src_offsets_valid,
        })
    return {'span_alignment_samples': results}


if __name__ == '__main__':
    print("=" * 70)
    print("RUNNING PLAGIARISM BENCHMARK: BASELINE vs CAMeL TOOLS")
    print("=" * 70)

    print("\n--- 1. Running BASELINE Configuration ---")
    base_res = run_benchmark('BASELINE')
    print(f"Time: {base_res['total_time_seconds']}s | Avg Latency: {base_res['avg_latency_ms']}ms | Peak RAM: {base_res['peak_tracemalloc_mb']}MB")
    print(f"Macro F1 (Plagiarism): {base_res['macro_plagiarism_f1']} | Original FPR: {base_res['original_unrelated_fpr']}")
    for k, v in base_res['metrics'].items():
        print(f"  {k}: P={v['precision']}, R={v['recall']}, F1={v['f1_score']}, FPR={v['fpr']}")

    print("\n--- 2. Running CAMeL TOOLS Configuration ---")
    camel_res = run_benchmark('CAMEL')
    print(f"Time: {camel_res['total_time_seconds']}s | Avg Latency: {camel_res['avg_latency_ms']}ms | Peak RAM: {camel_res['peak_tracemalloc_mb']}MB")
    print(f"Macro F1 (Plagiarism): {camel_res['macro_plagiarism_f1']} | Original FPR: {camel_res['original_unrelated_fpr']}")
    for k, v in camel_res['metrics'].items():
        print(f"  {k}: P={v['precision']}, R={v['recall']}, F1={v['f1_score']}, FPR={v['fpr']}")

    print("\n--- 3. Testing Span Alignment Offset Fidelity ---")
    span_comp = compare_span_alignment()
    for s in span_comp['span_alignment_samples']:
        print(f"Sample {s['sample_idx']}: Baseline {s['baseline_spans_count']} spans ({s['baseline_time_ms']}ms) | CAMeL Sus Valid={s['sus_offsets_valid']}, Src Valid={s['src_offsets_valid']} ({s['camel_time_ms']}ms)")

    output_path = ROOT / 'docs' / 'CAMEL_TOOLS_BENCHMARK_RESULTS.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({'baseline': base_res, 'camel': camel_res, 'span_alignment': span_comp}, f, ensure_ascii=False, indent=2)
    print(f"\nSaved benchmark results to: {output_path}")
