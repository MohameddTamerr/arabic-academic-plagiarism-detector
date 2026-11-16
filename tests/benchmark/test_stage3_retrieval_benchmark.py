from tests.benchmark.stage3_retrieval_benchmark import run_retrieval_benchmark


def test_stage3_retrieval_benchmark_is_repeatable_on_small_synthetic_corpus():
    result = run_retrieval_benchmark((16,))
    row = result['results'][0]
    assert row['persistent_bm25']['cold_load']['loaded_from_disk'] is True
    assert row['persistent_bm25']['recall_at_k']['10'] >= row['legacy']['recall_at_k']['10']
    assert row['persistent_bm25']['storage_bytes'] > 0
