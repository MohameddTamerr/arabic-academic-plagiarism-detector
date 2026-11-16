# -*- coding: utf-8 -*-
"""Unit tests for CAMeL Tools integration adapter."""
import pytest
from plagiarism_detector.preprocessing.camel_adapter import (
    is_camel_available,
    camel_normalize_unicode,
    camel_normalize_alef,
    camel_normalize_alef_maksura,
    camel_normalize_teh_marbuta,
    camel_dediac,
    camel_normalize_light,
    camel_normalize_aggressive,
    camel_tokenize_words,
    camel_tokenize_with_offsets,
    strip_arabic_proclitics,
    light_stem_or_lemmatize,
    camel_lemmatize_token,
)


def test_camel_availability():
    assert is_camel_available() is True


def test_camel_unicode_normalization():
    # Decomposed vs Composed Arabic characters
    text = "أحمد"
    normalized = camel_normalize_unicode(text)
    assert len(normalized) > 0
    assert "أ" in normalized or "ا" in normalized


def test_camel_alef_normalization():
    text = "أحمد وإبراهيم والآن وٱستخدام"
    normalized = camel_normalize_alef(text)
    assert "أ" not in normalized
    assert "إ" not in normalized
    assert "آ" not in normalized
    assert "ٱ" not in normalized
    assert "احمد وابراهيم والان واستخدام" in normalized


def test_camel_alef_maksura_normalization():
    text = "مستشفى علي"
    normalized = camel_normalize_alef_maksura(text)
    assert "مستشفي" in normalized


def test_camel_teh_marbuta_normalization():
    text = "جامعة القاهرة"
    normalized = camel_normalize_teh_marbuta(text)
    assert "جامعه القاهره" in normalized


def test_camel_dediac():
    diacritized = "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ"
    dediac = camel_dediac(diacritized)
    assert "بِسْمِ" not in dediac
    assert dediac.strip() == "بسم الله الرحمن الرحيم"


def test_camel_normalize_light_preserves_teh_marbuta_and_removes_tatweel():
    text = "جَامِعَـةُ القَاهِـرَةِ أُسِّسَتْ عَامَ"
    norm = camel_normalize_light(text)
    # Teh Marbuta preserved in light normalization
    assert "جامعة" in norm
    assert "القاهرة" in norm
    # Tatweel removed
    assert "ـ" not in norm
    # Diacritics removed
    assert "َ" not in norm
    # Alef unified
    assert "اسست" in norm


def test_camel_normalize_aggressive_converts_teh_marbuta():
    text = "جَامِعَـةُ القَاهِـرَةِ أُسِّسَتْ عَامَ"
    norm = camel_normalize_aggressive(text)
    # Teh Marbuta converted to Ha
    assert "جامعه" in norm
    assert "القاهره" in norm


def test_camel_tokenize_words():
    text = "أجري الباحث دراسة ميدانية في جامعة القاهرة."
    tokens = camel_tokenize_words(text)
    assert isinstance(tokens, list)
    assert "الباحث" in tokens
    assert "دراسة" in tokens
    assert "القاهرة" in tokens


def test_camel_tokenize_with_offsets_preserves_exact_spans():
    text = "أجري الباحث د. أحمد دراسةً علميةً في كلية الحقوق."
    tokens = camel_tokenize_with_offsets(text)
    assert len(tokens) > 0
    for tok in tokens:
        # Guarantee: exact match against original substring
        substring = text[tok.start:tok.end]
        assert substring == tok.original, f"Offset mismatch: expected '{tok.original}', got '{substring}'"
        assert tok.start >= 0
        assert tok.end <= len(text)
        assert tok.end > tok.start


def test_light_lemmatize():
    assert strip_arabic_proclitics("والدراسات") == "دراسات"
    assert strip_arabic_proclitics("بالجامعة") == "جامعة"
    assert light_stem_or_lemmatize("والدراسات") == "دراس"
    assert light_stem_or_lemmatize("للباحثين") == "باحث"
    assert light_stem_or_lemmatize("كتابهم") == "كتاب"


def test_span_alignment_with_camel_tokenization():
    from plagiarism_detector.detection.span_aligner import align_lexical_spans
    suspicious = "ان ادارة الازمات الامنية تحمي المسافرين وتدعم التشغيل."
    source = "إن إدارة الأزمات الأمنية تحمي المسافرين وتدعم التشغيل."
    res = align_lexical_spans(suspicious, source, use_camel=True)
    assert len(res["spans"]) > 0
    span = res["spans"][0]
    assert suspicious[span["suspicious_start"]:span["suspicious_end"]] == span["suspicious_text"]
    assert source[span["source_start"]:span["source_end"]] == span["source_text"]


def test_full_detection_pipeline_with_camel_enabled(monkeypatch):
    import config
    from plagiarism_detector.detection.shingle_matcher import match_exact_or_near_copy
    from plagiarism_detector.preprocessing.normalizer import normalize_aggressive, get_shingles

    monkeypatch.setitem(config.DEFAULT_SETTINGS, 'enable_camel_preprocessing', True)

    query = "أجري الباحث دراسة ميدانية في كلية الحقوق بجامعة القاهرة."
    ref = "اجري الباحث دراسه ميدانيه في كليه الحقوق بجامعه القاهره."

    q_aggr = normalize_aggressive(query)
    r_aggr = normalize_aggressive(ref)
    assert q_aggr == r_aggr

    q_shingles = get_shingles(q_aggr, size=4)
    r_shingles = get_shingles(r_aggr, size=4)
    res = match_exact_or_near_copy(q_shingles, q_aggr, [0], [r_shingles], [r_aggr], threshold=0.33)
    assert res is not None
    assert res[1] >= 0.70


