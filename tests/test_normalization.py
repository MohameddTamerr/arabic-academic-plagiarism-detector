# -*- coding: utf-8 -*-
"""
اختبارات التطبيع اللغوي العربي بمستوييه الخفيف والمشدد (Normalization Unit Tests).
"""

import pytest
from plagiarism_detector.preprocessing.normalizer import (
    normalize_light,
    normalize_aggressive,
    split_sentences,
    get_shingles
)
from plagiarism_detector.preprocessing.cheating_detector import (
    detect_cheating_manipulation,
    clean_cheating_text
)


def test_normalize_light_preserves_teh_marbuta():
    """التحقق من أن التطبيع الخفيف يحافظ على التاء المربوطة (ة) لتفادي اللبس الدلالي."""
    text = "استراتيجية أمنية دقيقة للمؤسسة"
    norm = normalize_light(text)
    assert 'ة' in norm, "يجب أن تبقى التاء المربوطة في normalize_light"
    assert 'أ' not in norm, "يجب توحيد همزة الألف إلى ا"
    assert norm == "استراتيجية امنية دقيقة للمؤسسة"


def test_normalize_aggressive_converts_teh_marbuta():
    """التحقق من أن التطبيع المشدد يوحد التاء المربوطة إلى هاء لكشف النسخ والتهرب."""
    text = "استراتيجية أمنية دقيقة للمؤسسة"
    norm = normalize_aggressive(text)
    assert 'ة' not in norm, "يجب تحويل التاء المربوطة إلى هاء في normalize_aggressive"
    assert norm == "استراتيجيه امنيه دقيقه للموسسه"


def test_tashkeel_and_tatweel_removal():
    """التحقق من حذف التشكيل والكشيدة (التطويل) في كلا المستويين."""
    text = "بِـسْـمِ اللهِ الرَّحْـمٰـنِ الـرَّحِـيـمِ"
    norm_l = normalize_light(text)
    norm_a = normalize_aggressive(text)
    assert 'ـ' not in norm_l and 'ـ' not in norm_a
    assert 'ِ' not in norm_l and 'ِ' not in norm_a
    assert "بسم الله" in norm_l


def test_alef_variants_unification():
    """توحيد أشكال الألف (أ / إ / آ / ٱ / ى)."""
    text = "أحمد وإبراهيم في القاهرة رأى آثاراً"
    norm_l = normalize_light(text)
    assert "احمد" in norm_l
    assert "ابراهيم" in norm_l
    assert "راي" in norm_l
    assert "اثارا" in norm_l


def test_cheating_zero_width_and_homoglyphs():
    """كشف المسافات الصفرية الخفية والحروف اللاتينية المزروعة."""
    # نص يحتوي مسافة صفرية \u200B وحرف سيريلي 'а'
    cheated_text = "الامـ\u200bـن الـوطـني والقـаـنون"
    report = detect_cheating_manipulation(cheated_text)
    assert report['has_cheating'] is True
    assert report['cheating_count'] >= 2

    cleaned = clean_cheating_text(cheated_text)
    assert '\u200B' not in cleaned
    assert 'а' not in cleaned
    assert "القانون" in cleaned or "والقانون" in cleaned


def test_sentence_splitting():
    """تقسيم النص إلى جمل عربية مفيدة مع استبعاد الجمل الأقصر من الحد الأدنى."""
    text = "هذه جملة أولى مفيدة جداً. نعم! وهنا جملة ثانية توضح الفكرة الرئيسية؟ لا. تمت التجربة بنجاح كبير."
    sentences = split_sentences(text, min_words=4)
    # الجمل "نعم!" و "لا." يجب استبعادها لصغرها
    assert len(sentences) >= 2
    for s in sentences:
        assert len(s.split()) >= 4


def test_shingles_generation():
    """توليد Shingles من متواليات الكلمات."""
    text = "الامن السيبراني والدفاع الالكتروني الوطني"
    shingles = get_shingles(text, size=3)
    assert len(shingles) == 3
    assert ('الامن', 'السيبراني', 'والدفاع') in shingles
