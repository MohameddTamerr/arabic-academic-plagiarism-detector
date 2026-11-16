import pytest
import json
from pathlib import Path

from plagiarism_detector.ai_detection.dataset import assess_dataset_readiness, validate_record
from plagiarism_detector.ai_detection.provenance import (
    assess_split_leakage, find_exact_duplicates, find_near_duplicates,
    has_arabic_content, validate_manifest,
)
from tools.generate_ai_writing_splits import assign_splits


def record(sample_id, text, document_id, **extra):
    return {'sample_id': sample_id, 'text': text, 'document_id': document_id, **extra}


def test_manifest_rejects_acquisition_without_explicit_permission():
    errors = validate_manifest({
        'dataset_id': 'x', 'title': 'x', 'version': '1', 'publisher': 'x',
        'source_url': 'https://example.invalid/x', 'license_identifier': 'unknown',
        'license_permission': False, 'acquisition_status': 'ACQUIRED_ISOLATED',
    })
    assert 'invalid:acquired_without_permission' in errors


def test_manifest_requires_a_version_for_reproducibility():
    errors = validate_manifest({
        'dataset_id': 'x', 'title': 'x', 'publisher': 'x',
        'source_url': 'https://example.invalid/x', 'license_identifier': 'CC-BY-4.0',
        'license_permission': True, 'acquisition_status': 'NOT_ACQUIRED',
    })
    assert 'missing:version' in errors


def test_record_rejects_missing_generator_and_invalid_label():
    errors = validate_record({
        'sample_id': 'x', 'document_id': 'x', 'text': 'نص',
        'provenance_label': 'PREDICTED_AI', 'editing_category': 'NONE',
        'academic_domain': 'unknown', 'collection_method': 'unknown',
        'license_permission': True, 'annotation_confidence': 1.0,
        'data_origin': 'PUBLISHER',
    })
    assert 'missing:generator_family' in errors
    assert 'invalid:provenance_label' in errors


def test_readiness_requires_declared_split_boundaries():
    labels = ['HUMAN', 'AI_GENERATED', 'HUMAN_AI_LIGHT_EDIT', 'AI_HUMAN_EDIT']
    records = [
        {
            'sample_id': label, 'document_id': label, 'text': 'نص عربي ' + label,
            'provenance_label': label, 'generator_family': 'none',
            'editing_category': 'NONE', 'academic_domain': 'education',
            'collection_method': 'verified', 'license_permission': True,
            'annotation_confidence': 1.0, 'data_origin': 'PUBLISHER',
        }
        for label in labels
    ]
    assert assess_dataset_readiness(records)['scientific_readiness'] == 'UNVERIFIED'


def test_normalized_exact_duplicate_is_reported_not_deleted():
    records = [record('a', 'إنَّ البحثَ العلميّ مهم', 'd1'), record('b', 'ان البحث العلمي مهم', 'd2')]
    assert len(find_exact_duplicates(records)) == 1


def test_near_duplicate_detection_preserves_candidates_for_review():
    records = [record('a', 'هذا نص عربي طويل عن البحث العلمي والمنهجية والتحليل', 'd1'),
               record('b', 'هذا نص عربي طويل عن البحث العلمي والمنهجية والتحليل المتقدم', 'd2')]
    assert find_near_duplicates(records, threshold=.5)[0]['left_sample_id'] == 'a'


def test_declared_document_across_splits_is_leakage():
    findings = assess_split_leakage([
        record('a', 'نص', 'document-1', split='train'),
        record('b', 'نص آخر', 'document-1', split='test'),
    ])
    assert findings['has_leakage'] is True
    assert findings['leaks'][0]['field'] == 'document_id'


def test_deterministic_split_is_document_disjoint():
    records = [record('a', 'نص أول', 'd1'), record('b', 'نص ثان', 'd1'), record('c', 'نص ثالث', 'd2')]
    assigned = assign_splits(records, seed='test')
    assert assigned[0]['split'] == assigned[1]['split']
    assert not assess_split_leakage(assigned)['has_leakage']


def test_non_arabic_content_is_detected():
    assert has_arabic_content('Arabic text only') is False
    assert has_arabic_content('نص Arabic') is True


def test_invalid_duplicate_threshold_is_rejected():
    with pytest.raises(ValueError):
        find_near_duplicates([record('a', 'نص', 'd')], threshold=0)


def test_multitude_manifest_does_not_grant_restricted_access():
    manifest_path = Path(__file__).parent / 'benchmark' / 'stage8b_acquisition_manifest.json'
    candidates = json.loads(manifest_path.read_text(encoding='utf-8'))
    candidate = next(item for item in candidates if item['dataset_id'] == 'multitude-arabic')
    assert validate_manifest(candidate) == []
    assert candidate['license_permission'] is False
    assert candidate['acquisition_status'] == 'APPROVAL_REQUIRED'
