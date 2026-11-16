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
    if not text_a or not text_b or not text_a.strip() or not text_b.strip():
        return 0.0
    return SequenceMatcher(None, text_a, text_b).ratio()


def match_exact_or_near_copy(
    query_shingles: set[tuple],
    query_norm_text: str,
    candidate_indices: set[int] | list[int],
    corpus_shingles: list[set[tuple]],
    corpus_norm_texts: list[str],
    threshold: float = 0.33,
    min_words: int = 4,
    min_sequence_ratio: float = 0.60,
) -> Optional[tuple[int, float, str]]:
    """
    مقارنة المقطع المدخل بمجموعة المرشحين لكشف النسخ الحرفي أو شبه الحرفي.
    يقيّم كلاً من Jaccard و SequenceMatcher على جميع المرشحين ويختار الأفضل عالمياً.
    يرجع: (أفضل مؤشر مرشح، درجة التشابه من 0 إلى 1، نوع التطابق).
    """
    if not query_norm_text or not query_norm_text.strip():
        return None
    query_words = query_norm_text.split()
    if len(query_words) < min_words:
        return None

    best_idx = -1
    best_score = 0.0
    best_match_type = 'DIRECT COPY'

    candidate_list = list(candidate_indices)

    for idx in candidate_list:
        cand_text = corpus_norm_texts[idx]
        if not cand_text or not cand_text.strip():
            continue
        cand_words = cand_text.split()
        if len(cand_words) < min_words:
            continue

        cand_shingles = corpus_shingles[idx]

        # 1. فحص Jaccard على مستوى الـ Shingles
        if query_shingles and cand_shingles:
            j_score = jaccard_similarity(query_shingles, cand_shingles)
            if j_score > best_score:
                best_score = j_score
                best_idx = idx
                best_match_type = 'DIRECT COPY'

        # 2. فحص SequenceMatcher على مستوى التسلسل الحرفي للكلمات
        #    يُشغَّل على كل مرشح (ليس فقط عند فشل Jaccard) لضمان اختيار الأفضل عالمياً
        seq_score = sequence_ratio(query_norm_text, cand_text)
        # نقبل SequenceMatcher إذا تجاوز الحد الأدنى للنسخ شبه الحرفي (افتراضياً 60%)
        if seq_score >= min_sequence_ratio and seq_score > best_score:
            best_score = seq_score
            best_idx = idx
            best_match_type = 'DIRECT COPY' if seq_score >= 0.95 else 'NEAR COPY'

    if best_score >= threshold and best_idx != -1:
        return best_idx, best_score, best_match_type

    return None
