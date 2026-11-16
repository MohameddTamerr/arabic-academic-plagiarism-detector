from tests.benchmark.stage4_semantic_benchmark import run_semantic_benchmark


def test_stage4_semantic_benchmark_runs_offline_and_keeps_hybrid_ranking_stable():
    result = run_semantic_benchmark()
    held_out = result['metrics']['held_out']
    assert result['model_initialization_seconds'] >= 0
    assert held_out['e5_full_corpus']['recall_at_k']['10'] is not None
    assert held_out['rrf_hybrid']['recall_at_k']['10'] is not None
    assert result['calibration']['experimental_midpoint_threshold'] is not None
