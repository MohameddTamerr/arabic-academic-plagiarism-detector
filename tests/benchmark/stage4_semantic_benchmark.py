"""Offline synthetic Stage 4 E5/BM25/hybrid retrieval evaluation."""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np
import psutil

from plagiarism_detector.detection.candidate_retriever import CandidateRetriever
from plagiarism_detector.detection.hybrid_retrieval import reciprocal_rank_fusion
from plagiarism_detector.detection.persistent_retrieval import load_or_reconcile_index, map_persistent_candidates
from plagiarism_detector.detection.semantic_matcher import compute_embeddings, get_embedder, rank_semantic_candidates
from plagiarism_detector.preprocessing.normalizer import get_shingles, normalize_aggressive, normalize_light

HERE = Path(__file__).resolve().parent
DATASET = HERE / 'stage4_semantic_cases.json'


def _metric(values: list[bool]) -> float | None:
    return sum(values) / len(values) if values else None


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    return values[min(len(values) - 1, int((len(values) - 1) * fraction))]


def _ranking_metrics(records: list[dict], cases: list[dict]) -> dict:
    positives = [case for case in cases if case['expected_source_id']]
    recall = {k: 0 for k in (1, 3, 5, 10)}
    reciprocal = []
    ndcg = {k: [] for k in (1, 3, 5, 10)}
    for case in positives:
        rank = records[case['case_id']]['ranking']
        expected = case['expected_source_id']
        position = next((idx + 1 for idx, source in enumerate(rank) if source == expected), None)
        reciprocal.append(1 / position if position else 0.0)
        for k in recall:
            if position and position <= k:
                recall[k] += 1
                ndcg[k].append(1 / np.log2(position + 1))
            else:
                ndcg[k].append(0.0)
    return {
        'recall_at_k': {str(k): recall[k] / len(positives) if positives else None for k in recall},
        'mrr': sum(reciprocal) / len(reciprocal) if reciprocal else None,
        'ndcg_at_k': {str(k): sum(ndcg[k]) / len(ndcg[k]) if ndcg[k] else None for k in ndcg},
        'positive_cases': len(positives),
    }


def _evaluate_strategy(name: str, cases: list[dict], source_ids: list[str], ranker) -> tuple[dict, list[dict]]:
    records = []
    latency = []
    false_top1 = []
    paraphrase = []
    for case in cases:
        started = time.perf_counter()
        positions = ranker(case['text'])
        latency.append((time.perf_counter() - started) * 1000)
        ranking = [source_ids[position] for position in positions]
        record = {'case_id': case['case_id'], 'ranking': ranking}
        records.append(record)
        if not case['semantic_relevant']:
            false_top1.append(bool(ranking))
        if case['kind'] == 'academic_paraphrase':
            paraphrase.append(case['expected_source_id'] in ranking[:10])
    by_case = {record['case_id']: record for record in records}
    metric = _ranking_metrics(by_case, cases)
    metric.update({
        'strategy': name,
        'paraphrase_candidate_recall_at_10': _metric(paraphrase),
        # Candidate retrieval always returns ranked sources; this count means a
        # non-relevant query has a top candidate, not plagiarism classification.
        'nonrelevant_queries_with_top_candidate_rate': _metric(false_top1),
        'latency_ms': {'p50': _percentile(latency, .50), 'p95': _percentile(latency, .95), 'samples': len(latency)},
    })
    return metric, records


def _end_to_end_latency(cases: list[dict], passage_embeddings: np.ndarray, bm25_rank) -> dict:
    """Measure query embedding plus local ranking, not just vector sorting."""
    e5_elapsed: list[float] = []
    hybrid_elapsed: list[float] = []
    for case in cases:
        started = time.perf_counter()
        vector = compute_embeddings([case['text']], role='query')
        ranked = rank_semantic_candidates(vector[0] if vector is not None else None, passage_embeddings, top_k=10)
        e5_elapsed.append((time.perf_counter() - started) * 1000)
        started = time.perf_counter()
        vector = compute_embeddings([case['text']], role='query')
        semantic = rank_semantic_candidates(vector[0] if vector is not None else None, passage_embeddings, top_k=10)
        reciprocal_rank_fusion({'bm25': bm25_rank(case['text']), 'e5': [item[0] for item in semantic]}, top_k=10, rrf_k=60)
        hybrid_elapsed.append((time.perf_counter() - started) * 1000)
    return {
        'e5_query_plus_rank_ms': {'p50': _percentile(e5_elapsed, .50), 'p95': _percentile(e5_elapsed, .95), 'samples': len(e5_elapsed)},
        'hybrid_query_plus_rank_ms': {'p50': _percentile(hybrid_elapsed, .50), 'p95': _percentile(hybrid_elapsed, .95), 'samples': len(hybrid_elapsed)},
    }


def run_semantic_benchmark() -> dict[str, Any]:
    data = json.loads(DATASET.read_text(encoding='utf-8'))
    sources = data['sources']
    source_ids = [source['source_id'] for source in sources]
    records = [{'seg_id': (idx + 1) * 10, 'doc_id': idx + 1, 'page_number': 1, 'segment_number': 1,
                'raw_text': source['text'], 'normalized_text': normalize_light(source['text'])}
               for idx, source in enumerate(sources)]
    rss_before = psutil.Process(os.getpid()).memory_info().rss
    legacy = CandidateRetriever()
    for position, record in enumerate(records):
        legacy.add_segment(position, record['normalized_text'].split(),
                           get_shingles(normalize_aggressive(record['raw_text']), 4), record['normalized_text'])
    workspace_temp = Path.cwd() / 'tmp'
    workspace_temp.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='stage4-semantic-', dir=workspace_temp) as temporary:
        disk_index, _info = load_or_reconcile_index(records, 'STAGE4-SYNTH', 'stage4-synthetic', Path(temporary) / 'index')
        position_by_segment = {record['seg_id']: pos for pos, record in enumerate(records)}
        init_started = time.perf_counter()
        get_embedder()
        model_init_seconds = time.perf_counter() - init_started
        passage_embeddings = compute_embeddings([source['text'] for source in sources], role='passage')
        queries = compute_embeddings([case['text'] for case in data['cases']], role='query')
        if passage_embeddings is None or queries is None:
            raise RuntimeError('Bundled E5 embedding inference unavailable')
        case_to_embedding = {case['case_id']: queries[idx] for idx, case in enumerate(data['cases'])}
        legacy_rank = lambda text: legacy.retrieve_candidates(normalize_light(text), top_k=10, mode='dual_channel')
        bm25_rank = lambda text: map_persistent_candidates(disk_index, normalize_light(text), position_by_segment, 10)
        semantic_rank = lambda text: [idx for idx, _ in rank_semantic_candidates(case_to_embedding[next(c['case_id'] for c in data['cases'] if c['text'] == text)], passage_embeddings, top_k=10)]
        hybrid_rank = lambda text: reciprocal_rank_fusion({'bm25': bm25_rank(text), 'e5': semantic_rank(text)}, top_k=10, rrf_k=60)
        strategies = {'legacy_lexical': legacy_rank, 'persistent_bm25': bm25_rank, 'e5_full_corpus': semantic_rank, 'rrf_hybrid': hybrid_rank}
        output = {}
        record_output = {}
        for split in ('calibration', 'held_out'):
            cases = [case for case in data['cases'] if case['split'] == split]
            output[split] = {}
            record_output[split] = {}
            for name, ranker in strategies.items():
                metric, rows = _evaluate_strategy(name, cases, source_ids, ranker)
                output[split][name] = metric
                record_output[split][name] = rows
            output[split]['end_to_end_latency'] = _end_to_end_latency(cases, passage_embeddings, bm25_rank)
        calibration_scores = []
        for case in [item for item in data['cases'] if item['split'] == 'calibration']:
            ranked = rank_semantic_candidates(case_to_embedding[case['case_id']], passage_embeddings, top_k=1)
            calibration_scores.append({'case_id': case['case_id'], 'semantic_relevant': case['semantic_relevant'], 'top_cosine': ranked[0][1] if ranked else None})
        negatives = [item['top_cosine'] for item in calibration_scores if not item['semantic_relevant'] and item['top_cosine'] is not None]
        positives = [item['top_cosine'] for item in calibration_scores if item['semantic_relevant'] and item['top_cosine'] is not None]
        experimental_threshold = (max(negatives) + min(positives)) / 2 if negatives and positives else None
        held_out_scores = []
        for case in [item for item in data['cases'] if item['split'] == 'held_out']:
            ranked = rank_semantic_candidates(case_to_embedding[case['case_id']], passage_embeddings, top_k=1)
            score = ranked[0][1] if ranked else None
            held_out_scores.append({'case_id': case['case_id'], 'semantic_relevant': case['semantic_relevant'], 'top_cosine': score})
        tp = fp = fn = 0
        if experimental_threshold is not None:
            for item in held_out_scores:
                predicted = item['top_cosine'] is not None and item['top_cosine'] >= experimental_threshold
                if predicted and item['semantic_relevant']:
                    tp += 1
                elif predicted:
                    fp += 1
                elif item['semantic_relevant']:
                    fn += 1
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else None
        return {
            'dataset': data['dataset_id'], 'origin': data['origin'], 'model_initialization_seconds': model_init_seconds,
            'rss_before_bytes': rss_before, 'rss_after_bytes': psutil.Process(os.getpid()).memory_info().rss,
            'rss_delta_bytes': psutil.Process(os.getpid()).memory_info().rss - rss_before,
            'metrics': output, 'records': record_output,
            'calibration': {'top_scores': calibration_scores, 'experimental_midpoint_threshold': experimental_threshold,
                            'held_out_top_scores': held_out_scores,
                            'held_out_threshold_screen': {'tp': tp, 'fp': fp, 'fn': fn, 'precision': precision, 'recall': recall, 'f1': f1},
                            'warning': 'Derived only from four synthetic calibration cases; not applied to production settings.'},
            'limitations': ['Synthetic developer-authored data only.', 'Non-relevant retrieval candidates are not plagiarism decisions.',
                            'RSS includes model runtime and interpreter state; no independent corpus evaluation.'],
        }


if __name__ == '__main__':
    print(json.dumps(run_semantic_benchmark(), ensure_ascii=True, indent=2))
