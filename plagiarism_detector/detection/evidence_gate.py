# -*- coding: utf-8 -*-
"""Quality gates that keep topical similarity from becoming plagiarism evidence."""

import re

from plagiarism_detector.preprocessing.normalizer import normalize_light


_TOKEN_RE = re.compile(r"[A-Za-z\u0600-\u06FF0-9]+", re.UNICODE)

# Small bilingual stop-list.  Domain terms are intentionally not listed: the
# gate rejects a match because too little *combined* evidence is shared, not
# because a particular discipline word is globally ignored.
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in",
    "is", "it", "of", "on", "or", "that", "the", "this", "to", "using", "with",
    "الى", "او", "ان", "التي", "الذي", "على", "عن", "في", "من", "و", "هو", "هي",
    "هذا", "هذه", "ذلك", "تلك", "تم", "مع", "ما", "لا", "كل", "بين",
}


def meaningful_tokens(text: str) -> list[str]:
    """Return normalized content tokens suitable for evidence-quality checks."""
    normalized = normalize_light(text or "").casefold()
    return [
        token
        for token in _TOKEN_RE.findall(normalized)
        if len(token) > 1 and not token.isdigit() and token not in _STOPWORDS
    ]


def accept_lexical_paraphrase(
    query_text: str,
    source_text: str,
    *,
    min_words: int = 6,
    min_shared_terms: int = 4,
    min_shorter_coverage: float = 0.35,
) -> bool:
    """Require a substantive shared idea, not one or two generic terms."""
    query_tokens = meaningful_tokens(query_text)
    source_tokens = meaningful_tokens(source_text)
    if min(len(query_tokens), len(source_tokens)) < min_words:
        return False

    query_terms = set(query_tokens)
    source_terms = set(source_tokens)
    shared = query_terms & source_terms
    shorter_size = min(len(query_terms), len(source_terms))
    coverage = len(shared) / max(1, shorter_size)
    return len(shared) >= min_shared_terms and coverage >= min_shorter_coverage


def accept_semantic_paraphrase(
    query_text: str,
    source_text: str,
    score: float,
    configured_threshold: float,
    *,
    min_words: int = 8,
    evidence_threshold: float = 0.80,
    min_length_ratio: float = 0.45,
) -> bool:
    """Keep strong, passage-level multilingual rephrases and reject loose topics."""
    query_tokens = meaningful_tokens(query_text)
    source_tokens = meaningful_tokens(source_text)
    shorter = min(len(query_tokens), len(source_tokens))
    longer = max(len(query_tokens), len(source_tokens))
    if shorter < min_words or longer == 0:
        return False
    if shorter / longer < min_length_ratio:
        return False
    return float(score) >= max(float(configured_threshold), evidence_threshold)
