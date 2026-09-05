# -*- coding: utf-8 -*-
"""
محرك استرجاع المرشحين السريع والمحسن (Candidate Retriever & Dual-Channel Index):
- يدعم نمطين للاسترجاع محكومين براية الإعدادات (Feature Flag):
  1. نمط الفهرس ثنائي القناة (Dual-Channel: Word Tokens + Character 3-grams) للإصدار RC2.
  2. نمط الفهرس المعجمي الأساسي (Baseline Word Tokens) للتوافق وإمكانية الرجوع الفوري لـ RC1.
- يمنع المقارنة الشاملة البطيئة O(N x M) عند تضخم قاعدة الأبحاث.
- يعمل بكفاءة استثنائية على المعالجات العادية (CPU-Friendly) مع استهلاك ذاكرة منخفض جداً.
"""

import math
from collections import defaultdict
from typing import Optional, Union, List, Set, Tuple


class CandidateRetriever:
    """فهرس مقلوب سريع في الذاكرة للبحث عن الفقرات المرجعية المرشحة."""

    def __init__(self):
        # كلمة -> مجموعة أرقام المقاطع في الفهرس
        self.word_to_segments: dict[str, set[int]] = defaultdict(set)
        # n-gram حرفي (3 أحرف) -> مجموعة أرقام المقاطع
        self.char_ngrams_to_segments: dict[str, set[int]] = defaultdict(set)
        # shingle -> مجموعة أرقام المقاطع
        self.shingle_to_segments: dict[tuple, set[int]] = defaultdict(set)
        # عدد الكلمات في كل مقطع
        self.segment_word_counts: dict[int, int] = defaultdict(int)
        # إجمالي المقاطع المفهرسة
        self.total_segments: int = 0

    def add_segment(
        self,
        seg_idx: int,
        normalized_words: list[str],
        shingles: set[tuple],
        norm_light: Optional[str] = None
    ):
        """إضافة مقطع إلى الفهرس المقلوب (يدعم القناة الأحادية والثنائية)."""
        self.total_segments += 1
        words = list(normalized_words) if normalized_words else []
        self.segment_word_counts[seg_idx] = len(words)

        # 1. إضافة الكلمات ذات الدلالة (طول 3 أحرف فأكثر)
        for w in set(words):
            if len(w) >= 3:
                self.word_to_segments[w].add(seg_idx)

        # 2. إضافة n-grams الحروف المورفولوجية (char 3-grams)
        if norm_light is None and words:
            norm_light = " ".join(words)

        if norm_light:
            clean_text = "".join(c for c in norm_light if c != " ")
            if len(clean_text) >= 3:
                char_ngrams = set(clean_text[i:i+3] for i in range(len(clean_text) - 2))
                for cng in char_ngrams:
                    self.char_ngrams_to_segments[cng].add(seg_idx)

        # 3. إضافة المتواليات (Shingles)
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
        نمط خط الأساس (RC1 Baseline): استرجاع أعلى top_k مقطع مرجعي حسب عدد الكلمات المشتركة.
        """
        scores: dict[int, int] = defaultdict(int)
        for w in set(query_words):
            if len(w) >= 3 and w in self.word_to_segments:
                for seg_idx in self.word_to_segments[w]:
                    scores[seg_idx] += 1

        if not scores:
            return []

        sorted_candidates = sorted(scores.keys(), key=lambda idx: scores[idx], reverse=True)
        return sorted_candidates[:top_k]

    def retrieve_candidates_dual_channel(
        self,
        query_input: Union[str, list[str]],
        top_k: int = 50
    ) -> list[int]:
        """
        نمط الاسترجاع المطور ثنائي القناة (RC2 EXP-01 Dual-Channel):
        يجمع بين أوزان الكلمات النادرة (Sublinear IDF proxy) وأوزان متواليات الحروف المورفولوجية (Char 3-grams).
        """
        if isinstance(query_input, list):
            words = query_input
            query_light = " ".join(query_input)
        else:
            query_light = str(query_input)
            words = query_light.split()

        scores: dict[int, float] = defaultdict(float)
        tot_seg = max(self.total_segments, 1)

        # 1. قناة الكلمات مع تقدير ندرة المفردة (Sublinear IDF Proxy)
        for w in set(words):
            if len(w) >= 3 and w in self.word_to_segments:
                df = len(self.word_to_segments[w])
                idf_weight = math.log(1.0 + (tot_seg / (1.0 + df)))
                for seg_idx in self.word_to_segments[w]:
                    scores[seg_idx] += 2.0 * idf_weight

        # 2. قناة متواليات الحروف (Char 3-grams) لالتقاط التغيرات الصرفية وإعادة الصياغة
        clean_q = "".join(c for c in query_light if c != " ")
        if len(clean_q) >= 3:
            q_cngs = set(clean_q[i:i+3] for i in range(len(clean_q) - 2))
            for cng in q_cngs:
                if cng in self.char_ngrams_to_segments:
                    df = len(self.char_ngrams_to_segments[cng])
                    idf_weight = math.log(1.0 + (tot_seg / (1.0 + df)))
                    for seg_idx in self.char_ngrams_to_segments[cng]:
                        scores[seg_idx] += 0.2 * idf_weight

        if not scores:
            return []

        sorted_candidates = sorted(scores.keys(), key=lambda idx: scores[idx], reverse=True)
        return sorted_candidates[:top_k]

    def retrieve_candidates(
        self,
        query_input: Union[str, list[str]],
        top_k: int = 50,
        mode: str = 'dual_channel'
    ) -> list[int]:
        """
        الموزع الموحد لاسترجاع المرشحين بناءً على راية التكوين المحددة.
        """
        if mode == 'baseline':
            words = query_input if isinstance(query_input, list) else query_input.split()
            return self.retrieve_candidates_by_tokens(words, top_k=top_k)
        else:
            return self.retrieve_candidates_dual_channel(query_input, top_k=top_k)
