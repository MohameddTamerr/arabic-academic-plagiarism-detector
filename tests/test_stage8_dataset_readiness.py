import json
from pathlib import Path
from plagiarism_detector.ai_detection.dataset import assess_dataset_readiness, validate_record


def test_synthetic_stage8_fixture_is_not_scientifically_ready():
    records = json.loads((Path(__file__).parent / 'benchmark' / 'stage8_ai_writing_synthetic.json').read_text(encoding='utf-8'))
    result = assess_dataset_readiness(records)
    assert result['scientific_readiness'] == 'UNVERIFIED'
    assert result['invalid_records'] == {}


def test_dataset_validator_requires_provenance_and_permission():
    errors = validate_record({'sample_id': 'x', 'text': 'نص'})
    assert 'missing:document_id' in errors
    assert 'invalid:provenance_label' in errors
