# -*- coding: utf-8 -*-

from plagiarism_detector.detection.evidence_gate import (
    accept_lexical_paraphrase,
    accept_semantic_paraphrase,
)


def test_generic_machine_learning_term_is_not_lexical_evidence():
    query = "AI & Machine Learning Engineer"
    source = "Using Artificial Intelligence and Machine Learning to Identify Terrorist Content Online"
    assert not accept_lexical_paraphrase(query, source)


def test_generic_location_or_contact_terms_are_not_lexical_evidence():
    assert not accept_lexical_paraphrase(
        "Cairo, Egypt | mohamed@example.com",
        "Cairo Egypt: The Institution and its history",
    )


def test_substantive_reworded_passage_can_be_lexical_evidence():
    query = "Deep learning systems improve diagnostic accuracy when doctors examine medical images"
    source = "Diagnostic accuracy for medical images can be improved by deep learning systems"
    assert accept_lexical_paraphrase(query, source)


def test_topic_similarity_below_evidence_confidence_is_rejected():
    assert not accept_semantic_paraphrase(
        "Fourth year computer science student specializing in artificial intelligence and machine learning",
        "طالب متخصص في علوم الحاسب والذكاء الاصطناعي وتعلم الالة وتطبيقاتها الحديثة",
        score=0.75,
        configured_threshold=0.70,
    )


def test_strong_multilingual_passage_level_paraphrase_is_allowed():
    assert accept_semantic_paraphrase(
        "Machine learning systems analyze large medical datasets to help physicians detect disease earlier and improve diagnostic decisions",
        "تحلل انظمة تعلم الالة مجموعات كبيرة من البيانات الطبية لمساعدة الاطباء على اكتشاف المرض مبكرا وتحسين قرارات التشخيص",
        score=0.91,
        configured_threshold=0.70,
    )


def test_strong_arabic_rewording_clears_balanced_semantic_gate():
    assert accept_semantic_paraphrase(
        "تعتمد التنمية المستدامة على تحقيق التوازن بين النمو الاقتصادي وحماية البيئة والعدالة الاجتماعية",
        "لا تتحقق الاستدامة إلا بالجمع بين ازدهار الاقتصاد وصون الموارد الطبيعية وضمان الإنصاف المجتمعي",
        score=0.81,
        configured_threshold=0.80,
    )


def test_borderline_topic_similarity_stays_below_balanced_semantic_gate():
    assert not accept_semantic_paraphrase(
        "تسهم تقنيات الذكاء الاصطناعي في تحسين جودة التعليم من خلال تخصيص المحتوى وفق احتياجات كل طالب",
        "تناقش الدراسة مخاطر استخدام الذكاء الاصطناعي في الجامعات مثل انتهاك الخصوصية والتحيز في القرارات",
        score=0.79,
        configured_threshold=0.80,
    )


def test_short_semantic_match_is_not_enough_even_with_high_score():
    assert not accept_semantic_paraphrase(
        "Machine learning engineer",
        "مهندس تعلم الالة",
        score=0.96,
        configured_threshold=0.70,
    )
