"""Offline Arabic lexical span alignment with original Unicode offsets.

The detector normalizes only token copies used for comparison.  Every returned
offset is an index into the original Python Unicode string, never the
normalized string.  Semantic similarity deliberately has no path here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from difflib import SequenceMatcher
from typing import Iterable

from plagiarism_detector.preprocessing.normalizer import normalize_aggressive

_TOKEN_RE = re.compile(r"[^\s،؛؟!.,:;()\[\]{}«»\"'`]+", re.UNICODE)
_TRIVIAL = {"و", "في", "من", "على", "علي", "الى", "إلى", "الي", "عن", "مع", "أن", "ان", "او", "أو", "ما", "لا", "هذا", "هذه", "الذي", "التي"}


@dataclass(frozen=True)
class OriginalToken:
    original: str
    normalized: str
    start: int
    end: int
    index: int


@dataclass(frozen=True)
class AlignedSpan:
    suspicious_start: int
    suspicious_end: int
    source_start: int
    source_end: int
    suspicious_token_start: int
    suspicious_token_end: int
    source_token_start: int
    source_token_end: int
    suspicious_text: str
    source_text: str
    token_count: int
    kind: str = "lexical"

    def to_dict(self) -> dict:
        return asdict(self)


def tokenize_original(text: str, *, use_camel: bool | None = None) -> list[OriginalToken]:
    """Tokenize original text and retain stable Unicode character boundaries."""
    from plagiarism_detector.preprocessing.normalizer import is_camel_enabled
    if use_camel or (use_camel is None and is_camel_enabled()):
        from plagiarism_detector.preprocessing.camel_adapter import camel_tokenize_with_offsets
        tokens: list[OriginalToken] = []
        for t in camel_tokenize_with_offsets(text):
            tokens.append(OriginalToken(t.original, t.normalized, t.start, t.end, t.index))
        return tokens

    tokens: list[OriginalToken] = []
    for index, match in enumerate(_TOKEN_RE.finditer(text or "")):
        original = match.group(0)
        normalized = normalize_aggressive(original)
        if normalized:
            tokens.append(OriginalToken(original, normalized, match.start(), match.end(), index))
    return tokens


def _substantive(tokens: Iterable[OriginalToken]) -> bool:
    normalized = [token.normalized for token in tokens]
    return any(len(word) > 1 and word not in _TRIVIAL for word in normalized)


def align_lexical_spans(
    suspicious_text: str,
    source_text: str,
    *,
    min_tokens: int = 2,
    allow_single_distinctive_token: bool = False,
    use_camel: bool | None = None,
) -> dict:
    """Return non-trivial exact normalized token blocks and their original offsets.

    ``SequenceMatcher`` yields several blocks around substitutions/insertions and
    around reordered material.  Blocks are accepted independently, so a moved
    phrase remains evidence without treating intervening unmatched words as
    copied.  This is lexical evidence, not a paraphrase/semantic claim.
    """
    suspicious = tokenize_original(suspicious_text, use_camel=use_camel)
    source = tokenize_original(source_text, use_camel=use_camel)
    if not suspicious or not source:
        return {"spans": [], "matched_suspicious_token_indexes": [], "suspicious_tokens": suspicious, "source_tokens": source}

    matcher = SequenceMatcher(
        None, [token.normalized for token in suspicious], [token.normalized for token in source], autojunk=False
    )
    spans: list[AlignedSpan] = []
    matched_indexes: set[int] = set()
    for block in matcher.get_matching_blocks():
        if block.size == 0:
            continue
        suspect_block = suspicious[block.a:block.a + block.size]
        source_block = source[block.b:block.b + block.size]
        acceptable = block.size >= min_tokens and _substantive(suspect_block)
        if allow_single_distinctive_token and block.size == 1:
            acceptable = len(suspect_block[0].normalized) >= 5 and suspect_block[0].normalized not in _TRIVIAL
        if not acceptable:
            continue
        span = AlignedSpan(
            suspicious_start=suspect_block[0].start,
            suspicious_end=suspect_block[-1].end,
            source_start=source_block[0].start,
            source_end=source_block[-1].end,
            suspicious_token_start=suspect_block[0].index,
            suspicious_token_end=suspect_block[-1].index + 1,
            source_token_start=source_block[0].index,
            source_token_end=source_block[-1].index + 1,
            suspicious_text=suspicious_text[suspect_block[0].start:suspect_block[-1].end],
            source_text=source_text[source_block[0].start:source_block[-1].end],
            token_count=block.size,
        )
        spans.append(span)
        matched_indexes.update(range(span.suspicious_token_start, span.suspicious_token_end))
    return {
        "spans": [span.to_dict() for span in spans],
        "matched_suspicious_token_indexes": sorted(matched_indexes),
        "suspicious_tokens": suspicious,
        "source_tokens": source,
    }


def alignment_evidence(
    suspicious_text: str,
    source_text: str,
    source_key: str | int,
    *,
    min_tokens: int = 2,
) -> dict | None:
    """Serialize one source's lexical evidence for reports without DB coupling."""
    aligned = align_lexical_spans(suspicious_text, source_text, min_tokens=min_tokens)
    if not aligned["spans"]:
        return None
    return {
        "source_key": source_key,
        "kind": "lexical",
        "spans": aligned["spans"],
        "matched_suspicious_token_indexes": aligned["matched_suspicious_token_indexes"],
        "matched_token_count": len(aligned["matched_suspicious_token_indexes"]),
        "coordinate_status": "original_text_offsets",
    }


def unique_matched_token_indexes(evidence: Iterable[dict]) -> set[int]:
    """Union submitted-token indexes across sources so overlap cannot inflate score."""
    result: set[int] = set()
    for item in evidence or []:
        if item.get("kind") == "lexical":
            result.update(int(idx) for idx in item.get("matched_suspicious_token_indexes", []) if int(idx) >= 0)
    return result


def coverage_from_evidence(evidence: Iterable[dict], evaluated_token_count: int) -> dict:
    """Return bounded unique-token coverage for a single submitted passage."""
    denominator = max(int(evaluated_token_count or 0), 0)
    indexes = unique_matched_token_indexes(evidence)
    # Ignore malformed indexes outside this passage; never allow >100%.
    indexes = {idx for idx in indexes if idx < denominator}
    numerator = len(indexes)
    return {
        "matched_token_indexes": sorted(indexes),
        "matched_token_count": numerator,
        "evaluated_token_count": denominator,
        "coverage": numerator / denominator if denominator else 0.0,
    }
