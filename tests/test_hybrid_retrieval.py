import numpy as np

from plagiarism_detector.detection.hybrid_retrieval import build_semantic_evidence, reciprocal_rank_fusion
from plagiarism_detector.detection.semantic_matcher import rank_semantic_candidates


def test_rrf_keeps_a_semantic_candidate_missing_from_bm25():
    # Candidate 99 is absent from the lexical ranking but must survive fusion.
    fused = reciprocal_rank_fusion({'bm25': [1, 2, 3], 'e5': [99, 2, 1]}, top_k=5, rrf_k=60)
    assert 99 in fused
    assert len(fused) == len(set(fused))


def test_semantic_ranking_is_stable_and_full_corpus_not_bm25_limited():
    query = np.array([1.0, 0.0], dtype=np.float32)
    corpus = np.array([[0.1, 0.9], [1.0, 0.0], [0.8, 0.2]], dtype=np.float32)
    # The relevant semantic candidate at position 1 is not in the supplied
    # lexical subset, but full-corpus semantic ranking retrieves it.
    assert rank_semantic_candidates(query, corpus, candidate_indices=[0, 2], top_k=2)[0][0] == 2
    assert rank_semantic_candidates(query, corpus, top_k=2)[0][0] == 1


def test_semantic_evidence_is_review_only_and_has_no_lexical_coordinates():
    evidence = build_semantic_evidence([(1, 0.91)], [
        {'doc_id': 1, 'title': 'أ', 'reference_id': 'R1', 'page_number': 1},
        {'doc_id': 2, 'title': 'ب', 'reference_id': 'R2', 'page_number': 2},
    ])
    assert evidence[0]['review_required'] is True
    assert evidence[0]['lexical_span_available'] is False
    assert 'suspicious_start' not in evidence[0]
