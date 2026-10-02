import numpy as np

from plagiarism_detector.detection.semantic_matcher import (
    batch_match_semantic_similarity,
    match_semantic_similarity,
)


def test_batch_semantic_matches_scalar_results():
    rng = np.random.default_rng(20261002)
    corpus = rng.normal(size=(257, 48)).astype(np.float32)
    queries = rng.normal(size=(19, 48)).astype(np.float32)
    candidates = [idx for idx in range(len(corpus)) if idx % 5 != 0]
    threshold = -1.0

    expected = [
        match_semantic_similarity(
            query_text='',
            candidate_indices=candidates,
            corpus_texts=[],
            corpus_embeddings=corpus,
            threshold=threshold,
            query_embedding=query,
        )
        for query in queries
    ]
    actual = batch_match_semantic_similarity(
        query_embeddings=queries,
        candidate_indices=candidates,
        corpus_embeddings=corpus,
        threshold=threshold,
    )

    assert len(actual) == len(expected)
    for scalar, batched in zip(expected, actual):
        assert scalar is not None
        assert batched is not None
        assert batched[0] == scalar[0]
        assert batched[2] == scalar[2]
        np.testing.assert_allclose(batched[1], scalar[1], rtol=1e-5, atol=1e-6)


def test_batch_semantic_preserves_threshold_and_empty_candidate_behavior():
    corpus = np.eye(3, dtype=np.float32)
    queries = np.array([[1.0, 0.0, 0.0], [0.7, 0.7, 0.0]], dtype=np.float32)

    matches = batch_match_semantic_similarity(queries, [0, 1, 2], corpus, threshold=0.9)
    assert matches[0] is not None and matches[0][0] == 0
    assert matches[1] is None
    assert batch_match_semantic_similarity(queries, [], corpus) == [None, None]


def test_batch_semantic_accepts_one_query_vector():
    corpus = np.eye(2, dtype=np.float32)
    matches = batch_match_semantic_similarity(
        np.array([0.0, 1.0], dtype=np.float32),
        [0, 1],
        corpus,
        threshold=0.8,
    )
    assert len(matches) == 1
    assert matches[0] is not None and matches[0][0] == 1
