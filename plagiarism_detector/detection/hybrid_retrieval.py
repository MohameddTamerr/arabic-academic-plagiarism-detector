"""Experimental Stage 4 lexical/semantic candidate fusion.

The component only ranks candidate positions.  It neither classifies plagiarism
nor emits lexical spans, report percentages, or PDF coordinates.
"""
from __future__ import annotations

from typing import Iterable


def reciprocal_rank_fusion(
    ranked_lists: dict[str, Iterable[int]],
    top_k: int = 50,
    rrf_k: int = 60,
) -> list[int]:
    """Fuse independently retrieved candidate IDs with deterministic RRF."""
    scores: dict[int, float] = {}
    best_rank: dict[int, int] = {}
    for _channel, ranking in ranked_lists.items():
        seen: set[int] = set()
        for rank, candidate in enumerate(ranking, start=1):
            candidate = int(candidate)
            if candidate in seen:
                continue
            seen.add(candidate)
            scores[candidate] = scores.get(candidate, 0.0) + 1.0 / (int(rrf_k) + rank)
            best_rank[candidate] = min(best_rank.get(candidate, rank), rank)
    return [candidate for candidate, _score in sorted(
        scores.items(), key=lambda item: (-item[1], best_rank[item[0]], item[0])
    )[:max(0, int(top_k))]]


def build_semantic_evidence(
    ranked_semantic: list[tuple[int, float]],
    corpus_metadata: list[dict],
    limit: int = 5,
) -> list[dict]:
    """Expose review-only semantic candidate provenance without fake spans."""
    evidence = []
    for position, score in ranked_semantic[:max(0, int(limit))]:
        if position < 0 or position >= len(corpus_metadata):
            continue
        meta = corpus_metadata[position]
        evidence.append({
            'candidate_position': position,
            'source_id': meta.get('doc_id'),
            'source_reference_id': meta.get('reference_id', ''),
            'source_title': meta.get('title', ''),
            'source_page': meta.get('page_number'),
            'semantic_cosine': float(score),
            'review_required': True,
            'lexical_span_available': False,
        })
    return evidence
