# -*- coding: utf-8 -*-
"""Match submitted passages against preliminary/rejected report history."""

from sklearn.feature_extraction.text import TfidfVectorizer

from plagiarism_detector.detection.evidence_gate import (
    accept_lexical_paraphrase,
    accept_semantic_paraphrase,
)
from plagiarism_detector.detection.semantic_matcher import compute_embeddings, match_semantic_similarity
from plagiarism_detector.detection.shingle_matcher import match_exact_or_near_copy
from plagiarism_detector.detection.tfidf_matcher import match_lexical_paraphrase
from plagiarism_detector.preprocessing.normalizer import (
    get_shingles,
    normalize_aggressive,
    normalize_light,
)


def build_review_history_index(raw_segments: list[dict], settings: dict) -> dict:
    metadata = []
    light_texts = []
    aggressive_texts = []
    shingles = []
    shingle_size = int(settings.get('shingle_size', 4))

    for segment in raw_segments:
        raw_text = str(segment.get('raw_text') or '').strip()
        if not raw_text:
            continue
        light = segment.get('normalized_text') or normalize_light(raw_text)
        aggressive = normalize_aggressive(raw_text)
        metadata.append(dict(segment))
        light_texts.append(light)
        aggressive_texts.append(aggressive)
        shingles.append(get_shingles(aggressive, size=shingle_size))

    vectorizer = None
    tfidf_matrix = None
    if light_texts:
        vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1)
        tfidf_matrix = vectorizer.fit_transform(light_texts)

    embeddings = None
    if light_texts and settings.get('enable_semantic_model', False):
        embeddings = compute_embeddings(light_texts)

    return {
        'metadata': metadata,
        'light_texts': light_texts,
        'aggressive_texts': aggressive_texts,
        'shingles': shingles,
        'vectorizer': vectorizer,
        'tfidf_matrix': tfidf_matrix,
        'embeddings': embeddings,
    }


def match_review_history_segment(
    query_text: str,
    index: dict,
    settings: dict,
    allowed_statuses: set[str],
    query_embedding=None,
):
    """Return the strongest accepted match within the requested review states."""
    metadata = index.get('metadata') or []
    candidates = [
        position for position, item in enumerate(metadata)
        if item.get('review_status') in allowed_statuses
    ]
    if not candidates:
        return None

    query_light = normalize_light(query_text)
    query_aggressive = normalize_aggressive(query_text)
    query_shingles = get_shingles(query_aggressive, size=int(settings.get('shingle_size', 4)))

    exact = match_exact_or_near_copy(
        query_shingles=query_shingles,
        query_norm_text=query_aggressive,
        candidate_indices=candidates,
        corpus_shingles=index['shingles'],
        corpus_norm_texts=index['aggressive_texts'],
        threshold=settings['jaccard_threshold'],
    )
    if exact:
        candidate_index, score, match_type = exact
        return metadata[candidate_index], score, match_type

    lexical = match_lexical_paraphrase(
        query_norm_text=query_light,
        candidate_indices=candidates,
        corpus_norm_texts=index['light_texts'],
        threshold=settings['tfidf_threshold'],
        vectorizer=index.get('vectorizer'),
        corpus_tfidf_matrix=index.get('tfidf_matrix'),
    )
    if lexical:
        candidate_index, score, match_type = lexical
        candidate = metadata[candidate_index]
        if accept_lexical_paraphrase(query_text, candidate['raw_text']):
            return candidate, score, match_type

    embeddings = index.get('embeddings')
    if settings.get('enable_semantic_model', False) and embeddings is not None and query_embedding is not None:
        semantic = match_semantic_similarity(
            query_text=query_text,
            candidate_indices=candidates,
            corpus_texts=index['light_texts'],
            corpus_embeddings=embeddings,
            threshold=settings['semantic_threshold'],
            query_embedding=query_embedding,
        )
        if semantic:
            candidate_index, score, _ = semantic
            candidate = metadata[candidate_index]
            if accept_semantic_paraphrase(
                query_text,
                candidate['raw_text'],
                score,
                settings['semantic_threshold'],
            ):
                return candidate, score, 'SEMANTIC PARAPHRASE'

    return None
