import pytest
from tools.prepare_authorized_ai_data import prepare
from plagiarism_detector.ai_detection.provenance import assess_split_leakage


def manifest():
    return {'dataset_id': 'fixture', 'title': 'fixture', 'version': '1', 'publisher': 'fixture',
        'source_url': 'https://example.invalid', 'license_identifier': 'fixture', 'license_permission': True,
        'acquisition_status': 'ACQUIRED_ISOLATED', 'research_use_authorized': True,
        'authorization_reference': 'test-fixture-only'}


def record(sample_id, label='HUMAN', source='shared'):
    return {'sample_id': sample_id, 'document_id': sample_id, 'source_document_id': source,
        'text': 'هذا نص عربي مصطنع لاختبار أداة تحضير البيانات.', 'provenance_label': label,
        'generator_family': 'NONE' if label == 'HUMAN' else 'test-generator',
        'editing_category': 'NONE', 'academic_domain': 'fixture', 'collection_method': 'test fixture',
        'license_permission': True, 'annotation_confidence': 1.0, 'data_origin': 'DEVELOPER_SYNTHETIC'}


def test_all_variants_stay_together_and_original_text_preserved():
    rows = [record('human'), record('ai', 'AI_GENERATED'), record('polished', 'HUMAN_AI_LIGHT_EDIT')]
    result = prepare(rows, manifest())
    assert len({r['split'] for r in result}) == 1
    assert [r['provenance_label'] for r in result] == [r['provenance_label'] for r in rows]
    assert [r['text'] for r in result] == [r['text'] for r in rows]
    assert not assess_split_leakage(result)['has_leakage']
    assert result == prepare(rows, manifest())


def test_missing_authorization_or_source_is_rejected():
    m = manifest(); m['research_use_authorized'] = False
    with pytest.raises(ValueError, match='permission'):
        prepare([record('a')], m)
    r = record('a'); del r['source_document_id']
    with pytest.raises(ValueError, match='source_document_id'):
        prepare([r], manifest())


def test_mixed_requires_valid_ground_truth_spans():
    r = record('mixed', 'MIXED')
    with pytest.raises(ValueError, match='segment labels'):
        prepare([r], manifest())
    r['segment_labels'] = [{'start': 0, 'end': 5, 'label': 'HUMAN'}, {'start': 4, 'end': 8, 'label': 'AI_GENERATED'}]
    with pytest.raises(ValueError, match='overlapping'):
        prepare([r], manifest())
    r['segment_labels'][1]['start'] = 5
    assert prepare([r], manifest())[0]['segment_labels'] == r['segment_labels']


def test_unauthorized_or_invalid_unicode_is_rejected():
    r = record('a'); r['license_permission'] = False
    with pytest.raises(ValueError, match='permission'):
        prepare([r], manifest())
    r = record('a'); r['text'] += '\ufffd'
    with pytest.raises(ValueError, match='Unicode'):
        prepare([r], manifest())


def test_existing_splits_are_never_silently_reassigned():
    r = record('locked'); r['split'] = 'test'
    with pytest.raises(ValueError, match='already has split'):
        prepare([r], manifest())
