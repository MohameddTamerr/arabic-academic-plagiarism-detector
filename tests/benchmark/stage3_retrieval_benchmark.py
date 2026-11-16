"""Reproducible, local-only Stage 3 candidate-retrieval benchmark.

This is a synthetic scale/regression benchmark. It has no database access and
creates its index only in a temporary directory.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

import psutil

import config
from plagiarism_detector.detection.candidate_retriever import CandidateRetriever
from plagiarism_detector.detection.persistent_retrieval import load_or_reconcile_index, map_persistent_candidates
from plagiarism_detector.preprocessing.normalizer import get_shingles, normalize_aggressive, normalize_light
from tests.benchmark.benchmark_harness import load_dataset


def _rss() -> int:
    return psutil.Process(os.getpid()).memory_info().rss


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))]


def _corpus(dataset: dict[str, Any], size: int) -> tuple[list[dict[str, Any]], dict[str, int]]:
    sources = dataset['sources']
    records: list[dict[str, Any]] = []
    source_to_position: dict[str, int] = {}
    for offset, source in enumerate(sources, start=1):
        records.append({'seg_id': offset * 10, 'doc_id': offset, 'page_number': 1,
                        'segment_number': 1, 'raw_text': source['text'],
                        'normalized_text': normalize_light(source['text']), 'source_id': source['source_id']})
        source_to_position[source['source_id']] = len(records) - 1
    for offset in range(len(records) + 1, size + 1):
        ordinal = offset - len(sources)
        text = (f'تبحث الدراسة الأكاديمية رقم {ordinal} في منهجيات البحث والتعليم '
                f'والتنمية المؤسسية وتحليل البيانات العامة ضمن سياق جامعي مستقل')
        records.append({'seg_id': offset * 10, 'doc_id': offset, 'page_number': 1,
                        'segment_number': 1, 'raw_text': text,
                        'normalized_text': normalize_light(text), 'source_id': f'D{ordinal:04d}'})
    return records, source_to_position


def _recall(source_positions: dict[str, int], dataset: dict[str, Any], search) -> dict[str, float | None]:
    positive = [case for case in dataset['cases'] if case['expected_source_ids']]
    counts = {1: 0, 3: 0, 5: 0, 10: 0}
    for case in positive:
        ranked = search(normalize_light(case['suspicious_text']), 10)
        expected = {source_positions[source_id] for source_id in case['expected_source_ids']}
        for k in counts:
            if expected.intersection(ranked[:k]):
                counts[k] += 1
    return {str(k): counts[k] / len(positive) if positive else None for k in counts}


def _latency(search, dataset: dict[str, Any], repeats: int = 5) -> dict[str, float | int | None]:
    elapsed: list[float] = []
    for _ in range(repeats):
        for case in dataset['cases']:
            start = time.perf_counter()
            search(normalize_light(case['suspicious_text']), 10)
            elapsed.append((time.perf_counter() - start) * 1000)
    return {'p50_ms': _percentile(elapsed, .50), 'p95_ms': _percentile(elapsed, .95), 'samples': len(elapsed)}


def run_retrieval_benchmark(sizes: tuple[int, ...] = (64, 256, 1024)) -> dict[str, Any]:
    dataset = load_dataset()
    all_results = []
    for size in sizes:
        records, source_positions = _corpus(dataset, max(size, len(dataset['sources'])))
        rss_before = _rss()
        legacy = CandidateRetriever()
        start = time.perf_counter()
        for pos, record in enumerate(records):
            legacy.add_segment(pos, record['normalized_text'].split(),
                               get_shingles(normalize_aggressive(record['raw_text']), config.DEFAULT_SETTINGS['shingle_size']),
                               norm_light=record['normalized_text'])
        legacy_build = time.perf_counter() - start
        legacy_search = lambda query, k: legacy.retrieve_candidates(query, top_k=k, mode='dual_channel')

        # The application sandbox may deny the process-global temp directory;
        # keep all benchmark artefacts in the workspace-local temporary area.
        workspace_temp = Path.cwd() / 'tmp'
        workspace_temp.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='stage3-retrieval-', dir=workspace_temp) as temporary:
            index_dir = Path(temporary) / 'index'
            start = time.perf_counter()
            disk_index, disk_info = load_or_reconcile_index(records, 'STAGE3-SYNTH', f'synthetic-{size}', index_dir)
            disk_build = time.perf_counter() - start
            index_size = sum(path.stat().st_size for path in index_dir.rglob('*') if path.is_file())
            position_by_segment = {int(record['seg_id']): pos for pos, record in enumerate(records)}
            disk_search = lambda query, k: map_persistent_candidates(disk_index, query, position_by_segment, k)

            cold_start = time.perf_counter()
            cold_index, cold_info = load_or_reconcile_index(records, 'STAGE3-SYNTH', f'synthetic-{size}', index_dir)
            cold_load = time.perf_counter() - cold_start
            cold_search = lambda query, k: map_persistent_candidates(cold_index, query, position_by_segment, k)
            all_results.append({
                'corpus_segments': len(records), 'synthetic_only': True,
                'legacy': {'build_seconds': legacy_build,
                           'recall_at_k': _recall(source_positions, dataset, legacy_search),
                           'latency': _latency(legacy_search, dataset)},
                'persistent_bm25': {'build_or_reconcile_seconds': disk_build, 'cold_load_seconds': cold_load,
                                    'warm_search_latency': _latency(disk_search, dataset),
                                    'cold_search_latency': _latency(cold_search, dataset),
                                    'recall_at_k': _recall(source_positions, dataset, disk_search),
                                    'storage_bytes': index_size, 'initial_build': disk_info, 'cold_load': cold_info},
                'rss_before_bytes': rss_before, 'rss_after_bytes': _rss(),
                'rss_delta_bytes': _rss() - rss_before,
            })
    return {
        'dataset': 'arabic-plagiarism-synthetic-v1 plus deterministic distractors',
        'limitations': ['Synthetic scale/retrieval regression only; not real-world accuracy.',
                        'RSS is process RSS and includes interpreter/module allocator state from earlier sizes.',
                        'Excludes PDF extraction, OCR, TF-IDF fitting, E5, and report scoring.'],
        'results': all_results,
    }


if __name__ == '__main__':
    print(json.dumps(run_retrieval_benchmark(), ensure_ascii=False, indent=2))
