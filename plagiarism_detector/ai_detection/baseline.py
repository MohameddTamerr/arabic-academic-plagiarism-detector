"""Offline research baselines. These artifacts are never loaded by the app.

Training and calibration use only train/validation; test evaluation is an
explicit separate operation. Serialized sklearn artifacts are trusted-code
objects and must only be loaded from a trusted source.
"""
from __future__ import annotations

from collections import Counter
import math
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.svm import LinearSVC
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix, brier_score_loss

from .dataset import validate_record
from .provenance import assess_split_leakage, find_exact_duplicates, find_near_duplicates, has_arabic_content, validate_manifest

LABELS = {'HUMAN': 0, 'AI_GENERATED': 1}


def validate_input(records, manifest, *, fixture=False):
    """Fail closed on known data issues; curator attestations are not proof."""
    if not records or not isinstance(manifest, dict):
        raise ValueError('records and manifest are required')
    errors = validate_manifest(manifest)
    if errors or not manifest.get('license_permission') or manifest.get('acquisition_status') != 'ACQUIRED_ISOLATED':
        raise ValueError('manifest is invalid or acquisition permission is missing')
    if not fixture and not all(manifest.get(k) is True for k in (
        'provenance_reviewed', 'labels_reviewed', 'near_duplicates_reviewed', 'research_use_authorized'
    )):
        raise ValueError('documented curator reviews and research authorization required')
    ids = set()
    for r in records:
        if validate_record(r) or not r.get('license_permission') or not has_arabic_content(r.get('text')):
            raise ValueError('invalid, unauthorized, or non-Arabic record')
        if r.get('sample_id') in ids or not r.get('sample_id') or not r.get('document_id'):
            raise ValueError('sample IDs must be unique and document IDs required')
        ids.add(r['sample_id'])
        if r.get('split') not in {'train', 'validation', 'test'}:
            raise ValueError('every record requires a valid split')
        if r.get('provenance_label') not in LABELS:
            raise ValueError('binary baseline only accepts HUMAN and AI_GENERATED; keep mixed/edit cases separate')
        if not fixture and r.get('data_origin') in {'SYNTHETIC', 'DEVELOPER_SYNTHETIC'}:
            raise ValueError('synthetic data is allowed only in fixture mode')
    if assess_split_leakage(records)['has_leakage']:
        raise ValueError('declared group crosses splits')
    # Exact and near duplicates crossing splits are never accepted, even when
    # a curator has reviewed the candidate corpus.
    splits = {str(r['sample_id']): r['split'] for r in records}
    if any(len({splits[i] for i in ids}) > 1 for ids in find_exact_duplicates(records).values()):
        raise ValueError('exact duplicate crosses splits')
    if any(splits[p['left_sample_id']] != splits[p['right_sample_id']] for p in find_near_duplicates(records)):
        raise ValueError('near duplicate candidate crosses splits')
    for split in ('train', 'validation', 'test'):
        if {r['provenance_label'] for r in records if r['split'] == split} != set(LABELS):
            raise ValueError(f'{split} requires both binary classes')


def make_pipeline(kind, features='both', max_features=30000):
    if features not in {'word', 'char', 'both'} or kind not in {'logistic', 'svm'}:
        raise ValueError('unknown model or feature configuration')
    vectors = []
    if features in {'word', 'both'}:
        vectors.append(('word', TfidfVectorizer(token_pattern=r'(?u)\b\w+\b', ngram_range=(1, 2), max_features=max_features, dtype=np.float32)))
    if features in {'char', 'both'}:
        vectors.append(('char', TfidfVectorizer(analyzer='char', ngram_range=(3, 5), max_features=max_features, dtype=np.float32)))
    classifier = (LogisticRegression(max_iter=1000, class_weight='balanced', random_state=8)
                  if kind == 'logistic' else LinearSVC(class_weight='balanced', random_state=8))
    return Pipeline([('features', FeatureUnion(vectors)), ('classifier', classifier)])


def fit_baseline(records, kind='logistic', features='both'):
    """Fit train-only vectorizers/classifier and validation-only score calibration."""
    train = [r for r in records if r['split'] == 'train']
    validation = [r for r in records if r['split'] == 'validation']
    pipeline = make_pipeline(kind, features)
    pipeline.fit([r['text'] for r in train], [LABELS[r['provenance_label']] for r in train])
    scores = pipeline.decision_function([r['text'] for r in validation]).reshape(-1, 1)
    calibrator = LogisticRegression(random_state=8).fit(scores, [LABELS[r['provenance_label']] for r in validation])
    return {'pipeline': pipeline, 'calibrator': calibrator, 'kind': kind, 'features': features,
            'research_only': True, 'training_counts': dict(Counter(r['provenance_label'] for r in train)),
            'validation_counts': dict(Counter(r['provenance_label'] for r in validation))}


def probabilities(model, texts):
    scores = model['pipeline'].decision_function(texts).reshape(-1, 1)
    return model['calibrator'].predict_proba(scores)[:, 1]


def select_validation_threshold(model, records, max_fpr=0.02):
    """Select maximum observed recall under a strict validation FPR target.

    An observed FPR is not a confidence bound or deployment acceptance. Return
    None when no threshold yields a true positive and the requested FPR.
    """
    if not 0 < max_fpr <= 1:
        raise ValueError('max_fpr must be in (0, 1]')
    rows = [r for r in records if r['split'] == 'validation']
    y = np.array([LABELS[r['provenance_label']] for r in rows])
    if set(y) != {0, 1}:
        raise ValueError('validation requires both classes')
    p = probabilities(model, [r['text'] for r in rows])
    choices = []
    for threshold in np.unique(p):
        pred = p >= threshold
        fpr = float(np.mean(pred[y == 0]))
        recall = float(np.mean(pred[y == 1]))
        if fpr < max_fpr and recall > 0:
            choices.append((recall, -fpr, float(threshold)))
    return max(choices)[2] if choices else None


def wilson_interval(events, total):
    """Approximate 95% binomial interval, assuming independent observations."""
    z = 1.959963984540054
    p = events / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return [max(0.0, center - half), min(1.0, center + half)]


def evaluate(model, records, *, split, threshold):
    if split not in {'validation', 'test'} or not 0 <= threshold <= 1:
        raise ValueError('valid evaluation split and threshold required')
    rows = [r for r in records if r['split'] == split]
    y = np.array([LABELS[r['provenance_label']] for r in rows])
    if set(y) != {0, 1}:
        raise ValueError('evaluation requires both classes')
    p = probabilities(model, [r['text'] for r in rows])
    pred = (p >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {'split': split, 'count': len(rows), 'threshold': threshold,
            'accuracy': float(accuracy_score(y, pred)), 'precision': float(precision_score(y, pred, zero_division=0)),
            'recall': float(recall_score(y, pred, zero_division=0)), 'f1': float(f1_score(y, pred, zero_division=0)),
            'false_positive_rate': float(fp / (fp + tn)), 'false_negative_rate': float(fn / (fn + tp)),
            'false_positive_rate_wilson_95': wilson_interval(int(fp), int(fp + tn)),
            'false_negative_rate_wilson_95': wilson_interval(int(fn), int(fn + tp)),
            'confusion_matrix': [[int(tn), int(fp)], [int(fn), int(tp)]],
            'brier_score': float(brier_score_loss(y, p))}
