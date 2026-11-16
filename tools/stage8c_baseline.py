#!/usr/bin/env python
"""Local research-only baseline training/evaluation; never used by the app.

Use only trusted artifacts: joblib loading executes pickle data. The held-out
test set must not be used to select features, models, thresholds, or calibration.
"""
import argparse
import hashlib
import json
from pathlib import Path

import joblib
from plagiarism_detector.ai_detection.baseline import validate_input, fit_baseline, evaluate, select_validation_threshold


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['train', 'evaluate'])
    parser.add_argument('--dataset', required=True, type=Path, help='JSON array with declared splits')
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--artifact', required=True, type=Path)
    parser.add_argument('--fixture', action='store_true', help='explicitly permit synthetic test fixtures; never for deployment')
    parser.add_argument('--kind', choices=['logistic', 'svm'], default='logistic')
    parser.add_argument('--features', choices=['word', 'char', 'both'], default='both')
    parser.add_argument('--split', choices=['validation', 'test'], default='validation')
    parser.add_argument('--threshold', type=float, default=0.5, help='research-only; set from validation before test')
    args = parser.parse_args()
    raw = args.dataset.read_bytes()
    records = json.loads(raw)
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    validate_input(records, manifest, fixture=args.fixture)
    digest = hashlib.sha256(raw).hexdigest()
    if args.action == 'train':
        model = fit_baseline(records, args.kind, args.features)
        model['validation_threshold_lt_2pct_fpr'] = select_validation_threshold(model, records)
        model.update(dataset_sha256=digest, fixture=args.fixture)
        # Exclusive creation protects an existing research artifact.
        with args.artifact.open('xb') as output:
            joblib.dump(model, output)
        result = {'status': 'trained_research_only', 'dataset_sha256': digest,
                  'fixture': args.fixture, 'model': args.kind, 'features': args.features,
                  'validation_threshold_lt_2pct_fpr': model['validation_threshold_lt_2pct_fpr']}
    else:
        model = joblib.load(args.artifact)  # trusted local research artifacts only
        if model.get('dataset_sha256') != digest or bool(model.get('fixture')) != args.fixture:
            raise ValueError('dataset or fixture mode differs from training')
        result = evaluate(model, records, split=args.split, threshold=args.threshold)
        result.update(dataset_sha256=digest, fixture=args.fixture, research_only=True)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
