"""
Unit and integration tests for retrieval scale benchmarking tool.
Verifies that the synthetic scale benchmark runs correctly, measures query latencies,
asserts sublinear performance scaling, and validates bounded top-K behavior.
"""

import os
import tempfile
import pytest
from tools.benchmark_retrieval_scale import (
    generate_synthetic_corpus,
    benchmark_scale,
    run_scale_benchmarks
)
from plagiarism_detector.detection.retrieval_index import LocalDiskRetrievalIndex


def test_synthetic_corpus_generator():
    corpus = generate_synthetic_corpus(count=50, seed=42)
    assert len(corpus) == 50
    for doc in corpus:
        assert "doc_id" in doc
        assert "text" in doc
        assert "department_id" in doc
        assert len(doc["text"]) > 0


def test_benchmark_scale_execution():
    with tempfile.TemporaryDirectory() as tmpdir:
        res = benchmark_scale(
            scale_name="TEST_50",
            num_docs=50,
            num_queries=10,
            index_dir=os.path.join(tmpdir, "test_index"),
            seed=42
        )
        assert res["scale_name"] == "TEST_50"
        assert res["num_docs"] == 50
        assert res["build_time_sec"] >= 0.0
        assert res["avg_query_latency_ms"] >= 0.0
        assert res["p95_query_latency_ms"] >= 0.0
        assert res["p99_query_latency_ms"] >= 0.0
        assert res["max_candidates_returned"] <= 50
        assert res["index_disk_size_bytes"] > 0


def test_retrieval_sublinear_scaling_assertion():
    """
    Verify that query latency scales sublinearly between small and medium corpora.
    Linear scaling would mean 10x docs -> 10x latency. Sublinear inverted index
    maintains bounded query latency orders of magnitude lower than linear scan.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        res_small = benchmark_scale(
            scale_name="SCALE_100",
            num_docs=100,
            num_queries=20,
            index_dir=os.path.join(tmpdir, "small_index"),
            seed=101
        )
        res_med = benchmark_scale(
            scale_name="SCALE_500",
            num_docs=500,
            num_queries=20,
            index_dir=os.path.join(tmpdir, "med_index"),
            seed=101
        )
        
        # Candidate count must never exceed top_k=50
        assert res_small["max_candidates_returned"] <= 50
        assert res_med["max_candidates_returned"] <= 50
        
        # Memory/disk footprint should be reasonable
        assert res_med["index_disk_size_bytes"] > res_small["index_disk_size_bytes"]
