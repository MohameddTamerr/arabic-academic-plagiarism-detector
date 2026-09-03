# -*- coding: utf-8 -*-
"""
وحدة تقطيع النصوص وتوليد الفقرات مع الحفاظ على أرقام الصفحات (Document Segmenter):
تحويل صفحات المستند المستخرجة إلى وحدات فحص دقيقة (Segments) مع حفظ البيانات الوصفية.
"""

from dataclasses import dataclass
from typing import Optional

from .normalizer import normalize_light, normalize_aggressive, split_sentences


@dataclass
class DocumentSegment:
    segment_number: int
    page_number: Optional[int]  # None if unavailable (DOCX/TXT)
    raw_text: str
    normalized_light: str
    normalized_aggressive: str
    word_count: int
    is_cited: bool = False
    citation_text: str = ''


def segment_pages(pages: list[dict], min_words: int = 4) -> list[DocumentSegment]:
    """
    تحويل قائمة الصفحات المستخرجة (كل صفحة لها page_number و text) إلى قائمة وحدات فحص (Segments).
    """
    segments: list[DocumentSegment] = []
    seg_counter = 1

    for page in pages:
        p_num = page.get('page_number')
        text = page.get('text', '')
        if not text.strip():
            continue

        from plagiarism_detector.citations.bibliography_detector import is_bibliography_header
        sentences = split_sentences(text, min_words=min_words)
        for sent in sentences:
            n_light = normalize_light(sent)
            n_aggr = normalize_aggressive(sent)
            w_count = len(sent.split())
            if w_count < min_words and not is_bibliography_header(sent):
                continue

            segments.append(DocumentSegment(
                segment_number=seg_counter,
                page_number=p_num,
                raw_text=sent,
                normalized_light=n_light,
                normalized_aggressive=n_aggr,
                word_count=w_count
            ))
            seg_counter += 1

    return segments
