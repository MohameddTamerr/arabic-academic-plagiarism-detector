from tests.benchmark.stage5_citation_benchmark import run_citation_benchmark


def test_stage5_synthetic_citation_benchmark_is_reproducible():
    result = run_citation_benchmark()
    assert result['citation_extraction']['precision'] == 1.0
    assert result['citation_extraction']['recall'] == 1.0
    assert result['citation_link_accuracy'] == 1.0
