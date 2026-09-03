# -*- coding: utf-8 -*-
"""
اختبارات محرك الكشف متعدد المراحل ومنع التكرار (Detection & Pipeline Tests).
"""

from plagiarism_detector.detection.shingle_matcher import (
    jaccard_similarity, match_exact_or_near_copy
)
from plagiarism_detector.detection.tfidf_matcher import match_lexical_paraphrase
from plagiarism_detector.preprocessing.normalizer import (
    normalize_aggressive, normalize_light, get_shingles
)
from plagiarism_detector.reporting.page_allowance import compute_source_allowance
from app.repositories import document_repo
from app.services.paper_service import import_reference_paper


def test_jaccard_similarity_exact():
    """حساب تشابه جاكارد لمجموعتين متطابقتين تماماً."""
    s1 = {('الامن', 'القومي'), ('القومي', 'العربي')}
    s2 = {('الامن', 'القومي'), ('القومي', 'العربي')}
    assert jaccard_similarity(s1, s2) == 1.0


def test_jaccard_similarity_different():
    """تشابه جاكارد لمجموعتين مختلفتين تماماً."""
    s1 = {('الفلسفة', 'الحديثة')}
    s2 = {('الكيمياء', 'العضوية')}
    assert jaccard_similarity(s1, s2) == 0.0


def test_match_exact_copy():
    """كشف النسخ الحرفي المباشر عبر Shingles."""
    src = "التخطيط الاستراتيجي الامني يمثل ركيزة اساسية لحماية المنشات الحيوية في الدولة"
    query = "التخطيط الاستراتيجي الامني يمثل ركيزة اساسية لحماية المنشات الحيوية في الدولة الحديثة"

    src_norm = normalize_aggressive(src)
    q_norm = normalize_aggressive(query)

    src_shingles = [get_shingles(src_norm, size=4)]
    q_shingles = get_shingles(q_norm, size=4)

    res = match_exact_or_near_copy(
        query_shingles=q_shingles,
        query_norm_text=q_norm,
        candidate_indices=[0],
        corpus_shingles=src_shingles,
        corpus_norm_texts=[src_norm],
        threshold=0.35
    )
    assert res is not None
    best_idx, score, m_type = res
    assert best_idx == 0
    assert score >= 0.50
    assert "COPY" in m_type


def test_match_paraphrase():
    """كشف إعادة الصياغة اللفظية التي تحتفظ بالكلمات المفتاحية."""
    src = "الذكاء الاصطناعي يحدث ثورة تكنولوجية شاملة في علوم الحاسب والرعاية الصحية"
    query = "يؤدي استخدام الذكاء الاصطناعي الى احداث تطور تكنولوجي كبير في مجالات الرعاية الصحية وعلوم الحاسب"

    src_norm = normalize_light(src)
    q_norm = normalize_light(query)

    res = match_lexical_paraphrase(
        query_norm_text=q_norm,
        candidate_indices=[0],
        corpus_norm_texts=[src_norm],
        threshold=0.25
    )
    assert res is not None
    best_idx, score, m_type = res
    assert best_idx == 0
    assert score >= 0.25
    assert m_type == 'POSSIBLE PARAPHRASE'


def test_page_allowance_alert():
    """التحقق من تنبيه تجاوز الحد الأقصى للصفحات المسموحة (5 صفحات)."""
    # 1500 كلمة = 6 صفحات بمعدل 250 كلمة/صفحة
    allowance = compute_source_allowance(
        source_id=1,
        source_title="الاستراتيجية الأمنية",
        source_author="د. تامر",
        matched_words=1500,
        matched_pages_set={12, 14, 25},
        words_per_page=250,
        max_allowed_pages=5.0
    )
    assert allowance['is_limit_exceeded'] is True
    assert allowance['estimated_pages'] == 6.0
    assert allowance['matched_source_pages'] == [12, 14, 25]
    assert "تجاوز الحد المسموح" in allowance['alert_message']


def test_duplicate_file_prevention():
    """منع استيراد نفس البحث مرتين بالاعتماد على الـ SHA-256 Hash."""
    import uuid
    uid = uuid.uuid4().hex[:6]
    title = f"بحث تجريبي لفحص التكرار {uid}"
    text = f"هذا نص مخصص لاختبار منع تكرار استيراد نفس المستند المرجعي مرتين في قاعدة الأبحاث رقم {uid}."

    # إضافة أولى
    res1 = import_reference_paper(title=title, author="مؤلف تجريبي", raw_text=text)
    assert res1['success'] is True

    # محاولة إضافة ثانية بنفس العنوان
    res2 = import_reference_paper(title=title, author="مؤلف تجريبي", raw_text=text)
    assert res2['success'] is False
    assert res2['is_duplicate'] is True
