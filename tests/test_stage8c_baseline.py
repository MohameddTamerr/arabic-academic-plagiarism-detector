import copy
import json
import subprocess
import sys
import joblib
import pytest

from plagiarism_detector.ai_detection.baseline import validate_input, fit_baseline, evaluate, probabilities, select_validation_threshold


@pytest.fixture
def fixture_data():
    records = []
    for split in ('train', 'validation', 'test'):
        for i in range(4):
            for label, words in [('HUMAN', 'تحليل الباحث شواهد منهج نقدي'), ('AI_GENERATED', 'خوارزمية نموذج توليد استجابة آلية')]:
                ident = f'{split}-{label}-{i}'
                records.append({'sample_id': ident, 'document_id': ident,
                    'text': f'{words} قسم {split} رقم {i} وثيقة مختلفة', 'provenance_label': label,
                    'generator_family': 'fixture', 'editing_category': 'NONE', 'academic_domain': 'fixture',
                    'collection_method': 'fixture', 'license_permission': True, 'annotation_confidence': 1.0,
                    'data_origin': 'DEVELOPER_SYNTHETIC', 'split': split})
    manifest = {'dataset_id': 'fixture', 'title': 'fixture', 'version': '1', 'publisher': 'test',
        'source_url': 'https://example.invalid', 'license_identifier': 'fixture',
        'license_permission': True, 'acquisition_status': 'ACQUIRED_ISOLATED'}
    return records, manifest


@pytest.mark.parametrize('kind', ['logistic', 'svm'])
@pytest.mark.parametrize('features', ['word', 'char', 'both'])
def test_train_calibrate_evaluate_and_local_reload(fixture_data, tmp_path, kind, features, monkeypatch):
    records, manifest = fixture_data
    validate_input(records, manifest, fixture=True)
    import socket
    monkeypatch.setattr(socket.socket, 'connect', lambda *args, **kwargs: pytest.fail('network access'))
    model = fit_baseline(records, kind, features)
    path = tmp_path / 'fixture.joblib'
    joblib.dump(model, path)
    loaded = joblib.load(path)
    assert probabilities(model, ['فقرة اختبار عربية']).tolist() == probabilities(loaded, ['فقرة اختبار عربية']).tolist()
    metrics = evaluate(loaded, records, split='test', threshold=0.5)
    assert metrics['count'] == 8
    assert sum(sum(row) for row in metrics['confusion_matrix']) == 8
    assert 0 <= metrics['brier_score'] <= 1
    assert metrics['false_positive_rate_wilson_95'][0] <= metrics['false_positive_rate'] <= metrics['false_positive_rate_wilson_95'][1]
    threshold = select_validation_threshold(loaded, records)
    if threshold is not None:
        assert evaluate(loaded, records, split='validation', threshold=threshold)['false_positive_rate'] < 0.02


def test_test_data_is_not_used_for_fit(fixture_data):
    records, _ = fixture_data
    changed = copy.deepcopy(records)
    for r in changed:
        if r['split'] == 'test':
            r['text'] = 'تغيير كلمات مجموعة الاختبار فقط للتأكد من فصل التدريب'
    a, b = fit_baseline(records), fit_baseline(changed)
    assert probabilities(a, ['الباحث يحلل الشواهد العلمية']).tolist() == probabilities(b, ['الباحث يحلل الشواهد العلمية']).tolist()


def test_gate_rejects_synthetic_without_explicit_fixture_mode(fixture_data):
    records, manifest = fixture_data
    with pytest.raises(ValueError):
        validate_input(records, manifest)


def test_gate_rejects_cross_split_duplicate(fixture_data):
    records, manifest = fixture_data
    records[-1]['text'] = records[0]['text']
    with pytest.raises(ValueError, match='duplicate'):
        validate_input(records, manifest, fixture=True)


def test_gate_rejects_missing_permission_and_cross_split_group(fixture_data):
    records, manifest = fixture_data
    manifest['license_permission'] = False
    with pytest.raises(ValueError, match='permission'):
        validate_input(records, manifest, fixture=True)
    manifest['license_permission'] = True
    records[-1]['document_id'] = records[0]['document_id']
    with pytest.raises(ValueError, match='crosses splits'):
        validate_input(records, manifest, fixture=True)


def test_research_cli_trains_and_evaluates_fixture_without_overwrite(fixture_data, tmp_path):
    records, manifest = fixture_data
    data_path, manifest_path, model_path = (tmp_path / 'data.json', tmp_path / 'manifest.json', tmp_path / 'model.joblib')
    data_path.write_text(json.dumps(records, ensure_ascii=False), encoding='utf-8')
    manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
    common = ['--dataset', str(data_path), '--manifest', str(manifest_path), '--artifact', str(model_path), '--fixture']
    train = [sys.executable, '-m', 'tools.stage8c_baseline', 'train', *common]
    result = subprocess.run(train, capture_output=True, text=True, encoding='utf-8', check=True)
    assert json.loads(result.stdout)['status'] == 'trained_research_only'
    assert subprocess.run(train, capture_output=True).returncode != 0
    evaluate_cmd = [sys.executable, '-m', 'tools.stage8c_baseline', 'evaluate', *common, '--split', 'test']
    evaluated = subprocess.run(evaluate_cmd, capture_output=True, text=True, encoding='utf-8', check=True)
    assert json.loads(evaluated.stdout)['fixture'] is True
