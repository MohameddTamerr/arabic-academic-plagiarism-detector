from tests.benchmark.benchmark_harness import load_dataset, run_alignment_benchmark, run_benchmark


def test_gold_spans_resolve_and_cover_required_categories():
    dataset = load_dataset()
    categories = {case["category"] for case in dataset["cases"]}
    assert {"EXACT_COPY", "PARTIAL_COPY", "SEMANTIC_PARAPHRASE", "MULTI_SOURCE_COPY", "CITED_QUOTE", "BIBLIOGRAPHY", "OCR_CORRUPTION", "UNRELATED", "SHARED_TERMINOLOGY"} <= categories
    for case in dataset["cases"]:
        for span in case["expected_spans"]:
            assert span["resolved_source_span"]["start"] is not None
            assert span["resolved_suspicious_span"]["start"] is not None


def test_harness_is_deterministic_without_semantic_runtime():
    first = run_benchmark(enable_semantic=False)
    second = run_benchmark(enable_semantic=False)
    assert first["metrics"]["passage_detection"] == second["metrics"]["passage_detection"]
    assert first["metrics"]["retrieval_recall_at_k"] == second["metrics"]["retrieval_recall_at_k"]
    assert first["metrics"]["token_level"]["f1"] is None


def test_alignment_benchmark_reports_real_span_metrics_only_for_labeled_subset():
    result = run_alignment_benchmark()
    assert result["evaluated_cases"]
    assert result["token_metrics"]["precision"] is not None
    assert result["span_boundary_exactness"] is not None
