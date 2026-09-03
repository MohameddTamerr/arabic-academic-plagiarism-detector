# -*- coding: utf-8 -*-
"""
المرحلة A: محرك كشف النسخ الحرفي وشبه الحرفي (Stage A - Shingle & Jaccard Matcher):
- يعتمد على متواليات الكلمات (Word Shingles / N-Grams بحجم 5 كلمات).
- يقيس تشابه جاكارد (Jaccard Similarity) ونسبة التطابق التسلسلي (SequenceMatcher).
- يكشف النسخ المباشر، التعديلات الطفيفة، تبديل بعض الكلمات، أو إضافة فواصل.
"""

from difflib import SequenceMatcher
from typing import Optional


def jaccard_similarity(set_a: set, set_b: set) -> float:
    """حساب معامل تشابه جاكارد بين مجموعتين من الـ Shingles."""
    if not set_a or not set_b:
        return 0.0
    inter = len(set_a & set_b)
    union = len(set_a | set_b)
    return inter / union if union > 0 else 0.0


def sequence_ratio(text_a: str, text_b: str) -> float:
    """حساب نسبة التشابه التسلسلي الحقيقي باستخدام SequenceMatcher."""
    return SequenceMatcher(None, text_a, text_b).ratio()


def match_exact_or_near_copy(
    query_shingles: set[tuple],
    query_norm_text: str,
    candidate_indices: set[int] | list[int],
    corpus_shingles: list[set[tuple]],
    corpus_norm_texts: list[str],
    threshold: float = 0.40
) -> Optional[tuple[int, float, str]]:
    """
    مقارنة المقطع المدخل بمجموعة المرشحين لكشف النسخ الحرفي أو شبه الحرفي.
    يرجع: (أفضل مؤشر مرشح، درجة التشابه من 0 إلى 1، نوع التطابق).
    """
    best_idx = -1
    best_score = 0.0
    match_type = 'DIRECT COPY'

    for idx in candidate_indices:
        cand_shingles = corpus_shingles[idx]
        j_score = jaccard_similarity(query_shingles, cand_shingles)

        if j_score > best_score:
            best_score = j_score
            best_idx = idx

    # إذا كان تشابه جاكارد دون العتبة، نفحص تشابه التسلسل للمرشحين بشرط نسبة عالية (>= 65%)
    if best_score < threshold and candidate_indices:
        for idx in candidate_indices:
            seq_score = sequence_ratio(query_norm_text, corpus_norm_texts[idx])
            if seq_score >= 0.65 and seq_score > best_score:
                best_score = seq_score
                best_idx = idx
                match_type = 'NEAR COPY'

    if best_score >= threshold and best_idx != -1:
        return best_idx, best_score, match_type

    return None
