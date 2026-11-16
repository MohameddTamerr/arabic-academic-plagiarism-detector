from plagiarism_detector.detection.span_aligner import (
    alignment_evidence, align_lexical_spans, coverage_from_evidence, tokenize_original,
)


def test_arabic_normalization_returns_original_unicode_offsets():
    source = "إن إدارة الأزمات الأمنية تحمي المسافرين وتدعم التشغيل."
    suspicious = "ان ادارة الازمات الامنية تحمي المسافرين وتدعم التشغيل."
    result = align_lexical_spans(suspicious, source)
    assert result["spans"]
    span = result["spans"][0]
    assert suspicious[span["suspicious_start"]:span["suspicious_end"]] == span["suspicious_text"]
    assert source[span["source_start"]:span["source_end"]] == span["source_text"]
    assert span["token_count"] >= 2


def test_partial_copy_does_not_claim_unmatched_prefix_or_suffix():
    source = "تسهم إدارة المياه في تقليل آثار الجفاف وحماية المجتمعات الزراعية."
    suspicious = "توضح الدراسة أن إدارة المياه في تقليل آثار الجفاف وحماية المجتمعات الزراعية تمثل أولوية."
    result = align_lexical_spans(suspicious, source)
    assert result["spans"]
    text = " ".join(span["suspicious_text"] for span in result["spans"])
    assert "توضح الدراسة" not in text
    assert "أولوية" not in text


def test_multiple_sources_union_does_not_double_count_same_tokens():
    suspicious = "إدارة الأزمات تحمي المسافرين وتدعم التشغيل المستمر"
    first = alignment_evidence(suspicious, "إدارة الأزمات تحمي المسافرين وتدعم التشغيل", "A")
    duplicate = alignment_evidence(suspicious, "إدارة الأزمات تحمي المسافرين وتدعم التشغيل", "B")
    count = len(tokenize_original(suspicious))
    coverage = coverage_from_evidence([first, duplicate], count)
    assert coverage["matched_token_count"] <= count
    assert coverage["coverage"] <= 1.0


def test_reordered_blocks_are_separate_and_word_substitution_is_not_highlighted():
    source = "خطط استباقية وتنسيق أمني يحمي المسافرين واستمرار التشغيل"
    suspicious = "يحمي المسافرين واستمرار التشغيل تنسيق أمني وخطط بديلة"
    result = align_lexical_spans(suspicious, source)
    highlighted = " ".join(item["suspicious_text"] for item in result["spans"])
    assert "خطط بديلة" not in highlighted
    assert result["spans"]


def test_trivial_or_semantic_only_text_has_no_lexical_span():
    assert align_lexical_spans("في من على", "في من على")["spans"] == []
    assert align_lexical_spans(
        "يفيد التخطيط المسبق في حماية الركاب", "تتطلب إدارة الأزمات خططا استباقية لضمان سلامة المسافرين"
    )["spans"] == []


def test_empty_and_long_paragraphs_are_safe():
    assert align_lexical_spans("", "نص مصدر")["spans"] == []
    source = " ".join(["كلمة%d" % i for i in range(250)])
    result = align_lexical_spans(source, source)
    assert result["matched_suspicious_token_indexes"] == list(range(250))
