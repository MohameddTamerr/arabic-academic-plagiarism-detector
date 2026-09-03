# -*- coding: utf-8 -*-
"""
محرك استرجاع المرشحين السريع (Lightweight Candidate Retriever):
- يستخدم فهراً مقلوباً (Inverted Index) للكلمات والمتواليات لاسترجاع أفضل المرشحين فقط.
- يمنع المقارنة الشاملة البطيئة O(N x M) عند تضخم قاعدة الأبحاث إلى آلاف الصفحات.
- يعمل بكفاءة استثنائية على المعالجات العادية (CPU-Friendly) مع استهلاك ذاكرة منخفض جداً.
"""

from collections import defaultdict
from typing import Optional


class CandidateRetriever:
    """فهرس مقلوب سريع في الذاكرة للبحث عن الفقرات المرجعية المرشحة."""

    def __init__(self):
        # كلمة -> مجموعة أرقام المقاطع في الفهرس
        self.word_to_segments: dict[str, set[int]] = defaultdict(set)
        # shingle -> مجموعة أرقام المقاطع
        self.shingle_to_segments: dict[tuple, set[int]] = defaultdict(set)

    def add_segment(self, seg_idx: int, normalized_words: list[str], shingles: set[tuple]):
        """إضافة مقطع إلى الفهرس المقلوب."""
        # إضافة الكلمات ذات الدلالة (تجاهل الكلمات القصيرة جداً ذات الحرفين)
        for w in set(normalized_words):
            if len(w) >= 3:
                self.word_to_segments[w].add(seg_idx)

        for sh in shingles:
            self.shingle_to_segments[sh].add(seg_idx)

    def retrieve_candidates_for_shingles(self, query_shingles: set[tuple]) -> set[int]:
        """استرجاع المقاطع التي تشترك في shingle واحد على الأقل مع نص الفحص."""
        candidates = set()
        for sh in query_shingles:
            if sh in self.shingle_to_segments:
                candidates.update(self.shingle_to_segments[sh])
        return candidates

    def retrieve_candidates_by_tokens(self, query_words: list[str], top_k: int = 50) -> list[int]:
        """
        استرجاع أعلى top_k مقطع مرجعي يشترك في أكبر عدد من الكلمات مع المقطع المفحوص.
        """
        scores: dict[int, int] = defaultdict(int)
        for w in set(query_words):
            if len(w) >= 3 and w in self.word_to_segments:
                for seg_idx in self.word_to_segments[w]:
                    scores[seg_idx] += 1

        if not scores:
            return []

        # ترتيب المقاطع حسب عدد الكلمات المشتركة
        sorted_candidates = sorted(scores.keys(), key=lambda idx: scores[idx], reverse=True)
        return sorted_candidates[:top_k]
