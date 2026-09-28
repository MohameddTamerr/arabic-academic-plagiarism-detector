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
