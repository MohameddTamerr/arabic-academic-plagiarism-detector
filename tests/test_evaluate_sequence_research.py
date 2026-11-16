"""Evaluation accounting and gates. No detector accuracy is measured here."""

import pytest

from tools.evaluate_sequence_research import evaluate, select_test_records


def test_dataset_rejects_unapproved_and_synthetic_rows():
    with pytest.raises(ValueError, match='attestations'):
        select_test_records([], {}, 'fixture')
    manifest = dict(dataset_use_authorized=True, model_use_authorized=True,
                    independent_evaluation_attested=True, dataset_authorization_reference='fixture',
                    model_authorization_reference='fixture', threshold_reference='fixture',
                    human_threshold=0.25, ai_threshold=0.75, data_sha256='fixture')
    record = dict(sample_id='fixture', document_id='fixture', source_document_id='fixture',
                  text='هذه عينة تجريبية', provenance_label='HUMAN', generator_family='none',
                  editing_category='none', academic_domain='fixture', collection_method='fixture',
                  license_permission=True, annotation_confidence=1, data_origin='DEVELOPER_SYNTHETIC', split='test')
    with pytest.raises(ValueError, match='test split'):
        select_test_records([record], manifest, 'fixture')
    with pytest.raises(ValueError, match='hash'):
        select_test_records([record], manifest, 'different')


def test_confusion_rates_distinguish_abstentions_from_classified_results():
    class ScriptedOutputs:
        batch_size = 2

        def analyze(self, records):
            return [record['fixture_output'] for record in records]

    rows = [
        {'provenance_label': label, 'fixture_output': {'truncated': truncated, 'scores': {'AI_GENERATED': score}}}
        for label, score, truncated in (
            ('HUMAN', 0.10, False), ('HUMAN', 0.85, False), ('HUMAN', 0.50, False),
            ('AI_GENERATED', 0.10, False), ('AI_GENERATED', 0.90, True),
        )
    ]
    metrics = evaluate(ScriptedOutputs(), rows, 0.25, 0.75)
    assert metrics['classified_coverage'] == 3 / 5
    assert metrics['abstention_reasons'] == {'between_thresholds': 1, 'truncated': 1}
    assert metrics['false_positive_rate_all_human'] == 1 / 3
    assert metrics['false_positive_rate_classified_human'] == 1 / 2
    assert metrics['false_negative_rate_all_ai'] == 1 / 2
    assert metrics['false_negative_rate_classified_ai'] == 1
