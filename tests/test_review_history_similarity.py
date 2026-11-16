# -*- coding: utf-8 -*-

from plagiarism_detector.detection.candidate_retriever import CandidateRetriever
from plagiarism_detector.reporting import report_builder


PASSAGE = (
    "تعتمد الدراسة على تحليل الأدلة الرقمية وربط النتائج بالسياق المؤسسي "
    "لتحسين دقة القرارات وتوثيق جميع مراحل المراجعة العلمية"
)


def _empty_reference_index():
    return {
        'shingle_size': 4,
        'retriever': CandidateRetriever(),
        'corpus_shingles': [],
        'corpus_light_texts': [],
        'corpus_aggr_texts': [],
        'corpus_metadata': [],
        'vectorizer': None,
        'tfidf_matrix': None,
        'corpus_embeddings': None,
    }


def _history_segment(review_status):
    return {
        'report_id': f'{review_status}-report',
        'research_id': 77,
        'review_status': review_status,
        'title': 'بحث سابق',
        'author': 'باحث تجريبي',
        'page_number': 3,
        'segment_number': 1,
        'raw_text': PASSAGE,
        'normalized_text': '',
    }


def test_preliminary_history_contributes_to_official_similarity(monkeypatch):
    monkeypatch.setattr(report_builder, 'get_pipeline_index', lambda **_: _empty_reference_index())
    monkeypatch.setattr(
        report_builder.report_repo,
        'get_review_history_segments',
        lambda _statuses: [_history_segment('preliminary_accepted')],
    )

    result = report_builder.analyze_academic_document(
        PASSAGE,
        settings_override={'enable_semantic_model': False},
    )

    assert result['overall_pct'] == 100.0
    assert result['rejected_history_pct'] == 0.0
    assert result['segments'][0]['source_review_status'] == 'preliminary_accepted'


def test_rejected_history_is_separate_from_official_similarity(monkeypatch):
    monkeypatch.setattr(report_builder, 'get_pipeline_index', lambda **_: _empty_reference_index())
    monkeypatch.setattr(
        report_builder.report_repo,
        'get_review_history_segments',
        lambda _statuses: [_history_segment('rejected')],
    )

    result = report_builder.analyze_academic_document(
        PASSAGE,
        settings_override={'enable_semantic_model': False},
    )

    assert result['overall_pct'] == 0.0
    assert result['problematic_pct'] == 0.0
    assert result['rejected_history_pct'] == 100.0
    assert result['rejected_history_matches_count'] == 1
    assert result['rejected_history_sources'][0]['title'] == 'بحث سابق'
    assert result['rejected_history_sources'][0]['pct'] == 100.0


def test_partial_history_matches_keep_official_and_rejected_tokens_independent(monkeypatch):
    from plagiarism_detector.detection.span_aligner import alignment_evidence, tokenize_original
    monkeypatch.setattr(report_builder, 'get_pipeline_index', lambda **_: _empty_reference_index())
    monkeypatch.setattr(report_builder, '_get_review_history_index', lambda _: {})
    preliminary = {**_history_segment('preliminary_accepted'), 'raw_text': 'تعتمد الدراسة على تحليل الأدلة الرقمية وربط النتائج'}
    rejected = {**_history_segment('rejected'), 'raw_text': 'وربط النتائج بالسياق المؤسسي لتحسين دقة القرارات'}
    def match(_text, _index, _settings, statuses, _embedding):
        return (preliminary if 'preliminary_accepted' in statuses else rejected, 0.9, 'NEAR COPY')
    monkeypatch.setattr(report_builder, 'match_review_history_segment', match)
    result = report_builder.analyze_academic_document(PASSAGE, settings_override={'enable_semantic_model': False})
    segment = result['segments'][0]
    pre = alignment_evidence(PASSAGE, preliminary['raw_text'], 'p')['matched_suspicious_token_indexes']
    rej = alignment_evidence(PASSAGE, rejected['raw_text'], 'r')['matched_suspicious_token_indexes']
    assert set(pre) != set(rej)
    assert segment['matched_token_indexes'] == pre
    assert segment['rejected_history_match']['matched_token_indexes'] == rej
    assert result['overall_pct'] == round(100 * len(pre) / len(tokenize_original(PASSAGE)), 1)
    assert result['rejected_history_pct'] == round(100 * len(rej) / len(tokenize_original(PASSAGE)), 1)
    assert segment['alignment_evidence'][0]['source_report_id'] == preliminary['report_id']
    from plagiarism_detector.reporting.reviewer_evidence import build_evidence_catalog
    assert build_evidence_catalog(result)[0]['matched_token_indexes'] == pre


def test_semantic_review_history_never_fabricates_lexical_coverage(monkeypatch):
    monkeypatch.setattr(report_builder, 'get_pipeline_index', lambda **_: _empty_reference_index())
    monkeypatch.setattr(report_builder, '_get_review_history_index', lambda _: {})
    monkeypatch.setattr(report_builder, 'match_review_history_segment',
        lambda _text, _index, _settings, statuses, _embedding:
            (_history_segment(next(iter(statuses))), 0.9, 'SEMANTIC PARAPHRASE'))
    result = report_builder.analyze_academic_document(PASSAGE, settings_override={'enable_semantic_model': False})
    assert result['overall_pct'] == result['rejected_history_pct'] == 0.0
    assert result['segments'][0]['alignment_coordinate_status'] == 'semantic_no_lexical_coordinates'
    assert result['segments'][0]['rejected_history_match']['alignment_coordinate_status'] == 'semantic_no_lexical_coordinates'


def test_rejected_history_symbol_noise_never_matches(monkeypatch):
    """المقاطع الرمزية أو الخالية من الكلمات لا تتطابق إطلاقاً مع سجل المرفوضات."""
    monkeypatch.setattr(report_builder, 'get_pipeline_index', lambda **_: _empty_reference_index())
    noisy_segment = {
        'report_id': 'rejected-noise-report',
        'research_id': 99,
        'review_status': 'rejected',
        'title': 'AI AGEDNDA',
        'author': 'Unknown',
        'page_number': 2,
        'segment_number': 3,
        'raw_text': "$%  $  % & '",
        'normalized_text': '',
    }
    monkeypatch.setattr(
        report_builder.report_repo,
        'get_review_history_segments',
        lambda _statuses: [noisy_segment],
    )

    # فحص نص يحتوي على رموز أو مقاطع قصيرة
    query_text = "( %    $ %\nدراسة أكاديمية جديدة تبحث في أمن المعلومات الرقمية والتصدي للهجمات"
    result = report_builder.analyze_academic_document(
        query_text,
        settings_override={'enable_semantic_model': False},
    )

    assert result['rejected_history_pct'] == 0.0
    assert result['rejected_history_matches_count'] == 0
    assert len(result['rejected_history_sources']) == 0


def test_sequence_ratio_empty_and_noise_protection():
    """التحقق من أن sequence_ratio لا ترجع 1.0 للنصوص الفارغة أو الرموز."""
    from plagiarism_detector.detection.shingle_matcher import sequence_ratio, match_exact_or_near_copy

    assert sequence_ratio("", "") == 0.0
    assert sequence_ratio("   ", "") == 0.0
    assert sequence_ratio("abc", "") == 0.0

    res = match_exact_or_near_copy(
        query_shingles=set(),
        query_norm_text="",
        candidate_indices=[0],
        corpus_shingles=[set()],
        corpus_norm_texts=[""],
        threshold=0.33,
    )
    assert res is None

