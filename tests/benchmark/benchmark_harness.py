"""Deterministic Stage 0/1 benchmark; it does not read or write application data."""
from __future__ import annotations

import json
import os
import time
import tracemalloc
from pathlib import Path
from typing import Any

import config
from plagiarism_detector.citations.citation_detector import detect_citation
from plagiarism_detector.detection.candidate_retriever import CandidateRetriever
from plagiarism_detector.detection.semantic_matcher import (
    check_semantic_model_availability, compute_embeddings,
)
from plagiarism_detector.detection.shingle_matcher import match_exact_or_near_copy
from plagiarism_detector.detection.tfidf_matcher import match_lexical_paraphrase
from plagiarism_detector.preprocessing.normalizer import (
    get_shingles, normalize_aggressive, normalize_light,
)
from plagiarism_detector.detection.span_aligner import align_lexical_spans, tokenize_original

HERE = Path(__file__).resolve().parent
DEFAULT_DATASET = HERE / "arabic_benchmark_v1.json"
POSITIVE_CATEGORIES = {
    "EXACT_COPY", "PARTIAL_COPY", "NORMALIZED_COPY", "MODIFIED_COPY",
    "RESTRUCTURED_COPY", "REORDERED_COPY", "SEMANTIC_PARAPHRASE",
    "MULTI_SOURCE_COPY", "CITED_QUOTE", "UNCITED_QUOTE", "OCR_CORRUPTION",
}


def _metric(tp: int, fp: int, fn: int) -> dict[str, float | None]:
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else None
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


def _resolve_span(text: str, span_text: str) -> dict[str, int | str]:
    start = text.find(span_text)
    if start < 0:
        return {"text": span_text, "start": None, "end": None}
    return {"text": span_text, "start": start, "end": start + len(span_text)}


def load_dataset(path: Path = DEFAULT_DATASET) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as stream:
        dataset = json.load(stream)
    source_by_id = {item["source_id"]: item for item in dataset["sources"]}
    for case in dataset["cases"]:
        for span in case["expected_spans"]:
            source = source_by_id[span["source_id"]]
            span["resolved_source_span"] = _resolve_span(source["text"], span["source_text"])
            span["resolved_suspicious_span"] = _resolve_span(case["suspicious_text"], span["suspicious_text"])
            if span["resolved_source_span"]["start"] is None or span["resolved_suspicious_span"]["start"] is None:
                raise ValueError(f"Unresolvable gold span in {case['case_id']}")
    return dataset


def _build_index(dataset: dict[str, Any]) -> dict[str, Any]:
    retriever = CandidateRetriever()
    lights, aggressive, shingles, ids = [], [], [], []
    for idx, source in enumerate(dataset["sources"]):
        light = normalize_light(source["text"])
        aggr = normalize_aggressive(source["text"])
        shingle_set = get_shingles(aggr, config.DEFAULT_SETTINGS["shingle_size"])
        retriever.add_segment(idx, light.split(), shingle_set, norm_light=light)
        lights.append(light)
        aggressive.append(aggr)
        shingles.append(shingle_set)
        ids.append(source["source_id"])
    return {"retriever": retriever, "lights": lights, "aggressive": aggressive, "shingles": shingles, "ids": ids}


def _category_is_flagged(category: str) -> bool:
    return category in POSITIVE_CATEGORIES


def _evaluate_case(case: dict[str, Any], index: dict[str, Any], enable_semantic: bool) -> dict[str, Any]:
    query_light = normalize_light(case["suspicious_text"])
    query_aggr = normalize_aggressive(case["suspicious_text"])
    q_shingles = get_shingles(query_aggr, config.DEFAULT_SETTINGS["shingle_size"])
    exact_candidates = sorted(index["retriever"].retrieve_candidates_for_shingles(q_shingles))
    lexical_candidates = index["retriever"].retrieve_candidates(query_light, top_k=50, mode="dual_channel")
    prediction, score, source_idx = "NONE", None, None
    exact = match_exact_or_near_copy(q_shingles, query_aggr, exact_candidates, index["shingles"], index["aggressive"], threshold=config.DEFAULT_SETTINGS["jaccard_threshold"])
    if exact:
        source_idx, score, kind = exact
        prediction = kind
    elif lexical_candidates:
        lexical = match_lexical_paraphrase(query_light, lexical_candidates, index["lights"], threshold=config.DEFAULT_SETTINGS["tfidf_threshold"])
        if lexical:
            source_idx, score, prediction = lexical

    semantic_score = None
    semantic_source = None
    if enable_semantic:
        q_vectors = compute_embeddings([case["suspicious_text"]], role="query")
        s_vectors = compute_embeddings(index["lights"], role="passage")
        if q_vectors is not None and s_vectors is not None:
            values = s_vectors @ q_vectors[0]
            semantic_source = int(values.argmax())
            semantic_score = float(values[semantic_source])
            # A semantic score is reported as a candidate only; it is never promoted
            # to a confirmed plagiarism prediction by this harness.
    source_id = index["ids"][source_idx] if source_idx is not None else None
    candidate_ids = [index["ids"][i] for i in lexical_candidates]
    return {
        "case_id": case["case_id"], "category": case["category"],
        "predicted": prediction, "predicted_source_id": source_id,
        "candidate_source_ids": candidate_ids, "score": score,
        "citation_detected": detect_citation(case["suspicious_text"]).is_cited,
        "semantic_candidate_source_id": index["ids"][semantic_source] if semantic_source is not None else None,
        "semantic_candidate_score": semantic_score,
    }


def run_benchmark(dataset_path: Path = DEFAULT_DATASET, enable_semantic: bool = True) -> dict[str, Any]:
    """Run entirely in memory. ``tracemalloc`` excludes native ONNX allocations."""
    dataset = load_dataset(dataset_path)
    tracemalloc.start()
    started = time.perf_counter()
    index = _build_index(dataset)
    semantic_status = check_semantic_model_availability()
    semantic_used = bool(enable_semantic and semantic_status.get("available"))
    records = [_evaluate_case(case, index, semantic_used) for case in dataset["cases"]]
    elapsed = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    by_id = {r["case_id"]: r for r in records}
    passage_tp = passage_fp = passage_fn = 0
    attr_total = attr_correct = 0
    r_at = {1: 0, 3: 0, 5: 0}
    r_denominator = 0
    citation_total = citation_correct = 0
    for case in dataset["cases"]:
        record = by_id[case["case_id"]]
        actual = _category_is_flagged(case["category"])
        predicted = record["predicted"] != "NONE"
        if predicted and actual: passage_tp += 1
        elif predicted: passage_fp += 1
        elif actual: passage_fn += 1
        expected_ids = set(case["expected_source_ids"])
        if expected_ids:
            r_denominator += 1
            candidates = record["candidate_source_ids"]
            for k in r_at:
                if expected_ids.intersection(candidates[:k]): r_at[k] += 1
            if record["predicted_source_id"] is not None:
                attr_total += 1
                if record["predicted_source_id"] in expected_ids: attr_correct += 1
        if case["citation_status"] in {"cited", "uncited", "none"}:
            citation_total += 1
            citation_correct += (record["citation_detected"] == (case["citation_status"] == "cited"))

    return {
        "metadata": {
            "dataset_id": dataset["dataset_id"], "origin": dataset["origin"],
            "production_algorithms_modified": False,
            "semantic": {"requested": enable_semantic, "used": semantic_used, "availability": semantic_status},
            "measurement_limitations": [
                "Synthetic regression data only; not real-world accuracy.",
                "Token-level precision/recall/F1 is unavailable: production matchers expose no token spans.",
                "Peak memory is Python tracemalloc only and excludes native ONNX/BLAS allocations.",
                "Semantic candidates are not counted as confirmed plagiarism."
            ],
        },
        "metrics": {
            "passage_detection": _metric(passage_tp, passage_fp, passage_fn),
            "false_positive_rate": passage_fp / sum(1 for c in dataset["cases"] if not _category_is_flagged(c["category"])) if dataset["cases"] else None,
            "retrieval_recall_at_k": {str(k): r_at[k] / r_denominator if r_denominator else None for k in r_at},
            "source_attribution_accuracy": attr_correct / attr_total if attr_total else None,
            "citation_binary_accuracy": citation_correct / citation_total if citation_total else None,
            "token_level": {"precision": None, "recall": None, "f1": None, "reason": "No production token-span output"},
            "runtime_seconds": elapsed, "peak_python_tracemalloc_bytes": peak,
        },
        "records": records,
        "resolved_cases": dataset["cases"],
    }


def run_alignment_benchmark(dataset_path: Path = DEFAULT_DATASET) -> dict[str, Any]:
    """Score exact raw lexical spans only; normalized/semantic spans stay out.

    This deliberately does not fabricate ground-truth character offsets for a
    paraphrase or a normalized form whose raw strings differ.
    """
    dataset = load_dataset(dataset_path)
    sources = {item["source_id"]: item["text"] for item in dataset["sources"]}
    tp = fp = fn = boundary_total = boundary_correct = 0
    evaluated = []
    for case in dataset["cases"]:
        if not case["expected_spans"]:
            continue
        expected_indexes: set[int] = set()
        predicted_indexes: set[int] = set()
        expected_boundaries: set[tuple[int, int]] = set()
        predicted_boundaries: set[tuple[int, int]] = set()
        suspect_tokens = tokenize_original(case["suspicious_text"])
        for expected in case["expected_spans"]:
            resolved = expected["resolved_suspicious_span"]
            expected_boundaries.add((resolved["start"], resolved["end"]))
            expected_indexes.update(
                token.index for token in suspect_tokens
                if token.start >= resolved["start"] and token.end <= resolved["end"]
            )
            aligned = align_lexical_spans(case["suspicious_text"], sources[expected["source_id"]])
            for span in aligned["spans"]:
                predicted_boundaries.add((span["suspicious_start"], span["suspicious_end"]))
            predicted_indexes.update(aligned["matched_suspicious_token_indexes"])
        tp += len(expected_indexes & predicted_indexes)
        fp += len(predicted_indexes - expected_indexes)
        fn += len(expected_indexes - predicted_indexes)
        boundary_total += len(expected_boundaries)
        boundary_correct += len(expected_boundaries & predicted_boundaries)
        evaluated.append(case["case_id"])
    return {
        "evaluated_cases": evaluated,
        "token_metrics": _metric(tp, fp, fn),
        "span_boundary_exactness": boundary_correct / boundary_total if boundary_total else None,
        "counts": {"expected_tokens": tp + fn, "predicted_tokens": tp + fp, "exact_boundaries": boundary_correct, "gold_boundaries": boundary_total},
        "limitations": "Exact raw-span subset only; normalized, reordered, OCR, and semantic cases require token-mapping adjudication before they can be scored fairly.",
    }


if __name__ == "__main__":
    print(json.dumps(run_benchmark(), ensure_ascii=False, indent=2))
